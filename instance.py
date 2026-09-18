#!/usr/bin/env python3
"""The instance's configuration: the file that names the factory's store of records and where it
works.

The configuration is a TOML file, the one the environment's `FACTORY_INSTANCE` names or, with
none named, `.config/factory/instance.toml` under the home of whoever runs the program. It is
found when the program runs and not when this module is imported, so `HOME` and the environment
are read at the call and never at the import. Its `records` is the absolute path of the store,
the directory outside every checkout where the builder leaves a record and `runs.py` reads them.
Its `work` is the absolute path of the directory the instance works in: a build clones its branch
into a directory of its own under it, and the directory is made when the configuration is read.

This module imports nothing of the builder's, so printing a table of numbers does not import the
model stack behind `builder.py`; `builder.py`, `runs.py` and `build.py` all read the configuration
through it. A configuration that is missing, is not TOML, has no `records`, or names one that is
not a string or not an absolute path is a ValueError naming the file and which fault; with a
checkout, a store that is inside it or holds it is too. A configuration without `work`, or with a
`work` that is not a string or not an absolute path, is a ValueError naming the file and which
fault, and the directory is made when it is read. Nothing else is made.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path


def instance_config() -> Path:
    """The instance's configuration file: the one the environment's `FACTORY_INSTANCE` names, or
    `.config/factory/instance.toml` under the home of whoever runs the program. Found when the
    program runs, never when it is imported. A `FACTORY_INSTANCE` that is set and empty names no
    file and is a ValueError: only an unset variable falls back to the home's configuration."""
    if "FACTORY_INSTANCE" in os.environ:
        named = os.environ["FACTORY_INSTANCE"]
        if not named:
            raise ValueError("FACTORY_INSTANCE: set and empty names no instance configuration")
        return Path(named)
    return Path.home() / ".config" / "factory" / "instance.toml"


def _read_config() -> tuple[Path, dict]:
    """The instance's configuration, as its file and the mapping it holds. A configuration that is
    missing, cannot be read or is not TOML is a ValueError naming the file and which fault; the
    environment is read at this call and never at the import."""
    config = instance_config()
    try:
        text = config.read_text(encoding="utf-8")
    except UnicodeDecodeError:  # bytes that are not UTF-8 are not TOML either
        raise ValueError(f"{config}: the instance configuration is not TOML")
    except OSError:
        raise ValueError(f"{config}: the instance configuration cannot be read")
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        raise ValueError(f"{config}: the instance configuration is not TOML")
    return config, data


def record_store(checkout: Path | None = None) -> Path:
    """The store the instance's configuration names, its `records`, as an absolute path. A
    configuration that is missing, is not TOML, has no `records`, or names one that is not a
    string or not an absolute path is a usage error naming the configuration's file and which
    fault; with a checkout, a store that is inside it or holds it is too. Nothing is made."""
    config, data = _read_config()
    records = data.get("records")
    if records is None:
        raise ValueError(f"{config}: the instance configuration has no records")
    if not isinstance(records, str):
        raise ValueError(f"{config}: records is not a string: {records!r}")
    store = Path(records)
    if not store.is_absolute():
        raise ValueError(f"{config}: records is not an absolute path: {records}")
    store = store.resolve()
    if checkout is not None:
        checkout = checkout.resolve()
        if store == checkout or checkout in store.parents:
            raise ValueError(f"{config}: records {records} is inside the checkout")
        if store in checkout.parents:
            raise ValueError(f"{config}: records {records} holds the checkout")
    return store


def work_dir() -> Path:
    """The directory the instance works in, its `work`, as an absolute path, made when it is read.
    A configuration that is missing, is not TOML, has no `work`, or names one that is not a string
    or not an absolute path is a ValueError naming the configuration's file and which fault; so is
    a `work` the process cannot make. The directory is created here, so a build always has it."""
    config, data = _read_config()
    work = data.get("work")
    if work is None:
        raise ValueError(f"{config}: the instance configuration has no work")
    if not isinstance(work, str):
        raise ValueError(f"{config}: work is not a string: {work!r}")
    path = Path(work)
    if not path.is_absolute():
        raise ValueError(f"{config}: work is not an absolute path: {work}")
    path = path.resolve()
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        raise ValueError(f"{config}: work {work} cannot be made")
    return path
