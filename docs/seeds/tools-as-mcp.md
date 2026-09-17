---
created: 2026-09-16
type: seed
status: open
summary: Expose the tools as an MCP server so a frontier model in a subscription harness works under the same walls, paid by subscription; two claims to verify first.
value: 5
effort: L
version:
---

## Evidence

The roles that need a frontier model cannot run inside the pydantic-ai loop at API prices (owner, 2026-09-16). v1 ran cold `claude -p` sessions under a subscription. The tools is five functions with no dependency on the loop that calls them.

2026-09-17, the first claim checked: Claude Code 2.1.274 on the owner's subscription, no API key (`apiKeySource: none`), model haiku, run from a shell without the attended session's variables. `claude -p` with `--tools ""`, `--strict-mcp-config` and `--mcp-config` naming one stdio server with one tool, `--allowedTools` naming that tool, `--disable-slash-commands`, `--no-session-persistence` and `--setting-sources project`, in a directory holding no settings, started a session whose init listed one tool, `mcp__factory__list_files`, one server, and no skill, plugin or slash command; no hook ran. Asked to list the world, read a file in its working directory and run `ls /`, it listed the world and said it had no tool for the other two; the server received `initialize`, the initialized notification, `tools/list` and one `tools/call`, nothing more. With the user's settings read, the tool was still the only one, but twelve plugins loaded and their SessionStart hooks returned 27,061 characters into the session, so a role's context is its own only when `--setting-sources` leaves the user's settings out. The second claim is not checked. Every session streams a `rate_limit_event` with the subscription's windows, that afternoon the five-hour at 10% and the seven-day at 69% of their limits, so a loop can read its headroom and stop before a limit. The three sessions took 8 to 9 seconds and reported $0.017 to $0.021 as their cost at API prices. The server, the flags and the three streams were the attended agent's scratch of the day and are not kept. The tools are six since v0.7.

## Idea

The same tools, two loops: pydantic-ai for API models, a headless harness for frontier ones, both recorded. Checked on 2026-09-17: a headless Claude Code session runs with every built-in tool disabled and only our server allowed, the user's settings left out. Unverified and to check before any size is trusted: that a subscription tolerates being driven that way at factory rates.
