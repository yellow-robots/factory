"""Acceptance tests for issue #35 — split the runner into build and review roles with a
fail-closed rank gate.

Derived from the CRITERIA (the spec), not the runner's internals. Reuses the stubbed harness in
tests/test_dev_runner.py (the stage-aware `claude`/`gh`/check stubs, the read-only `--dry-run` seam,
and the real-git happy-path helpers) and adds ONE new stub: a `claude` that records the `--model`
each stage was launched with, so we can prove the build role runs implement/test/repair and the
review role runs the reviewer at the review rank.

Covered criteria:
  * two roles resolved from the registry: build (implement/test/repair) + review (reviewer/round);
  * precedence per role: per-task > per-repo(manifest) > registry default, env override atop;
  * `model:` (build) and `review_model:` (review) body selectors — same bare-line, case-insensitive parser;
  * `model`/`review_model` manifest keys, read from the base ref;
  * a stage-tiered repair stage runs at its tier; the reviewer never runs below the review rank;
  * unknown name (task body OR manifest) -> Backlog+Needs-info before claiming, comment, no stage;
  * a ranked pair that is inverted or cross-provider -> Needs-info, naming the pair;
  * an equal-rank pair builds;
  * a raw unregistered id supplied ONLY via the operator env override runs unranked, no bounce;
  * MODEL/HARD_MODEL env tiers are retired (ignored);
  * additive dry-run JSON: `model` == resolved build id, plus `build`/`review` {name,id,provider,rank};
  * AGENTS.md documents the registry-as-model-surface, `review_model`, the retired env pair, the convention record.

Runs under `.venv/bin/python -m pytest tests/ -q` (system python3 works too — no third-party deps).
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import test_dev_runner as base  # the shared stub harness (gh/claude/check stubs + helpers)
import claude_fake  # tests/harness/claude_fake.py — the classifier's one legal home

ROOT = base.ROOT


# ---------------------------------------------------------------------------
# A claude stub that RECORDS the --model each stage was launched with, alongside its usual
# stage-aware behaviour. DERIVED from the shared classifier (tests/harness/claude_fake.CLAUDE_STUB)
# via .replace(): a model-capture preamble is spliced in before the case block, and a recording line
# is spliced in right after the case block reads — locating both insertion points by their exact
# text, never retyping the classification patterns themselves.
# ---------------------------------------------------------------------------
_MODEL_RECORD_PREAMBLE = r'''model=""; prev=""
for a in "$@"; do
  [ "$prev" = "--model" ] && model="$a"
  prev="$a"
done
'''

REC_CLAUDE_STUB = claude_fake.CLAUDE_STUB.replace(
    'case "$args" in\n', _MODEL_RECORD_PREAMBLE + 'case "$args" in\n', 1,
).replace(
    'esac\nexit 0\n',
    'esac\n'
    '[ -n "${STUB_STAGE_MODELS:-}" ] && printf \'%s %s\\n\' "$(tail -n1 "$STUB_TIMELINE" 2>/dev/null)" "$model" >> "$STUB_STAGE_MODELS"\n'
    'exit 0\n',
    1,
)


def _rec_stubs(binp):
    """Install gh + check from the shared harness, but a model-recording claude."""
    binp.mkdir(parents=True, exist_ok=True)
    base._exec(binp / "gh", base.GH_STUB)
    base._exec(binp / "claude", REC_CLAUDE_STUB)
    base._exec(binp / "check.sh", base.CHECK_STUB)


def _stage_models(tmp):
    """Parse $STUB_STAGE_MODELS into {STAGE: [model-id, ...]} in call order."""
    p = tmp / "stage_models"
    out = {}
    if p.exists():
        for line in p.read_text().splitlines():
            stage, _, model = line.partition(" ")
            out.setdefault(stage, []).append(model)
    return out


def _write_manifest(tmp, name="mrepo", **fields):
    """A minimal repo dir carrying a .yr/factory.toml (dry-run/bounce never touches git, so no
    git init is needed — the runner falls back to catting the working-tree manifest). A leading
    comment line is always present: with no fields at all, a bare "\\n" reads back as an EMPTY string
    through `$(cat ...)`, which the admission wall (issue #125) can't tell apart from no manifest."""
    repo = tmp / name
    (repo / ".yr").mkdir(parents=True, exist_ok=True)
    body = "\n".join(["# seeded by the test harness"] + [f'{k} = "{v}"' for k, v in fields.items()]) + "\n"
    (repo / ".yr" / "factory.toml").write_text(body)
    return repo


def _env(tmp, binp, **kw):
    """Wraps `base._env`, defaulting BASE_REPO to a shared onboarded-but-key-less manifest dir (issue
    #125's admission wall bounces any repo with no `.yr/factory.toml` at all) — a no-op for any caller
    that sets its own BASE_REPO (explicitly, or via `base._real`) right after, since that simply
    overwrites this default."""
    env = base._env(tmp, binp, **kw)
    env.setdefault("BASE_REPO", str(_write_manifest(tmp, name="mrepo-default")))
    return env


def _registry_file(tmp, text, name="reg.toml"):
    p = tmp / name
    p.write_text(text)
    return p


# A two-provider registry (adds an openai entry) for the cross-provider intake test.
TWO_PROVIDER_REGISTRY = '''
[models.sonnet]
id = "claude-sonnet-5"
provider = "anthropic"
rank = 30
quota_pool = "anthropic-main"

[models.opus]
id = "claude-opus-4-8"
provider = "anthropic"
rank = 40
quota_pool = "anthropic-main"

[models.gptx]
id = "gpt-x"
provider = "openai"
rank = 50
quota_pool = "openai-main"

[roles]
build = "sonnet"
review = "opus"
'''

# A registry with a stage tier for check_repair (haiku, rank 20 <= build rank 30).
STAGE_TIER_REGISTRY = '''
[models.haiku]
id = "claude-haiku-4-5"
provider = "anthropic"
rank = 20
quota_pool = "anthropic-main"

[models.sonnet]
id = "claude-sonnet-5"
provider = "anthropic"
rank = 30
quota_pool = "anthropic-main"

[models.opus]
id = "claude-opus-4-8"
provider = "anthropic"
rank = 40
quota_pool = "anthropic-main"

[roles]
build = "sonnet"
review = "opus"

[roles.stage_tiers]
check_repair = "haiku"
'''


# ===========================================================================
# Additive dry-run JSON shape: model == build id, plus build/review objects
# ===========================================================================

def test_dryrun_json_is_additive_build_and_review_objects(tmp_path):
    """The dry-run JSON keeps `model` = the resolved BUILD id (back-compat) and ADDS `build` and
    `review` objects, each carrying name/id/provider/rank from the registry."""
    binp = tmp_path / "bin"; base._stubs(binp)
    r = base._run(["7", "--repo", "test/repo", "--dry-run"], _env(tmp_path, binp))
    assert r.returncode == 0, r.stderr
    d = json.loads(r.stdout)
    # additive `model` remains = the resolved build id
    assert d["model"] == "claude-sonnet-5"
    # new role objects
    assert d["build"] == {"name": "sonnet", "id": "claude-sonnet-5", "provider": "anthropic", "rank": 30}
    assert d["review"] == {"name": "opus", "id": "claude-opus-4-8", "provider": "anthropic", "rank": 40}
    # `model` mirrors the build object's id exactly (the additive contract)
    assert d["model"] == d["build"]["id"]
    assert d["ready"] is True


def test_dryrun_default_roles_are_registry_defaults(tmp_path):
    """With no task/manifest/env selection, both roles fall back to the registry's per-role default
    (build=sonnet, review=opus)."""
    binp = tmp_path / "bin"; base._stubs(binp)
    r = base._run(["7", "--repo", "test/repo", "--dry-run"], _env(tmp_path, binp))
    d = json.loads(r.stdout)
    assert d["build"]["name"] == "sonnet" and d["review"]["name"] == "opus"


# ===========================================================================
# Body selectors: model: (build) + review_model: (review), same bare-line parser
# ===========================================================================

def test_dryrun_review_model_body_selects_review_role(tmp_path):
    """`review_model:` in the body selects the review role (here sonnet, distinct from the default
    opus), using the same bare-line parser as `model:`. The build role is untouched (default sonnet)."""
    binp = tmp_path / "bin"; base._stubs(binp)
    env = _env(tmp_path, binp, body="### Acceptance criteria\n- [ ] x\n\nreview_model: sonnet\n")
    r = base._run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    d = json.loads(r.stdout)
    assert d["review"]["name"] == "sonnet" and d["review"]["id"] == "claude-sonnet-5"
    assert d["build"]["name"] == "sonnet"          # build role unaffected by review_model:
    assert d["model"] == "claude-sonnet-5"         # `model` = build id


def test_dryrun_body_model_is_the_build_selector(tmp_path):
    """`model:` in the body selects the BUILD role (opus here). review stays at the default opus,
    an equal-rank pair that still builds."""
    binp = tmp_path / "bin"; base._stubs(binp)
    env = _env(tmp_path, binp, body="### Acceptance criteria\n- [ ] x\n\nmodel: opus\n")
    r = base._run(["7", "--repo", "test/repo", "--dry-run"], env)
    d = json.loads(r.stdout)
    assert d["build"]["name"] == "opus" and d["model"] == "claude-opus-4-8"
    assert d["review"]["name"] == "opus"           # default review


def test_dryrun_build_selector_case_insensitive(tmp_path):
    """`MODEL:` (uppercase) is parsed the same as `model:` — case-insensitive."""
    binp = tmp_path / "bin"; base._stubs(binp)
    env = _env(tmp_path, binp, body="### Acceptance criteria\n- [ ] x\n\nMODEL: opus\n")
    r = base._run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["build"]["name"] == "opus"


def test_dryrun_review_selector_case_insensitive(tmp_path):
    """`Review_Model:` (mixed case) is parsed the same as `review_model:` — case-insensitive,
    same parser as the build selector."""
    binp = tmp_path / "bin"; base._stubs(binp)
    env = _env(tmp_path, binp, body="### Acceptance criteria\n- [ ] x\n\nReview_Model: sonnet\n")
    r = base._run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["review"]["name"] == "sonnet"


# ===========================================================================
# Manifest selectors: model + review_model
# ===========================================================================

def test_dryrun_manifest_review_model_selects_review_role(tmp_path):
    """The repo manifest's `review_model` sets the review role (sonnet here, distinct from the
    default opus) when nothing per-task overrides it."""
    repo = _write_manifest(tmp_path, review_model="sonnet")
    binp = tmp_path / "bin"; base._stubs(binp)
    env = _env(tmp_path, binp); env["BASE_REPO"] = str(repo)
    r = base._run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    d = json.loads(r.stdout)
    assert d["review"]["name"] == "sonnet"
    assert d["build"]["name"] == "sonnet"          # build still the default


def test_dryrun_manifest_model_selects_build_role(tmp_path):
    """The repo manifest's `model` sets the build role (opus here)."""
    repo = _write_manifest(tmp_path, model="opus")
    binp = tmp_path / "bin"; base._stubs(binp)
    env = _env(tmp_path, binp); env["BASE_REPO"] = str(repo)
    r = base._run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert json.loads(r.stdout)["build"]["name"] == "opus"


# ===========================================================================
# Precedence: per-task > per-repo(manifest) > registry default, env override atop
# ===========================================================================

def test_dryrun_task_review_beats_manifest_review(tmp_path):
    """Per-task `review_model:` (opus) wins over the manifest `review_model` (sonnet)."""
    repo = _write_manifest(tmp_path, review_model="sonnet")
    binp = tmp_path / "bin"; base._stubs(binp)
    env = _env(tmp_path, binp, body="### Acceptance criteria\n- [ ] x\n\nreview_model: opus\n")
    env["BASE_REPO"] = str(repo)
    r = base._run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert json.loads(r.stdout)["review"]["name"] == "opus"


def test_dryrun_env_build_override_beats_task(tmp_path):
    """The operator env override BUILD_MODEL sits ATOP the per-task selector: body `model: sonnet`
    but BUILD_MODEL=opus resolves the build role to opus."""
    binp = tmp_path / "bin"; base._stubs(binp)
    env = _env(tmp_path, binp, body="### Acceptance criteria\n- [ ] x\n\nmodel: sonnet\n")
    env["BUILD_MODEL"] = "opus"
    r = base._run(["7", "--repo", "test/repo", "--dry-run"], env)
    d = json.loads(r.stdout)
    assert d["build"]["name"] == "opus" and d["model"] == "claude-opus-4-8"


def test_dryrun_env_review_override_beats_task(tmp_path):
    """The operator env override REVIEW_MODEL sits ATOP the per-task selector: body
    `review_model: sonnet` but REVIEW_MODEL=opus resolves the review role to opus."""
    binp = tmp_path / "bin"; base._stubs(binp)
    env = _env(tmp_path, binp, body="### Acceptance criteria\n- [ ] x\n\nreview_model: sonnet\n")
    env["REVIEW_MODEL"] = "opus"
    r = base._run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert json.loads(r.stdout)["review"]["name"] == "opus"


# ===========================================================================
# Equal-rank pair builds (the intake bar is a never-weaker reviewer)
# ===========================================================================

def test_dryrun_equal_rank_pair_builds(tmp_path):
    """A `model: opus` build under the default opus review is an EQUAL-rank pair — the intake bar is
    only that the reviewer is never weaker, so it builds (ready True); the strict review>build bar is
    the later merge gate, not intake."""
    binp = tmp_path / "bin"; base._stubs(binp)
    env = _env(tmp_path, binp, body="### Acceptance criteria\n- [ ] x\n\nmodel: opus\n")
    r = base._run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    d = json.loads(r.stdout)
    assert d["ready"] is True
    assert d["build"]["rank"] == 40 and d["review"]["rank"] == 40   # equal rank, still builds


# ===========================================================================
# Fail-closed intake: inverted / cross-provider ranked pair -> Needs-info, naming the pair
# ===========================================================================

def test_inverted_ranked_pair_bounces_needs_info(tmp_path):
    """A ranked pair whose review rank is strictly BELOW the build rank (opus build, sonnet review)
    is an inversion — bounced to Needs-info before claiming, naming the pair."""
    binp = tmp_path / "bin"; base._stubs(binp)
    # dry-run: the intake gate still fires (read-only), so no git/state is touched.
    env = _env(tmp_path, binp,
                    body="### Acceptance criteria\n- [ ] x\n\nmodel: opus\nreview_model: sonnet\n")
    r = base._run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 3
    msg = r.stderr.lower()
    assert "invert" in msg                         # names the failure mode
    assert "opus" in msg and "sonnet" in msg       # names the pair


def test_inverted_ranked_pair_bounces_and_runs_no_stage(tmp_path):
    """Non-dry-run: an inverted ranked pair sets Backlog + Needs-info with a comment, before
    claiming — no implement/test/review stage runs, no PR."""
    binp = tmp_path / "bin"; base._stubs(binp)
    env = _env(tmp_path, binp,
                    body="### Acceptance criteria\n- [ ] x\n\nmodel: opus\nreview_model: sonnet\n")
    r = base._run(["7", "--repo", "test/repo"], env)
    assert r.returncode == 3
    tl = base._timeline(tmp_path)
    assert not base._ran(tl)                        # no LLM stage ran
    edits = " ".join(base._edits(tl))
    assert "Backlog" in edits and "NeedsInfo" in edits and base._comments(tl)
    assert "https://stub/pr/1" not in r.stdout


def test_cross_provider_ranked_pair_bounces_needs_info(tmp_path):
    """A ranked pair on different providers (anthropic build, openai review) has ranks that are not
    comparable — bounced to Needs-info, naming the pair."""
    reg = _registry_file(tmp_path, TWO_PROVIDER_REGISTRY)
    binp = tmp_path / "bin"; base._stubs(binp)
    env = _env(tmp_path, binp,
                    body="### Acceptance criteria\n- [ ] x\n\nmodel: sonnet\nreview_model: gptx\n")
    env["MODELS_REGISTRY"] = str(reg)
    r = base._run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 3
    msg = r.stderr.lower()
    assert "cross-provider" in msg or "provider" in msg
    assert "sonnet" in msg and "gptx" in msg


# ===========================================================================
# Fail-closed intake: unknown name (task body OR manifest) -> Needs-info, no stage
# ===========================================================================

def test_unknown_review_model_body_bounces_needs_info(tmp_path):
    """A `review_model:` naming a model absent from the registry bounces to Backlog + Needs-info
    before claiming — comment posted, no stage, no PR."""
    binp = tmp_path / "bin"; base._stubs(binp)
    env = _env(tmp_path, binp,
                    body="### Acceptance criteria\n- [ ] x\n\nreview_model: nonesuch\n")
    r = base._run(["7", "--repo", "test/repo"], env)
    assert r.returncode == 3
    tl = base._timeline(tmp_path)
    assert not base._ran(tl)
    edits = " ".join(base._edits(tl))
    assert "Backlog" in edits and "NeedsInfo" in edits and base._comments(tl)
    assert "https://stub/pr/1" not in r.stdout


def test_unknown_manifest_model_bounces_needs_info(tmp_path):
    """An unknown BUILD model in the manifest bounces to Needs-info before claiming — a deliberate
    tightening (a bad manifest model no longer merely warns). No stage runs, no PR."""
    repo = _write_manifest(tmp_path, model="bogus-manifest-model")
    binp = tmp_path / "bin"; base._stubs(binp)
    env = _env(tmp_path, binp); env["BASE_REPO"] = str(repo)
    r = base._run(["7", "--repo", "test/repo"], env)
    assert r.returncode == 3
    tl = base._timeline(tmp_path)
    assert not base._ran(tl)
    edits = " ".join(base._edits(tl))
    assert "Backlog" in edits and "NeedsInfo" in edits and base._comments(tl)
    assert "https://stub/pr/1" not in r.stdout


def test_unknown_manifest_review_model_bounces_needs_info(tmp_path):
    """An unknown REVIEW model in the manifest (`review_model`) also bounces to Needs-info."""
    repo = _write_manifest(tmp_path, review_model="bogus-review-model")
    binp = tmp_path / "bin"; base._stubs(binp)
    env = _env(tmp_path, binp); env["BASE_REPO"] = str(repo)
    r = base._run(["7", "--repo", "test/repo"], env)
    assert r.returncode == 3
    tl = base._timeline(tmp_path)
    assert not base._ran(tl)
    assert "NeedsInfo" in " ".join(base._edits(tl)) and base._comments(tl)
    assert "https://stub/pr/1" not in r.stdout


def test_unknown_model_bounce_is_read_only_under_dry_run(tmp_path):
    """Under --dry-run the unknown-name intake still refuses (exit 3) but writes nothing — a
    read-only preflight."""
    binp = tmp_path / "bin"; base._stubs(binp)
    env = _env(tmp_path, binp, body="### Acceptance criteria\n- [ ] x\n\nmodel: nonesuch\n")
    r = base._run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 3
    tl = base._timeline(tmp_path)
    assert not base._ran(tl) and not base._edits(tl) and not base._comments(tl)


# ===========================================================================
# The env raw-id escape: a raw unregistered id via the operator override runs unranked, no bounce
# ===========================================================================

def test_raw_build_env_override_runs_unranked_without_bounce(tmp_path):
    """A raw unregistered id supplied ONLY through the BUILD_MODEL operator override runs UNRANKED
    (rank None) with a loud warning and is NOT bounced at intake."""
    binp = tmp_path / "bin"; base._stubs(binp)
    env = _env(tmp_path, binp); env["BUILD_MODEL"] = "some-raw-model-id"
    r = base._run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0, r.stderr                  # NOT bounced
    d = json.loads(r.stdout)
    assert d["ready"] is True
    assert d["model"] == "some-raw-model-id"
    assert d["build"]["id"] == "some-raw-model-id"
    assert d["build"]["rank"] is None                   # unranked
    assert "unranked" in r.stderr.lower()               # loud warning


def test_raw_review_env_override_runs_unranked_without_bounce(tmp_path):
    """A raw unregistered id through REVIEW_MODEL also runs unranked without a bounce."""
    binp = tmp_path / "bin"; base._stubs(binp)
    env = _env(tmp_path, binp); env["REVIEW_MODEL"] = "raw-reviewer-id"
    r = base._run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    d = json.loads(r.stdout)
    assert d["ready"] is True
    assert d["review"]["id"] == "raw-reviewer-id" and d["review"]["rank"] is None
    assert "unranked" in r.stderr.lower()


def test_unknown_body_model_bounces_but_raw_env_override_does_not(tmp_path):
    """The distinction is by SOURCE: the SAME raw id bounces from the task body but runs from the
    env override — the env is the one place a non-registry id is allowed."""
    binp = tmp_path / "bin"; base._stubs(binp)
    raw = "definitely-not-registered"
    # from the body: bounce
    env_body = _env(tmp_path, binp, body=f"### Acceptance criteria\n- [ ] x\n\nmodel: {raw}\n")
    r_body = base._run(["7", "--repo", "test/repo", "--dry-run"], env_body)
    assert r_body.returncode == 3
    # from the env override: runs
    env_env = _env(tmp_path, binp); env_env["BUILD_MODEL"] = raw
    r_env = base._run(["7", "--repo", "test/repo", "--dry-run"], env_env)
    assert r_env.returncode == 0
    assert json.loads(r_env.stdout)["model"] == raw


# ===========================================================================
# MODEL / HARD_MODEL env tiers are retired (ignored)
# ===========================================================================

def test_legacy_model_env_tier_is_retired(tmp_path):
    """The retired MODEL env tier no longer selects the build model: MODEL=claude-opus-4-8 is ignored
    and the build role stays at the registry default (sonnet). BUILD_MODEL is its replacement."""
    binp = tmp_path / "bin"; base._stubs(binp)
    env = _env(tmp_path, binp)
    env["MODEL"] = "claude-opus-4-8"; env["HARD_MODEL"] = "claude-opus-4-8"
    r = base._run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    d = json.loads(r.stdout)
    assert d["model"] == "claude-sonnet-5"              # MODEL ignored -> registry default
    assert d["build"]["name"] == "sonnet"


def test_legacy_hard_model_env_does_not_select_review(tmp_path):
    """HARD_MODEL (the retired 'hard' tier) does not select the review role either — review stays the
    registry default (opus) regardless of HARD_MODEL."""
    binp = tmp_path / "bin"; base._stubs(binp)
    env = _env(tmp_path, binp); env["HARD_MODEL"] = "claude-sonnet-5"
    r = base._run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert json.loads(r.stdout)["review"]["name"] == "opus"


# ===========================================================================
# The build role runs implement/test/repair; the review role runs the reviewer at the review rank.
# (Uses the model-recording claude stub over a real-git happy path.)
# ===========================================================================

def test_build_role_runs_impl_and_test_review_role_runs_reviewer(tmp_path):
    """On a clean pass: implementer and independent tester both run at the BUILD id (sonnet); the
    reviewer runs at the REVIEW id (opus) — the review rank, never below it."""
    work, _ = base._make_repo(tmp_path)
    binp = tmp_path / "bin"; _rec_stubs(binp)
    env = base._real(tmp_path, _env(tmp_path, binp, number=5, title="Role split happy path"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    env["STUB_STAGE_MODELS"] = str(tmp_path / "stage_models")
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert "https://stub/pr/1" in r.stdout
    sm = _stage_models(tmp_path)
    assert sm.get("IMPL") == ["claude-sonnet-5"]        # implementer = build id
    assert sm.get("TEST") == ["claude-sonnet-5"]        # independent tester = build id
    assert sm.get("REVIEW") == ["claude-opus-4-8"]      # reviewer = review id (review rank)
    assert "REPAIR" not in sm and "REVIEWFIX" not in sm  # no repair on a clean pass


def test_check_repair_runs_at_its_stage_tier(tmp_path):
    """When the registry sets a stage tier for check_repair, that repair stage runs at the tier's
    entry (haiku) — while implement/test stay at the build id and the reviewer stays at the review id
    (never below the review rank)."""
    reg = _registry_file(tmp_path, STAGE_TIER_REGISTRY)
    work, _ = base._make_repo(tmp_path)
    binp = tmp_path / "bin"; _rec_stubs(binp)
    env = base._real(tmp_path, _env(tmp_path, binp, number=5, title="Stage tier repair"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_CHECK_FAIL": "1",   # check fails until the repair marker
                "STUB_STAGE_MODELS": str(tmp_path / "stage_models"),
                "MODELS_REGISTRY": str(reg)})
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert "https://stub/pr/1" in r.stdout
    sm = _stage_models(tmp_path)
    assert sm.get("REPAIR") == ["claude-haiku-4-5"]     # check-repair ran at its stage tier
    assert sm.get("IMPL") == ["claude-sonnet-5"]        # implement stays at the build id
    assert sm.get("TEST") == ["claude-sonnet-5"]        # tester stays at the build id
    assert sm.get("REVIEW") == ["claude-opus-4-8"]      # reviewer still at the review rank


def test_review_repair_falls_back_to_build_id_without_a_tier(tmp_path):
    """With no stage tier for review_repair, the review-repair stage runs at the BUILD id (a build-role
    repair), and both reviewer rounds run at the review id — the reviewer is never tiered below the
    review rank."""
    work, _ = base._make_repo(tmp_path)
    binp = tmp_path / "bin"; _rec_stubs(binp)
    env = base._real(tmp_path, _env(tmp_path, binp, number=5, title="Review repair fallback"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_REVIEW_BLOCK": "1",   # reviewer blocks until one repair
                "STUB_STAGE_MODELS": str(tmp_path / "stage_models")})
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    sm = _stage_models(tmp_path)
    assert sm.get("REVIEWFIX") == ["claude-sonnet-5"]           # review-repair = build id (no tier)
    assert sm.get("REVIEW") == ["claude-opus-4-8", "claude-opus-4-8"]  # both rounds at review rank


def test_reviewer_never_runs_below_the_review_rank_even_with_lower_build(tmp_path):
    """With a lower build role (a stage-tier registry whose build is sonnet), the reviewer still runs
    at the higher review id (opus) every round — never dragged down to the build/repair tier."""
    reg = _registry_file(tmp_path, STAGE_TIER_REGISTRY)
    work, _ = base._make_repo(tmp_path)
    binp = tmp_path / "bin"; _rec_stubs(binp)
    env = base._real(tmp_path, _env(tmp_path, binp, number=5, title="Reviewer rank floor"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_STAGE_MODELS": str(tmp_path / "stage_models"),
                "MODELS_REGISTRY": str(reg)})
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    sm = _stage_models(tmp_path)
    assert all(m == "claude-opus-4-8" for m in sm.get("REVIEW", [])) and sm.get("REVIEW")
    assert sm.get("IMPL") == ["claude-sonnet-5"]        # build stages below the reviewer


# ===========================================================================
# The PR/commit carry the resolved build + review ids (roles are both surfaced)
# ===========================================================================

def test_pr_body_names_both_build_and_review_ids(tmp_path):
    """The opened PR body records both the resolved build id and the resolved review id — the two
    roles are surfaced, not a single collapsed model."""
    work, _ = base._make_repo(tmp_path)
    binp = tmp_path / "bin"; _rec_stubs(binp)
    env = base._real(tmp_path, _env(tmp_path, binp, number=5, title="Both ids in PR"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_STAGE_MODELS": str(tmp_path / "stage_models")})
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    gh_calls = (tmp_path / "gh_calls").read_text()
    assert "claude-sonnet-5" in gh_calls        # build id (default)
    assert "claude-opus-4-8" in gh_calls         # review id (default)


# ===========================================================================
# Docs ride: AGENTS.md describes the registry surface, review_model, retired env tiers, convention record
# ===========================================================================

def test_agents_md_documents_registry_model_surface_and_roles():
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    low = text.lower()
    assert "model surface" in low                       # the registry is the model surface
    assert "review_model" in low                        # the new review-role selector
    assert "build_model" in low and "review_model" in low  # the operator env override vars
    assert "hard_model" in low                          # names the retired tier...
    assert "retire" in low                              # ...as retired
    assert "convention record" in low                   # the convention record beside the registry header
