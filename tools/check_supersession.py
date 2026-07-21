#!/usr/bin/env python3
"""check_supersession — fail loud on a broken supersession declaration, pair, or down-flow disposition.

A sibling of `check_links` / `check_task`: the same fail-loud principle, applied to the vault's
`supersedes` / `superseded_by` edges instead of `source_*` crossing-links.

Two modes:

**Draft mode** (`<draft.md> [--vault-root DIR]`) checks one artifact before it crosses into the vault
proper. A `product-spec` / `feature-rfc` draft must carry a `supersedes` key: missing is an error; a
value that doesn't parse as a list is an error; an empty list is only allowed with a body line matching
`**Supersedes:** nothing <justification>`. Every declared target must resolve with the same wikilink
semantics as `check_links._resolve_wikilink` (explicit vault-relative path, or a unique basename —
dot-dirs excluded); an unresolved/ambiguous, already-superseded, or non-`active` target is an error — except
a target that is itself an ideas-folder note (vault-relative path with an `ideas/` segment), whose
legitimate pre-accept status is `open` instead of `active`; a `rejected` or already-`superseded` ideas
target still errors exactly as any other non-conformant target. When
a target is a `product-spec`, every *active* spine doc (the four spine types) whose `source_spec`
resolves to it must be named in the draft's own declaration or cited as a `[[wikilink]]` in the draft's
body — an undispositioned child is an error, and a child this check cannot classify (alien type/status,
no frontmatter) is an error too, never silently skipped. Any other draft type passes outright, with
`supersedes`/`superseded_by` grammar-checked only if present (no presence/resolution requirement).

**Sweep mode** (`--sweep --scope REL [--vault-root DIR]`) audits the governed vault space instead of
one draft. `--scope` is required — a scope-less `--sweep` exits 1 naming every component root (a directory
with its own `iterations/` child) visible anywhere under `--vault-root`, instead of silently falling back
to some pinned default; a sweep can no longer green-light space it did not scan. The governed space is
enumerated by a pinned rule: every component directory directly under `--scope` that has an `iterations/`
child contributes that subtree plus every non-hidden sibling directory (dot-dirs excluded, underscore dirs
included — legacy zoos included whole, aggregated). When `--scope` itself has an `iterations/` child — a
component-rooted scope, e.g. a single-project root — the scope sweeps as that one component instead, named
by the scope's own basename, picking up its root-level docs too. When `--scope` is parent-shaped instead
(no `iterations/` child of its own), the parent tier joins the sweep as one more component, also named by
the scope's own basename: it covers the parent root's own loose docs (the org tier's `brand/`/`strategy/`
notes) and every non-component child (no `iterations/` child of its own) except `archive/`, which stays
excluded by folder name — the sweep still prints that one skip line so the exclusion stays visible rather
than silent. Every doc in the scanned space is classified: legacy (alien type, alien
status, or no
parseable frontmatter — aggregated per folder, never itemized) or conformant (alien frontmatter keys
surfaced as one observation line per key, never blocking). An ideas-folder note (vault-relative path with
an `ideas/` segment) runs the ideas-backlog contract instead of the spine one for this classification:
`open`/`rejected`/`superseded` are its known statuses (`draft` is alien status there, by design — no
transitional tolerance), and `summary`/`value`/`effort` join its closed keys, so they never surface as
alien-key observations. Pair integrity runs both directions — forward
from a `supersedes` declaration to its target, and backward from a `superseded` doc to its `superseded_by`
replacer. An ideas-folder note may close its backward pair with `crossed_to: owner/repo#N` instead of
`superseded_by` (the task-delivered arm, ruled 2026-07-21): well-formed completes the pair, malformed is a
hard finding, neither key stays the standing advisory. Findings split into **hard** (exit 1) — anything reachable from a `supersedes` declaration
(unresolved/not-yet-superseded target, missing/wrong back-pointer, an unjustified empty declaration,
down-flow incompleteness under a doc that itself declares `supersedes`) plus any indeterminate
(unclassifiable) case anywhere — and **advisory** (exit 0) — a `superseded_by` replacer that carries no
`supersedes` key at all (a pre-grammar pairing, predating this convention), a superseded doc with no
`superseded_by`, down-flow gaps under such a pre-grammar replacer, a spine-typed doc sitting inside a
governed cross-cutting home instead of an iteration, and every active doc whose any `source_*` resolves
to a superseded doc (the pair-adjacent signal). A census headline — the scope scanned, total docs,
spine-active per component (the four spine types, status exactly `active`, counted inside `iterations/`
subtrees), legacy count — always prints, computed under the same pinned rule the sweep scopes by.

This is an attended-session check like its siblings: advisory-first, wired into nothing.

Usage: check_supersession.py <draft.md> [--vault-root DIR]
       check_supersession.py --sweep --scope REL [--vault-root DIR]
Exit 0 clean; 1 (with `<file>: <message>` lines) on any hard finding.
"""
import argparse
import os
import pathlib
import re
import sys
from collections import namedtuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from tools.check_links import _resolve_wikilink
from tools.textutil import split_frontmatter

DEFAULT_VAULT = os.environ.get("OBSIDIAN_VAULT", "/srv/obsidian/vaults/obsidian")

SPINE_TYPES = ("product-spec", "feature-rfc", "technical-rfc", "task")
SUPPORTING_TYPES = ("research", "note", "runbook")
KNOWN_TYPES = set(SPINE_TYPES) | set(SUPPORTING_TYPES)
KNOWN_STATUSES = {"draft", "active", "rejected", "superseded"}
REQUIRES_SUPERSEDES = {"product-spec", "feature-rfc"}
CLOSED_KEYS = {
    "type", "status", "created", "updated",
    "source_spec", "source_feature_rfc", "source_technical_rfc",
    "crossed_to", "superseded_by", "retired_reason", "supersedes",
}

# An ideas-folder note (vault-relative path with an `ideas/` directory segment) runs the
# ideas-backlog contract instead of the spine one: `open` replaces `draft`/`active` as its pending
# status (no `draft` tolerance — a draft idea is alien status by design), and its scoring keys join
# the closed set.
IDEAS_STATUSES = {"open", "rejected", "superseded"}
IDEAS_EXTRA_CLOSED_KEYS = {"summary", "value", "effort"}

_NOTHING_RE = re.compile(r"^\*\*Supersedes:\*\*\s*nothing\b(.*)$", re.IGNORECASE)
_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
# The task-delivered arm's ref grammar (ideas-notes only, ruled 2026-07-21): the task Issue as
# `owner/repo#N` — the same shape `crossed_to` carries on a spec that crossed to an epic.
_CROSSED_TO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#\d+$")

DocRecord = namedtuple("DocRecord", "path rel meta body legacy_reason")


# --- shared primitives (frontmatter classification, wikilink resolution) --------------------------

def _legacy_reason(meta, is_ideas=False):
    """Why a doc is legacy-class (alien type / alien status / unparseable) — None if conformant.
    `is_ideas` swaps in the ideas-folder status vocabulary in place of the spine one; the type
    vocabulary is shared either way (the discriminator is the path, never the type)."""
    if not meta:
        return "no parseable frontmatter"
    t = meta.get("type")
    if not isinstance(t, str) or t not in KNOWN_TYPES:
        return "alien type"
    s = meta.get("status")
    statuses = IDEAS_STATUSES if is_ideas else KNOWN_STATUSES
    if not isinstance(s, str) or s not in statuses:
        return "alien status"
    return None


def _is_ideas_note(path, vault_root):
    """True if `path`'s vault-relative directory chain has an `ideas` segment."""
    try:
        rel_parts = path.resolve().relative_to(vault_root.resolve()).parts
    except ValueError:
        rel_parts = path.resolve().parts
    return "ideas" in rel_parts[:-1]


def _closed_keys_for(path, vault_root):
    if _is_ideas_note(path, vault_root):
        return CLOSED_KEYS | IDEAS_EXTRA_CLOSED_KEYS
    return CLOSED_KEYS


def _wikilink_target(value):
    """Strip an optional `[[...]]` wrapper; `_resolve_wikilink` handles any `#heading|alias` left."""
    v = (value or "").strip()
    if v.startswith("[[") and v.endswith("]]"):
        v = v[2:-2]
    return v.strip()


def _resolve_target(value, vault_root):
    target = _wikilink_target(value)
    if not target:
        return False, "empty target"
    return _resolve_wikilink(target, vault_root)


def _has_nothing_justification(body):
    for line in body.split("\n"):
        m = _NOTHING_RE.match(line.strip())
        if m and re.search(r"\w", m.group(1)):
            return True
    return False


def _body_wikilink_targets(body, vault_root):
    """Resolved absolute paths of every `[[wikilink]]` cited in a body — unresolved ones are ignored."""
    resolved = set()
    for m in _WIKILINK_RE.finditer(body):
        ok, detail = _resolve_wikilink(m.group(1), vault_root)
        if ok:
            resolved.add(pathlib.Path(detail).resolve())
    return resolved


def _disposed_paths(meta, body, vault_root):
    """Every target a doc has already dispositioned — its own `supersedes` list plus its body citations."""
    disposed = set()
    sup = meta.get("supersedes")
    if isinstance(sup, list):
        for raw in sup:
            ok, detail = _resolve_wikilink(_wikilink_target(raw), vault_root)
            if ok:
                disposed.add(pathlib.Path(detail).resolve())
    disposed |= _body_wikilink_targets(body, vault_root)
    return disposed


def _walk_md(root):
    for p in sorted(root.rglob("*.md")):
        rel = p.relative_to(root)
        if any(part.startswith(".") for part in rel.parts):
            continue
        yield p


def _downflow_findings(spec_path, disposed_paths, vault_root):
    """(gaps, indeterminate) — undispositioned active-spine children of `spec_path`, and children whose
    own frontmatter this check cannot classify (always fail-loud, regardless of caller context)."""
    spec_resolved = spec_path.resolve()
    gaps, indeterminate = [], []
    for p in _walk_md(vault_root):
        p_resolved = p.resolve()
        if p_resolved == spec_resolved:
            continue
        meta, _ = split_frontmatter(p.read_text(encoding="utf-8", errors="replace"))
        sv = meta.get("source_spec")
        if not isinstance(sv, str) or not sv.strip():
            continue
        ok, detail = _resolve_wikilink(_wikilink_target(sv), vault_root)
        if not ok or pathlib.Path(detail).resolve() != spec_resolved:
            continue
        reason = _legacy_reason(meta)
        if reason:
            indeterminate.append(str(p))
            continue
        if meta.get("type") not in SPINE_TYPES or meta.get("status") != "active":
            continue
        if p_resolved not in disposed_paths:
            gaps.append(str(p))
    return gaps, indeterminate


# --- draft mode -------------------------------------------------------------------------------------

def _grammar_check_pair_keys(meta):
    errors = []
    if "supersedes" in meta:
        value = meta["supersedes"]
        if not isinstance(value, list) and value != "":
            errors.append(f"`supersedes` does not parse as a list (found {value!r})")
    if "superseded_by" in meta:
        value = meta["superseded_by"]
        if not isinstance(value, str) or not value.strip():
            errors.append("`superseded_by` must be a non-empty value")
    return errors


def _check_supersedes_required(meta, body, vault_root):
    if "supersedes" not in meta:
        return ["missing `supersedes` key — a product-spec/feature-rfc draft must declare what it "
                "supersedes (or 'nothing', justified in the body)"]
    value = meta["supersedes"]
    if isinstance(value, list):
        targets = value
    elif value == "":
        targets = []
    else:
        return [f"`supersedes` does not parse as a list (found {value!r})"]

    if not targets:
        if _has_nothing_justification(body):
            return []
        return ["`supersedes` is empty but no body line '**Supersedes:** nothing — <justification>' "
                "is present"]

    errors = []
    product_spec_targets = []
    for raw in targets:
        target_str = _wikilink_target(raw)
        ok, detail = _resolve_wikilink(target_str, vault_root)
        if not ok:
            errors.append(f"supersedes target {raw!r} unresolved — {detail}")
            continue
        target_path = pathlib.Path(detail)
        t_meta, _ = split_frontmatter(target_path.read_text(encoding="utf-8", errors="replace"))
        is_ideas = _is_ideas_note(target_path, vault_root)
        reason = _legacy_reason(t_meta, is_ideas)
        if reason:
            errors.append(f"supersedes target {raw!r} is indeterminate ({reason}) — cannot verify status")
            continue
        status = t_meta.get("status")
        if status == "superseded":
            replacer = t_meta.get("superseded_by", "<unspecified>")
            errors.append(f"supersedes target {raw!r} is already superseded — see {replacer!r}")
            continue
        # An ideas-folder target's legitimate pre-accept state is `open` (its pending status); every
        # other target still expects the spine's `active`.
        expected_status = "open" if is_ideas else "active"
        if status != expected_status:
            errors.append(f"supersedes target {raw!r} has status {status!r}, expected {expected_status!r}")
            continue
        if t_meta.get("type") == "product-spec":
            product_spec_targets.append(target_path)

    if product_spec_targets:
        disposed = _disposed_paths(meta, body, vault_root)
        for target_path in product_spec_targets:
            gaps, indeterminate = _downflow_findings(target_path, disposed, vault_root)
            for g in gaps:
                errors.append(f"undispositioned child of {target_path.name}: {g} — name it in the "
                              f"declaration or cite it in the body")
            for g in indeterminate:
                errors.append(f"indeterminate child of {target_path.name} (cannot classify): {g}")
    return errors


def check_draft(text, *, vault_root):
    """Return error messages (list[str]) for one draft artifact; [] ⇒ clean."""
    meta, body = split_frontmatter(text)
    doc_type = meta.get("type", "")
    if doc_type in REQUIRES_SUPERSEDES:
        return _check_supersedes_required(meta, body, vault_root)
    return _grammar_check_pair_keys(meta)


# --- sweep mode -------------------------------------------------------------------------------------

def _component_dirs(comp_dir):
    """[dirs...] for one component root: its `iterations/` child plus every non-hidden sibling
    directory (dot-dirs excluded, underscore dirs included)."""
    dirs = [comp_dir / "iterations"]
    for sib in sorted(p for p in comp_dir.iterdir()
                       if p.is_dir() and not p.name.startswith(".") and p.name != "iterations"):
        dirs.append(sib)
    return dirs


def _governed_components(vault_root, scope):
    """[(component_name, [dirs...], [root_docs...])] — every component under scope, scanned.
    A component-rooted scope (its own `iterations/` child) sweeps as that one component, named
    by the scope's basename, `root_docs` holding its own loose root `*.md` files. A parent-shaped
    scope (no `iterations/` child of its own) sweeps as: every child component with its own
    `iterations/` child, PLUS the parent tier itself as one more component — named by the scope's
    basename — covering every non-iteration child except `archive/` (which stays excluded by
    folder name, reported by `_parent_skip_lines` instead) and the parent root's own loose `*.md`
    files."""
    scope_dir = vault_root / scope
    if not scope_dir.is_dir():
        return []

    if (scope_dir / "iterations").is_dir():
        root_docs = sorted(p for p in scope_dir.glob("*.md") if not p.name.startswith("."))
        return [(scope_dir.name, _component_dirs(scope_dir), root_docs)]

    components = []
    parent_dirs = []
    for comp in sorted(p for p in scope_dir.iterdir() if p.is_dir() and not p.name.startswith(".")):
        if (comp / "iterations").is_dir():
            components.append((comp.name, _component_dirs(comp), []))
        elif comp.name != "archive":
            parent_dirs.append(comp)

    parent_root_docs = sorted(p for p in scope_dir.glob("*.md") if not p.name.startswith("."))
    components.append((scope_dir.name, parent_dirs, parent_root_docs))
    return components


def _parent_skip_lines(scope_dir, scope):
    """Skip-report lines for a parent-shaped scope — named, never scanned: only `archive/`, excluded
    by folder name. Every other non-component subtree and the parent root's own loose docs now scan
    as the parent tier's own component (`_governed_components`), so this narrows to that one line."""
    lines = []
    if (scope_dir / "archive").is_dir():
        lines.append(f"skip: {scope} — non-component subtree(s) with no iterations/, excluded: archive")
    return lines


def _visible_component_roots(vault_root):
    """Every directory anywhere under vault_root (dot-dirs excluded) that itself has an `iterations/`
    child — every scope a sweep could be pointed at directly. Used only to name what's visible when
    `--sweep` is invoked without `--scope`; a sweep itself never walks the whole vault."""
    roots = []

    def _walk(d):
        for p in sorted(d.iterdir()):
            if not p.is_dir() or p.name.startswith("."):
                continue
            if (p / "iterations").is_dir():
                roots.append(str(p.relative_to(vault_root)))
            else:
                _walk(p)

    if vault_root.is_dir():
        _walk(vault_root)
    return sorted(roots)


def _sweep_docs(vault_root, scope):
    """(docs, component_of, in_iterations) across the governed space, keyed by resolved absolute path."""
    docs, component_of, in_iterations = [], {}, {}

    def _record(p, name, is_iter):
        text = p.read_text(encoding="utf-8", errors="replace")
        meta, body = split_frontmatter(text)
        rec = DocRecord(path=p, rel=str(p.relative_to(vault_root)), meta=meta, body=body,
                         legacy_reason=_legacy_reason(meta, _is_ideas_note(p, vault_root)))
        docs.append(rec)
        resolved = p.resolve()
        component_of[resolved] = name
        in_iterations[resolved] = is_iter

    for name, dirs, root_docs in _governed_components(vault_root, scope):
        for d in dirs:
            is_iter = d.name == "iterations"
            for p in _walk_md(d):
                _record(p, name, is_iter)
        for p in root_docs:
            _record(p, name, False)
    return docs, component_of, in_iterations


def _census(docs, component_of, in_iterations):
    total = len(docs)
    legacy = sum(1 for d in docs if d.legacy_reason)
    spine_active = {}
    for d in docs:
        resolved = d.path.resolve()
        if d.legacy_reason or not in_iterations.get(resolved):
            continue
        if d.meta.get("type") in SPINE_TYPES and d.meta.get("status") == "active":
            comp = component_of.get(resolved, "?")
            spine_active[comp] = spine_active.get(comp, 0) + 1
    return total, spine_active, legacy


def _format_census(scope, total, spine_active, legacy):
    comp_str = ", ".join(f"{k} {v}" for k, v in sorted(spine_active.items()))
    spine_total = sum(spine_active.values())
    return (f"census [{scope}]: {total} docs / {spine_total} spine-active ({comp_str}) / "
            f"{legacy} legacy")


def _lookup(index, resolved_path, vault_root):
    """A DocRecord for `resolved_path` — from the governed index if present, else loaded fresh (a
    target outside the sweep scope but still a real vault file)."""
    rec = index.get(resolved_path)
    if rec is not None:
        return rec
    text = resolved_path.read_text(encoding="utf-8", errors="replace")
    meta, body = split_frontmatter(text)
    return DocRecord(path=resolved_path, rel=str(resolved_path), meta=meta, body=body,
                      legacy_reason=_legacy_reason(meta, _is_ideas_note(resolved_path, vault_root)))


def _points_back(back_value, replacer_path, vault_root):
    if not back_value:
        return False
    replacer_resolved = replacer_path.resolve()
    for v in (back_value if isinstance(back_value, list) else [back_value]):
        ok, detail = _resolve_target(v, vault_root)
        if ok and pathlib.Path(detail).resolve() == replacer_resolved:
            return True
    return False


def _resolved_supersedes_targets(meta, vault_root):
    targets = meta.get("supersedes")
    resolved = set()
    if isinstance(targets, list):
        for raw in targets:
            ok, detail = _resolve_wikilink(_wikilink_target(raw), vault_root)
            if ok:
                resolved.add(pathlib.Path(detail).resolve())
    return resolved


def _pair_forward_errors(d, raw, index, vault_root):
    """Hard findings reachable from one `supersedes` target of a declaring doc `d`."""
    target_str = _wikilink_target(raw)
    ok, detail = _resolve_wikilink(target_str, vault_root)
    if not ok:
        return [f"{d.rel}: supersedes target {raw!r} unresolved — {detail}"]
    target_path = pathlib.Path(detail)
    target = _lookup(index, target_path.resolve(), vault_root)
    if target.legacy_reason:
        return [f"{d.rel}: supersedes target {raw!r} is indeterminate ({target.legacy_reason})"]

    # The pairing only comes fully into effect once the declaring doc itself is accepted (`active`) —
    # a still-`draft` declaration is legitimate WIP, its target rightly still `active` too.
    if d.meta.get("status") != "active":
        return []

    errors = []
    if target.meta.get("status") != "superseded":
        return [f"{d.rel}: supersedes target {raw!r} is not marked superseded "
                f"(status={target.meta.get('status')!r})"]

    if not _points_back(target.meta.get("superseded_by"), d.path, vault_root):
        errors.append(f"{d.rel}: supersedes target {raw!r} ({target.rel}) has a missing/wrong "
                      f"superseded_by back-pointer")

    if target.meta.get("type") == "product-spec":
        disposed = _disposed_paths(d.meta, d.body, vault_root)
        gaps, indeterminate = _downflow_findings(target.path, disposed, vault_root)
        for g in gaps:
            errors.append(f"{d.rel}: undispositioned child of {target.rel}: {g}")
        for g in indeterminate:
            errors.append(f"{d.rel}: indeterminate child of {target.rel} (cannot classify): {g}")
    return errors


def _pair_backward_findings(d, index, vault_root):
    """(hard, advisory) findings reachable backward from one already-`superseded` doc `d`."""
    back = d.meta.get("superseded_by")
    if not back:
        # The task-delivered arm (ideas-notes only, ruled 2026-07-21): a seed whose intent shipped
        # through a standalone task pairs via `crossed_to: owner/repo#N` — the task Issue — instead
        # of a vault-side `superseded_by`. Well-formed completes the pair; malformed is hard (a ref
        # that cannot be read is a defect, never an executed lifecycle); absent stays the standing
        # advisory it always was.
        if _is_ideas_note(d.path, vault_root):
            crossed = d.meta.get("crossed_to")
            if crossed is not None:
                if isinstance(crossed, str) and _CROSSED_TO_RE.match(crossed.strip()):
                    return [], []
                return [f"{d.rel}: superseded with malformed crossed_to {crossed!r} — "
                        f"expected owner/repo#N"], []
        return [], [f"{d.rel}: superseded with no superseded_by"]
    ok, detail = _resolve_target(back, vault_root)
    if not ok:
        return [], [f"{d.rel}: superseded_by target unresolved — {detail}"]
    replacer = _lookup(index, pathlib.Path(detail).resolve(), vault_root)
    if replacer.legacy_reason:
        return [], [f"{d.rel}: superseded_by replacer {replacer.rel} is indeterminate "
                    f"({replacer.legacy_reason})"]

    if "supersedes" not in replacer.meta:
        advisory = [f"{d.rel}: superseded_by {replacer.rel}, which carries no supersedes key "
                    f"(pre-grammar pairing)"]
        hard = []
        if d.meta.get("type") == "product-spec":
            disposed = _disposed_paths(replacer.meta, replacer.body, vault_root)
            gaps, indeterminate = _downflow_findings(d.path, disposed, vault_root)
            for g in gaps:
                advisory.append(f"{d.rel}: down-flow gap under pre-grammar replacer {replacer.rel}: {g}")
            for g in indeterminate:
                hard.append(f"{d.rel}: indeterminate child (cannot classify) under pre-grammar "
                            f"replacer {replacer.rel}: {g}")
        return hard, advisory

    resolved_r_targets = _resolved_supersedes_targets(replacer.meta, vault_root)
    if d.path.resolve() not in resolved_r_targets:
        return [f"{d.rel}: superseded_by {replacer.rel} does not declare supersedes back to this doc"], []
    return [], []


def _pair_adjacent_advisory(docs, index, vault_root):
    """Every active doc whose any source_* resolves to a superseded doc."""
    advisory = []
    for d in docs:
        if d.legacy_reason or d.meta.get("status") != "active":
            continue
        for key, value in d.meta.items():
            if not key.startswith("source_"):
                continue
            for v in (value if isinstance(value, list) else [value]):
                ok, detail = _resolve_target(v, vault_root)
                if not ok:
                    continue
                target = _lookup(index, pathlib.Path(detail).resolve(), vault_root)
                if not target.legacy_reason and target.meta.get("status") == "superseded":
                    advisory.append(f"{d.rel}: {key} resolves to superseded doc {target.rel}")
    return advisory


def _spine_in_home_advisory(docs, in_iterations):
    advisory = []
    for d in docs:
        if d.legacy_reason:
            continue
        if not in_iterations.get(d.path.resolve(), False) and d.meta.get("type") in SPINE_TYPES:
            advisory.append(f"{d.rel}: spine-typed doc ({d.meta.get('type')}) sits inside a governed "
                            f"home, not an iteration")
    return advisory


def _legacy_aggregate(docs, vault_root):
    by_folder = {}
    for d in docs:
        if not d.legacy_reason:
            continue
        folder = str(d.path.parent.relative_to(vault_root))
        by_folder[folder] = by_folder.get(folder, 0) + 1
    return [f"legacy: {folder}: {n} doc(s)" for folder, n in sorted(by_folder.items())]


def _alien_key_observations(docs, vault_root):
    counts = {}
    for d in docs:
        if d.legacy_reason:
            continue
        closed = _closed_keys_for(d.path, vault_root)
        for k in d.meta:
            if k not in closed:
                counts[k] = counts.get(k, 0) + 1
    return [f"observation: alien frontmatter key {k!r} present on {n} conformant doc(s)"
            for k, n in sorted(counts.items())]


def check_sweep(*, vault_root, scope):
    """(lines, failed) — lines to print (census headline first), failed ⇒ any hard finding."""
    docs, component_of, in_iterations = _sweep_docs(vault_root, scope)
    index = {d.path.resolve(): d for d in docs}

    hard, advisory = [], []
    for d in docs:
        if d.legacy_reason:
            continue
        supersedes = d.meta.get("supersedes")
        if supersedes is None:
            continue
        if not isinstance(supersedes, list):
            hard.append(f"{d.rel}: supersedes does not parse as a list (found {supersedes!r})")
            continue
        if not supersedes:
            if not _has_nothing_justification(d.body):
                hard.append(f"{d.rel}: supersedes is empty with no body justification "
                            f"('**Supersedes:** nothing — <justification>')")
            continue
        for raw in supersedes:
            hard.extend(_pair_forward_errors(d, raw, index, vault_root))

    for d in docs:
        if d.legacy_reason or d.meta.get("status") != "superseded":
            continue
        h, a = _pair_backward_findings(d, index, vault_root)
        hard.extend(h)
        advisory.extend(a)

    advisory.extend(_pair_adjacent_advisory(docs, index, vault_root))
    advisory.extend(_spine_in_home_advisory(docs, in_iterations))

    legacy_lines = _legacy_aggregate(docs, vault_root)
    observations = _alien_key_observations(docs, vault_root)
    total, spine_active, legacy = _census(docs, component_of, in_iterations)

    lines = [_format_census(scope, total, spine_active, legacy)]
    scope_dir = vault_root / scope
    if scope_dir.is_dir() and not (scope_dir / "iterations").is_dir():
        lines += _parent_skip_lines(scope_dir, scope)
    lines += legacy_lines
    lines += observations
    lines += [f"advisory: {a}" for a in advisory]
    lines += [f"error: {h}" for h in hard]
    return lines, bool(hard)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Verify supersession declarations, pair integrity, and down-flow disposition.")
    ap.add_argument("file", nargs="?", help="a draft product-spec/feature-rfc (or other doc) to check")
    ap.add_argument("--vault-root", default=DEFAULT_VAULT, help="Obsidian vault root")
    ap.add_argument("--sweep", action="store_true",
                    help="sweep the governed vault space instead of checking one draft")
    ap.add_argument("--scope", default=None,
                    help="sweep scope, vault-relative — required for --sweep, no implicit default")
    args = ap.parse_args(argv)
    vault_root = pathlib.Path(args.vault_root)

    if args.sweep:
        if not args.scope:
            roots = _visible_component_roots(vault_root)
            if roots:
                print("error: --sweep requires --scope — component roots visible under "
                      f"{vault_root}: " + ", ".join(roots))
            else:
                print(f"error: --sweep requires --scope — no component roots (iterations/ child) "
                      f"found under {vault_root}")
            return 1
        lines, failed = check_sweep(vault_root=vault_root, scope=args.scope)
        for line in lines:
            print(line)
        return 1 if failed else 0

    if not args.file:
        ap.error("a draft file is required unless --sweep is given")
    text = pathlib.Path(args.file).read_text(encoding="utf-8")
    errors = check_draft(text, vault_root=vault_root)
    for e in errors:
        print(f"{args.file}: {e}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
