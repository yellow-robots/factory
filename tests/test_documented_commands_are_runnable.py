"""A command the canon tells a human to type must be typeable.

Provenance: 2026-09-06. The owner ran the release act's own documented invocation and got
`-bash: tools/release.py: Permission denied` — the file carries `#!/usr/bin/env python3` but was
committed 100644, while every sibling operator script is 100755. Nothing caught it because no
*machine* caller uses the bare form: `process.toml`'s `release-validation` evaluator declares
`argv = ["python3", "tools/release.py", "validate", …]`, and the suite drives `release.main()`
in-process. The release is also the one act whose actor is exclusively the human
(`plugin.release.validated`, `agent_may = "propose"`), so it is the one command an agent never
types and never discovers broken.

The guard is derived from the tree, never an enumerated list of tools (the it-27 anti-recurrence
shape): whatever a tracked markdown file names at the START of a command line — the position where
a reader is meant to type it — must be a tracked file committed executable. Documenting a new
operator command therefore drags its mode along, and the next missing execute bit fails here rather
than under a human's fingers.

Deliberately NOT asserted: that every shebanged file is executable. Most shebanged tracked files in
this repo are committed non-executable, and nearly all of those are imported modules
(`tools/predicates.py`, `tools/sources.py`, `tools/records.py`, …) that merely carry a shebang;
demanding +x on those would be noise, and the mode of a module nobody invokes is not a fact about
anything. (No count is quoted here on purpose: it would rot with the next tool added, and the rule
below does not depend on it.)

Scope note: the scan is content-blind over every tracked markdown file, so a line that merely *looks*
like a command in the first position — a `diff --stat` paste, a bare path listing — would be read as
one. Today no such line exists. If one ever appears, the fix is to exclude that file or reword the
line, not to weaken the rule.
"""
import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent

# The command position: start of line (a fenced block's own lines, or an indented continuation),
# optionally behind a shell prompt, naming a path in one of the repo's executable-script homes.
# A prose mention never sits here — prose lines open with a word, a backtick, `-`, `|` or `#`.
COMMAND_LINE = re.compile(r"^[ \t]*(?:\$ +)?((?:tools|hooks|qa)/[\w.-]+(?:/[\w.-]+)*)(?=[ \t]|$)")


def _tracked_modes():
    """{path: git mode} for every tracked file — the COMMITTED mode, not the checkout's, so a
    stray local chmod can neither create nor hide a finding."""
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-s"],
                         capture_output=True, text=True, check=True).stdout
    modes = {}
    for line in out.splitlines():
        meta, _, path = line.partition("\t")
        modes[path] = meta.split()[0]
    return modes


def _offenders(modes, found):
    """{tool: (mode, sites)} for every documented command whose file is tracked but not committed
    executable. One home for the predicate, so the guard's own teeth test exercises the real thing
    rather than a re-implementation of it."""
    return {tool: (modes[tool], sites) for tool, sites in found.items()
            if tool in modes and modes[tool] != "100755"}


def _documented_commands(modes, root=None):
    """{tool path: [doc:line, …]} over every tracked markdown file. Modes come from the index and
    content from the working tree: a tracked file missing from the checkout is skipped rather than
    raising, and a file's staged content is what a reader of this branch would see. `root` is the
    tree the paths are read under — injected only by the teeth test, which scans a synthetic doc."""
    root = ROOT if root is None else root
    found = {}
    for path in modes:
        if not path.endswith(".md"):
            continue
        try:
            text = (root / path).read_text(encoding="utf-8")
        except OSError:                                  # a tracked file absent from the checkout
            continue
        for n, line in enumerate(text.splitlines(), 1):
            m = COMMAND_LINE.match(line)
            if m:
                found.setdefault(m.group(1), []).append(f"{path}:{n}")
    return found


def test_every_documented_command_names_a_tracked_file():
    modes = _tracked_modes()
    found = _documented_commands(modes)
    missing = {tool: sites for tool, sites in found.items() if tool not in modes}
    assert not missing, (
        "a doc gives a command for a path that is not tracked in this repo — the reader cannot run "
        f"it: {missing}")


def test_every_documented_command_is_committed_executable():
    """The finding itself: a documented command whose file is not executable cannot be typed."""
    modes = _tracked_modes()
    found = _documented_commands(modes)
    assert found, "no documented commands found at all — the scan is broken, not the repo"
    offenders = _offenders(modes, found)
    assert not offenders, (
        "a doc tells a human to type these commands, but the files are not committed executable "
        f"(mode 100755), so the bare invocation dies with 'Permission denied': {offenders}")


def test_the_release_act_is_executable():
    """The specific regression, pinned by name as well as by the general rule above: the release act
    is the one act reserved exclusively for the human, so it is the one whose bare invocation no
    agent ever exercises."""
    modes = _tracked_modes()
    assert modes.get("tools/release.py") == "100755", (
        "tools/release.py must be committed executable: it carries a shebang, it is the human's own "
        f"act, and the canon gives its command in bare form (got {modes.get('tools/release.py')!r})")


def test_the_scan_would_catch_a_non_executable_documented_command(tmp_path):
    """The guard's own teeth, through the REAL scan rather than a re-implementation of it: drop a
    synthetic doc whose command line names a file this repo genuinely commits non-executable, run
    the same `_documented_commands` + `_offenders` pair the guard above runs, and require a finding.
    Without this, a green run could mean 'the regex matched nothing' instead of 'no offenders'."""
    modes = _tracked_modes()
    victim = next((p for p, m in sorted(modes.items())
                   if m == "100644" and p.startswith("tools/") and p.endswith(".py")), None)
    assert victim, "expected at least one non-executable tools/*.py module to test the rule against"

    doc = tmp_path / "synthetic.md"
    doc.write_text(f"Run it like this:\n\n```\n{victim} --some-flag\n```\n", encoding="utf-8")
    found = _documented_commands({doc.name: "100644"}, root=tmp_path)
    assert victim in found, f"the real scan did not read {victim!r} as a command"

    offenders = _offenders(modes, found)
    assert victim in offenders and offenders[victim][0] == "100644", (
        "the offender predicate did not flag a documented command that is not executable")


def test_prose_mentions_are_not_read_as_commands():
    """A backticked name in a sentence or a repo-map table row is not a command position — the rule
    must not demand +x of every module the canon merely names."""
    for prose in ("`tools/predicates.py` is the closed predicate vocabulary.",
                  "| `tools/records.py` | the record registry |",
                  "- `tools/sources.py` — the only I/O home",
                  "See tools/wall.py for the shim.",
                  "#  tools/process.py in a comment"):
        assert COMMAND_LINE.match(prose) is None, f"prose read as a command: {prose!r}"


def test_a_command_line_is_recognised_in_every_shape_the_canon_uses():
    for cmd, want in (
        ("tools/dev-runner.sh <issue#> --repo <owner/name>", "tools/dev-runner.sh"),
        ("  tools/deploy.sh --who human      # or --who attended-agent", "tools/deploy.sh"),
        ("$ tools/release.py ship --version 1.3.0", "tools/release.py"),
        ("hooks/deliver.sh", "hooks/deliver.sh"),
    ):
        m = COMMAND_LINE.match(cmd)
        assert m and m.group(1) == want, f"{cmd!r} did not yield {want!r}"
