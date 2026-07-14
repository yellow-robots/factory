#!/usr/bin/env python3
"""bench_replay — sealed-checkout replay harness + deterministic grading, no LLM, plus the live
candidate replay driver (slice B + slice C of epic yellow-robots/factory#161; slice A is
`tools/bench_corpus.py`).

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
  3. Applies the candidate's patch (a stub — a no-op or fixture diff; `run_candidate()` below wires the
     live candidate instead of a canned patch), then patches the held-out tests back **from the record,
     never from git** (the sealed workdir cannot reach them any other way).
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

`run_candidate()` is the slice C driver: it seals + verifies exactly as above, then runs the candidate
LIVE through the pipeline's own cold-stage seam instead of applying a canned patch — the implement
stage's own system charter and prompt shape (`STAGE_CHARTER` and `IMPL_SYS`, `tools/dev-runner.sh:779`
and `:782` at 425e0bb; the implement stage's task-prompt prefix at `:791`), `claude -p` with the tool
allowlist `Read Edit Write Bash`, the corpus prompt as the task body, the model id resolved through
`tools/registry.py`, inside the sealed workdir with the GitHub credential withheld (the same
`_sealed_env` the check run already uses). On a clean exit it captures the usage envelope the
`capture_stage_usage` pattern does (`tools/dev-runner.sh:690-698`): the CLI's single JSON result
envelope, never rewriting a log on disk here since nothing is written outside the sealed workdir and
`bench/results/` — the envelope is read straight off the captured subprocess output. A non-zero exit
whose output matches the runner's own quota/rate-limit signature discipline (`QUOTA_SIGNATURES`,
`tools/dev-runner.sh:651`) — and any other non-zero exit, since no trustworthy candidate state exists to
grade — is `ungraded-environmental`, never a graded fail. It then grades exactly as `grade()` does and
appends one `yr-bench-result/1` row (outcome, model, task, repo, the four raw usage counts, and the
weighted total computed from `tools/stage_usage.py`'s imported weights) to
`bench/results/<run-date>-<config>.jsonl`. Attended host CLI only: no dispatch coupling, no `/build`
path, no capacity-slot claims.

CLI (stdlib-only, `tools/registry.py`'s JSON-CLI shape): `bench_replay.py grade --record <path>
--source <local-clone>`; `bench_replay.py run-candidate --record <path> --source <local-clone> --config
<registry-entry-name>`.
"""
import argparse
import collections
import datetime
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib

# sibling-module import (never `tools.`-prefixed): run as a bare script (`tools/bench_replay.py ...`),
# sys.path[0] is already `tools/` — the same discipline tools/epic_gate.py documents for `import dispatch`.
import registry
import stage_usage

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_RESULTS_DIR = ROOT / "bench" / "results"

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

# --- the candidate stage: the implement stage's own charter + prompt shape, verbatim -------------------
# Copied from tools/dev-runner.sh's STAGE_CHARTER (:779) and implement-stage IMPL_SYS (:782) at 425e0bb —
# located by NAME, per the epic's citation-pin discipline (numbers are a written-against snapshot, not a
# promise the lines never move). The candidate must see exactly what a real implement stage sees, so this
# is copied verbatim rather than paraphrased.
STAGE_CHARTER = "You are one stage of an automated pipeline, running in one fresh worktree cut from the base ref. The pipeline holds builder ≠ verifier: the implementer writes production code and never authors the committed test suite; the tester writes tests only, derived from the acceptance criteria and never from the implementation's internals; the reviewer changes nothing. Write only inside this worktree — never the host. Make no git or board writes; the runner owns them (the reviewer's read-only git, e.g. diffing staged changes, is the one carve-out). Never weaken a gate: do not edit checks, CI configuration, .yr/factory.toml, or any test you were told not to touch. Manage processes by PID only — pattern-kills such as PKILL -f or PGREP -f are forbidden, because a stage's own command environment can contain the task text, and a pattern match can hit and kill the stage's own process instead of its intended target. If the task cannot be done within these rules, stop and say so — a Blocked run is a correct outcome, not a failure to route around. This pipeline produces a pull request only; deploy and host work are never a stage's. In-stage verification exercises only the scope this stage's change touches, with targeted tests; the repo's full check suite belongs to the deterministic check gate and server CI, never an in-stage inner loop. A stage works in the foreground only: it never polls, watches, or sleeps on external state, and when it cannot proceed it stops and says so. The task in front of it is self-contained by design; standing documents are not this stage's context."
IMPL_SYS = "You are the IMPLEMENTER stage of an automated dev pipeline. Implement the task so it satisfies every acceptance criterion. Write PRODUCTION CODE ONLY — do not author the committed test suite (an independent tester stage does that)."
# the implement stage's own task-prompt prefix (tools/dev-runner.sh:791) — the corpus prompt (the
# record's stored DoR issue body) fills the same %s the real SPEC would.
TASK_PREFIX = "Implement the task below against its acceptance criteria. Make the minimal, clean change.\n\n"
ALLOWED_TOOLS = ("Read", "Edit", "Write", "Bash")
DEFAULT_EFFORT = "high"

# a claude -p candidate that dies with one of these in its output is an ENVIRONMENTAL ceiling
# (account/rate limit), never a graded fail — same signature discipline as tools/dev-runner.sh's
# QUOTA_SIGNATURES (:651), overridable the same way (a single grep -E-style alternation).
_DEFAULT_QUOTA_SIGNATURES = "usage limit|rate limit|quota|overloaded|429"


def _is_quota_failure(text):
    pattern = os.environ.get("QUOTA_SIGNATURES", _DEFAULT_QUOTA_SIGNATURES)
    return bool(re.search(pattern, text, re.IGNORECASE))

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


# --- the candidate replay driver (slice C) ------------------------------------------------------------
def resolve_candidate_model(config, *, registry_path=None):
    """The candidate's model id, resolved through tools/registry.py exactly the way the runner resolves
    the build role (`role="build"`, task-value override) — `config` names a `models.toml` entry the same
    way a task's per-task model override would, so an unregistered or unranked name fails the same way it
    would in a real build (`KeyError`, loud — never silently guessed)."""
    data = registry.load(registry_path)
    return registry.resolve(data, "build", task_value=config)


def run_candidate_stage(workdir, task_prompt, model_id, *, claude_bin=None, effort=None, env=None, run=None):
    """One `claude -p` call in `workdir`, shaped exactly like `tools/dev-runner.sh`'s `run_stage` for the
    implement stage: the charter appended to the system prompt, the task prompt on stdin (never argv —
    the same self-pattern-match discipline `run_stage` observes), the same tool allowlist, a single JSON
    result envelope. Returns the completed subprocess (never raises on a non-zero exit)."""
    run = run or _run
    claude_bin = claude_bin or os.environ.get("CLAUDE_BIN") or "claude"
    effort = effort or os.environ.get("EFFORT") or DEFAULT_EFFORT
    sys_prompt = f"{IMPL_SYS}\n\n{STAGE_CHARTER}"
    argv = [claude_bin, "-p", "--model", model_id, "--effort", effort,
            "--permission-mode", "bypassPermissions", "--append-system-prompt", sys_prompt,
            "--allowedTools", *ALLOWED_TOOLS,
            "--setting-sources", "project", "--strict-mcp-config", "--output-format", "json"]
    return run(argv, cwd=str(workdir), env=env, input=task_prompt)


def _candidate_result(record, outcome, ts, *, config, model, usage=None, check_cmd=None, check_rc=None,
                       output=None, detail=None):
    """Like `_result`, plus the candidate configuration (config label, resolved model id, a stable task
    identifier) and the usage envelope: the four raw counts (missing -> 0, an envelope-less environmental
    death carries no usage) and the weighted total, computed from `tools/stage_usage.py`'s own
    `WEIGHTED_TOTAL_WEIGHTS` — imported, never re-typed."""
    usage = usage or {}
    issue, pr = record.get("issue"), record.get("pr")
    counts = {key: usage.get(key, 0) for key in stage_usage.WEIGHTED_TOTAL_WEIGHTS}
    weighted_total = round(sum(counts[key] * w for key, w in stage_usage.WEIGHTED_TOTAL_WEIGHTS.items()))
    return {
        "schema": SCHEMA,
        "config": config,
        "model": model,
        "task": f"{issue}-pr{pr}" if issue is not None and pr is not None else None,
        "repo": record.get("repo"),
        "issue": issue,
        "pr": pr,
        "outcome": outcome,
        **counts,
        "weighted_total": weighted_total,
        "check_cmd": check_cmd,
        "check_rc": check_rc,
        "output": output,
        "detail": detail,
        "graded_at": ts,
    }


def _append_result_row(out_dir, config, ts, result):
    """Append one `yr-bench-result/1` row to `bench/results/<run-date>-<config>.jsonl` (`run-date` is the
    result's own `graded_at` date) — the only write this driver ever makes outside the sealed workdir."""
    if not config or "/" in config or config in (".", ".."):
        raise ValueError(f"invalid --config value: {config!r}")
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    run_date = ts.split("T", 1)[0]
    path = out_dir / f"{run_date}-{config}.jsonl"
    with open(path, "a") as f:
        f.write(json.dumps(result) + "\n")
    return path


def run_candidate(record, *, source_repo, config, workdir=None, run=None, now=None, registry_path=None,
                   claude_bin=None, effort=None, out_dir=None):
    """Seal + verify exactly as `grade()` does, then run the candidate LIVE through the cold-stage seam
    (`run_candidate_stage`) instead of applying a canned patch: the model edits the sealed workdir
    directly via Read/Edit/Write/Bash, exactly as a real implement stage would. On a clean exit, grade
    exactly as `grade()` does (held-out tests patched back, `check_cmd` run, rc -> pass/fail, 126/127 ->
    ungraded-environmental). A non-zero candidate exit is always `ungraded-environmental` — a quota/
    rate-limit signature names an environmental ceiling; any other non-zero exit leaves no trustworthy
    candidate state to grade either. Every outcome appends one `yr-bench-result/1` row to
    `bench/results/<run-date>-<config>.jsonl` and returns that row."""
    run = run or _run
    now = now or _utcnow_iso
    out_dir = out_dir or DEFAULT_RESULTS_DIR

    model_id = resolve_candidate_model(config, registry_path=registry_path)["id"]

    def emit(outcome, **kw):
        result = _candidate_result(record, outcome, now(), config=config, model=model_id, **kw)
        _append_result_row(out_dir, config, result["graded_at"], result)
        return result

    run_root = tempfile.mkdtemp(prefix="bench-candidate-")
    own_workdir = workdir is None
    try:
        tmpdir = pathlib.Path(run_root) / "tmp"
        tmpdir.mkdir()
        target = pathlib.Path(workdir) if workdir else pathlib.Path(run_root) / "workdir"

        try:
            seal_workdir(record, target, source_repo, run=run)
        except (SealError, OSError) as exc:
            return emit(OUTCOME_UNGRADED_ENV, detail=f"seal failed: {exc}")

        env = _sealed_env(source_repo, tmpdir)
        verdict = verify_seal(target, record["pre_solution_ref"], env, source_repo=source_repo, run=run)
        if not verdict.ok:
            return emit(OUTCOME_INVALID_SEAL, detail="; ".join(verdict.reasons))

        try:
            # read BEFORE the candidate ever touches the tree — a candidate must never be able to
            # weaken its own check by rewriting the manifest (mirrors the STAGE_CHARTER it just ran under).
            check_cmd = _read_check_cmd(target)
        except ProvisionError as exc:
            return emit(OUTCOME_UNGRADED_ENV, detail=str(exc))

        task_prompt = TASK_PREFIX + ((record.get("prompt") or {}).get("body") or "")
        try:
            proc = run_candidate_stage(target, task_prompt, model_id, claude_bin=claude_bin,
                                        effort=effort, env=env, run=run)
        except OSError as exc:
            return emit(OUTCOME_UNGRADED_ENV, detail=f"candidate stage failed to start: {exc}")

        candidate_log = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0:
            if _is_quota_failure(candidate_log):
                detail = f"candidate stage hit a quota/rate-limit signature (exit {proc.returncode})"
            else:
                detail = f"candidate stage failed (exit {proc.returncode})"
            return emit(OUTCOME_UNGRADED_ENV, detail=detail, output=candidate_log)

        envelope = stage_usage.find_result_envelope(candidate_log)
        usage = stage_usage.usage_record(envelope, stage="candidate", model=model_id) if envelope else {}

        try:
            _patch_back_held_out_tests(target, record.get("held_out_tests") or [])
        except ProvisionError as exc:
            return emit(OUTCOME_UNGRADED_ENV, usage=usage, detail=str(exc))

        proc = run(["bash", "-c", check_cmd], cwd=str(target), env=env)
        rc = proc.returncode
        output = (proc.stdout or "") + (proc.stderr or "")
        if rc in _ENV_FAILURE_RCS:
            return emit(OUTCOME_UNGRADED_ENV, usage=usage, check_cmd=check_cmd, check_rc=rc, output=output,
                        detail=f"check command could not execute (exit {rc})")
        outcome = OUTCOME_PASS if rc == 0 else OUTCOME_FAIL
        return emit(outcome, usage=usage, check_cmd=check_cmd, check_rc=rc, output=output)
    finally:
        shutil.rmtree(run_root, ignore_errors=True)
        if own_workdir:
            shutil.rmtree(target, ignore_errors=True)


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


def _cli_run_candidate(args):
    record = json.loads(pathlib.Path(args.record).read_text())
    result = run_candidate(record, source_repo=args.source, config=args.config, workdir=args.workdir,
                            registry_path=args.registry, out_dir=args.out_dir,
                            claude_bin=args.claude_bin, effort=args.effort)
    print(json.dumps(result))
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

    p_run = sub.add_parser("run-candidate", help="run the candidate live via claude -p inside the sealed workdir, grade, and append a yr-bench-result/1 row")
    p_run.add_argument("--record", required=True, help="path to a yr-bench-corpus/1 record JSON file")
    p_run.add_argument("--source", required=True, help="local git clone of the record's repo (never a URL)")
    p_run.add_argument("--config", required=True, help="models.toml entry name for the candidate (resolved via tools/registry.py)")
    p_run.add_argument("--registry", default=None, help="path to models.toml (default: tools/registry.py's own default)")
    p_run.add_argument("--workdir", default=None, help="sealed workdir path (default: auto-created and torn down)")
    p_run.add_argument("--out-dir", default=None, help="bench/results output root (default: bench/results)")
    p_run.add_argument("--claude-bin", default=None, help="claude CLI to invoke (default: $CLAUDE_BIN or 'claude')")
    p_run.add_argument("--effort", default=None, help="--effort value for the candidate stage (default: $EFFORT or 'high')")
    p_run.set_defaults(func=_cli_run_candidate)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
