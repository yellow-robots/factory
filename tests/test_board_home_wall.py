"""The wall-11 guard for issue #388 — One home for the board's plumbing.

Derived from the issue's acceptance criteria (the spec), not from tools/board_plumbing.py's internals:

  - "The wall-11 guard: a pytest test under tests/ asserts that each board identifier literal appears in
    exactly ONE home. It reads PRODUCTION AND TESTS both ... It derives its expected home from the tree
    rather than enumerating offenders, and it names the surfaces it reads."
  - "IF the seven option-id literals resist a sound predicate — they are bare eight-character hexadecimal
    tokens and a naïve pattern collides with short commit hashes — THEN the guard covers the unambiguous
    prefixed identifiers and the slice RECORDS why no guard is expressible for the option-id half and what
    would have to be true for one to exist."
  - "The new home is named in AGENTS.md's ## Repo map table."

THE SURFACES THIS GUARD READS (named, per debt-rounds.md wall 11 — a match outside them cannot satisfy
the guard):

  1. PRODUCTION — every `*.py` and `*.sh` file under `tools/`.
  2. TESTS — every `*.py` file under `tests/`.

Both are read for BOTH halves of the wall's mandate, because the suite has been a second home for these
literals since round zero: a guard blind to `tests/` would pass while the clones it exists to end sit
there (they did, in tests/test_epic_gate.py, until issue #388 migrated them onto the home).

WHAT COUNTS AS A "HOME" (the predicate, derived — not a hardcoded offender list). A home for a board
identifier is a source LINE that carries BOTH that identifier's UPPERCASE environment-variable NAME and
its literal value together — the shape of a declaration or a re-declaration of the configured value
(`os.environ.get("PROJECT_ID", "PVT_…")` in the home; `epic_gate.PROJECT_ID == "PVT_…"` in the old test
clone). A behavioural assertion that merely names the observed value against a gh flag
(`f["--project-id"] == "PVT_…"`, as the pin suite does) does NOT pair the uppercase env-name with the
literal on one line, so it is not a home and is left standing — exactly the behaviour pins issue #388's
constraints forbid this slice from touching. The (name, literal) pairs themselves are read out of the
home module's own `os.environ.get(...)` declarations, so nothing is enumerated and no literal is restated
in this guard file.

THE OPTION-ID HALF — a recorded impossibility, scoped to that half only (debt-rounds.md wall 11's escape
hatch: a recorded impossibility is a finding; silence is not). The three PVT-prefixed identifiers — the
project id (`PVT_…`) and the two single-select field ids (`PVTSSF_…`) — carry distinguishing prefixes, so
a tree-wide predicate for them is sound and this guard enforces it. The seven status/reason OPTION ids are
bare eight-character hexadecimal tokens (`b863a902`, `c85eb5c1`, …), indistinguishable from the short
commit hashes that appear in comments and test fixtures across this repo; any pattern that matched them
would collide, so NO sound guard is expressible for the option-id half. It would become expressible only
if those ids gained a distinguishing prefix (a board-schema change, out of scope) or a declared registry
the tree could diff against. Absent either, the option-id half is left unguarded BY DESIGN; this docstring
and tools/board_plumbing.py's own module docstring are that recorded impossibility, and
test_the_option_id_impossibility_is_recorded_at_the_home below pins the home's record so it cannot be
silently dropped.

Runs under `pytest tests/ -q` (no venv in a cut build worktree).
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
HOME = ROOT / "tools" / "board_plumbing.py"

# the two named surfaces
PROD_FILES = sorted(ROOT.glob("tools/*.py")) + sorted(ROOT.glob("tools/*.sh"))
TEST_FILES = sorted(ROOT.glob("tests/*.py"))
SURFACE = PROD_FILES + TEST_FILES

# a PVT-prefixed board id default, as it is declared in the home: os.environ.get("<NAME>", "<PVT…>").
# Both the env-var NAME and its literal are read out of the home here — the guard restates neither.
_PAIR_RE = re.compile(r'os\.environ\.get\(\s*"([A-Z_]+)"\s*,\s*"(PVT(?:SSF)?_[A-Za-z0-9]+)"\s*\)')


def _prefixed_pairs():
    """(env-var name, literal) for every PVT-prefixed identifier, read from the home's declarations."""
    return _PAIR_RE.findall(HOME.read_text(encoding="utf-8"))


def _homes_of(name, literal):
    """Every (file, lineno) whose line pairs `name` (uppercase env-var name) with `literal` — the
    declaration shape. Scans both named surfaces."""
    hits = []
    for f in SURFACE:
        for i, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if name in line and literal in line:
                hits.append((f, i))
    return hits


# ---------------------------------------------------------------------------
# The surface exists — a guard that reads a vanished/renamed home reports "one home" forever while
# guarding nothing. Pin that the home is real and actually declares the prefixed identifiers.
# ---------------------------------------------------------------------------

def test_the_named_home_surface_exists_and_declares_the_prefixed_identifiers():
    assert HOME.is_file(), f"the guarded home does not exist: {HOME}"
    pairs = _prefixed_pairs()
    names = {n for n, _ in pairs}
    assert names == {"PROJECT_ID", "STATUS_FIELD_ID", "REASON_FIELD_ID"}, (
        "tools/board_plumbing.py no longer declares exactly the three PVT-prefixed board identifiers via "
        f"os.environ.get(\"<NAME>\", \"PVT…\") — the guard's derived pair set drifted to {sorted(names)}"
    )


# ---------------------------------------------------------------------------
# THE wall-11 guard — each PVT-prefixed board identifier literal has exactly one home, and it is the same
# single file. Reads production and tests both; derives the home from the tree.
# ---------------------------------------------------------------------------

def test_each_prefixed_board_identifier_literal_has_exactly_one_home():
    pairs = _prefixed_pairs()
    assert pairs, "no PVT-prefixed identifier declarations found in the home — cannot run the guard"
    offenders = {}
    for name, literal in pairs:
        homes = _homes_of(name, literal)
        if len(homes) != 1:
            offenders[name] = [f"{f.relative_to(ROOT)}:{i}" for f, i in homes]
    assert not offenders, (
        "a board identifier literal is homed in more than one place across the named surfaces "
        "(tools/*.py, tools/*.sh, tests/*.py) — a declaration line pairs the identifier's uppercase "
        "env-var name with its literal value. Every board identifier must live in exactly one home "
        f"(tools/board_plumbing.py). Offending identifiers and their homes: {offenders}"
    )


def test_the_single_home_is_one_file_derived_from_the_tree():
    """Not just 'exactly one home each' but 'the SAME one file for all of them' — the home is derived as
    the single file the declarations resolve to, never enumerated."""
    pairs = _prefixed_pairs()
    home_files = set()
    for name, literal in pairs:
        for f, _ in _homes_of(name, literal):
            home_files.add(f)
    assert len(home_files) == 1, (
        f"the PVT-prefixed board identifiers are declared across {len(home_files)} files "
        f"{sorted(str(f.relative_to(ROOT)) for f in home_files)}, not one shared home"
    )
    home = home_files.pop()
    assert home == HOME, f"the derived home is {home}, expected tools/board_plumbing.py"
    text = home.read_text(encoding="utf-8")
    # the derived home is a real module owning the two operations, not merely a place the literals sit
    assert "def set_field(" in text, "the derived home does not define the field write set_field"
    assert "def select_project_item(" in text, "the derived home does not define the selection rule"


# ---------------------------------------------------------------------------
# The behaviour-pin suite is left standing — its observed-value assertions are NOT homes, so this slice's
# constraint ("do not modify the pin suite") and the guard coexist.
# ---------------------------------------------------------------------------

def test_the_behaviour_pin_suite_is_not_mistaken_for_a_second_home():
    pins = ROOT / "tests" / "test_board_plumbing_pins.py"
    assert pins.is_file(), "the preceding slice's pin suite is missing"
    pins_text = pins.read_text(encoding="utf-8")
    # the pin suite legitimately asserts observed literal values (e.g. against a gh --project-id flag);
    # the guard must not count those, or the immovable pin suite would make the guard unsatisfiable.
    assert "PVT_kwDOEEAo0M4Ba6Ls" in pins_text, (
        "the pin suite no longer asserts the project-id value as observed behaviour — this test's premise "
        "(that a behaviour pin is not a home) is now vacuous and should be revisited"
    )
    for name, literal in _prefixed_pairs():
        for f, _ in _homes_of(name, literal):
            assert f != pins, (
                "a line in the pin suite pairs an identifier's env-var name with its literal — that is a "
                "declaration shape the guard counts as a home, and the pin suite must not be one"
            )


# ---------------------------------------------------------------------------
# The recorded impossibility for the option-id half (scoped to that half only).
# ---------------------------------------------------------------------------

def test_the_option_id_impossibility_is_recorded_at_the_home():
    doc = HOME.read_text(encoding="utf-8")
    lowered = doc.lower()
    assert "option-id" in lowered or "option id" in lowered, (
        "tools/board_plumbing.py does not record the option-id half at all — a recorded impossibility is "
        "a finding; silence is not"
    )
    assert "hexadecimal" in lowered, (
        "the home's option-id record does not name WHY no guard is expressible (bare hexadecimal tokens "
        "colliding with short commit hashes)"
    )
    assert "commit hash" in lowered, (
        "the home's option-id record does not name the collision hazard (short commit hashes)"
    )
    # what would have to be true for a guard to exist
    assert "prefix" in lowered and "registry" in lowered, (
        "the home's option-id record does not state what would have to be true for a guard to exist "
        "(a distinguishing prefix, or a declared registry the tree could diff against)"
    )


def test_the_impossibility_is_scoped_to_the_option_id_half_only():
    """The escape hatch covers the option-id half; the prefixed half is guarded, not excused. Prove the
    guard actually enforces the prefixed half rather than declaring it impossible too."""
    pairs = _prefixed_pairs()
    assert {n for n, _ in pairs} == {"PROJECT_ID", "STATUS_FIELD_ID", "REASON_FIELD_ID"}, (
        "the prefixed identifiers the guard must enforce are not all present — the impossibility must be "
        "scoped to the option-id half ONLY, never widened to a prefixed identifier"
    )


# ---------------------------------------------------------------------------
# The home is named in AGENTS.md's ## Repo map table.
# ---------------------------------------------------------------------------

def test_the_home_is_named_in_the_agents_md_repo_map_table():
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    start = agents.find("## Repo map")
    assert start != -1, "AGENTS.md has no '## Repo map' section"
    end = agents.find("\n## ", start + 1)
    section = agents[start: end if end != -1 else len(agents)]
    row = next((l for l in section.splitlines()
                if l.lstrip().startswith("|") and "`tools/board_plumbing.py`" in l), None)
    assert row is not None, (
        "AGENTS.md's ## Repo map table has no row naming `tools/board_plumbing.py` — the new home must be "
        "named there (issue #388)"
    )
    assert row.count("|") >= 3, "the board_plumbing.py repo-map row is not a two-column table row"
    _, _, what = row.split("|", 2)
    assert what.strip().strip("|").strip(), "the board_plumbing.py repo-map row has an empty description"
