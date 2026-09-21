#!/usr/bin/env python3
"""The host's own state, apart: the installed product's version, and nothing else.

The host is not the repository; the loop reaches it through this module alone, so `repo.py`
reads nothing of the host and `host.py` runs no git.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass

# A terminal colour escape, as `uv` writes it around the product's name; stripped before the
# version is read so a coloured `tool list` answers the same as a plain one.
COLOUR = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


@dataclass(frozen=True)
class Instance:
    """The installed product: its version, or `None` and the words of what went wrong."""

    version: str | None
    error: str


def instance() -> Instance:
    """The product's version from `uv tool list`, its colour escapes stripped, or `None` and the
    words of what went wrong when there is no factory or no uv; never raises."""
    command = "uv tool list"
    try:
        done = subprocess.run(
            ["uv", "tool", "list"], capture_output=True, text=True, errors="replace"
        )
    except (OSError, subprocess.SubprocessError) as e:
        return Instance(None, " ".join(str(e).split()))
    if done.returncode != 0:
        said = " ".join((done.stderr or done.stdout).split())
        return Instance(None, said or f"{command} failed")
    for line in COLOUR.sub("", done.stdout).splitlines():
        words = line.split()
        if len(words) >= 2 and words[0] == "factory":
            version = words[1][1:] if words[1].startswith("v") else words[1]
            return Instance(version, "")
    return Instance(None, "uv tool list names no factory")
