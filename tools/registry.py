#!/usr/bin/env python3
"""registry — stdlib loader for the factory's model registry (models.toml).

Reads the registry from the factory's own deployed checkout — the file beside this loader — never
from a git ref: the factory's working tree *is* its deployment (the same trust already extended to
tools/dev-runner.sh, which is invoked straight out of the checkout). Dependency-free (stdlib
`tomllib` only, matching tools/textutil.py's style) and tolerant of unknown keys, so later additive
fields (per-role `effort`, `auto_merge`, ...) don't break older callers.

Exposes: load(), validate(), resolve_name()/resolve(), rank_check() — and a JSON CLI (`resolve`,
`validate`) for the runner to shell to, the same shell-to-python3 seam it already uses for a target
repo's .yr/factory.toml (tools/dev-runner.sh:87-96).
"""
import argparse
import json
import pathlib
import sys
import tomllib

REGISTRY_PATH = pathlib.Path(__file__).resolve().parent.parent / "models.toml"

_REQUIRED_ENTRY_FIELDS = ("id", "provider", "rank", "quota_pool")


def load(path=None):
    """Parse and return the registry as a dict. Defaults to the shipped models.toml beside this
    file — the factory's deployed checkout, never a git ref."""
    p = pathlib.Path(path) if path else REGISTRY_PATH
    with open(p, "rb") as f:
        return tomllib.load(f)


def _entries(data):
    return data.get("models") or {}


def _roles(data):
    return data.get("roles") or {}


def _stage_tiers(data):
    return _roles(data).get("stage_tiers") or {}


def price_for_id(data, model_id):
    """The registered `input_price_per_mtok` for a model id (never a registry name — the ledger's
    per-stage records are tagged with the resolved id, e.g. 'claude-sonnet-5'), or None when the id
    names no entry, or names one with no price set. Never raises — an unpriceable model is a null
    read, not an error."""
    if not model_id:
        return None
    for entry in _entries(data).values():
        if entry.get("id") == model_id:
            return entry.get("input_price_per_mtok")
    return None


def rank_check(build_entry, review_entry):
    """True iff the reviewer is never weaker than the build: both entries ranked, same provider,
    and review.rank >= build.rank. Missing entries or ranks, or a cross-provider pair, fail closed."""
    if not build_entry or not review_entry:
        return False
    b_rank, r_rank = build_entry.get("rank"), review_entry.get("rank")
    if not isinstance(b_rank, int) or isinstance(b_rank, bool):
        return False
    if not isinstance(r_rank, int) or isinstance(r_rank, bool):
        return False
    if build_entry.get("provider") != review_entry.get("provider"):
        return False
    return r_rank >= b_rank


def resolve_name(data, role, task_value=None, manifest_value=None):
    """Resolve a role ('build'/'review') to an entry name. Precedence: per-task override > per-repo
    manifest value > the registry's per-role default."""
    for value in (task_value, manifest_value):
        if value:
            return value
    return _roles(data).get(role)


def resolve(data, role, task_value=None, manifest_value=None):
    """Resolve a role to its full entry (plus its resolved 'name'). Raises KeyError if the
    resolved name has no matching registry entry."""
    name = resolve_name(data, role, task_value, manifest_value)
    entry = _entries(data).get(name)
    if entry is None:
        raise KeyError(f"unknown model '{name}' for role '{role}'")
    return {"name": name, **entry}


def validate(data):
    """Return a list of human-readable error strings (empty = the registry is self-consistent).

    Checks: every entry has id/provider/rank/quota_pool; no two entries in the same provider share
    a rank; the default build/review pair satisfies rank_check(); every roles.stage_tiers reference
    names an existing entry and does not exceed the default build entry's rank.
    """
    errors = []
    entries = _entries(data)

    seen_ranks = {}  # provider -> {rank: [names sharing it]}
    for name, entry in entries.items():
        missing = [f for f in _REQUIRED_ENTRY_FIELDS if entry.get(f) is None]
        if missing:
            errors.append(f"entry '{name}' is missing required field(s): {', '.join(missing)}")
            continue
        provider, rank = entry["provider"], entry["rank"]
        seen_ranks.setdefault(provider, {}).setdefault(rank, []).append(name)

    for provider, by_rank in seen_ranks.items():
        for rank, names in by_rank.items():
            if len(names) > 1:
                errors.append(
                    f"provider '{provider}' has {len(names)} entries sharing rank {rank}: "
                    f"{', '.join(sorted(names))}"
                )

    roles = _roles(data)
    build_name, review_name = roles.get("build"), roles.get("review")
    build_entry, review_entry = entries.get(build_name), entries.get(review_name)
    if build_entry is None:
        errors.append(f"roles.build names missing entry '{build_name}'")
    if review_entry is None:
        errors.append(f"roles.review names missing entry '{review_name}'")
    if build_entry is not None and review_entry is not None and not rank_check(build_entry, review_entry):
        errors.append(
            f"default build/review pair fails the rank check: build='{build_name}' review='{review_name}'"
        )

    build_rank = build_entry.get("rank") if build_entry else None
    for tier_name, entry_name in _stage_tiers(data).items():
        tier_entry = entries.get(entry_name)
        if tier_entry is None:
            errors.append(f"roles.stage_tiers.{tier_name} names missing entry '{entry_name}'")
            continue
        tier_rank = tier_entry.get("rank")
        if isinstance(build_rank, int) and isinstance(tier_rank, int) and tier_rank > build_rank:
            errors.append(
                f"roles.stage_tiers.{tier_name} ('{entry_name}', rank {tier_rank}) "
                f"exceeds the build rank ({build_rank})"
            )

    return errors


def _cli_resolve(args):
    data = load(args.registry)
    try:
        entry = resolve(data, args.role, args.task or None, args.manifest or None)
    except KeyError as e:
        print(json.dumps({"error": str(e)}))
        return 1
    print(json.dumps(entry))
    return 0


def _cli_pool_for_id(args):
    """Resolve a model id to its registry entry's quota_pool (the pool->credential seam, issue #40).

    Looked up by id (not name) because the runner calls stages with resolved ids (BUILD_ID/REVIEW_ID/
    a stage-tier id), and a raw operator-override id never matches a registry entry. No match -> {}
    (exit 0, not an error) so the caller falls back to the ambient default credential."""
    data = load(args.registry)
    for name, entry in _entries(data).items():
        if entry.get("id") == args.id:
            print(json.dumps({"name": name, "quota_pool": entry.get("quota_pool")}))
            return 0
    print(json.dumps({}))
    return 0


def _cli_price_for_id(args):
    """Resolve a model id to its registry entry's input_price_per_mtok (JSON; {} if unknown/unpriced,
    exit 0 either way — the same 'no match is not an error' shape as pool-for-id)."""
    data = load(args.registry)
    for name, entry in _entries(data).items():
        if entry.get("id") == args.id:
            print(json.dumps({"name": name, "input_price_per_mtok": entry.get("input_price_per_mtok")}))
            return 0
    print(json.dumps({}))
    return 0


def _cli_stage_tier(args):
    """Resolve a stage's tier entry when roles.stage_tiers names one, else signal "no tier" ({}).

    The runner shells to this to decide a repair stage's model: a set tier runs the stage at that
    entry; no tier falls the stage back to the resolved build id. Kept separate from `resolve` so a
    missing tier is an empty object (exit 0), not an error."""
    data = load(args.registry)
    name = _stage_tiers(data).get(args.stage)
    if not name:
        print(json.dumps({}))
        return 0
    entry = _entries(data).get(name)
    if entry is None:
        print(json.dumps({"error": f"stage tier '{args.stage}' names unknown model '{name}'"}))
        return 1
    print(json.dumps({"name": name, **entry}))
    return 0


def _cli_validate(args):
    data = load(args.registry)
    errors = validate(data)
    print(json.dumps({"valid": not errors, "errors": errors}))
    return 0 if not errors else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="Resolve/validate the factory's model registry.")
    ap.add_argument("--registry", default=None, help="path to models.toml (default: shipped file)")
    sub = ap.add_subparsers(dest="command", required=True)

    p_resolve = sub.add_parser("resolve", help="resolve a role to its model entry (JSON)")
    p_resolve.add_argument("--role", required=True, help="role name, e.g. build or review")
    p_resolve.add_argument("--task", default="", help="per-task override value")
    p_resolve.add_argument("--manifest", default="", help="per-repo manifest value")
    p_resolve.set_defaults(func=_cli_resolve)

    p_stage = sub.add_parser("stage-tier", help="resolve a stage's tier entry if the registry sets one (JSON; {} if none)")
    p_stage.add_argument("--stage", required=True, help="stage name, e.g. check_repair or review_repair")
    p_stage.set_defaults(func=_cli_stage_tier)

    p_pool = sub.add_parser("pool-for-id", help="resolve a model id to its entry's quota_pool (JSON; {} if unknown)")
    p_pool.add_argument("--id", required=True, help="model id, e.g. claude-sonnet-5")
    p_pool.set_defaults(func=_cli_pool_for_id)

    p_price = sub.add_parser("price-for-id", help="resolve a model id to its entry's input_price_per_mtok (JSON; {} if unknown)")
    p_price.add_argument("--id", required=True, help="model id, e.g. claude-sonnet-5")
    p_price.set_defaults(func=_cli_price_for_id)

    p_validate = sub.add_parser("validate", help="validate registry self-consistency (JSON)")
    p_validate.set_defaults(func=_cli_validate)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
