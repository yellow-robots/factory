"""Packaging guard for issue #51 — the plugin ships the manual, registers nothing.

The factory skill is distributed as a git-sourced plugin (the plugin is the whole
repo), so anything the *tracked tree* ships rides along to every consumer machine.
These tests guard the tracked tree (`git ls-files`), not the working filesystem:
`.gitignore` invites a legitimate untracked local `.mcp.json`, so a filesystem
existence check would fail on a dev machine while CI stayed green.
"""

import json
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _tracked_files():
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files"],
        check=True, capture_output=True, text=True,
    )
    return out.stdout.splitlines()


def test_plugin_version_is_current():
    """The single canonical plugin-version pin (issue #149) — a plugin release
    edits this one assertion, not one per doc-test file."""
    data = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert data["version"] == "0.9.4", \
        f".claude-plugin/plugin.json version is {data['version']!r}, expected '0.9.4'"


def test_repo_ships_no_mcp_json_at_root():
    tracked = _tracked_files()
    assert ".mcp.json" not in tracked


def test_no_tracked_mcp_json_anywhere():
    tracked = _tracked_files()
    mcp_files = [p for p in tracked if pathlib.PurePosixPath(p).name == ".mcp.json"]
    assert mcp_files == []


def test_plugin_manifest_registers_no_mcp_servers():
    tracked = _tracked_files()
    plugin_dir_files = [p for p in tracked if p.startswith(".claude-plugin/")]
    assert plugin_dir_files, "expected a tracked .claude-plugin/ manifest directory"

    for relpath in plugin_dir_files:
        path = ROOT / relpath
        if path.suffix != ".json":
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "mcpServers" not in data, f"{relpath} registers an MCP server"
        assert "mcp_servers" not in data, f"{relpath} registers an MCP server"


def test_plugin_manifest_has_no_mcp_config_file():
    tracked = _tracked_files()
    plugin_dir_files = [p for p in tracked if p.startswith(".claude-plugin/")]
    mcp_config_files = [p for p in plugin_dir_files if "mcp" in pathlib.PurePosixPath(p).name.lower()]
    assert mcp_config_files == []
