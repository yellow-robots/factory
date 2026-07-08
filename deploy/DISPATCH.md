# Deploying dispatch (RFC 0004) — the watched switch-on

This turns the factory **autonomous**: n8n polls the project for `Status=Ready` and POSTs each issue to a host service that runs the dev-runner. Deploy in order; **keep n8n inactive until step 4**.

```
n8n (Docker, schedule)  --GraphQL-->  GitHub: Ready items
        |  POST /build {issue}  (bearer token)
        v
host dispatch.service  --flock(single-flight)-->  dev-runner.sh <issue>  -->  PR
```

## 1. Host service

```bash
# config + secret (NOT in the repo)
mkdir -p ~/.config/dev-runner
cp deploy/dispatch.env.example ~/.config/dev-runner/dispatch.env
# edit: set DISPATCH_TOKEN (long random), DISPATCH_BIND (step 2), DISPATCH_PORT
chmod 600 ~/.config/dev-runner/dispatch.env

# install + start the user service
mkdir -p ~/.config/systemd/user
cp deploy/dispatch.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now dispatch
loginctl enable-linger "$USER"        # so it survives logout
systemctl --user status dispatch
```

## 2. Networking (n8n container → host)

n8n is in Docker; it reaches the host over the **bridge gateway IP**, not `127.0.0.1`. Bind the service there and open the port to the docker subnet only.

```bash
# find n8n's network + gateway
docker inspect <n8n-container> --format '{{range .NetworkSettings.Networks}}{{.Gateway}} {{end}}'
# n8n is on caddy_caddy-net here → gateway 172.19.0.1; set DISPATCH_BIND to it, then allow ONLY that subnet:
sudo ufw allow from 172.19.0.0/16 to any port 8770 proto tcp   # the n8n subnet only — never 172.0.0.0/8
```
(Same pattern as the Joam TG webhook: container → `172.19.0.1:<port>` + a ufw rule.)

**Smoke test** (use a throwaway `Status=Ready` issue, watched):
```bash
TOKEN=$(grep DISPATCH_TOKEN ~/.config/dev-runner/dispatch.env | cut -d= -f2-)
curl -s -XPOST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
     -d '{"issue": <N>}' http://<BIND>:8770/build      # expect 202; watch the runner open a PR
```

## 3. n8n workflow

Import `deploy/n8n-dispatch.json`, then wire:
- **GraphQL node** — a GitHub token with `project`+`repo` read (a Header-Auth credential `Authorization: Bearer <gh-token>`, or n8n's GitHub credential). Query is `deploy/ready-query.graphql`.
- **POST /build node** — set the URL to `http://<BIND>:8770/build` and the `Authorization: Bearer <DISPATCH_TOKEN>` (same token as the host).
- The Code node already filters to `Status=Ready` + `state=OPEN` and emits one item per issue.

Node `typeVersion`s may need bumping to your n8n; the JSON is a starting skeleton — verify on import.

## 4. Switch-on — watched

1. Leave the Schedule trigger but **run the workflow manually** ("Execute Workflow") against the current Ready queue. Watch a full build (claim → implement → test → review → PR). Confirm the issue moves Ready → In Progress → In Review.
2. Repeat for a few tasks until boring.
3. **Then** activate the workflow (the schedule starts polling). Autonomy is on.

**Kill switch (dispatch):** deactivate the n8n workflow, or `systemctl --user stop dispatch` — either stops *new* dispatch instantly. The unit uses `KillMode=process`, so an **in-flight build runs to completion** (it is not killed). To also abort a running build, `pkill -f dev-runner.sh` — note it then dies mid-stage and leaves the issue at `In Progress` with a leftover worktree, for a human to reset.

**Merge kill switch (the sentinel) — stop autonomous merges without stopping builds.** For an *armed* repo (`auto_merge = true` in its `.yr/factory.toml`) the runner squash-merges a green, fresh, approved, rank-holding PR itself (see AGENTS.md → "the terminal merge decision"). To halt **all** factory merges globally — leaving every PR for a human to merge by hand, while builds keep flowing to open PRs — throw the **sentinel**:

```bash
touch "$DEV_RUNNER_HOME/merge-killswitch"     # DEV_RUNNER_HOME defaults to ~/.cache/dev-runner
```

- It is a **host file**, read **live** at each merge decision — not an environment variable, because a spawned runner carries its spawn-time environment and would miss a later change. A file is seen by the very next decision, globally, with no git round-trip.
- While it is present, an armed repo whose merge conditions otherwise pass is **refused**: the runner posts `YR-MERGE: BLOCKED — sentinel`, sets `Reason=Blocked`, and leaves the PR at `In Review` for a human. It does **not** stop building, testing, reviewing, or opening PRs, and it never affects a non-armed (shadow) repo (which was never going to auto-merge anyway).
- **Clear it** to resume autonomous merges: `rm "$DEV_RUNNER_HOME/merge-killswitch"`. PRs blocked while it was thrown stay `Reason=Blocked` until re-run or merged by hand — clear the reason (or re-Ready to rebuild) once you have merged or are ready for the factory to.
- Override the path with `MERGE_SENTINEL=/some/other/file` if the dispatch home is not the default.

This is a deliberate operator switch (distinct from an *environmental* failure, which the runner classifies as resumable and never treats as a block). Use it during an incident, a `main`-branch freeze, or any window where you want to hold the final merge gate by hand.

## Quota/rate-limit holds on the `claude -p` stages

A build or review stage (`claude -p`) can die because its account has hit a usage/rate limit — not because the code is wrong. The runner detects this from the stage's own log (an exit code alone isn't a stable signal: CLI exit codes for a limit kill aren't documented), never hands it to LLM repair, and holds the run exactly like the check gate's environmental failure (see AGENTS.md → "the deterministic check gate"): the worktree, run dir, and completed-stage checkpoints are **preserved**, `Reason=Blocked` is set with a comment naming it an **environmental hold (quota)**, and a relaunch **resumes** at the first incomplete stage — never a silently stranded claim.

- **Signatures are data**, not a hardcoded exit code: `QUOTA_SIGNATURES` is a `grep -E` alternation checked against the stage's log (default: `usage limit|rate limit|quota|overloaded|429` — verified against the installed Claude CLI's own error vocabulary: "usage limit reached", "rate limited", "overloaded"/`overloaded_error`, and the Anthropic API's `429 rate_limit_error` status; `quota` is kept as a conservative catch-all). Override `QUOTA_SIGNATURES` in the dispatch environment to add or narrow signatures for a different CLI/provider mix. Keep it conservative — a signature that's too broad risks misclassifying a genuine code failure as environmental.
- **Resume, don't repair:** a quota hold reuses the same branch-keyed worktree + per-branch `.done` markers as the check gate's env-hold (issue #39) — wait for the limit to reset, then re-run; the earlier green stages are not re-paid.

### The pool → credential seam (`YR_POOL_<POOL>`)

Every `models.toml` entry names a `quota_pool` — the shared rate/spend ceiling it draws from. A single account ceiling can halt every stage using that account at once, even across build and review. `YR_POOL_<POOL_UPPER_SNAKE>` (hyphens become underscores; e.g. pool `anthropic-main` → `YR_POOL_ANTHROPIC_MAIN`) in the dispatch environment names the **credential/config directory** (`CLAUDE_CONFIG_DIR`) to use for a stage whose resolved model belongs to that pool, letting different pools draw on different accounts.

- **Fallback is the ambient default:** when a pool's `YR_POOL_*` variable is unset, the runner sets nothing and the stage runs exactly as it does today (single account) — this is why shipping the seam changes no behavior yet.
- **This iteration only names the seam.** Both shipping registry entries (`sonnet`, `opus`) share `quota_pool = "anthropic-main"`, so no `YR_POOL_*` variable needs to be set until a second pool/account is actually provisioned (a separate, deliberate operator action — never automatic).
- Set it in `~/.config/dev-runner/dispatch.env` alongside `DISPATCH_TOKEN` (see `deploy/dispatch.env.example`).

## Safety properties (already built)

- **Single-flight:** the host `flock` serializes to one build at a time; a duplicate dispatch exits immediately.
- **No double-pickup:** the runner claims (`Ready → In Progress`) as its first act, dropping the task off the Ready query within seconds.
- **Fail-closed:** any runner failure → `Reason=Blocked` + comment, no PR. A bad task can't run wild.
- **Grooming stays human:** dispatch only *pulls* `Ready`; promoting Backlog → Ready is a human/Joam decision.
- **Output survives the detach:** the runner is spawned with no terminal to write to, so dispatch captures
  its combined stdout+stderr into `~/.cache/dev-runner/runs/dispatch-<issue>-<epoch ms>.log` — including
  whatever it managed to print before a hard kill or a failure with no per-stage log of its own.

## Deploying the epic-gate sweep

The same host service also exposes `POST /sweep`, which fires `tools/epic_gate.py` — the org-wide sweep
that promotes the next pre-approved slice under a standing approval, self-closes a finished Ready epic,
and raises stranded claims. It takes no issue/repo (the board is org-wide) and runs under its **own**
lock (`SWEEP_LOCK`, default `~/.cache/dev-runner/epic-sweep.lock`), separate from the build lock
(`DISPATCH_LOCK`) — a running build never blocks a sweep, and vice versa. No code change or restart is
needed if the service is already running `/build`; `/sweep` is live on the same process.

1. **Import the workflow.** Import `deploy/n8n-epic-sweep.json`, then wire the **POST /sweep** node:
   set the URL to `http://<BIND>:8770/sweep` and `Authorization: Bearer <DISPATCH_TOKEN>` (same token
   and bind as the build workflow — no separate networking setup required). There is no GraphQL/filter
   node — the sweep needs no input, so the schedule trigger feeds `POST /sweep` directly.
2. **Smoke test:**
   ```bash
   TOKEN=$(grep DISPATCH_TOKEN ~/.config/dev-runner/dispatch.env | cut -d= -f2-)
   curl -s -XPOST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
        -d '{}' http://<BIND>:8770/sweep      # expect 202
   ```
3. **Watched switch-on.** Same discipline as the build workflow: run `/sweep` manually against the live
   board (via "Execute Workflow" or the curl above) and watch it act — a slice promotion, an epic
   self-close, or a stranded-claim raise. Repeat until boring, then activate the schedule.

**Kill switch, sweep vs. build:** `systemctl --user stop dispatch` stops the whole host service — **both**
`/build` and `/sweep` — instantly (new dispatches only; an in-flight build or sweep runs to completion,
`KillMode=process`). To stop *only* promotions while builds keep running, deactivate just the epic-sweep
n8n workflow — the build workflow (and `/build`) is unaffected.
