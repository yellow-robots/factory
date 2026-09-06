#!/usr/bin/env python3
"""tools/notify.py — deliver an iteration's changelog to its registered stakeholders (it-36 slice I,
#474).

RULING (cold review of #474, ruling 1): this act's own `epic_closed` precondition (mirrored from
`tools/release.py`'s `it/<n>` family) cannot hold while H's `tools/close-runner.sh` is still running
— that stage runs BEFORE the epic actually closes (the close arm, `tools/epic_gate.py`, closes it
only once `YR-SHIP-WALK`/`YR-ROUND-RECORD` already exist on the trail). This tool's host is
therefore a LATER moment: the design/close sweep (`tools/design_gate.py`), on a pass AFTER the epic
has self-closed — not yet wired (a future slice's own duty). Until item P (the owner's Telegram
credential and webhook secret) exists, no `[[stakeholders]]` entry can name a real telegram/webhook
address anyway, so delivery is gated on that human dependency regardless of wiring.

The manifest's `[[stakeholders]]` table (`name`, `channel` = telegram | webhook | issue-comment |
github-release, `address`, `events`) names who is told what. `channel` picks the delivery:
  telegram      — an n8n webhook (deploy/n8n-changelog-telegram.json: webhook trigger -> Telegram
                  node, the bot token in n8n's OWN credential store) — signed JSON to `address`.
  webhook       — the same signed JSON, to any system's own URL (`address`).
  issue-comment — a GitHub issue comment on `address` (an `owner/repo#N` reference, validated at
                  read time and split into gh's own `<number> --repo <owner/repo>` argv shape —
                  gh rejects the combined `owner/repo#N` form outright).
  github-release — no separate push: the GitHub Release `tools/release.py ship-it` already created
                  IS the notification for this channel, so delivery is trivially satisfied.
Every network call runs through the two injectable seams below (`_http_post`, `_gh`) — stubbed
whole in tests, the `tools/release.py:_run` precedent split in two because one is HTTP and the
other a `gh` subprocess. The signed body carries `X-YR-Signature` (HMAC-SHA256 over the exact JSON
bytes posted, keyed by `YR_NOTIFY_SECRET` from dispatch's PM-only allowlist — see
`tools/dispatch.py::_PM_ONLY_KEYS`) and a stable `event_id` (one per (release, stakeholder), so a
retried post is idempotent on the receiving end). The secret is read once from the environment and
never printed, logged, or embedded in a record; a missing secret with a network channel wanting
delivery is a fail-CLOSED refusal (`secret_missing`), never a silent unsigned/empty-keyed send.

After delivery, `record_body` posts ONE `YR-CHANGELOG` (records.toml; `iteration`, `release`,
`delivered` fields) naming the delivered set — the record the CLI's `post` subcommand emits on the
closing epic's trail.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

CHANNELS = ("telegram", "webhook", "issue-comment", "github-release")
_NETWORK_CHANNELS = ("telegram", "webhook")
GH_TIMEOUT = 20
HTTP_TIMEOUT = 20
NOTIFY_SECRET_ENV = "YR_NOTIFY_SECRET"
_ISSUE_REF_RE = re.compile(r"^([^/\s#]+/[^/\s#]+)#(\d+)$")


def _split_issue_ref(address: str) -> tuple[str, str] | None:
    """`owner/repo#N` -> (`owner/repo`, `N`), or None when `address` doesn't match — the real `gh`
    CLI rejects the combined form outright (`invalid issue format`), so every issue-comment
    stakeholder is split into gh's own `<number> --repo <owner/repo>` argv shape at call time."""
    m = _ISSUE_REF_RE.match(address)
    return (m.group(1), m.group(2)) if m else None


# ── the manifest reader: [[stakeholders]], tri-state on `_read_stage_conduct`'s own shape ────────

def _bad_stakeholder(entry) -> str | None:
    """None when `entry` is a well-formed stakeholder table; else the reason it's rejected."""
    if not isinstance(entry, dict):
        return f"not a table: {entry!r}"
    name = entry.get("name")
    channel = entry.get("channel")
    address = entry.get("address")
    events = entry.get("events")
    if not isinstance(name, str) or not name:
        return f"'name' must be a non-empty string (got {name!r})"
    if channel not in CHANNELS:
        return f"'channel' must be one of {CHANNELS} (got {channel!r})"
    if not isinstance(address, str) or not address:
        return f"'address' must be a non-empty string (got {address!r})"
    if channel == "issue-comment" and _split_issue_ref(address) is None:
        return f"'address' for channel 'issue-comment' must be 'owner/repo#N' (got {address!r})"
    if not isinstance(events, list) or not events or any(not isinstance(e, str) or not e for e in events):
        return f"'events' must be a non-empty array of non-empty strings (got {events!r})"
    return None


def read_stakeholders(manifest_text: str) -> tuple[str, list[dict] | str]:
    """("absent", None) — no `[[stakeholders]]` table declared (a repo with no stakeholders yet);
    ("ok", [...]) — every declared entry is well-formed; ("malformed", reason) — the FIRST rejected
    entry's own reason, fail-closed (never a partial delivery over a manifest that half-parses). A
    manifest that fails to parse AT ALL is "absent" too — same silent-default precedent
    `_manifest_read`'s bulk channel already uses for the scalar keys."""
    try:
        data = tomllib.loads(manifest_text)
    except Exception:
        return "absent", None
    entries = data.get("stakeholders")
    if not entries:
        return "absent", None
    if not isinstance(entries, list):
        return "malformed", f"'stakeholders' must be an array of tables (got {entries!r})"
    for entry in entries:
        reason = _bad_stakeholder(entry)
        if reason:
            return "malformed", reason
    return "ok", entries


def wants_event(stakeholder: dict, event: str) -> bool:
    events = stakeholder.get("events") or []
    return event in events or "all" in events


# ── signing ────────────────────────────────────────────────────────────────────────────────────

def hmac_signature(secret: bytes, body: bytes) -> str:
    return hmac.new(secret, body, hashlib.sha256).hexdigest()


def build_event_id(release: str, stakeholder_name: str) -> str:
    """Stable per (release, stakeholder) — a retried post for the SAME release/stakeholder pair
    carries the SAME id, so a receiver can dedupe; a different release or a different stakeholder
    never collides."""
    return hashlib.sha256(f"{release}:{stakeholder_name}".encode()).hexdigest()[:16]


# ── the two network seams — stubbed whole in tests ────────────────────────────────────────────────

def _http_post(url: str, body: bytes, headers: dict) -> tuple[bool, str]:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            return 200 <= resp.status < 300, f"HTTP {resp.status}"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        return False, str(e)


def _gh(argv: list[str]) -> tuple[int, str, str]:
    """`$GH_BIN <argv...>` (default `gh`) — the PM instance's own routing (design_gate.py,
    round_record.py, sources.py): every `gh` call this tool makes goes through `GH_BIN`, so pointing
    it at the App-token wrapper (`tools/gh-app`) makes this act run under the App's own identity,
    never an attended session's `gh` login."""
    try:
        out = subprocess.run([os.environ.get("GH_BIN", "gh"), *argv], capture_output=True, text=True,
                             timeout=GH_TIMEOUT)
        return out.returncode, out.stdout or "", out.stderr or ""
    except (OSError, subprocess.TimeoutExpired) as e:
        return 127, "", str(e)


# ── delivery ───────────────────────────────────────────────────────────────────────────────────

def notify_stakeholder(stakeholder: dict, payload: dict, secret: bytes) -> tuple[bool, str]:
    """Deliver `payload` (already carrying its own `event_id`) to one stakeholder. Never raises —
    every failure (an unreachable webhook, a `gh` failure) returns (False, detail); the caller
    decides whether that stakeholder counts as delivered."""
    channel = stakeholder["channel"]
    if channel == "github-release":
        return True, "the GitHub Release itself is the notification for this channel"
    if channel in _NETWORK_CHANNELS:
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        headers = {"Content-Type": "application/json", "X-YR-Signature": hmac_signature(secret, body)}
        return _http_post(stakeholder["address"], body, headers)
    if channel == "issue-comment":
        text = _render_comment(payload)
        ref = _split_issue_ref(stakeholder["address"])
        if ref is None:  # unreachable given read_stakeholders' own validation; fail-closed anyway
            return False, f"'address' is not 'owner/repo#N' ({stakeholder['address']!r})"
        repo, number = ref
        rc, _, err = _gh(["issue", "comment", number, "--repo", repo, "--body", text])
        return (rc == 0), (err.strip() if rc != 0 else "posted")
    return False, f"unknown channel {channel!r}"  # unreachable given read_stakeholders' own validation


def _render_comment(payload: dict) -> str:
    lines = [f"**{payload.get('iteration', '?')} shipped** — release `{payload.get('release', '?')}`"]
    notes = payload.get("notes")
    if notes:
        lines.append("")
        lines.append(notes)
    return "\n".join(lines)


def network_stakeholders_want(stakeholders: list[dict], event: str) -> bool:
    """True iff at least one stakeholder wanting `event` is on a network channel (telegram/webhook)
    — the gate `secret_missing` checks before ever attempting a send."""
    return any(wants_event(s, event) and s["channel"] in _NETWORK_CHANNELS for s in stakeholders)


def notify_all(stakeholders: list[dict], event: str, payload: dict, secret: bytes) -> list[str]:
    """Deliver to every stakeholder that wants `event`; return the names actually delivered (never
    the whole roster — a stakeholder whose channel failed is NOT in the delivered set, so the
    posted YR-CHANGELOG's `delivered` field states a fact, not an attempt). A failed delivery is
    never silent: `<name> (<channel>): <detail>` prints to stderr, one line per failure."""
    delivered = []
    release = payload.get("release", "")
    for s in stakeholders:
        if not wants_event(s, event):
            continue
        p = dict(payload)
        p["event_id"] = build_event_id(release, s["name"])
        ok, detail = notify_stakeholder(s, p, secret)
        if ok:
            delivered.append(s["name"])
        else:
            print(f"{s['name']} ({s['channel']}): {detail}", file=sys.stderr)
    return delivered


# ── the record ─────────────────────────────────────────────────────────────────────────────────

def record_body(iteration: str, release: str, delivered: list[str]) -> str:
    """YR-CHANGELOG (records.toml: marker `YR-CHANGELOG:`, mode prefix, fields `iteration`,
    `release`, `delivered`) — one compact line, the YR-TRIAGE precedent's shape."""
    names = ",".join(delivered) if delivered else "none"
    return f"YR-CHANGELOG: iteration={iteration} release={release} delivered={names}\n"


# ── CLI ────────────────────────────────────────────────────────────────────────────────────────

def _read_manifest_text(path: str | None) -> str:
    return Path(path).read_text(encoding="utf-8") if path else ""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="notify.py", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("post", help="deliver to every stakeholder wanting `event`, then post YR-CHANGELOG")
    p.add_argument("--manifest", required=True, help="path to the target repo's .yr/factory.toml")
    p.add_argument("--iteration", required=True)
    p.add_argument("--release", required=True, help="the tag, e.g. it/36")
    p.add_argument("--event", default="release")
    p.add_argument("--notes-file", default=None)
    p.add_argument("--epic", required=True, help="the issue to post YR-CHANGELOG on")
    p.add_argument("--repo", required=True, help="owner/name, for the YR-CHANGELOG post")
    p.add_argument("--test-mode", action="store_true", help="print the plan; deliver nothing, post nothing")
    args = ap.parse_args(argv)

    manifest_text = _read_manifest_text(args.manifest)
    status, entries = read_stakeholders(manifest_text)
    if status == "malformed":
        print(f"stakeholders_invalid\n{entries}")
        return 1
    stakeholders = entries or []

    payload = {"iteration": args.iteration, "release": args.release}
    if args.notes_file:
        payload["notes"] = Path(args.notes_file).read_text(encoding="utf-8")

    if args.test_mode:
        print("TEST-MODE: no delivery, no record — the plan only")
        wanted = [s["name"] for s in stakeholders if wants_event(s, args.event)]
        print(f"would notify: {wanted or '(none)'}")
        print(record_body(args.iteration, args.release, wanted), end="")
        return 0

    secret_raw = os.environ.get(NOTIFY_SECRET_ENV, "")
    if not secret_raw and network_stakeholders_want(stakeholders, args.event):
        print("secret_missing")
        print(f"{NOTIFY_SECRET_ENV} is not set, but a stakeholder wanting event {args.event!r} is on "
              f"a network channel (telegram/webhook) — refusing to send an unsigned/empty-keyed "
              f"delivery; nothing was sent")
        return 1
    secret = secret_raw.encode("utf-8")
    delivered = notify_all(stakeholders, args.event, payload, secret)
    body = record_body(args.iteration, args.release, delivered)
    rc, _, err = _gh(["issue", "comment", args.epic, "--repo", args.repo, "--body", body])
    if rc != 0:
        print(f"record_post_failed\n{err.strip()}")
        return 1
    print(body, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
