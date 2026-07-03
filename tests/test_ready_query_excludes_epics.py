"""
Tests for Issue #14 — Exclude epics from the Ready build-poll so a Ready epic
never consumes build dispatch.

Derived from the Issue #14 acceptance criteria (the spec), not from the
implementation internals. These are text/JSON-property assertions against the
two deploy/ artifacts n8n runs each poll tick: deploy/ready-query.graphql and
deploy/n8n-dispatch.json. No runtime n8n execution is needed.
"""

import json
import pathlib
import shutil
import subprocess
import tempfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
QUERY = ROOT / "deploy" / "ready-query.graphql"
WORKFLOW = ROOT / "deploy" / "n8n-dispatch.json"


def _query_text():
    return QUERY.read_text(encoding="utf-8")


def _workflow_data():
    return json.loads(WORKFLOW.read_text(encoding="utf-8"))


def _node(data, node_id):
    for node in data["nodes"]:
        if node["id"] == node_id:
            return node
    raise AssertionError(f"n8n-dispatch.json has no node with id={node_id!r}")


def test_standalone_query_requests_issue_type():
    text = _query_text()
    assert "issueType" in text, \
        "ready-query.graphql does not fetch issueType — the poll can't see epic type"
    assert "issueType { name }" in text, \
        "ready-query.graphql fetches issueType but not its name field"


def test_embedded_query_requests_issue_type():
    data = _workflow_data()
    ghquery = _node(data, "ghquery")
    body = ghquery["parameters"]["jsonBody"]
    assert "issueType" in body, \
        "the embedded query in the 'GitHub: Ready items' http node does not request issueType"


def test_filter_code_references_issue_type():
    data = _workflow_data()
    filter_node = _node(data, "filter")
    js_code = filter_node["parameters"]["jsCode"]
    assert "issueType" in js_code, \
        "the 'Extract Ready issue numbers' Code node does not reference issueType"


def test_filter_code_excludes_feature_and_epic():
    data = _workflow_data()
    filter_node = _node(data, "filter")
    js_code = filter_node["parameters"]["jsCode"]
    assert "Feature" in js_code, \
        "the build-poll filter does not exclude issueType 'Feature'"
    assert "Epic" in js_code, \
        "the build-poll filter does not exclude issueType 'Epic'"


def test_filter_code_still_checks_status_and_state():
    """The new type exclusion must be in addition to, not instead of, the
    existing Status=Ready + state=OPEN conditions."""
    data = _workflow_data()
    filter_node = _node(data, "filter")
    js_code = filter_node["parameters"]["jsCode"]
    assert "'Ready'" in js_code
    assert "'OPEN'" in js_code


def test_filter_code_is_not_a_task_only_allowlist():
    """The exclusion must be an epic-hosting-type blocklist (Feature/Epic),
    not a 'Task'-only allowlist — an allowlist would also drop untyped and
    Bug items, breaking repos that opt out of Issue Types."""
    data = _workflow_data()
    filter_node = _node(data, "filter")
    js_code = filter_node["parameters"]["jsCode"]
    assert "=== 'Task'" not in js_code and '=== "Task"' not in js_code, \
        "the filter allowlists issueType === 'Task' instead of blocklisting Feature/Epic"
    assert "includes('Task')" not in js_code, \
        "the filter allowlists Task by inclusion instead of blocklisting Feature/Epic"


def _run_filter_jscode(fixture_nodes):
    """Actually execute the 'Extract Ready issue numbers' Code node's jsCode
    (via Node) against a fixture GraphQL response, mirroring how n8n invokes
    it: $json is the item's input data, and the code body returns the output
    items. This checks real filtering behavior, not just substring presence."""
    data = _workflow_data()
    filter_node = _node(data, "filter")
    js_code = filter_node["parameters"]["jsCode"]
    fixture = {
        "data": {
            "organization": {
                "projectV2": {"items": {"nodes": fixture_nodes}}
            }
        }
    }
    harness = (
        "const $json = " + json.dumps(fixture) + ";\n"
        "function __run() {\n" + js_code + "\n}\n"
        "console.log(JSON.stringify(__run()));\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(harness)
        script_path = f.name
    try:
        result = subprocess.run(
            ["node", script_path], capture_output=True, text=True, timeout=10
        )
    finally:
        pathlib.Path(script_path).unlink(missing_ok=True)
    assert result.returncode == 0, (
        f"filter jsCode raised an error under Node:\n{result.stderr}"
    )
    return json.loads(result.stdout)


def _fixture_node(number, *, status, state, issue_type, repo="yellow-robots/factory"):
    content = {
        "number": number,
        "state": state,
        "repository": {"nameWithOwner": repo},
    }
    if issue_type is not None:
        content["issueType"] = {"name": issue_type}
    else:
        content["issueType"] = None
    return {
        "content": content,
        "status": {"name": status} if status is not None else None,
    }


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not on PATH")
def test_filter_behavior_excludes_epics_but_passes_other_ready_open_items():
    fixture_nodes = [
        _fixture_node(101, status="Ready", state="OPEN", issue_type="Feature"),
        _fixture_node(102, status="Ready", state="OPEN", issue_type="Epic"),
        _fixture_node(103, status="Ready", state="OPEN", issue_type="Task"),
        _fixture_node(104, status="Ready", state="OPEN", issue_type="Bug"),
        _fixture_node(105, status="Ready", state="OPEN", issue_type=None),
        _fixture_node(106, status="Backlog", state="OPEN", issue_type="Task"),
        _fixture_node(107, status="Ready", state="CLOSED", issue_type="Task"),
    ]

    dispatched = _run_filter_jscode(fixture_nodes)
    dispatched_issues = sorted(item["json"]["issue"] for item in dispatched)

    assert dispatched_issues == [103, 104, 105], (
        "expected only the untyped/Task/Bug Ready+OPEN items to dispatch, "
        f"got {dispatched_issues}"
    )
