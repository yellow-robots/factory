#!/usr/bin/env python3
"""compile_slice.py — the delivered slice's compiler (it-30 slice 4, epic #415).

Deterministic text assembly, never a model call: the bounded slice an attended session receives at
start is compiled from the canon's two tables (`skills/factory/references/attended-lane.md` — the
step set and the walled-act map), the registry's lanes (`records.toml`), and the router's operation
rows (`skills/factory/SKILL.md`). Three parts, per the spec's callout (f) as ruled: (1) the step set,
(2) the walled-act map, (3) canon pointers with the human's checkpoints marked. Never the manual —
the compiler enforces its own bound and fails loud past it.

The artifact is compiled, never edited: a hand fix is a defect; the fix lands in the tables this
reads. The runtime position element is COMPOSED AT DELIVERY by the delivery hook — never cached here
(`hooks/deliver.sh` owns it, loud-non-blocking).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import records  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
LANE_REF = REPO / "skills" / "factory" / "references" / "attended-lane.md"
SKILL = REPO / "skills" / "factory" / "SKILL.md"

# The bound: the slice is a slice. Past this, delivery is rebuilding the read-channel failure it
# exists to fix — fail loud, fix the tables.
MAX_BYTES = 12_000

def _section(text: str, heading: str) -> str:
    """The body of the `## heading` section — bounded at the next `## `. Unbounded search was a
    silent-wrong-canon hazard (a moved or emptied table let the NEXT section's table be delivered
    under this heading, exit 0); the bound makes a canon reshape fail loud instead."""
    m = re.search(rf"^## {re.escape(heading)}.*?$", text, flags=re.M)
    if not m:
        raise SystemExit(f"compile_slice: ERROR: heading not found in attended-lane.md: {heading!r} "
                         f"— the canon was reshaped; the compiler reads its tables by heading")
    return text[m.end():].split("\n## ")[0]


def _extract_table(text: str, heading: str) -> str:
    """The markdown table inside `heading`'s own section, verbatim."""
    t = re.search(r"((?:^\|.*\n)+)", _section(text, heading), flags=re.M)
    if not t:
        raise SystemExit(f"compile_slice: ERROR: no table under heading: {heading!r}")
    return t.group(1).rstrip()


def _human_checkpoints(text: str) -> str:
    """The checkpoint list, read from canon — never authored here. A hardcoded copy in this file
    would be a third authority beside the canon and the registry, editable only by hand, which the
    round's own drift contract forbids."""
    bullets = [l.rstrip() for l in _section(text, "The human's checkpoints (what the coordination arm surfaces)").splitlines()
               if l.startswith("- ")]
    if not bullets:
        raise SystemExit("compile_slice: ERROR: attended-lane.md carries no human-checkpoint bullets")
    return "\n".join(bullets)


def _router_rows(text: str) -> str:
    """The router table — header, separator, and operation rows — from SKILL.md's own table block."""
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if l.startswith("| Operation ")), None)
    if start is None:
        raise SystemExit("compile_slice: ERROR: SKILL.md's router table header not found")
    rows = []
    for l in lines[start:]:
        if not l.startswith("|"):
            break
        rows.append(l)
    if len(rows) < 4:
        raise SystemExit("compile_slice: ERROR: SKILL.md's router table is empty")
    return "\n".join(rows)


def compile_slice() -> str:
    lane = LANE_REF.read_text(encoding="utf-8")
    skill = SKILL.read_text(encoding="utf-8")
    reg = records.load()
    steps = _extract_table(lane, "The mandatory step set (reified — the existing mandates, not new ones)")
    acts = _extract_table(lane, "The walled-act map (total — every act carries condition AND stance)")
    lanes = records.lanes(reg)
    lane_lines = "\n".join(f"- `{name}` lane mandates: {', '.join(f'`{w}`' for w in wanted)}"
                           for name, wanted in sorted(lanes.items()))
    out = f"""# The attended lane — the delivered slice (compiled; never hand-edited)

Delivered at session start to every attended session in a workspace carrying the factory plugin.
WHERE the work is factory work, this slice is the lane's operating ground — the step set, the walled
acts, and where depth lives; the position element below is composed at delivery.

## 1 · The mandatory step set (each step emits its record)

{steps}

Lane mandates (the detector checks these — `tools/check_trail.py`):
{lane_lines}

## 2 · The walled-act map (condition ⇒ stance; refusals name the rule)

{acts}

## 3 · Depth, routed — and the human's checkpoints

Load the reference for the operation you are performing (the factory skill's router):

{_router_rows(skill)}

**The human's checkpoints — surfaced, never remembered** (when a round reaches one, the surface she
watches — the board item or the session's close report — names it):
{_human_checkpoints(lane)}

*A record absent from `records.toml` is unsanctioned. Walls check existence and grammar only —
genuineness stays with independent review and the adherence bench. Fail loud; the talking wall
teaches.*
"""
    if len(out.encode("utf-8")) > MAX_BYTES:
        raise SystemExit(f"compile_slice: ERROR: slice exceeds its bound "
                         f"({len(out.encode('utf-8'))} > {MAX_BYTES} bytes) — trim the tables, "
                         f"never raise the bound casually")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="compile the attended lane's delivered slice")
    ap.add_argument("--out", type=Path, default=None, help="write here instead of stdout")
    args = ap.parse_args(argv)
    try:
        text = compile_slice()
    except records.RegistryError as e:
        # A registry defect is the likeliest real failure; it must reach the banner as ITSELF, never
        # as the head of a traceback (legible failure, derivable recovery).
        raise SystemExit(f"compile_slice: ERROR: the record registry does not load: {e}")
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
