#!/usr/bin/env python3
"""tools/release.py — the validation-gated, git-native skill release act (it-31 slice 7, ruling 6).

A skill release is a git-native act on the public factory repo: validation runs first — the model
loads at the release commit, server CI is green there, the compiled surfaces carry no drift — and
refuses on any failure; then the act creates an annotated tag `skill/vX.Y.Z` at the commit plus the
GitHub Release object whose body carries the YR-RELEASE record (registry row; fields `version`,
`commit`, `validation`, `who`). Backfill mode types the pre-tool releases retroactively against
their shipped commits (spec callout (d) as ruled: both).

Validation evidence, stated plainly:
  * version_spans_content — the declared version's payload is the whole delivered tree (it-33
    slice 1's canon): the anchor is the BUMP COMMIT, the first first-parent commit since the
    previous tag (full history when none exists) at which plugin.json first declares the version
    — never the previous tag itself. Any tracked path changed between the bump commit and the
    commit under validation refuses; a version whose tree is unchanged since its bump passes.
  * manual_current — the human's manual (docs/manual.md) is current with the two surfaces it
    renders by citation (it-32 slice 5, the manual's ruled update trigger): when the range since
    the previous tag (the whole tracked tree when no earlier tag exists) changed
    skills/factory/SKILL.md or AGENTS.md without touching docs/manual.md, the act refuses unless
    invoked with `--manual-unaffected "<reason>"`; the YR-RELEASE record carries `manual:` either
    way (`updated` · `sources unchanged` · `unaffected — <reason>`).
  * model_loads / no_drift — judged in a detached worktree AT THE COMMIT, by that commit's own
    `tools/process.py` (builds from git refs, never a mutable tree).
  * server_ci_green — CI runs on PR heads, never on main's squash commits, so the evidence chain
    is: release commit -> its squash-source PR (`commits/{sha}/pulls`) -> the PR head's check
    rollup, with TREE EQUALITY (`release^{tree} == head^{tree}`) making the head's green rollup
    certify the release commit's exact tree. The armed merge evaluator's freshness condition is
    what makes the trees equal in practice; this tool VERIFIES it rather than assuming. Never an
    attended full-suite run on the workspace host (owner ruling 2026-08-09).

Contract (mirrors the merge evaluator's): exit 0 pass; exit 1 fail with the failed-condition token
as stdout's first line; any other outcome is UNKNOWN to a caller. Test mode (`--test-mode`) runs
the full validation but writes no live record — no tag, no Release, no trail.

The walls see the act (it-31 slice 7's model amendment): both this funnel and a raw
`gh release create` resolve to the `plugin.release.validated` transition — propose at a one-way
door, so an interactive session is asked and a headless one refused; the evaluator row
`release-validation` delegates to this tool's `validate` subcommand (one implementation, cited).
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPO = "yellow-robots/factory"
TAG_PREFIX = "skill/v"
GH_TIMEOUT = 20
GIT_TIMEOUT = 60
WORKTREE_TIMEOUT = 120

CONDITIONS = ("version_spans_content", "manual_current", "model_loads", "server_ci_green",
              "no_drift")
# The iteration-release family (it-36 slice I, #474) — a SEPARATE tag family beside the skill
# family above, its own conditions, its own CLI verbs (validate-it/ship-it); CONDITIONS/`validate`/
# `ship`/`backfill` above stay byte-identical. `record_body` below is the ONE shared record shape —
# generalized with a third `mode` ("iteration"), never duplicated — since `YR-RELEASE`'s registered
# `fields` (`version`, `commit`, `validation`, `who`, `manual`) are pinned for both families
# (tests/test_release_lane.py::test_registry_row): `version` carries the tag itself ("it/<n>", not
# X.Y.Z — check_trail's field grammar is presence-only, never format-validated), and `manual` is
# always recorded "n/a" (the manual's ruled update trigger is a skill-family-only condition; a
# required, never-defaulted field must still state a fact, so "n/a" is that fact, not a guess).
IT_TAG_PREFIX = "it/"
IT_CONDITIONS = ("epic_closed", "round_record_present", "server_ci_green")
IT_MANUAL_NA = "n/a — an iteration release, not a skill version; the manual's ruled update trigger applies only to the skill family"
MANUAL_PATH = "docs/manual.md"                       # the human's manual (it-32 slice 4)
MANUAL_SOURCES = ("skills/factory/SKILL.md", "AGENTS.md")   # what it renders by citation
_OK_CONCLUSIONS = {"success", "neutral", "skipped"}
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
_TAG_VERSION_RE = re.compile(rf"^{re.escape(TAG_PREFIX)}(\d+)\.(\d+)\.(\d+)$")

# The retroactive pair (spec callout (d) as ruled 2026-08-16: both) — pinned commits, so the
# backfill types exactly the trees that shipped, never a nearby tip.
BACKFILL = {
    "1.0.0": "021cb1400438b87aff9bfc4a6da81d53684e09f9",
    "1.0.1": "cc8624f656a27732eb498fd16ac3cdd987fec78f",
}


def _run(argv: list[str], timeout: int = GIT_TIMEOUT, cwd=None) -> tuple[int, str, str]:
    """The ONLY subprocess seam — stubbed whole in tests."""
    try:
        out = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, cwd=cwd)
        return out.returncode, out.stdout or "", out.stderr or ""
    except (OSError, subprocess.TimeoutExpired) as e:  # UNKNOWN class, never a silent pass
        return 127, "", str(e)


def _fail(token: str, detail: str) -> int:
    print(token)
    print(detail)
    return 1


def _resolve_commit(ref: str) -> str | None:
    rc, out, _ = _run(["git", "rev-parse", ref], cwd=str(REPO_ROOT))
    sha = out.strip().splitlines()[0] if out.strip() else ""
    return sha if rc == 0 and sha else None


def _version_at_commit(commit: str) -> str | None:
    rc, out, _ = _run(["git", "show", f"{commit}:.claude-plugin/plugin.json"], cwd=str(REPO_ROOT))
    if rc != 0:
        return None
    try:
        return json.loads(out).get("version")
    except (json.JSONDecodeError, AttributeError):
        return None


def _existing_version_tags() -> tuple[bool, list[tuple[str, tuple[int, int, int]]], str]:
    """Every `skill/vX.Y.Z` tag on origin, as (tag-name, version-tuple) pairs, oldest first.
    (ok, tags, detail) — ok is False only when the remote was unreadable."""
    rc, out, err = _run(["git", "ls-remote", "origin", f"{TAG_PREFIX}*"], cwd=str(REPO_ROOT))
    if rc != 0:
        return False, [], err.strip() or str(rc)
    seen: dict[str, tuple[int, int, int]] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        ref = parts[1][:-3] if parts[1].endswith("^{}") else parts[1]
        if not ref.startswith("refs/tags/"):
            continue
        name = ref[len("refs/tags/"):]
        m = _TAG_VERSION_RE.match(name)
        if m:
            seen[name] = tuple(int(g) for g in m.groups())
    return True, sorted(seen.items(), key=lambda kv: kv[1]), ""


def _previous_tag(version: str) -> tuple[bool, str | None, str]:
    """The latest existing `skill/vX.Y.Z` tag below `version` — (ok, tag-or-None, detail).
    ok is False only when the remote was unreadable (fail-closed to the caller, detail
    says why); a non-semver `version` has no comparable predecessor and yields None, the
    callers' full-history / whole-tree fallback. The one home for the resolution both
    range-based conditions (`version_spans_content`, `manual_current`) start from."""
    ok, tags, detail = _existing_version_tags()
    if not ok:
        return False, None, (f"could not read origin's tags: {detail} — an unreadable remote "
                             f"never passes (fail-closed)")
    if not _VERSION_RE.match(version):
        return True, None, ""
    want = tuple(int(g) for g in version.split("."))
    below = [name for name, v in tags if v < want]
    return True, (below[-1] if below else None), ""


def _bump_commit(version: str, commit: str) -> tuple[str | None, str]:
    """The anchor for `version_spans_content`: the first first-parent commit in
    `<previous tag>..<commit>` (full history when no earlier tag exists) at which plugin.json
    first declares `version` — never the previous tag itself (the tag's own commit may sit long
    after the bump, which is exactly the failure this guards). Returns (sha, detail); sha is None
    only when the remote or the history walk was unreadable (fail-closed to the caller). When the
    declared version never appears anywhere in range, the commit under validation is its own
    anchor — an unchanged (empty) tree, by construction. A non-semver `version` never raises: it
    can't be compared against existing tags, so it falls back to the full-history walk (no
    previous-tag bound) — a too-early start costs time, never correctness."""
    ok, prev_tag, detail = _previous_tag(version)
    if not ok:
        return None, detail
    rng = f"{prev_tag}..{commit}" if prev_tag else commit
    rc, out, err = _run(["git", "log", "--first-parent", "--reverse", "--format=%H", rng,
                        "--", ".claude-plugin/plugin.json"], cwd=str(REPO_ROOT))
    if rc != 0:
        return None, f"could not walk first-parent history over {rng!r}: {err.strip()}"
    for sha in (s for s in out.splitlines() if s.strip()):
        if _version_at_commit(sha) == version:
            return sha, (f"bump commit {sha[:9]} (first-parent history since "
                         f"{prev_tag or 'the repo root'})")
    return commit, "the declared version never appears in range — the commit is its own anchor"


def _version_spans_content(version: str, commit: str) -> tuple[str, str]:
    """'' + evidence on pass; 'version_spans_content' + detail on fail. The payload is the whole
    delivered tree (it-33 slice 1's canon): any tracked path changed since the bump commit fails."""
    bump, detail = _bump_commit(version, commit)
    if bump is None:
        return "version_spans_content", detail
    if bump == commit:
        return "", detail
    rc, out, err = _run(["git", "diff", "--name-only", f"{bump}..{commit}"], cwd=str(REPO_ROOT))
    if rc != 0:
        return "version_spans_content", f"could not diff {bump[:9]}..{commit[:9]}: {err.strip()}"
    changed = [p for p in out.splitlines() if p.strip()]
    if changed:
        return "version_spans_content", (
            f"{len(changed)} file(s) changed in the delivered tree between the bump commit "
            f"{bump[:9]} (where plugin.json first declared {version}) and {commit[:9]} — a "
            f"released version's tree must be unchanged since it was declared")
    return "", f"tree unchanged since the bump commit {bump[:9]}"


def _changed_since_previous_tag(version: str, commit: str) -> tuple[list[str] | None, str, str]:
    """The tracked paths changed in `<previous tag>..<commit>` — every tracked path at `commit`
    when no earlier tag exists (the whole tree is new). Returns (paths, range, error); paths is
    None only when the remote or git was unreadable (fail-closed to the caller)."""
    ok, prev_tag, detail = _previous_tag(version)
    if not ok:
        return None, "", detail
    if prev_tag:
        rng = f"{prev_tag}..{commit[:9]}"
        rc, out, err = _run(["git", "diff", "--name-only", f"{prev_tag}..{commit}"],
                            cwd=str(REPO_ROOT))
    else:
        rng = f"the whole tree at {commit[:9]} (no earlier tag)"
        rc, out, err = _run(["git", "ls-tree", "-r", "--name-only", commit], cwd=str(REPO_ROOT))
    if rc != 0:
        return None, rng, f"could not read the paths changed over {rng}: {err.strip() or rc}"
    return [p for p in out.splitlines() if p.strip()], rng, ""


def _manual_current(version: str, commit: str,
                    unaffected: str | None) -> tuple[str, str, str]:
    """'' + evidence + the record's `manual` value on pass; 'manual_current' + detail + '' on
    fail. The manual (MANUAL_PATH) renders MANUAL_SOURCES by citation, so a release whose range
    changed a source without touching the manual would ship a stale manual — refused, unless the
    act records the manual unaffected with a reason (`--manual-unaffected`), which the record
    then carries verbatim. The judgment is diff-based like `version_spans_content` and, like it,
    runs only when a version is declared. The judgment always runs: the override is honoured
    only where the act would otherwise refuse, so the record states what was observed
    (`updated` / `sources unchanged`) whenever that is the fact, an unreadable range refuses
    even under the override, and a blank reason is a refusal naming the value — never read as
    a declaration."""
    override = unaffected.strip() if unaffected is not None else ""
    if unaffected is not None and not override:
        return "manual_current", (
            f"--manual-unaffected was given a blank reason ({unaffected!r}) — the record carries "
            f"the reason verbatim, so a blank declaration is refused, never read as unaffected"), ""
    changed, rng, err = _changed_since_previous_tag(version, commit)
    if changed is None:
        return "manual_current", err, ""
    sources = sorted(p for p in changed if p in MANUAL_SOURCES)
    unused = (f" (--manual-unaffected {override!r} was not needed and is not recorded)"
              if override else "")
    if not sources:
        return "", f"manual sources unchanged over {rng}{unused}", "sources unchanged"
    if MANUAL_PATH in changed:
        return "", (f"manual updated over {rng} alongside {', '.join(sources)}{unused}"), "updated"
    if override:
        value = f"unaffected — {override}"
        return "", (f"{', '.join(sources)} changed over {rng} without {MANUAL_PATH}; manual "
                    f"{value} (recorded by the act)"), value
    return "manual_current", (
        f"{', '.join(sources)} changed over {rng} but {MANUAL_PATH} did not — the manual renders "
        f"those surfaces by citation and would ship stale; update it in the same range, or "
        f"record it unaffected with --manual-unaffected \"<reason>\""), ""


def _ci_green_at(repo: str, commit: str) -> tuple[bool, str]:
    """The PR-head evidence chain. Returns (ok, evidence-or-reason)."""
    rc, out, err = _run(["gh", "api", f"repos/{repo}/commits/{commit}/pulls"],
                        timeout=GH_TIMEOUT)
    if rc != 0:
        return False, f"could not list the commit's source PRs: {err.strip() or rc}"
    try:
        pulls = json.loads(out)
    except json.JSONDecodeError:
        return False, "unparseable /pulls payload"
    if not pulls:
        return False, "no squash-source PR is associated with the commit — no CI evidence exists"
    reasons = []
    for pr in pulls:
        head = (pr.get("head") or {}).get("sha") or ""
        number = pr.get("number")
        if not head:
            reasons.append(f"pr #{number}: no head sha")
            continue
        rc, out, _ = _run(["git", "rev-parse", f"{commit}^{{tree}}", f"{head}^{{tree}}"],
                          cwd=str(REPO_ROOT))
        trees = out.split()
        if rc != 0 or len(trees) != 2 or trees[0] != trees[1]:
            reasons.append(f"pr #{number}: head {head[:9]} is not tree-equal to the commit")
            continue
        rc, out, err = _run(["gh", "api", f"repos/{repo}/commits/{head}/check-runs"],
                            timeout=GH_TIMEOUT)
        if rc != 0:
            reasons.append(f"pr #{number}: check-runs unreadable: {err.strip() or rc}")
            continue
        try:
            runs = json.loads(out).get("check_runs") or []
        except json.JSONDecodeError:
            reasons.append(f"pr #{number}: unparseable check-runs payload")
            continue
        if not runs:
            reasons.append(f"pr #{number}: zero check-runs at head — an empty rollup is not green")
            continue
        bad = [r for r in runs
               if r.get("status") != "completed"
               or (r.get("conclusion") or "") not in _OK_CONCLUSIONS]
        if bad:
            b = bad[0]
            reasons.append(f"pr #{number}: {b.get('name')} is "
                           f"{b.get('conclusion') or b.get('status')}")
            continue
        if not any((r.get("conclusion") or "") == "success" for r in runs):
            reasons.append(f"pr #{number}: no successful run in the rollup")
            continue
        return True, f"pr #{number} head {head[:9]}, tree-equal, rollup green"
    return False, "; ".join(reasons)


def _judged_at_commit(commit: str) -> tuple[str, str]:
    """model_loads + no_drift in a detached worktree AT the commit, by its own tools.
    Returns ('' , evidence) on pass or (failed_token, detail)."""
    wt = tempfile.mkdtemp(prefix="yr-release-")
    rc, _, err = _run(["git", "worktree", "add", "--detach", wt, commit],
                      cwd=str(REPO_ROOT), timeout=WORKTREE_TIMEOUT)
    if rc != 0:
        shutil.rmtree(wt, ignore_errors=True)   # mkdtemp preceded the failed add — no leak
        return "model_loads", f"could not stage a worktree at {commit[:9]}: {err.strip()}"
    try:
        rc, _, err = _run(["python3", "tools/process.py", "validate"], cwd=wt,
                          timeout=WORKTREE_TIMEOUT)
        if rc != 0:
            return "model_loads", f"the model does not load at {commit[:9]}: {err.strip()}"
        rc, out, _ = _run(["python3", "tools/process.py", "check", "--drift"], cwd=wt,
                          timeout=WORKTREE_TIMEOUT)
        if rc != 0:
            return "no_drift", f"compiled surfaces are stale at {commit[:9]}: {out.strip()}"
        return "", f"model loads and build/ is drift-free at {commit[:9]}"
    finally:
        _run(["git", "worktree", "remove", "--force", wt], cwd=str(REPO_ROOT),
             timeout=WORKTREE_TIMEOUT)


def validate(repo: str, commit: str, version: str | None,
             manual_unaffected: str | None = None) -> tuple[int, str, list[str], str]:
    """CONDITIONS, in conditions_display order, fail-closed. Returns (rc, evidence, evaluated,
    manual) — `evaluated` names only the conditions actually judged this call
    (version_spans_content and manual_current run only when a version is given), so a caller
    never claims a condition it didn't run; `manual` is the YR-RELEASE record's `manual` value
    (empty when the condition was not judged)."""
    span_evidence = ""
    manual_evidence = ""
    manual = ""
    evaluated: list[str] = []
    if version is not None:
        at = _version_at_commit(commit)
        if at != version:
            return _fail("version_mismatch",
                         f"plugin.json at {commit[:9]} says {at!r}, not {version!r} — the tag "
                         f"must anchor the commit that shipped the version"), "", evaluated, ""
        evaluated.append("version_spans_content")
        token, detail = _version_spans_content(version, commit)
        if token:
            return _fail(token, detail), "", evaluated, ""
        span_evidence = detail
        evaluated.append("manual_current")
        token, detail, manual = _manual_current(version, commit, manual_unaffected)
        if token:
            return _fail(token, detail), "", evaluated, ""
        manual_evidence = detail
    evaluated.append("model_loads")
    token, detail = _judged_at_commit(commit)
    if token == "model_loads":
        return _fail(token, detail), "", evaluated, ""
    evaluated.append("server_ci_green")
    ok, ci_evidence = _ci_green_at(repo, commit)
    if not ok:
        return _fail("server_ci_green", ci_evidence), "", evaluated, ""
    evaluated.append("no_drift")
    if token == "no_drift":
        return _fail(token, detail), "", evaluated, ""
    evidence = "; ".join(e for e in (span_evidence, manual_evidence, detail, ci_evidence) if e)
    return 0, evidence, evaluated, manual


def record_body(version: str, commit: str, validation: str, who: str, mode: str, *,
                manual: str) -> str:
    """The YR-RELEASE record. `manual` is required, never defaulted: a record emitter with a
    fail-open default would state a fact no judgment produced once the manual exists. `mode`
    "iteration" (it-36 slice I, #474) is the it/<n> family's own tail, beside "ship"/"backfill" —
    the field shape stays the one YR-RELEASE grammar, pinned across both families."""
    tail = {
        "ship": ("Released via `tools/release.py` (the validation-gated, git-native release act — "
                 "it-31 slice 7, ruling 6): the annotated tag anchors the commit; the validation "
                 "evidence above is the record's own."),
        "backfill": ("Backfilled via `tools/release.py` (spec callout (d) as ruled 2026-08-16: "
                     "both shipped versions typed retroactively against their commits)."),
        "iteration": ("Released via `tools/release.py` (the it/<n> tag family, it-36 slice I, "
                      "#474): the epic's own close — closed, YR-ROUND-RECORD present, server CI "
                      "green at the tagged commit — is the validation evidence above."),
    }[mode]
    return (f"YR-RELEASE\n"
            f"version: {version}\n"
            f"commit: {commit}\n"
            f"validation: {validation}\n"
            f"who: {who}\n"
            f"manual: {manual}\n\n{tail}\n")


# ── the it/<n> iteration-release family (it-36 slice I, #474) ──────────────────────────────────

def _epic_closed(repo: str, epic: str) -> tuple[bool, str]:
    """'' the epic issue is CLOSED — (ok, evidence-or-reason)."""
    rc, out, err = _run(["gh", "issue", "view", epic, "--repo", repo, "--json", "state"],
                        timeout=GH_TIMEOUT)
    if rc != 0:
        return False, f"could not read epic #{epic}: {err.strip() or rc}"
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return False, f"unparseable issue payload for epic #{epic}"
    state = str(data.get("state") or "").upper()
    if state != "CLOSED":
        return False, f"epic #{epic} is {state or 'unknown'}, not CLOSED"
    return True, f"epic #{epic} is closed"


def _round_record_present(repo: str, epic: str) -> tuple[bool, str]:
    """A `YR-ROUND-RECORD:` marker line (column 0, records.toml's own grammar) somewhere on the
    epic's own trail — its body or any comment. Presence only, content-blind, the same discipline
    tools/check_trail.py's `_marker_present` applies to every other registered record."""
    rc, out, err = _run(["gh", "issue", "view", epic, "--repo", repo, "--json", "body,comments"],
                        timeout=GH_TIMEOUT)
    if rc != 0:
        return False, f"could not read epic #{epic}'s trail: {err.strip() or rc}"
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return False, f"unparseable issue payload for epic #{epic}"
    texts = [data.get("body") or ""] + [c.get("body") or "" for c in (data.get("comments") or [])]
    marker = "YR-ROUND-RECORD:"
    if any(line.startswith(marker) for text in texts for line in text.splitlines()):
        return True, f"YR-ROUND-RECORD found on epic #{epic}'s trail"
    return False, f"no {marker} record found on epic #{epic}'s trail"


def validate_it(repo: str, commit: str, epic: str) -> tuple[int, str, list[str]]:
    """IT_CONDITIONS, in order, fail-closed. Returns (rc, evidence, evaluated) — mirrors `validate`'s
    contract (exit 0 pass; exit 1 + failed-condition token as stdout's first line printed by `_fail`;
    `evaluated` names only the conditions actually judged before a failure)."""
    evaluated: list[str] = []
    evaluated.append("epic_closed")
    ok, epic_evidence = _epic_closed(repo, epic)
    if not ok:
        return _fail("epic_closed", epic_evidence), "", evaluated
    evaluated.append("round_record_present")
    ok, rr_evidence = _round_record_present(repo, epic)
    if not ok:
        return _fail("round_record_present", rr_evidence), "", evaluated
    evaluated.append("server_ci_green")
    ok, ci_evidence = _ci_green_at(repo, commit)
    if not ok:
        return _fail("server_ci_green", ci_evidence), "", evaluated
    evidence = "; ".join(e for e in (epic_evidence, rr_evidence, ci_evidence) if e)
    return 0, evidence, evaluated


def _release_it(repo: str, iteration: str, commit_ref: str, epic: str, who: str | None,
                test_mode: bool) -> int:
    if not iteration.isdigit():
        return _fail("iteration_malformed",
                     f"{iteration!r} is not a bare integer — it/<n> names an iteration number")
    commit = _resolve_commit(commit_ref)
    if not commit:
        return _fail("commit_unresolvable", f"{commit_ref!r} does not resolve")
    tag = f"{IT_TAG_PREFIX}{iteration}"
    rc, out, err = _run(["git", "ls-remote", "origin", f"refs/tags/{tag}"], cwd=str(REPO_ROOT))
    if rc != 0:
        return _fail("tag_exists", f"could not read origin's tags: {err.strip() or rc} — "
                                   f"an unreadable remote never passes (fail-closed)")
    if out.strip():
        return _fail("tag_exists", f"refs/tags/{tag} already exists on origin — an iteration "
                                   f"ships once; a re-release is a new iteration")
    rc, evidence, evaluated = validate_it(repo, commit, epic)
    if rc != 0:
        return rc
    validation = f"{' '.join(evaluated)} ({evidence})"
    body = record_body(tag, commit, validation, _who(who), "iteration", manual=IT_MANUAL_NA)
    if test_mode:
        print(f"TEST-MODE: no tag, no Release, no trail — the plan only")
        print(f"would tag:     {tag} at {commit}")
        print(f"would release: {tag} on {repo}")
        print("--- record body ---")
        print(body, end="")
        return 0
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False,
                                     prefix="yr-release-it-body-") as f:
        f.write(body)
        body_file = f.name
    rc, _, err = _run(["git", "tag", "-a", tag, commit, "-F", body_file], cwd=str(REPO_ROOT))
    if rc != 0:
        return _fail("tag_write_failed", err.strip() or str(rc))
    rc, _, err = _run(["git", "push", "origin", f"refs/tags/{tag}"], cwd=str(REPO_ROOT),
                      timeout=WORKTREE_TIMEOUT)
    if rc != 0:
        return _fail("tag_push_failed", err.strip() or str(rc))
    rc, out, err = _run(["gh", "release", "create", tag, "--repo", repo,
                         "--title", tag, "--notes-file", body_file,
                         "--verify-tag"], timeout=WORKTREE_TIMEOUT)
    if rc != 0:
        return _fail("release_create_failed", err.strip() or str(rc))
    print(f"released: {tag} at {commit} (iteration)")
    print(out.strip())
    return 0


def _who(explicit: str | None) -> str:
    if explicit:
        return explicit if explicit.startswith("@") else f"@{explicit}"
    rc, out, _ = _run(["gh", "api", "user", "-q", ".login"], timeout=GH_TIMEOUT)
    login = out.strip()
    return f"@{login}" if rc == 0 and login else "@unknown"


def _release(repo: str, version: str, commit_ref: str, who: str | None, mode: str,
             test_mode: bool, manual_unaffected: str | None = None) -> int:
    if not _VERSION_RE.match(version):
        return _fail("version_malformed", f"{version!r} is not X.Y.Z")
    commit = _resolve_commit(commit_ref)
    if not commit:
        return _fail("commit_unresolvable", f"{commit_ref!r} does not resolve")
    tag = f"{TAG_PREFIX}{version}"
    rc, out, err = _run(["git", "ls-remote", "origin", f"refs/tags/{tag}"], cwd=str(REPO_ROOT))
    if rc != 0:
        return _fail("tag_exists", f"could not read origin's tags: {err.strip() or rc} — "
                                   f"an unreadable remote never passes (fail-closed)")
    if out.strip():
        return _fail("tag_exists", f"refs/tags/{tag} already exists on origin — a version is "
                                   f"released once; a re-release is a new version")
    rc, evidence, evaluated, manual = validate(repo, commit, version, manual_unaffected)
    if rc != 0:
        return rc
    validation = f"{' '.join(evaluated)} ({evidence})" if evaluated else evidence
    body = record_body(version, commit, validation, _who(who), mode, manual=manual)
    if test_mode:
        print(f"TEST-MODE: no tag, no Release, no trail — the plan only")
        print(f"would tag:     {tag} at {commit}")
        print(f"would release: {tag} on {repo}")
        print("--- record body ---")
        print(body, end="")
        return 0
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False,
                                     prefix="yr-release-body-") as f:
        f.write(body)
        body_file = f.name
    rc, _, err = _run(["git", "tag", "-a", tag, commit, "-F", body_file], cwd=str(REPO_ROOT))
    if rc != 0:
        return _fail("tag_write_failed", err.strip() or str(rc))
    rc, _, err = _run(["git", "push", "origin", f"refs/tags/{tag}"], cwd=str(REPO_ROOT),
                      timeout=WORKTREE_TIMEOUT)
    if rc != 0:
        return _fail("tag_push_failed", err.strip() or str(rc))
    rc, out, err = _run(["gh", "release", "create", tag, "--repo", repo,
                         "--title", f"skill v{version}", "--notes-file", body_file,
                         "--verify-tag"], timeout=WORKTREE_TIMEOUT)
    if rc != 0:
        return _fail("release_create_failed", err.strip() or str(rc))
    print(f"released: {tag} at {commit} ({mode})")
    print(out.strip())
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="release.py", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_v = sub.add_parser("validate", help="judge only: exit 0 pass; exit 1 + token line on fail")
    p_v.add_argument("--repo", default=DEFAULT_REPO)
    p_v.add_argument("--commit", default="origin/main")
    p_v.add_argument("--version", default=None,
                     help="when given, plugin.json at the commit must agree")
    p_v.add_argument("--manual-unaffected", default=None, metavar="REASON",
                     help="record docs/manual.md unaffected by this range, with the reason")
    p_s = sub.add_parser("ship", help="release origin/main's tip as the given version")
    p_b = sub.add_parser("backfill", help="type a shipped version against its pinned commit")
    for p in (p_s, p_b):
        p.add_argument("--repo", default=DEFAULT_REPO)
        p.add_argument("--version", required=True)
        p.add_argument("--who", default=None)
        p.add_argument("--test-mode", action="store_true",
                       help="full validation, zero writes — no tag, no Release, no trail")
        p.add_argument("--manual-unaffected", default=None, metavar="REASON",
                       help="record docs/manual.md unaffected by this range, with the reason")
    p_b.add_argument("--commit", default=None,
                     help="required for a version outside the pinned BACKFILL pair")
    p_vi = sub.add_parser("validate-it", help="judge only, the it/<n> family: exit 0 pass; exit 1 + token line on fail")
    p_vi.add_argument("--repo", default=DEFAULT_REPO)
    p_vi.add_argument("--commit", default="origin/main")
    p_vi.add_argument("--epic", required=True, help="the closing epic's issue number")
    p_si = sub.add_parser("ship-it", help="release origin/main's tip as it/<iteration>")
    p_si.add_argument("--repo", default=DEFAULT_REPO)
    p_si.add_argument("--iteration", required=True, help="bare integer, e.g. 36 -> tag it/36")
    p_si.add_argument("--epic", required=True, help="the closing epic's issue number")
    p_si.add_argument("--who", default=None)
    p_si.add_argument("--test-mode", action="store_true",
                      help="full validation, zero writes — no tag, no Release, no trail")
    args = ap.parse_args(argv)

    if args.cmd == "validate":
        commit = _resolve_commit(args.commit)
        if not commit:
            return _fail("commit_unresolvable", f"{args.commit!r} does not resolve")
        rc, evidence, evaluated, _ = validate(args.repo, commit, args.version,
                                              args.manual_unaffected)
        if rc == 0:
            print(f"ok: {' '.join(evaluated)} ({evidence})")
        return rc
    if args.cmd == "ship":
        rc, _, err = _run(["git", "fetch", "origin"], cwd=str(REPO_ROOT),
                          timeout=WORKTREE_TIMEOUT)
        if rc != 0:
            return _fail("commit_unresolvable", f"git fetch origin failed: {err.strip()}")
        return _release(args.repo, args.version, "origin/main", args.who, "ship",
                        args.test_mode, args.manual_unaffected)
    if args.cmd == "validate-it":
        commit = _resolve_commit(args.commit)
        if not commit:
            return _fail("commit_unresolvable", f"{args.commit!r} does not resolve")
        rc, evidence, evaluated = validate_it(args.repo, commit, args.epic)
        if rc == 0:
            print(f"ok: {' '.join(evaluated)} ({evidence})")
        return rc
    if args.cmd == "ship-it":
        rc, _, err = _run(["git", "fetch", "origin"], cwd=str(REPO_ROOT),
                          timeout=WORKTREE_TIMEOUT)
        if rc != 0:
            return _fail("commit_unresolvable", f"git fetch origin failed: {err.strip()}")
        return _release_it(args.repo, args.iteration, "origin/main", args.epic, args.who,
                           args.test_mode)
    # backfill
    commit = BACKFILL.get(args.version) or args.commit
    if not commit:
        print(f"backfill: {args.version} is not in the pinned pair and no --commit was given "
              f"— name the shipped commit explicitly", file=sys.stderr)
        return 1
    return _release(args.repo, args.version, commit, args.who, "backfill", args.test_mode,
                    args.manual_unaffected)


if __name__ == "__main__":
    sys.exit(main())
