#!/usr/bin/env python3
"""The observer: a cold session that looks at a world and reports. Factory v0.1.

    python3 observer.py "<goal>"

The world is the directory this file lives in, reachable only through two functions, list and
read; the run record under runs/ is not part of the world. The provider is DeepSeek's chat
completions API with function calling; the key is read from ~/.config/factory/deepseek.key
and never written anywhere. Each run leaves runs/<utc-stamp>/ with goal.txt, transcript.jsonl
(every message as it happened), response.md (the report) and numbers.json.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

WORLD = Path(__file__).resolve().parent
RUNS = WORLD / "runs"
KEY_FILE = Path.home() / ".config" / "factory" / "deepseek.key"
ENDPOINT = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-flash"
CALL_CAP = 40  # function calls per run; then the model is asked to report with what it has
LIST_CAP = 500  # entries per list
READ_LINES_CAP = 300  # lines per read
READ_BYTES_CAP = 32_000  # bytes per read
# USD per 1M tokens, peak rates; api-docs.deepseek.com/quick_start/pricing read on 2026-09-15.
PRICE = {"cache_hit": 0.006, "cache_miss": 0.3, "output": 1.2}

ROLE = """\
You are the observer. You are given a goal and a world: a directory you can explore with two
functions, list and read. Your only product is a report about the world as it bears on the goal.

Explore first, then write the report. The report has these four sections, in this order, with
these exact headings:

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

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list",
            "description": (
                "List one directory of the world: one entry per line as kind, size, path. "
                "Path is relative to the world root; '.' is the root."
            ),
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read",
            "description": (
                f"Read a file of the world as numbered lines, from line `start` (1-based), at "
                f"most {READ_LINES_CAP} lines or {READ_BYTES_CAP} bytes per call; a truncated "
                "read says where to continue."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "start": {"type": "integer", "minimum": 1},
                },
                "required": ["path"],
            },
        },
    },
]


class Plane:
    """The execution plane: what the model can do to the world, and the record of it."""

    def __init__(self, root: Path, hidden: tuple[str, ...] = ("runs",)):
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
        self.listed.append(rel)
        return "\n".join(lines) or "(empty)"

    def read(self, path: str, start: int = 1) -> str:
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
                    out.append(f"...\ttruncated; continue with start={i}")
                    break
                out.append(f"{i}\t{line.rstrip(chr(10))}")
                n += 1
                nbytes += size
        self.read_paths.append(rel)
        self.lines_read += n
        return "\n".join(out) or "(empty)"

    def call(self, name: str, args: dict) -> str:
        if name not in ("list", "read"):
            return f"error: unknown function {name}"
        try:
            return getattr(self, name)(**args)
        except (TypeError, ValueError, OSError) as e:
            return f"error: {e}"


def complete(messages: list[dict], key: str, tools: bool = True) -> dict:
    """One provider call. Retries on rate limits and server errors, fails on anything else."""
    body: dict = {"model": MODEL, "messages": messages, "temperature": 0}
    if tools:
        body["tools"] = TOOLS
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            detail = e.read()[:400].decode(errors="replace")
            if e.code in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(2 * 2**attempt)
                continue
            raise RuntimeError(f"provider HTTP {e.code}: {detail}") from None
    raise RuntimeError("provider unreachable")


def run(goal: str, plane: Plane, provider, record) -> tuple[str, dict]:
    """The loop: role + goal, execute what the model calls, until it answers in text."""
    messages = [{"role": "system", "content": ROLE}, {"role": "user", "content": goal}]
    for m in messages:
        record(m)
    n = {"turns": 0, "calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "cache_hit_tokens": 0}
    stopped = "answer"
    while True:
        resp = provider(messages, tools=stopped == "answer")
        u = resp.get("usage", {})
        n["turns"] += 1
        n["prompt_tokens"] += u.get("prompt_tokens", 0)
        n["completion_tokens"] += u.get("completion_tokens", 0)
        n["cache_hit_tokens"] += u.get("prompt_cache_hit_tokens", 0)
        msg = resp["choices"][0]["message"]
        record({"role": "assistant", "content": msg.get("content"), "tool_calls": msg.get("tool_calls")})
        messages.append({k: v for k, v in msg.items() if k in ("role", "content", "tool_calls")})
        calls = msg.get("tool_calls") or []
        if not calls:
            n["stopped"] = stopped
            return msg.get("content") or "", n
        for tc in calls:
            n["calls"] += 1
            fn = tc["function"]
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError as e:
                args, result = {}, f"error: arguments are not JSON ({e})"
            else:
                result = plane.call(fn["name"], args)
            record({"role": "call", "name": fn["name"], "args": args, "result": result})
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})
        if n["calls"] >= CALL_CAP and stopped == "answer":
            stopped = "cap"
            m = {
                "role": "user",
                "content": f"The call cap ({CALL_CAP}) is reached. Write the report now from what you have.",
            }
            messages.append(m)
            record(m)


def sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def main(argv: list[str]) -> int:
    if len(argv) != 2 or not argv[1].strip():
        print('usage: observer.py "<goal>"', file=sys.stderr)
        return 2
    goal = argv[1].strip()
    # The key file holds the bare key, or one `name=value` line as in an env file.
    key = KEY_FILE.read_text().strip().rsplit("=", 1)[-1].strip().strip("'\"")
    run_dir = RUNS / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir.mkdir(parents=True)
    (run_dir / "goal.txt").write_text(goal + "\n")
    transcript = (run_dir / "transcript.jsonl").open("a", encoding="utf-8")

    def record(m: dict) -> None:
        transcript.write(json.dumps({"t": round(time.time(), 3), **m}, ensure_ascii=False) + "\n")
        transcript.flush()

    plane = Plane(WORLD)
    t0 = time.time()
    try:
        text, n = run(goal, plane, lambda msgs, tools=True: complete(msgs, key, tools), record)
    except RuntimeError as e:
        record({"role": "error", "content": str(e)})
        print(f"{run_dir}\nerror: {e}", file=sys.stderr)
        return 1
    (run_dir / "response.md").write_text(text + ("\n" if not text.endswith("\n") else ""))
    miss = n["prompt_tokens"] - n["cache_hit_tokens"]
    numbers = {
        "model": MODEL,
        "role": sha256(ROLE),
        "wrapper": sha256(Path(__file__).read_text()),
        **n,
        "lists": len(plane.listed),
        "reads": len(plane.read_paths),
        "files_read": len(set(plane.read_paths)),
        "lines_read": plane.lines_read,
        "cost_usd": round(
            (
                n["cache_hit_tokens"] * PRICE["cache_hit"]
                + miss * PRICE["cache_miss"]
                + n["completion_tokens"] * PRICE["output"]
            )
            / 1e6,
            5,
        ),
        "seconds": round(time.time() - t0, 1),
    }
    (run_dir / "numbers.json").write_text(json.dumps(numbers, indent=1) + "\n")
    print(run_dir)
    print(" ".join(f"{k}={v}" for k, v in numbers.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
