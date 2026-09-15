# factory

v0.1: the observer. A cold session that looks at a world and reports.

```sh
python3 observer.py "describe what this program does and what it cannot do"
python3 -m unittest -v          # the execution plane and the loop, without a provider
```

The world is this directory, reachable only through `list` and `read`. The provider is
DeepSeek (`deepseek-flash`), key in `~/.config/factory/deepseek.key` (the bare key, or one
`name=value` line). A run leaves
`runs/<utc-stamp>/`:

- `goal.txt` what was asked
- `transcript.jsonl` every message and every call, as it happened
- `response.md` the report
- `numbers.json` turns, calls, files and lines read, tokens, cost, seconds, and the hashes of
  the role and the wrapper that produced it
