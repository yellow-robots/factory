"""it-31 slice 7 (#439): the release lane — a validation-gated, git-native act (ruling 6).

A skill release is a git-native act on the public factory repo: `tools/release.py` validates —
the model loads at the release commit, server CI is green there (evidence: the squash-source PR's
head rollup, tree-equal to the release commit; never an attended full-suite run), the compiled
surfaces carry no drift — refuses on any failure, then creates the annotated `skill/vX.Y.Z` tag
plus the GitHub Release whose body carries YR-RELEASE. Backfill types 1.0.0/1.0.1 against their
shipped commits (callout (d) as ruled: both). The owed model amendment lands: the plugin.version
store and the release transition demanding the record; the header's release-lane bullet retires.
Test mode writes no live record. Fixtures only — most tests stub release._run entirely; the
version_spans_content tests (it-33 slice 5, #461) instead run real git against a tmp_path repo
that reproduces the SHAPE of the live exhibit (never the network — ls-remote/log/diff/show all
resolve against a tmp bare 'origin' on the filesystem).
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import check_trail  # noqa: E402
import process  # noqa: E402
import records  # noqa: E402
import release  # noqa: E402
import sources  # noqa: E402

ATTENDED = {"YR_CALLER": "attended-agent"}

SHA_100 = "021cb1400438b87aff9bfc4a6da81d53684e09f9"
SHA_101 = "cc8624f656a27732eb498fd16ac3cdd987fec78f"


@pytest.fixture(scope="module")
def model():
    return process.load()


@pytest.fixture()
def reg(model):
    return model["_registry"]


def _bash(cmd, session="sR", permission_mode=None):
    hook = {"tool_name": "Bash", "tool_input": {"command": cmd}, "session_id": session}
    if permission_mode is not None:
        hook["permission_mode"] = permission_mode
    return hook


class _Eval:
    def __init__(self, rc=0, out=""):
        self.returncode = rc
        self.stdout = out
        self.stderr = ""


class _EvalCapture:
    """A subprocess stub that RECORDS argv — a blind fiat stub let the empty-repo substitution
    through (the cold review's critical 1); the capture makes that class of gap fail loudly."""

    def __init__(self, rc=0, out=""):
        self.rc, self.out, self.calls = rc, out, []

    def __call__(self, argv, *a, **k):
        self.calls.append(list(argv))
        return _Eval(self.rc, self.out)


# ── the model amendment ──────────────────────────────────────────────────────────────────────────

def test_release_transition_shape(model):
    t = next(t for t in model["transition"] if t["id"] == "plugin.release.validated")
    assert sorted(t["actor"]) == ["attended-agent", "human"]
    assert t["agent_may"] == "propose"          # rule D: one-way forbids execute
    assert t["door"] == "one-way"
    assert t["lane"] == "release"
    guards = t.get("guard") or []
    assert any(g["predicate"] == "evaluator_pass"
               and g["args"]["evaluator"] == "release-validation" for g in guards)
    posts = t.get("post") or []
    assert any(p["predicate"] == "record_present"
               and p["args"]["record"] == "YR-RELEASE" for p in posts)


def test_plugin_version_store_guarded_both_paths_bound(model):
    store = model["_stores"]["plugin.version"]
    assert store["guarded"] is True
    assert sorted(store["writable_by"]) == ["attended-agent", "human"]
    paths = {wp["id"]: wp for wp in store.get("write_path") or []}
    assert set(paths) == {"funnel", "gh-release"}
    assert all(wp.get("observable") for wp in paths.values())
    # rule C: every observable path of a guarded store is bound
    bound = {w["write_path"] for b in model["port"]["binding"]
             for w in b.get("writes") or [] if w["store"] == "plugin.version"}
    assert bound == {"funnel", "gh-release"}


def test_release_evaluator_declared(model):
    ev = model["_evaluators"]["release-validation"]
    assert "tools/release.py" in " ".join(ev["argv"])
    assert ev["conditions_display"] == ["model_loads", "server_ci_green", "no_drift"]


def test_release_lane_mandate_compiles(model):
    mandate, _ = process.lanes(model)
    assert mandate.get("release") == ["YR-RELEASE"]


def test_header_bullet_retired_and_version_bumped(model):
    text = (REPO / "process.toml").read_text(encoding="utf-8")
    assert "the release lane (plugin.version store" not in text, \
        "the v1 header's owed release-lane bullet retires with this slice"
    newest = model["amendment"][0]
    assert newest["version"] == model["model"]["version"], \
        "the newest amendment row IS the current version (newest-first discipline)"
    slice7 = next(a for a in model["amendment"] if "#439" in a.get("review", ""))
    assert "plugin.release.validated" in slice7["touches"]


def test_conformance_vectors_cover_the_release_bindings(model):
    vectors = json.loads(process.compile_conformance(model))
    ids = {v.get("binding") for v in vectors["vectors"]}
    assert {"release.funnel-ship", "release.funnel-backfill", "release.gh-cli"} <= ids


# ── the registry row and its surface ─────────────────────────────────────────────────────────────

def test_registry_row(reg):
    row = records.get(reg, "YR-RELEASE")
    assert row["fields"] == ["version", "commit", "validation", "who"]
    assert row["surfaces"] == ["release"]
    assert sorted(row["emitted_by"]) == ["attended-agent", "human"]


def test_release_surface_in_the_closed_vocabulary():
    assert "release" in records.SURFACES


def test_record_body_satisfies_its_own_grammar(reg):
    body = release.record_body("1.0.0", SHA_100,
                               "model-loads server-ci-green no-drift", "@jbrey",
                               mode="backfill")
    row = records.get(reg, "YR-RELEASE")
    assert body.splitlines()[0].startswith(row["marker"])
    assert check_trail._missing_fields(row, [body]) == []


# ── the walls see the act ────────────────────────────────────────────────────────────────────────

def _stub_repo(monkeypatch):
    monkeypatch.setattr(sources, "origin_repo",
                        lambda cwd=None: (True, "yellow-robots/factory"))


def test_raw_gh_release_create_asks_interactive(model, monkeypatch):
    """A raw `gh release create` resolves to the release transition: propose at a one-way door —
    the wall asks the human when validation holds, and the evaluator receives the RESOLVED repo
    (an empty --repo substitution can never validate anything — review critical 1)."""
    _stub_repo(monkeypatch)
    ev = _EvalCapture(0)
    monkeypatch.setattr(process.subprocess, "run", ev)
    out, rows = process.decide(model, _bash("gh release create skill/v9.9.9 --notes x"),
                               env=ATTENDED)
    assert out["hookSpecificOutput"]["permissionDecision"] == "ask"
    assert rows and rows[0]["transition_id"] == "plugin.release.validated"
    assert ev.calls and any("yellow-robots/factory" in c for call in ev.calls for c in call), \
        "the evaluator must be invoked with the checkout's resolved origin repo, never an empty --repo"


def test_raw_gh_release_create_denies_headless(model, monkeypatch):
    _stub_repo(monkeypatch)
    monkeypatch.setattr(process.subprocess, "run", lambda *a, **k: _Eval(0))
    out, rows = process.decide(model, _bash("gh release create skill/v9.9.9 --notes x",
                                            permission_mode="bypassPermissions"), env=ATTENDED)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert rows and rows[0]["stance"] == "refuse"


def test_failing_validation_refuses_the_raw_act(model, monkeypatch):
    _stub_repo(monkeypatch)
    monkeypatch.setattr(process.subprocess, "run",
                        lambda *a, **k: _Eval(1, "server_ci_green\n"))
    out, _ = process.decide(model, _bash("gh release create skill/v9.9.9 --notes x"),
                            env=ATTENDED)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "server_ci_green" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_funnel_resolves_the_same_transition(model, monkeypatch):
    """The funnel is coverage of the same door, not a bypass: `release.py ship` is judged by the
    SAME transition and guards as the raw spelling."""
    _stub_repo(monkeypatch)
    monkeypatch.setattr(process.subprocess, "run", lambda *a, **k: _Eval(0))
    out, rows = process.decide(model, _bash("python3 tools/release.py ship --version 1.0.3"),
                               env=ATTENDED)
    assert out["hookSpecificOutput"]["permissionDecision"] == "ask"
    assert rows and rows[0]["transition_id"] == "plugin.release.validated"


def test_validate_only_invocation_is_not_a_write(model, monkeypatch):
    _stub_repo(monkeypatch)
    out, rows = process.decide(model,
                               _bash(f"python3 tools/release.py validate --commit {SHA_100}"),
                               env=ATTENDED)
    assert out is None or out["hookSpecificOutput"].get("permissionDecision") != "deny"
    assert not any(r.get("transition_id") == "plugin.release.validated" for r in rows)


# ── release.py: validation refuses per condition, in order ───────────────────────────────────────

class _Fake:
    """Dispatches release._run(argv, ...) by token; records every call."""

    def __init__(self, **beh):
        self.beh = {"validate_rc": 0, "drift_rc": 0, "pulls": [{"number": 427,
                    "head": {"sha": "HEAD" * 10}}], "trees_equal": True,
                    "runs": [{"name": "test", "status": "completed", "conclusion": "success"}],
                    "tag_exists": False, "plugin_version": None}
        self.beh.update(beh)
        self.calls = []

    def __call__(self, argv, timeout=0, cwd=None):
        self.calls.append((list(argv), cwd))
        j = " ".join(argv)
        if "worktree add" in j or "worktree remove" in j or argv[:2] == ["git", "fetch"]:
            return 0, "", ""
        if "process.py" in j and "validate" in j:
            return self.beh["validate_rc"], "", "load failed" if self.beh["validate_rc"] else ""
        if "process.py" in j and "check" in j:
            return self.beh["drift_rc"], "DRIFT" if self.beh["drift_rc"] else "", ""
        if "/pulls" in j:
            return 0, json.dumps(self.beh["pulls"]), ""
        if "rev-parse" in j and "^{tree}" in j:
            return (0, "T1\nT1\n", "") if self.beh["trees_equal"] else (0, "T1\nT2\n", "")
        if "rev-parse" in j:
            return 0, "RESOLVED" + "0" * 32 + "\n", ""
        if "/check-runs" in j:
            return 0, json.dumps({"check_runs": self.beh["runs"]}), ""
        if "ls-remote" in j:
            return 0, ("X\trefs/tags/skill/v1.0.0\n" if self.beh["tag_exists"] else ""), ""
        if "show" in j and "plugin.json" in j:
            v = self.beh["plugin_version"]
            return 0, json.dumps({"name": "factory", "version": v}), ""
        if argv[:2] == ["gh", "api"] and "user" in j:
            return 0, "jbrey\n", ""
        return 0, "", ""

    def wrote(self):
        writing = []
        for argv, _ in self.calls:
            j = " ".join(argv)
            if ("git tag" in j or "push" in j or ("release" in j and "create" in j)
                    or "issue comment" in j):
                writing.append(argv)
        return writing


def _v(monkeypatch, fake, argv):
    monkeypatch.setattr(release, "_run", fake)
    rc = release.main(argv)
    return rc


def test_validate_refuses_on_model_load(monkeypatch, capsys):
    fake = _Fake(validate_rc=1, plugin_version="1.0.0")
    rc = _v(monkeypatch, fake, ["validate", "--commit", SHA_100, "--version", "1.0.0"])
    out = capsys.readouterr().out
    assert rc == 1 and out.splitlines()[0] == "model_loads"


def test_validate_refuses_when_no_source_pr(monkeypatch, capsys):
    fake = _Fake(pulls=[], plugin_version="1.0.0")
    rc = _v(monkeypatch, fake, ["validate", "--commit", SHA_100, "--version", "1.0.0"])
    assert rc == 1 and capsys.readouterr().out.splitlines()[0] == "server_ci_green"


def test_validate_refuses_on_tree_mismatch(monkeypatch, capsys):
    fake = _Fake(trees_equal=False, plugin_version="1.0.0")
    rc = _v(monkeypatch, fake, ["validate", "--commit", SHA_100, "--version", "1.0.0"])
    assert rc == 1 and capsys.readouterr().out.splitlines()[0] == "server_ci_green"


def test_validate_refuses_on_red_rollup(monkeypatch, capsys):
    fake = _Fake(runs=[{"name": "test", "status": "completed", "conclusion": "failure"}],
                 plugin_version="1.0.0")
    rc = _v(monkeypatch, fake, ["validate", "--commit", SHA_100, "--version", "1.0.0"])
    assert rc == 1 and capsys.readouterr().out.splitlines()[0] == "server_ci_green"


def test_validate_refuses_on_empty_rollup(monkeypatch, capsys):
    """Zero check-runs is not green — fail-closed, never a bare empty pass."""
    fake = _Fake(runs=[], plugin_version="1.0.0")
    rc = _v(monkeypatch, fake, ["validate", "--commit", SHA_100, "--version", "1.0.0"])
    assert rc == 1 and capsys.readouterr().out.splitlines()[0] == "server_ci_green"


def test_validate_refuses_on_drift(monkeypatch, capsys):
    fake = _Fake(drift_rc=1, plugin_version="1.0.0")
    rc = _v(monkeypatch, fake, ["validate", "--commit", SHA_100, "--version", "1.0.0"])
    assert rc == 1 and capsys.readouterr().out.splitlines()[0] == "no_drift"


def test_ship_refuses_on_existing_tag(monkeypatch, capsys):
    fake = _Fake(tag_exists=True, plugin_version="1.0.0")
    rc = _v(monkeypatch, fake, ["backfill", "--version", "1.0.0", "--who", "@jbrey"])
    assert rc == 1 and capsys.readouterr().out.splitlines()[0] == "tag_exists"
    assert fake.wrote() == []


def test_refuses_on_version_mismatch(monkeypatch, capsys):
    fake = _Fake(plugin_version="9.9.9")
    rc = _v(monkeypatch, fake, ["backfill", "--version", "1.0.0", "--who", "@jbrey"])
    assert rc == 1 and capsys.readouterr().out.splitlines()[0] == "version_mismatch"
    assert fake.wrote() == []


def test_test_mode_writes_nothing(monkeypatch, capsys):
    fake = _Fake(plugin_version="1.0.0")
    rc = _v(monkeypatch, fake, ["backfill", "--version", "1.0.0", "--who", "@jbrey",
                                "--test-mode"])
    out = capsys.readouterr().out
    assert rc == 0
    assert fake.wrote() == [], "test mode creates no tag, no Release, no trail"
    assert "TEST-MODE" in out and "skill/v1.0.0" in out


def test_live_backfill_tags_and_releases(monkeypatch, capsys):
    fake = _Fake(plugin_version="1.0.0")
    rc = _v(monkeypatch, fake, ["backfill", "--version", "1.0.0", "--who", "@jbrey"])
    assert rc == 0
    wrote = [" ".join(a) for a in fake.wrote()]
    assert any("tag" in w and "skill/v1.0.0" in w for w in wrote)
    assert any("push" in w and "refs/tags/skill/v1.0.0" in w for w in wrote)
    assert any("release create skill/v1.0.0" in w for w in wrote)


def test_backfill_pins():
    assert release.BACKFILL == {"1.0.0": SHA_100, "1.0.1": SHA_101}


def test_backfill_unpinned_version_needs_explicit_commit(monkeypatch, capsys):
    fake = _Fake(plugin_version="1.0.2")
    rc = _v(monkeypatch, fake, ["backfill", "--version", "1.0.2", "--who", "@jbrey",
                                "--test-mode"])
    assert rc == 1 and "commit" in capsys.readouterr().err


def test_bad_version_refuses(monkeypatch, capsys):
    fake = _Fake()
    rc = _v(monkeypatch, fake, ["ship", "--version", "banana", "--who", "@x", "--test-mode"])
    assert rc == 1 and capsys.readouterr().out.splitlines()[0] == "version_malformed"


# ── the bounded fetcher ──────────────────────────────────────────────────────────────────────────

def test_releases_fetcher_bounded_and_shaped(monkeypatch):
    seen = {}

    def fake_run(argv, timeout=None):
        seen["argv"], seen["timeout"] = argv, timeout
        return True, json.dumps([{"tag_name": "skill/v1.0.0", "body": "YR-RELEASE\nversion: 1.0.0"},
                                 {"tag_name": "skill/v1.0.1", "body": "YR-RELEASE\nversion: 1.0.1"}])

    monkeypatch.setattr(sources, "_run", fake_run)
    ok, texts = sources.releases("yellow-robots/factory")
    assert ok and len(texts) == 2 and all("YR-RELEASE" in t for t in texts)
    assert seen["timeout"] is not None
    assert "releases" in " ".join(seen["argv"])


# ── the cold review's folds (the readers become real; the probe watches its own surface) ─────────

def test_engine_fetches_the_release_surface(model, reg, monkeypatch):
    """Review major 2: record_present over YR-RELEASE must be readable by the engine — the close
    report's post re-check reads this surface, and an unwired surface is a permanent UNKNOWN."""
    monkeypatch.setattr(sources, "releases",
                        lambda repo: (True, ["skill/v1.0.0\nYR-RELEASE\nversion: 1.0.0"]))
    ctx = process._Ctx(model)
    ctx.scope["repo"] = "yellow-robots/factory"
    row = records.get(reg, "YR-RELEASE")
    texts = process._fetch_surface_texts(ctx, row, {})
    assert texts and "YR-RELEASE" in texts[0]


def test_check_trail_cli_reads_the_release_lane(reg, monkeypatch, capsys):
    """Review major 3: the registry row names check_trail as a reader — the CLI must actually be
    able to fetch the surface, or the release lane can never be checked."""
    body = release.record_body("1.0.0", SHA_100, "evidence", "@jbrey", mode="backfill")
    monkeypatch.setattr(check_trail, "fetch_releases",
                        lambda repo: [f"skill/v1.0.0\n{body}"])
    rc = check_trail._cli(["--lane", "release", "--repo", "yellow-robots/factory"])
    out = capsys.readouterr().out
    assert rc == 0 and "clean" in out


def test_release_binding_probes_its_own_surface(model):
    """Review medium 5: `gh release create`'s drift probe must fingerprint `gh release`, not an
    unrelated subcommand family."""
    bd = next(b for b in model["port"]["binding"] if b["id"] == "release.gh-cli")
    assert bd["probe"] == "gh.release.surface"
    pr = next(p for p in model["port"]["probe"] if p["id"] == "gh.release.surface")
    assert pr["fingerprint_cmd"] == "gh release --help"


def test_releases_fetcher_paginates(monkeypatch):
    """Review medium 6: --paginate concatenates top-level arrays across pages, breaking a single
    json.loads — the fetcher pages explicitly, like the comment fetcher."""
    pages = {1: [{"tag_name": f"skill/v0.0.{i}", "body": "YR-RELEASE"} for i in range(100)],
             2: [{"tag_name": "skill/v1.0.0", "body": "YR-RELEASE"}]}
    calls = []

    def fake_run(argv, timeout=None):
        page = int(next(a.split("=")[1] for a in argv if a.startswith("page=")))
        calls.append(page)
        return True, json.dumps(pages[page])

    monkeypatch.setattr(sources, "_run", fake_run)
    ok, texts = sources.releases("yellow-robots/factory")
    assert ok and len(texts) == 101 and calls == [1, 2]


def test_evaluator_timeout_leaves_hook_headroom(model):
    """Review medium 7: the hook's own ceiling is 600s and a harness kill is fail-OPEN (the
    invisible-exit contract) — the evaluator must die first, closed."""
    ev = model["_evaluators"]["release-validation"]
    assert int(ev["timeout_s"]) <= 300


def test_worktree_dir_reclaimed_when_add_fails(monkeypatch, tmp_path):
    """Review low 8: mkdtemp precedes `git worktree add`; a failed add must not leak the dir."""
    wt = tmp_path / "leaky"
    monkeypatch.setattr(release.tempfile, "mkdtemp", lambda **k: str(wt.mkdir() or wt))

    def failing_run(argv, timeout=0, cwd=None):
        if "worktree" in argv and "add" in argv:
            return 1, "", "boom"
        return 0, "", ""

    monkeypatch.setattr(release, "_run", failing_run)
    token, _ = release._judged_at_commit(SHA_100)
    assert token == "model_loads"
    assert not wt.exists(), "a failed worktree add must reclaim its temp dir"


# ── the canon row moves with the model ───────────────────────────────────────────────────────────

def test_canon_release_act_is_walled_now():
    """The release act left advisory-v1: the canon carries no 'not yet walled' residue, and the
    GENERATED map (the walled-act authority since it-31 slice 8) carries the release rows with the
    record their condition names."""
    canon = (REPO / "skills/factory/references/attended-lane.md").read_text(encoding="utf-8")
    assert "not yet walled" not in canon
    gen = (REPO / "build" / "walled-acts.md").read_text(encoding="utf-8")
    release_rows = [l for l in gen.splitlines() if "release.gh-cli" in l or "release.funnel" in l]
    assert release_rows, "the generated map lost the release rows"
    lanes_txt = (REPO / "build" / "lanes.toml").read_text(encoding="utf-8")
    assert "YR-RELEASE" in lanes_txt, "the release lane's mandate left the compiled lanes"


# ── version_spans_content: the payload-drift refusal (it-33 slice 5, #461) ─────────────────────────
#
# The live exhibit: skill/v1.0.2's plugin.json bump lands at c14e73d, but the tag itself was cut
# much later at e96e5d4 — forty-two files of unrelated shipped content sit in between under the
# SAME declared version, and the previous-tag anchor (skill/v1.0.1) can't see the problem because
# plugin.json changes again across v1.0.1..v1.0.2 too. These tests reproduce that SHAPE against a
# throwaway tmp_path repo — never the live repo's network remotes.

def _git(args, cwd):
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)


def _rev_parse(cwd, ref="HEAD"):
    out = subprocess.run(["git", "rev-parse", ref], cwd=str(cwd), check=True,
                         capture_output=True, text=True)
    return out.stdout.strip()


def _write_plugin_version(work, version):
    d = work / ".claude-plugin"
    d.mkdir(exist_ok=True)
    (d / "plugin.json").write_text(json.dumps({"name": "factory", "version": version}))


def _commit_all(work, msg):
    _git(["add", "-A"], work)
    _git(["commit", "-q", "-m", msg], work)


def _make_release_repo(tmp_path):
    """A real bare 'origin' plus a working clone, seeded at declared version 1.0.0 with its tag
    already pushed — the branch is 'release-trunk', never 'main': this repo is throwaway, not a
    shared ref, and every git call the new condition makes (ls-remote/log/diff/show) resolves
    against this tmp filesystem repo, no network."""
    origin = tmp_path / "origin.git"
    origin.mkdir()
    _git(["init", "-q", "--bare", "-b", "release-trunk", "."], origin)
    work = tmp_path / "work"
    work.mkdir()
    _git(["init", "-q", "-b", "release-trunk", "."], work)
    _git(["config", "user.email", "t@t"], work)
    _git(["config", "user.name", "tester"], work)
    _write_plugin_version(work, "1.0.0")
    _commit_all(work, "seed 1.0.0")
    _git(["remote", "add", "origin", str(origin)], work)
    _git(["push", "-q", "origin", "release-trunk"], work)
    _git(["tag", "-a", "skill/v1.0.0", "-m", "v1.0.0"], work)
    _git(["push", "-q", "origin", "skill/v1.0.0"], work)
    return work


@pytest.fixture()
def stub_other_conditions(monkeypatch):
    """Cans model_loads/no_drift/server_ci_green so the full `validate()` pipeline runs against a
    tmp repo that carries no real `tools/process.py` and makes no `gh` call — isolating the NEW
    condition inside the real pipeline ordering without needing the live tooling or network."""
    monkeypatch.setattr(release, "_judged_at_commit",
                        lambda commit: ("", "stubbed: loads, no drift"))
    monkeypatch.setattr(release, "_ci_green_at", lambda repo, commit: (True, "stubbed: ci green"))


def test_conditions_tuple_gains_version_spans_content_in_order():
    assert release.CONDITIONS == ("version_spans_content", "model_loads", "server_ci_green",
                                  "no_drift")


def test_registry_row_validation_note_names_the_new_condition(reg):
    row = records.get(reg, "YR-RELEASE")
    assert "bump commit" in row["notes"]


def test_version_spans_content_refuses_the_spanning_case(monkeypatch, capsys, tmp_path,
                                                          stub_other_conditions):
    """The exhibit's SHAPE: bump to 1.0.2, then forty-two files of shipped content with no
    further version bump — the anchor is the bump commit, never the previous tag."""
    work = _make_release_repo(tmp_path)
    _write_plugin_version(work, "1.0.1")
    _commit_all(work, "bump to 1.0.1")
    _git(["tag", "-a", "skill/v1.0.1", "-m", "v1.0.1"], work)
    _git(["push", "-q", "origin", "release-trunk", "skill/v1.0.1"], work)
    _write_plugin_version(work, "1.0.2")
    _commit_all(work, "bump to 1.0.2")
    bump = _rev_parse(work)
    for i in range(42):
        (work / f"f{i}.txt").write_text(f"content {i}\n")
    _commit_all(work, "forty-two files of shipped content, no further version bump")
    tip = _rev_parse(work)
    _git(["push", "-q", "origin", "release-trunk"], work)
    monkeypatch.setattr(release, "REPO_ROOT", work)
    rc = release.main(["validate", "--commit", tip, "--version", "1.0.2"])
    out = capsys.readouterr().out
    assert rc == 1
    assert out.splitlines()[0] == "version_spans_content"
    assert bump[:9] in out and "42" in out


def test_version_spans_content_passes_when_tree_unchanged_since_bump(monkeypatch, capsys,
                                                                      tmp_path,
                                                                      stub_other_conditions):
    """Validated exactly at its own bump commit — no content added since — passes the new
    condition and reaches the (stubbed) later conditions, so overall validation is ok."""
    work = _make_release_repo(tmp_path)
    _write_plugin_version(work, "1.0.1")
    _commit_all(work, "bump to 1.0.1")
    bump = _rev_parse(work)
    _git(["push", "-q", "origin", "release-trunk"], work)
    monkeypatch.setattr(release, "REPO_ROOT", work)
    rc = release.main(["validate", "--commit", bump, "--version", "1.0.1"])
    out = capsys.readouterr().out
    assert rc == 0 and out.splitlines()[0].startswith("ok:")


def test_version_spans_content_passes_with_no_prior_tag(monkeypatch, capsys, tmp_path,
                                                         stub_other_conditions):
    """No skill/v* tag exists on origin at all — the range is FULL history (never bounded by a
    previous tag), and the walk still finds the right bump commit among earlier, untagged
    commits."""
    origin = tmp_path / "origin.git"
    origin.mkdir()
    _git(["init", "-q", "--bare", "-b", "release-trunk", "."], origin)
    work = tmp_path / "work"
    work.mkdir()
    _git(["init", "-q", "-b", "release-trunk", "."], work)
    _git(["config", "user.email", "t@t"], work)
    _git(["config", "user.name", "tester"], work)
    _write_plugin_version(work, "0.9.0")
    _commit_all(work, "pre-release scaffolding")
    _write_plugin_version(work, "1.0.0")
    _commit_all(work, "bump to 1.0.0")
    bump = _rev_parse(work)
    _git(["remote", "add", "origin", str(origin)], work)
    _git(["push", "-q", "origin", "release-trunk"], work)
    monkeypatch.setattr(release, "REPO_ROOT", work)
    rc = release.main(["validate", "--commit", bump, "--version", "1.0.0"])
    out = capsys.readouterr().out
    assert rc == 0 and out.splitlines()[0].startswith("ok:")


def test_version_mismatch_still_wins_first_when_content_also_spans(monkeypatch, capsys,
                                                                    tmp_path,
                                                                    stub_other_conditions):
    """Ordering: version_mismatch is judged before version_spans_content — a wrong declared
    version refuses with its own token even when the tree also spans content since the real
    bump."""
    work = _make_release_repo(tmp_path)
    _write_plugin_version(work, "1.0.1")
    _commit_all(work, "bump to 1.0.1")
    for i in range(3):
        (work / f"g{i}.txt").write_text("x\n")
    _commit_all(work, "content after the bump")
    tip = _rev_parse(work)
    _git(["push", "-q", "origin", "release-trunk"], work)
    monkeypatch.setattr(release, "REPO_ROOT", work)
    rc = release.main(["validate", "--commit", tip, "--version", "9.9.9"])
    out = capsys.readouterr().out
    assert rc == 1 and out.splitlines()[0] == "version_mismatch"


# ── cold-review folds (commit 561c9ee's review): the ok-line, the tag-shape agreement, the ─────────
# malformed-version guard, empty-diff coverage, and the emitted record's own validation field ──────

def test_ok_line_omits_version_spans_content_when_no_version_given(monkeypatch, capsys):
    """`validate` with no --version never runs the new condition — the ok-line must never claim
    it (review fold 2: print only the conditions actually evaluated)."""
    fake = _Fake()
    rc = _v(monkeypatch, fake, ["validate", "--commit", SHA_100])
    out = capsys.readouterr().out
    assert rc == 0
    assert out.splitlines()[0].startswith("ok:")
    assert "version_spans_content" not in out.splitlines()[0]


def test_ok_line_names_version_spans_content_when_version_given(monkeypatch, capsys):
    fake = _Fake(plugin_version="1.0.0")
    rc = _v(monkeypatch, fake, ["validate", "--commit", SHA_100, "--version", "1.0.0"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "version_spans_content" in out.splitlines()[0]


def test_existing_version_tags_shape_agrees_name_first(tmp_path, monkeypatch):
    """Review fold 3: the annotation/docstring say (tag-name, version-tuple) — prove the actual
    return shape agrees, not just the consumer's unpacking order."""
    work = _make_release_repo(tmp_path)
    monkeypatch.setattr(release, "REPO_ROOT", work)
    ok, tags, _detail = release._existing_version_tags()
    assert ok and tags
    name, version_tuple = tags[0]
    assert name == "skill/v1.0.0"
    assert version_tuple == (1, 0, 0)


def test_bump_commit_malformed_version_falls_back_to_full_history(tmp_path, monkeypatch):
    """Review fold 4: a non-semver declared version must never raise comparing against existing
    tags — it falls back to the full-history walk (no previous-tag bound); safe by construction,
    since the declared version can never match a real commit's plugin.json anyway."""
    work = _make_release_repo(tmp_path)
    tip = _rev_parse(work)
    monkeypatch.setattr(release, "REPO_ROOT", work)
    bump, detail = release._bump_commit("not-a-semver", tip)
    assert bump == tip
    assert "never appears in range" in detail


def test_version_spans_content_passes_when_bump_differs_but_diff_is_empty(monkeypatch, capsys,
                                                                          tmp_path,
                                                                          stub_other_conditions):
    """Review fold 5a: bump != commit, but nothing tracked changed in between (an empty commit)
    — the condition judges the TREE, not commit identity, so this still passes."""
    work = _make_release_repo(tmp_path)
    _write_plugin_version(work, "1.0.1")
    _commit_all(work, "bump to 1.0.1")
    _git(["commit", "--allow-empty", "-q", "-m", "empty follow-up, no tree change"], work)
    tip = _rev_parse(work)
    _git(["push", "-q", "origin", "release-trunk"], work)
    monkeypatch.setattr(release, "REPO_ROOT", work)
    rc = release.main(["validate", "--commit", tip, "--version", "1.0.1"])
    out = capsys.readouterr().out
    assert rc == 0 and out.splitlines()[0].startswith("ok:")


def test_emitted_record_validation_field_names_version_spans_content(monkeypatch, capsys):
    """Review fold 5b: not just the registry row's notes — the RENDERED YR-RELEASE record's own
    validation field must name the condition, at the render site (`_release`'s TEST-MODE body
    print, since --test-mode writes nothing else)."""
    fake = _Fake(plugin_version="1.0.0")
    rc = _v(monkeypatch, fake, ["backfill", "--version", "1.0.0", "--who", "@jbrey",
                                "--test-mode"])
    out = capsys.readouterr().out
    assert rc == 0
    validation_line = next(l for l in out.splitlines() if l.startswith("validation:"))
    assert "version_spans_content" in validation_line
