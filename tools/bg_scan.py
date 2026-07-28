#!/usr/bin/env python3
"""bg_scan — detect an unresolved CLI-managed background-task conversion in a stage's own archived
session transcript (issue #306).

A stage that lets a long-running command of its own auto-convert to a CLI-managed background task, then
ends its turn without observing that task to a terminal state, orphans it: the CLI kills its own
background tasks at session exit, silently, so the harness's "you'll be notified when it completes"
promise is structurally void in a one-shot stage. This is the transcript-only-visible complement to
`tools/dev-runner.sh`'s STAGE_GROUP_GRACE / wait_group_or_refuse (issue #247), which catches the inverse
case — a SHELL-backgrounded child left alive in the stage's own process group, which survives the CLI's
own exit and is still there to be reaped. A CLI-managed task is already gone from the process table by
the time that machinery looks; the archived transcript is the only durable evidence.

The conversion is matched on the PARSED JSONL's structural grammar, never a substring search over raw
line text — the self-match defense: a stage `Read`ing or `cat`ing a fixture transcript that itself
contains this marker sees it prefixed by a line number (Read) or buried inside JSON string-quoting
(cat), never leading its OWN tool_result text. The grammar (verified against real incident transcripts):
a `type: "user"` event whose `message.content[0]` is a `tool_result` block whose text BEGINS EXACTLY
with "Command running in background with ID: <id>. Output is being written to: ".

Resolution for a found id is judged only on later transcript events — positive evidence, never the
absence of one: a kill/stop tool_use naming the id, or any other later event (not the assistant's own
prose) naming the id whose text does not read as still-running. An assistant text block mentioning the
id is never resolution (an intention or a description, not an observed terminal state); a status read
that still says "running" is never resolution either.

Stdlib only, like tools/ledger.py — invoked as a subprocess from tools/dev-runner.sh.
"""
import argparse
import json
import re
import sys

# The conversion marker: start-anchored (never `.search`) so a transcript event that merely CONTAINS the
# marker text somewhere inside a larger tool_result (a Read's line-numbered dump, a cat's raw JSON) never
# matches — only a tool_result block whose text is itself exactly this at its start.
CONVERSION_RE = re.compile(r'^Command running in background with ID: ([a-z0-9]+)\. Output is being written to: ')
# A negated form ("no longer running", "not running") is a TERMINAL report, not a still-running one — it
# must win over the bare STILL_RUNNING_RE match below, or a status read that says the task ENDED would be
# misread as still-running simply for containing the word "running".
NOT_RUNNING_RE = re.compile(r'\b(?:no longer|not|n\'t)\s+running\b', re.I)
STILL_RUNNING_RE = re.compile(r'\brunning\b', re.I)
KILL_STOP_NAME_RE = re.compile(r'kill|stop', re.I)


def _load_events(path):
    """Parse `path` as JSONL, one transcript event per line. A line that fails to parse is skipped (not
    fatal on its own — a hard-killed session can leave a truncated tail line); returns `(events, ok)`
    where `ok` is False only when the file itself could not be opened/read at all."""
    try:
        text = open(path, "r", errors="replace").read()
    except OSError:
        return [], False
    events = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except ValueError:
            continue
    return events, True


def _block_text(block):
    """The textual payload of one content block, whether it's a plain text block (`text`) or a
    tool_result block (`content` — a bare string, or a list of text sub-blocks to concatenate)."""
    if isinstance(block.get("text"), str):
        return block["text"]
    content = block.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text")
    return ""


def _find_conversions(events):
    """`[(event_index, task_id), ...]` for every structurally-matched background conversion, in the
    order they appear."""
    found = []
    for i, ev in enumerate(events):
        if not isinstance(ev, dict) or ev.get("type") != "user":
            continue
        message = ev.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not isinstance(content, list) or not content:
            continue
        block = content[0]
        if not isinstance(block, dict) or block.get("type") != "tool_result":
            continue
        m = CONVERSION_RE.match(_block_text(block))
        if m:
            found.append((i, m.group(1)))
    return found


def _iter_later_blocks(events, start_idx):
    """`(role, block)` for every content block in every event strictly after `start_idx` — `role` is the
    event's own `type` (`"assistant"`, `"user"`, or whatever else the transcript carries)."""
    for ev in events[start_idx + 1:]:
        if not isinstance(ev, dict):
            continue
        role = ev.get("type")
        message = ev.get("message")
        content = message.get("content") if isinstance(message, dict) else ev.get("content")
        if isinstance(content, str):
            yield role, {"type": "text", "text": content}
            continue
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict):
                yield role, block


def _names_id(text, task_id):
    """Whether `text` names `task_id` as its own token, not merely as a substring of something longer —
    ids are `[a-z0-9]+` (word characters only), so a `\\b`-anchored search is exact."""
    return re.search(r'\b' + re.escape(task_id) + r'\b', text) is not None


def _is_resolved(events, start_idx, task_id):
    for role, block in _iter_later_blocks(events, start_idx):
        btype = block.get("type")
        if role == "assistant" and btype == "text":
            continue  # the assistant's own prose mention of the id is never resolution
        if btype == "tool_use":
            if KILL_STOP_NAME_RE.search(block.get("name", "") or "") and _names_id(json.dumps(block.get("input", {})), task_id):
                return True
            continue  # a non-kill/stop tool_use (e.g. a plain status check) is not itself resolution
        text = _block_text(block)
        if not _names_id(text, task_id):
            continue
        if NOT_RUNNING_RE.search(text):
            return True  # an explicit "no longer/not running" report IS a terminal state
        if STILL_RUNNING_RE.search(text):
            continue  # a status read that still reports "running" is not resolution
        return True
    return False


def scan(path):
    """Return `{"parsed": bool, "unresolved": [task_id, ...]}` for the transcript at `path`. `parsed` is
    False only when the file could not be read or held nothing parseable at all — the caller treats that
    as log-and-continue, never a gate (positive, session-attributed evidence only)."""
    events, ok = _load_events(path)
    if not ok or not events:
        return {"parsed": False, "unresolved": []}
    unresolved = [tid for idx, tid in _find_conversions(events) if not _is_resolved(events, idx, tid)]
    return {"parsed": True, "unresolved": unresolved}


def _cli_scan(args):
    print(json.dumps(scan(args.transcript)))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_scan = sub.add_parser("scan", help="scan an archived stage transcript for an unresolved background-task conversion")
    p_scan.add_argument("--transcript", required=True)
    p_scan.set_defaults(func=_cli_scan)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
