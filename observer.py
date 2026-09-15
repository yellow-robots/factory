#!/usr/bin/env python3
"""The observer: a cold session that looks at a world and reports. Factory v0.2.

    uv run observer.py "<goal>"

The world is the directory this file lives in, reachable only through two functions, list and
read; the run record under runs/ is not part of the world. The loop is pydantic-ai, pinned; the
provider is DeepSeek's chat completions API, the key read from ~/.config/factory/deepseek.key
and never written anywhere. Each run leaves runs/<utc-stamp>/ with goal.txt, wire.jsonl (every
HTTP attempt as it happened), messages.json (the library's messages), report.json, response.md
(the report rendered) and numbers.json.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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

WORLD = Path(__file__).resolve().parent
RUNS = WORLD / "runs"
KEY_FILE = Path.home() / ".config" / "factory" / "deepseek.key"
MODEL = "deepseek-flash"
LIBRARY = "pydantic-ai-slim " + importlib.metadata.version("pydantic-ai-slim")
TOOL_CALLS_CAP = 40  # tool calls per run; over it the run stops with no report
REQUEST_CAP = 60  # provider requests per run
LIST_CAP = 500  # entries per list
READ_LINES_CAP = 300  # lines per read
READ_BYTES_CAP = 32_000  # bytes per read
# Hidden at the root because they are what running, installing and planning the program leave
# behind, not the world.
HIDDEN = ("runs", ".claude", "__pycache__", ".venv", "plans")
# USD per 1M tokens, peak rates; api-docs.deepseek.com/quick_start/pricing read on 2026-09-15.
PRICE = {"cache_hit": 0.006, "cache_miss": 0.3, "output": 1.2}

ROLE = """\
You are the observer. You are given a goal and a world: a directory you can explore with two
functions, list and read. Your only product is a report about the world as it bears on the goal.

Explore first, then write the report. Return the report through the `final_result` function, one
field per section:

## Looked at
The paths you listed or read, in the order you did.

## Found
What is there that bears on the goal. Facts only, each naming the path it comes from.

## Missing
What the goal needs that is not there.

## Unsure
What you could not determine from the world, and why.

Rules:
- Facts only. No recommendations, no plans, no code, no judgement of quality.
- A claim in Found names the path it comes from; a claim without a path does not go in.
- Read what the goal needs and nothing else.
- Stop when another read would not change the report, and write it.
- If the goal cannot be answered from the world, the report says so under Missing.
"""


class Report(BaseModel):
    """The observer's report on the world as it bears on the goal."""

    looked_at: list[str] = Field(description="The paths you listed or read, in the order you did.")
    found: list[str] = Field(
        description="What is there that bears on the goal. Facts only, each naming the path it "
        "comes from."
    )
    missing: list[str] = Field(description="What the goal needs that is not there.")
    unsure: list[str] = Field(description="What you could not determine from the world, and why.")


SECTIONS = (("Looked at", "looked_at"), ("Found", "found"), ("Missing", "missing"), ("Unsure", "unsure"))


def render(report: Report) -> str:
    """The report in v0.1's markdown shape: four headings, one bullet per item."""
    out: list[str] = []
    for heading, field in SECTIONS:
        out.append(f"## {heading}")
        items = getattr(report, field)
        out.extend(f"- {item}" for item in items or ["(none)"])
        out.append("")
    return "\n".join(out)


class Plane:
    """The execution plane: what the model can do to the world, and the record of it."""

    def __init__(self, root: Path, hidden: tuple[str, ...] = HIDDEN):
        self.root = root.resolve()
        self.hidden = hidden
        self.listed: list[str] = []
        self.read_paths: list[str] = []
        self.lines_read = 0

    def _resolve(self, path: str) -> tuple[Path, str]:
        p = (self.root / (path or ".")).resolve()
        if p != self.root and self.root not in p.parents:
            raise ValueError(f"outside the world: {path}")
        rel = p.relative_to(self.root).as_posix() or "."
        if rel.split("/", 1)[0] in self.hidden:
            raise ValueError(f"not part of the world: {path}")
        return p, rel

    def list(self, path: str = ".") -> str:
        """List one directory of the world: one entry per line as kind, size, path. Path is
        relative to the world root; '.' is the root.

        Args:
            path: The directory to list, relative to the world root.
        """
        try:
            p, rel = self._resolve(path)
            if not p.is_dir():
                raise ValueError(f"not a directory: {path}")
            entries = sorted(p.iterdir(), key=lambda e: (not e.is_dir(), e.name))
            if rel == ".":
                entries = [e for e in entries if e.name not in self.hidden]
            lines = []
            for e in entries[:LIST_CAP]:
                kind = "link" if e.is_symlink() else "dir" if e.is_dir() else "file"
                size = e.lstat().st_size if kind == "file" else 0
                lines.append(f"{kind}\t{size}\t{e.relative_to(self.root).as_posix()}")
            if len(entries) > LIST_CAP:
                lines.append(f"...\t{len(entries) - LIST_CAP} more entries not shown")
        except (ValueError, OSError, RuntimeError) as e:  # RuntimeError: a symlink loop
            return f"error: {e}"
        self.listed.append(rel)
        return "\n".join(lines) or "(empty)"

    def read(self, path: str, start: int = 1) -> str:
        """Read a file of the world as numbered lines, from line `start` (1-based), at most 300
        lines or 32000 bytes per call; a truncated read says where to continue.

        Args:
            path: The file to read, relative to the world root.
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
            body=body,
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
            body=response.text,
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
    plane: Plane, key: str = "", http_client: Any = None, model: Any = None
) -> Agent[None, Report]:
    """The agent: the role, the two functions of the plane, a typed report, our caps."""
    if model is None:
        model = OpenAIChatModel(
            MODEL, provider=DeepSeekProvider(api_key=key, http_client=http_client), profile=PROFILE
        )
    return Agent(
        model,
        instructions=ROLE,
        output_type=Report,
        tools=[Tool(plane.list, takes_ctx=False), Tool(plane.read, takes_ctx=False)],
        model_settings=OpenAIChatModelSettings(temperature=0, timeout=180),
        retries={"tools": 1, "output": 2},
    )


def run(agent: Agent[None, Report], goal: str) -> tuple[Report | None, list, RunUsage, str, str]:
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


def sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def main(argv: list[str], model: Any = None) -> int:
    if len(argv) != 2 or not argv[1].strip():
        print('usage: observer.py "<goal>"', file=sys.stderr)
        return 2
    goal = argv[1].strip()
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
    plane = Plane(WORLD)
    agent = build_agent(plane, key=key, http_client=wire.client, model=model)
    t0 = time.time()
    report, messages, usage, stopped, detail = run(agent, goal)
    seconds = round(time.time() - t0, 1)

    (run_dir / "messages.json").write_bytes(ModelMessagesTypeAdapter.dump_json(messages, indent=1))
    if report is not None:
        (run_dir / "report.json").write_text(report.model_dump_json(indent=1) + "\n")
        (run_dir / "response.md").write_text(render(report))
    miss = usage.input_tokens - usage.cache_read_tokens
    table = (
        usage.cache_read_tokens * PRICE["cache_hit"]
        + miss * PRICE["cache_miss"]
        + usage.output_tokens * PRICE["output"]
    ) / 1e6
    priced = usage.cost is not None  # genai-prices has no deepseek-flash row; ours is the fallback
    cost_usd = round(float(usage.cost) if priced else table, 5)
    numbers = {
        "model": MODEL,
        "role": sha256(ROLE),
        "wrapper": sha256(Path(__file__).read_text()),
        "library": LIBRARY,
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
        "lists": len(plane.listed),
        "reads": len(plane.read_paths),
        "files_read": len(set(plane.read_paths)),
        "lines_read": plane.lines_read,
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
