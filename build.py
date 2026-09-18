#!/usr/bin/env python3
"""Build a pushed branch: clone it, run the builder on its head, push one commit back.

    uv run build.py <repository> <branch> <seed>

The request is a branch that was pushed, holding a seed at building and its tests red; the answer
is one commit pushed to that branch. The branch is cloned into a directory of the instance's own
under the `work` its configuration names, one branch, and the builder is run on the clone with the
seed's path as its goal, so the record is the builder's own, in the store, with the clone as its
checkout and the branch's head as its head. The command prints the record's path as its first
line, the builder having printed it.

What the builder cannot build is a usage error, exit 2 on stderr, before the key is read, a model
is called or a record is made: arguments that are not three; a repository git cannot read; a branch
the repository does not have; a seed the branch does not hold or one with no `## Goal`; a project
whose root has no `check.Dockerfile`; and a configuration with no `work`. Nothing is left in the
working directory by a refusal. The model and the sandbox given to `main` are passed to the
builder and to nothing else.

A green check that changed something becomes one commit on the branch: the branch's head as the
command found it is its parent, the diff is what the model left in the clone, the author and the
committer are the factory's, and the message is the seed's name, a blank line, then the one
trailer `Built-By: factory at <version>, run <stamp>`, which git's own parser reads. The version
is the instance's own, `git describe --tags --always --dirty` where this file lives, or `unknown`
when git cannot say, and never the project's. The commit is pushed to the branch it came from,
never forced; the command prints one line naming the commit by git's abbreviation and the branch,
and exits 0.
"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import builder
import instance


class GitFailed(RuntimeError):
    """git ran and exited nonzero: the message carries git's own words."""


def version() -> str:
    """The instance's own version: `git describe --tags --always --dirty` run where this file
    lives, or `unknown` when git cannot say. Never the project's."""
    try:
        done = subprocess.run(
            ["git", "describe", "--tags", "--always", "--dirty"],
            cwd=Path(__file__).resolve().parent,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            env=builder.git_env(),
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    described = done.stdout.strip() if done.returncode == 0 else ""
    return described or "unknown"


def _run(args: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """git with the caller's environment cleaned of its own GIT_* pointers, its output captured. It
    runs from `/`, never from the caller's directory: the factory's own checkout may be a worktree
    whose `.git` file points at a path that does not resolve here, and no step of a build needs it."""
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        cwd="/",
        env=env if env is not None else builder.git_env(),
    )


def _git(args: list[str], env: dict[str, str] | None = None) -> str:
    """git as `_run`, its stdout returned; a nonzero exit is a GitFailed carrying its stderr."""
    done = _run(args, env=env)
    if done.returncode != 0:
        raise GitFailed(done.stderr.strip() or f"git exited {done.returncode}")
    return done.stdout


def _first(text: str) -> str:
    """The first line of git's stderr, or empty when it said nothing."""
    lines = text.splitlines()
    return lines[0].strip() if lines else ""


def usage_error(reason: str = "") -> int:
    print("usage: build.py <repository> <branch> <seed>", file=sys.stderr)
    if reason:
        print(reason, file=sys.stderr)
    return 2


NOTE_REF = "refs/notes/factory"  # where git keeps what the factory says about a commit


def _leave_note(clone: Path, head: str, line: str) -> None:
    """The factory's note on the head a failed build was asked of: one line of the factory's own
    words under `refs/notes/factory`, added to the note a failure before it left, both kept, and
    pushed to the repository, never a branch or a tag of it. A note git cannot push is one line on
    stderr and no more: the build's own exit is what it was."""
    env = builder.store_env()
    try:
        # The note the repository already holds, so a second failure adds to it rather than
        # replacing it; a repository with none leaves nothing to read.
        _run(["-C", str(clone), "fetch", "--quiet", "origin", f"{NOTE_REF}:{NOTE_REF}"], env=env)
        shown = _run(["-C", str(clone), "notes", "--ref=factory", "show", head], env=env)
        old = shown.stdout if shown.returncode == 0 else ""
        note = f"{old.rstrip()}\n{line}\n" if old.strip() else f"{line}\n"
        _git(["-C", str(clone), "notes", "--ref=factory", "add", "-f", "-m", note, head], env=env)
        _git(["-C", str(clone), "push", "--quiet", "origin", f"{NOTE_REF}:{NOTE_REF}"], env=env)
    except (GitFailed, OSError, subprocess.SubprocessError) as e:
        print(f"{head}: the note cannot be pushed: {e}", file=sys.stderr)


def _branch_moved(repository: str, branch: str, requested: str) -> bool:
    """Whether the repository's branch now points somewhere other than the head the build was
    asked of: the mover's commit is kept and the push refused rather than overwritten."""
    done = _run(["ls-remote", "--heads", repository, f"refs/heads/{branch}"])
    if done.returncode != 0:
        return False
    for line in done.stdout.splitlines():
        if "\t" not in line:
            continue
        sha, ref = line.split("\t", 1)
        if ref.strip() == f"refs/heads/{branch}" and sha.strip() != requested:
            return True
    return False


def main(argv: list[str], model: Any = None, sandbox: Any = None) -> int:
    if len(argv) != 4 or not all(arg.strip() for arg in argv[1:4]):
        return usage_error("three arguments are needed: <repository> <branch> <seed>")
    repository, branch, seed = argv[1], argv[2], argv[3]

    # The configuration is the instance's and read before anything of the build: its `work` is
    # where the clone goes, made when the configuration is read, and a configuration without one
    # is refused naming the file and the fault.
    try:
        work = instance.work_dir()
    except (ValueError, OSError) as e:
        return usage_error(str(e))

    # The repository git can read and the branch it has, refused by name before a clone is made.
    try:
        seen = _run(["ls-remote", "--heads", repository])
    except (OSError, subprocess.SubprocessError) as e:
        return usage_error(f"{repository}: git could not run: {e}")
    if seen.returncode != 0:
        return usage_error(f"{repository}: git cannot read the repository: {_first(seen.stderr)}")
    refs = {line.split("\t", 1)[1].strip() for line in seen.stdout.splitlines() if "\t" in line}
    if f"refs/heads/{branch}" not in refs:
        return usage_error(f"{repository}: no branch {branch}")

    # A build works in a directory of its own under `work`, removed when the command ends, whatever
    # ended it, so the working directory holds nothing of a build that is over.
    build_dir = Path(tempfile.mkdtemp(dir=work, prefix="build-"))
    try:
        clone = build_dir / "checkout"
        try:
            _git(["clone", "--quiet", "--branch", branch, "--single-branch", repository, str(clone)])
        except (GitFailed, OSError, subprocess.SubprocessError) as e:
            return usage_error(f"{repository}: git cannot clone {branch}: {e}")

        # The seed's note is the branch's commit, read as the builder reads it: a path the commit
        # does not hold, or a note with no ## Goal with text under it, is refused naming the seed.
        try:
            _goal, name = builder.read_seed(clone, seed)
        except (ValueError, builder.GitError, OSError, subprocess.SubprocessError) as e:
            return usage_error(str(e))
        if name is None:
            return usage_error(f"not a seed of the branch: {seed}")

        # The check needs a check.Dockerfile at the root of the project.
        if not (clone / "check.Dockerfile").is_file():
            return usage_error(f"the project has no check.Dockerfile: {branch}")

        # The head the build was asked of: the clone's HEAD is the branch's head as the command
        # found it, the parent of the commit and the commit a failure's note is left on.
        try:
            requested = _git(["-C", str(clone), "rev-parse", "HEAD"]).strip()
        except (GitFailed, OSError, subprocess.SubprocessError) as e:
            return usage_error(f"{repository}: git cannot read the branch's head: {e}")

        # The builder runs on the clone with the seed's path; the record is its own, in the store,
        # with the clone as its checkout and the branch's head as its head. Its first printed line
        # is the record's path, and the command prints it first. Its stderr is the factory's to
        # read, captured here so the command can say its own one line of it.
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = builder.main(["builder.py", str(clone), seed], model=model, sandbox=sandbox)
        printed = out.getvalue().splitlines()
        record = Path(printed[0]) if printed else None
        if record is None:  # the builder refused before a record: its line and exit are the command's
            if err.getvalue():
                print(err.getvalue(), end="", file=sys.stderr)
            return code or 1
        print(record)

        # How the run ended, from the record's own numbers and never the model's report: a red
        # check, a green check that changed nothing, a run that was capped and one that ended in an
        # error are each an error, and never a commit that might be read as work.
        try:
            numbers = json.loads((record / "numbers.json").read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            numbers = {}
        said = err.getvalue().strip().splitlines()
        reason = said[0].strip() if said else ""
        stopped, check = numbers.get("stopped"), numbers.get("check")

        def refused(how: str) -> int:
            """A build that leaves the branch alone: the record named on stderr, the factory's note
            on the head it was asked of, and exit 1."""
            line = f"{record}: {how}"
            print(line, file=sys.stderr)
            _leave_note(clone, requested, line)
            return 1

        if stopped == "cap":
            return refused("the run was capped")
        if stopped == "error":
            return refused("the run ended in an error")
        if code != 0:  # the store would not take the record: nothing is committed or pushed
            return refused(reason or "the store would not take the record")
        if check != "green":
            return refused("the check is red" if check == "red" else "the check did not run")

        # A green check that changed nothing is an error too: nothing of the model's to answer with.
        try:
            changed = builder.dirty_paths(clone)
        except (builder.GitError, OSError, subprocess.SubprocessError) as e:
            return refused(str(e))
        if not changed:
            return refused("the check is green and nothing changed")

        # The commit is the factory's: the branch's head as the command found it is its parent and
        # the diff what the model left in the clone. The message is the seed's name, a blank line,
        # then the one trailer git reads, naming the instance's own version and the run; nothing of
        # the model's report is in it, since the report is in the record.
        message = f"{name}\n\nBuilt-By: factory at {version()}, run {record.name}"
        env = builder.store_env()
        try:
            _git(["-C", str(clone), "add", "-A"], env=env)
            _git(["-C", str(clone), "commit", "-q", "-m", message], env=env)
            short = _git(["-C", str(clone), "rev-parse", "--short", "HEAD"], env=env).strip()
            # Pushed to the branch it came from, never forced: a branch that moved meanwhile
            # refuses this push, and the command says that rather than overwrite the mover's work.
            _git(["-C", str(clone), "push", "--quiet", "origin", f"HEAD:refs/heads/{branch}"], env=env)
        except (GitFailed, OSError, subprocess.SubprocessError) as e:
            moved = _branch_moved(repository, branch, requested)
            return refused("the branch moved" if moved else str(e))
        print(f"{short} {branch}")
        return 0
    finally:
        shutil.rmtree(build_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
