"""
Tests for Issue #484 — it-32 slice 3: the workflow taxonomy in AGENTS.md
("### Workflow types — who decides, and what each walks").

Derived from the Issue #484 acceptance criteria (the spec), not from the
implementation internals. The canon (AGENTS.md), inside *The operating model*,
gains a subsection that:

  1. names the actor and the moment that decide which workflow type a piece of
     work is — decided at the moment the work's first artifact is created, the
     session proposing the type on that artifact, the deciding actor being the
     PM once it-36 ships (a forward reference) and the owner until then;

  2. states, for each of the seven workflow types, its path, actors in order,
     mandatory/optional steps, and each gate with its holder, in a seven-row
     table; and

  3. declares which steps are machine-checked and which are prose — every
     machine-checked cell naming ONLY `id`s of transition rows of
     `process.toml`, or, where the check is a gate's refusal rather than a
     transition, the refusal's `records.toml` row name.

The pins below read `process.toml` and `records.toml` with `tomllib`, on the
shape of tests/test_architect_reconciliation_and_gate_locations.py:32 — so a
cited transition id or record name is checked against the machines themselves,
never a copy. The taxonomy CITES ids; it never re-describes a machine, so a
renamed transition surfaces here as a broken citation.
"""

import pathlib
import re
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[1]

AGENTS = ROOT / "AGENTS.md"
PROCESS = ROOT / "process.toml"
RECORDS = ROOT / "records.toml"

HEADING = "### Workflow types — who decides, and what each walks"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _agents_text():
    return AGENTS.read_text(encoding="utf-8")


def _taxonomy_section():
    """The subsection body, from its `### ` heading to the next section boundary
    (`\\n---` or the next `\\n## `/`\\n### `)."""
    text = _agents_text()
    start = text.find(HEADING)
    assert start != -1, (
        f"AGENTS.md is missing the taxonomy subsection heading {HEADING!r} — it must sit "
        "inside *The operating model*, between the task-lifecycle table and the closing '---'"
    )
    rest = text[start + len(HEADING):]
    ends = [m.start() for m in re.finditer(r"\n---|\n## |\n### ", rest)]
    end = min(ends) if ends else len(rest)
    return rest[:end]


def _taxonomy_is_inside_operating_model():
    """The heading sits after '## The operating model' and before the next '## ' heading."""
    text = _agents_text()
    om = text.find("## The operating model")
    assert om != -1, "AGENTS.md is missing its '## The operating model' section"
    nxt = text.find("\n## ", om + len("## The operating model"))
    section = text[om: nxt if nxt != -1 else len(text)]
    return HEADING in section


def _table_rows():
    """The taxonomy table's DATA rows as lists of stripped cell strings (header and
    the `|---|` separator dropped)."""
    section = _taxonomy_section()
    pipe_lines = [ln.strip() for ln in section.splitlines() if ln.strip().startswith("|")]
    assert pipe_lines, "the taxonomy subsection has no markdown table"

    def cells(line):
        return [c.strip() for c in line.split("|")[1:-1]]

    def is_separator(line):
        return all(set(c) <= set("-:") and c for c in cells(line))

    header = cells(pipe_lines[0])
    data = [cells(ln) for ln in pipe_lines[1:] if not is_separator(ln)]
    return header, data


def _process_transition_ids():
    data = tomllib.load(PROCESS.open("rb"))
    return {t["id"] for t in data["transition"]}


def _record_names():
    data = tomllib.load(RECORDS.open("rb"))
    return {r["name"] for r in data["record"]}


# ---------------------------------------------------------------------------
# AC1 — the subsection exists, inside The operating model
# ---------------------------------------------------------------------------

def test_subsection_exists_inside_the_operating_model():
    assert _taxonomy_is_inside_operating_model(), (
        "the '### Workflow types' subsection is not inside '## The operating model' — the "
        "spec places it between :45 and the closing '---'"
    )


# ---------------------------------------------------------------------------
# AC1 — the rule: who decides, and the moment
# ---------------------------------------------------------------------------

def test_rule_names_the_moment_the_first_artifact_is_created():
    section = _taxonomy_section().lower()
    assert "first artifact" in section, (
        "the taxonomy rule does not tie the type decision to the moment the work's FIRST "
        "ARTIFACT is created"
    )


def test_rule_says_the_session_proposes_the_type():
    section = _taxonomy_section().lower()
    assert re.search(r"session propos", section), (
        "the taxonomy rule does not say the session PROPOSES the type on that artifact"
    )


def test_rule_names_the_pm_by_forward_reference_and_the_owner():
    section = _taxonomy_section()
    lowered = section.lower()
    assert "PM" in section, "the taxonomy rule does not name the PM as the eventual deciding actor"
    assert "it-36" in lowered, (
        "the taxonomy rule does not carry the forward reference ('once it-36 ships') that "
        "makes the PM the deciding actor only after it-36"
    )
    assert "owner" in lowered, (
        "the taxonomy rule does not name the owner as the deciding actor until it-36 ships"
    )


# ---------------------------------------------------------------------------
# AC2 — exactly seven rows, and the seven types are the named seven
# ---------------------------------------------------------------------------

def test_table_has_a_seven_column_header():
    header, _ = _table_rows()
    for expected in ("type", "path", "machine-checked", "prose"):
        assert any(expected in h.lower() for h in header), (
            f"the taxonomy table header is missing the {expected!r} column: {header}"
        )
    assert any("actor" in h.lower() for h in header), \
        f"the taxonomy table header is missing the 'actors in order' column: {header}"
    assert any("gate" in h.lower() for h in header), \
        f"the taxonomy table header is missing the 'gates and holders' column: {header}"


def test_table_has_exactly_seven_rows():
    _, data = _table_rows()
    assert len(data) == 7, (
        f"the taxonomy table must have exactly seven type rows (one per workflow type); "
        f"found {len(data)}"
    )


def test_the_seven_named_types_are_all_present():
    _, data = _table_rows()
    type_cells = " || ".join(row[0].lower() for row in data)
    expected = [
        "full ladder",        # (1) full ladder, legacy
        "technical-rfc",      # (2) spec + technical-rfc, the norm
        "floor",              # (3) the floor
        "seed-to-task",       # (4) the direct seed-to-task lane
        "attended host",      # (5) attended host and ops
        "gate evolution",     # (6) attended gate evolution
        "debt round",         # (7) the debt round
    ]
    for keyword in expected:
        assert keyword in type_cells, (
            f"the taxonomy's type column does not name the {keyword!r} workflow type: "
            f"{[row[0] for row in data]}"
        )


# ---------------------------------------------------------------------------
# AC3 / AC4 — every machine-checked transition id is a real process.toml id
# ---------------------------------------------------------------------------

def _machine_checked_column_index():
    header, _ = _table_rows()
    for i, h in enumerate(header):
        if "machine-checked" in h.lower():
            return i
    raise AssertionError(f"the taxonomy table has no 'machine-checked' column: {header}")


def _machine_checked_tokens():
    """Every backtick-wrapped token in any machine-checked cell."""
    idx = _machine_checked_column_index()
    _, data = _table_rows()
    tokens = []
    for row in data:
        tokens.extend(re.findall(r"`([^`]+)`", row[idx]))
    return tokens


def _cited_transition_ids():
    """The machine-checked tokens containing '->' — the transition-id tokens the taxonomy
    cites, identified by the spec's '->' heuristic."""
    return [t for t in _machine_checked_tokens() if "->" in t]


def test_machine_checked_column_cites_transition_ids():
    cited = _cited_transition_ids()
    assert cited, (
        "no machine-checked cell cites any transition id (a backtick token containing "
        "'->'); the taxonomy must name the process.toml transitions its steps ride"
    )


def test_every_cited_transition_id_exists_in_process_toml():
    cited = _cited_transition_ids()
    valid = _process_transition_ids()
    unknown = sorted({t for t in cited if t not in valid})
    assert not unknown, (
        "the taxonomy's machine-checked column cites transition ids that are NOT rows in "
        f"process.toml (read with tomllib): {unknown}. The table cites ids; a renamed or "
        "removed transition must break this citation, never be re-described in prose."
    )


def test_key_transitions_are_cited_across_the_table():
    """Spot-pin the load-bearing transitions the spec assigns to specific rows, so a table
    that silently drops one is caught — each must appear somewhere in the machine-checked
    column AND be a real process.toml id. Uses all backtick tokens (not the '->' subset),
    because one load-bearing transition — `shared-ref.push.instructed` — carries no '->'."""
    cited = set(_machine_checked_tokens())
    valid = _process_transition_ids()
    must_be_cited = {
        "design-doc.draft->active",
        "task.backlog->ready.epic-flip",
        "task.backlog->ready.epic-child",
        "task.backlog->ready.standalone",
        "task.ready->in-progress.claim",
        "task.in-progress->in-review.pr-open",
        "pr.approved->merged.evaluator",
        "task.in-review->done.native",
        "task.ready->done.epic-close",
        "sentinel.clear->thrown.throw",
        "sentinel.thrown->clear.clear",
        "arming.disarmed->armed.arm",
        "arming.armed->disarmed.unarm",
        "shared-ref.push.instructed",
    }
    missing_from_table = sorted(must_be_cited - cited)
    assert not missing_from_table, (
        f"the taxonomy's machine-checked column no longer cites these transitions: "
        f"{missing_from_table}"
    )
    not_real = sorted(must_be_cited - valid)
    assert not not_real, (
        f"expected transitions are not process.toml ids (the fixture drifted from the "
        f"model): {not_real}"
    )


# ---------------------------------------------------------------------------
# AC3 — the gate-refusal row names a real records.toml row (not a transition)
# ---------------------------------------------------------------------------

def test_gate_touching_row_names_a_records_toml_row_not_a_transition():
    idx = _machine_checked_column_index()
    _, data = _table_rows()
    gate_rows = [row for row in data if "gate evolution" in row[0].lower()]
    assert len(gate_rows) == 1, (
        "the 'attended gate evolution' type row must appear exactly once; found "
        f"{len(gate_rows)}"
    )
    cell = gate_rows[0][idx]
    assert "YR-EPIC-GATE: gate-touching" in cell, (
        "attended gate evolution's machine-checked cell must name the refusal record "
        "`YR-EPIC-GATE: gate-touching` — its check is a gate's refusal, not a transition"
    )
    # Where the check is a refusal, the cell names a records.toml row, not a transition id.
    tokens = re.findall(r"`([^`]+)`", cell)
    assert not any("->" in t for t in tokens), (
        "attended gate evolution cites a transition id, but the spec says this row has NO "
        f"transition — the gate's refusal is a record: {cell!r}"
    )
    assert "YR-EPIC-GATE: gate-touching" in _record_names(), (
        "`YR-EPIC-GATE: gate-touching` is not a `name` row of records.toml (read with "
        "tomllib) — the taxonomy's refusal citation must resolve to a real record"
    )
