#!/usr/bin/env python3
"""bench_corpus — derive the replayable benchmark corpus from a repo's merged task PRs (RFC — bench,
slice A of epic yellow-robots/factory#161).

`extract_corpus(repo, *, gh=None, ...)` is the reusable core (mirrors `tools/epic_gate.py`'s injectable
`gh(argv)` seam, so the whole decision tree is unit-testable with no live `gh`): for `owner/name`, it
enumerates merged PRs whose head branch is `task/*` and, per PR, decides eligibility and either writes a
corpus record or an exclusion row — never a guess. Eligibility is fail-closed on two independent facts:

  1. >=1 PR file matches the repo's `bench_test_globs` manifest key (read from the manifest at the
     repo's default branch — a stable, current declaration, not tied to any one PR's history). Unset or
     unmatched -> excluded, by name.
  2. `.yr/factory.toml` carries a `check_cmd` at the PRE-SOLUTION ref (the merge commit's first parent —
     deterministic, since a squash/merge commit has exactly one parent): the state of the repo just
     before this task's code landed must have had a runnable check gate. Missing manifest or missing
     `check_cmd` there -> excluded, by name.

Every manifest read follows `tools/epic_gate.py`'s `_repo_has_manifest` discipline exactly: a confirmed
HTTP 404 is real data (no manifest there — an exclusion, not a guess); any other failure (network error,
5xx, rate limit, timeout) is transient — retried with bounded backoff, and if it still fails, raises
rather than ever resolving to "excluded". Every other network read (PR list, issue body, commit parents,
file contents) retries the same way and raises on exhaustion — a transient failure always errors loudly,
never silently drops or misfiles a PR.

A corpus record (`schema: yr-bench-corpus/1`) carries everything a sealed replay needs without ever
touching git again: the source issue/PR numbers, the DoR prompt (the issue body verbatim plus the date it
was read — this tool authors no prompt, ever), the pre-solution ref, the held-out test paths AND their
file contents at the PR head (a sealed replay can't reach git history for them), the repo, and extraction
dates (the recency caveat stays readable on the record itself).

Output: `bench/corpus/<owner>--<name>/<issue>-pr<pr>.json` per eligible PR, plus one shared, append-only
`bench/corpus/exclusions.jsonl` naming every excluded PR and its reason. This PR ships the tool only —
attended runs write the corpus data.

CLI (stdlib-only, `tools/registry.py`'s JSON-CLI shape): `bench_corpus.py extract --repo owner/name`.
"""
import argparse
import datetime
import fnmatch
import json
import pathlib
import re
import subprocess
import sys
import time
import tomllib

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_OUT_DIR = ROOT / "bench" / "corpus"

SCHEMA = "yr-bench-corpus/1"

_TASK_BRANCH_RE = re.compile(r"^task/(\d+)-")
_HTTP_404_RE = re.compile(r"\b404\b")

# a couple of attempts, bounded backoff — a scan must not stall on a dead network, and a transient
# failure must never be read as a confirmed absence (see module docstring)
_PROBE_ATTEMPTS = 2
_PROBE_BACKOFF_S = 2


class ManifestProbeError(Exception):
    """Raised when every attempt at a manifest read fails for a reason other than a confirmed 404
    (network error, 5xx, rate limit, timeout). Distinct from a plain `None` result: the caller must not
    read this as "no manifest" — it should stop the whole run instead of guessing (mirrors
    `tools/epic_gate.py`'s own `ManifestProbeError`)."""


# --- default `gh` runner (the only real external; injected/overridden in tests) -----------------------
def _gh(argv):
    """Run `gh <argv...>`; return stdout text. Raises on a non-zero exit so a broken read is loud."""
    proc = subprocess.run(["gh", *argv], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"gh {' '.join(argv)} failed ({proc.returncode}): {proc.stderr.strip()}")
    return proc.stdout


def _utcnow_iso():
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_with_retry(gh, argv):
    """One `gh` read, retried with bounded backoff on any failure; raises after exhausting attempts.
    Every non-manifest network read in this tool goes through this — a transient failure must error
    loudly, never silently become an exclusion or a dropped PR."""
    last_exc = None
    for attempt in range(_PROBE_ATTEMPTS):
        try:
            return gh(argv)
        except Exception as exc:
            last_exc = exc
            if attempt + 1 < _PROBE_ATTEMPTS:
                time.sleep(_PROBE_BACKOFF_S)
    raise RuntimeError(f"gh {' '.join(argv)} failed after {_PROBE_ATTEMPTS} attempts: {last_exc}") from last_exc


def _gh_json(gh, argv):
    out = _read_with_retry(gh, argv)
    return out if isinstance(out, (dict, list)) else json.loads(out)


def _contents_argv(owner, name, path, *, ref=None):
    """argv for a `gh api` contents-endpoint read, GET-safe by construction: `-X GET` accompanies any
    `-f ref=` field, since `gh api` otherwise silently switches a fielded call to POST."""
    argv = ["api", f"repos/{owner}/{name}/contents/{path}",
            "-H", "Accept: application/vnd.github.raw"]
    if ref:
        argv += ["-X", "GET", "-f", f"ref={ref}"]
    return argv


def _manifest_at(gh, owner, name, ref=None):
    """Parsed `.yr/factory.toml` at `ref` (the default branch when `ref` is None), or None on a
    confirmed 404 — the same discipline as `tools/epic_gate.py`'s `_repo_has_manifest`: a 404 is real
    data (no manifest there); any other failure retries with backoff, then raises `ManifestProbeError`
    rather than ever guessing "absent"."""
    argv = _contents_argv(owner, name, ".yr/factory.toml", ref=ref)
    last_exc = None
    for attempt in range(_PROBE_ATTEMPTS):
        try:
            raw = gh(argv)
            text = raw if isinstance(raw, str) else json.dumps(raw)
            return tomllib.loads(text)
        except Exception as exc:
            if _HTTP_404_RE.search(str(exc)):
                return None
            last_exc = exc
            if attempt + 1 < _PROBE_ATTEMPTS:
                time.sleep(_PROBE_BACKOFF_S)
    raise ManifestProbeError(f"manifest probe failed for {owner}/{name}@{ref or 'HEAD'}: {last_exc}") from last_exc


def _issue_from_branch(head_ref):
    """The source issue number from `task/<n>-<slug>`'s grammar, or None if it doesn't match."""
    m = _TASK_BRANCH_RE.match(head_ref or "")
    return int(m.group(1)) if m else None


def _list_merged_task_prs(gh, repo, limit):
    """Every merged PR on `repo` whose head branch matches `task/*`, each tagged with its parsed issue
    number. A merged PR whose branch doesn't match the grammar is simply not part of the working set —
    never recorded as an exclusion (it was never a candidate)."""
    out = _gh_json(gh, ["pr", "list", "--repo", repo, "--state", "merged",
                        "--json", "number,headRefName,mergeCommit,headRefOid,files",
                        "--limit", str(limit)])
    prs = []
    for pr in out:
        issue = _issue_from_branch(pr.get("headRefName") or "")
        if issue is not None:
            prs.append({**pr, "issue": issue})
    return prs


def _issue_body(gh, owner, name, issue):
    out = _gh_json(gh, ["api", f"repos/{owner}/{name}/issues/{issue}"])
    return out.get("body") or ""


def _pre_solution_ref(gh, owner, name, merge_sha):
    """The merge commit's first parent — the deterministic pre-solution ref (a squash/merge commit has
    exactly one parent: the base tip just before this task's code landed)."""
    out = _gh_json(gh, ["api", f"repos/{owner}/{name}/commits/{merge_sha}"])
    parents = out.get("parents") or []
    if not parents:
        raise RuntimeError(f"merge commit {merge_sha} has no parent — cannot derive a pre-solution ref")
    return parents[0]["sha"]


def _file_content_at(gh, owner, name, path, ref):
    raw = _read_with_retry(gh, _contents_argv(owner, name, path, ref=ref))
    return raw if isinstance(raw, str) else json.dumps(raw)


def _matching_paths(files, globs):
    """PR file paths matching any of `globs` (fnmatch, case-sensitive — paths are data, not a
    filesystem, so no platform case-folding), sorted for a deterministic record."""
    paths = [f.get("path") for f in (files or []) if f.get("path")]
    return sorted(p for p in paths if any(fnmatch.fnmatchcase(p, g) for g in globs))


def _write_record(out_dir, repo, owner, name, record):
    path = out_dir / f"{owner}--{name}" / f"{record['issue']}-pr{record['pr']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n")
    return path


def _append_exclusion(out_dir, row):
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "exclusions.jsonl", "a") as f:
        f.write(json.dumps(row) + "\n")
    return row


def extract_corpus(repo, *, gh=None, now=None, out_dir=None, limit=200):
    """Derive corpus records for every eligible merged `task/*` PR on `repo` (`owner/name`); write each
    to `bench/corpus/<owner>--<name>/<issue>-pr<pr>.json` and append every exclusion, by name and
    reason, to `bench/corpus/exclusions.jsonl`. Returns `{"written": [...], "excluded": [...]}` (paths /
    exclusion rows) for the CLI and for tests to assert on directly."""
    gh = gh or _gh
    now = now or _utcnow_iso
    out_dir = pathlib.Path(out_dir) if out_dir else DEFAULT_OUT_DIR
    owner, _, name = repo.partition("/")

    manifest = _manifest_at(gh, owner, name)
    globs = (manifest or {}).get("bench_test_globs")
    if not isinstance(globs, list):
        globs = []

    written, excluded = [], []

    for pr in _list_merged_task_prs(gh, repo, limit):
        number, issue = pr["number"], pr["issue"]

        def _exclude(reason):
            row = _append_exclusion(out_dir, {
                "repo": repo, "issue": issue, "pr": number, "reason": reason, "excluded_at": now(),
            })
            excluded.append(row)

        if not globs:
            _exclude("bench_test_globs is unset for this repo")
            continue

        matched = _matching_paths(pr.get("files"), globs)
        if not matched:
            _exclude("no PR file matches bench_test_globs")
            continue

        merge_sha = (pr.get("mergeCommit") or {}).get("oid")
        if not merge_sha:
            _exclude("merged PR carries no merge commit")
            continue
        pre_solution_ref = _pre_solution_ref(gh, owner, name, merge_sha)

        pre_manifest = _manifest_at(gh, owner, name, ref=pre_solution_ref)
        if pre_manifest is None:
            _exclude("no .yr/factory.toml at the pre-solution ref")
            continue
        if not pre_manifest.get("check_cmd"):
            _exclude("no check_cmd in the manifest at the pre-solution ref")
            continue

        head_sha = pr.get("headRefOid")
        read_at = now()
        body = _issue_body(gh, owner, name, issue)
        held_out_tests = [
            {"path": p, "content": _file_content_at(gh, owner, name, p, head_sha)}
            for p in matched
        ]

        record = {
            "schema": SCHEMA,
            "repo": repo,
            "issue": issue,
            "pr": number,
            "prompt": {"body": body, "read_at": read_at},
            "pre_solution_ref": pre_solution_ref,
            "held_out_tests": held_out_tests,
            "extracted_at": now(),
        }
        written.append(str(_write_record(out_dir, repo, owner, name, record)))

    return {"written": written, "excluded": excluded}


def _cli_extract(args):
    result = extract_corpus(args.repo, out_dir=args.out, limit=args.limit)
    print(json.dumps(result))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Derive the replayable bench corpus from a repo's merged task PRs.")
    sub = ap.add_subparsers(dest="command", required=True)

    p_extract = sub.add_parser("extract", help="extract corpus records for one repo (JSON)")
    p_extract.add_argument("--repo", required=True, help="owner/name")
    p_extract.add_argument("--out", default=None, help="corpus output root (default: bench/corpus)")
    p_extract.add_argument("--limit", type=int, default=200, help="max merged PRs to scan")
    p_extract.set_defaults(func=_cli_extract)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
