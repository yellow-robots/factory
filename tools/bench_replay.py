#!/usr/bin/env python3
"""bench_replay — sealed-checkout replay harness + deterministic grading, no LLM (slice B of epic
yellow-robots/factory#161; slice A is `tools/bench_corpus.py`).

Given a `yr-bench-corpus/1` record and `source_repo` (an ordinary, already-provisioned local clone of
the record's repo — never touched, never a URL), `grade()`:

  1. **Seals** a fresh workdir at the record's `pre_solution_ref`: `git init` from scratch, then a
     depth-1 `git fetch` of exactly that one commit from `source_repo` (a local path — sealing needs no
     network round-trip), checked out detached. A depth-1 fetch of one commit transfers only that
     commit's own tree/blobs, so the workdir cannot hold any object "at or beyond" the source merge
     commit — that commit (`pre_solution_ref`'s child) was simply never fetched.
  2. **Verifies** the seal before any grading — the epic's one forbidden shortcut is grading an
     unverified run. Three properties, each independently checked, any failure -> `invalid-seal`, loud,
     never graded: no configured remote; exactly one commit reachable from HEAD and it IS
     `pre_solution_ref` (nothing beyond it — best-effort corroborated by confirming the source merge
     commit's own object, when derivable from `source_repo`, is absent); the GitHub credential env vars
     absent from the environment the child process will run under.
  3. Applies the candidate's patch (a stub this slice — a no-op or fixture diff; slice C wires the live
     candidate), then patches the held-out tests back **from the record, never from git** (the sealed
     workdir cannot reach them any other way).
  4. Reads `check_cmd` from the manifest in the checked-out (pre-solution) tree, provisions the check
     toolchain the way build worktrees do (`tools/dev-runner.sh`'s PATH-only pattern: the sealed workdir
     is ephemeral and has no `.venv`/`node_modules` of its own — point PATH at `source_repo`'s, already
     built), and runs it, capturing the exit code directly off the subprocess — never through a pipe.
  5. **Grades**: rc 0 -> `pass`, else `fail`, with output preserved verbatim. A check harness that could
     not even execute (rc 126/127 — a missing/broken toolchain, the same convention as `dev-runner.sh`'s
     `is_env_failure`) is `ungraded-environmental`, never a graded fail — so is any seal/provisioning
     failure before this point.

Every subprocess this module spawns for the graded run inherits one run-scoped TMPDIR, removed at
teardown (the #142 discipline, `tools/dev-runner.sh` ~:551).

CLI (stdlib-only, `tools/registry.py`'s JSON-CLI shape): `bench_replay.py grade --record <path>
--source <local-clone>`.
"""
import argparse
import collections
import datetime
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import tomllib

SCHEMA = "yr-bench-result/1"

OUTCOME_PASS = "pass"
OUTCOME_FAIL = "fail"
OUTCOME_INVALID_SEAL = "invalid-seal"
OUTCOME_UNGRADED_ENV = "ungraded-environmental"

# a sealed child process must never see a GitHub credential — the solution must be unreachable by API
# just as it is by tree (the epic's "the seal must survive its own verification" contract).
CREDENTIAL_ENV_VARS = ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN")

# a check harness that could not even execute (missing/broken toolchain) — same convention as
# tools/dev-runner.sh's is_env_failure: 126 = found-but-not-executable, 127 = command not found.
_ENV_FAILURE_RCS = (126, 127)

SealVerdict = collections.namedtuple("SealVerdict", "ok reasons")


class SealError(Exception):
    """Sealing (the git plumbing that produces the workdir) failed outright — always environmental,
    never a graded outcome."""


class ProvisionError(Exception):
    """Setup after a verified seal (manifest read, patch-back, candidate patch) failed — environmental,
    never a graded outcome."""


# --- subprocess seams (injected/overridden in tests) ----------------------------------------------------
def _run(argv, cwd=None, env=None, input=None):
    """One subprocess call; returns the completed process (never raises on a non-zero exit — callers
    decide what a given exit code means)."""
    return subprocess.run(argv, cwd=cwd, env=env, input=input, capture_output=True, text=True)


def _git(argv, cwd, run=None):
    """A git call that must succeed for sealing to proceed; raises SealError (loud, never silently
    read as a graded outcome) on any non-zero exit."""
    run = run or _run
    proc = run(["git", *argv], cwd=str(cwd))
    if proc.returncode != 0:
        raise SealError(f"git {' '.join(argv)} failed ({proc.returncode}): {proc.stderr.strip()}")
    return proc.stdout


def _utcnow_iso():
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


# --- sealing ---------------------------------------------------------------------------------------------
def seal_workdir(record, workdir, source_repo, *, run=None):
    """Produce a sealed checkout of `record["pre_solution_ref"]` in `workdir`: `git init` from scratch,
    then a depth-1 fetch of exactly that commit from `source_repo` (a LOCAL path — never a URL/remote),
    checked out detached. Leaves no remote configured; a depth-1 fetch of one commit cannot carry any
    object beyond it, so nothing at or beyond the source merge commit is ever present. Raises SealError
    on any git failure."""
    ref = record["pre_solution_ref"]
    workdir = pathlib.Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    # resolved to absolute: the fetch below runs with cwd=workdir, so a relative source_repo (as a
    # caller would naturally pass, e.g. "src") must not be interpreted relative to the wrong cwd.
    source_repo = str(pathlib.Path(source_repo).resolve())
    _git(["init", "-q"], workdir, run=run)
    _git(["fetch", "-q", "--depth", "1", source_repo, ref], workdir, run=run)
    _git(["checkout", "-q", "--detach", "FETCH_HEAD"], workdir, run=run)
    return workdir


def _find_merge_sha(source_repo, pre_solution_ref, run=None):
    """Best-effort: the commit in `source_repo` (an ordinary, full clone) whose first parent is
    `pre_solution_ref` — the source merge commit itself (a squash/merge commit has exactly one parent,
    per tools/bench_corpus.py). None if no such commit is reachable there — nothing extra to check."""
    run = run or _run
    proc = run(["git", "rev-list", "--all", "--children"], cwd=str(source_repo))
    if proc.returncode != 0:
        return None
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) > 1 and parts[0] == pre_solution_ref:
            return parts[1]
    return None


def verify_seal(workdir, pre_solution_ref, env, *, source_repo=None, run=None):
    """Independently re-check the three seal properties before any grading. Any property that fails —
    or that cannot even be read — is a reason; `ok` is true only when there are none."""
    run = run or _run
    reasons = []

    proc = run(["git", "remote"], cwd=str(workdir))
    if proc.returncode != 0:
        reasons.append(f"could not read configured remotes: {proc.stderr.strip()}")
    elif proc.stdout.strip():
        reasons.append(f"a remote is configured: {proc.stdout.strip()!r}")

    proc = run(["git", "rev-list", "HEAD"], cwd=str(workdir))
    if proc.returncode != 0:
        reasons.append(f"could not read reachable history: {proc.stderr.strip()}")
    else:
        shas = [line for line in proc.stdout.splitlines() if line.strip()]
        if shas != [pre_solution_ref]:
            reasons.append(f"more than (or other than) the pre-solution commit is reachable: {shas}")

    if source_repo is not None:
        merge_sha = _find_merge_sha(source_repo, pre_solution_ref, run=run)
        if merge_sha:
            proc = run(["git", "cat-file", "-e", merge_sha], cwd=str(workdir))
            if proc.returncode == 0:
                reasons.append(f"the source merge commit's object ({merge_sha}) is reachable in the sealed workdir")

    present = [v for v in CREDENTIAL_ENV_VARS if v in env]
    if present:
        reasons.append(f"GitHub credential env var(s) present in the child environment: {present}")

    return SealVerdict(ok=not reasons, reasons=reasons)


# --- provisioning + grading --------------------------------------------------------------------------
def _sealed_env(source_repo, tmpdir):
    """The environment the candidate/check child processes run under: no GitHub credential, a
    run-scoped TMPDIR, neutralized ambient git config (mirrors tools/dev-runner.sh's run_checks — host
    config must never make a graded run greener than a clean one), and the check toolchain provisioned
    the way build worktrees do: PATH-only, pointed at source_repo's already-built .venv/node_modules
    (the sealed workdir is ephemeral and carries neither — both are gitignored in any repo it replays)."""
    env = dict(os.environ)
    for key in CREDENTIAL_ENV_VARS:
        env.pop(key, None)
    env["TMPDIR"] = str(tmpdir)
    env["GIT_CONFIG_GLOBAL"] = "/dev/null"
    env["GIT_CONFIG_SYSTEM"] = "/dev/null"
    venv_bin = pathlib.Path(source_repo) / ".venv" / "bin"
    node_bin = pathlib.Path(source_repo) / "node_modules" / ".bin"
    env["PATH"] = os.pathsep.join(p for p in (str(venv_bin), str(node_bin), env.get("PATH", "")) if p)
    return env


def _apply_patch(workdir, patch_text, run=None):
    run = run or _run
    proc = run(["git", "apply", "--whitespace=nowarn", "-"], cwd=str(workdir), input=patch_text)
    if proc.returncode != 0:
        raise ProvisionError(f"candidate patch failed to apply: {proc.stderr.strip()}")


def _patch_back_held_out_tests(workdir, held_out_tests):
    """Write the held-out test files from the corpus record's own stored contents — the sealed
    workdir can never reach them via git, so this is the only source."""
    for entry in held_out_tests:
        path = pathlib.Path(workdir) / entry["path"]
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(entry["content"])
        except OSError as exc:
            raise ProvisionError(f"could not patch back held-out test {entry['path']}: {exc}") from exc


def _read_check_cmd(workdir):
    """`check_cmd`, read from the manifest as checked out at the pre-solution ref (never fetched or
    re-read from GitHub — the sealed tree itself IS that ref's state)."""
    manifest_path = pathlib.Path(workdir) / ".yr" / "factory.toml"
    if not manifest_path.is_file():
        raise ProvisionError("no .yr/factory.toml at the pre-solution ref")
    try:
        manifest = tomllib.loads(manifest_path.read_text())
    except (tomllib.TOMLDecodeError, OSError) as exc:
        raise ProvisionError(f"unreadable .yr/factory.toml at the pre-solution ref: {exc}") from exc
    check_cmd = manifest.get("check_cmd")
    if not check_cmd:
        raise ProvisionError("no check_cmd in the manifest at the pre-solution ref")
    return check_cmd


def _result(record, outcome, ts, *, check_cmd=None, check_rc=None, output=None, detail=None):
    return {
        "schema": SCHEMA,
        "repo": record.get("repo"),
        "issue": record.get("issue"),
        "pr": record.get("pr"),
        "outcome": outcome,
        "check_cmd": check_cmd,
        "check_rc": check_rc,
        "output": output,
        "detail": detail,
        "graded_at": ts,
    }


def grade(record, *, source_repo, workdir=None, run=None, candidate_patch=None, now=None):
    """Seal, verify, and grade one `yr-bench-corpus/1` record against `source_repo` (a local,
    already-provisioned clone of its repo). Returns a `yr-bench-result/1` dict — never raises for any
    failure this module is meant to classify (seal/provisioning/grading); those become the record's
    `outcome`. `workdir`, when given, is used as-is and left in place for inspection; otherwise a fresh
    one is created and torn down (with its run-scoped TMPDIR) before returning."""
    run = run or _run
    now = now or _utcnow_iso

    run_root = tempfile.mkdtemp(prefix="bench-replay-")
    own_workdir = workdir is None
    try:
        tmpdir = pathlib.Path(run_root) / "tmp"
        tmpdir.mkdir()
        target = pathlib.Path(workdir) if workdir else pathlib.Path(run_root) / "workdir"

        try:
            seal_workdir(record, target, source_repo, run=run)
        except (SealError, OSError) as exc:
            return _result(record, OUTCOME_UNGRADED_ENV, now(), detail=f"seal failed: {exc}")

        env = _sealed_env(source_repo, tmpdir)
        verdict = verify_seal(target, record["pre_solution_ref"], env, source_repo=source_repo, run=run)
        if not verdict.ok:
            return _result(record, OUTCOME_INVALID_SEAL, now(), detail="; ".join(verdict.reasons))

        try:
            if candidate_patch:
                _apply_patch(target, candidate_patch, run=run)
            _patch_back_held_out_tests(target, record.get("held_out_tests") or [])
            check_cmd = _read_check_cmd(target)
        except ProvisionError as exc:
            return _result(record, OUTCOME_UNGRADED_ENV, now(), detail=str(exc))

        proc = run(["bash", "-c", check_cmd], cwd=str(target), env=env)
        rc = proc.returncode
        output = (proc.stdout or "") + (proc.stderr or "")
        if rc in _ENV_FAILURE_RCS:
            return _result(record, OUTCOME_UNGRADED_ENV, now(),
                            detail=f"check command could not execute (exit {rc})",
                            check_cmd=check_cmd, check_rc=rc, output=output)
        outcome = OUTCOME_PASS if rc == 0 else OUTCOME_FAIL
        return _result(record, outcome, now(), check_cmd=check_cmd, check_rc=rc, output=output)
    finally:
        shutil.rmtree(run_root, ignore_errors=True)
        if own_workdir:
            shutil.rmtree(target, ignore_errors=True)


def _cli_grade(args):
    record = json.loads(pathlib.Path(args.record).read_text())
    patch = pathlib.Path(args.patch).read_text() if args.patch else None
    result = grade(record, source_repo=args.source, workdir=args.workdir, candidate_patch=patch)
    print(json.dumps(result))
    if args.out:
        out_path = pathlib.Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "a") as f:
            f.write(json.dumps(result) + "\n")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Sealed-checkout replay harness + deterministic grading (no LLM).")
    sub = ap.add_subparsers(dest="command", required=True)

    p_grade = sub.add_parser("grade", help="seal, verify, and grade one corpus record")
    p_grade.add_argument("--record", required=True, help="path to a yr-bench-corpus/1 record JSON file")
    p_grade.add_argument("--source", required=True, help="local git clone of the record's repo (never a URL)")
    p_grade.add_argument("--patch", default=None, help="unified-diff candidate patch to apply before grading (stub this slice)")
    p_grade.add_argument("--workdir", default=None, help="sealed workdir path (default: auto-created and torn down)")
    p_grade.add_argument("--out", default=None, help="append the yr-bench-result/1 record to this JSONL file")
    p_grade.set_defaults(func=_cli_grade)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
