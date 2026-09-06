#!/usr/bin/env python3
"""round_record.py — the close stage's own records module (it-36 slice H, #473).

The close stage's three trail records, computed and applied so a finished epic satisfies the gate's
hold arm (`tools/epic_gate.py`'s close arm, `:972-1004`, itself UNCHANGED — this module only makes
what it demands appear):

  * `YR-ROUND-RECORD` (`records.toml:423-431`) — four counts computed from the trails alone, never
    `tools/ledger.py`'s `rows.jsonl` (that sits on the build host, not this one): refusals (the
    runner's Needs-info/Blocked comments on the CHILD trails), records-demanded (`YR-EPIC-GATE`/
    `YR-CLOSE-HOLD` raises on the EPIC trail), detector-findings (`tools/check_trail.py`'s own close
    lane, run over the round's own trails), escalations (`YR-ESCALATION` records across the round) —
    plus the `deployed` field (it-33's addition): the latest `YR-DEPLOY` record on
    yellow-robots/factory#464, read live through `tools/sources.py issue_trail` (the SAME grammar
    `tools/drift.py`'s own `_parse_deploy_records` reads — imported, never re-implemented here).
  * `YR-CROSSOVER` (`records.toml:467-475`) — the epic's own merged-PR usage (`tools/sources.py
    pr_usage`, summed), the verdict a comparison against the strategy doc's own theme `budget_usd`
    (`tools/ledger.py`'s own `_cli_crossover` reads a local, build-host ledger dir — never this
    machinery's own path).
  * `YR-SHIP-WALK` (`records.toml:412-420`) — posted once the close-walk stage's own directive (the
    grounding list walked: a living-reference SECTION update, superseded research stamped) has been
    applied through `tools/vault_api.py` — the ONLY vault write path — and verified by its own
    read-back.

Pure core + injectable seams (`gh`, the vault client), a thin CLI drives `tools/close-runner.sh`:
`fetch` (the epic + its children's trails and linked merged-PR numbers, one GraphQL call), `round-
record` / `crossover` / `ship-walk` (compute + render + post, or `--test-mode` print-only — the
`tools/ledger.py crossover` CLI's own shape).

Gotcha (the mandate's own words, `tools/epic_gate.py`'s `_close_hold_body` is the precedent): a
machinery-emitted close record must never spell a MANDATED FIELD at column 0 inside a body that
carries another marker. Each of the three renderers below produces its OWN body, carrying exactly
ONE marker, with field values that are always short counts/strings — never a quoted excerpt of
another record's raw marker text — so this can never arise by construction; `tests/test_round_
record.py` pins it directly (no render function's body ever satisfies another record's presence
check).
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
import check_trail  # noqa: E402
import drift        # noqa: E402 — sibling import: reuses drift._parse_deploy_records, the one grammar
import records      # noqa: E402
import sources      # noqa: E402
import strategy     # noqa: E402
import textutil     # noqa: E402
import vault_api    # noqa: E402

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


def count_detector_findings(reg, epic_texts: list, child_texts_by_number: dict) -> int:
    """The close lane's own trail-shape check (`tools/check_trail.py check_texts`), run over the
    round's own trails — epic AND every child, pooled — as one `issue-trail` surface. Not the same
    question as the close arm's own `_close_records_findings` (that runs on the epic's trail alone,
    at hold time); this is the round's own hygiene metric, priced for the human, never a gate."""
    all_texts = list(epic_texts)
    for texts in child_texts_by_number.values():
        all_texts.extend(texts)
    return len(check_trail.check_texts(reg, "close", {"issue-trail": all_texts}))


def deployed_field(deploy_texts: list) -> str:
    """The `deployed` field's own value: the latest well-formed `YR-DEPLOY` record among
    `deploy_texts` (yellow-robots/factory#464's own trail, read through `tools/sources.py
    issue_trail` — the same way `tools/drift.py deploy_record_findings` reads it), rendered as
    `surface=... commit=<12> restart=...`. `'none'` when no record exists yet — the literal token
    the close lane's own fixtures already use (`tests/test_epic_gate.py`'s `CLOSE_RECORDS`)."""
    parsed = drift._parse_deploy_records(deploy_texts)
    if not parsed:
        return "none"
    latest = parsed[-1]
    return f"surface={latest['surface']} commit={latest['commit'][:12]} restart={latest['restart'] or 'unstated'}"


def round_record_body(*, refusals, records_demanded, detector_findings, escalations, deployed,
                      reg=None) -> str:
    reg = reg or records.load()
    marker = records.get(reg, "YR-ROUND-RECORD")["marker"]
    return (
        f"{marker} the round's observable counts\n"
        f"refusals: {refusals}\n"
        f"records-demanded: {records_demanded}\n"
        f"detector-findings: {detector_findings}\n"
        f"escalations: {escalations}\n"
        f"deployed: {deployed}\n\n"
        "Computed from the trails alone (it-36 slice H, #473) — never the build host's ledger: "
        "refusals (the runner's Needs-info/Blocked comments on the child trails), records-demanded "
        "(YR-EPIC-GATE/YR-CLOSE-HOLD raises on the epic trail), detector-findings (the close lane's "
        "own trail-shape check over the round's own trails), escalations (YR-ESCALATION records "
        f"across the round), and deployed (the latest YR-DEPLOY record on "
        f"{drift.DEPLOY_TRAIL_REPO}#{drift.DEPLOY_TRAIL_ISSUE}). The pricing judgment against "
        "attended attention stays the human's."
    )


# ── YR-CROSSOVER: this epic's own merged-PR usage vs. the strategy doc's theme budget ────────────────
def crossover_verdict(total_cost_usd: float, budget_usd) -> str:
    if not isinstance(budget_usd, (int, float)):
        return "no-budget-declared"
    return "within-budget" if total_cost_usd <= budget_usd else "over-budget"


def crossover_from_pr_usages(pr_usages: dict, budget_usd) -> dict:
    """`pr_usages`: `{"<repo>#<pr>": <tools/sources.py pr_usage result dict>}` — already-fetched, so
    this stays pure and network-free. Returns `{"cost_usd", "pr_count", "verdict"}`."""
    total = sum((u.get("cost_usd") or 0) for u in pr_usages.values())
    return {"cost_usd": total, "pr_count": len(pr_usages), "verdict": crossover_verdict(total, budget_usd)}


def crossover_body(*, cost_usd, pr_count, budget_usd, verdict, who, reg=None) -> str:
    reg = reg or records.load()
    marker = records.get(reg, "YR-CROSSOVER")["marker"]
    budget_text = f"${budget_usd:.2f}/round" if isinstance(budget_usd, (int, float)) else "none declared"
    return (
        f"{marker}\n"
        f"cost: ${cost_usd:.2f} across {pr_count} merged PR(s) (theme budget {budget_text})\n"
        f"verdict: {verdict}\n"
        f"who: {who}\n\n"
        "The crossover test's typed verdict (it-36 slice H, #473): cost is this epic's own "
        "merged-PR usage (tools/sources.py pr_usage, summed); verdict compares that cost against "
        "the strategy doc's own theme budget_usd. The pricing judgment stays the human's."
    )


def matching_theme_budget(parsed_strategy: dict, repo: str):
    """The first theme (declared order) whose `repos` names `repo` -> its `budget_usd`, or `None`
    when no theme targets this repo (mirrors `tools/design_gate.py`'s own `_matching_theme`, not
    imported — that module's theme-matching is private and this is a one-line rule, not a shared
    grammar worth coupling two sweep modules over)."""
    for theme in parsed_strategy.get("themes") or []:
        if repo in (theme.get("repos") or []):
            return theme.get("budget_usd")
    return None


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
    heading path joined by `'::'` (documentation-model.md `:278`'s own delimiter for a heading
    target's array-of-heading-texts, outermost first) -> `heading_path`, a list. A `target` of
    `none` (case-insensitive) is a declared no-op, dropped, never applied. Raises `ValueError` on a
    malformed or entirely-empty shape — a stage output this runner cannot act on is a loud stop,
    never a guessed partial apply (`tools/cross.py split_draft`'s own discipline)."""
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
    targeted PATCH (never a whole-body overwrite — documentation-model.md `:277` names exactly this
    hazard for a repeatedly-edited living reference), anchored to the document map's own `version`
    as the concurrency token (`ifMatch`); each superseded doc is stamped `status: superseded` +
    `superseded_by`, both frontmatter writes the vault client already verifies by read-back on its
    own. Returns a summary dict; raises `vault_api.VaultUnreachable` on any refused or unconfirmed
    write — a loud stop, never a partial, silently-accepted apply."""
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


def ship_walk_body(*, who, scope, reg=None) -> str:
    reg = reg or records.load()
    marker = records.get(reg, "YR-SHIP-WALK")["marker"]
    return (
        f"{marker} walked at close\n"
        f"who: {who}\n"
        f"scope: {scope}\n\n"
        "The grounding list was walked, the living reference's section updated in place through the "
        "vault client (a heading-targeted PATCH, never a whole-body overwrite), and any superseded "
        "research stamped — each write verified by its own read-back (it-36 slice H, #473)."
    )


# ── CLI: the seams close-runner.sh drives — real gh, real vault; every core above stays pure ─────────
_ROUND_QUERY = """
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    issue(number: $number) {
      body
      comments(first: 100) { nodes { body } }
      subIssues(first: 100) {
        nodes {
          number
          body
          repository { nameWithOwner }
          comments(first: 100) { nodes { body } }
          closedByPullRequestsReferences(first: 10) { nodes { number repository { nameWithOwner } } }
        }
      }
    }
  }
}
"""


def _gh(argv):
    proc = subprocess.run([os.environ.get("GH_BIN", "gh"), *argv], capture_output=True, text=True)
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
    epic_texts = [issue.get("body") or ""] + [
        c.get("body") or "" for c in ((issue.get("comments") or {}).get("nodes") or [])]
    children = (issue.get("subIssues") or {}).get("nodes") or []
    child_texts = {}
    pr_refs = []
    for c in children:
        child_repo = (c.get("repository") or {}).get("nameWithOwner") or args.repo
        key = f"{child_repo}#{c.get('number')}"
        child_texts[key] = [c.get("body") or ""] + [
            cc.get("body") or "" for cc in ((c.get("comments") or {}).get("nodes") or [])]
        for pr in ((c.get("closedByPullRequestsReferences") or {}).get("nodes") or []):
            pr_repo = (pr.get("repository") or {}).get("nameWithOwner") or child_repo
            pr_refs.append({"repo": pr_repo, "number": pr.get("number")})
    print(json.dumps({"epic_texts": epic_texts, "child_texts": child_texts, "pr_refs": pr_refs}))
    return 0


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
    ok, deploy_texts = sources.issue_trail(args.deploy_repo, str(args.deploy_issue))
    deployed = deployed_field(deploy_texts if ok else [])
    all_child_texts = [t for texts in fetched["child_texts"].values() for t in texts]
    body = round_record_body(
        refusals=count_refusals(all_child_texts),
        records_demanded=count_records_demanded(fetched["epic_texts"], reg),
        detector_findings=count_detector_findings(reg, fetched["epic_texts"], fetched["child_texts"]),
        escalations=count_escalations(fetched["epic_texts"] + all_child_texts, reg),
        deployed=deployed, reg=reg)
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
    parsed_strategy = strategy.parse_strategy(strategy_text)
    budget_usd = matching_theme_budget(parsed_strategy, args.repo)
    pr_usages = {}
    for ref in fetched.get("pr_refs") or []:
        ok, usage = sources.pr_usage(ref["repo"], str(ref["number"]))
        if ok:
            pr_usages[f"{ref['repo']}#{ref['number']}"] = usage
    result = crossover_from_pr_usages(pr_usages, budget_usd)
    body = crossover_body(cost_usd=result["cost_usd"], pr_count=result["pr_count"],
                          budget_usd=budget_usd, verdict=result["verdict"], who=args.who)
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
    body = ship_walk_body(who=args.who, scope=args.scope)
    if args.test_mode:
        print("TEST-MODE: no trail write — the record only")
        print(body)
        return 0
    _comment(_gh, repo=args.repo, issue=args.epic, body=body)
    print(f"ship-walk: YR-SHIP-WALK posted on {args.repo}#{args.epic}")
    return 0


_SUBCOMMANDS = {
    "fetch": _cli_fetch,
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
