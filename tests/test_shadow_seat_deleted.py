"""Pin for issue #468 (it-36 slice A) — the factory carries no shadow review seat and nothing that
only it fed.

A repository-wide grep, scoped to the surfaces the acceptance criteria names (`tools/`, `records.toml`,
`deploy/`, `tests/`, `skills/` — "the references" — and `AGENTS.md`), for the retired seat's own names:
`YR_SHADOW_MODEL`, `YR_SHADOW_BASE_URL`, `shadow_review_round`, `verdict_diff`, `sweep-diffs`,
`YR-SHADOW-REVIEW`, `YR-VERDICT-DIFF`, `shadow_model`, `SHADOW_ROUNDS`. None of these strings is a
substring of any surviving identifier (`shadow_cost_usd` is the price total; `SHADOW_ORDER`,
`shadow_complete`, `shadow_freshness`, `shadow_terminal_approval`, `shadow_rank_gate`, `shadow_ci`,
`merge-shadow`/`merge_shadow`, and `YR-MERGE-SHADOW` are the merge gate's own shadow PHASE vocabulary —
untouched by this slice) — so a literal-substring scan needs no special-case exclusion logic to avoid
flagging them; they simply never contain a banned pattern.

Derived from the issue's own acceptance criteria, never from the implementation's internals — this
file only greps text, and reads no production module.
"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
THIS_FILE = pathlib.Path(__file__).resolve()

# The retired seat's own names — verbatim from the issue #468 acceptance criteria.
RETIRED_NAMES = [
    "YR_SHADOW_MODEL",
    "YR_SHADOW_BASE_URL",
    "shadow_review_round",
    "verdict_diff",
    "sweep-diffs",
    "YR-SHADOW-REVIEW",
    "YR-VERDICT-DIFF",
    "shadow_model",
    "SHADOW_ROUNDS",
]

# The surfaces the acceptance criteria names: tools/, records.toml, deploy/, tests/, skills/ (the
# references), AGENTS.md. README.md is checked by its own docs-drift suite (test_readme_public_audience
# already pins the seat line's removal) but is included here too since the criteria names it.
SCAN_DIRS = ["tools", "deploy", "tests", "skills"]
SCAN_FILES = ["records.toml", "AGENTS.md", "README.md"]

_SKIP_PARTS = {".git", "__pycache__", ".venv"}


def _scan_targets():
    for d in SCAN_DIRS:
        base = ROOT / d
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            if _SKIP_PARTS & set(path.parts):
                continue
            if path.resolve() == THIS_FILE:
                continue  # this pin's own file necessarily quotes every retired name
            yield path
    for f in SCAN_FILES:
        path = ROOT / f
        if path.exists():
            yield path


def test_no_shadow_review_seat_reference_survives():
    offenders = {}
    for path in _scan_targets():
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        hits = [name for name in RETIRED_NAMES if name in content]
        if hits:
            offenders[str(path.relative_to(ROOT))] = hits
    assert not offenders, (
        "the shadow review seat (or something that only it fed) is still referenced: "
        f"{offenders}"
    )


def test_verdict_diff_module_is_gone():
    assert not (ROOT / "tools" / "verdict_diff.py").exists()


def test_bench_diffs_directory_does_not_exist():
    assert not (ROOT / "bench" / "diffs").exists()
