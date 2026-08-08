# The Claude Code hook contract — verified 2026-08-07

Ground truth for the attended lane's enforcement layer. Two sources, and where they disagree the probe wins:
**D** = the published reference (`https://code.claude.com/docs/en/hooks`), **P** = a live probe run this session
(`claude -p` in a scratch dir with a settings.json registering SessionStart/PreToolUse/Stop; payloads captured).

The round already shipped one slice built on an *unverified* assumption about the transport (that plugin hooks
could be workspace-scoped). Everything below is checked.

---

## 1. Hooks fire in headless mode, and `bypassPermissions` does NOT skip them — **P, decisive**

`claude -p "…" --permission-mode bypassPermissions` fired **SessionStart, PreToolUse and Stop**, all three.

Consequences, both load-bearing:

- The ship-walk's "fail-dangerous" finding is **confirmed, not speculative**. If the plugin were installed for
  the `yr-factory` user on the build host, the walls would fire inside every cold pipeline stage — including
  the implement stage, which runs `bypassPermissions` precisely because the environment is the confinement.
  The `YR_MACHINERY` declaration is **essential**, not defence in depth.
- Delivery to cold stages is mechanically possible. The round's choice to *exclude* machinery by declaration is
  therefore a real decision with a real alternative, not a technical necessity.

## 2. Only exit code 2 blocks. A crashing hook lets the tool through, SILENTLY — **D, and P decisive**

The reference says:

> "For most hook events, only exit code 2 blocks the action. Claude Code treats exit code 1 as a non-blocking
> error and proceeds with the action, even though 1 is the conventional Unix failure code."

Probed directly — three dispositions, each asked to stop a `touch`; sentinel present means the tool ran:

| Hook disposition | Result | What the session was told |
|---|---|---|
| **crashes (exit 1, stderr `WALL SAYS NO`)** | **TOOL RAN** | *"Done — created SENTINEL."* — **nothing at all** |
| exit 2 with stderr | blocked | the refusal reached the model |
| exit 0 + `permissionDecision: deny` | blocked | *"The command was blocked… `WALL SAYS NO` … I ran only that one command and stopped without retrying or working around the denial."* |

Three things follow, and all three are load-bearing:

1. **Slice 5's fail-open defect is confirmed by experiment, not inference.** An unguarded `mkdir` raising inside
   `decide()` exits 1, which is not a refusal — the walled act proceeds.
2. **It is worse than permissive: it is invisible.** The stderr was swallowed and the session reported success.
   A wall whose bookkeeping breaks does not merely stop protecting; it stops existing, and nobody is told.
   This is the same failure signature as slice 4's silent banner — the round produced it twice, independently.
3. **A `deny` decision wins even under `bypassPermissions`.** Combined with §1, that means walls installed for
   the build-host user would actively refuse acts *inside the runner's own stages*, implement stage included.
   The `YR_MACHINERY` declaration is the only thing standing between the plugin and a broken pipeline.

And the positive result deserves recording too: when the deny path works, it works exactly as the "talking wall"
design intends — the model received the rule, respected it, and declined to route around it unprompted.

Two independent ways to refuse: **exit 2 with stderr**, or **exit 0 with a deny decision on stdout**. The wall
uses the second, so any crash is silently permissive. A wall must never let an exception reach the interpreter's
exit path.

## 3. PreToolUse decisions have four values, not two — **D**

`permissionDecision` ∈ `allow` · `deny` · `ask` · `defer`.

- **`ask`** escalates to the human for a permission prompt. **This is the native transport for the spec's
  severity valve.** The round defined `YR-ESCALATION` as canon and shipped no emitter for it; the harness has
  had the mechanism all along. An agent-initiated escalation at a one-way door is `ask`, not `deny`.
- **`defer`** falls through to the normal permission flow — the honest disposition for an act the model has no
  opinion about.

Also available under `hookSpecificOutput`:
- **`additionalContext`** — inject context *next to the tool result*, without blocking. **This is the native
  transport for the canon's "advisory" stance**, which until now had no mechanism and so collapsed into
  refuse-or-be-silent.
- **`updatedInput`** — rewrite the tool's arguments before it runs. Powerful and dangerous; noted, not adopted.

### 3a. The advisory stance has a working transport — **P, confirmed**

A PreToolUse hook returning `permissionDecision: allow` *plus* `additionalContext` was probed. The tool ran, and
the model reported the injected text **verbatim**, correctly attributed:

> "There was extra context attached to that tool call — a `PreToolUse:Bash` hook message, quoted verbatim:
> ADVISORY-MARKER-7Q4X …"

It even distinguished the tool-scoped injection from the SessionStart injection. So the canon's **advisory**
stance — which had no mechanism and therefore collapsed into refuse-or-be-silent — is buildable exactly as
written: teach at the moment of the act, do not block it.

### 3b. `ask` fails OPEN without a human — **P, safety-critical**

`permissionDecision: "ask"` was probed headlessly under `bypassPermissions`. Result: **the tool ran, silently.**
No prompt, no denial, no hang (13s, well inside the timeout), and the model was told nothing at all — its reply
was "NONE … there was no advisory note, system-reminder, or extra context attached to that tool call."

So the severity valve must never be the *only* guard on a fail-closed act. `ask` is an escalation on top of a
decision, not a substitute for one: where the act is fail-closed and no human is present to answer, the correct
disposition is `deny`, with `ask` reserved for contexts a human is actually attending.

*Untested and therefore unclaimed:* `ask` under a non-bypass permission mode with a human present. It presumably
prompts, but this session could not verify it headlessly, so no design should assume it.

## 4. Stop supports non-blocking feedback — **D**, and `stop_hook_active` is real — **P**

Stop accepts top-level `{"decision": "block", "reason": …}` *and* `hookSpecificOutput.additionalContext` for
"non-error feedback that continues the conversation."

That second form is exactly the design we converged on: **Stop reports, transitions gate.** The bookend to
SessionStart — arrival and hand-back — has a first-class channel that isn't a refusal.

`stop_hook_active` is **absent from the docs' common-fields table but present in the live payload** (`false` in
the probe). It is the built-in loop guard; `wall.py`'s hand-rolled "did I already block" ledger re-implements
it — a fourth instance of the re-implementation pattern.

## 5. Verified payload fields (P)

| Field | SessionStart | PreToolUse | Stop |
|---|:--:|:--:|:--:|
| `session_id`, `transcript_path`, `cwd`, `hook_event_name` | ✅ | ✅ | ✅ |
| `source` (`startup`…) | ✅ | — | — |
| `prompt_id`, `permission_mode`, `effort` | — | ✅ | ✅ |
| `tool_name`, `tool_input`, `tool_use_id` | — | ✅ | — |
| `stop_hook_active`, `last_assistant_message`, `background_tasks`, `session_crons` | — | — | ✅ |

Consequences:

- **`cwd` arrives in the payload.** The workspace boundary must read `hook["cwd"]`, **not** `Path.cwd()` — the
  hook process's own working directory is not a contract. My uncommitted `in_scope()` uses `Path.cwd()` and is
  wrong on exactly this point.
- **SessionStart carries no `permission_mode`.** Delivery cannot detect a machinery stage from the payload, so
  the `YR_MACHINERY` declaration is the only available signal there. The declared-not-sniffed rule is forced,
  not merely preferred.
- **`last_assistant_message` and `background_tasks` on Stop** are free material for a close report — including
  "you are handing back with background work still running."

## 6. Plugin hooks are user-scoped, with no built-in directory limiting — **D**

> "Plugin (`hooks/hooks.json`): Scope: When plugin is enabled."

There is no per-project or per-directory scoping for a plugin's hooks. The two available narrowings:

- the **`if` field** — permission-rule syntax (`"Bash(git *)"`, `"Edit(*.ts)"`), evaluated only on tool events;
  a declarative pre-filter that avoids invoking the engine at all. Still matches *spelling*, so it narrows cost,
  never coverage.
- **inspecting `cwd`** from the payload — which is the workspace boundary, and is ours to write.

## 7. Hooks fire inside subagents too — **D**

> "Hooks from settings files, managed policy settings, and plugins also run inside subagents… the input carries
> the `agent_id` and `agent_type` common input fields."

So the blast radius includes every subagent of every session — cold reviewers, Explore agents, workflow agents.
`SubagentStart` / `SubagentStop` exist as their own events, which is the natural seam for giving an independent
reviewer its own grounding and its own close.

## 8. SessionStart matcher values: `startup` · `resume` · `clear` · `compact` · **`fork`** — **D**

The round's `hooks/hooks.json` registers only the first four. **A forked session receives no canon** — a gap in
the delivery slice that already merged.

## 9. Timeouts and async — **D**

Command hooks default to **600s** (not the short window assumed). `async: true` runs in the background without
blocking; `asyncRewake: true` additionally wakes Claude on exit 2, surfacing stderr as a system reminder.

Delivery is registered `async: false` and must stay so — `additionalContext` has to land before the first
prompt. But its slow half (the position read: `gh repo view`, `gh pr list`, `board.sh` — up to 45s of timeouts)
is a candidate for splitting: canon synchronously, position asynchronously.

## 10. Undocumented and untested, flagged rather than assumed

- **Precedence when several matching hooks return conflicting decisions** (one `allow`, one `deny`) is not
  specified. "All matching hooks run in parallel" is all the reference says. Any design that relies on a
  conflict resolving a particular way is relying on undefined behaviour.
