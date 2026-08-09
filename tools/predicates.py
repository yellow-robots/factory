#!/usr/bin/env python3
"""predicates.py — the closed predicate vocabulary, PURE (it-30, the process model).

Six predicates, one implementation each, tri-state: `TRUE | FALSE | UNKNOWN(reason)`. `Result`
implements no `__bool__`, so a caller cannot accidentally collapse UNKNOWN into falsy-or-truthy —
disposition happens in exactly one table (tools/process.py). No predicate performs I/O: every
function judges a payload some `[[source]]` fetcher already produced (tools/sources.py), which is
the design's root-cause fix for one-grammar-three-implementations. An import-level guard in the
test suite rejects this module if it grows `subprocess`, `socket`, `urllib`, or a filesystem read.

Admission rule (model-design § predicates): a new predicate needs (i) no existing implementation
anywhere in the tree and (ii) at least two rows needing it — otherwise delegate via `[[evaluator]]`
or express it as a store. Adding one is a `[model].version` bump plus an `[[amendment]]` row.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_trail  # noqa: E402 — _marker_present/_missing_fields: ONE grammar implementation
import records  # noqa: E402


class Result:
    """Tri-state verdict. No `__bool__` on purpose: `if result:` is a type error by convention,
    enforced by a guard test — disposition is the engine's one table, never a truthiness check."""

    __slots__ = ("state", "reason")

    def __init__(self, state: str, reason: str = ""):
        assert state in ("TRUE", "FALSE", "UNKNOWN")
        self.state = state
        self.reason = reason

    def __bool__(self):  # noqa: D105
        raise TypeError("Result has no truthiness — dispose through the engine's table")

    def __repr__(self):
        return f"Result({self.state}{', ' + self.reason if self.reason else ''})"


TRUE = Result("TRUE")
FALSE = Result("FALSE")


def unknown(reason: str) -> Result:
    return Result("UNKNOWN", reason)


def false(reason: str = "") -> Result:
    return Result("FALSE", reason)


# ── the six ──────────────────────────────────────────────────────────────────────────────────────

def facet_is(facet: str, state_id: str, *, current: dict) -> Result:
    """`current` maps facet -> resolved state id, or -> ("UNKNOWN", reason)."""
    got = current.get(facet)
    if got is None:
        return unknown(f"facet {facet!r} not resolved")
    if isinstance(got, tuple):
        return unknown(got[1])
    return TRUE if got == state_id else false(f"{facet} is {got!r}, not {state_id!r}")


def store_is(store: str, value: str, *, reads: dict) -> Result:
    """`reads` maps store id -> raw value, or -> ("UNKNOWN", reason)."""
    got = reads.get(store)
    if got is None:
        return unknown(f"store {store!r} not read")
    if isinstance(got, tuple):
        return unknown(got[1])
    return TRUE if str(got) == value else false(f"{store} reads {got!r}, not {value!r}")


def record_present(record: str, *, registry: dict, texts: list[str] | None) -> Result:
    """Presence + grammar of a registered record over pre-fetched surface texts. The registry row
    routes the read (rule R) — there is no surface argument to get wrong. UNKNOWN when the surface
    could not be fetched; NEVER FALSE for infrastructure."""
    if texts is None:
        return unknown("the record's surface could not be fetched")
    row = records.get(registry, record)
    if not check_trail._marker_present(row, texts):
        return false(f"no {row['marker']!r} line on the trail")
    missing = check_trail._missing_fields(row, texts)
    if missing:
        return false(f"{record}: field(s) missing: {', '.join(missing)}")
    return TRUE


def record_absent(record: str, *, registry: dict, texts: list[str] | None) -> Result:
    """The airlock shape. UNKNOWN stays UNKNOWN — `not UNKNOWN` is the fail-open trapdoor, which is
    why there is no `not` combinator anywhere in the vocabulary."""
    if texts is None:
        return unknown("the record's surface could not be fetched")
    row = records.get(registry, record)
    if check_trail._marker_present(row, texts):
        return false(f"a {row['marker']!r} line rides the trail")
    return TRUE


def evaluator_pass(evaluator: str, *, outcome: tuple[int | None, str]) -> Result:
    """`outcome` = (exit_code | None, first_stdout_line) from the engine's bounded run of the
    declared argv. Contract: 0 -> TRUE; 1 with a token -> FALSE naming it; anything else UNKNOWN —
    indeterminate is never success (the merge evaluator's own rule, inherited)."""
    code, token = outcome
    if code == 0:
        return TRUE
    if code == 1:
        return false(f"still needs: {token}") if token.strip() else unknown(
            f"evaluator {evaluator!r} failed without naming a condition")
    return unknown(f"evaluator {evaluator!r} indeterminate (exit {code!r})")


def act_field_contains(field: str, literal: str, *, act: dict) -> Result:
    """Invariants only; pure over the normalized act. UNKNOWN when the field is not visible
    pre-execution (an editor-driven commit body) — a typed UNKNOWN, never a silent pass."""
    got = act.get("fields", {}).get(field)
    if got is None:
        return unknown(f"the act's {field!r} is not visible pre-execution")
    return TRUE if literal in str(got) else false(f"the act's {field!r} lacks {literal!r}")


PREDICATES = ("facet_is", "store_is", "record_present", "record_absent",
              "evaluator_pass", "act_field_contains")
