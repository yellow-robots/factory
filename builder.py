#!/usr/bin/env python3
"""The builder: a cold session that changes a checkout until its tests pass.

    uv run builder.py <checkout> "<goal>"

The checkout is the directory named on the command line, reachable only through six tools:
list, read, search, write, edit and check. Writes are confined to the checkout and refused on the goal's
tests and the toolchain; check runs the checkout's tests in a container with no network and the
checkout mounted read-only, so code the model writes never runs on the host and cannot reach the
key. The loop is pydantic-ai, pinned; the provider is DeepSeek's chat completions API, the key
read from ~/.config/factory/deepseek.key and never written anywhere. When the model returns,
whatever ended the run, the builder runs the check once more on the tree as it then is, unless
nothing was written or edited since the model's last check, so the record's check is the tree
the run left. Each run leaves a record
under the store the instance's configuration names, outside the checkout, with goal.txt,
wire.jsonl.gz (every HTTP attempt as it happened, compressed once the run ends), messages.json
(the library's messages), check-<n>.log per check, diff.patch (what the run left in the checkout; absent when it left nothing),
report.json, response.md (the report rendered) and numbers.json.
"""

from __future__ import annotations

import fnmatch
import gzip
import hashlib
import importlib.metadata
import json
import os
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from instance import _read_config, instance_config, key_paths, record_store, role as instance_role

# Before the import: the library greets stderr once per process unless this is set.
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

import genai_prices  # noqa: E402
import httpx2  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402
from pydantic_ai import (  # noqa: E402
    Agent,
    ModelAPIError,
    ModelMessagesTypeAdapter,
    RunUsage,
    Tool,
    UnexpectedModelBehavior,
    UsageLimitExceeded,
    UsageLimits,
    capture_run_messages,
)
from pydantic_ai.messages import RetryPromptPart  # noqa: E402
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIChatModelSettings  # noqa: E402
from pydantic_ai.models.wrapper import WrapperModel  # noqa: E402
from openai import AsyncOpenAI  # noqa: E402
from pydantic_ai.profiles.openai import OpenAIModelProfile  # noqa: E402
from pydantic_ai.providers.deepseek import DeepSeekProvider  # noqa: E402

KEY_FILE = Path.home() / ".config" / "factory" / "deepseek.key"
MODEL = "deepseek-flash"
LIBRARY = "pydantic-ai-slim " + importlib.metadata.version("pydantic-ai-slim")
# The two backstops, fixed rather than derived from anything: a cheap counter that catches a runaway
# beside the spend, which is the bound that means something. Neither binds before the spend on any
# run the store has ever seen: at the expensive end a request costs 0.0040 USD, so HARD_SPEND at 0.25
# is reached within 120 requests, and the store's deepest builds sit far below both. REQUEST_LIMIT is
# above CALLS_LIMIT for the reason it always has: a run that has spent its calls must still have the
# requests to say what it did, the failure of v0.15 the landing exists to prevent.
CALLS_LIMIT = 200  # tool calls one run may make before the tools land it; a backstop, not a budget
REQUEST_LIMIT = 250  # requests the library allows; above CALLS_LIMIT, so a landed run can report
# What a run may spend, from the store: a ceiling of 0.125 sits above every one of the 85 builds
# that answered and below six of the 13 that were capped. The tools land a run there; twice it is
# the backstop for a run that will not land, a guard and not a tuned threshold.
SOFT_SPEND = 0.125  # USD a run may spend before every tool refuses and says report now
HARD_SPEND = 0.25  # USD, twice the soft ceiling: the runaway's backstop, derived from nothing
LIST_CAP = 500  # entries per list
READ_LINES_CAP = 1000  # lines per read
READ_BYTES_CAP = 64_000  # bytes per read
SEARCH_LINES_CAP = 100  # matches per search
SEARCH_BYTES_CAP = 32_000  # bytes per search
SEARCH_FILE_CAP = 1_000_000  # bytes of one file search will read; a larger file is not searched
WRITE_CAP = 30  # writes and edits per run, together
CHECK_CAP = 8  # checks per run
# What green means, in the checkout's own terms. -P keeps the checkout's root off sys.path while
# the runner is imported, or a file named unittest.py at the checkout root shadows the stdlib and
# turns any suite green; `discover` still finds the checkout's tests and puts the root back for them.
CHECK_CMD = ("python", "-P", "-m", "unittest", "discover", "-q")
CHECK_TIMEOUT = 120  # seconds for one check, then the container is killed
# Tasks the check's container may hold at once, a guard against a fork bomb and not a wall: the
# walls are the read-only mount, `--network none`, the memory and the CPUs. It counts threads as
# well as processes, and the factory's own suite accumulates them, so 256 -- where every module
# passed alone and the suite did not -- stopped the factory building itself on 2026-09-20. Why the
# suite holds so many at once is its own seed; this is the headroom until that is answered.
PIDS_LIMIT = 1024
CHECK_TAIL_LINES = 60  # lines of check output handed back
CHECK_TAIL_BYTES = 8_000  # and at most this many bytes of them
IMAGE_TIMEOUT = 600  # seconds for the one image build
# Hidden at the root because they are the checkout's machinery, not its content: the caches,
# git, and `runs`, the record's old place that a project may still have. The record itself is
# the instance's store now, outside the checkout; .git is the human's record and its hooks run
# on the host. A caller that needs more hidden -- the evaluation harness hides its own `cases`
# -- names them through main's `hidden` argument, so a checkout of another program keeps its
# ordinary names.
HIDDEN = ("runs", ".claude", "__pycache__", ".venv", ".git")


def limits() -> UsageLimits:
    """The library's caps for a run: the two fixed constants, read here at the moment they are
    asked for rather than derived from the checkout or from anything else. The tools refuse at
    `CALLS_LIMIT`; `REQUEST_LIMIT` is above it, so a run that spent its calls still has the requests
    to report, and the request limit can never cut a landed run off before the tools say stop."""
    return UsageLimits(tool_calls_limit=CALLS_LIMIT, request_limit=REQUEST_LIMIT)


def which_cap(stopped: str, detail: str) -> str:
    """Which cap ended a run, from what `run` returns: `calls` when the library's tool-call limit
    raised, `requests` when its request limit did, `spend` when the hard spend ceiling did, and the
    empty string when no cap ended the run or the detail names none rather than guessing."""
    if stopped != "cap":
        return ""
    if "tool_calls_limit" in detail:
        return "calls"
    if "request_limit" in detail:
        return "requests"
    if "spend" in detail:  # the hard spend ceiling, raised from a tool
        return "spend"
    return ""


# Refused to write and edit: the tests are the goal's acceptance criteria, the toolchain is what
# check runs against, and a .gitattributes or .gitignore the model wrote would change what git
# records of the run. A basename glob anywhere, a dotted basename anywhere, a prefix, or an exact
# path at the root; the glob is unittest's own discovery pattern, so every file the check collects
# is covered.
PROTECTED = ("test*.py", "tests/", "pyproject.toml", "uv.lock", "check.Dockerfile", "docs/",
             ".gitattributes", ".gitignore")  # fmt: skip
# USD per 1M tokens, peak rates; api-docs.deepseek.com/quick_start/pricing read on 2026-09-15.
# `PRICE` is DeepSeek's published peak rate for `deepseek-flash` and a statement about that one
# model: it stays the source for `MODEL` and is not the fallback for any other name. A role on
# another model is priced by the library when it has a row, and a role whose price nobody knows is
# refused rather than bounded by a number that is not its own.
PRICE = {"cache_hit": 0.006, "cache_miss": 0.3, "output": 1.2}


class UnknownPrice(RuntimeError):
    """The model's price is not known: neither `PRICE` nor the library can price it, so a run on it
    cannot be bounded and must not start. The message names the model."""


def table_price(usage: Any) -> float:
    """The USD those tokens cost at `PRICE`, for anything carrying `input_tokens`,
    `cache_read_tokens` and `output_tokens`: the tokens the cache served at the cache-hit rate, the
    rest of the input at the miss rate and the output at the output rate. This is the one model's
    arithmetic, and `priced` is the one place tokens are priced, so the tools' landing on what a run
    has spent and the record's `cost_usd` cannot drift."""
    miss = usage.input_tokens - usage.cache_read_tokens  # what the cache did not serve
    return (
        usage.cache_read_tokens * PRICE["cache_hit"]
        + miss * PRICE["cache_miss"]
        + usage.output_tokens * PRICE["output"]
    ) / 1e6


def library_price(usage: Any, model: str, provider_api_url: str | None = None) -> float:
    """What the library prices those tokens at for `model`, at `provider_api_url` when the role is
    served at an address: the provider and the model looked up together. A name or an address the
    library has no row for raises `LookupError`, which `priced` turns into `UnknownPrice`."""
    asked = genai_prices.Usage(
        input_tokens=usage.input_tokens,
        cache_read_tokens=usage.cache_read_tokens,
        output_tokens=usage.output_tokens,
    )
    if provider_api_url:
        calc = genai_prices.calc_price(asked, model, provider_api_url=provider_api_url)
    else:
        calc = genai_prices.calc_price(asked, model)
    return float(calc.total_price)


def priced(usage: Any, model: str, base_url: str | None = None) -> tuple[float, str]:
    """The one function that prices tokens: what they cost on `model` reached at `base_url` when the
    role names one, and the source that answered -- `table` for the one model `PRICE` was written
    for, `genai-prices` for a name the library has a row for. The address is asked first when there
    is one, so a name served by more than one vendor is priced at the address the role is reached
    at, and the bare name answers only when there is no address or the library does not know that
    one. A name neither source can price raises `UnknownPrice`, because a bound derived from
    another model's rate is not a bound."""
    if model == MODEL:
        return table_price(usage), "table"
    if base_url:
        try:
            return library_price(usage, model, base_url), "genai-prices"
        except LookupError:
            pass
    try:
        return library_price(usage, model), "genai-prices"
    except LookupError as e:
        raise UnknownPrice(f"no price for model {model}") from e


def price(usage: Any, model: str, base_url: str | None = None) -> float:
    """The USD those tokens cost on `model`, reached at `base_url` when the role names one: the one
    function's number, whose source `priced` also names. `model` has no default: a caller that does
    not name one gets a TypeError."""
    return priced(usage, model, base_url)[0]


def require_price(model: str, base_url: str | None = None) -> None:
    """Raise `UnknownPrice` when the one function that prices tokens has no rate for `model` at
    `base_url`, so a program can refuse a role whose run could not be bounded before it starts.
    `price` is asked for the price of no tokens, so nothing is priced here -- only whether a rate
    exists -- and the answer cannot disagree with the number the run would carry. A price that could
    not be asked at all is no price either: a `TypeError` from the asking is an `UnknownPrice`, not
    a pass, because anything that makes the asking itself fail admits every unpriceable model."""
    try:
        if base_url:
            price(RunUsage(), model, base_url)
        else:
            price(RunUsage(), model)
    except UnknownPrice:
        raise
    except TypeError as e:  # the asking itself failed: no price was learned, so none is admitted
        raise UnknownPrice(f"no price for model {model}") from e

ROLE = """\
You are the builder. You are given a goal and a checkout: a directory with code and tests. You
can explore it with `list`, `read` and `search`, change it with `write` and `edit`, and test it with
`check`. The goal is reached when `check` is green: the tests are the goal's acceptance
criteria and cannot be changed.

Work in this order: read what the goal touches; run `check` once to see what fails; make the
smallest change that can make it pass; run `check`; repeat. Stop when `check` is green, or
when you cannot make it green within the budget, and return the report through the
`final_result` function: changed (the paths you wrote or edited, in order), did (what you
changed and why, one fact per item, each naming a path), check (green or red), failing (test
names if red), unsure (what you could not determine or verify).

Rules: change only what the goal needs; prefer `edit` over `write` for existing files; never
work around a failing test by changing what it asserts; no commentary outside the report.
"""


class BuildReport(BaseModel):
    """The builder's report: what it changed in the checkout, and whether the tests pass."""

    changed: list[str] = Field(description="The paths you wrote or edited, in order.")
    did: list[str] = Field(
        description="What you changed and why, one fact per item, each naming a path."
    )
    check: Literal["green", "red"] = Field(description="Green or red: the state of the last check.")
    failing: list[str] = Field(description="Test names if red.")
    unsure: list[str] = Field(description="What you could not determine or verify.")


SECTIONS = (("Changed", "changed"), ("Did", "did"), ("Check", "check"),
            ("Failing", "failing"), ("Unsure", "unsure"))  # fmt: skip


def render(report: BuildReport) -> str:
    """The report in v0.1's markdown shape: five headings, one bullet per item."""
    out: list[str] = []
    for heading, field in SECTIONS:
        out.append(f"## {heading}")
        items = getattr(report, field)
        if isinstance(items, str):  # check is one value, and renders as one bullet
            items = [items]
        out.extend(f"- {item}" for item in items or ["(none)"])
        out.append("")
    return "\n".join(out)


class Tools:
    """The tools: what the model can do to the checkout, and the record of it."""

    def __init__(self, root: Path, run_dir: Path, hidden: tuple[str, ...] = HIDDEN,
                 protected: tuple[str, ...] = PROTECTED, sandbox: Any = None,
                 spent: Any = None):  # fmt: skip
        self.root = root.resolve()
        self.run_dir = run_dir
        self.hidden = hidden
        self.protected = protected
        self.sandbox = sandbox
        # Something callable with no arguments for what the run has spent so far in USD, or None
        # when the caller has none: a `Tools` built without one refuses nothing on spend.
        self.spent = spent
        # Every call through the six tools, work or refusal alike: once it is past `CALLS_LIMIT`
        # they all answer the cap and stop, so the run lands and can still report.
        self.calls = 0
        self.listed: list[str] = []
        self.read_paths: list[str] = []
        self.searched: list[str] = []
        self.lines_read = 0
        self.bytes_read = 0
        self.written: list[str] = []
        self.edited: list[str] = []
        self.checks: list[dict[str, Any]] = []
        # What the tools know of the tree since the last check: a write or edit that landed, and
        # nothing a wall refused, is a tree the last check did not see. The builder's own final
        # check is what the run ends on, and it is run only when this is so.
        self.changed_since_check = False

    def _resolve(self, path: str) -> tuple[Path, str]:
        p = (self.root / (path or ".")).resolve()
        if p != self.root and self.root not in p.parents:
            raise ValueError(f"outside the checkout: {path}")
        rel = p.relative_to(self.root).as_posix() or "."
        parts = rel.split("/")
        # A .git component at any depth is git's, not the checkout's: a write there could forge a
        # nested repository and hide a subtree from the record. The other hidden names apply only
        # at the root.
        if parts[0] in self.hidden or ".git" in parts or ".git" in path.split("/"):
            raise ValueError(f"not part of the checkout: {path}")
        return p, rel

    def _writable(self, rel: str) -> None:
        """The goal's tests and the toolchain are the human's; the builder may read them only."""
        name = rel.rsplit("/", 1)[-1]
        for pattern in self.protected:
            if pattern.endswith("/"):  # anything under that directory
                hit = rel == pattern[:-1] or rel.startswith(pattern)
            elif "*" in pattern:  # that basename glob, anywhere in the checkout
                hit = fnmatch.fnmatchcase(name, pattern)
            elif pattern.startswith("."):  # that dotted basename, anywhere in the checkout
                hit = name == pattern
            else:  # that exact path at the root, not the basename anywhere
                hit = rel == pattern
            if hit:
                raise ValueError(
                    f"protected: {rel} (not the builder's to change: the tests, the toolchain, "
                    "the vault and git's own files)"
                )

    def _over_limit(self) -> str:
        """The run's own caps: what it has spent, and the fixed backstop on its calls. The spend is
        asked here and never cached, because a run crosses the line in the middle and must land
        there. At `SOFT_SPEND` every tool answers the cap and refuses; at `HARD_SPEND`, above it,
        the run itself ends, the way the library's limits end a runaway. A refusal is the write
        cap's shape with this cap's number and moves no counter but `calls`; `CALLS_LIMIT` is read
        here rather than cached, so it is the constant the caller sees at the moment of the call."""
        if self.spent is not None:
            spent = self.spent()
            if spent >= HARD_SPEND:
                raise UsageLimitExceeded(
                    f"exceed the hard spend ceiling of {HARD_SPEND} USD, spent {spent:.6f}"
                )
            if spent >= SOFT_SPEND:
                return f"error: cap reached ({SOFT_SPEND} USD spent); report now"
        if self.calls > CALLS_LIMIT:
            return f"error: cap reached ({CALLS_LIMIT} tool calls); report now"
        return ""

    def _capped(self) -> str:
        over = self._over_limit()
        if over:
            return over
        if len(self.written) + len(self.edited) >= WRITE_CAP:
            return f"error: cap reached ({WRITE_CAP} writes and edits); report now"
        return ""

    def list(self, path: str = ".") -> str:
        """List one directory of the checkout: one entry per line as kind, size, name. Path is the
        directory to list, relative to the checkout root; '.' is the root.

        Args:
            path: The directory to list, relative to the checkout root.
        """
        self.calls += 1
        if capped := self._over_limit():
            return capped
        try:
            p, rel = self._resolve(path)
            if not p.is_dir():
                raise ValueError(f"not a directory: {path}")
            entries = sorted(p.iterdir(), key=lambda e: (not e.is_dir(), e.name))
            skip = self.hidden if rel == "." else (".git",)  # git's own files are never listed
            entries = [e for e in entries if e.name not in skip]
            lines = []
            for e in entries[:LIST_CAP]:
                kind = "link" if e.is_symlink() else "dir" if e.is_dir() else "file"
                size = e.lstat().st_size if kind == "file" else 0
                name = e.name if rel == "." else f"{rel}/{e.name}"  # paths from the checkout root
                lines.append(f"{kind}\t{size}\t{name}")
            if len(entries) > LIST_CAP:
                lines.append(f"...\t{len(entries) - LIST_CAP} more entries not shown")
        except (ValueError, OSError, RuntimeError) as e:  # RuntimeError: a symlink loop
            return f"error: {e}"
        self.listed.append(rel)
        return "\n".join(lines) or "(empty)"

    def read(self, path: str, start: int = 1, limit: int | None = None) -> str:
        """Read a file of the checkout as numbered lines, from line `start` (1-based): at most
        `limit` lines, at most 1000 lines and at most 64000 bytes per call, whichever is met first,
        and a read cut short by any of the three says where to continue. `limit` omitted, zero or
        above the line cap is the line cap; a negative `limit` is one.

        Args:
            path: The file to read, relative to the checkout root.
            start: The first line to read, 1-based.
            limit: The most lines to return; omitted, zero or above the line cap is the line cap,
                a negative limit is one.
        """
        self.calls += 1
        if capped := self._over_limit():
            return capped
        try:
            p, rel = self._resolve(path)
            if not p.is_file():
                raise ValueError(f"not a file: {path}")
            start = max(1, int(start))
            # Omitted or zero is the line cap, above it is the cap, below one is one.
            limit = int(limit) if limit else READ_LINES_CAP
            limit = max(1, min(limit, READ_LINES_CAP))
            out: list[str] = []
            n = nbytes = 0
            with p.open("r", encoding="utf-8", errors="replace") as f:
                for i, line in enumerate(f, 1):
                    if i < start:
                        continue
                    size = len(line.encode())
                    if n >= limit or nbytes + size > READ_BYTES_CAP:
                        if n:  # one line per call at least, or a long line dead-ends the read
                            out.append(f"...\ttruncated; continue with start={i}")
                            break
                        cut = line.encode()[:READ_BYTES_CAP].decode("utf-8", "ignore")
                        out.append(f"{i}\t{cut} …(line cut at {READ_BYTES_CAP} bytes)")
                        size = len(cut.encode())  # the bytes returned, not the whole line's
                    else:
                        out.append(f"{i}\t{line.rstrip(chr(10))}")
                    n += 1
                    nbytes += size
        except (ValueError, OSError, RuntimeError) as e:  # RuntimeError: a symlink loop
            return f"error: {e}"
        self.read_paths.append(rel)
        self.lines_read += n
        self.bytes_read += nbytes
        return "\n".join(out) or "(empty)"

    def _files(self, directory: Path, rel: str, unlistable: list[int]):
        """Every file under `directory`, in the order `list` gives: directories first, then files,
        each by name, hidden names at the root and any .git component skipped, symlinks not
        followed. Yields the file and its path from the checkout root. A directory that cannot be
        listed appends 1 to `unlistable`: what is under it was not searched."""
        try:
            entries = sorted(directory.iterdir(), key=lambda e: (not e.is_dir(), e.name))
        except (OSError, RuntimeError):  # a directory that cannot be listed: nothing under it
            unlistable.append(1)
            return
        for e in entries:
            if e.is_symlink():  # a link is not a file of the checkout, whatever it points at
                continue
            if e.name == ".git" or (rel == "." and e.name in self.hidden):
                continue
            child = e.name if rel == "." else f"{rel}/{e.name}"
            if e.is_dir():
                yield from self._files(e, child, unlistable)
            elif e.is_file():
                yield e, child

    def search(self, pattern: str, path: str = ".") -> str:
        """Search the checkout for a pattern: every line of every file under `path` that contains
        `pattern` as plain text, case-sensitive, one match per line as `<path>:<line number>:<text>`.
        Files come in the order `list` gives and lines in order, numbered as `read` numbers them; at
        most 100 lines or 32000 bytes per search, then how many more matches were not shown. A file
        whose bytes are not UTF-8, one larger than 1000000 bytes, or one that cannot be read is
        skipped, and the result ends with how many files that was. A lone match longer than the cap
        is cut to fit and marked, as `read` cuts a long line.

        Args:
            pattern: The plain text to find; case-sensitive, and must not be empty or have a newline
                in it.
            path: The directory to search, relative to the checkout root; '.' is the root.
        """
        self.calls += 1
        if capped := self._over_limit():
            return capped
        if not pattern:
            return "error: the pattern is empty"
        if "\n" in pattern or "\r" in pattern:
            return "error: the pattern has a newline; search matches one line at a time"
        try:
            p, rel = self._resolve(path)
            if not p.is_dir():
                raise ValueError(f"not a directory: {path}")
            out: list[str] = []
            shown = nbytes = total = skipped = 0
            unlistable: list[int] = []
            full = False  # the first match that does not fit ends the shown part
            for f, frel in self._files(p, rel, unlistable):
                try:
                    if f.stat().st_size > SEARCH_FILE_CAP:  # too large: never opened
                        skipped += 1
                        continue
                    with f.open("r", encoding="utf-8") as fh:  # line by line, universal newlines
                        hits = [(i, line.rstrip("\n")) for i, line in enumerate(fh, 1) if pattern in line]
                except (OSError, UnicodeDecodeError):  # not UTF-8, or unreadable: the file is skipped
                    skipped += 1
                    continue
                for i, line in hits:
                    total += 1
                    if full or shown >= SEARCH_LINES_CAP:
                        continue
                    entry = f"{frel}:{i}:{line}"
                    size = len(entry.encode()) + 1
                    if nbytes + size > SEARCH_BYTES_CAP:
                        full = True
                        if not shown:  # one match longer than the cap: cut it and mark it, as read does
                            head = f"{frel}:{i}:"
                            marker = f" …(match cut at {SEARCH_BYTES_CAP} bytes)"
                            room = SEARCH_BYTES_CAP - len((head + marker).encode())
                            cut = line.encode()[: max(0, room)].decode("utf-8", "ignore")
                            out.append(head + cut + marker)
                            shown += 1
                        continue
                    out.append(entry)
                    nbytes += size
                    shown += 1
            skipped += len(unlistable)  # a directory that could not be listed counts once
            if not total:
                found = "no matches"
            else:
                found = "\n".join(out)
                if total > shown:
                    found += f"\n...\t{total - shown} more matches not shown"
            if skipped:
                found += f"\n...\t{skipped} files not searched"
        except (ValueError, OSError, RuntimeError) as e:  # RuntimeError: a symlink loop
            return f"error: {e}"
        self.searched.append(rel)
        return found

    def write(self, path: str, content: str) -> str:
        """Write a file of the checkout: create it, or replace what is there with `content`.
        Directories on the way are created. The tests and the toolchain cannot be written.

        Args:
            path: The file to write, relative to the checkout root.
            content: The whole text of the file, as it should be afterwards.
        """
        self.calls += 1
        capped = self._capped()
        if capped:
            return capped
        try:
            p, rel = self._resolve(path)
            self._writable(rel)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        except (ValueError, OSError, RuntimeError) as e:  # RuntimeError: a symlink loop
            return f"error: {e}"
        self.written.append(rel)
        self.changed_since_check = True
        return f"wrote {rel} ({len(content.splitlines())} lines)"

    def edit(self, path: str, old: str, new: str) -> str:
        """Edit a file of the checkout: replace `old` with `new`, once. `old` must appear in the
        file exactly once; if it does not, nothing is changed and the count is reported. The
        tests and the toolchain cannot be edited.

        Args:
            path: The file to edit, relative to the checkout root.
            old: The exact text to replace; include lines around it to make it unique.
            new: The text to put in its place.
        """
        self.calls += 1
        capped = self._capped()
        if capped:
            return capped
        if not old:  # every file contains the empty string, everywhere
            return "error: old text is empty"
        try:
            p, rel = self._resolve(path)
            self._writable(rel)
            if not p.is_file():
                raise ValueError(f"not a file: {path}")
            text = p.read_text(encoding="utf-8")
            found = text.count(old)
            if found != 1:
                if found == 0:
                    return f"error: old text not found in {rel}"
                return f"error: old text found {found} times in {rel}; include more context"
            before = len(text.splitlines())
            text = text.replace(old, new, 1)
            p.write_text(text, encoding="utf-8")
        except (ValueError, OSError, RuntimeError) as e:  # UnicodeDecodeError is a ValueError
            return f"error: {e}"
        self.edited.append(rel)
        self.changed_since_check = True
        return f"edited {rel} ({before} -> {len(text.splitlines())} lines)"

    def _check_once(self) -> str:
        """One check on the tree as it is: the same sandbox, numbered after the checks so far, its
        log `check-<n>.log` beside theirs and its seconds added to theirs. Raises whatever running
        the sandbox raises, so each caller decides how to answer."""
        n = len(self.checks) + 1
        t0 = time.time()
        code, output = self.sandbox.run(self.root, self.run_dir, n)
        seconds = round(time.time() - t0, 1)
        log = self.run_dir / f"check-{n}.log"
        log.write_text(output, encoding="utf-8", errors="replace")
        self.checks.append({"exit": code, "seconds": seconds})
        self.changed_since_check = False
        tail = "\n".join(output.splitlines()[-CHECK_TAIL_LINES:])
        if len(tail.encode()) > CHECK_TAIL_BYTES:  # the end of the output is the part that says why
            tail = tail.encode()[-CHECK_TAIL_BYTES:].decode("utf-8", "ignore")
        return f"exit {code}\n{tail}"

    def check(self) -> str:
        """Run the checkout's tests and return the exit code and the tail of the output: exit 0 is
        green, anything else is red. The tests run in a container, with the checkout read-only and
        no network, so this reports on the checkout as it is on disk. At most 8 checks per run; the
        builder's own check of the tree the model leaves is not one of the 8.
        """
        self.calls += 1
        if capped := self._over_limit():
            return capped
        if len(self.checks) >= CHECK_CAP:
            return f"error: cap reached ({CHECK_CAP} checks); report now"
        if self.sandbox is None:
            return "error: no sandbox; check is not available in this run"
        try:
            return self._check_once()
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as e:
            return f"error: {e}"

    def check_final(self) -> None:
        """The builder's check of the tree the model left, run once when the run ends: the model's
        own kind of check, and only when it wrote or edited since its last check, a refused write
        being nothing written. The cap of 8 binds the model's checks, not this one, and a sandbox
        that cannot run leaves the record as it is rather than losing it.

        A check that could not run leaves `changed_since_check` standing, which is what the record
        reads: the last verdict is kept only when it saw the tree the record is for, so the stale
        green of an earlier tree is written as `none` instead of standing as permission to push.
        """
        if self.sandbox is None or not self.changed_since_check:
            return
        try:
            self._check_once()
        except Exception:  # a sandbox that cannot run must not lose the record
            pass


class Sandbox:
    """Where the checkout's tests run: a container, no network, the checkout mounted read-only.

    The only place that knows about Docker. The image is the checkout's own locked dependencies,
    built once per (uv.lock, check.Dockerfile) pair and reused by every run afterwards.
    """

    @staticmethod
    def image(checkout: Path) -> str:
        """The image name for this checkout: what it locks and how it is built, hashed."""
        h = hashlib.sha256((checkout / "uv.lock").read_bytes() + (checkout / "check.Dockerfile").read_bytes())
        return f"factory-check:{h.hexdigest()[:12]}"

    @staticmethod
    def ensure_image(checkout: Path, run_dir: Path) -> str:
        """Build the image if it is not there yet; the build is the one step with network."""
        name = Sandbox.image(checkout)
        seen = subprocess.run(["docker", "image", "inspect", name], capture_output=True)
        if seen.returncode == 0:
            return name
        built = subprocess.run(
            # -f absolute: docker resolves a relative -f against the caller's directory, and the
            # factory never runs from inside the checkout.
            ["docker", "build", "-f", str(checkout / "check.Dockerfile"), "-t", name, str(checkout)],
            capture_output=True,
            timeout=IMAGE_TIMEOUT,
        )
        (run_dir / "image-build.log").write_bytes(built.stdout + built.stderr)
        if built.returncode != 0:
            raise RuntimeError(f"docker build failed (exit {built.returncode}); see image-build.log")
        return name

    @staticmethod
    def run(checkout: Path, run_dir: Path, n: int) -> tuple[int, str]:
        """The checkout's tests, once: the exit code and everything the run printed."""
        name = Sandbox.ensure_image(checkout, run_dir)
        container = f"factory-check-{run_dir.name}-{n}"
        argv = [
            "docker", "run", "--rm", "--name", container,
            "--network", "none",  # the check cannot reach the key, the provider or the internet
            "--user", f"{os.getuid()}:{os.getgid()}",
            "-e", "HOME=/tmp",
            "-e", "PYTHONDONTWRITEBYTECODE=1",  # the checkout is read-only; do not try to cache
            "-v", f"{checkout}:/w:ro", "-w", "/w",
            "--memory", "1g", "--cpus", "2", "--pids-limit", str(PIDS_LIMIT),
            name, *CHECK_CMD,
        ]  # fmt: skip
        try:
            done = subprocess.run(argv, capture_output=True, timeout=CHECK_TIMEOUT)
        except subprocess.TimeoutExpired:
            try:  # the check is over either way; a wedged daemon must not hang the run too
                subprocess.run(["docker", "kill", container], capture_output=True, timeout=30)
            except (OSError, subprocess.SubprocessError):
                pass
            return 124, f"timeout after {CHECK_TIMEOUT} s"
        # unittest writes to stderr; the checkout's own code may write to either.
        return done.returncode, (done.stdout + done.stderr).decode("utf-8", "replace")


SECRET_HEADERS = ("authorization", "x-api-key", "cookie", "set-cookie", "proxy-authorization")


class Wire:
    """The raw HTTP record: one line per attempt, request and response, with no secret in it."""

    def __init__(self, path: Path, transport: Any = None):
        self.path = path
        self.attempts = 0
        path.touch()
        self.client = httpx2.AsyncClient(
            transport=transport,
            event_hooks={"request": [self.on_request], "response": [self.on_response]},
        )

    def _write(self, **entry: Any) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"t": round(time.time(), 3), **entry}, ensure_ascii=False) + "\n")

    @staticmethod
    def _body(text: str) -> Any:
        """A body that parses as JSON is recorded as the parsed value, so reading the record needs
        no second json.loads; a body that does not parse as JSON stays the text it was."""
        try:
            return json.loads(text)
        except ValueError:  # not JSON: keep the text, as the only thing it can be read as
            return text

    def _headers(self, headers: Any) -> dict[str, str]:
        """Which headers were sent, never what the secret ones said."""
        out = {}
        for name, value in headers.items():
            name = name.lower()
            out[name] = "<redacted>" if name in SECRET_HEADERS else value
        return out

    async def on_request(self, request: Any) -> None:
        """Every attempt the SDK makes, headers and body included; the key is never written."""
        self.attempts += 1
        try:
            body = request.content.decode("utf-8", "replace")
        except Exception:  # a streamed body has nothing to record
            body = ""
        self._write(
            dir="request",
            method=request.method,
            url=str(request.url),
            status=None,
            headers=self._headers(request.headers),
            body=self._body(body),
        )

    async def on_response(self, response: Any) -> None:
        """The answer to it, read in full so the body is there even when the SDK streams."""
        await response.aread()
        req = response.request
        self._write(
            dir="response",
            method=req.method,
            url=str(req.url),
            status=response.status_code,
            headers=self._headers(response.headers),
            body=self._body(response.text),
        )


# The stock DeepSeek profile keys on the name: only `deepseek-v4-*` is treated as thinking-capable,
# so for `deepseek-flash` the library believes thinking is off and forces a tool choice, which the
# API rejects with 400 "Thinking mode does not support this tool_choice". Saying what the model is
# — thinking-capable, thinking on by default, no forced tool choice while it thinks — makes the
# library send `tool_choice: auto` and leaves thinking at the API default, as in v0.1.
PROFILE = OpenAIModelProfile(
    supports_thinking=True,
    openai_reasoning_enabled_by_default=True,
    openai_supports_forced_tool_choice_with_thinking=False,
)


class SpendModel(WrapperModel):
    """A model that asks what the run has spent at every request after the first: a call of the
    wrong shape never reaches a tool, so a run whose every call is malformed would otherwise be
    bounded by `REQUEST_LIMIT` alone and run past `HARD_SPEND`. The first request is answered --
    nothing has been spent before it -- and a call that does reach a tool is still ended by the
    tool's own check, so the two do not disagree about where the line is."""

    def __init__(self, wrapped: Any, spent: Any):
        super().__init__(wrapped)
        self._spent = spent
        self._answered = False

    async def request(self, messages: Any, model_settings: Any, model_request_parameters: Any) -> Any:
        if self._answered and self._spent is not None:
            spent = self._spent()
            if spent >= HARD_SPEND:
                raise UsageLimitExceeded(
                    f"exceed the hard spend ceiling of {HARD_SPEND} USD, spent {spent:.6f}"
                )
        self._answered = True
        return await super().request(messages, model_settings, model_request_parameters)


def build_agent(
    tools: Tools, key: str = "", http_client: Any = None, model: Any = None,
    model_name: str = MODEL, base_url: str | None = None,
) -> Agent[None, BuildReport]:  # fmt: skip
    """The agent: the role, the six tools, a typed report, our caps. The model is the caller's, or
    the one `model_name` names -- the instance's `builder` role when it holds one, the program's
    constant otherwise -- reached at `base_url` when the role names one. `PROFILE` says what
    DeepSeek's thinking models are, so it is passed only for the model it was written for; a model
    served at another address is not one and is given the stock profile."""
    if model is None:
        # The role's address, when it names one, is the client the provider reaches: the stock
        # DeepSeekProvider has no `base_url` of its own, so an OpenAI client built at it is what
        # the provider is handed. `PROFILE` is DeepSeek's, so it is passed only for the model it
        # was written for; a model served elsewhere gets the library's own profile.
        provider = (
            DeepSeekProvider(
                openai_client=AsyncOpenAI(base_url=base_url, api_key=key, http_client=http_client)
            )
            if base_url
            else DeepSeekProvider(api_key=key, http_client=http_client)
        )
        model = OpenAIChatModel(model_name, provider=provider, profile=None if base_url else PROFILE)
    if tools.spent is not None:  # a tool-less caller that bounds nothing is not wrapped
        model = SpendModel(model, tools.spent)
    agent = Agent(
        model,
        instructions=ROLE,
        output_type=BuildReport,
        tools=[
            # sequential: the calls of one response run one at a time in the order the model gave
            # them, a barrier between them, so a later call sees what the earlier ones wrote.
            Tool(tools.list, takes_ctx=False, sequential=True),
            Tool(tools.read, takes_ctx=False, sequential=True),
            Tool(tools.search, takes_ctx=False, sequential=True),
            Tool(tools.write, takes_ctx=False, sequential=True),
            Tool(tools.edit, takes_ctx=False, sequential=True),
            Tool(tools.check, takes_ctx=False, sequential=True),
        ],
        # No temperature: DeepSeek ignores it in thinking mode, and the settings should say what
        # the request actually is. Thinking stays at the API default.
        model_settings=OpenAIChatModelSettings(timeout=180),
        # A call of the wrong shape is the library's to answer, with a retry prompt the model reads
        # and moves on from, so the tool retries sit above what a run can afford -- one request each,
        # and no more requests than REQUEST_LIMIT -- and never end a run; the output retries stay.
        retries={"tools": REQUEST_LIMIT, "output": 2},
    )
    return agent


def run(agent: Agent[None, BuildReport], goal: str,
        usage: RunUsage | None = None) -> tuple[BuildReport | None, list, RunUsage, str, str]:  # fmt: skip
    """One run under the caps: the report if there is one, the messages either way. The tools are
    what land a run, on what it has spent; `limits` gives the library the two fixed backstops, so a
    runaway that spends nothing is still caught and the requests outlast the calls. `usage` is the
    object the run counts into and the caller may hold it already, so a spend the tools ask for is
    the same one the record writes; a caller that names none gets a fresh one."""
    usage = RunUsage() if usage is None else usage
    report, stopped, detail = None, "answer", ""
    with capture_run_messages() as messages:
        try:
            result = agent.run_sync(
                goal,
                usage=usage,
                usage_limits=limits(),
            )
            report = result.output
        except UsageLimitExceeded as e:
            stopped, detail = "cap", str(e)
        except (UnexpectedModelBehavior, ModelAPIError) as e:  # ModelHTTPError is one of these
            stopped, detail = "error", str(e)
    return report, list(messages), usage, stopped, detail


def shape_retries(messages: list) -> dict[str, int]:
    """How many times the library answered a call of each tool for its shape, counted from a run's
    messages: every retry prompt part a tool names, by that name, and nothing for one that names no
    tool -- a plain-text answer retried for the output is no tool's shape. `{}` when none did."""
    retries: dict[str, int] = {}
    for message in messages:
        for part in getattr(message, "parts", []):
            name = getattr(part, "tool_name", None)
            if isinstance(part, RetryPromptPart) and name:
                retries[name] = retries.get(name, 0) + 1
    return retries


# The environment's own GIT_* pointers are not the checkout's: git runs without them, so it
# discovers the repository from the directory it is given and not from where the caller points.
GIT_ENV_UNSET = (
    "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
)  # fmt: skip


def git_env() -> dict[str, str]:
    """The environment git runs in: the caller's, without its own GIT_* pointers, with the host's
    system and global configuration files left unread -- a GIT_CONFIG_GLOBAL the caller names
    explicitly is honored -- and in English, so git's refusals are the ones the code reads
    whatever the host's locale says."""
    env = dict(os.environ)
    for name in GIT_ENV_UNSET:
        env.pop(name, None)
    env.setdefault("GIT_CONFIG_NOSYSTEM", "1")  # the system file is not read
    env.setdefault("GIT_CONFIG_GLOBAL", os.devnull)  # nor the global one, unless the caller names one
    env["LC_ALL"] = "C"
    return env


class GitError(RuntimeError):
    """git ran and exited nonzero: the message carries git's own words."""


class LeakedKey(RuntimeError):
    """A record holds the key's value, in the file this exception carries; never the value."""


def git(checkout: Path, *args: str, ok: tuple[int, ...] = (0,)) -> str:
    """Read-only git in the checkout, not one of the tools: the model never sees this. A git that
    exits outside `ok` is an error carrying git's own words; --no-index exits 1 when the files
    differ, which is the normal case here, and a checkout with no commit answers HEAD with 1."""
    done = subprocess.run(
        ["git", "-C", str(checkout), *args],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        env=git_env(),
    )
    if done.returncode not in ok:
        raise GitError(done.stderr.strip() or f"git exited {done.returncode}")
    return done.stdout


def git_refusal(stderr: str) -> str:
    """What git said, from the first line of its stderr after `fatal: ` and nothing else: a path
    that merely contains the phrase cannot decide it, and LC_ALL keeps the phrase English."""
    for line in stderr.splitlines():
        line = line.strip()
        if line.startswith("fatal:"):
            return line[len("fatal:"):].strip()
    lines = stderr.splitlines()
    return lines[0].strip() if lines else ""


def head(checkout: Path) -> str:
    """The checkout's HEAD commit; empty only when the checkout has no commit yet."""
    return git(checkout, "rev-parse", "--verify", "-q", "HEAD", ok=(0, 1)).strip()


def dirty_paths(checkout: Path) -> list[str]:
    """The paths a git checkout has changed, staged or not, as git status names them. Read-only."""
    status = git(checkout, "status", "--porcelain", "-z", "--untracked-files=all")
    # Each entry is two status characters, a space, then the path; a rename adds the old path as
    # a second NUL-separated field, which does not have that shape and is skipped.
    return [entry[3:] for entry in status.split("\0") if len(entry) > 3 and entry[2] == " "]


def record_diff(checkout: Path, run_dir: Path) -> dict[str, Any]:
    """What the run left in the checkout: diff.patch (absent when the run left nothing), and the
    three numbers about it."""
    # -z so a path with a space or a quote survives; -uall so a new directory is listed as files.
    status = git(checkout, "status", "--porcelain", "-z", "--untracked-files=all")
    untracked = [entry[3:] for entry in status.split("\0") if entry.startswith("?? ")]
    # Against HEAD, so a change the run staged is in the patch too; the checkout is always a git
    # checkout with a commit, so there is always a HEAD. A run that left nothing leaves no patch.
    # --no-ext-diff and --no-textconv keep the patch git's own: neither the environment, nor the
    # configuration, nor a .gitattributes in the checkout can replace it with a program's output.
    # Every diff ends its options with --, so a file the run names -x.txt or HEAD is a path to git
    # and not an option or a revision.
    flags = ("--no-ext-diff", "--no-textconv", "--text")
    parts = [git(checkout, "diff", *flags, "HEAD", "--")]
    for rel in untracked:
        parts.append(git(checkout, "diff", *flags, "--no-index", "--", "/dev/null", rel, ok=(0, 1)))
    patch = "".join(parts)
    if patch:
        (run_dir / "diff.patch").write_text(patch)  # the patch first: counting can fail
    files = insertions = deletions = 0
    for line in git(checkout, "diff", "HEAD", "--numstat", "--").splitlines():
        added, removed, _path = line.split("\t", 2)
        files += 1
        insertions += int(added) if added.isdigit() else 0  # "-" for a binary file
        deletions += int(removed) if removed.isdigit() else 0
    for rel in untracked:
        files += 1
        p = checkout / rel  # a broken symlink or a nested checkout has no lines to count
        insertions += len(p.read_bytes().splitlines()) if p.is_file() and not p.is_symlink() else 0
    return {"files_changed": files, "insertions": insertions, "deletions": deletions}


def sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def usage_error(reason: str = "") -> int:
    print('usage: builder.py <checkout> "<goal>"', file=sys.stderr)
    if reason:
        print(reason, file=sys.stderr)
    return 2


FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
FENCE_CLOSE = re.compile(r"^ {0,3}(`{3,}|~{3,})[ \t]*$")
HEADING = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*$")


def opening_fence(line: str) -> tuple[str, int] | None:
    """The fence a line opens, as its character and how many marks, or None. A fence is three or
    more backticks or tildes, indented at most three spaces, with any info string; a backtick
    fence's info string holds no backtick, so a line whose rest has one is no fence."""
    m = FENCE_OPEN.match(line)
    if not m:
        return None
    run = m.group(1)
    if run[0] == "`" and "`" in m.group(2):
        return None
    return run[0], len(run)


def closing_fence(line: str, fence: tuple[str, int]) -> bool:
    """Whether a line closes `fence`: the same character and at least as many marks, alone on the
    line, so a block of four backticks holds a block of three whole and a backtick block tildes."""
    m = FENCE_CLOSE.match(line)
    return bool(m) and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1]


def heading(line: str) -> tuple[int, str]:
    """A markdown ATX heading: its level, 0 when the line is not one, and its text. The heading is
    indented at most three spaces; a line indented four is no heading, whatever it starts with."""
    m = HEADING.match(line)
    if not m:
        return 0, ""
    return len(m.group(1)), (m.group(2) or "").strip()


def _code_span_close(line: str, start: int, run: int) -> int | None:
    """The index of the next run of exactly `run` backticks at or after `start`, or None: only a
    run of the same length closes a code span, so the marks inside one are the note's text."""
    i, n = start, len(line)
    while i < n:
        if line[i] == "`":
            j = i
            while j < n and line[j] == "`":
                j += 1
            if j - i == run:
                return i
            i = j
        else:
            i += 1
    return None


def _scan_line(line: str, in_comment: bool) -> tuple[str, bool]:
    """One line's text with its `%%` comments removed and its code spans kept whole, starting in
    the comment state `in_comment`; the returned bool says whether a comment is still open. A mark
    inside a code span, between backticks on the line, is the note's text, not a mark."""
    out: list[str] = []
    i, n = 0, len(line)
    while i < n:
        if in_comment:
            j = line.find("%%", i)
            if j < 0:
                return "".join(out), True
            in_comment = False
            i = j + 2
            continue
        if line[i] == "`":
            j = i
            while j < n and line[j] == "`":
                j += 1
            close = _code_span_close(line, j, j - i)
            if close is None:
                out.append(line[i:j])
                i = j
                continue
            end = close + (j - i)
            out.append(line[i:end])
            i = end
            continue
        if line.startswith("%%", i):
            in_comment = True
            i += 2
            continue
        out.append(line[i])
        i += 1
    return "".join(out), in_comment


def note_text(text: str) -> str:
    """The note's text with its `%%` comments removed. A mark inside a code span, a fenced code
    block or an indented code block (four spaces or more) is the note's text, not a mark, and a
    comment left open to the end is a usage error."""
    out: list[str] = []
    in_comment = False
    fence: tuple[str, int] | None = None
    for line in text.split("\n"):
        if fence is not None:
            out.append(line)
            if closing_fence(line, fence):
                fence = None
            continue
        if not in_comment:
            opened = opening_fence(line)
            if opened is not None:
                out.append(line)
                fence = opened
                continue
            if line.startswith(("    ", "\t")):  # an indented code block: %% here is text
                out.append(line)
                continue
        scanned, in_comment = _scan_line(line, in_comment)
        out.append(scanned)
    if in_comment:
        raise ValueError("a %% comment is not closed")
    return "\n".join(out)


def goal_section(text: str) -> str | None:
    """The text under the note's `## Goal`, from its heading to the next heading of level one or
    two, or None when the note has no such heading. A fenced code block belongs whole: a heading
    inside one neither starts the section nor ends it, whatever its lines start with."""
    lines = text.split("\n")
    start = None
    fence: tuple[str, int] | None = None
    for i, line in enumerate(lines):
        if fence is not None:
            if closing_fence(line, fence):
                fence = None
            continue
        opened = opening_fence(line)
        if opened is not None:
            fence = opened
            continue
        level, title = heading(line)
        if level == 2 and title == "Goal":
            start = i
            break
    if start is None:
        return None
    section: list[str] = []
    fence = None
    for line in lines[start + 1:]:
        if fence is not None:
            section.append(line)
            if closing_fence(line, fence):
                fence = None
            continue
        opened = opening_fence(line)
        if opened is not None:
            section.append(line)
            fence = opened
            continue
        if heading(line)[0] in (1, 2):  # the next section ends the text
            break
        section.append(line)
    while section and not section[0].strip():  # only blank lines: the first line keeps its indent
        section.pop(0)
    while section and not section[-1].strip():
        section.pop()
    return "\n".join(section)


def committed_file(checkout: Path, arg: str) -> bool:
    """Whether the commit's entry at `arg` is a regular file: `git ls-tree` gives the mode, so a
    directory, a symbolic link and a submodule are no seed, whatever their bytes say."""
    entry = git(checkout, "ls-tree", "HEAD", "--", arg).strip()
    mode = entry.split(" ", 1)[0] if entry else ""
    return mode.startswith("100")


def read_seed(checkout: Path, arg: str) -> tuple[str, str | None]:
    """The goal argument as the model gets it. One word ending in `.md`, with no whitespace in it,
    names a seed note of the checkout: its text is the commit's, `git show HEAD:<path>`, not the
    working tree's, and the goal is `seed: <name without .md>` then the text of the note's `## Goal`
    section; the name is the seed. Any other argument is text, the goal as it is and no seed.

    Every refusal is a ValueError, which main turns into a usage error: a `.md` path that leaves
    the checkout, `..` and absolute paths among them; one whose commit entry is no file, a symbolic
    link or a directory among them; a note the commit does not hold; a note with no `## Goal`
    section, or none with text under it; and a `%%` comment left open to the end of the note. A git
    failure reading the seed is such a refusal too -- a checkout without a commit, or a path git
    reads as pathspec magic -- never a traceback."""
    if not arg.endswith(".md") or any(c.isspace() for c in arg):
        return arg, None
    rel = Path(arg)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"not a seed of the checkout: {arg}")
    try:
        if not committed_file(checkout, arg):  # no entry, or a tree, a link or a submodule
            raise ValueError(f"no such seed in the commit: {arg}")
        committed = git(checkout, "show", f"HEAD:{arg}")
    except GitError as e:
        raise ValueError(f"no such seed in the commit: {arg}: {e}") from e
    text = goal_section(note_text(committed))
    if text is None:
        raise ValueError(f"the seed has no ## Goal section: {arg}")
    if not text:
        raise ValueError(f"the seed has no text under ## Goal: {arg}")
    name = rel.name.removesuffix(".md")
    return f"seed: {name}\n{text}", name


def store_env() -> dict[str, str]:
    """The environment the store's git runs in: `git_env`'s, with the factory's own author and
    committer identity, so committing a record needs nothing of the host's, and with the host's
    system and global configuration left unread and no hook of the store's run, so the store's
    git is the factory's alone."""
    env = git_env()
    env["GIT_CONFIG_NOSYSTEM"] = "1"  # the system file is not read
    env["GIT_CONFIG_GLOBAL"] = os.devnull  # nor the global one
    env["GIT_CONFIG_COUNT"] = "1"  # nor the store's own hooks: none runs
    env["GIT_CONFIG_KEY_0"] = "core.hooksPath"
    env["GIT_CONFIG_VALUE_0"] = os.devnull
    env["GIT_AUTHOR_NAME"] = env["GIT_COMMITTER_NAME"] = "factory"
    env["GIT_AUTHOR_EMAIL"] = env["GIT_COMMITTER_EMAIL"] = "factory@localhost"
    return env


def _store_git(store: Path, *args: str) -> str:
    """git in the factory's store: the environment `git_env` cleans and the factory's identity, and
    git's own words when it fails. Read or write; never one of the model's tools."""
    done = subprocess.run(
        ["git", "-C", str(store), *args],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        env=store_env(),
    )
    if done.returncode != 0:
        raise GitError(done.stderr.strip() or f"git exited {done.returncode}")
    return done.stdout


def _unstage(store: Path, name: str) -> None:
    """Take the record's paths out of the store's index again, so a commit the store refused
    leaves nothing of the record staged and the store as the run found it. Best effort: the
    refusal is the error the caller reports, and an index git will not touch is left alone."""
    try:
        _store_git(store, "rm", "-r", "--cached", "-q", "--", name)
    except (GitError, OSError, subprocess.SubprocessError):
        pass


def compress_wire(run_dir: Path) -> None:
    """The record's `wire.jsonl` compressed to `wire.jsonl.gz`, the plain file gone."""
    wire = run_dir / "wire.jsonl"
    if not wire.is_file():
        return
    (run_dir / "wire.jsonl.gz").write_bytes(gzip.compress(wire.read_bytes()))
    wire.unlink()


def read_key(path: Path | None = None) -> str:
    """The key from its file: the bare key, or one `name=value` line as in an env file. The file is
    `path` -- the instance's `builder` role names it when it holds one, the program's constant
    otherwise, read at the call so a patch of `KEY_FILE` still answers. A key file that cannot be
    read, or one that holds no key -- empty, or a name with nothing after the `=` -- is a ValueError
    naming the file: an empty key is a key no record can be searched for, and that search is the
    wall that keeps the key out of the store."""
    if path is None:
        path = KEY_FILE
    try:
        text = path.read_text()
    except OSError:
        raise ValueError(f"{path}: the key file cannot be read")
    key = text.strip().rsplit("=", 1)[-1].strip().strip("'\"")
    if not key:
        raise ValueError(f"{path}: the key file holds no key")
    return key


def _record_files(run_dir: Path) -> list[Path]:
    """Every file of the record, in name order, the directories walked first. A `.gz` file is one
    of them whatever the case of its name. A link, or a directory the walk cannot list, is not a
    file the search can leave unread: it refuses as a file holding the key does, naming the path
    and the reason."""
    files: list[Path] = []

    def walk(directory: Path) -> None:
        try:
            entries = sorted(directory.iterdir())
        except OSError as e:
            raise LeakedKey(f"{directory}: the record cannot be searched: {e}")
        for entry in entries:
            if entry.is_symlink():
                raise LeakedKey(f"{entry}: the record cannot be searched: a link")
            if entry.is_dir():
                walk(entry)
            elif entry.is_file():
                files.append(entry)

    walk(run_dir)
    return files


def _read_through(path: Path) -> bytes:
    """The bytes of one record file: a `.gz`, whatever the case of its name, is read through its
    compression; one that is not gzip at all -- its magic is not gzip's -- is read as the bytes it
    is. A gzip stream that ends before it should, or a file that cannot be read, is an OSError."""
    if path.name.lower().endswith(".gz"):
        try:
            return gzip.open(path, "rb").read()
        except gzip.BadGzipFile:  # not what its name says: the bytes it is
            return path.read_bytes()
        except EOFError as e:  # a gzip stream that ends before it should
            raise OSError(f"the gzip stream ends before it should: {e}") from e
    return path.read_bytes()


def leaked_file(run_dir: Path, keys: list[str]) -> Path | None:
    """The first file of the record whose bytes hold any of `keys`, a `.gz` file read through its
    compression; a `.gz` that is not gzip is searched as the bytes it is. None when no file holds
    any of them. A file the search cannot read through, or a link or a directory it will not walk
    into, raises a LeakedKey naming the path and the reason: the search never fails open."""
    needles = [key.encode() for key in keys]
    for path in _record_files(run_dir):
        try:
            data = _read_through(path)
        except OSError as e:  # a file that cannot be read refuses the commit, never a skip
            raise LeakedKey(f"{path}: the record cannot be searched: {e}")
        if any(needle in data for needle in needles):
            return path
    return None


def configured_keys() -> list[str]:
    """Every key the instance's configuration names, read from its file. A configuration whose
    roles are missing, malformed or name no role is a LeakedKey naming the configuration's file and
    which fault, never a value: a key that cannot be named cannot be searched for, and a record
    searched for no key is a record unsearched. A key file that cannot be read is a LeakedKey
    naming it, never a value: a key that cannot be searched for cannot be shown to be absent."""
    try:
        paths = key_paths()
    except (ValueError, OSError) as e:
        raise LeakedKey(str(e)) from e
    keys: list[str] = []
    for path in paths:
        try:
            keys.append(read_key(path))
        except (ValueError, OSError) as e:
            raise LeakedKey(str(e)) from e
    if not keys:  # a roles table holding no role leaves the search with nothing to look for
        raise LeakedKey(f"{instance_config()}: the instance configuration names no key")
    return keys


def commit_record(store: Path, run_dir: Path, key: str | None = None) -> None:
    """The record committed to the store as one commit of its own, the one place a record is
    searched and committed. A store that is not yet a git repository is made one now; the whole
    record is searched for every key the instance's configuration names -- the one key `key` names
    instead when the caller gives it -- a `.gz` file read through its compression, a `.gz` that is
    not gzip read as the bytes it is, and a record that holds any of them is not committed: a
    LeakedKey names the file, never the value. A configuration whose roles are missing or malformed,
    or that names no key at all, refuses the commit too, naming the configuration's file; a key file
    the configuration names that cannot be read refuses it naming that key file. The search never
    fails open: a file it cannot read through, a `.gz` that ends before its stream does, and a link
    or a directory it will not walk into refuse the commit the same way. The record and nothing
    else enters the commit whatever else the store holds uncommitted, the message the stamp, the
    author and committer the factory's."""
    keys = configured_keys() if key is None else [key]
    if not keys:  # nothing to search for: a record searched for nothing is unsearched
        raise LeakedKey(f"{instance_config()}: the instance configuration names no key")
    # The program's own key for the older, records-only configuration is empty; a caller that
    # names one key itself is searched for that one, and an empty key names no key at all.
    keys = [k for k in keys if k]
    try:
        top = _store_git(store, "rev-parse", "--show-toplevel").strip()
    except (GitError, OSError, subprocess.SubprocessError):
        top = ""
    if not top or Path(top).resolve() != store.resolve():
        _store_git(store, "init", "-q")  # a store that is not a git repository is made one now
    leaked = leaked_file(run_dir, keys)
    if leaked is not None:
        raise LeakedKey(str(leaked))
    try:
        # -f: an ignore file of the host's or of the store's does not keep any file of the record
        # out, so the commit holds every file of the record.
        _store_git(store, "add", "-f", "--", run_dir.name)
        _store_git(store, "commit", "-q", "-m", run_dir.name, "--", run_dir.name)
    except (GitError, OSError, subprocess.SubprocessError):
        _unstage(store, run_dir.name)  # a refused commit leaves nothing of the record staged
        raise


def main(argv: list[str], model: Any = None, sandbox: Any = None,
         hidden: tuple[str, ...] = ()) -> int:  # fmt: skip
    if len(argv) != 3 or not argv[1].strip() or not argv[2].strip():
        return usage_error()
    checkout = Path(argv[1]).resolve()
    if not checkout.is_dir():
        return usage_error(f"not a directory: {argv[1]}")
    # A checkout is the root of its own repository, and the environment may not point git
    # elsewhere. The first half: `git rev-parse --show-toplevel` run in the directory must name
    # it -- a subdirectory of a repository answers with the repository's root, a stray .git that
    # is not git's fails, and a worktree, whose .git is a file, answers with itself. The second
    # half: git runs with its environment's GIT_* pointers removed (see git_env), so a directory
    # the environment points at another repository is refused and not answered for. It is a usage
    # error, refused before the run directory or the key is touched.
    try:
        top = git(checkout, "rev-parse", "--show-toplevel").strip()
    except FileNotFoundError:
        return usage_error(f"git is not available: {argv[1]}")
    except GitError as e:
        # git ran and refused the directory. It is no checkout only when git itself says so, read
        # from the first line of its stderr after `fatal: ` and nothing else: a directory with no
        # repository above it ("not a git repository") and a .git that is not git's ("invalid
        # gitfile format") are the two such refusals, with no probe. Any other refusal of git's --
        # a broken configuration, here or at a later call -- carries git's own words, exit 2, since
        # a good checkout is not called not a git checkout for git's failure.
        refusal = git_refusal(str(e))
        if not refusal.startswith(("not a git repository", "invalid gitfile format")):
            return usage_error(str(e))
        return usage_error(f"not a git checkout: {argv[1]}")
    except (OSError, subprocess.SubprocessError) as e:
        return usage_error(f"git could not run: {e}")
    if not top or Path(top).resolve() != checkout:
        return usage_error(f"not a git checkout: {argv[1]}")
    # The argument is text, or one word ending in .md that names a seed note; the note's text is
    # the checkout's commit, `git show HEAD:<path>`. A path that leaves the checkout, names no
    # file of the commit, or a note without a ## Goal with text under it, is refused here, before
    # any run directory exists.
    try:
        goal, seed = read_seed(checkout, argv[2].strip())
    except (ValueError, OSError, subprocess.SubprocessError) as e:
        return usage_error(str(e))
    # A build is reproducible only if the checkout it ran on is committed: a dirty git checkout is
    # a usage error, refused before the run directory or the key is touched.
    try:
        dirty = dirty_paths(checkout)
    except (OSError, subprocess.SubprocessError, GitError) as e:
        return usage_error(str(e))
    if dirty:
        shown = ", ".join(dirty[:5]) + (" ..." if len(dirty) > 5 else "")
        return usage_error(f"the checkout has uncommitted or untracked changes: {shown}")
    try:
        checkout_head = head(checkout)
    except (OSError, subprocess.SubprocessError, GitError) as e:
        return usage_error(str(e))
    if not checkout_head:  # a git checkout with no commit has nothing to pin the run to
        return usage_error(f"the checkout has no commit: {argv[1]}")
    # The store is the instance's, from its configuration; a configuration the run cannot use is a
    # usage error before the key is read, a model called or anything made. The configuration's own
    # faults come first, then the key, then the store's directory.
    try:
        config = instance_config()
        store = record_store(checkout)
    except (ValueError, OSError) as e:
        return usage_error(str(e))
    # The run's model and key file are the instance's `builder` role. A configuration that holds no
    # roles, holds others but not that one, or holds a malformed one cannot say which key a run
    # uses, and is refused in the words `instance.py` raises for it -- naming the configuration's
    # file and the role -- before the model is called or anything is made, as any other
    # configuration a run cannot use is. The older, records-only configuration that names neither
    # `roles` nor `work` is no run's configuration at all: nothing there can name a key, and the
    # program's own model and key still answer for it.
    try:
        builder_role = instance_role("builder")
    except (ValueError, OSError) as e:
        _, data = _read_config()
        if "roles" in data or "work" in data:
            return usage_error(str(e))
        builder_role = None
    # The key file holds the bare key, or one `name=value` line as in an env file; one that cannot
    # be read or holds no key is a usage error too, before anything is made.
    if builder_role is None:
        model_name, key, base_url = MODEL, "", None
    else:
        model_name, base_url = builder_role.model, builder_role.base_url
        try:
            key = read_key(builder_role.key)
        except (ValueError, OSError) as e:
            return usage_error(str(e))
    # The role's model must be one the one function can price before a run on it starts: the spend
    # ceilings are the only bound on a run, and a ceiling derived from another model's rate is not a
    # ceiling. A model neither the table nor the library can price is refused naming the role and the
    # model, exit 2, before a model is called and before a record is made.
    try:
        require_price(model_name, base_url)
    except UnknownPrice:
        return usage_error(f"the builder role runs on model {model_name}, which cannot be priced")
    # The store's directory is made once the configuration is read and the key is a key; a plain
    # file or a path the run cannot make is a usage error naming both the configuration and the
    # store.
    try:
        store.mkdir(parents=True, exist_ok=True)
    except OSError:
        return usage_error(f"{config}: records {store} cannot be made")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir, nth = store / stamp, 1
    while True:  # two runs in the same second each keep their own record
        try:
            run_dir.mkdir(parents=True)
            break
        except FileExistsError:
            nth += 1
            run_dir = store / f"{stamp}-{nth}"
    (run_dir / "goal.txt").write_text(goal + "\n")

    wire = Wire(run_dir / "wire.jsonl")
    usage = RunUsage()  # the run counts into it; the tools ask it, the record prices it

    def spent() -> float:
        """What the run has spent so far, in the record's own arithmetic: the one function's price
        for every token the run counted on the role's model, reached at the role's address -- which
        the configuration check above has already proved it can price. The library's own running
        total is never consulted: it adds a response's cost only when the library gave one for that
        response and its tokens always, so a sum of some of a run's responses is not the run's
        price, and what bounds the run must be what its record carries."""
        return price(usage, model_name, base_url)

    tools = Tools(checkout, run_dir, hidden=(*HIDDEN, *hidden), spent=spent,
                  sandbox=sandbox if sandbox is not None else Sandbox())  # fmt: skip
    agent = build_agent(tools, key=key, http_client=wire.client, model=model, model_name=model_name,
                        base_url=base_url)  # fmt: skip
    t0 = time.time()
    report, messages, usage, stopped, detail = run(agent, goal, usage=usage)
    seconds = round(time.time() - t0, 1)

    # The record's check is the tree the run left, whatever ended it: when the model wrote or
    # edited since its last check the builder runs the same check once more, numbered after the
    # model's own and logged beside them, so `check` in the numbers is the last check run -- or
    # `none`, when that final check could not run and no verdict stands for the tree it left.
    tools.check_final()

    (run_dir / "messages.json").write_bytes(ModelMessagesTypeAdapter.dump_json(messages, indent=1))
    if report is not None:
        (run_dir / "report.json").write_text(report.model_dump_json(indent=1) + "\n")
        (run_dir / "response.md").write_text(render(report))
    try:
        changes = record_diff(checkout, run_dir)
    except (OSError, ValueError, subprocess.SubprocessError, GitError) as e:  # never lose the record
        changes = {"diff": f"error: {e}", "files_changed": 0, "insertions": 0, "deletions": 0}
    # The record's cost is the tokens priced through the one function, so the number in the record
    # and the number the tools land on are the same arithmetic: `price` is the factory's table for
    # `MODEL` and the library's row, at the role's address, for every model the configuration check
    # above proved it can price. The library's own running total is not the run's price, and
    # `cost_source` names the source that answered and never the name that was configured. `MODEL`
    # stays the table's, so every record ever written stays comparable with every after it.
    cost_usd = round(price(usage, model_name, base_url), 5)
    cost_source = priced(RunUsage(), model_name, base_url)[1]
    checks = [c["exit"] for c in tools.checks]
    numbers = {
        "model": model_name,
        "role": sha256(ROLE),
        "wrapper": sha256(Path(__file__).read_text()),
        "library": LIBRARY,
        "checkout": str(checkout),
        "head": checkout_head,
        "seed": seed,
        "stopped": stopped,
        "cap": which_cap(stopped, detail),
        # The shape errors the library answered, by the tool each named: what a run spent learning a
        # call it did not have, and `{}` when the library corrected none of them.
        "retries": shape_retries(messages),
        "requests": usage.requests,
        "requests_cap": limits().request_limit,
        "wire_attempts": wire.attempts,
        "tool_calls": usage.tool_calls,
        "calls_cap": CALLS_LIMIT,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cache_read_tokens": usage.cache_read_tokens,
        "reasoning_tokens": usage.details.get("reasoning_tokens", 0),
        "cost_usd": cost_usd,
        "cost_source": cost_source,
        # The spend ceilings, beside the count they bound: the soft one the tools land a run on and
        # the hard one the run itself ends on.
        "spend_cap": SOFT_SPEND,
        "hard_spend_cap": HARD_SPEND,
        "lists": len(tools.listed),
        "reads": len(tools.read_paths),
        "files_read": len(set(tools.read_paths)),
        "lines_read": tools.lines_read,
        "bytes_read": tools.bytes_read,
        "searches": len(tools.searched),
        "writes": len(tools.written),
        "edits": len(tools.edited),
        # The paths the tools touched, in order: the record names every file the run changed,
        # whatever git lists or hides from the diff.
        "written": tools.written,
        "edited": tools.edited,
        "checks": len(checks),
        # The tools' own truth about the checkout, next to the report's claim about it: the last
        # check's verdict, but only when that check saw the tree the record is for. A run that wrote
        # since its last check and whose final check could not run -- `check_final` swallows the
        # sandbox's failure so the record survives -- has no verdict on the tree it left: the flag
        # still says the check is due, so `check` says nothing rather than carrying the stale one.
        "check": "none" if not checks or tools.changed_since_check
                 else "green" if checks[-1] == 0 else "red",  # fmt: skip
        "check_seconds": round(sum(c["seconds"] for c in tools.checks), 1),
        **changes,
        "seconds": seconds,
    }
    recorded = numbers | {"detail": detail} if detail else numbers  # why it stopped, if not answer
    (run_dir / "numbers.json").write_text(json.dumps(recorded, indent=1) + "\n")
    # The record is the factory's: the wire is compressed and the whole record searched for every
    # key the instance's configuration names by the one function that commits it, whatever ended
    # the run.
    compress_wire(run_dir)
    print(run_dir)  # the first line the builder prints is the record's path
    numbers_line = " ".join(f"{k}={v}" for k, v in numbers.items())  # stays one line of k=v
    try:
        # A run made as a role searches every key the configuration names; the older, records-only
        # run that names no role has only the program's own key, and names that itself, so the
        # configuration is not consulted for it.
        commit_record(store, run_dir, key=None if builder_role is not None else key)
    except LeakedKey as e:
        print(numbers_line)
        print(f"{e}: the record holds the key", file=sys.stderr)  # never the value
        return 1
    except (GitError, OSError, subprocess.SubprocessError) as e:
        # A commit the store refuses is a run reported, never a traceback: the record's path was
        # the first line and the numbers line follows it, one line on stderr names the record and
        # git's own words, and the record stays on disk with nothing of it staged.
        print(numbers_line)
        print(f"{run_dir}: {' '.join(str(e).split())}", file=sys.stderr)
        return 1
    print(numbers_line)
    if detail:
        print(f"{stopped}: {detail}", file=sys.stderr)
    return 0 if stopped == "answer" else 1


def cli() -> None:
    """The console script's entry: no argument, `main` called with `sys.argv` whole and the process
    exited with what `main` returned, as the guard does when the file is run."""
    sys.exit(main(sys.argv))


if __name__ == "__main__":
    cli()
