"""Tests for issue #466 slice B — tools/design_resolver.py folds its own ad hoc frontmatter regex
onto `tools.textutil.split_frontmatter`, the one parser.

Derived from the issue's acceptance criteria (the spec), not from design_resolver's internals: the
fold is byte-identical for the two fail tokens (`design_status_unreadable`, `design_not_active`) —
covered by the untouched `tests/test_epic_flip.py` — but reading through the shared parser also
means the resolver now benefits from that parser's richer (still declared-subset) value handling:
a quoted status value and a trailing inline comment on the status line, which a bare
`^status:\\s*(\\S+)` regex would have read wrong or missed.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import design_resolver  # noqa: E402

SOURCE_LINE = "**Source:** product-spec [[04 projects/factory/iterations/9-x/01-x]] (Obsidian design brain)"


def _doc(tmp_path, frontmatter_lines, body="body\n"):
    doc = tmp_path / "04 projects" / "factory" / "iterations" / "9-x" / "01-x.md"
    doc.parent.mkdir(parents=True, exist_ok=True)
    text = "---\n" + "\n".join(frontmatter_lines) + "\n---\n" + body
    doc.write_text(text, encoding="utf-8")
    return doc


def test_quoted_active_status_is_recognized(tmp_path, monkeypatch):
    monkeypatch.setenv("YR_VAULT_ROOT", str(tmp_path))
    _doc(tmp_path, ['status: "active"'])
    assert design_resolver.check_body(SOURCE_LINE) == (0, "")


def test_status_with_trailing_inline_comment_is_recognized(tmp_path, monkeypatch):
    monkeypatch.setenv("YR_VAULT_ROOT", str(tmp_path))
    _doc(tmp_path, ["status: active   # draft | active | retired"])
    assert design_resolver.check_body(SOURCE_LINE) == (0, "")


def test_status_with_crlf_line_endings_is_still_readable(tmp_path, monkeypatch):
    monkeypatch.setenv("YR_VAULT_ROOT", str(tmp_path))
    doc = tmp_path / "04 projects" / "factory" / "iterations" / "9-x" / "01-x.md"
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_bytes(b"---\r\nstatus: active\r\n---\r\nbody\r\n")
    assert design_resolver.check_body(SOURCE_LINE) == (0, "")


def test_fail_tokens_unchanged_no_frontmatter(tmp_path, monkeypatch):
    monkeypatch.setenv("YR_VAULT_ROOT", str(tmp_path))
    doc = tmp_path / "04 projects" / "factory" / "iterations" / "9-x" / "01-x.md"
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text("no frontmatter at all\n", encoding="utf-8")
    assert design_resolver.check_body(SOURCE_LINE) == (1, "design_status_unreadable")


def test_fail_tokens_unchanged_inactive_status(tmp_path, monkeypatch):
    monkeypatch.setenv("YR_VAULT_ROOT", str(tmp_path))
    _doc(tmp_path, ["status: draft"])
    assert design_resolver.check_body(SOURCE_LINE) == (1, "design_not_active")
