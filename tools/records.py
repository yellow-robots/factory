#!/usr/bin/env python3
"""records.py — loader + CLI for the record registry (`records.toml`, it-30 slice 1, epic #415).

The registry is the one machine-readable home for every machine-parsed trail grammar: the `YR-`
family, the two unprefixed grammars (the line-anchored review verdict; the stage escape), and the
versioned JSON record schemas. A record absent from the registry is unsanctioned — the canon states
that authority; this loader is how tools read the home.

Shape rules the loader enforces (fail-loud, never guess):
  * `[marker].yr` is the single named marker constant — one edit plus a migration round changes it.
  * every record has a unique, non-empty `name`, a non-empty `marker`, a `mode` from the closed
    vocabulary, and at least one surface from the closed surface set;
  * a record whose name starts with the marker constant must carry a marker that also starts with it
    (the umbrella is consistent with itself);
  * `lanes` is optional data (authored by the canon slice): absent or empty means nothing mandated —
    consumers (the trail-shape detector) treat that as zero mandates, never an error; when present,
    every lane maps to a list of registered record names, shape-checked here.

CLI: `records.py list` · `records.py show <name>` · `records.py validate` · `records.py marker`.
Advisory-tier plumbing: never wired into check_cmd, CI, or the manifest.
"""

from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

REGISTRY_PATH = Path(__file__).resolve().parent.parent / "records.toml"

# The closed mode vocabulary. The two shared anchoring modes live in tools/textutil.py
# (MARKER_SENTINEL / MARKER_PREFIX); the other four name reader disciplines the registry documents.
MODES = ("prefix", "sentinel", "strict-line", "verdict-line", "stage-escape", "json-schema")

# The closed surface set. `vault-doc` joins with the design-side records (it-30 slice 3, per the
# crossing ruling of 2026-08-07) — present in the vocabulary so the canon slice adds rows, not code.
# `release` joins with the release lane (it-31 slice 7, ruling 6): the GitHub Release object whose
# body carries the YR-RELEASE record, fetched via tools/sources.py:releases.
SURFACES = ("issue-trail", "issue-body", "pr-trail", "run-dir", "stage-log", "ledger", "bench",
            "vault-doc", "release")

# The closed actor-class vocabulary — ONE authority; tools/process.py imports it from here. Every
# record row carries a typed `emitted_by` list (the process model's rule S column) beside the prose
# `emitter`.
ACTORS = ("human", "attended-agent", "machinery", "external-service")


class RegistryError(ValueError):
    """A malformed registry is a loud failure, never a silent fallback."""


def load(path: Path | None = None) -> dict:
    """Parse and validate the registry; return the raw dict with defaults applied."""
    p = path or REGISTRY_PATH
    try:
        data = tomllib.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise RegistryError(f"registry not found: {p}")
    except tomllib.TOMLDecodeError as e:
        raise RegistryError(f"registry does not parse: {p}: {e}")
    _validate(data, p)
    return data


def _validate(data: dict, p: Path) -> None:
    marker = (data.get("marker") or {}).get("yr")
    if not marker or not isinstance(marker, str):
        raise RegistryError(f"{p}: [marker].yr missing or not a string")
    records = data.get("record")
    if not isinstance(records, list) or not records:
        raise RegistryError(f"{p}: no [[record]] rows")
    seen: set[str] = set()
    for i, r in enumerate(records):
        name = r.get("name")
        if not name or not isinstance(name, str):
            raise RegistryError(f"{p}: record[{i}] has no name")
        if name in seen:
            raise RegistryError(f"{p}: duplicate record name {name!r}")
        seen.add(name)
        if not r.get("marker") or not isinstance(r.get("marker"), str):
            raise RegistryError(f"{p}: {name}: marker missing or not a string")
        if not r.get("emitter") or not isinstance(r.get("emitter"), str):
            raise RegistryError(f"{p}: {name}: emitter missing")
        emitted_by = r.get("emitted_by")
        if not isinstance(emitted_by, list) or not emitted_by or any(
                cls not in ACTORS for cls in emitted_by):
            raise RegistryError(f"{p}: {name}: emitted_by must be a non-empty list drawn from "
                                f"{ACTORS} (the process model's rule S column)")
        readers = r.get("readers")
        if not isinstance(readers, list) or not readers or any(
                not isinstance(x, str) or not x for x in readers):
            raise RegistryError(f"{p}: {name}: readers must be a non-empty list of non-empty strings")
        if r.get("mode") not in MODES:
            raise RegistryError(f"{p}: {name}: mode {r.get('mode')!r} not in {MODES}")
        surfaces = r.get("surfaces")
        if not isinstance(surfaces, list) or not surfaces:
            raise RegistryError(f"{p}: {name}: surfaces missing")
        for s in surfaces:
            if s not in SURFACES:
                raise RegistryError(f"{p}: {name}: surface {s!r} not in {SURFACES}")
        if name.startswith(marker) and not r["marker"].startswith(marker):
            raise RegistryError(f"{p}: {name}: name is {marker}-family but marker {r['marker']!r} is not")
        fields = r.get("fields", [])
        if not isinstance(fields, list) or any(not isinstance(f, str) or not f for f in fields):
            raise RegistryError(f"{p}: {name}: fields must be a list of non-empty strings")
    if data.get("lanes") is not None:
        raise RegistryError(f"{p}: a [lanes] table no longer lives here — lane mandates compile "
                            f"from process.toml (one authority; the it-30 model migration)")


def marker_constant(data: dict) -> str:
    return data["marker"]["yr"]


def records(data: dict) -> list[dict]:
    return list(data["record"])


def get(data: dict, name: str) -> dict:
    for r in data["record"]:
        if r["name"] == name:
            return r
    raise RegistryError(f"unregistered record: {name!r} — a record absent from the registry is unsanctioned")


def lanes(data: dict) -> dict:
    """The lane → mandated-records mapping, DELEGATED to the process model (the migration's 'one
    authority' rule): mandates compile from process.toml's transitions, never from registry data.
    Loud on a non-loading model — a silently-empty mandate set would disable the detector unnoticed."""
    try:
        import process
        mandate, _forbid = process.lanes(process.load(registry=data))
        return mandate
    except Exception as e:  # noqa: BLE001 — surface the model failure as a registry failure, loud
        raise RegistryError(f"lane mandates unavailable — process.toml does not load: {e}")


def lane_forbids(data: dict) -> dict:
    """The lane → must-not-carry mapping (record_absent guards), same delegation."""
    try:
        import process
        _mandate, forbid = process.lanes(process.load(registry=data))
        return forbid
    except Exception as e:  # noqa: BLE001
        raise RegistryError(f"lane forbids unavailable — process.toml does not load: {e}")


def _cli(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="record registry loader (records.toml)")
    ap.add_argument("--registry", type=Path, default=None, help="registry path (default: repo records.toml)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="one line per record: name, mode, surfaces")
    p_show = sub.add_parser("show", help="one record, every field")
    p_show.add_argument("name")
    sub.add_parser("validate", help="parse + shape-check; exit 0 clean, 1 malformed")
    sub.add_parser("marker", help="print the marker constant")
    args = ap.parse_args(argv)
    try:
        data = load(args.registry)
    except RegistryError as e:
        print(f"records: ERROR: {e}", file=sys.stderr)
        return 1
    if args.cmd == "validate":
        print(f"records: ok — {len(records(data))} records, marker {marker_constant(data)!r}, "
              f"{len(lanes(data))} lane(s)")
        return 0
    if args.cmd == "marker":
        print(marker_constant(data))
        return 0
    if args.cmd == "list":
        for r in records(data):
            print(f"{r['name']}\t{r['mode']}\t{','.join(r['surfaces'])}")
        return 0
    if args.cmd == "show":
        try:
            r = get(data, args.name)
        except RegistryError as e:
            print(f"records: ERROR: {e}", file=sys.stderr)
            return 1
        for k in ("name", "marker", "mode", "fields", "emitter", "readers", "surfaces", "notes"):
            if k in r:
                print(f"{k}: {r[k]}")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(_cli())
