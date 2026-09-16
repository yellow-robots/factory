#!/usr/bin/env python3
"""The builder: a cold session that changes a checkout until its tests pass.

    uv run builder.py <checkout> "<goal>"

The checkout is the directory named on the command line, reachable only through six tools:
list, read, search, write, edit and check. Writes are confined to the checkout and refused on the goal's
tests and the toolchain; check runs the checkout's tests in a container with no network and the
checkout mounted read-only, so code the model writes never runs on the host and cannot reach the
key. The loop is pydantic-ai, pinned; the provider is DeepSeek's chat completions API, the key
read from ~/.config/factory/deepseek.key and never written anywhere. Each run leaves
runs/<utc-stamp>/ under the factory itself, never in the checkout, with goal.txt, wire.jsonl
(every HTTP attempt as it happened), messages.json (the library's messages), check-<n>.log per
check, diff.patch (what the run left in the checkout; absent when it left nothing), report.json,
response.md (the report rendered) and numbers.json.
"""

from __future__ import annotations

import fnmatch
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

# Before the import: the library greets stderr once per process unless this is set.
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

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
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIChatModelSettings  # noqa: E402
from pydantic_ai.profiles.openai import OpenAIModelProfile  # noqa: E402
from pydantic_ai.providers.deepseek import DeepSeekProvider  # noqa: E402

RUNS = Path(__file__).resolve().parent / "runs"  # the factory's record, never inside the checkout
KEY_FILE = Path.home() / ".config" / "factory" / "deepseek.key"
MODEL = "deepseek-flash"
LIBRARY = "pydantic-ai-slim " + importlib.metadata.version("pydantic-ai-slim")
TOOL_CALLS_CAP = 80  # tool calls per run; over it the run stops with no report
REQUEST_CAP = 60  # provider requests per run
LIST_CAP = 500  # entries per list
READ_LINES_CAP = 300  # lines per read
READ_BYTES_CAP = 32_000  # bytes per read
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
CHECK_TAIL_LINES = 60  # lines of check output handed back
CHECK_TAIL_BYTES = 8_000  # and at most this many bytes of them
IMAGE_TIMEOUT = 600  # seconds for the one image build
# Hidden at the root because they are what running and installing the program leave behind,
# not the checkout; .git is the human's record and its hooks run on the host.
HIDDEN = ("runs", ".claude", "__pycache__", ".venv", ".git")
# Refused to write and edit: the tests are the goal's acceptance criteria, the toolchain is what
# check runs against, and a .gitattributes or .gitignore the model wrote would change what git
# records of the run. A basename glob anywhere, a dotted basename anywhere, a prefix, or an exact
# path at the root; the glob is unittest's own discovery pattern, so every file the check collects
# is covered.
PROTECTED = ("test*.py", "tests/", "pyproject.toml", "uv.lock", "check.Dockerfile", "docs/",
             ".gitattributes", ".gitignore")  # fmt: skip
# USD per 1M tokens, peak rates; api-docs.deepseek.com/quick_start/pricing read on 2026-09-15.
PRICE = {"cache_hit": 0.006, "cache_miss": 0.3, "output": 1.2}

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
                 protected: tuple[str, ...] = PROTECTED, sandbox: Any = None):  # fmt: skip
        self.root = root.resolve()
        self.run_dir = run_dir
        self.hidden = hidden
        self.protected = protected
        self.sandbox = sandbox
        self.listed: list[str] = []
        self.read_paths: list[str] = []
        self.searched: list[str] = []
        self.lines_read = 0
        self.written: list[str] = []
        self.edited: list[str] = []
        self.checks: list[dict[str, Any]] = []

    def _resolve(self, path: str) -> tuple[Path, str]:
        p = (self.root / (path or ".")).resolve()
        if p != self.root and self.root not in p.parents:
            raise ValueError(f"outside the checkout: {path}")
        rel = p.relative_to(self.root).as_posix() or "."
        parts = rel.split("/")
        # A .git component at any depth is git's, not the checkout's: a write there could forge a
        # nested repository and hide a subtree from the record. The other hidden names are only
        # the record at the root.
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

    def _capped(self) -> str:
        if len(self.written) + len(self.edited) >= WRITE_CAP:
            return f"error: cap reached ({WRITE_CAP} writes and edits); report now"
        return ""

    def list(self, path: str = ".") -> str:
        """List one directory of the checkout: one entry per line as kind, size, name. Path is the
        directory to list, relative to the checkout root; '.' is the root.

        Args:
            path: The directory to list, relative to the checkout root.
        """
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

    def read(self, path: str, start: int = 1) -> str:
        """Read a file of the checkout as numbered lines, from line `start` (1-based), at most 300
        lines or 32000 bytes per call; a truncated read says where to continue.

        Args:
            path: The file to read, relative to the checkout root.
            start: The first line to read, 1-based.
        """
        try:
            p, rel = self._resolve(path)
            if not p.is_file():
                raise ValueError(f"not a file: {path}")
            start = max(1, int(start))
            out: list[str] = []
            n = nbytes = 0
            with p.open("r", encoding="utf-8", errors="replace") as f:
                for i, line in enumerate(f, 1):
                    if i < start:
                        continue
                    size = len(line.encode())
                    if n >= READ_LINES_CAP or nbytes + size > READ_BYTES_CAP:
                        if n:  # one line per call at least, or a long line dead-ends the read
                            out.append(f"...\ttruncated; continue with start={i}")
                            break
                        cut = line.encode()[:READ_BYTES_CAP].decode("utf-8", "ignore")
                        out.append(f"{i}\t{cut} …(line cut at {READ_BYTES_CAP} bytes)")
                    else:
                        out.append(f"{i}\t{line.rstrip(chr(10))}")
                    n += 1
                    nbytes += size
        except (ValueError, OSError, RuntimeError) as e:  # RuntimeError: a symlink loop
            return f"error: {e}"
        self.read_paths.append(rel)
        self.lines_read += n
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
        return f"edited {rel} ({before} -> {len(text.splitlines())} lines)"

    def check(self) -> str:
        """Run the checkout's tests and return the exit code and the tail of the output: exit 0 is
        green, anything else is red. The tests run in a container, with the checkout read-only and
        no network, so this reports on the checkout as it is on disk. At most 8 checks per run.
        """
        if len(self.checks) >= CHECK_CAP:
            return f"error: cap reached ({CHECK_CAP} checks); report now"
        if self.sandbox is None:
            return "error: no sandbox; check is not available in this run"
        n = len(self.checks) + 1
        t0 = time.time()
        try:
            code, output = self.sandbox.run(self.root, self.run_dir, n)
            seconds = round(time.time() - t0, 1)
            log = self.run_dir / f"check-{n}.log"
            log.write_text(output, encoding="utf-8", errors="replace")
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as e:
            return f"error: {e}"
        self.checks.append({"exit": code, "seconds": seconds})
        tail = "\n".join(output.splitlines()[-CHECK_TAIL_LINES:])
        if len(tail.encode()) > CHECK_TAIL_BYTES:  # the end of the output is the part that says why
            tail = tail.encode()[-CHECK_TAIL_BYTES:].decode("utf-8", "ignore")
        return f"exit {code}\n{tail}"


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
            "--memory", "1g", "--cpus", "2", "--pids-limit", "256",
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


def build_agent(
    tools: Tools, key: str = "", http_client: Any = None, model: Any = None
) -> Agent[None, BuildReport]:
    """The agent: the role, the six tools, a typed report, our caps."""
    if model is None:
        model = OpenAIChatModel(
            MODEL, provider=DeepSeekProvider(api_key=key, http_client=http_client), profile=PROFILE
        )
    return Agent(
        model,
        instructions=ROLE,
        output_type=BuildReport,
        tools=[
            Tool(tools.list, takes_ctx=False),
            Tool(tools.read, takes_ctx=False),
            Tool(tools.search, takes_ctx=False),
            Tool(tools.write, takes_ctx=False),
            Tool(tools.edit, takes_ctx=False),
            Tool(tools.check, takes_ctx=False),
        ],
        # No temperature: DeepSeek ignores it in thinking mode, and the settings should say what
        # the request actually is. Thinking stays at the API default.
        model_settings=OpenAIChatModelSettings(timeout=180),
        retries={"tools": 1, "output": 2},
    )


def run(agent: Agent[None, BuildReport], goal: str) -> tuple[BuildReport | None, list, RunUsage, str, str]:
    """One run under the caps: the report if there is one, the messages either way."""
    usage = RunUsage()
    report, stopped, detail = None, "answer", ""
    with capture_run_messages() as messages:
        try:
            result = agent.run_sync(
                goal,
                usage=usage,
                usage_limits=UsageLimits(tool_calls_limit=TOOL_CALLS_CAP, request_limit=REQUEST_CAP),
            )
            report = result.output
        except UsageLimitExceeded as e:
            stopped, detail = "cap", str(e)
        except (UnexpectedModelBehavior, ModelAPIError) as e:  # ModelHTTPError is one of these
            stopped, detail = "error", str(e)
    return report, list(messages), usage, stopped, detail


# The environment's own GIT_* pointers are not the checkout's: git runs without them, so it
# discovers the repository from the directory it is given and not from where the caller points.
GIT_ENV_UNSET = (
    "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
)  # fmt: skip


def git_env() -> dict[str, str]:
    """The environment git runs in: the caller's, without its own GIT_* pointers, and in English,
    so git's refusals are the ones the code reads whatever the host's locale says."""
    env = dict(os.environ)
    for name in GIT_ENV_UNSET:
        env.pop(name, None)
    env["LC_ALL"] = "C"
    return env


class GitError(RuntimeError):
    """git ran and exited nonzero: the message carries git's own words."""


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


def main(argv: list[str], model: Any = None, sandbox: Any = None) -> int:
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
    # The key file holds the bare key, or one `name=value` line as in an env file.
    key = KEY_FILE.read_text().strip().rsplit("=", 1)[-1].strip().strip("'\"")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir, nth = RUNS / stamp, 1
    while True:  # two runs in the same second each keep their own record
        try:
            run_dir.mkdir(parents=True)
            break
        except FileExistsError:
            nth += 1
            run_dir = RUNS / f"{stamp}-{nth}"
    (run_dir / "goal.txt").write_text(goal + "\n")

    wire = Wire(run_dir / "wire.jsonl")
    tools = Tools(checkout, run_dir, sandbox=sandbox if sandbox is not None else Sandbox())
    agent = build_agent(tools, key=key, http_client=wire.client, model=model)
    t0 = time.time()
    report, messages, usage, stopped, detail = run(agent, goal)
    seconds = round(time.time() - t0, 1)

    (run_dir / "messages.json").write_bytes(ModelMessagesTypeAdapter.dump_json(messages, indent=1))
    if report is not None:
        (run_dir / "report.json").write_text(report.model_dump_json(indent=1) + "\n")
        (run_dir / "response.md").write_text(render(report))
    try:
        changes = record_diff(checkout, run_dir)
    except (OSError, ValueError, subprocess.SubprocessError, GitError) as e:  # never lose the record
        changes = {"diff": f"error: {e}", "files_changed": 0, "insertions": 0, "deletions": 0}
    miss = usage.input_tokens - usage.cache_read_tokens
    table = (
        usage.cache_read_tokens * PRICE["cache_hit"]
        + miss * PRICE["cache_miss"]
        + usage.output_tokens * PRICE["output"]
    ) / 1e6
    priced = usage.cost is not None  # genai-prices has no deepseek-flash row; ours is the fallback
    cost_usd = round(float(usage.cost) if priced else table, 5)
    checks = [c["exit"] for c in tools.checks]
    numbers = {
        "model": MODEL,
        "role": sha256(ROLE),
        "wrapper": sha256(Path(__file__).read_text()),
        "library": LIBRARY,
        "checkout": str(checkout),
        "head": checkout_head,
        "seed": seed,
        "stopped": stopped,
        "requests": usage.requests,
        "wire_attempts": wire.attempts,
        "tool_calls": usage.tool_calls,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cache_read_tokens": usage.cache_read_tokens,
        "reasoning_tokens": usage.details.get("reasoning_tokens", 0),
        "cost_usd": cost_usd,
        "cost_source": "genai-prices" if priced else "table",
        "lists": len(tools.listed),
        "reads": len(tools.read_paths),
        "files_read": len(set(tools.read_paths)),
        "lines_read": tools.lines_read,
        "searches": len(tools.searched),
        "writes": len(tools.written),
        "edits": len(tools.edited),
        # The paths the tools touched, in order: the record names every file the run changed,
        # whatever git lists or hides from the diff.
        "written": tools.written,
        "edited": tools.edited,
        "checks": len(checks),
        # The tools' own truth about the checkout, next to the report's claim about it.
        "check": "none" if not checks else "green" if checks[-1] == 0 else "red",
        "check_seconds": round(sum(c["seconds"] for c in tools.checks), 1),
        **changes,
        "seconds": seconds,
    }
    recorded = numbers | {"detail": detail} if detail else numbers  # why it stopped, if not answer
    (run_dir / "numbers.json").write_text(json.dumps(recorded, indent=1) + "\n")
    print(run_dir)
    print(" ".join(f"{k}={v}" for k, v in numbers.items()))  # the numbers line stays one line of k=v
    if detail:
        print(f"{stopped}: {detail}", file=sys.stderr)
    return 0 if stopped == "answer" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
