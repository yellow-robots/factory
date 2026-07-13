"""Tests for the model registry (models.toml) and its loader (tools/registry.py).

Derived from the issue #34 acceptance criteria, not from the loader's internals: a
self-consistency check over the *shipped* registry, resolution-precedence tests, and
rank-check tests. Uses only the loader's public surface (load/validate/resolve/rank_check).
"""
import copy
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import registry
from tools.registry import load, validate, resolve, resolve_name, rank_check


# ---------------------------------------------------------------------------
# The registry file itself
# ---------------------------------------------------------------------------

def test_registry_file_lives_at_repo_root():
    assert (ROOT / "models.toml").is_file()


def test_registry_header_records_upper_pipeline_convention():
    text = (ROOT / "models.toml").read_text(encoding="utf-8")
    header = "\n".join(
        line for line in text.splitlines() if line.lstrip().startswith("#")
    ).lower()
    assert "strategy" in header or "upper" in header
    assert "opus" in header or "strongest" in header


def test_loader_reads_shipped_registry_beside_itself_by_default():
    # REGISTRY_PATH must resolve next to tools/registry.py, not some git-ref checkout.
    assert registry.REGISTRY_PATH == ROOT / "models.toml"
    assert registry.REGISTRY_PATH.is_file()
    data = load()
    assert "models" in data
    assert "roles" in data


# ---------------------------------------------------------------------------
# Self-consistency of the shipped registry
# ---------------------------------------------------------------------------

def test_shipped_registry_has_sonnet_and_opus_entries():
    data = load()
    entries = data["models"]
    assert entries["sonnet"]["id"] == "claude-sonnet-5"
    assert entries["opus"]["id"] == "claude-opus-4-8"


def test_shipped_registry_default_roles_are_sonnet_build_opus_review():
    data = load()
    assert data["roles"]["build"] == "sonnet"
    assert data["roles"]["review"] == "opus"


def test_shipped_registry_default_pair_passes_rank_check():
    data = load()
    entries = data["models"]
    build_entry = entries[data["roles"]["build"]]
    review_entry = entries[data["roles"]["review"]]
    assert rank_check(build_entry, review_entry) is True


def test_shipped_registry_every_entry_has_required_fields():
    data = load()
    for name, entry in data["models"].items():
        for field in ("id", "provider", "rank", "quota_pool"):
            assert entry.get(field) is not None, f"{name} missing {field}"


def test_shipped_registry_ranks_distinct_within_provider():
    data = load()
    seen = {}
    for name, entry in data["models"].items():
        key = (entry["provider"], entry["rank"])
        assert key not in seen, f"{name} shares rank with {seen.get(key)}"
        seen[key] = name


def test_shipped_registry_stage_tier_refs_exist_and_do_not_exceed_build_rank():
    data = load()
    entries = data["models"]
    build_rank = entries[data["roles"]["build"]]["rank"]
    stage_tiers = data.get("roles", {}).get("stage_tiers", {})
    for tier_name, entry_name in stage_tiers.items():
        assert entry_name in entries, f"stage tier {tier_name} names missing entry {entry_name}"
        assert entries[entry_name]["rank"] <= build_rank


def test_shipped_registry_validates_with_no_errors():
    data = load()
    assert validate(data) == []


# ---------------------------------------------------------------------------
# resolve() / resolve_name(): precedence per-task > per-repo > registry default
# ---------------------------------------------------------------------------

def test_resolve_falls_back_to_registry_default_when_nothing_else_given():
    data = load()
    assert resolve_name(data, "build") == "sonnet"
    assert resolve_name(data, "review") == "opus"


def test_resolve_env_value_overrides_default():
    data = load()
    assert resolve_name(data, "build", env_value="opus") == "opus"


def test_resolve_manifest_value_overrides_env_and_default():
    data = load()
    assert resolve_name(data, "build", manifest_value="opus", env_value="sonnet") == "opus"


def test_resolve_task_value_overrides_manifest_and_env():
    data = load()
    name = resolve_name(
        data, "review", task_value="sonnet", manifest_value="opus", env_value="opus"
    )
    assert name == "sonnet"


def test_resolve_returns_full_entry_including_resolved_name():
    data = load()
    entry = resolve(data, "build")
    assert entry["name"] == "sonnet"
    assert entry["id"] == "claude-sonnet-5"


def test_resolve_unknown_name_raises_key_error():
    data = load()
    try:
        resolve(data, "build", task_value="nonexistent-model")
    except KeyError:
        pass
    else:
        raise AssertionError("expected KeyError for an unknown model name")


# ---------------------------------------------------------------------------
# rank_check(): the reviewer is never weaker — review >= build, same provider, both ranked
# (issue #139: relaxed from strict review > build so an equal-rank pair, e.g. two independent
# instances of the top-ranked model, can pass; a weaker reviewer still fails closed)
# ---------------------------------------------------------------------------

def test_rank_check_true_when_review_strictly_outranks_build_same_provider():
    build = {"provider": "anthropic", "rank": 30}
    review = {"provider": "anthropic", "rank": 40}
    assert rank_check(build, review) is True


def test_rank_check_true_when_ranks_equal_same_provider():
    """An equal-rank same-provider pair passes — the bar is 'never weaker', not 'strictly stronger'."""
    build = {"provider": "anthropic", "rank": 30}
    review = {"provider": "anthropic", "rank": 30}
    assert rank_check(build, review) is True


def test_rank_check_false_when_inverted():
    """review rank strictly below build rank still fails, exactly as before the relaxation."""
    build = {"provider": "anthropic", "rank": 40}
    review = {"provider": "anthropic", "rank": 30}
    assert rank_check(build, review) is False


def test_rank_check_false_when_cross_provider():
    build = {"provider": "anthropic", "rank": 30}
    review = {"provider": "other", "rank": 40}
    assert rank_check(build, review) is False


def test_rank_check_false_when_cross_provider_and_ranks_equal():
    """Equal ranks across different providers are still not comparable — fails closed."""
    build = {"provider": "anthropic", "rank": 30}
    review = {"provider": "other", "rank": 30}
    assert rank_check(build, review) is False


def test_rank_check_false_when_build_unranked():
    build = {"provider": "anthropic", "rank": None}
    review = {"provider": "anthropic", "rank": 40}
    assert rank_check(build, review) is False


def test_rank_check_false_when_review_unranked():
    build = {"provider": "anthropic", "rank": 30}
    review = {"provider": "anthropic", "rank": None}
    assert rank_check(build, review) is False


def test_rank_check_false_when_either_entry_missing():
    review = {"provider": "anthropic", "rank": 40}
    assert rank_check(None, review) is False
    assert rank_check({"provider": "anthropic", "rank": 30}, None) is False


def test_rank_check_false_when_rank_is_bool_typed():
    """bool is a subclass of int in Python — a bool-typed rank must still fail closed, even where the
    raw comparison would otherwise pass (e.g. True >= True)."""
    build = {"provider": "anthropic", "rank": True}
    review = {"provider": "anthropic", "rank": True}
    assert rank_check(build, review) is False
    build = {"provider": "anthropic", "rank": True}
    review = {"provider": "anthropic", "rank": 30}
    assert rank_check(build, review) is False
    build = {"provider": "anthropic", "rank": 30}
    review = {"provider": "anthropic", "rank": True}
    assert rank_check(build, review) is False


# ---------------------------------------------------------------------------
# rank_check() docstring: every surface stating the contract must state the NEW one (issue #139)
# ---------------------------------------------------------------------------

def test_rank_check_docstring_states_the_never_weaker_contract():
    doc = rank_check.__doc__ or ""
    assert "review.rank >= build.rank" in doc or ">= build.rank" in doc
    assert "never weaker" in doc.lower()
    assert "strictly" not in doc.lower()
    assert "review.rank > build.rank" not in doc


# ---------------------------------------------------------------------------
# validate(): each failure mode from the acceptance criteria, on synthetic data
# ---------------------------------------------------------------------------

def _base_data():
    return {
        "models": {
            "sonnet": {"id": "claude-sonnet-5", "provider": "anthropic", "rank": 30, "quota_pool": "anthropic-main"},
            "opus": {"id": "claude-opus-4-8", "provider": "anthropic", "rank": 40, "quota_pool": "anthropic-main"},
        },
        "roles": {"build": "sonnet", "review": "opus"},
    }


def test_validate_passes_on_well_formed_data():
    assert validate(_base_data()) == []


def test_validate_fails_when_default_pair_fails_rank_check():
    data = copy.deepcopy(_base_data())
    data["roles"] = {"build": "opus", "review": "sonnet"}  # inverted
    errors = validate(data)
    assert errors


def test_validate_fails_when_stage_tier_names_missing_entry():
    data = copy.deepcopy(_base_data())
    data["roles"]["stage_tiers"] = {"check_repair": "does-not-exist"}
    errors = validate(data)
    assert any("does-not-exist" in e or "check_repair" in e for e in errors)


def test_validate_fails_when_stage_tier_exceeds_build_rank():
    data = copy.deepcopy(_base_data())
    data["models"]["overpowered"] = {
        "id": "claude-overpowered", "provider": "anthropic", "rank": 35, "quota_pool": "anthropic-main"
    }
    data["roles"]["stage_tiers"] = {"check_repair": "overpowered"}  # 35 > build rank 30
    errors = validate(data)
    assert errors


def test_validate_fails_when_two_entries_share_a_rank_in_one_provider():
    data = copy.deepcopy(_base_data())
    data["models"]["sonnet2"] = {
        "id": "claude-sonnet-5-again", "provider": "anthropic", "rank": 30, "quota_pool": "anthropic-main"
    }
    errors = validate(data)
    assert errors


def test_validate_fails_when_entry_omits_a_required_field():
    for missing_field in ("id", "provider", "rank", "quota_pool"):
        data = copy.deepcopy(_base_data())
        del data["models"]["sonnet"][missing_field]
        errors = validate(data)
        assert errors, f"expected validate() to fail with missing '{missing_field}'"


def test_validate_allows_same_rank_across_different_providers():
    # rank only orders WITHIN one provider — the same rank in a different provider is fine.
    data = copy.deepcopy(_base_data())
    data["models"]["other-model"] = {
        "id": "some-other-model", "provider": "other", "rank": 30, "quota_pool": "other-main"
    }
    errors = validate(data)
    assert errors == []


def test_validate_tolerates_unknown_keys():
    # additive fields (e.g. per-role effort, auto_merge) must not break validation.
    data = copy.deepcopy(_base_data())
    data["models"]["sonnet"]["effort"] = "high"
    data["roles"]["build_effort"] = "high"
    errors = validate(data)
    assert errors == []


# ---------------------------------------------------------------------------
# CLI surface: JSON resolve/validate, shelled to like the runner's other seams
# ---------------------------------------------------------------------------

def _run_cli(*args):
    return subprocess.run(
        [sys.executable, str(ROOT / "tools" / "registry.py"), *args],
        capture_output=True, text=True,
    )


def test_cli_validate_on_shipped_registry_exits_zero():
    result = _run_cli("validate")
    assert result.returncode == 0
    assert '"valid": true' in result.stdout.replace(" ", "") or '"valid":true' in result.stdout.replace(" ", "")


def test_cli_resolve_build_defaults_to_sonnet():
    result = _run_cli("resolve", "--role", "build")
    assert result.returncode == 0
    assert "claude-sonnet-5" in result.stdout


def test_cli_resolve_task_override_wins():
    result = _run_cli("resolve", "--role", "build", "--task", "opus")
    assert result.returncode == 0
    assert "claude-opus-4-8" in result.stdout


# ---------------------------------------------------------------------------
# pool-for-id: the pool->credential seam (issue #40) — resolve a model id to its quota_pool
# ---------------------------------------------------------------------------

def test_cli_pool_for_id_known_model_returns_its_quota_pool():
    result = _run_cli("pool-for-id", "--id", "claude-sonnet-5")
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["name"] == "sonnet"
    assert data["quota_pool"] == "anthropic-main"


def test_cli_pool_for_id_unknown_model_returns_empty_object():
    result = _run_cli("pool-for-id", "--id", "not-a-real-model")
    assert result.returncode == 0
    assert json.loads(result.stdout) == {}
