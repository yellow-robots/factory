#!/usr/bin/env python3
"""process.py — loader, validator, compilers, and decision engine for the factory's process model
(`process.toml`; it-30, the enforcement layer; design: architecture/state-machine/model-design in
the vault, built under the rulings of 2026-08-08).

Sibling of `records.py`: the registry holds record GRAMMARS; this model holds the machines,
transitions, guards, stores, and vendor bindings the walls compile from. `stance` and
`enforcement` are DERIVED — no field exists to author either.

Tier contract (ruling 1, split tier): the LOAD-TIME rules gate — `load()` raising means the walls
are structurally off, and a pytest test asserts the shipped model loads, which puts the gate inside
`check_cmd` and CI without a new wiring point. The drift check (`check --drift`) is ADVISORY, loud:
its consumers are the sweep, the delivery banner, and the close report — never a merge gate.

CLI: validate · compile {acts,lanes,slice,conformance,all} · check --drift · lanes ·
     transition-check <id> · decide · close-report · decay.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import acts as acts_mod  # noqa: E402
import predicates  # noqa: E402
import records  # noqa: E402
import sources  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
MODEL_PATH = REPO_ROOT / "process.toml"
BUILD_DIR = REPO_ROOT / "build"

CONTRACT = "yr-process/1"
PORT = "port."

ACTORS = records.ACTORS                  # one authority (records.py); never restated
AGENT_MAY = ("execute", "propose")
DOOR = ("one-way", "reversible")
STANCES = ("refuse", "escalate", "advise", "observe")
ENFORCE = ("prevented", "detected", "partial", "unenforced")
PREDICATES = ("facet_is", "store_is", "record_present", "record_absent",
              "evaluator_pass", "act_field_contains")
STORE_KIND = ("board-single-select", "frontmatter-key", "pr-attribute", "git-ref",
              "host-file", "manifest-key", "issue-field")
MATCH_KIND = ("argv", "graphql-mutation", "path-write", "shell-redirect",
              "mcp-tool", "git-refspec")
VALUE_KIND = ("option-id", "literal", "frontmatter-value", "graphql-variable",
              "toml-key", "refspec-target", "flag-literal")
PRECISION = ("exact", "over-matching")
DECAY_STATES = ("fresh", "stale", "drifted", "broken")
AMEND_KIND = ("widen", "narrow", "port", "decay-repair", "editorial")
VENDORS = ("neutral", "github", "anthropic-claude-code", "obsidian", "git", "host")
SURFACES = records.SURFACES  # imported, never restated

_STRICT = {"refuse": 3, "escalate": 2, "advise": 1, "observe": 0}

_ALLOWED = {
    "model": {"contract", "version", "records_registry", "change_duty", "slice_max_bytes", "compiled"},
    "amendment": {"version", "date", "kind", "touches", "reason", "review", "who"},
    "boundary": {"marker_files", "roots", "outside_scope", "caller_env", "caller_default", "caller_trust"},
    "observability": {"journal", "written", "may_influence_decisions", "best_effort"},
    "source": {"id", "fetches", "impl", "vendor", "timeout_s", "cache"},
    "store": {"id", "kind", "vendor", "location", "identifiers", "values", "read", "writable_by",
              "guarded", "change_clock", "unknown_value_policy", "write_path", "server_chokepoint"},
    "write_path": {"id", "how", "observable", "detected_by", "undetectable", "reason"},
    "machine": {"id", "subject", "scope", "facets", "note"},
    "state": {"machine", "facet", "id", "store", "value", "initial", "terminal"},
    "lane": {"id", "subject", "scope"},
    "evaluator": {"id", "argv", "conditions_display", "timeout_s", "contract", "note"},
    "transition": {"id", "machine", "from", "to", "lane", "actor", "agent_may", "door",
                   "writes_unguarded_facets", "unguarded_why", "because", "guard", "post"},
    "guard": {"predicate", "args", "why", "window"},
    "post": {"predicate", "args"},
    "invariant": {"id", "title", "tool", "actor", "door", "authority", "does_not_cover",
                  "match", "guard"},
    "probe": {"id", "vendor", "subject", "fingerprint_cmd", "fingerprint", "verified_on",
              "recheck_days", "on_drift"},
    "binding": {"id", "vendor", "observed_via", "tool", "precision", "over_matches",
                "does_not_cover", "probe", "verified_on", "recheck_days", "verify",
                "match", "writes"},
    "writes": {"store", "write_path", "selects_when", "value"},
}


class ModelError(ValueError):
    """A model that does not load means the walls are OFF — the loud, gating failure class."""


def _keys(table: dict, kind: str, where: str) -> None:
    extra = set(table) - _ALLOWED[kind]
    if extra:
        raise ModelError(f"{where}: unknown key(s) {sorted(extra)} — a field cannot be smuggled "
                         f"where it does not belong")


# ── load + validate ──────────────────────────────────────────────────────────────────────────────

def load(path: Path | None = None, registry: dict | None = None) -> dict:
    import tomllib
    p = path or MODEL_PATH
    try:
        model = tomllib.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ModelError(f"model not found: {p}")
    except tomllib.TOMLDecodeError as e:
        raise ModelError(f"model does not parse: {p}: {e}")
    if registry is None:
        rr = (model.get("model") or {}).get("records_registry") or "records.toml"
        registry = records.load(Path(rr) if Path(rr).is_absolute() else REPO_ROOT / rr)
    reg = registry
    _validate(model, reg, p)
    _index(model)
    model["_registry"] = reg
    return model


def _validate(model: dict, reg: dict, p: str | Path) -> None:  # noqa: C901 — the rule list IS the function
    m = model.get("model") or {}
    _keys(m, "model", "[model]")
    if m.get("contract") != CONTRACT:
        raise ModelError(f"[model].contract must be {CONTRACT!r}")
    if m.get("change_duty") != "gate-touching":
        raise ModelError("[model].change_duty: 'gate-touching' is the only legal value")
    if not isinstance(m.get("slice_max_bytes"), int) or m["slice_max_bytes"] <= 0:
        raise ModelError("[model].slice_max_bytes must be a positive integer")
    amendments = model.get("amendment") or []
    for a in amendments:
        _keys(a, "amendment", f"amendment {a.get('version')}")
        if a.get("kind") not in AMEND_KIND:
            raise ModelError(f"amendment {a.get('version')}: kind {a.get('kind')!r} not in {AMEND_KIND}")
        for k in ("version", "date", "reason", "review", "who"):
            if not a.get(k):
                raise ModelError(f"amendment: {k} missing")
    if m.get("version") not in {a["version"] for a in amendments}:
        raise ModelError(f"[model].version {m.get('version')!r} has no [[amendment]] row")

    b = model.get("boundary") or {}
    _keys(b, "boundary", "[boundary]")
    if b.get("caller_default") not in ACTORS:
        raise ModelError(f"[boundary].caller_default {b.get('caller_default')!r} not in {ACTORS}")
    if b.get("caller_trust") != "declared":
        raise ModelError("[boundary].caller_trust: 'declared' is the only honest value we can claim")
    if b.get("outside_scope") != "observe":
        raise ModelError("[boundary].outside_scope: 'observe' — the lane never refuses outside its world")

    o = model.get("observability") or {}
    _keys(o, "observability", "[observability]")
    if o.get("written") != "after-decision":
        raise ModelError("[observability].written: 'after-decision' is a constant")
    if o.get("may_influence_decisions") is not False:
        raise ModelError("[observability].may_influence_decisions: false is a constant")
    if o.get("best_effort") is not True:
        raise ModelError("[observability].best_effort: true is a constant")

    stores = {s["id"]: s for s in model.get("store") or []}
    for s in (model.get("store") or []):
        _keys(s, "store", f"store {s.get('id')}")
        if s.get("kind") not in STORE_KIND:
            raise ModelError(f"store {s['id']}: kind {s.get('kind')!r} not in {STORE_KIND}")
        for cls in s.get("writable_by") or []:
            if cls not in ACTORS:
                raise ModelError(f"store {s['id']}: writable_by {cls!r} not in {ACTORS}")
        for wp in s.get("write_path") or []:
            _keys(wp, "write_path", f"store {s['id']} path {wp.get('id')}")
            if wp.get("observable") is False:
                # rule C2: named holes
                if not wp.get("detected_by") and not wp.get("undetectable"):
                    raise ModelError(f"store {s['id']} path {wp['id']}: observable=false needs "
                                     f"detected_by (a registered record) or undetectable=true with a reason")
                if wp.get("detected_by"):
                    records.get(reg, wp["detected_by"])  # raises if unregistered
                if wp.get("undetectable") and not wp.get("reason"):
                    raise ModelError(f"store {s['id']} path {wp['id']}: undetectable=true needs a reason")

    machines = {mm["id"]: mm for mm in model.get("machine") or []}
    for mm in machines.values():
        _keys(mm, "machine", f"machine {mm['id']}")
        if not mm.get("facets"):
            raise ModelError(f"machine {mm['id']}: facets missing")

    # rule P: per facet, states' values are a permutation of the store's values
    states = model.get("state") or []
    for st in states:
        _keys(st, "state", f"state {st.get('machine')}.{st.get('id')}")
        if st["machine"] not in machines:
            raise ModelError(f"state {st['id']}: unknown machine {st['machine']!r}")
        if st["facet"] not in machines[st["machine"]]["facets"]:
            raise ModelError(f"state {st['id']}: facet {st['facet']!r} not on machine {st['machine']!r}")
        if st["store"] not in stores:
            raise ModelError(f"state {st['id']}: unknown store {st['store']!r}")
    for mm in machines.values():
        for facet in mm["facets"]:
            rows = [st for st in states if st["machine"] == mm["id"] and st["facet"] == facet]
            if not rows:
                raise ModelError(f"machine {mm['id']}: facet {facet!r} has no states")
            facet_stores = {st["store"] for st in rows}
            if len(facet_stores) != 1:
                raise ModelError(f"machine {mm['id']}.{facet}: states span stores {sorted(facet_stores)}")
            store = stores[rows[0]["store"]]
            values = [st["value"] for st in rows]
            if sorted(values) != sorted(store.get("values") or []):
                raise ModelError(f"machine {mm['id']}.{facet}: states' values {sorted(values)} are not a "
                                 f"permutation of store {store['id']}'s {sorted(store.get('values') or [])} "
                                 f"(rule P)")

    lanes_declared = {ln["id"] for ln in model.get("lane") or []}
    evaluators = {e["id"]: e for e in model.get("evaluator") or []}
    for e in evaluators.values():
        _keys(e, "evaluator", f"evaluator {e['id']}")

    transitions = model.get("transition") or []
    seen_t = set()
    for t in transitions:
        tid = t.get("id") or "<unnamed>"
        _keys(t, "transition", f"transition {tid}")
        if tid in seen_t:
            raise ModelError(f"transition {tid}: duplicate id")
        seen_t.add(tid)
        if t["machine"] not in machines:
            raise ModelError(f"transition {tid}: unknown machine {t['machine']!r}")
        mm = machines[t["machine"]]
        primary = mm["facets"][0]
        f_ids = {st["id"] for st in states if st["machine"] == t["machine"] and st["facet"] == primary}
        if t["from"] not in f_ids or t["to"] not in f_ids:
            raise ModelError(f"transition {tid}: from/to must be states of the primary facet {primary!r}")
        if t.get("lane") and t["lane"] not in lanes_declared:
            raise ModelError(f"transition {tid}: unknown lane {t['lane']!r}")
        for cls in t.get("actor") or []:
            if cls not in ACTORS:
                raise ModelError(f"transition {tid}: actor {cls!r} not in {ACTORS}")
        if not t.get("actor"):
            raise ModelError(f"transition {tid}: actor missing")
        # rule A
        if t.get("agent_may") is not None:
            if t["agent_may"] not in AGENT_MAY:
                raise ModelError(f"transition {tid}: agent_may {t['agent_may']!r} not in {AGENT_MAY}")
            if "attended-agent" not in t["actor"]:
                raise ModelError(f"transition {tid}: agent_may present but attended-agent not in actor (rule A)")
        if t.get("door") not in DOOR:
            raise ModelError(f"transition {tid}: door {t.get('door')!r} not in {DOOR}")
        # rule D
        if t["door"] == "one-way" and t.get("agent_may") == "execute":
            raise ModelError(f"transition {tid}: door=one-way forbids agent_may=execute (rule D) — "
                             f"an agent never walks through a one-way door silently")
        if not t.get("because"):
            raise ModelError(f"transition {tid}: because (the teaching sentence) missing")
        guarded_facets, posted_facets = set(), set()
        for g in t.get("guard") or []:
            _keys(g, "guard", f"transition {tid} guard")
            _check_predicate(g, tid, reg, stores, evaluators, machines, states, t, "guard")
            if g["predicate"] == "facet_is":
                guarded_facets.add(g["args"]["facet"])
            if g.get("window"):
                clocked = [st["store"] for st in states if st["machine"] == t["machine"]
                           and stores[st["store"]].get("change_clock")]
                if not clocked:
                    raise ModelError(f"transition {tid}: window on a machine with no change_clock store")
        if not t.get("post"):
            raise ModelError(f"transition {tid}: at least one post is required")
        for po in t.get("post") or []:
            _keys(po, "post", f"transition {tid} post")
            _check_predicate(po, tid, reg, stores, evaluators, machines, states, t, "post")
            if po["predicate"] == "facet_is":
                posted_facets.add(po["args"]["facet"])
        # rules F1/F2 over non-primary facets
        declared = set(t.get("writes_unguarded_facets") or [])
        for facet in guarded_facets:
            if facet != primary and facet not in posted_facets:
                raise ModelError(f"transition {tid}: guards non-primary facet {facet!r} but no post "
                                 f"disposes it (rule F1 — the Reason-clearing rule's home)")
        for facet in posted_facets:
            if facet != primary and facet not in guarded_facets and facet not in declared:
                raise ModelError(f"transition {tid}: posts unguarded non-primary facet {facet!r} without "
                                 f"declaring it in writes_unguarded_facets (rule F2)")
        for facet in declared:
            if not (t.get("unguarded_why") or {}).get(facet):
                raise ModelError(f"transition {tid}: writes_unguarded_facets entry {facet!r} needs an "
                                 f"unguarded_why sentence")
        # rule S (satisfiability, as ruled: reject a self-licensing guard, and a guard record
        # nobody declared can produce)
        own_posts = {po["args"].get("record") for po in t.get("post") or []
                     if po["predicate"] == "record_present"}
        for g in t.get("guard") or []:
            if g["predicate"] != "record_present":
                continue
            rec = g["args"]["record"]
            if rec in own_posts:
                raise ModelError(f"transition {tid}: guard record {rec!r} is a post of this same "
                                 f"transition — a self-licensing wall (rule S; the promote.sh half-write shape)")
            row = records.get(reg, rec)
            emitted_by = row.get("emitted_by") or []
            produced_elsewhere = any(
                rec in {po["args"].get("record") for po in (t2.get("post") or [])
                        if po["predicate"] == "record_present"}
                for t2 in transitions if t2 is not t)
            if not emitted_by and not produced_elsewhere:
                raise ModelError(f"transition {tid}: guard record {rec!r} has no emitted_by actor class "
                                 f"and is no other transition's post — unsatisfiable (rule S)")

    # rule C: coverage — a guarded store's observable write path must be covered by a binding
    bindings = (model.get("port") or {}).get("binding") or []
    covered = set()
    for bd in bindings:
        _keys(bd, "binding", f"binding {bd.get('id')}")
        if bd.get("precision") not in PRECISION:
            raise ModelError(f"binding {bd.get('id')}: precision {bd.get('precision')!r} not in {PRECISION}")
        if not bd.get("does_not_cover"):
            raise ModelError(f"binding {bd.get('id')}: does_not_cover is required non-empty — you must "
                             f"write down at least one way around your own wall")
        if bd.get("precision") == "over-matching" and not bd.get("over_matches"):
            raise ModelError(f"binding {bd.get('id')}: over-matching needs an over_matches sentence")
        mk = (bd.get("match") or {}).get("kind")
        if mk not in MATCH_KIND:
            raise ModelError(f"binding {bd.get('id')}: match.kind {mk!r} not in {MATCH_KIND} — "
                             f"there is no substring and no regex member")
        probes = {pr["id"] for pr in (model.get("port") or {}).get("probe") or []}
        if bd.get("probe") not in probes | {"none", None}:
            raise ModelError(f"binding {bd.get('id')}: unknown probe {bd.get('probe')!r}")
        for w in bd.get("writes") or []:
            _keys(w, "writes", f"binding {bd['id']} writes")
            if w["store"] not in stores:
                raise ModelError(f"binding {bd['id']}: unknown store {w['store']!r}")
            paths = {wp["id"] for wp in stores[w["store"]].get("write_path") or []}
            if w["write_path"] not in paths:
                raise ModelError(f"binding {bd['id']}: store {w['store']} has no write path "
                                 f"{w['write_path']!r}")
            if (w.get("value") or {}).get("kind") not in VALUE_KIND:
                raise ModelError(f"binding {bd['id']}: value.kind not in {VALUE_KIND}")
            covered.add((w["store"], w["write_path"]))
    for s in stores.values():
        if not s.get("guarded"):
            continue
        for wp in s.get("write_path") or []:
            if wp.get("observable") and (s["id"], wp["id"]) not in covered:
                raise ModelError(f"store {s['id']}: observable write path {wp['id']!r} is covered by no "
                                 f"binding (rule C — prevention-by-omission is a load error)")

    for inv in model.get("invariant") or []:
        _keys(inv, "invariant", f"invariant {inv.get('id')}")
        for g in inv.get("guard") or []:
            _keys(g, "guard", f"invariant {inv['id']} guard")
            if g["predicate"] in ("facet_is", "store_is"):
                raise ModelError(f"invariant {inv['id']}: a state predicate on an invariant is a load "
                                 f"error — if it depends on state it is a transition guard")
            if g["predicate"] not in PREDICATES:
                raise ModelError(f"invariant {inv['id']}: predicate {g['predicate']!r} not in {PREDICATES}")
        if not inv.get("does_not_cover"):
            raise ModelError(f"invariant {inv.get('id')}: does_not_cover is required non-empty")

    # the seam: a neutral row may never cite a port.* id
    for kind in ("source", "store", "machine", "state", "lane", "evaluator", "transition", "invariant"):
        for row in model.get(kind) or []:
            for v in _strings(row):
                if v.startswith(PORT):
                    raise ModelError(f"{kind} {row.get('id', '?')}: cites {v!r} — a neutral row may "
                                     f"never reference the port half (the seam is one-way)")

    # determinism: two transitions surviving selection for one (machine, from, to-value, caller)
    for i, t1 in enumerate(transitions):
        for t2 in transitions[i + 1:]:
            if t1["machine"] != t2["machine"] or t1["from"] != t2["from"] or t1["to"] != t2["to"]:
                continue
            if set(t1["actor"]) & set(t2["actor"]):
                raise ModelError(f"transitions {t1['id']} / {t2['id']}: same machine, from, to and an "
                                 f"overlapping caller class — runtime never picks between rules "
                                 f"(determinism)")


def _check_predicate(g: dict, tid: str, reg: dict, stores: dict, evaluators: dict,
                     machines: dict, states: list, t: dict, tier: str) -> None:
    pred = g.get("predicate")
    if pred not in PREDICATES:
        raise ModelError(f"transition {tid}: predicate {pred!r} not in {PREDICATES} — prose "
                         f"conditions are unwritable (rule V)")
    args = g.get("args") or {}
    if pred in ("record_present", "record_absent"):
        try:
            records.get(reg, args.get("record", ""))  # rule R: resolves or the model does not load
        except records.RegistryError as e:
            raise ModelError(f"transition {tid}: {e} (rule R)")
    elif pred == "facet_is":
        mm = machines[t["machine"]]
        if args.get("facet") not in mm["facets"]:
            raise ModelError(f"transition {tid}: facet_is names unknown facet {args.get('facet')!r}")
        ids = {st["id"] for st in states
               if st["machine"] == t["machine"] and st["facet"] == args["facet"]}
        if args.get("state") not in ids:
            raise ModelError(f"transition {tid}: facet_is names unknown state {args.get('state')!r}")
    elif pred == "store_is":
        if args.get("store") not in stores:
            raise ModelError(f"transition {tid}: store_is names unknown store {args.get('store')!r}")
        vals = stores[args["store"]].get("values") or []
        if vals and args.get("value") not in vals:
            raise ModelError(f"transition {tid}: store_is value {args.get('value')!r} outside "
                             f"{args['store']}'s values")
    elif pred == "evaluator_pass":
        if args.get("evaluator") not in evaluators:
            raise ModelError(f"transition {tid}: unknown evaluator {args.get('evaluator')!r}")
    elif pred == "act_field_contains" and tier != "guard":
        raise ModelError(f"transition {tid}: act_field_contains is invariant-tier only")


def _strings(obj) -> list[str]:
    out = []
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            out += _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            out += _strings(v)
    return out


def _index(model: dict) -> None:
    model["_stores"] = {s["id"]: s for s in model.get("store") or []}
    model["_machines"] = {m["id"]: m for m in model.get("machine") or []}
    model["_evaluators"] = {e["id"]: e for e in model.get("evaluator") or []}
    model["_state_rows"] = model.get("state") or []
    model["_facet_store"] = {}
    model["_value_state"] = {}
    for st in model["_state_rows"]:
        model["_facet_store"][(st["machine"], st["facet"])] = st["store"]
        model["_value_state"][(st["machine"], st["facet"], st["value"])] = st["id"]


# ── derivations (code, not data) ─────────────────────────────────────────────────────────────────

def stance(caller: str, t: dict, guards_ok: bool | None, binding: dict | None,
           headless: bool = False) -> str:
    if caller not in t["actor"]:
        s = "refuse"                       # categorical for this class; guards unread
    elif guards_ok is False:
        s = "refuse"                       # FALSE and UNKNOWN are the same answer
    elif caller == "attended-agent" and t.get("agent_may") == "propose":
        s = "escalate"
        if headless:
            s = "refuse"                   # propose has no one to propose to: ask fails open
                                           # unattended (harness-contract §3b) — a fail-closed
                                           # one-way door refuses instead (it-31 slice 2)
    else:
        s = "observe"
    if binding and binding.get("precision") == "over-matching" and s in ("refuse", "escalate"):
        s = "advise"                       # a binding that cannot confirm the effect may never deny
    return s


def is_headless(model: dict, hook: dict) -> bool:
    """The transport's declared no-human signal, read from the hook payload — never inferred
    inside the engine (the one-way port rule: the vendor block declares, the neutral derivation
    consumes a boolean). Field absent = interactive, today's behavior."""
    decl = ((model.get("port") or {}).get("transport") or {}) \
        .get("anthropic-claude-code", {}).get("headless") or {}
    field = decl.get("field")
    if not field:
        return False
    return hook.get(field) in (decl.get("values") or [])


def decay(binding: dict, today: _dt.date | None = None) -> str:
    today = today or _dt.date.today()
    try:
        seen = _dt.date.fromisoformat(str(binding.get("verified_on")))
    except (TypeError, ValueError):
        return "broken"
    if (today - seen).days > int(binding.get("recheck_days") or 30):
        return "stale"
    return "fresh"


def _stores_written(t: dict, model: dict) -> set[str]:
    out = set()
    for po in t.get("post") or []:
        if po["predicate"] == "facet_is":
            out.add(model["_facet_store"][(t["machine"], po["args"]["facet"])])
        elif po["predicate"] == "store_is":
            out.add(po["args"]["store"])
    return out


def chokepoint(t: dict, model: dict) -> str:
    """Ruling 2's SECOND derived column: does a server enforce this transition, independent of any
    client-side hook? Derived from the written stores' declared `server_chokepoint`; v1 declares
    none anywhere, so every row honestly reads the client-side-only sentence — the two claims never
    collapse into one word."""
    points = sorted({model["_stores"][sid].get("server_chokepoint")
                     for sid in _stores_written(t, model)
                     if model["_stores"][sid].get("server_chokepoint")})
    return " + ".join(points) if points else "none — client-side hook coverage only"


def enforcement(t: dict, model: dict, today: _dt.date | None = None) -> tuple[str, list[str]]:
    """Derived, never authored. Returns (value, open_paths_rendered). Iteration is SORTED so the
    compiled surfaces are byte-stable across processes (hash-seed independence)."""
    bindings = (model.get("port") or {}).get("binding") or []
    paths, live, open_paths = [], [], []
    for sid in sorted(_stores_written(t, model)):
        store = model["_stores"][sid]
        for wp in store.get("write_path") or []:
            paths.append((store, wp))
            is_live = wp.get("observable") and any(
                w["store"] == sid and w["write_path"] == wp["id"] and decay(bd, today) == "fresh"
                for bd in bindings for w in bd.get("writes") or [])
            if is_live:
                live.append((store, wp))
            else:
                det = f" (detected by {wp['detected_by']})" if wp.get("detected_by") else ""
                open_paths.append(f"{sid}.{wp['id']}: {wp['how']}{det}")
    has_record_post = any(po["predicate"] == "record_present" for po in t.get("post") or [])
    all_open_detected = all(wp.get("detected_by") for _, wp in paths
                            if (_, wp) not in live) if paths else False
    detected = has_record_post or (bool(open_paths) and all_open_detected)
    if paths and not open_paths:
        return "prevented", []
    if live and (open_paths or detected):
        return "partial", open_paths
    if not live and detected:
        return "detected", open_paths
    return "unenforced", open_paths


# ── lane mandates (surface 2) — traced against the shipped registry in the design ───────────────

def _primary_facet(model: dict, machine: str) -> str:
    return model["_machines"][machine]["facets"][0]


def _on_course(model: dict, t: dict) -> bool:
    p = _primary_facet(model, t["machine"])
    return not any(g["predicate"] == "facet_is" and g["args"]["facet"] != p
                   for g in t.get("guard") or [])


def lanes(model: dict) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    mandate: dict[str, set] = {}
    forbid: dict[str, set] = {}
    for t in model.get("transition") or []:
        if not t.get("lane") or not _on_course(model, t):
            continue
        for pr in (t.get("guard") or []) + (t.get("post") or []):
            if pr["predicate"] == "record_present":
                mandate.setdefault(t["lane"], set()).add(pr["args"]["record"])
            elif pr["predicate"] == "record_absent":
                forbid.setdefault(t["lane"], set()).add(pr["args"]["record"])
    return ({k: sorted(v) for k, v in mandate.items()},
            {k: sorted(v) for k, v in forbid.items()})


# ── render: the ONLY place a predicate becomes prose ─────────────────────────────────────────────

def render(g: dict, model: dict) -> str:
    reg = model["_registry"]
    pred, args, why = g["predicate"], g.get("args") or {}, g.get("why", "")
    if pred == "record_present":
        row = records.get(reg, args["record"])
        fields = f", fields {row['fields']}" if row.get("fields") else ""
        return (f"{why} — the `{args['record']}` record (records.toml: marker `{row['marker']}`, "
                f"mode `{row['mode']}`{fields}, on {', '.join(row['surfaces'])})")
    if pred == "record_absent":
        row = records.get(reg, args["record"])
        return f"{why} — no `{args['record']}` line on {', '.join(row['surfaces'])}"
    if pred == "facet_is":
        return f"{why} — the `{args['facet']}` facet reads `{args['state']}`"
    if pred == "store_is":
        st = model["_stores"][args["store"]]
        return f"{why} — `{args['store']}` reads `{args['value']}` ({st['kind']}: {st['location']})"
    if pred == "evaluator_pass":
        ev = model["_evaluators"][args["evaluator"]]
        return f"{why} — the `{args['evaluator']}` evaluator passes ({' '.join(ev['argv'])})"
    if pred == "act_field_contains":
        return f"{why} — the act's `{args['field']}` carries `{args['literal']}`"
    return why


def _headless_line(model: dict) -> str:
    """The headless rule + the blind-write residual, printed wherever the map could otherwise
    overclaim (it-31 slice 2). Empty when the transport declares no signal."""
    decl = ((model.get("port") or {}).get("transport") or {}) \
        .get("anthropic-claude-code", {}).get("headless") or {}
    if not decl.get("field"):
        return ""
    vals = "/".join(decl.get("values") or [])
    return (f"headless: where the hook payload's `{decl['field']}` is {vals}, a propose-gated "
            f"one-way transition REFUSES instead of asking — ask fails open unattended (verified, "
            f"harness-contract); other unattended contexts are unclaimed by the contract and keep "
            f"today's ask; the blind-write residual stands — an over-matching binding advises, "
            f"never denies, detection-tier.")


def _gen_header(model: dict, model_path: Path | None = None) -> str:
    raw = (model_path or MODEL_PATH).read_bytes()
    sha = hashlib.sha256(raw).hexdigest()[:16]
    v = model["model"]["version"]
    return f"GENERATED from process.toml v{v} sha256:{sha} — never hand-edit"


# ── compilers ────────────────────────────────────────────────────────────────────────────────────

def compile_lanes(model: dict) -> str:
    mandate, forbid = lanes(model)
    amendment = next(a for a in model["amendment"] if a["version"] == model["model"]["version"])
    out = [f"# {_gen_header(model)}",
           "# The detector's lane mandates, compiled from the transitions (surface 2).",
           "", "[meta]",
           f'model_version = "{model["model"]["version"]}"',
           f'effective = "{amendment["date"]}"', "", "[mandate]"]
    for lane in sorted(mandate):
        out.append(f"{lane} = {json.dumps(mandate[lane])}")
    out += ["", "[must-not-carry]"]
    for lane in sorted(forbid):
        out.append(f"{lane} = {json.dumps(forbid[lane])}")
    return "\n".join(out) + "\n"


def compile_acts(model: dict) -> str:
    rows = []
    bindings = (model.get("port") or {}).get("binding") or []
    for bd in bindings:
        for w in bd.get("writes") or []:
            store = model["_stores"][w["store"]]
            for cls in [c for c in ACTORS if c not in (store.get("writable_by") or [])]:
                rows.append({"tier": "store-permission", "act": bd["id"], "caller": cls,
                             "effect": f"{store['id']} <- (any)",
                             "condition": f"writable_by = {store.get('writable_by')}",
                             "stance": "refuse" if bd.get("precision") == "exact" else "advise",
                             "stance_on_fail": "—", "door": "—",
                             "because": f"the {store['id']} store's permission tier"})
            for t in model.get("transition") or []:
                if w["store"] not in _stores_written(t, model):
                    continue
                enf, open_paths = enforcement(t, model)
                tv = _target_value(model, t, w["store"])
                for caller in ACTORS:
                    rows.append({
                        "tier": "transition", "act": bd["id"], "caller": caller,
                        "effect": f"{w['store']} <- {'(cleared)' if tv == '' else tv}",
                        "transition": f"{t['machine']}: {t['from']} -> {t['to']} ({t['id']})",
                        "condition": " AND ".join(render(g, model) for g in t.get("guard") or []) or "—",
                        "stance": stance(caller, t, True, bd),
                        "stance_on_fail": stance(caller, t, False, bd),
                        "door": t["door"], "enforcement": enf,
                        "chokepoint": chokepoint(t, model),
                        "open": "; ".join(open_paths) or "—",
                        "because": t["because"]})
    for inv in model.get("invariant") or []:
        rows.append({"tier": "conduct", "act": inv["id"], "caller": ",".join(inv["actor"]),
                     "effect": inv["title"],
                     "condition": " AND ".join(render(g, model) for g in inv.get("guard") or []),
                     "stance": "refuse", "stance_on_fail": "refuse", "door": inv["door"],
                     "enforcement": "detected",  # an invariant can never reach prevented
                     "because": inv.get("authority", "")})
    lines = [f"<!-- {_gen_header(model)} -->", "", "# The walled-act map — compiled",
             "",
             f"caller_trust = `{model['boundary']['caller_trust']}` — this boundary is declared, "
             f"not proven.",
             _headless_line(model), ""]
    lines.append("| tier | act (binding) | caller | effect | condition | stance | on-fail | door | enforcement | chokepoint | open paths | because |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        lines.append("| " + " | ".join(str(r.get(k, "—")).replace("|", "\\|").replace("\n", " ")
                                       for k in ("tier", "act", "caller", "effect", "condition",
                                                 "stance", "stance_on_fail", "door", "enforcement",
                                                 "chokepoint", "open", "because")) + " |")
    return "\n".join(lines) + "\n"


def compile_slice(model: dict) -> str:
    parts = [f"<!-- {_gen_header(model)} -->", "",
             "# The attended lane — the delivered slice (static half)", ""]
    # Part 1 — the machines: the belief-killer, rendered
    parts.append("## The machines — where each state physically lives")
    for mm in model.get("machine") or []:
        parts.append(f"\n**{mm['id']}** — {mm['subject']}")
        for facet in mm["facets"]:
            rows = [st for st in model["_state_rows"]
                    if st["machine"] == mm["id"] and st["facet"] == facet]
            store = model["_stores"][rows[0]["store"]]
            vals = " · ".join(f"`{st['id']}`={st['value']!r}" for st in rows)
            parts.append(f"- {facet} (store `{store['id']}`, {store['kind']}): {vals}")
    # Part 2 — the transitions with both stance columns (compact form of surface 1)
    parts.append("\n## The transitions — who may move what, under which conditions")
    for t in model.get("transition") or []:
        enf, open_paths = enforcement(t, model)
        conds = "; ".join(g.get("why", "") for g in t.get("guard") or []) or "no guards"
        parts.append(f"- **{t['id']}** [{'/'.join(t['actor'])}; door {t['door']}; {enf}; "
                     f"chokepoint: {chokepoint(t, model)}] — {conds}. {t['because']}")
        if open_paths:
            parts.append(f"  - open: {'; '.join(open_paths)}")
    # Part 3 — the honesty block
    parts.append("\n## Honesty block")
    parts.append(f"- caller_trust = `{model['boundary']['caller_trust']}` — the caller class is "
                 f"declared, not proven; the journal and the detector find the shape afterwards.")
    parts.append("- guards check existence and grammar only — genuineness stays with independent "
                 "review and the bench.")
    parts.append("- an act matching no binding is OBSERVED, never silently permitted as lawful — "
                 "silence is absence of coverage, not permission.")
    parts.append("- " + _headless_line(model))
    for inv in model.get("invariant") or []:
        parts.append(f"- conduct: {inv['title']} ({', '.join(inv.get('does_not_cover') or [])} "
                     f"are not covered).")
    out = "\n".join(parts) + "\n"
    limit = model["model"]["slice_max_bytes"]
    if len(out.encode()) > limit:
        raise ModelError(f"compiled slice is {len(out.encode())} bytes, over the "
                         f"slice_max_bytes bound {limit} — fail loud, never truncate")
    return out


def compile_conformance(model: dict) -> str:
    vectors = []
    for bd in (model.get("port") or {}).get("binding") or []:
        act = _example_act(bd)
        if act:
            vectors.append({"kind": "journal-independence", "binding": bd["id"], "act": act})
    for t in model.get("transition") or []:
        for i, g in enumerate(t.get("guard") or []):
            vectors.append({"kind": "unknown-refuses", "transition": t["id"], "guard": i,
                            "predicate": g["predicate"]})
    vectors.append({"kind": "same-transition",
                    "acts": [
                        {"tool_name": "Bash", "tool_input": {"command": _board_cmd()}},
                        {"tool_name": "Bash", "tool_input": {"command":
                         "python3 tools/board_plumbing.py set-field --id ITEM --status Ready"}}],
                    "note": "the funnel spelling and the raw spelling write the same store the same "
                            "value, so they resolve the SAME transition and the SAME guards — the "
                            "funnel is covered, never special-cased"})
    return json.dumps({"header": _gen_header(model), "vectors": vectors}, indent=1) + "\n"


def _board_cmd() -> str:
    try:
        import board_plumbing as bp
        return (f"gh project item-edit --id ITEM --project-id {bp.PROJECT_ID} "
                f"--field-id {bp.STATUS_FIELD_ID} --single-select-option-id {bp.STATUS_OPT['Ready']}")
    except Exception:  # noqa: BLE001
        return "gh project item-edit --id ITEM --field-id F --single-select-option-id O"


def _example_act(bd: dict) -> dict | None:
    """One hook-shaped act per binding — the SAME keys PreToolUse delivers (`tool_name`,
    `tool_input`), so a vector can be fed to `decide()` verbatim."""
    mk = bd["match"]["kind"]
    if mk == "argv" and bd["match"].get("program") == "gh":
        sub = " ".join(bd["match"].get("subcommands") or [])
        tail = {"project item-edit": _board_cmd().removeprefix("gh "),
                "pr merge": "pr merge 1 --repo yellow-robots/factory --squash",
                "api": "api repos/yellow-robots/factory/pulls/1/merge -X PUT"}.get(sub)
        return {"tool_name": "Bash", "tool_input": {"command": f"gh {tail}"}} if tail else None
    if mk == "argv" and bd["match"].get("subcommand_contains"):
        return {"tool_name": "Bash", "tool_input": {
            "command": "python3 tools/board_plumbing.py set-field --id ITEM --status Ready"}}
    if mk == "graphql-mutation":
        m = (bd["match"].get("mutations") or ["m"])[0]
        return {"tool_name": "Bash", "tool_input": {
            "command": f'gh api graphql -f query="mutation {{ {m}(input: {{}}) }}"'}}
    if mk == "path-write":
        root = bd["match"].get("path_under", "")
        if "VAULT" in root:
            return {"tool_name": "Write", "tool_input": {
                "file_path": os.path.expandvars(root) + "/04 projects/x.md", "content": "---\nstatus: active\n---\n"}}
        return {"tool_name": "Edit", "tool_input": {
            "file_path": "/tmp/x/.yr/factory.toml", "old_string": "auto_merge = false",
            "new_string": "auto_merge = true"}}
    if mk == "git-refspec":
        return {"tool_name": "Bash", "tool_input": {"command": "git push origin HEAD:main"}}
    if mk == "mcp-tool":
        tools = bd["match"].get("tools") or [bd["match"].get("tool")]
        ti = dict(bd["match"].get("arg_equals") or {})
        ti.setdefault("path", "04 projects/x.md")
        ti.setdefault("content", "active")
        return {"tool_name": tools[0], "tool_input": ti}
    return None


# ── the decision path ────────────────────────────────────────────────────────────────────────────

def in_scope(model: dict, cwd: Path) -> bool:
    b = model["boundary"]
    here = cwd.resolve()
    roots = []
    for r in b.get("roots") or []:
        expanded = os.path.expandvars(r)
        if expanded and "$" not in expanded:
            roots.append(Path(expanded).resolve())
    if not any("YR_WORKSPACE" in r for r in b.get("roots") or []) or os.environ.get("YR_WORKSPACE"):
        pass
    roots.append(REPO_ROOT.parent.parent)  # the workspace the factory sits in, by construction
    for d in (here, *here.parents):
        for mf in b.get("marker_files") or []:
            if (d / mf).is_file():
                return True
        if (d / ".claude-plugin" / "plugin.json").is_file() and (d / "tools" / "dev-runner.sh").is_file():
            return True
        if d in roots:
            return True
    return False


def resolve_caller(model: dict, env: dict | None = None) -> str:
    env = os.environ if env is None else env
    b = model["boundary"]
    raw = env.get(b["caller_env"], "")
    if raw in ACTORS:
        return raw
    if env.get("YR_MACHINERY"):
        return "machinery"  # the transitional bridge: the runner's standing declaration, honored
    return b["caller_default"]


class _Ctx:
    """Per-decision fetch cache + payloads the pure predicates judge."""

    def __init__(self, model):
        self.model = model
        self.registry = model["_registry"]
        self.texts: dict[tuple, list[str] | None] = {}
        self.scope: dict[str, str] = {}
        self.current: dict[str, object] = {}
        self.reads: dict[str, object] = {}


def _fetch_surface_texts(ctx: _Ctx, row: dict, act: dict) -> list[str] | None:
    for surface in row["surfaces"]:
        key = (surface, ctx.scope.get("repo"), ctx.scope.get("issue"),
               ctx.scope.get("pr"), ctx.scope.get("path"))
        if key in ctx.texts:
            got = ctx.texts[key]
            if got is not None:
                return got
        got = None
        if surface in ("issue-trail", "issue-body") and ctx.scope.get("repo") and ctx.scope.get("issue"):
            ok, payload = sources.issue_trail(ctx.scope["repo"], ctx.scope["issue"])
            got = payload if ok else None
        elif surface == "pr-trail" and ctx.scope.get("repo") and ctx.scope.get("pr"):
            ok, payload = sources.pr_trail(ctx.scope["repo"], ctx.scope["pr"])
            got = payload if ok else None
        elif surface == "vault-doc" and ctx.scope.get("path"):
            ok, payload = sources.vault_doc(Path(ctx.scope["path"]))
            got = [payload] if ok else None
        ctx.texts[key] = got
        if got is not None:
            return got
    return None


def _fetch_windowed_texts(ctx: _Ctx, row: dict) -> list[str] | None:
    """The `since-store-change` window, enforced at decision time: only trail texts STAMPED AT OR
    AFTER the store's change clock count, so one old record cannot license every future transition
    (the design's worked example (b); the review reproduced the fail-open of skipping this). `None`
    — UNKNOWN, disposing fail-closed — when the clock or the timestamps cannot be read."""
    clock = ctx.scope.get("store_changed")
    if not clock or not (ctx.scope.get("repo") and ctx.scope.get("issue")):
        return None
    key = ("timed", ctx.scope["repo"], ctx.scope["issue"])
    if key not in ctx.texts:
        ok, payload = sources.issue_trail_timed(ctx.scope["repo"], ctx.scope["issue"])
        ctx.texts[key] = payload if ok else None
    timed = ctx.texts[key]
    if timed is None:
        return None
    fresh = [text for ts, text in timed if ts and ts >= clock]
    return fresh


def _eval_guard(ctx: _Ctx, t: dict, g: dict, act: dict) -> predicates.Result:
    pred, args = g["predicate"], g.get("args") or {}
    if pred == "facet_is":
        return predicates.facet_is(args["facet"], args["state"], current=ctx.current)
    if pred == "store_is":
        _read_store(ctx, args["store"])
        return predicates.store_is(args["store"], args["value"], reads=ctx.reads)
    if pred in ("record_present", "record_absent"):
        row = records.get(ctx.registry, args["record"])
        if g.get("window") == "since-store-change":
            texts = _fetch_windowed_texts(ctx, row)
        else:
            texts = _fetch_surface_texts(ctx, row, act)
        fn = predicates.record_present if pred == "record_present" else predicates.record_absent
        return fn(args["record"], registry=ctx.registry, texts=texts)
    if pred == "evaluator_pass":
        ev = ctx.model["_evaluators"][args["evaluator"]]
        argv = [a.replace("{scope.repo}", ctx.scope.get("repo", ""))
                 .replace("{scope.pr}", ctx.scope.get("pr", "")) for a in ev["argv"]]
        try:
            out = subprocess.run(argv, capture_output=True, text=True,
                                 timeout=int(ev.get("timeout_s") or 120))
            token = (out.stdout or "").splitlines()[0] if out.stdout else ""
            return predicates.evaluator_pass(args["evaluator"], outcome=(out.returncode, token))
        except (OSError, subprocess.TimeoutExpired) as e:
            return predicates.evaluator_pass(args["evaluator"], outcome=(None, str(e)))
    if pred == "act_field_contains":
        return predicates.act_field_contains(args["field"], args["literal"], act=act)
    return predicates.unknown(f"unknown predicate {pred!r}")


def _read_store(ctx: _Ctx, store_id: str) -> None:
    if store_id in ctx.reads:
        return
    store = ctx.model["_stores"][store_id]
    read = store.get("read") or ""
    if read == "source.manifest-at-base-tip":
        repo_dir = Path(ctx.scope.get("repo_dir") or Path.cwd())
        ok, text = sources.manifest_at_base_tip(repo_dir)
        if not ok:
            ctx.reads[store_id] = ("UNKNOWN", text)
            return
        try:
            import tomllib
            manifest = tomllib.loads(text)
            key = store_id.split(".", 1)[1]
            ctx.reads[store_id] = str(manifest.get(key, "false")).lower()
        except Exception as e:  # noqa: BLE001
            ctx.reads[store_id] = ("UNKNOWN", f"manifest unparseable: {e}")
    elif read == "source.host-file":
        sentinel = os.environ.get("YR_MERGE_SENTINEL",
                                  str(Path.home() / ".cache" / "dev-runner" / "merge-killswitch"))
        ok, exists = sources.host_file(Path(sentinel))
        ctx.reads[store_id] = ("thrown" if exists else "clear") if ok else ("UNKNOWN", str(exists))
    elif read == "source.pr-state":
        if ctx.scope.get("repo") and ctx.scope.get("pr"):
            ok, data = sources.pr_state(ctx.scope["repo"], ctx.scope["pr"])
            if ok:
                merged = bool(data.get("mergedAt")) or data.get("state") == "MERGED"
                ctx.reads["pr.merged"] = "true" if merged else "false"
                ctx.reads["pr.status"] = ("merged" if merged else
                                          "approved" if data.get("reviewDecision") == "APPROVED"
                                          else "open")
                return
            ctx.reads[store_id] = ("UNKNOWN", str(data))
        else:
            ctx.reads[store_id] = ("UNKNOWN", "no PR in scope")
    else:
        ctx.reads[store_id] = ("UNKNOWN", f"no reader for {read!r} in this context")


def _resolve_scope_and_state(ctx: _Ctx, store_id: str, act: dict, seg: dict) -> None:
    """Best-effort scope + current-state resolution for the store this hit writes."""
    if store_id.startswith("board."):
        item = (seg.get("flags") or {}).get("--id", "")
        if item:
            ok, data = sources.board_item(item)
            if ok:
                ctx.scope.update({"repo": data["repo"], "issue": data["issue"],
                                  "store_changed": data.get("updatedAt") or ""})
                for facet, key in (("status", "status"), ("reason", "reason")):
                    sid = ctx.model["_value_state"].get(("task", facet, data[key]))
                    ctx.current[facet] = sid if sid else ("UNKNOWN", f"board {facet} reads {data[key]!r}")
                return
            ctx.current["status"] = ("UNKNOWN", str(data))
            ctx.current["reason"] = ("UNKNOWN", str(data))
        else:
            ctx.current["status"] = ("UNKNOWN", "no --id flag on the act")
            ctx.current["reason"] = ("UNKNOWN", "no --id flag on the act")
    elif store_id.startswith("pr."):
        flags = seg.get("flags") or {}
        repo = flags.get("--repo") or flags.get("-R") or ""
        # the PR number is a LEADING positional (`gh pr merge 1 ...`), so it lands in subcommands,
        # not operands — scan both (the review reproduced the scope loss)
        ops = [o for o in (seg.get("subcommands") or []) + (seg.get("operands") or [])
               if o.isdigit()]
        if repo:
            ctx.scope["repo"] = repo
        if ops:
            ctx.scope["pr"] = ops[0]
        _read_store(ctx, "pr.merged")
        got = ctx.reads.get("pr.status")
        if isinstance(got, str):
            sid = ctx.model["_value_state"].get(("pr", "state", got))
            ctx.current["state"] = sid or ("UNKNOWN", f"pr.status reads {got!r}")
        else:
            ctx.current["state"] = ("UNKNOWN", (got or ("UNKNOWN", "pr state unread"))[1])
    elif store_id == "doc.frontmatter.status":
        path = act.get("fields", {}).get("path") or act.get("path") or ""
        if path and not os.path.isabs(path):
            vault = os.environ.get("YR_VAULT_ROOT", "/srv/obsidian/vaults/obsidian")
            path = str(Path(vault) / path)
        if path:
            ctx.scope["path"] = path
            ok, text = sources.vault_doc(Path(path))
            if ok:
                m = re.search(r"^status:\s*(\S+)", text, flags=re.M)
                val = m.group(1) if m else ""
                sid = ctx.model["_value_state"].get(("design-doc", "status", val))
                ctx.current["status"] = sid or ("UNKNOWN", f"doc status reads {val!r}")
            else:
                ctx.current["status"] = ("UNKNOWN", text)
        else:
            ctx.current["status"] = ("UNKNOWN", "no path on the act")


def decide(model: dict, hook: dict, env: dict | None = None,
           cwd: Path | None = None) -> tuple[dict | None, list[dict]]:
    """The full decision path. Returns (hook output | None, journal rows). Never raises."""
    try:
        return _decide(model, hook, env, cwd)
    except Exception as e:  # noqa: BLE001 — a crashing hook fails OPEN and INVISIBLE (harness contract);
        # the one honest fallback is silence plus a journal row naming the crash.
        return None, [{"ts": int(time.time()), "transition_id": None, "binding_id": None,
                       "scope": {}, "stance": "error", "caller": "?", "detail": str(e)[:300]}]


def _decide(model: dict, hook: dict, env: dict | None, cwd: Path | None):  # noqa: C901
    env = os.environ if env is None else env
    here = cwd or Path(hook.get("cwd") or Path.cwd())
    act = acts_mod.normalize(hook.get("tool_name") or "", hook.get("tool_input") or {})
    # The boundary is judged by the session's cwd OR the act's TARGET — a session sitting outside
    # the workspace writing INTO the factory's world is factory-governed work (the review showed
    # cwd-only judgment silenced an arming edit made from /tmp).
    target = act.get("path") or str(act.get("fields", {}).get("file_path") or "")
    if not target and act["tool"].startswith("mcp__obsidian__"):
        target = os.path.join(os.environ.get("YR_VAULT_ROOT", "/srv/obsidian/vaults/obsidian"),
                              str(act.get("fields", {}).get("path") or ""))
    if not in_scope(model, Path(here)) and not (target and in_scope(model, Path(target).parent)):
        return None, []                    # out of scope: observe, silence, no I/O at all
    caller = resolve_caller(model, env)
    headless = is_headless(model, hook)
    maps = _value_maps()
    journal: list[dict] = []
    decisions: list[tuple[str, str, str]] = []   # (stance, reason, ref)

    bindings = (model.get("port") or {}).get("binding") or []
    for bd in bindings:
        tools = (bd.get("match", {}).get("tools")
                 or ([bd["match"]["tool"]] if bd.get("match", {}).get("tool") else None)
                 or bd.get("tool", "").split("|"))
        if act["tool"] not in tools:
            continue
        segs = acts_mod.match(bd["match"]["kind"], bd["match"], act)
        # An unparseable leftover matches only a binding that OPTS IN (`unparsed_matches = true`,
        # per the design); no shipped binding does, so unparsed commands are observed, journaled —
        # never blanket-refused as every guarded store at once.
        if not segs and act.get("unparsed") and (bd.get("match") or {}).get("unparsed_matches"):
            segs = [{"flags": {}, "operands": [], "fields": act["fields"], "unparsed": True}]
        for seg in segs:
            for w in bd.get("writes") or []:
                if not acts_mod.selects(w.get("selects_when"), {**seg, "fields": act["fields"]}, maps):
                    continue
                st, reason, ref, meta = _dispose_hit(model, bd, w, seg, act, caller,
                                                     headless=headless)
                decisions.append((st, reason, ref))
                journal.append(_jrow(ref, bd["id"], caller, st, meta))
    for inv in model.get("invariant") or []:
        if act["tool"] != inv.get("tool"):
            continue
        segs = acts_mod.match(inv["match"]["kind"], inv["match"], act)
        for seg in segs:
            st, reason = _dispose_invariant(model, inv, seg, act, caller)
            if st != "observe":
                decisions.append((st, reason, f"invariant:{inv['id']}"))
            journal.append(_jrow(f"invariant:{inv['id']}", None, caller, st, {}))

    if not decisions:
        return None, journal
    st, reason, _ = max(decisions, key=lambda d: _STRICT.get(d[0], 0))
    return _transport(model, st, reason), journal


def _value_maps() -> dict:
    try:
        import board_plumbing as bp
        return {"board_plumbing.status_opt": bp.status_opt(),
                "board_plumbing.reason_opt": bp.reason_opt(),
                "__ids__": {"board_plumbing.status_field_id": bp.status_field_id(),
                            "board_plumbing.reason_field_id": bp.reason_field_id()}}
    except Exception:  # noqa: BLE001
        return {"__ids__": {}}


def _jrow(ref: str, binding: str | None, caller: str, st: str, meta: dict | None) -> dict:
    row = {"ts": int(time.time()), "transition_id": ref, "binding_id": binding,
           "scope": (meta or {}).get("scope") or {}, "stance": st, "caller": caller}
    if (meta or {}).get("failed_record"):
        row["failed_record"] = meta["failed_record"]
    return row


def _dispose_hit(model: dict, bd: dict, w: dict, seg: dict, act: dict,
                 caller: str, headless: bool = False) -> tuple[str, str, str, dict]:
    store = model["_stores"][w["store"]]
    over = bd.get("precision") == "over-matching"
    meta: dict = {"scope": {}}

    # store-permission tier: no state read needed
    if caller not in (store.get("writable_by") or []):
        st = "advise" if over else "refuse"
        return st, (f"wall: {'NOTE' if over else 'REFUSED'} [{store['id']}] — this store is writable "
                    f"by {store.get('writable_by')} and the declared caller class is `{caller}` "
                    f"(caller_trust = declared). {store['location']}"), f"store:{store['id']}", meta

    value = acts_mod.extract_value(w.get("value") or {}, {**seg, "fields": act["fields"]},
                                   _value_maps())
    candidates = [t for t in model.get("transition") or []
                  if w["store"] in _stores_written(t, model)]
    if value is None:
        if over:
            # act-side evidence (it-31 slice 1): a write whose visible text provably cannot reach
            # the frontmatter key draws no advisory — noise trains people to ignore a detector
            if store.get("kind") == "frontmatter-key" \
                    and acts_mod.cannot_touch_key(act, store["id"].rsplit(".", 1)[-1]):
                return "observe", "", f"store:{w['store']}", meta
            return "advise", (f"wall: NOTE [{w['store']}] — this act looks like a `{w['store']}` "
                              f"write, and the wall cannot confirm the value from the act alone; "
                              f"the lawful transitions are: "
                              f"{', '.join(t['id'] for t in candidates)}"), f"store:{w['store']}", meta
        return "refuse", (f"wall: REFUSED [{w['store']}] — the written value could not be read from "
                          f"the act (an unreadable argument refuses; it never falls through). "
                          f"Lawful transitions: {', '.join(t['id'] for t in candidates)}"), \
               f"store:{w['store']}", meta

    ctx = _Ctx(model)
    _resolve_scope_and_state(ctx, w["store"], act, seg)
    meta["scope"] = {k: v for k, v in ctx.scope.items() if k in ("repo", "issue", "pr", "path")}

    # same-value (it-31 slice 1): an act that provably cannot change the store's value is not
    # judged as that store's transition — the no-op observes, it never refuses. Proven only for
    # a plain set: a mutating patch operation (append/prepend) changes the value even when its
    # content equals it (the review's finding on #433), so anything but replace falls through.
    if candidates and act["fields"].get("operation") in (None, "replace"):
        primary0 = _primary_facet(model, candidates[0]["machine"])
        cur0 = ctx.current.get(primary0)
        if isinstance(cur0, str):
            for strow in model["_state_rows"]:
                if strow["machine"] == candidates[0]["machine"] \
                        and strow["facet"] == primary0 and strow["id"] == cur0:
                    if strow["value"] == value:
                        return "observe", "", f"store:{w['store']}", meta
                    break

    # narrow to transitions whose target matches the resolved value
    targeted = []
    for t in candidates:
        tv = _target_value(model, t, w["store"])
        if tv == value:
            targeted.append(t)
    if not targeted:
        if caller in ("machinery", "external-service"):
            return "observe", "", f"store:{w['store']}", meta   # v1: unmodeled machinery acts observe
        st = "advise" if over else "refuse"
        return st, (f"wall: {'NOTE' if over else 'REFUSED'} [{w['store']}] — no lawful transition "
                    f"writes `{w['store']}` to `{value}`"), f"store:{w['store']}", meta

    machine = targeted[0]["machine"]
    primary = _primary_facet(model, machine)
    current = ctx.current.get(primary)
    if isinstance(current, tuple) or current is None:
        why = current[1] if isinstance(current, tuple) else "current state unread"
        live = targeted
    else:
        live = [t for t in targeted if t["from"] == current]
        why = ""
        if not live:
            if caller in ("machinery", "external-service"):
                return "observe", "", f"store:{w['store']}", meta
            st = "advise" if over else "refuse"
            return st, (f"wall: {'NOTE' if over else 'REFUSED'} [{w['store']}] — no lawful "
                        f"transition from `{current}` writes `{w['store']}` to `{value}`"), \
                   f"store:{w['store']}", meta

    lawful = [t for t in live if caller in t["actor"]]
    if not lawful:
        sanctioned = sorted({a for t in live for a in t["actor"]})
        st = "advise" if over else "refuse"
        t0 = live[0]
        return st, (f"wall: {'NOTE' if over else 'REFUSED'} [{t0['id']}] — no actor class an "
                    f"`{caller}` session belongs to may perform this transition (sanctioned: "
                    f"{', '.join(sanctioned)}). {t0['because']}"), t0["id"], meta

    if why and len(lawful) != 1:
        # current state unreadable and the candidate is ambiguous: strictest stance, naming the
        # store — for EVERY caller class. (The earlier machinery-observe shortcut here was the
        # review's guard-skip: it let a machinery merge bypass the evaluator when the PR state
        # could not be read. With exactly one lawful candidate we fall through and evaluate its
        # guards instead — all candidates live, fail-closed on whatever cannot be read.)
        st = "advise" if over else "refuse"
        return st, (f"wall: {'NOTE' if over else 'REFUSED'} [{lawful[0]['id']}] — the current state "
                    f"could not be read ({why}); a fail-closed wall that cannot evaluate refuses, "
                    f"naming what it could not read"), lawful[0]["id"], meta

    t = lawful[0]
    for g in t.get("guard") or []:
        res = _eval_guard(ctx, t, g, act)
        if res.state == "TRUE":
            continue
        st = "advise" if over else "refuse"
        col = ("missing" if res.state == "FALSE" else "could not be read")
        if g["predicate"] in ("record_present", "record_absent"):
            meta["failed_record"] = g["args"].get("record")
        return st, (f"wall: {'NOTE' if over else 'REFUSED'} [{t['id']}] — {col}: "
                    f"{render(g, model)}" + (f" ({res.reason})" if res.reason else "") +
                    f". {t['because']}"), t["id"], meta
    final = stance(caller, t, True, bd, headless=headless)
    if final == "escalate":
        return "escalate", (f"wall: PROPOSED [{t['id']}] — guards hold; this transition is the "
                            f"human's to answer (door {t['door']}). {t['because']}"), t["id"], meta
    if final == "refuse":
        return "refuse", (f"wall: REFUSED [{t['id']}] — guards hold and this transition is the "
                          f"human's to answer, but the escalation has no human to reach (the "
                          f"transport's declared headless signal is present, and ask fails open "
                          f"unattended — harness-contract §3b); a fail-closed one-way door refuses "
                          f"instead of asking nobody. {t['because']}"), t["id"], meta
    return "observe", "", t["id"], meta


def _target_value(model: dict, t: dict, store_id: str) -> str | None:
    for po in t.get("post") or []:
        if po["predicate"] == "store_is" and po["args"]["store"] == store_id:
            return po["args"]["value"]
        if po["predicate"] == "facet_is":
            key = (t["machine"], po["args"]["facet"])
            if model["_facet_store"].get(key) == store_id:
                sid = po["args"]["state"]
                for st in model["_state_rows"]:
                    if st["machine"] == t["machine"] and st["facet"] == po["args"]["facet"] \
                            and st["id"] == sid:
                        return st["value"]
    return None


def _dispose_invariant(model: dict, inv: dict, seg: dict, act: dict, caller: str) -> tuple[str, str]:
    if caller not in inv.get("actor", []):
        return "observe", ""
    enriched = dict(act)
    enriched["fields"] = dict(act["fields"])
    flags = seg.get("flags") or {}
    msg = flags.get("-m") or flags.get("--message") or flags.get("-am")
    if msg is None and (flags.get("-F") or flags.get("--file")):
        try:
            msg = Path(flags.get("-F") or flags.get("--file")).read_text(encoding="utf-8")
        except OSError:
            msg = None
    if msg is not None:
        enriched["fields"]["message"] = msg
    for g in inv.get("guard") or []:
        res = _eval_guard(_Ctx(model), inv, g, enriched)
        if res.state == "TRUE":
            continue
        col = "missing" if res.state == "FALSE" else "could not be read"
        return "refuse", (f"wall: REFUSED [{inv['id']}] — {col}: {render(g, model)}"
                          + (f" ({res.reason})" if res.reason else "")
                          + f" ({inv.get('authority', '')})")
    return "observe", ""


def _transport(model: dict, st: str, reason: str) -> dict | None:
    if st == "refuse":
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                       "permissionDecision": "deny",
                                       "permissionDecisionReason": reason}}
    if st == "escalate":
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                       "permissionDecision": "ask",
                                       "permissionDecisionReason": reason}}
    if st == "advise":
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                       "additionalContext": reason}}
    return None


# ── the journal (best-effort, after the decision, may never influence one) ───────────────────────

def journal_path(model: dict) -> Path:
    raw = model["observability"]["journal"]
    expanded = os.path.expandvars(raw)
    if "$" in expanded:
        expanded = str(Path.home() / ".cache" / "yr-attended" / "journal.jsonl")
    return Path(expanded)


def journal_append(model: dict, rows: list[dict], session_id: str = "") -> None:
    if not rows:
        return
    try:
        p = journal_path(model)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps({**r, "session": session_id}) + "\n")
    except BaseException:  # noqa: BLE001 — bookkeeping physically cannot reach the decision
        pass


def journal_rows(model: dict, session_id: str | None = None) -> list[dict] | None:
    try:
        raw = journal_path(model).read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except OSError:
        return None                        # unreadable is UNKNOWN, never ok
    rows = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except (json.JSONDecodeError, ValueError):
            continue
    return [r for r in rows if session_id is None or r.get("session") == session_id]


def close_report(model: dict, session_id: str,
                 journal_announcements: bool = True) -> tuple[str, bool]:
    """The compiled close report (surface 4). Tracks MANDATED TRACES — the postconditions of the
    transitions this session was PERMITTED to perform — rather than its own refusals (the design
    names refusal-tracking the backwards shape). Record posts are re-evaluated live, per scope;
    an unreadable journal renders UNKNOWN, never ok. Returns (text, should_block_once); empty
    text is the silent exit — no actionable trace, nothing to say (issue #428)."""
    rows = journal_rows(model, session_id)
    if rows is None:
        return ("close report: UNKNOWN (journal unreadable) — a report that cannot see is never a "
                "clean report", False)
    if not rows:
        return "", False
    lines = []
    refused = [r for r in rows if r.get("stance") == "refuse"]
    escalated = [r for r in rows if r.get("stance") == "escalate"]
    overrides = [r for r in rows if r.get("stance") == "close-override"]
    blocks = [r for r in rows if r.get("stance") == "close-block"]
    errors = [r for r in rows if r.get("stance") == "error"]
    tids = {t["id"]: t for t in model.get("transition") or []}

    # postconditions of permitted transitions, re-read NOW (the design's LEFT BEHIND / MISSING)
    missing_posts, unknown_posts, seen_posts = [], [], set()
    missing_lines, unknown_lines = [], []
    for r in rows:
        tid = r.get("transition_id")
        if r.get("stance") not in ("observe", "escalate") or tid not in tids:
            continue
        scope = r.get("scope") or {}
        key = (tid, scope.get("repo"), scope.get("issue"), scope.get("path"))
        if key in seen_posts:
            continue
        seen_posts.add(key)
        t = tids[tid]
        for po in t.get("post") or []:
            if po["predicate"] != "record_present":
                continue                    # facet posts need a board re-read; records are the trail
            ctx = _Ctx(model)
            ctx.scope.update({k: v for k, v in scope.items() if v})
            res = _eval_guard(ctx, t, po, act={"fields": {}})
            if res.state == "FALSE":
                missing_posts.append((tid, po["args"]["record"], scope.get("repo"),
                                      scope.get("issue"), scope.get("path")))
                missing_lines.append(f"MISSING: {tid} was permitted and its mandated "
                                     f"`{po['args']['record']}` record is not on the trail")
            elif res.state == "UNKNOWN":
                unknown_posts.append((tid, po["args"]["record"]))
                unknown_lines.append(f"UNKNOWN: {tid}: `{po['args']['record']}` could not be "
                                     f"re-read ({res.reason}) — never counted as ok")

    def _resolved(r: dict) -> bool:
        # Accepted residual (re-review NIT, #433): for a `store:*` refusal any later same-store
        # observe counts — an unrelated exempted act can suppress the terminal bookkeeping row.
        # The close decision is identical either way (silent); only the round record's raw
        # material loses a disposition line, and distinguishing "real resolution" from
        # coincidence needs evidence the journal does not carry.
        return any(p.get("stance") == "observe"
                   and p.get("transition_id") == r.get("transition_id")
                   and p.get("ts", 0) >= r.get("ts", 0) for p in rows)

    # Terminal refusals (it-31 slice 1, #433): a `store:*` refusal means the wall found NO
    # transition for the act as performed — the refusal was the correct FINAL outcome, with no
    # lawful later pass by construction. Recorded once as `refusal-terminal` (bookkeeping, like
    # `drift-advised`: the row records a disposition already decided and cannot influence this
    # decision), excluded from the cycle immediately, never demanded again. Narrow by design
    # (the review's findings on #433): an `invariant:*` refusal IS retry-resolvable and stays in
    # the cycle, and a store refusal a later same-tid observe resolved is not terminal either.
    terminal = [r for r in refused
                if str(r.get("transition_id", "")).startswith("store:") and not _resolved(r)]
    if terminal and journal_announcements:
        already = {(r.get("transition_id"), r.get("refusal_ts")) for r in rows
                   if r.get("stance") == "refusal-terminal"}
        fresh_terminal = [r for r in terminal
                          if (r.get("transition_id"), r.get("ts", 0)) not in already]
        if fresh_terminal:
            journal_append(model, [{"ts": int(time.time()),
                                    "transition_id": r.get("transition_id"),
                                    "binding_id": r.get("binding_id"),
                                    "scope": r.get("scope") or {},
                                    "stance": "refusal-terminal",
                                    "caller": r.get("caller", "attended-agent"),
                                    "refusal_ts": r.get("ts", 0)} for r in fresh_terminal],
                           session_id)
    unresolved = [r for r in refused
                  if not str(r.get("transition_id", "")).startswith("store:")
                  and not _resolved(r)]

    # Drift — ruling 1B's close-report surface, bounded: durable repo state must never re-create
    # the wake/stop loop, so an outstanding finding is announced at most once per session (the
    # `drift-advised` marker row is the bound; a changed finding is a fresh announcement).
    advised = {r.get("finding") for r in rows if r.get("stance") == "drift-advised"}
    fresh_drift = [p for p in check_drift(model) if p not in advised]

    # The quiesce ladder (it-31 slice 1): the wall's own bookkeeping rows never re-arm a block —
    # `newest` reads only the actionable traces — and an override newer than every actionable
    # trace is TERMINAL for that state: block at most once, proceed loud at most once, then —
    # traces unchanged — silence. Two review-hardened details (#433): ordering is (ts, journal
    # row index), so a new trace in the SAME epoch second as the override still re-arms; and a
    # missing post is anchored at its ANNOUNCEMENT (the `missing-advised` marker row), so an
    # absence first detected after the override was never covered by it and still gets its cycle
    # — an unannounced missing post anchors at +infinity.
    _index = {id(r): i for i, r in enumerate(rows)}

    def _ord(r: dict) -> tuple:
        return (r.get("ts", 0), _index.get(id(r), -1))

    # Scope rides the key (re-review finding 2, #433): issue 2's missing record is a NEW trace
    # even after issue 1's identical (transition, record) pair was announced and overridden.
    advised_missing = {(r.get("post_tid"), r.get("record"), (r.get("scope") or {}).get("repo"),
                       (r.get("scope") or {}).get("issue"), (r.get("scope") or {}).get("path")):
                       _ord(r) for r in rows if r.get("stance") == "missing-advised"}
    missing_anchors = [advised_missing.get(key, (float("inf"), 0)) for key in missing_posts]
    block = False
    overridden = 0
    if unresolved or missing_posts:
        latest_block = max((_ord(r) for r in blocks), default=(0, -1))
        latest_override = max((_ord(r) for r in overrides), default=(0, -1))
        newest = max([_ord(r) for r in unresolved] + missing_anchors, default=(0, -1))
        if overrides and latest_override >= newest and latest_override >= latest_block:
            overridden = len(unresolved) + len(missing_posts)
            unresolved, missing_posts, missing_lines = [], [], []
        elif blocks and latest_block >= newest:
            pass                            # the one loud proceed; the OVERRIDE line lands below
        else:
            block = True
    if missing_posts and journal_announcements:
        # The announcement marker anchors the trace (bookkeeping, like `drift-advised`); written
        # only when the MISSING lines actually render, once per (transition, record).
        fresh_missing = [key for key in missing_posts if key not in advised_missing]
        if fresh_missing:
            journal_append(model, [{"ts": int(time.time()), "transition_id": "close",
                                    "binding_id": None,
                                    "scope": {k: v for k, v in
                                              zip(("repo", "issue", "path"), key[2:]) if v},
                                    "stance": "missing-advised", "caller": "attended-agent",
                                    "post_tid": key[0], "record": key[1]}
                                   for key in fresh_missing], session_id)

    # The silent exit: clean means NO ACTIONABLE TRACE — nothing unresolved, missing, unknown,
    # or errored, and no drift announcement due. Counts alone never decide: a refusal later
    # resolved lawfully — or terminally dispositioned, or overridden with traces unchanged —
    # leaves a nonzero count and a clean, silent session.
    if not (unresolved or missing_posts or unknown_posts or errors or fresh_drift):
        return "", False

    counts = {"refusals": len(refused),
              "records-demanded": len({r.get("failed_record") for r in refused
                                       if r.get("failed_record")}),
              "detector-findings": len(missing_posts),
              "escalations": len(escalated)}
    lines.append("close report — " + json.dumps(counts))
    lines += missing_lines + unknown_lines
    for r in unresolved:
        lines.append(f"UNRESOLVED: {r.get('transition_id')} was refused and no later lawful pass "
                     f"is journaled")
    if overridden:
        lines.append(f"OVERRIDDEN: {overridden} trace(s) stand overridden, recorded — unchanged "
                     f"traces never re-arm the close")
    for r in errors:
        detail = str(r.get("detail") or "no detail journaled")[:120].replace("\n", " ")
        lines.append(f"ERROR: the wall crashed on an act ({detail}) — a session whose "
                     f"walls crashed is never clean")
    for p in fresh_drift:
        lines.append(f"DRIFT (advisory): {p}")
    touched_stores = {r.get("transition_id", "").removeprefix("store:")
                      for r in rows if str(r.get("transition_id", "")).startswith("store:")}
    touched_stores |= {sid for r in rows if r.get("transition_id") in tids
                       for sid in _stores_written(tids[r["transition_id"]], model)}
    for sid in sorted(touched_stores):
        store = model["_stores"].get(sid)
        if not store:
            continue
        for wp in store.get("write_path") or []:
            if not wp.get("observable"):
                lines.append(f"NOT OBSERVED: {wp['how']} — detected only by "
                             f"{wp.get('detected_by', '(undetectable)')} via check_trail.py")
    if (unresolved or missing_posts) and not block:
        lines.append(f"OVERRIDE: proceeding loud with {len(unresolved)} unresolved refusal(s) "
                     f"and {len(missing_posts)} missing postcondition(s) — recorded "
                     f"({len(overrides) + 1} total)")
    if fresh_drift and journal_announcements:
        # The marker records an announcement that already happened; this write cannot influence
        # the decision it records. Fail-soft like every journal write.
        journal_append(model, [{"ts": int(time.time()), "transition_id": "close",
                                "binding_id": None, "scope": {}, "stance": "drift-advised",
                                "caller": "attended-agent", "finding": p} for p in fresh_drift],
                       session_id)
    return "\n".join(lines), block


# ── drift + decay ────────────────────────────────────────────────────────────────────────────────

def check_drift(model: dict) -> list[str]:
    problems = []
    expected = {"build/lanes.toml": compile_lanes(model),
                "build/walled-acts.md": compile_acts(model),
                "build/slice-static.md": compile_slice(model),
                "build/conformance.json": compile_conformance(model)}
    for rel, want in expected.items():
        p = REPO_ROOT / rel
        try:
            got = p.read_text(encoding="utf-8")
        except OSError:
            problems.append(f"{rel}: missing — run `process.py compile all`")
            continue
        if got != want:
            problems.append(f"{rel}: STALE against process.toml v{model['model']['version']} — "
                            f"run `process.py compile all` and commit the diff")
    return problems


def run_decay(model: dict) -> list[str]:
    notes = []
    for pr in (model.get("port") or {}).get("probe") or []:
        try:
            out = subprocess.run(pr["fingerprint_cmd"].split(), capture_output=True, timeout=30)
            fp = "sha256:" + hashlib.sha256(out.stdout).hexdigest()
        except (OSError, subprocess.TimeoutExpired) as e:
            notes.append(f"probe {pr['id']}: BROKEN ({e})")
            continue
        if fp != pr.get("fingerprint"):
            notes.append(f"probe {pr['id']}: DRIFTED — the `{pr['subject']}` surface changed "
                         f"({pr['on_drift']})")
    today = _dt.date.today()
    for bd in (model.get("port") or {}).get("binding") or []:
        d = decay(bd, today)
        if d != "fresh":
            notes.append(f"binding {bd['id']}: {d} (verified {bd.get('verified_on')}, "
                         f"recheck {bd.get('recheck_days')}d)")
    return notes


# ── transition-check: the sharper unit (promote.sh's wall, the epic flip tool's core) ────────────

def transition_check(model: dict, tid: str, scope: dict) -> tuple[int, list[str]]:
    t = next((t for t in model.get("transition") or [] if t["id"] == tid), None)
    if t is None:
        return 2, [f"unknown transition {tid!r}"]
    ctx = _Ctx(model)
    ctx.scope.update(scope)
    if scope.get("repo") and scope.get("issue"):
        ok, data = sources.issue_board_position(scope["repo"], scope["issue"])
        if ok:
            for facet in ("status", "reason"):
                sid = model["_value_state"].get((t["machine"], facet, data.get(facet, "")))
                ctx.current[facet] = sid or ("UNKNOWN", f"{facet} reads {data.get(facet)!r}")
    failures = []
    for g in t.get("guard") or []:
        res = _eval_guard(ctx, t, g, act={"fields": {}})
        if res.state != "TRUE":
            tag = "MISSING" if res.state == "FALSE" else "UNKNOWN"
            failures.append(f"{tag}: {render(g, model)}" + (f" ({res.reason})" if res.reason else ""))
    return (1 if failures else 0), failures


# ── CLI ──────────────────────────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:  # noqa: C901
    ap = argparse.ArgumentParser(description="the process model: loader, compilers, engine")
    ap.add_argument("--model", type=Path, default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate", help="load + every rule; exit 0 loaded, 1 broken (the gating tier)")
    p_c = sub.add_parser("compile", help="compile a surface (or all) into build/")
    p_c.add_argument("surface", choices=["acts", "lanes", "slice", "conformance", "all"])
    p_chk = sub.add_parser("check", help="advisory checks")
    p_chk.add_argument("--drift", action="store_true")
    sub.add_parser("lanes", help="print the compiled lane mandates")
    p_t = sub.add_parser("transition-check", help="evaluate one transition's guards for a scope")
    p_t.add_argument("transition")
    p_t.add_argument("--repo", default="")
    p_t.add_argument("--issue", default="")
    p_t.add_argument("--pr", default="")
    p_t.add_argument("--path", default="")
    p_d = sub.add_parser("decide", help="hook JSON on stdin -> decision JSON (dry-run friendly)")
    p_d.add_argument("--no-journal", action="store_true",
                     help="test mode: decide without touching the journal")
    sub.add_parser("decay", help="probe fingerprints + binding age; advisory, loud")
    p_cr = sub.add_parser("close-report", help="the compiled close report for a session")
    p_cr.add_argument("--session", required=True)
    args = ap.parse_args(argv)

    try:
        model = load(args.model)
    except (ModelError, records.RegistryError) as e:
        print(f"process: MODEL DOES NOT LOAD — the walls are OFF until this is repaired: {e}",
              file=sys.stderr)
        return 1

    if args.cmd == "validate":
        print(f"process: ok — v{model['model']['version']}, "
              f"{len(model.get('transition') or [])} transitions, "
              f"{len(model.get('store') or [])} stores, "
              f"{len((model.get('port') or {}).get('binding') or [])} bindings")
        return 0
    if args.cmd == "compile":
        BUILD_DIR.mkdir(exist_ok=True)
        surfaces = {"lanes": ("lanes.toml", compile_lanes),
                    "acts": ("walled-acts.md", compile_acts),
                    "slice": ("slice-static.md", compile_slice),
                    "conformance": ("conformance.json", compile_conformance)}
        chosen = surfaces if args.surface == "all" else {args.surface: surfaces[args.surface]}
        for name, (fn, compiler) in chosen.items():
            out = compiler(model)
            (BUILD_DIR / fn).write_text(out, encoding="utf-8")
            print(f"process: compiled build/{fn} ({len(out.encode())} bytes)")
        return 0
    if args.cmd == "check":
        problems = check_drift(model)
        for p in problems:
            print(f"process: DRIFT — {p}")
        return 1 if problems else 0
    if args.cmd == "lanes":
        mandate, forbid = lanes(model)
        print(json.dumps({"mandate": mandate, "must-not-carry": forbid}, indent=1))
        return 0
    if args.cmd == "transition-check":
        rc, failures = transition_check(model, args.transition,
                                        {k: v for k, v in (("repo", args.repo),
                                                           ("issue", args.issue),
                                                           ("pr", args.pr), ("path", args.path)) if v})
        for f in failures:
            print(f"process: {f}", file=sys.stderr)
        return rc
    if args.cmd == "decide":
        try:
            hook = json.load(sys.stdin)
        except (json.JSONDecodeError, ValueError):
            return 0
        out, rows = decide(model, hook)
        if not args.no_journal:
            journal_append(model, rows, hook.get("session_id") or "")
        if out:
            print(json.dumps(out))
        return 0
    if args.cmd == "decay":
        notes = run_decay(model)
        for n in notes:
            print(f"process: {n}")
        return 0
    if args.cmd == "close-report":
        # A read-named preview never consumes the Stop hook's once-per-session drift announcement.
        text, block = close_report(model, args.session, journal_announcements=False)
        if text:
            print(text)
        return 3 if block else 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
