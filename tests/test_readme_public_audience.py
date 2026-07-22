"""
Tests for Issue #266 — README refresh for the public audience.

Derived from the Issue #266 acceptance criteria (the spec), not from the
implementation:

  - the "What's here" map names the shipped surfaces the current tree holds
    that the pre-task map omitted, and stays consistent with AGENTS.md's own
    Repo map at merge time;
  - the consumer list names every registered product repo (gilda joins
    yellow-robots and website);
  - the license is named (MIT), and the README states the public read path
    (AGENTS.md / docs/rfcs / the skill) vs what runs host-side only
    (dispatch, n8n, the runner);
  - no host-residue strings (usernames, gateway IPs, docker network names)
    survive in README.md.

No test here restates AGENTS.md content into assertions by copy — the
Repo map consistency check is derived dynamically from AGENTS.md itself, so
it keeps tracking "at merge time" rather than pinning today's wording.
"""

import re
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
AGENTS = ROOT / "AGENTS.md"
LICENSE = ROOT / "LICENSE"


def _readme_text():
    assert README.exists(), "README.md is missing"
    return README.read_text(encoding="utf-8")


def _agents_text():
    assert AGENTS.exists(), "AGENTS.md is missing"
    return AGENTS.read_text(encoding="utf-8")


def _readme_section(heading):
    text = _readme_text()
    match = re.search(rf"## {re.escape(heading)}\n(.*?)(?=\n## |\Z)", text, re.DOTALL)
    assert match, f"README.md is missing a '## {heading}' section"
    return match.group(1)


def _readme_intro():
    """Text before the first '## ' heading — the opening pitch paragraphs."""
    text = _readme_text()
    match = re.search(r"\A(.*?)\n## ", text, re.DOTALL)
    assert match, "README.md has no '## ' headings after its intro"
    return match.group(1)


def _agents_repo_map_section():
    text = _agents_text()
    match = re.search(r"## Repo map\n\n(.*?)\n\n---", text, re.DOTALL)
    assert match, "AGENTS.md is missing a '## Repo map' section"
    return match.group(1)


def _agents_repo_map_paths():
    """Every backtick-quoted path in AGENTS.md's Repo map table, first column only."""
    paths = []
    for line in _agents_repo_map_section().splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = line.split("|")
        if len(cells) < 3:
            continue
        first_cell = cells[1]
        paths.extend(re.findall(r"`([^`]+)`", first_cell))
    assert paths, "could not extract any paths from AGENTS.md's Repo map table"
    return paths


# ---------------------------------------------------------------------------
# Criterion: the "What's here" map names the shipped surfaces the current
# tree holds that today's map omits
# ---------------------------------------------------------------------------

def test_whats_here_names_the_previously_omitted_surfaces():
    section = _readme_section("What's here")
    for path in [
        "tools/merge_shadow.py",
        "models.toml",
        "tools/registry.py",
        "tools/ledger.py",
        "tools/stage_usage.py",
        "tools/bench_corpus.py",
        "tools/bench_replay.py",
        "tools/verdict_diff.py",
        "qa/",
    ]:
        assert path in section, \
            f"README.md 'What's here' map is missing the shipped surface {path!r}"


def test_whats_here_consistent_with_agents_repo_map_at_merge_time():
    """Every path AGENTS.md's Repo map documents must be traceable from the
    README (directly in 'What's here', or via its explicit pointer to the
    full AGENTS.md map) — derived dynamically so this keeps holding as
    AGENTS.md's Repo map grows, not just against today's snapshot."""
    readme_text = _readme_text()
    missing = [p for p in _agents_repo_map_paths() if p not in readme_text]
    assert not missing, (
        "README.md does not mention these paths that AGENTS.md's Repo map "
        f"documents: {missing!r}"
    )


def test_whats_here_points_to_the_full_agents_repo_map():
    section_start = _readme_text().index("## What's here")
    tail = _readme_text()[section_start:]
    assert re.search(r"AGENTS\.md.*Repo map|Repo map.*AGENTS\.md", tail), \
        "README.md's 'What's here' section should point readers to AGENTS.md's full Repo map"


def test_whats_here_covers_every_tracked_top_level_tool():
    """Cross-check against the tracked tree, not just AGENTS.md: every
    tools/*.py and tools/*.sh file git actually ships should be named
    somewhere in README (directly, or by the AGENTS.md map it points to)."""
    import subprocess

    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "tools/"],
        capture_output=True, text=True, check=True,
    ).stdout
    tracked = [line.strip() for line in out.splitlines() if line.strip()]
    assert tracked, "git ls-files tools/ returned nothing — repo checkout looks wrong"

    readme_text = _readme_text()
    agents_text = _agents_text()
    missing = [
        p for p in tracked
        if p not in readme_text and p not in agents_text
    ]
    assert not missing, (
        "these tracked tools/ files are named in neither README.md nor the "
        f"AGENTS.md map it points to: {missing!r}"
    )


# ---------------------------------------------------------------------------
# Criterion: the consumer list names every registered product repo
# ---------------------------------------------------------------------------

def test_consumer_list_names_every_registered_product_repo():
    intro = _readme_intro()
    for repo in ["yellow-robots", "website", "gilda"]:
        assert repo in intro, \
            f"README.md's opening consumer list is missing the registered product repo {repo!r}"


# ---------------------------------------------------------------------------
# Criterion: the license is named (MIT), and the public read path is stated
# ---------------------------------------------------------------------------

def test_license_file_is_mit():
    assert LICENSE.exists(), "repo root is missing a LICENSE file"
    assert "MIT License" in LICENSE.read_text(encoding="utf-8"), \
        "LICENSE file does not read as the MIT License"


def test_readme_names_the_license_as_mit():
    text = _readme_text()
    assert re.search(r"\bMIT\b", text), "README.md never names the MIT license"
    assert "LICENSE" in text, "README.md does not link to the LICENSE file"


def test_readme_states_the_public_read_path():
    text = _readme_text()
    for readable in ["AGENTS.md", "docs/rfcs", "skill"]:
        assert readable in text, \
            f"README.md does not tell a public visitor that {readable!r} is readable"


def test_readme_states_what_runs_host_side_only():
    text = _readme_text()
    assert re.search(r"host.side", text, re.IGNORECASE), \
        "README.md does not mark anything as running host-side only"
    for host_only in ["dispatch", "n8n", "dev-runner"]:
        assert host_only in text, \
            f"README.md's host-side-only explanation is missing {host_only!r}"


# ---------------------------------------------------------------------------
# Criterion: no host-residue strings survive in README.md
# ---------------------------------------------------------------------------

def test_readme_has_no_known_host_residue_strings():
    """These are the concrete residue strings the sibling pre-public sweep
    (#265) found and scrubbed from deploy/DISPATCH.md and
    deploy/dispatch.env.example: a unix username, the docker bridge gateway
    IP, and the docker network name / neighbouring-service name that gave
    it away."""
    text = _readme_text()
    for residue in ["jbrey", "172.19.", "caddy_caddy-net", "Joam"]:
        assert residue not in text, \
            f"README.md leaks the host-residue string {residue!r}"


def test_readme_has_no_private_gateway_ip_addresses():
    text = _readme_text()
    private_ipv4 = re.compile(
        r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
        r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"
        r"|192\.168\.\d{1,3}\.\d{1,3})\b"
    )
    matches = private_ipv4.findall(text)
    assert not matches, f"README.md contains private/gateway IP address(es): {matches!r}"


def test_readme_has_no_bare_home_username_paths():
    text = _readme_text()
    matches = re.findall(r"/home/(\w+)", text)
    leaked = [m for m in matches if not m.upper().startswith("REPLACE")]
    assert not leaked, f"README.md contains a literal /home/<user> path: {leaked!r}"
