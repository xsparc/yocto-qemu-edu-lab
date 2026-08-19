#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT
"""Bounded read-only host-tool adapter used by project diagnostics."""

from __future__ import annotations

import os
import re
import shutil
import signal
import stat
import subprocess
import threading
from pathlib import Path


OUTPUT_LIMIT = 64 * 1024
TIMEOUT_SECONDS = 8
MINIMUM_GIT = (2, 36, 0)
PROJECT_REF_PREFIX = "refs/yocto-qemu-edu-lab"


class ToolUnavailable(OSError):
    """A required native executable is unavailable."""


class ToolContractError(RuntimeError):
    """A tool or repository violates the fixed diagnostics contract."""


def resolve_native(name: str) -> Path:
    candidate = shutil.which(name)
    if not candidate:
        raise ToolUnavailable("required executable is unavailable")
    path = Path(candidate)
    try:
        info = path.stat()
    except OSError as exc:
        raise ToolUnavailable("required executable is unavailable") from exc
    if not stat.S_ISREG(info.st_mode):
        raise ToolContractError("selected executable is not a regular file")
    if os.name == "nt":
        if path.suffix.lower() != ".exe":
            raise ToolContractError("selected executable is not a native Windows executable")
    elif not os.access(path, os.X_OK):
        raise ToolContractError("selected executable is not executable")
    try:
        return path.resolve(strict=True)
    except OSError as exc:
        raise ToolUnavailable("required executable is unavailable") from exc


def _environment(path: Path) -> dict[str, str]:
    environment = {
        "PATH": str(path.parent),
        "LANG": "C",
        "LC_ALL": "C",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_PAGER": "cat",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_TRACE": "0",
        "GIT_TRACE2": "0",
        "GIT_TRACE_CURL": "0",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
    }
    if os.name == "nt" and "SystemRoot" in os.environ:
        environment["SystemRoot"] = os.environ["SystemRoot"]
    return environment


def _terminate(process: subprocess.Popen[bytes]) -> None:
    try:
        if os.name != "nt":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except (OSError, ProcessLookupError):
        pass


def invoke(executable: Path, cwd: Path, arguments: list[str]) -> tuple[int, bytes]:
    command = [str(executable), *arguments]
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=_environment(executable),
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=os.name != "nt",
            creationflags=creationflags,
        )
    except OSError as exc:
        raise ToolContractError("selected executable could not be started") from exc
    output = bytearray()
    overflow = threading.Event()

    def drain() -> None:
        assert process.stdout is not None
        while True:
            chunk = process.stdout.read(4096)
            if not chunk:
                return
            remaining = OUTPUT_LIMIT + 1 - len(output)
            if remaining > 0:
                output.extend(chunk[:remaining])
            if len(output) > OUTPUT_LIMIT or len(chunk) > remaining:
                overflow.set()
                _terminate(process)
                return

    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    try:
        process.wait(timeout=TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as exc:
        _terminate(process)
        process.wait()
        reader.join(timeout=1)
        if process.stdout is not None:
            process.stdout.close()
        raise ToolContractError("tool invocation exceeded its time limit") from exc
    reader.join(timeout=1)
    if reader.is_alive():
        _terminate(process)
        if process.stdout is not None:
            process.stdout.close()
        raise ToolContractError("tool output could not be drained")
    if process.stdout is not None:
        process.stdout.close()
    if overflow.is_set():
        raise ToolContractError("tool output exceeded its byte limit")
    return process.returncode, bytes(output)


def git_arguments(root: Path, arguments: list[str]) -> list[str]:
    return [
        "--no-replace-objects",
        "-c", f"safe.directory={root}",
        "-c", "core.fsmonitor=false",
        "-c", "core.untrackedCache=false",
        "-c", "maintenance.auto=false",
        "-c", "core.hooksPath=/dev/null" if os.name != "nt" else "core.hooksPath=NUL",
        "-C", str(root),
        *arguments,
    ]


def git_query(executable: Path, root: Path, *arguments: str, allow: tuple[int, ...] = (0,)) -> bytes:
    code, output = invoke(executable, root, git_arguments(root, list(arguments)))
    if code not in allow:
        raise ToolContractError("Git query failed")
    return output


def git_version(executable: Path, cwd: Path) -> tuple[int, int, int]:
    code, output = invoke(executable, cwd, ["--version"])
    match = re.fullmatch(rb"git version (\d+)\.(\d+)\.(\d+)(?:\.[^\r\n ]+)?\r?\n?", output)
    if code or not match:
        raise ToolContractError("Git version output is invalid")
    version = tuple(int(part) for part in match.groups())
    if version < MINIMUM_GIT:
        raise ToolContractError("Git version is below 2.36.0")
    return version


def has_unsupported_repository_config(executable: Path, path: Path) -> bool:
    """Detect includes and partial-clone settings before any object query."""
    output = git_query(
        executable,
        path,
        "config",
        "--local",
        "--no-includes",
        "--null",
        "--list",
    )
    for record in output.split(b"\0"):
        key = record.partition(b"\n")[0].lower()
        if key == b"include.path":
            return True
        if key.startswith(b"includeif.") and key.endswith(b".path"):
            return True
        if key in {b"extensions.partialclone", b"extensions.worktreeconfig"}:
            return True
        if key.startswith(b"remote.") and key.endswith(b".promisor"):
            return True
    return False


def origin_matches(executable: Path, path: Path, expected: str) -> bool:
    """Compare the one raw local origin URL without rewrite expansion or includes."""
    output = git_query(
        executable,
        path,
        "config",
        "--local",
        "--no-includes",
        "--null",
        "--get-all",
        "remote.origin.url",
        allow=(0, 1),
    )
    return output == expected.encode("utf-8") + b"\0"


def repository_state(executable: Path, root: Path) -> tuple[str, bool]:
    root = root.resolve(strict=True)
    if has_unsupported_repository_config(executable, root):
        raise ToolContractError(
            "included, worktree-scoped, partial, or promisor repository configuration is unsupported"
        )
    top = git_query(executable, root, "rev-parse", "--show-toplevel").decode("utf-8").strip()
    if Path(top).resolve(strict=True) != root:
        raise ToolContractError("Git top level differs from the project root")
    if git_query(executable, root, "rev-parse", "--show-object-format").strip() != b"sha1":
        raise ToolContractError("repository object format is not SHA-1")
    revision = git_query(executable, root, "rev-parse", "--verify", "HEAD").decode("ascii").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ToolContractError("repository revision is invalid")
    dirty = bool(git_query(executable, root, "status", "--porcelain=v1", "-z", "--untracked-files=normal"))
    return revision, dirty


def checkout_matches(executable: Path, path: Path, source: dict[str, object]) -> bool:
    path = path.resolve(strict=True)
    if has_unsupported_repository_config(executable, path):
        return False
    top = git_query(executable, path, "rev-parse", "--show-toplevel").decode("utf-8").strip()
    if Path(top).resolve(strict=True) != path:
        return False
    expected = str(source["commit"])
    ancestry_code, ancestry_output = invoke(
        executable,
        path,
        git_arguments(
            path,
            [
                "merge-base",
                "--is-ancestor",
                expected,
                f"{PROJECT_REF_PREFIX}/{source['id']}/branch",
            ],
        ),
    )
    queries = (
        origin_matches(executable, path, str(source["url"])),
        git_query(executable, path, "rev-parse", "--show-object-format").strip() == b"sha1",
        git_query(executable, path, "rev-parse", "--verify", "HEAD").decode("ascii").strip() == expected,
        git_query(executable, path, "symbolic-ref", "-q", "HEAD", allow=(0, 1)).strip() == b"",
        git_query(executable, path, "status", "--porcelain=v1", "-z", "--untracked-files=normal") == b"",
        git_query(executable, path, "rev-parse", f"{PROJECT_REF_PREFIX}/{source['id']}/release^{{commit}}").decode("ascii").strip() == expected,
        ancestry_code == 0 and ancestry_output == b"",
    )
    return all(queries)
