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

Deliberately NOT asserted: that every shebanged file is executable. 31 of the repo's 44 shebanged
tracked files are non-executable, and almost all are imported modules (`tools/predicates.py`,
`tools/sources.py`, `tools/records.py`, …) that merely carry a shebang; demanding +x on those would
be noise, and the mode of a module nobody invokes is not a fact about anything.
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


def _documented_commands(modes):
    """{tool path: [doc:line, …]} over every tracked markdown file."""
    found = {}
    for path in modes:
        if not path.endswith(".md"):
            continue
        try:
            text = (ROOT / path).read_text(encoding="utf-8")
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
    offenders = {tool: (modes[tool], sites) for tool, sites in found.items()
                 if tool in modes and modes[tool] != "100755"}
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


def test_the_scan_would_catch_a_non_executable_documented_command():
    """The guard's own teeth: prove the rule fires on a doc line naming a file this repo commits
    non-executable, so a green run means 'no offenders', never 'the regex matched nothing'."""
    modes = _tracked_modes()
    victim = next((p for p, m in sorted(modes.items())
                   if m == "100644" and p.startswith("tools/") and p.endswith(".py")), None)
    assert victim, "expected at least one non-executable tools/*.py module to test the rule against"
    line = f"{victim} --some-flag"
    m = COMMAND_LINE.match(line)
    assert m and m.group(1) == victim, f"the command-position regex failed to match {line!r}"
    assert modes[victim] != "100755"            # so the assertion in the test above would fire


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
