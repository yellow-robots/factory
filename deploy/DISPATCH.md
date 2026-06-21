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

**Kill switch:** deactivate the n8n workflow, or `systemctl --user stop dispatch` — either stops *new* dispatch instantly. The unit uses `KillMode=process`, so an **in-flight build runs to completion** (it is not killed). To also abort a running build, `pkill -f dev-runner.sh` — note it then dies mid-stage and leaves the issue at `In Progress` with a leftover worktree, for a human to reset.

## Safety properties (already built)

- **Single-flight:** the host `flock` serializes to one build at a time; a duplicate dispatch exits immediately.
- **No double-pickup:** the runner claims (`Ready → In Progress`) as its first act, dropping the task off the Ready query within seconds.
- **Fail-closed:** any runner failure → `Reason=Blocked` + comment, no PR. A bad task can't run wild.
- **Grooming stays human:** dispatch only *pulls* `Ready`; promoting Backlog → Ready is a human/Joam decision.
