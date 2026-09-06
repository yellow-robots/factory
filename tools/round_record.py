#!/usr/bin/env python3
"""round_record.py — the close stage's own records module (it-36 slice H, #473).

The close stage's three trail records, computed and applied so a finished epic satisfies the gate's
hold arm (`tools/epic_gate.py`'s close arm — `_process_epic` `:977`, its close branch `:1010-1031`,
itself UNCHANGED — this module only makes what it demands appear):

  * `YR-ROUND-RECORD` (`records.toml:423-431`) — four counts computed from the trails alone, never
    `tools/ledger.py`'s `rows.jsonl` (that sits on the build host, not this one): refusals (the
    runner's Needs-info/Blocked comments on the CHILD trails), records-demanded (`YR-EPIC-GATE`/
    `YR-CLOSE-HOLD` raises on the EPIC trail), detector-findings (`tools/check_trail.py check_texts`
    `:124`'s own close lane, run over the round's own trails, EXCLUDING the close lane's own two
    mandates' bare absence — always true at compute time, by construction, since this call runs
    BEFORE this round's own records post), escalations (`YR-ESCALATION` records across the round) —
    plus the `deployed` field (it-33's addition): the latest `YR-DEPLOY` record on
    yellow-robots/factory#464, read live through `tools/sources.py issue_trail` (the SAME grammar
    `tools/drift.py`'s own `parse_deploy_records` reads — imported, never re-implemented here).
  * `YR-CROSSOVER` (`records.toml:467-475`) — the epic's own merged-PR usage (`tools/sources.py
    pr_usage`, summed over its MERGED linked PRs), the verdict a comparison against the strategy
    doc's own theme `budget_usd`, honest about incompleteness when not every linked PR could be
    priced (`tools/ledger.py`'s own `_cli_crossover` `:568` reads a local, build-host ledger dir —
    never this machinery's own path).
  * `YR-SHIP-WALK` (`records.toml:412-420`) — posted once the close-walk stage's own directive (the
    grounding list walked: a living-reference SECTION update, superseded research stamped, the
    deterministic `check_supersession.py --sweep` run over the component) has been applied through
    `tools/vault_api.py` — the ONLY vault write path — and verified by its own read-back. Idempotent
    (`ship_walk_already_posted`): a re-run after a failed `round-record`/`crossover` never re-runs
    the close-walk stage or re-patches the vault a second time.

Pure core + injectable seams (`gh`, the vault client), a thin CLI drives `tools/close-runner.sh`:
`fetch` (the epic + its children's trails and linked merged-PR numbers, one GraphQL call), `already-
shipped` (I3's idempotence guard), `round-record` / `crossover` / `ship-walk` (compute + render +
post, or `--test-mode` print-only — the `tools/ledger.py crossover` CLI's own shape).

Gotcha (the mandate's own words, `tools/epic_gate.py`'s `_close_hold_body` `:601` is the
precedent): a machinery-emitted close record must never spell a MANDATED FIELD at column 0 inside a
body that carries another marker. Each of the three renderers below produces its OWN body, carrying
exactly ONE marker; every EXTERNALLY supplied string a renderer interpolates (a sweep status, a
`who`/`scope`, the `deployed` field) runs through `_sanitize_interpolated` first — collapsing any
embedded newline (NB1, #473 fold review round 2: an unsanitized multi-line value could otherwise
open a fresh line at column 0 that satisfies a DIFFERENT record's own presence check, from inside
what should be a single-marker body) — so this can never arise by construction, structurally, not
by caller discipline; `tests/test_round_record.py` pins it directly, including a hostile multi-line
value for every external field (no render function's body ever satisfies another record's presence
check, sanitized or not).
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import check_trail   # noqa: E402
import drift         # noqa: E402 — sibling import: reuses drift.parse_deploy_records, the one grammar
import records       # noqa: E402
import sources       # noqa: E402
import strategy      # noqa: E402 — also reuses strategy.matching_theme, the one theme-matching rule
import textutil      # noqa: E402
import vault_api     # noqa: E402

GH_TIMEOUT = int(os.environ.get("YR_ROUND_RECORD_GH_TIMEOUT", "20"))  # N3: bounded, like sources._run

# ── refusals: the runner's own bounce/block comment prose (tools/dev-runner.sh, prose, not a YR-*
#    record — `:1114`/`:1150`) — counted on the CHILD trails only, the runner's own scope ────────────
NEEDS_INFO_PREFIX = "dev-runner: bounced to **Needs-info**"
BLOCKED_PREFIX = "dev-runner: **Blocked** — "


def count_refusals(child_texts: list) -> int:
    """One count per CHILD-trail comment that opens with the runner's own Needs-info bounce or
    Blocked prose (never a YR-* marker — this is dev-runner.sh's own comment text, matched
    verbatim)."""
    return sum(1 for t in child_texts if t.startswith(NEEDS_INFO_PREFIX) or t.startswith(BLOCKED_PREFIX))


def count_records_demanded(epic_texts: list, reg=None) -> int:
    """One count per EPIC-trail comment carrying ANY `YR-EPIC-GATE: *` raise-family marker or the
    `YR-CLOSE-HOLD` sentinel — registry-driven (never a hardcoded marker list), so a canon-side
    marker change is picked up automatically. A comment matching more than one such row still counts
    once (one raise event, one comment)."""
    reg = reg or records.load()
    rows = [r for r in records.records(reg)
           if r["name"].startswith("YR-EPIC-GATE") or r["name"] == "YR-CLOSE-HOLD"]
    count = 0
    for text in epic_texts:
        lines = text.splitlines()
        if any(any(textutil.marker_line_matches(l, row["marker"], mode=row["mode"]) for l in lines)
              for row in rows):
            count += 1
    return count


def count_escalations(all_texts: list, reg=None) -> int:
    """One count per comment (epic OR child trails — escalations can land on either) carrying the
    registered `YR-ESCALATION` marker."""
    reg = reg or records.load()
    row = records.get(reg, "YR-ESCALATION")
    count = 0
    for text in all_texts:
        lines = text.splitlines()
        if any(textutil.marker_line_matches(l, row["marker"], mode=row["mode"]) for l in lines):
            count += 1
    return count


# B5's own fix: the close lane mandates EXACTLY these two records (records.lanes(reg)["close"]) —
# checking for their bare ABSENCE here is meaningless by construction, since this call always runs
# BEFORE this round's own YR-ROUND-RECORD/YR-SHIP-WALK post (it-33's own hand count was 0; this
# detector, unfixed, always read 2). A finding that a record is instead PRESENT-BUT-MALFORMED (a
# stray, already-posted record on the trail missing a field) is real trail hygiene trouble and stays
# counted — only the "mandated record absent" finding for these two names is excluded.
_SELF_MANDATE_NAMES = ("YR-ROUND-RECORD", "YR-SHIP-WALK")


def count_detector_findings(reg, epic_texts: list, child_texts_by_number: dict) -> int:
    """The close lane's own trail-shape check (`tools/check_trail.py check_texts` `:124`), run over
    the round's own trails — epic AND every child, pooled — as one `issue-trail` surface, EXCLUDING
    the close lane's own two mandates' bare absence (see `_SELF_MANDATE_NAMES` above — B5). Not the
    same question as the close arm's own `_close_records_findings` (that runs on the epic's trail
    alone, at hold time, and is never filtered — it needs the real absence to hold); this is the
    round's own hygiene metric, priced for the human, never a gate."""
    all_texts = list(epic_texts)
    for texts in child_texts_by_number.values():
        all_texts.extend(texts)
    findings = check_trail.check_texts(reg, "close", {"issue-trail": all_texts})
    findings = [f for f in findings if not any(
        f.startswith(f"close: {name}: mandated record absent") for name in _SELF_MANDATE_NAMES)]
    return len(findings)


def deployed_field(deploy_texts: list) -> str:
    """The `deployed` field's own value: per-surface (I2), mirroring `drift.deploy_record_findings`'s
    own per-surface rule exactly — every surface the latest `YR-DEPLOY` record names (its own comma-
    separated `surface` list) reads the LATEST record's commit, except `dispatch` (a resident process
    a `restart: no` deploy legitimately leaves on its prior commit), which reads the latest record
    that actually claims `restart: yes` instead, or is named as carrying no such record yet. Parsed
    from `deploy_texts` (yellow-robots/factory#464's own trail, read through `tools/sources.py
    issue_trail` — the same way `tools/drift.py deploy_record_findings` reads it) via
    `drift.parse_deploy_records`, the one shared grammar. `'none'` when no record exists yet — the
    literal token the close lane's own fixtures already use (`tests/test_epic_gate.py`'s
    `CLOSE_RECORDS`). Callers distinguish "no record yet" from "the trail could not be read at all"
    themselves (I1) — this function only ever sees texts, never a fetch failure."""
    parsed = drift.parse_deploy_records(deploy_texts)
    if not parsed:
        return "none"
    latest = parsed[-1]
    latest_restart_yes = next((r for r in reversed(parsed) if r["restart"] == "yes"), None)
    parts = []
    for name in [s.strip() for s in latest["surface"].split(",") if s.strip()]:
        if name == "dispatch":
            if latest_restart_yes is None:
                parts.append(f"{name}: no restart:yes record yet")
                continue
            commit = latest_restart_yes["commit"]
        else:
            commit = latest["commit"]
        parts.append(f"{name}: commit={commit[:12]}")
    return ", ".join(parts) if parts else "none"


def ship_walk_already_posted(epic_texts: list, reg=None) -> bool:
    """True once `YR-SHIP-WALK` already rides the epic trail — the ship-walk's own idempotence guard
    (I3), mirroring `tools/epic_gate.py`'s own `already_held` precedent for its hold markers: a
    re-run of the close stage (say, after a failed `round-record`/`crossover`) must never re-run the
    close-walk stage or re-patch the vault a second time."""
    reg = reg or records.load()
    row = records.get(reg, "YR-SHIP-WALK")
    return any(
        any(textutil.marker_line_matches(l, row["marker"], mode=row["mode"]) for l in text.splitlines())
        for text in epic_texts
    )


def _sanitize_interpolated(value, *, max_len=200) -> str:
    """Collapses ALL whitespace (embedded newlines included) to single spaces and caps length —
    applied by EVERY renderer below to EVERY externally supplied string it interpolates (NB1, #473
    fold review round 2): a value carrying a literal newline could otherwise render a body that
    satisfies ANOTHER record's own presence check — `mode=prefix`'s column-0 anchor cares only
    about a LINE's own start, so an embedded `\\nYR-ROUND-RECORD: ...` inside, say, a hostile
    `supersession_sweep` status would anchor there exactly as if it opened its own comment. Exactly
    the class `epic_gate._close_hold_body`'s own column-0 discipline exists to prevent, and
    criterion 3 forbids. Structural, never caller-trusted: a renderer sanitizes its OWN inputs, so
    "can never arise by construction" (this module's own docstring) stays true regardless of what a
    caller — or a future caller — passes in."""
    return " ".join(str(value).split())[:max_len]


def round_record_body(*, refusals, records_demanded, detector_findings, escalations, deployed,
                      truncated=False, reg=None) -> str:
    reg = reg or records.load()
    marker = records.get(reg, "YR-ROUND-RECORD")["marker"]
    lines = [
        f"{marker} the round's observable counts",
        f"refusals: {refusals}",
        f"records-demanded: {records_demanded}",
        f"detector-findings: {detector_findings}",
        f"escalations: {escalations}",
        f"deployed: {_sanitize_interpolated(deployed)}",
    ]
    if truncated:
        # I5 (partial): a fetched page hit its own GraphQL cap — the counts above may undercount a
        # round whose comments/PRs ran past it. Stated on the record itself, never silently.
        lines.append("note: fetch page(s) hit the query's own cap — some comments/PRs beyond it "
                     "were not counted, so these counts may undercount the real round")
    return (
        "\n".join(lines) + "\n\n"
        "Computed from the trails alone (it-36 slice H, #473) — never the build host's ledger: "
        "refusals (the runner's Needs-info/Blocked comments on the child trails), records-demanded "
        "(YR-EPIC-GATE/YR-CLOSE-HOLD raises on the epic trail), detector-findings (the close lane's "
        "own trail-shape check over the round's own trails), escalations (YR-ESCALATION records "
        f"across the round), and deployed (the latest `YR-DEPLOY` record(s) on "
        f"{drift.DEPLOY_TRAIL_REPO}#{drift.DEPLOY_TRAIL_ISSUE}, PER SURFACE — NN4: every surface but "
        "`dispatch` reads the latest record's own commit; `dispatch` reads the latest record that "
        "actually claims `restart: yes` instead, since a resident process a `restart: no` deploy "
        "legitimately leaves on its prior commit). The pricing judgment against attended attention "
        "stays the human's."
    )


# ── YR-CROSSOVER: this epic's own merged-PR usage vs. the strategy doc's theme budget ────────────────
def crossover_verdict(total_cost_usd: float, budget_usd, *, priced_count: int, linked_count: int) -> str:
    """Honest about incompleteness (B4): `unpriceable` when NOT ONE linked PR could be priced (no
    cost evidence at all — a bare `within-budget` here would be a fabricated reading of $0);
    `within-budget-partial` / `over-budget-partial` when only SOME of the linked PRs priced (the
    total undercounts real cost, so a within-budget reading is provisional, never asserted plain);
    the ordinary three-way verdict only once EVERY linked PR priced."""
    if priced_count <= 0:
        return "unpriceable"
    if not isinstance(budget_usd, (int, float)):
        return "no-budget-declared"
    base = "within-budget" if total_cost_usd <= budget_usd else "over-budget"
    return f"{base}-partial" if priced_count < linked_count else base


def crossover_from_pr_usages(pr_usages: dict, budget_usd, *, linked_count: int) -> dict:
    """`pr_usages`: `{"<repo>#<pr>": <tools/sources.py pr_usage result dict>}` for every linked PR
    that COULD be priced — already-fetched, so this stays pure and network-free. `linked_count` is
    the TOTAL linked-PR count (priced or not — B4's own fix: silently dropping the unpriceable ones
    from the denominator understated a real round's cost by more than half on #455's own trail: 7
    linked, 3 priced, $9.15 read as the whole story against a $21.43 ledger truth). Returns
    `{"cost_usd", "pr_count" (priced), "linked_count", "verdict"}`."""
    priced_count = len(pr_usages)
    total = sum((u.get("cost_usd") or 0) for u in pr_usages.values())
    verdict = crossover_verdict(total, budget_usd, priced_count=priced_count, linked_count=linked_count)
    return {"cost_usd": total, "pr_count": priced_count, "linked_count": linked_count, "verdict": verdict}


def crossover_body(*, cost_usd, pr_count, linked_count, budget_usd, verdict, who, truncated=False,
                   reg=None) -> str:
    reg = reg or records.load()
    marker = records.get(reg, "YR-CROSSOVER")["marker"]
    # I7: the budget rides AS DECLARED — no invented period unit (no canon names one).
    budget_text = f"${budget_usd:.2f}" if isinstance(budget_usd, (int, float)) else "none declared"
    unpriced = linked_count - pr_count
    if unpriced > 0:
        pr_text = (f"across {pr_count} of {linked_count} linked PR(s) "
                  f"({unpriced} carried no dev-runner usage comment)")
    else:
        pr_text = f"across {pr_count} merged PR(s)"
    cost_line = f"cost: ${cost_usd:.2f} {pr_text} (theme budget {budget_text})"
    if truncated:
        # I5 (partial): the linked-PR page hit its own GraphQL cap — this cost may be missing PRs
        # past it. Stated on the record itself, never silently.
        cost_line += " — note: fetch page truncated, some linked PRs beyond the query's own cap may be missing"
    return (
        f"{marker}\n"
        f"{cost_line}\n"
        f"verdict: {verdict}\n"
        f"who: {_sanitize_interpolated(who)}\n\n"
        "The crossover test's typed verdict (it-36 slice H, #473): cost is this epic's own "
        "merged-PR usage (tools/sources.py pr_usage, summed over its priceable linked PRs); verdict "
        "compares that cost against the strategy doc's own theme budget_usd, naming any linked PR "
        "this evidence could not price rather than silently dropping it from the count. The pricing "
        "judgment stays the human's."
    )


def matching_theme_budget(parsed_strategy: dict, repo: str):
    """The first theme (declared order) whose `repos` names `repo` -> its `budget_usd`, or `None`
    when no theme targets this repo — delegates to `tools/strategy.py`'s own public
    `matching_theme` (I7/NN2: the ONE theme-matching rule, a public seam next to the schema it
    reads, never a private reach into another module)."""
    theme = strategy.matching_theme(parsed_strategy, repo)
    return theme.get("budget_usd") if theme else None


# ── YR-SHIP-WALK: the close-walk stage's own directive, applied through the vault client ─────────────
SHIP_WALK_LIVING_REF_RE = re.compile(
    r"===LIVING-REFERENCE===[ \t]*\r?\n"
    r"path:[ \t]*(?P<path>.+?)[ \t]*\r?\n"
    r"heading:[ \t]*(?P<heading>.+?)[ \t]*\r?\n"
    r"===CONTENT===\r?\n(?P<content>.*?)\r?\n===END-CONTENT===[ \t]*\r?\n"
    r"===END-LIVING-REFERENCE===",
    re.DOTALL,
)
SHIP_WALK_SUPERSEDED_BLOCK_RE = re.compile(
    r"===SUPERSEDED===[ \t]*\r?\n(?P<body>.*?)\r?\n===END-SUPERSEDED===", re.DOTALL)
SHIP_WALK_SUPERSEDED_LINE_RE = re.compile(r"^[ \t]*(?P<path>\S.*?)[ \t]*:[ \t]*(?P<target>\S.*?)[ \t]*$")


def parse_ship_walk_output(raw_text: str) -> dict:
    """The close-walk stage's own output grammar -> `{"living_reference": {"path", "heading_path",
    "content"} | None, "superseded": [(path, superseded_by), ...]}`. `heading` may name a nested
    heading path, PLAIN TEXT ONLY (never `#`/`##`-prefixed — B1: a real heading `target` is the
    heading's own text, verified 2026-09-06 against the live `/openapi.yaml`), joined by `'::'` for
    this module's OWN close-walk output grammar only — a plain-text convention for the stage's
    instruction, unrelated to the vault's actual wire encoding (`vault_api.patch_section` sends the
    resulting `heading_path` list as the server's own JSON array `target`, never re-joined) ->
    `heading_path`, a list. A `target` of `none` (case-insensitive) is a declared no-op, dropped,
    never applied. Raises `ValueError` on a malformed or entirely-empty shape — a stage output this
    runner cannot act on is a loud stop, never a guessed partial apply (`tools/cross.py split_draft`'s
    own discipline)."""
    m = SHIP_WALK_LIVING_REF_RE.search(raw_text)
    living_reference = None
    if m:
        heading_path = [h.strip() for h in m.group("heading").split("::") if h.strip()]
        if not heading_path:
            raise ValueError("close-walk output: ===LIVING-REFERENCE=== names an empty heading")
        living_reference = {
            "path": m.group("path").strip(),
            "heading_path": heading_path,
            "content": m.group("content").strip("\n"),
        }
    superseded = []
    sm = SHIP_WALK_SUPERSEDED_BLOCK_RE.search(raw_text)
    if sm:
        for line in sm.group("body").splitlines():
            line = line.strip()
            if not line:
                continue
            lm = SHIP_WALK_SUPERSEDED_LINE_RE.match(line)
            if not lm:
                raise ValueError(f"close-walk output: malformed ===SUPERSEDED=== line: {line!r}")
            target = lm.group("target")
            if target.lower() != "none":
                superseded.append((lm.group("path"), target))
    if living_reference is None and not superseded:
        raise ValueError("close-walk output carries neither a ===LIVING-REFERENCE=== block nor a "
                         "===SUPERSEDED=== entry — nothing to apply")
    return {"living_reference": living_reference, "superseded": superseded}


def apply_ship_walk(vault, parsed: dict) -> dict:
    """Applies a parsed close-walk directive through the vault client — the ONLY vault write path
    (`tools/vault_api.py`). The living reference's own named section is updated via a heading-
    targeted PATCH (never a whole-body overwrite — the hazard the `ifMatch` concurrency token exists
    to prevent for a repeatedly-edited living reference), anchored to the document map's own
    `version` as that token; each superseded doc is stamped `status: superseded` + `superseded_by`,
    both frontmatter writes the vault client already verifies by read-back on its own. Returns a
    summary dict; raises `vault_api.VaultUnreachable` on any refused or unconfirmed write — a loud
    stop, never a partial, silently-accepted apply."""
    applied = {"living_reference": None, "superseded": []}
    lr = parsed.get("living_reference")
    if lr:
        doc_map = vault.document_map(lr["path"])
        vault.patch_section(lr["path"], lr["heading_path"], lr["content"],
                            if_match=doc_map.get("version"))
        applied["living_reference"] = {"path": lr["path"], "heading_path": lr["heading_path"]}
    for path, target in parsed.get("superseded") or []:
        vault.patch_frontmatter(path, "status", "superseded")
        vault.patch_frontmatter(path, "superseded_by", target)
        applied["superseded"].append({"path": path, "superseded_by": target})
    return applied


def ship_walk_body(*, who, scope, supersession_sweep=None, reg=None) -> str:
    """`supersession_sweep` (I10): the deterministic `check_supersession.py --sweep`'s own outcome
    over the walked component, as a short status string (e.g. `"clean (exit 0)"` or `"3 finding(s)
    — see run log"`) — folded into the record's own prose so "the grounding list was walked" is
    backed by a run of the existing deterministic sweep, never asserted on prose alone. `None` when
    the caller had no component to sweep (an entirely superseded-only walk names nothing to check).
    `who`/`scope`/`supersession_sweep` are every EXTERNALLY supplied string this renderer takes —
    each runs through `_sanitize_interpolated` (NB1) before it ever reaches the body."""
    reg = reg or records.load()
    marker = records.get(reg, "YR-SHIP-WALK")["marker"]
    sweep_sentence = (f" The component's supersession sweep (`check_supersession.py --sweep`) ran: "
                      f"{_sanitize_interpolated(supersession_sweep)}." if supersession_sweep else "")
    return (
        f"{marker} walked at close\n"
        f"who: {_sanitize_interpolated(who)}\n"
        f"scope: {_sanitize_interpolated(scope)}\n\n"
        "The grounding list was walked: the living reference's section updated in place through the "
        "vault client (a heading-targeted PATCH, never a whole-body overwrite), and any superseded "
        f"research stamped — each write verified by its own read-back.{sweep_sentence} "
        "(it-36 slice H, #473)."
    )


# ── CLI: the seams close-runner.sh drives — real gh, real vault; every core above stays pure ─────────
_ROUND_QUERY = """
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    issue(number: $number) {
      body
      comments(first: 100) { pageInfo { hasNextPage } nodes { body } }
      subIssues(first: 100) {
        pageInfo { hasNextPage }
        nodes {
          number
          body
          repository { nameWithOwner }
          comments(first: 100) { pageInfo { hasNextPage } nodes { body } }
          closedByPullRequestsReferences(first: 10) {
            pageInfo { hasNextPage }
            nodes { number merged repository { nameWithOwner } }
          }
        }
      }
    }
  }
}
"""
# I5 (partial): none of the three connections above (an epic's own comments, a child's own
# comments, a child's own linked-PR list) WALK past their `first:` cap — a real epic/child/PR-
# linkage set past 100/100/10 still reads only that first page (a per-parent cursor walk three
# connections deep is a bigger lift than this fold's own scope). What changed: each connection's
# own `pageInfo.hasNextPage` is now READ (never walked) and folded into one overall `truncated`
# flag in fetch.json's own output — `_cli_round_record`/`_cli_crossover` thread it into the
# record's own body, so a truncated page is a STATED fact on the record, never a silently-wrong
# count.


def _gh(argv):
    try:
        proc = subprocess.run([os.environ.get("GH_BIN", "gh"), *argv], capture_output=True,
                              text=True, timeout=GH_TIMEOUT)
    except subprocess.TimeoutExpired:
        # N3 (partial): a stated refusal, never an uncaught exception racing past this seam.
        raise RuntimeError(f"gh {' '.join(argv)} timed out after {GH_TIMEOUT}s")
    if proc.returncode != 0:
        raise RuntimeError(f"gh {' '.join(argv)} failed ({proc.returncode}): {proc.stderr.strip()}")
    return proc.stdout


def _as_json(out):
    return out if isinstance(out, (dict, list)) else json.loads(out or "null")


def _comment(gh, *, repo, issue, body):
    gh(["issue", "comment", str(issue), "--repo", repo, "--body", body])


def _cli_fetch(argv):
    ap = argparse.ArgumentParser(description="fetch the epic + its children's trails and linked merged-PR numbers")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--epic", type=int, required=True)
    args = ap.parse_args(argv)
    owner, _, name = args.repo.partition("/")
    data = _as_json(_gh(["api", "graphql", "-f", "query=" + _ROUND_QUERY,
                        "-F", f"owner={owner}", "-F", f"name={name}", "-F", f"number={args.epic}"]))
    data = data.get("data", data) if isinstance(data, dict) else data
    issue = ((data.get("repository") or {}).get("issue")) or {}
    epic_comments = (issue.get("comments") or {})
    epic_texts = [issue.get("body") or ""] + [
        c.get("body") or "" for c in (epic_comments.get("nodes") or [])]
    sub_issues = (issue.get("subIssues") or {})
    children = sub_issues.get("nodes") or []
    # I5 (partial): one overall truncation flag — true iff ANY of the connections below hit its cap.
    truncated = bool((epic_comments.get("pageInfo") or {}).get("hasNextPage"))
    truncated = truncated or bool((sub_issues.get("pageInfo") or {}).get("hasNextPage"))
    child_texts = {}
    pr_refs = []
    for c in children:
        child_repo = (c.get("repository") or {}).get("nameWithOwner") or args.repo
        key = f"{child_repo}#{c.get('number')}"
        c_comments = (c.get("comments") or {})
        child_texts[key] = [c.get("body") or ""] + [
            cc.get("body") or "" for cc in (c_comments.get("nodes") or [])]
        truncated = truncated or bool((c_comments.get("pageInfo") or {}).get("hasNextPage"))
        c_prs = (c.get("closedByPullRequestsReferences") or {})
        truncated = truncated or bool((c_prs.get("pageInfo") or {}).get("hasNextPage"))
        for pr in (c_prs.get("nodes") or []):
            # I6: an OPEN linked PR (closes-by-reference without being merged — e.g. a superseding
            # PR, or one still in flight when this closed) is never priced as a merged one.
            if not pr.get("merged"):
                continue
            pr_repo = (pr.get("repository") or {}).get("nameWithOwner") or child_repo
            pr_refs.append({"repo": pr_repo, "number": pr.get("number")})
    print(json.dumps({"epic_texts": epic_texts, "child_texts": child_texts, "pr_refs": pr_refs,
                      "truncated": truncated}))
    return 0


def _cli_already_shipped(argv):
    """I3's idempotence guard, as a CLI check `close-runner.sh` runs BEFORE the close-walk stage:
    exit 0 iff `YR-SHIP-WALK` already rides the epic trail (nothing left to walk or patch this
    tick), exit 1 when it does not. NN1: a malformed/incomplete `fetch.json` (missing `epic_texts`,
    unparseable JSON, unreadable file) is a THIRD, DISTINCT outcome — exit 2 — never silently folded
    into "not shipped": that would let a fetch failure fall through to a FRESH close-walk + vault
    patch instead of stopping the run. `close-runner.sh` treats exit 2 as fail-closed STOP."""
    ap = argparse.ArgumentParser(description="exit 0 shipped / 1 not shipped / 2 fetch.json malformed (refuse)")
    ap.add_argument("--fetch-json", required=True)
    args = ap.parse_args(argv)
    try:
        fetched = json.loads(pathlib.Path(args.fetch_json).read_text(encoding="utf-8"))
        epic_texts = fetched["epic_texts"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"round_record: already-shipped refused — {args.fetch_json} is malformed: {e}",
              file=sys.stderr)
        return 2
    return 0 if ship_walk_already_posted(epic_texts) else 1


def _cli_round_record(argv):
    ap = argparse.ArgumentParser(description="compute + post/print YR-ROUND-RECORD")
    ap.add_argument("--fetch-json", required=True)
    ap.add_argument("--deploy-repo", default=drift.DEPLOY_TRAIL_REPO)
    ap.add_argument("--deploy-issue", default=drift.DEPLOY_TRAIL_ISSUE)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--epic", type=int, required=True)
    ap.add_argument("--test-mode", action="store_true")
    args = ap.parse_args(argv)
    fetched = json.loads(pathlib.Path(args.fetch_json).read_text(encoding="utf-8"))
    reg = records.load()
    # I1: "no record yet" (a clean read, nothing posted) and "the trail could not be read at all"
    # are different facts — never conflated under the same "none" token.
    ok, deploy_texts_or_reason = sources.issue_trail(args.deploy_repo, str(args.deploy_issue))
    deployed = deployed_field(deploy_texts_or_reason) if ok else f"unreadable ({deploy_texts_or_reason})"
    all_child_texts = [t for texts in fetched["child_texts"].values() for t in texts]
    body = round_record_body(
        refusals=count_refusals(all_child_texts),
        records_demanded=count_records_demanded(fetched["epic_texts"], reg),
        detector_findings=count_detector_findings(reg, fetched["epic_texts"], fetched["child_texts"]),
        escalations=count_escalations(fetched["epic_texts"] + all_child_texts, reg),
        deployed=deployed, truncated=bool(fetched.get("truncated")), reg=reg)
    if args.test_mode:
        print("TEST-MODE: no trail write — the record only")
        print(body)
        return 0
    _comment(_gh, repo=args.repo, issue=args.epic, body=body)
    print(f"round-record: YR-ROUND-RECORD posted on {args.repo}#{args.epic}")
    return 0


def _cli_crossover(argv):
    ap = argparse.ArgumentParser(description="compute + post/print YR-CROSSOVER")
    ap.add_argument("--fetch-json", required=True)
    ap.add_argument("--strategy-doc", required=True,
                    help="local vault-mirror path to the repo's strategy note")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--epic", type=int, required=True)
    ap.add_argument("--who", required=True)
    ap.add_argument("--test-mode", action="store_true")
    args = ap.parse_args(argv)
    fetched = json.loads(pathlib.Path(args.fetch_json).read_text(encoding="utf-8"))
    strategy_text = pathlib.Path(args.strategy_doc).read_text(encoding="utf-8")
    try:
        parsed_strategy = strategy.parse_strategy(strategy_text)
    except strategy.StrategyError as e:
        # I8: a stated refusal, never an unhandled traceback — named on the close-runner's own log.
        print(f"round_record: crossover refused — strategy doc malformed: {e}", file=sys.stderr)
        return 1
    budget_usd = matching_theme_budget(parsed_strategy, args.repo)
    pr_usages = {}
    for ref in fetched.get("pr_refs") or []:
        ok, usage = sources.pr_usage(ref["repo"], str(ref["number"]))
        if ok:
            pr_usages[f"{ref['repo']}#{ref['number']}"] = usage
    linked_count = len(fetched.get("pr_refs") or [])
    result = crossover_from_pr_usages(pr_usages, budget_usd, linked_count=linked_count)
    body = crossover_body(cost_usd=result["cost_usd"], pr_count=result["pr_count"],
                          linked_count=result["linked_count"], budget_usd=budget_usd,
                          verdict=result["verdict"], who=args.who, truncated=bool(fetched.get("truncated")))
    if args.test_mode:
        print("TEST-MODE: no trail write — the record only")
        print(body)
        return 0
    _comment(_gh, repo=args.repo, issue=args.epic, body=body)
    print(f"crossover: YR-CROSSOVER posted on {args.repo}#{args.epic} (verdict={result['verdict']})")
    return 0


def _cli_ship_walk(argv):
    ap = argparse.ArgumentParser(description="apply the close-walk stage's own output and post YR-SHIP-WALK")
    ap.add_argument("--in", dest="in_path", required=True, help="the close-walk stage's raw log")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--epic", type=int, required=True)
    ap.add_argument("--who", required=True)
    ap.add_argument("--scope", required=True)
    ap.add_argument("--supersession-sweep", default=None,
                    help="check_supersession.py --sweep's own outcome, a short status string (I10)")
    ap.add_argument("--test-mode", action="store_true")
    args = ap.parse_args(argv)
    raw = pathlib.Path(args.in_path).read_text(encoding="utf-8")
    try:
        parsed = parse_ship_walk_output(raw)
    except ValueError as e:
        print(f"round_record: close-walk output malformed: {e}", file=sys.stderr)
        return 1
    try:
        apply_ship_walk(vault_api.VaultClient(), parsed)
    except vault_api.VaultUnreachable as e:
        print(f"round_record: ship-walk apply stopped — {e}", file=sys.stderr)
        return 1
    body = ship_walk_body(who=args.who, scope=args.scope, supersession_sweep=args.supersession_sweep)
    if args.test_mode:
        print("TEST-MODE: no trail write — the record only")
        print(body)
        return 0
    _comment(_gh, repo=args.repo, issue=args.epic, body=body)
    print(f"ship-walk: YR-SHIP-WALK posted on {args.repo}#{args.epic}")
    return 0


_SUBCOMMANDS = {
    "fetch": _cli_fetch,
    "already-shipped": _cli_already_shipped,
    "round-record": _cli_round_record,
    "crossover": _cli_crossover,
    "ship-walk": _cli_ship_walk,
}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in _SUBCOMMANDS:
        return _SUBCOMMANDS[argv[0]](argv[1:])
    print(f"usage: round_record.py <{'|'.join(_SUBCOMMANDS)}> ...", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
