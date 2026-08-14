#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT
"""Bounded, single-read repository input helpers for diagnostics."""

from __future__ import annotations

import os
import stat
from pathlib import Path, PurePosixPath


class InputUnavailable(OSError):
    """A declared input does not currently exist or cannot be read."""


class InputContractError(ValueError):
    """A present input violates the diagnostics file contract."""


def relative_name(value: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise InputContractError("repository input name is invalid")
    candidate = PurePosixPath(value)
    if candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        raise InputContractError("repository input name is invalid")
    return candidate.as_posix()


def _is_reparse(path: Path) -> bool:
    try:
        attributes = path.lstat().st_file_attributes
    except AttributeError:
        return False
    return bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _safe_path(root: Path, relative: str) -> Path:
    relative = relative_name(relative)
    root = root.resolve(strict=True)
    current = root
    parts = PurePosixPath(relative).parts
    for part in parts[:-1]:
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError as exc:
            raise InputUnavailable("repository input is unavailable") from exc
        except OSError as exc:
            raise InputUnavailable("repository input could not be inspected") from exc
        if stat.S_ISLNK(info.st_mode) or _is_reparse(current):
            raise InputContractError("repository input traverses a link")
        if not stat.S_ISDIR(info.st_mode):
            raise InputContractError("repository input parent is not a directory")
    target = current / parts[-1]
    try:
        target.resolve(strict=False).relative_to(root)
    except (OSError, ValueError) as exc:
        raise InputContractError("repository input escapes the repository") from exc
    return target


def read_regular(root: Path, relative: str, maximum: int) -> bytes:
    """Read one non-link regular file at most once and enforce a hard byte cap."""
    if type(maximum) is not int or maximum < 1:
        raise ValueError("maximum must be a positive integer")
    target = _safe_path(root, relative)
    try:
        before = target.lstat()
    except FileNotFoundError as exc:
        raise InputUnavailable("repository input is unavailable") from exc
    except OSError as exc:
        raise InputUnavailable("repository input could not be inspected") from exc
    if stat.S_ISLNK(before.st_mode) or _is_reparse(target):
        raise InputContractError("repository input is a link")
    if not stat.S_ISREG(before.st_mode):
        raise InputContractError("repository input is not a regular file")

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(target, flags)
    except FileNotFoundError as exc:
        raise InputUnavailable("repository input is unavailable") from exc
    except OSError as exc:
        raise InputContractError("repository input could not be opened safely") from exc
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise InputContractError("repository input is not a regular file")
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise InputContractError("repository input changed before it was opened")
        raw = os.read(descriptor, maximum + 1)
        if len(raw) > maximum:
            raise InputContractError("repository input exceeds its byte limit")
        if os.read(descriptor, 1):
            raise InputContractError("repository input exceeds its byte limit")
        after = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise InputContractError("repository input changed while it was read")
        if len(raw) != after.st_size:
            raise InputContractError("repository input changed while it was read")
        return raw
    finally:
        os.close(descriptor)


def require_directory(root: Path, relative: str) -> Path:
    target = _safe_path(root, relative)
    try:
        info = target.lstat()
    except FileNotFoundError as exc:
        raise InputUnavailable("declared directory is unavailable") from exc
    except OSError as exc:
        raise InputUnavailable("declared directory could not be inspected") from exc
    if stat.S_ISLNK(info.st_mode) or _is_reparse(target) or not stat.S_ISDIR(info.st_mode):
        raise InputContractError("declared directory violates the path contract")
    return target


def require_entry(root: Path, relative: str) -> Path:
    """Require an existing regular file or directory without traversing links."""
    target = _safe_path(root, relative)
    try:
        info = target.lstat()
    except FileNotFoundError as exc:
        raise InputUnavailable("declared entry is unavailable") from exc
    except OSError as exc:
        raise InputUnavailable("declared entry could not be inspected") from exc
    if stat.S_ISLNK(info.st_mode) or _is_reparse(target):
        raise InputContractError("declared entry is a link")
    if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
        raise InputContractError("declared entry has an unsupported file type")
    return target
