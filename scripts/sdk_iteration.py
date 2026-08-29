#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT
"""Run the closed direct-eSDK/devtool application-iteration lifecycle."""

from __future__ import annotations

import argparse
import configparser
import hashlib
import os
import re
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Sequence


sys.dont_write_bytecode = True

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from configure_build import (  # noqa: E402
    AUTOMATIC_BUILD_CONFIGURATION,
    ConfigurationError,
    configure_sdk as configure_authoritative_build,
    render_sdk_bblayers,
    render_sdk_local_conf,
    sdk_configuration_root,
    sdk_effective_errors,
    verify_sdk_configuration_root,
)
from lab_config import LabError  # noqa: E402
from source_lock import LockError  # noqa: E402
from sdk_evidence import (  # noqa: E402
    SdkEvidenceError,
    build_evidence,
    clear_evidence,
    evidence_path,
    project_state,
    read_evidence,
    selected_contract,
    source_authority,
    validate_evidence,
    write_evidence,
)
from sdk_tooling import SDK_RECIPE_VERSION, SdkToolingError, verify_tooling  # noqa: E402


MAX_CAPTURE_BYTES = 64 * 1024
MAX_DEVTOOL_CONFIG_BYTES = 64 * 1024
MAX_BUILD_CONFIG_BYTES = 256 * 1024
MAX_WORKSPACE_FILE_BYTES = 64 * 1024
MAX_WORKSPACE_ENTRIES = 16
MAX_SOURCE_BYTES = 64 * 1024
MAX_ARTIFACT_BYTES = 4 * 1024 * 1024
MAX_RUNQEMU_OUTPUT_BYTES = 1024 * 1024
COMMAND_TIMEOUT_SECONDS = 7200
STARTUP_TIMEOUT_SECONDS = 600
SSH_READY_TIMEOUT_SECONDS = 180
SSH_COMMAND_TIMEOUT_SECONDS = 30
STOP_TIMEOUT_SECONDS = 15
CLEANUP_TIMEOUT_SECONDS = 120
PORT_PATTERN = re.compile(
    r"hostfwd=tcp:127\.0\.0\.1:([0-9]{1,5})-:22(?=[,\s]|\Z)"
)
SAFE_SHELL_PATH = re.compile(r"/[A-Za-z0-9_./+-]+\Z")
SSH_FIXED_OPTIONS = (
    "-F", os.devnull,
    "-o", "BatchMode=yes",
    "-o", "ConnectTimeout=10",
    "-o", "ConnectionAttempts=1",
    "-o", "StrictHostKeyChecking=no",
    "-o", "UserKnownHostsFile=/dev/null",
    "-o", "LogLevel=ERROR",
    "-o", "Hostname=127.0.0.1",
    "-o", "ProxyCommand=none",
    "-o", "ProxyJump=none",
    "-o", "CanonicalizeHostname=no",
    "-o", "IdentitiesOnly=yes",
    "-o", "IdentityAgent=none",
    "-o", "IdentityFile=none",
    "-o", "ForwardAgent=no",
    "-o", "ClearAllForwardings=yes",
    "-o", "PermitLocalCommand=no",
    "-o", "RequestTTY=no",
)
UNSAFE_CHILD_ENVIRONMENT = frozenset(
    {
        "BASHOPTS",
        "BASH_ENV",
        "CDPATH",
        "ENV",
        "PYTHONBREAKPOINT",
        "PYTHONCASEOK",
        "PYTHONHOME",
        "PYTHONINSPECT",
        "PYTHONNOUSERSITE",
        "PYTHONPATH",
        "PYTHONSAFEPATH",
        "PYTHONSTARTUP",
        "PYTHONUSERBASE",
        "PYTHONWARNINGS",
        "SHELLOPTS",
    }
)
BASELINE_TEXT = "qemu-edu-sdk-sample baseline"
WORKSPACE_TEXT = "qemu-edu-sdk-sample workspace"
IDE_OUTPUT_DIRNAME = "learner-ide-sdk"
SOURCE_TEMPLATE = Path(
    "meta-qemu-edu/recipes-support/qemu-edu-sdk-sample/files/"
    "qemu-edu-sdk-sample.c"
)
WORKSPACE_LAYER_CONF = (
    'BBPATH =. "${LAYERDIR}:"\n'
    'BBFILES += "${LAYERDIR}/recipes/*/*.bb \\\n'
    '            ${LAYERDIR}/appends/*.bbappend"\n'
    'BBFILE_COLLECTIONS += "workspacelayer"\n'
    'BBFILE_PATTERN_workspacelayer = "^${LAYERDIR}/"\n'
    'BBFILE_PATTERN_IGNORE_EMPTY_workspacelayer = "1"\n'
    'BBFILE_PRIORITY_workspacelayer = "99"\n'
    'LAYERSERIES_COMPAT_workspacelayer = "wrynose"\n'
).encode("utf-8")


def expected_workspace_append(recipe: str, source_dir: Path) -> bytes:
    """Return the only executable bbappend statements the controller accepts."""
    return (
        'FILESEXTRAPATHS:prepend := "${THISDIR}/${PN}:"\n'
        f'FILESPATH:prepend := "{source_dir / "oe-local-files"}:"\n'
        'inherit externalsrc\n'
        f'EXTERNALSRC:pn-{recipe} = "{source_dir}"\n'
        f'EXTERNALSRC_BUILD:pn-{recipe} = "{source_dir}"\n'
    ).encode("utf-8")


def workspace_append_name(recipe: str) -> str:
    """Return the exact versioned append name emitted by locked devtool."""
    return f"{recipe}_{SDK_RECIPE_VERSION}.bbappend"


def executable_bitbake_statements(raw: bytes) -> bytes:
    """Drop blank/full-comment lines while preserving every executable byte."""
    lines = raw.splitlines()
    executable = [
        line
        for line in lines
        if line.strip() and not line.lstrip().startswith(b"#")
    ]
    return b"\n".join(executable) + b"\n"


class SdkIterationError(RuntimeError):
    """The bounded SDK iteration could not complete safely."""


class SdkCancellation(SdkIterationError):
    """A host signal requested a controlled, restorative cancellation."""

    def __init__(self, signum: int) -> None:
        super().__init__(f"SDK iteration interrupted by signal {signum}")
        self.signum = signum


class DeferredCancellation:
    """Record host cancellation while a restorative critical section runs."""

    def __init__(self, *, raise_on_exit: bool = True) -> None:
        self.signum: int | None = None
        self._handlers: dict[int, Any] = {}
        self.raise_on_exit = raise_on_exit

    def _record(self, signum: int, _frame: Any) -> None:
        if self.signum is None:
            self.signum = signum

    def __enter__(self) -> "DeferredCancellation":
        if threading.current_thread() is not threading.main_thread():
            return self
        for name in ("SIGTERM", "SIGHUP", "SIGINT"):
            signum = getattr(signal, name, None)
            if signum is None:
                continue
            try:
                self._handlers[signum] = signal.getsignal(signum)
                signal.signal(signum, self._record)
            except (OSError, ValueError):
                self._handlers.pop(signum, None)
        return self

    def __exit__(
        self,
        exc_type: Any,
        exc: BaseException | None,
        traceback: Any,
    ) -> bool:
        del exc_type, traceback
        for signum, handler in self._handlers.items():
            signal.signal(signum, handler)
        if self.signum is not None:
            cancellation = SdkCancellation(self.signum)
            if exc is None and self.raise_on_exit:
                raise cancellation
            if exc is not None:
                exc.add_note(str(cancellation))
        return False


def _process_group_exists(group_id: int) -> bool:
    try:
        os.killpg(group_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    """Terminate and reap the complete session, even after its leader exits."""
    group_id = process.pid
    if _process_group_exists(group_id):
        try:
            os.killpg(group_id, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + STOP_TIMEOUT_SECONDS
    while _process_group_exists(group_id) and time.monotonic() < deadline:
        time.sleep(0.05)
    if _process_group_exists(group_id):
        try:
            os.killpg(group_id, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=STOP_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as exc:
        raise SdkIterationError("a process-group leader did not stop") from exc
    deadline = time.monotonic() + STOP_TIMEOUT_SECONDS
    while _process_group_exists(group_id) and time.monotonic() < deadline:
        time.sleep(0.05)
    if _process_group_exists(group_id):
        raise SdkIterationError("a process group did not stop")


def command_environment(
    overrides: dict[str, str] | None = None,
    *,
    locked_python_path: Path | None = None,
) -> dict[str, str]:
    """Return a child environment without ambient module/startup injection."""
    environment = os.environ.copy()
    if overrides is not None:
        environment.update(overrides)
    for key in UNSAFE_CHILD_ENVIRONMENT:
        environment.pop(key, None)
    environment["PYTHONNOUSERSITE"] = "1"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    if locked_python_path is not None:
        environment["PYTHONPATH"] = str(locked_python_path)
    return environment


class CommandRunner:
    """Run fixed commands without retaining their build logs."""

    def __init__(self) -> None:
        self.ssh_executable = "ssh"
        self.locked_python_path: Path | None = None

    @staticmethod
    def _terminate(process: subprocess.Popen[bytes]) -> None:
        with DeferredCancellation():
            if os.name == "posix":
                _terminate_process_group(process)
                return
            if process.poll() is None:
                process.kill()
                process.wait()

    def run(
        self,
        arguments: Sequence[str],
        *,
        capture: bool = False,
        check: bool = True,
        timeout: int = COMMAND_TIMEOUT_SECONDS,
        environment: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        child_environment = command_environment(
            environment,
            locked_python_path=self.locked_python_path,
        )
        try:
            process = subprocess.Popen(
                list(arguments),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE if capture else None,
                stderr=subprocess.STDOUT if capture else None,
                start_new_session=os.name == "posix",
                env=child_environment,
            )
        except OSError as exc:
            raise SdkIterationError("a required command was unavailable") from exc
        captured = bytearray()
        overflow = threading.Event()

        def read_output() -> None:
            assert process.stdout is not None
            while True:
                chunk = process.stdout.read(4096)
                if not chunk:
                    return
                if len(captured) + len(chunk) > MAX_CAPTURE_BYTES:
                    overflow.set()
                    return
                captured.extend(chunk)

        reader: threading.Thread | None = None
        if capture:
            reader = threading.Thread(target=read_output, daemon=True)
            reader.start()
        deadline = time.monotonic() + timeout
        try:
            while process.poll() is None:
                if overflow.is_set():
                    self._terminate(process)
                    raise SdkIterationError("a command exceeded the bounded output limit")
                if time.monotonic() >= deadline:
                    self._terminate(process)
                    raise SdkIterationError("a required command timed out")
                time.sleep(0.05)
            if reader is not None:
                reader.join(timeout=STOP_TIMEOUT_SECONDS)
                if reader.is_alive():
                    self._terminate(process)
                    raise SdkIterationError("a command output reader did not stop")
                if overflow.is_set():
                    raise SdkIterationError("a command exceeded the bounded output limit")
        except BaseException:
            self._terminate(process)
            if reader is not None:
                reader.join(timeout=STOP_TIMEOUT_SECONDS)
            raise
        finally:
            if process.stdout is not None:
                process.stdout.close()
        stdout = captured.decode("utf-8", errors="replace") if capture else ""
        result = subprocess.CompletedProcess(
            list(arguments), process.returncode, stdout, ""
        )
        if check and result.returncode != 0:
            command_name = Path(str(arguments[0])).name
            if not re.fullmatch(r"[A-Za-z0-9._+-]{1,64}", command_name):
                command_name = "command"
            raise SdkIterationError(
                f"{command_name} failed with exit status {result.returncode}"
            )
        return result

    def output(self, arguments: Sequence[str], *, timeout: int = 120) -> str:
        return self.run(arguments, capture=True, timeout=timeout).stdout.strip()


def ssh_arguments(
    port: int,
    remote: Sequence[str],
    *,
    executable: str = "ssh",
) -> list[str]:
    if type(port) is not int or not 1024 <= port <= 65535:
        raise SdkIterationError("runqemu selected an invalid SSH port")
    if not isinstance(executable, str) or not executable:
        raise SdkIterationError("SSH executable is invalid")
    if not remote or any(not isinstance(item, str) or not item for item in remote):
        raise SdkIterationError("remote command is invalid")
    return [
        executable,
        *SSH_FIXED_OPTIONS,
        "-p", str(port),
        "root@127.0.0.1",
        *remote,
    ]


def resolve_host_executable(command: str) -> Path:
    """Resolve one regular host prerequisite before any build-tree mutation."""
    candidate = shutil.which(command)
    if candidate is None:
        raise SdkIterationError("a required SDK iteration command is unavailable")
    path = Path(candidate)
    try:
        info = path.stat()
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise SdkIterationError("a required host executable is unavailable") from exc
    if not stat.S_ISREG(info.st_mode) or not os.access(resolved, os.X_OK):
        raise SdkIterationError("a required host executable is not regular")
    return resolved


def create_transport_wrappers(
    ssh_executable: Path,
    scp_executable: Path,
) -> tuple[tempfile.TemporaryDirectory[str], Path, Path]:
    """Create fixed executable wrappers for devtool's ssh and scp calls."""
    directory = tempfile.TemporaryDirectory(prefix="qemu-edu-sdk-ssh-")
    ssh_wrapper = Path(directory.name) / "ssh"
    scp_wrapper = Path(directory.name) / "scp"
    if os.name == "posix" and not SAFE_SHELL_PATH.fullmatch(str(ssh_wrapper)):
        directory.cleanup()
        raise SdkIterationError("temporary SSH wrapper path is unsafe")
    ssh_command = " ".join(
        shlex.quote(value) for value in (str(ssh_executable), *SSH_FIXED_OPTIONS)
    )
    scp_command = shlex.quote(str(scp_executable))
    try:
        ssh_wrapper.write_text(
            "#!/bin/sh\nexec " + ssh_command + ' "$@"\n',
            encoding="utf-8",
            newline="\n",
        )
        scp_wrapper.write_text(
            "#!/bin/sh\nexec " + scp_command + ' "$@"\n',
            encoding="utf-8",
            newline="\n",
        )
        ssh_wrapper.chmod(0o700)
        scp_wrapper.chmod(0o700)
    except OSError as exc:
        directory.cleanup()
        raise SdkIterationError("temporary transport wrapper is unavailable") from exc
    return directory, ssh_wrapper, scp_wrapper


def parse_ssh_port(output: str) -> int | None:
    matches = {int(value) for value in PORT_PATTERN.findall(output)}
    if len(matches) > 1:
        raise SdkIterationError("runqemu reported conflicting SSH forwards")
    if not matches:
        return None
    port = matches.pop()
    if not 1024 <= port <= 65535:
        raise SdkIterationError("runqemu selected an invalid SSH port")
    return port


class BootSession:
    """Own one foreground runqemu process and its loopback SSH transport."""

    def __init__(
        self,
        runner: CommandRunner,
        machine: str,
        image: str,
        *,
        popen: Any = subprocess.Popen,
    ) -> None:
        self.runner = runner
        self.machine = machine
        self.image = image
        self.popen = popen
        self.process: subprocess.Popen[bytes] | None = None
        self.port: int | None = None
        self._reader: threading.Thread | None = None
        self._startup_output = bytearray()
        self._output_lock = threading.Lock()
        self._output_overflow = threading.Event()
        self._startup_complete = threading.Event()

    def start(self) -> None:
        if os.name != "posix":
            raise SdkIterationError("SDK iteration requires a native Linux host")
        if self.process is not None:
            raise SdkIterationError("runqemu session is already active")
        try:
            self.process = self.popen(
                [
                    "runqemu",
                    self.machine,
                    self.image,
                    "ext4.zst",
                    "nographic",
                    "slirp",
                    "snapshot",
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                env=command_environment(
                    locked_python_path=self.runner.locked_python_path,
                ),
            )
        except OSError as exc:
            raise SdkIterationError("runqemu could not start") from exc
        if self.process.stdout is None:
            raise SdkIterationError("runqemu output pipe is unavailable")
        self._reader = threading.Thread(target=self._read_output, daemon=True)
        self._reader.start()
        deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise SdkIterationError("runqemu exited before publishing SSH transport")
            if self._output_overflow.is_set():
                raise SdkIterationError("runqemu startup output exceeded its bound")
            with self._output_lock:
                text = self._startup_output.decode("utf-8", errors="replace")
            port = parse_ssh_port(text)
            if port is not None:
                self.port = port
                self._wait_for_ssh(deadline)
                self._startup_complete.set()
                return
            time.sleep(0.1)
        raise SdkIterationError("runqemu did not publish a ready SSH transport")

    def _read_output(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        try:
            while True:
                chunk = self.process.stdout.read(4096)
                if not chunk:
                    break
                if self._startup_complete.is_set():
                    continue
                with self._output_lock:
                    if len(self._startup_output) + len(chunk) > MAX_RUNQEMU_OUTPUT_BYTES:
                        self._output_overflow.set()
                    else:
                        self._startup_output.extend(chunk)
        finally:
            self._startup_complete.set()

    def _wait_for_ssh(self, startup_deadline: float) -> None:
        assert self.port is not None
        deadline = min(startup_deadline, time.monotonic() + SSH_READY_TIMEOUT_SECONDS)
        while time.monotonic() < deadline:
            if self._output_overflow.is_set():
                raise SdkIterationError("runqemu startup output exceeded its bound")
            if self.process is None or self.process.poll() is not None:
                raise SdkIterationError("runqemu exited before SSH became ready")
            result = self.runner.run(
                ssh_arguments(
                    self.port,
                    ["true"],
                    executable=self.runner.ssh_executable,
                ),
                capture=True,
                check=False,
                timeout=SSH_COMMAND_TIMEOUT_SECONDS,
            )
            if result.returncode == 0:
                return
            time.sleep(1)
        raise SdkIterationError("runqemu SSH transport did not become ready")

    def remote(self, arguments: Sequence[str]) -> str:
        if self.process is None or self.process.poll() is not None or self.port is None:
            raise SdkIterationError("runqemu session is not active")
        return self.runner.output(
            ssh_arguments(
                self.port,
                arguments,
                executable=self.runner.ssh_executable,
            ),
            timeout=SSH_COMMAND_TIMEOUT_SECONDS,
        )

    def stop(self) -> None:
        with DeferredCancellation():
            self._stop_uninterrupted()

    def _stop_uninterrupted(self) -> None:
        process = self.process
        self._startup_complete.set()
        if process is None:
            self.port = None
            return
        if os.name == "posix":
            _terminate_process_group(process)
        elif process.poll() is None:
            process.kill()
            process.wait(timeout=STOP_TIMEOUT_SECONDS)
        if self._reader is not None:
            self._reader.join(timeout=STOP_TIMEOUT_SECONDS)
            if self._reader.is_alive():
                raise SdkIterationError("runqemu output reader did not stop")
        if process.stdout is not None:
            process.stdout.close()
        self.process = None
        self.port = None


class DirectSdkIteration:
    """Execute one catalog-selected lifecycle with restorative cleanup."""

    def __init__(
        self,
        repo: Path,
        lab_id: str,
        build_dir: Path,
        *,
        runner: CommandRunner | None = None,
        boot_factory: Any = BootSession,
    ) -> None:
        self.repo = repo.resolve()
        if os.name == "posix" and not SAFE_SHELL_PATH.fullmatch(str(self.repo)):
            raise SdkIterationError("repository path is unsafe for locked devtool")
        self.runner = runner or CommandRunner()
        self.boot_factory = boot_factory
        (
            self.manifest,
            self.lab_id,
            _,
            _,
            self.identity,
        ) = selected_contract(self.repo, lab_id)
        self.development = self.manifest["development"]
        self.machine = self.manifest["build"]["machine"]
        self.image = self.manifest["build"]["targets"][0]
        self.recipe = self.development["recipe"]
        self.guest_binary = self.development["guest_binary"]
        requested_build = build_dir.absolute()
        expected_build = self.repo / self.development["build_dir"]
        if requested_build != expected_build:
            raise SdkIterationError("SDK build directory differs from the lab contract")
        if expected_build.is_symlink() or (
            expected_build.exists() and not expected_build.is_dir()
        ):
            raise SdkIterationError("SDK build directory is not a regular directory")
        if expected_build.exists() and expected_build.resolve(strict=True) != expected_build:
            raise SdkIterationError("SDK build directory escapes the lab contract")
        self.build_dir = expected_build
        self.configuration_root = sdk_configuration_root(self.repo, self.manifest)
        conf_dir = self.build_dir / "conf"
        for path, kind in (
            (conf_dir, "directory"),
            (conf_dir / "local.conf", "file"),
            (conf_dir / "bblayers.conf", "file"),
        ):
            if path.is_symlink() or (
                path.exists()
                and ((kind == "directory" and not path.is_dir()) or (kind == "file" and not path.is_file()))
            ):
                raise SdkIterationError("SDK build configuration path is unsafe")
            if path.exists() and path.resolve(strict=True) != path:
                raise SdkIterationError("SDK build configuration escapes the lab contract")
        self.workspace = self.build_dir / "workspace"
        self.devtool_config = self.build_dir / "conf/devtool.conf"
        self.source_dir = self.build_dir / Path(self.development["source_dir"])
        if self.source_dir.parent != self.build_dir / "learner-source":
            raise SdkIterationError("SDK source directory differs from the closed profile")
        self.source_file = self.source_dir / "qemu-edu-sdk-sample.c"
        self.ide_output = self.build_dir / IDE_OUTPUT_DIRNAME
        self.output = evidence_path(self.repo, self.manifest, self.build_dir)
        self.workspace_added = False
        self.recipe_modified = False
        self.deployed = False
        self.deployment_attempted = False
        self.active_boot: BootSession | None = None
        self.ssh_wrapper: Path | None = None
        self.scp_wrapper: Path | None = None
        self.committed = False

    def _reject_automatic_configuration(self) -> None:
        """Reject build-local files that BitBake loads outside local.conf."""
        conf_dir = self.build_dir / "conf"
        for name in AUTOMATIC_BUILD_CONFIGURATION:
            path = conf_dir / name
            if path.exists() or path.is_symlink():
                raise SdkIterationError(
                    f"SDK configuration contains automatically parsed {path.name}"
                )

    def _configuration_state(self) -> str:
        """Classify raw configuration without invoking BitBake or layer code."""
        self._reject_automatic_configuration()
        conf_dir = self.build_dir / "conf"
        local_path = conf_dir / "local.conf"
        layers_path = conf_dir / "bblayers.conf"
        try:
            if any(
                path.is_symlink() or not path.is_file()
                for path in (local_path, layers_path)
            ):
                return "unknown"
            with local_path.open("rb") as handle:
                local_raw = handle.read(MAX_BUILD_CONFIG_BYTES + 1)
            with layers_path.open("rb") as handle:
                layers_raw = handle.read(MAX_BUILD_CONFIG_BYTES + 1)
            if (
                len(local_raw) > MAX_BUILD_CONFIG_BYTES
                or len(layers_raw) > MAX_BUILD_CONFIG_BYTES
            ):
                return "unknown"
            local = local_raw.decode("utf-8")
            layers = layers_raw.decode("utf-8")
        except (OSError, UnicodeDecodeError):
            return "unknown"
        if local != render_sdk_local_conf(self.manifest):
            return "unknown"
        try:
            verify_sdk_configuration_root(
                self.configuration_root,
                render_sdk_local_conf(self.manifest),
            )
        except ConfigurationError:
            return "unknown"
        base = render_sdk_bblayers(self.repo, self.manifest)
        active = render_sdk_bblayers(
            self.repo,
            self.manifest,
            workspace=self.workspace,
        )
        if layers == base:
            return "base"
        if layers == active:
            return "workspace"
        return "unknown"

    def _verify_closed_configuration(self, expected: str) -> None:
        if self._configuration_state() != expected:
            raise SdkIterationError("SDK build configuration is not authoritative")

    def preflight_repository(self) -> None:
        """Check immutable inputs and clear stale evidence before environment setup."""
        clear_evidence(self.output)
        source_authority(self.repo)
        _, dirty = project_state(self.repo)
        if dirty:
            raise SdkIterationError("SDK iteration requires a clean repository")
        self._reject_automatic_configuration()

    def _composition_preflight(self) -> None:
        self._verify_closed_configuration("base")
        distro = self.runner.output(["bitbake-getvar", "--value", "DISTRO"])
        machine = self.runner.output(["bitbake-getvar", "--value", "MACHINE"])
        bblayers = self.runner.output(["bitbake-getvar", "--value", "BBLAYERS"])
        bbpath = self.runner.output(["bitbake-getvar", "--value", "BBPATH"])
        errors = sdk_effective_errors(
            self.repo,
            self.manifest,
            build_dir=self.build_dir,
            distro=distro,
            machine=machine,
            bblayers=bblayers,
            bbpath=bbpath,
        )
        if errors:
            raise SdkIterationError("effective build composition is not authoritative")

    def _verify_devtool_config(self) -> None:
        """Require devtool to select only the declared disposable workspace."""
        path = self.devtool_config
        try:
            if path.is_symlink() or not path.is_file():
                raise SdkIterationError("devtool configuration is unavailable")
            path.resolve(strict=True).relative_to(self.build_dir.resolve(strict=True))
            with path.open("rb") as handle:
                raw = handle.read(MAX_DEVTOOL_CONFIG_BYTES + 1)
        except (OSError, ValueError) as exc:
            raise SdkIterationError("devtool configuration is unavailable") from exc
        if len(raw) > MAX_DEVTOOL_CONFIG_BYTES:
            raise SdkIterationError("devtool configuration exceeds its byte bound")
        try:
            parser = configparser.ConfigParser(interpolation=None)
            parser.read_string(raw.decode("utf-8"))
        except (UnicodeDecodeError, configparser.Error) as exc:
            raise SdkIterationError("devtool configuration is invalid") from exc
        if parser.sections() != ["General"] or dict(parser.items("General")) != {
            "workspace_path": str(self.workspace),
        }:
            raise SdkIterationError("devtool configuration is not authoritative")

    def _ensure_devtool_config(self) -> None:
        """Create the closed default-workspace config when devtool omits it."""
        if self.devtool_config.exists():
            self._verify_devtool_config()
            return
        conf_dir = self.devtool_config.parent
        if conf_dir.is_symlink() or not conf_dir.is_dir():
            raise SdkIterationError("devtool configuration directory is unavailable")
        if conf_dir.resolve(strict=True) != conf_dir:
            raise SdkIterationError("devtool configuration directory escapes the build root")
        payload = f"[General]\nworkspace_path = {self.workspace}\n"
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                prefix=".devtool-conf-",
                suffix=".tmp",
                dir=conf_dir,
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.devtool_config)
        except OSError as exc:
            raise SdkIterationError("devtool configuration is unavailable") from exc
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
        self._verify_devtool_config()

    def _verify_workspace(
        self,
        *,
        resting: bool,
        require_active: bool = False,
    ) -> None:
        """Accept only the closed active or inert tree produced by locked devtool."""
        if resting and require_active:
            raise SdkIterationError("workspace state requirement is inconsistent")
        workspace = self.workspace
        try:
            if workspace.is_symlink() or not workspace.is_dir():
                raise SdkIterationError("workspace is not a regular directory")
            workspace_root = workspace.resolve(strict=True)
            if workspace_root != workspace:
                raise SdkIterationError("workspace escapes the selected development root")
            entries = list(workspace.iterdir())
        except OSError as exc:
            raise SdkIterationError("workspace is unavailable") from exc
        if len(entries) > MAX_WORKSPACE_ENTRIES:
            raise SdkIterationError("workspace exceeds its entry bound")
        expected = {"conf", "README", "appends", "recipes", ".devtool_md5"}
        names = {entry.name for entry in entries}
        if not {"conf", "README"}.issubset(names) or names - expected:
            raise SdkIterationError("workspace contains unexpected residual state")

        for entry in entries:
            try:
                if entry.is_symlink():
                    raise SdkIterationError("workspace contains unsafe residual state")
                entry.resolve(strict=True).relative_to(workspace_root)
            except (OSError, ValueError) as exc:
                raise SdkIterationError("workspace contains unsafe residual state") from exc

        conf_dir = workspace / "conf"
        layer_conf = conf_dir / "layer.conf"
        try:
            if conf_dir.is_symlink() or not conf_dir.is_dir():
                raise SdkIterationError("workspace metadata is unavailable")
            conf_entries = list(conf_dir.iterdir())
            if conf_entries != [layer_conf] or layer_conf.is_symlink() or not layer_conf.is_file():
                raise SdkIterationError("workspace metadata is not authoritative")
            with layer_conf.open("rb") as handle:
                layer_bytes = handle.read(MAX_WORKSPACE_FILE_BYTES + 1)
        except OSError as exc:
            raise SdkIterationError("workspace metadata is unavailable") from exc
        if executable_bitbake_statements(layer_bytes) != WORKSPACE_LAYER_CONF:
            raise SdkIterationError("workspace metadata is not authoritative")

        readme = workspace / "README"
        try:
            if readme.is_symlink() or not readme.is_file():
                raise SdkIterationError("workspace README is unavailable")
            if readme.stat().st_size > MAX_WORKSPACE_FILE_BYTES:
                raise SdkIterationError("workspace README exceeds its byte bound")
        except OSError as exc:
            raise SdkIterationError("workspace README is unavailable") from exc

        active_append_digest: str | None = None
        appends = workspace / "appends"
        if appends.exists():
            try:
                if appends.is_symlink() or not appends.is_dir():
                    raise SdkIterationError("workspace contains unsafe residual state")
                append_entries = list(appends.iterdir())
            except OSError as exc:
                raise SdkIterationError("workspace contains unsafe residual state") from exc
            expected_append = appends / workspace_append_name(self.recipe)
            if resting:
                if append_entries:
                    raise SdkIterationError("workspace contains unexpected residual state")
            elif append_entries:
                try:
                    if (
                        append_entries != [expected_append]
                        or expected_append.is_symlink()
                        or not expected_append.is_file()
                    ):
                        raise SdkIterationError("workspace contains unexpected active state")
                    with expected_append.open("rb") as handle:
                        append_bytes = handle.read(MAX_WORKSPACE_FILE_BYTES + 1)
                except OSError as exc:
                    raise SdkIterationError("workspace contains unsafe active state") from exc
                if len(append_bytes) > MAX_WORKSPACE_FILE_BYTES:
                    raise SdkIterationError("workspace append exceeds its byte bound")
                if executable_bitbake_statements(
                    append_bytes
                ) != expected_workspace_append(self.recipe, self.source_dir):
                    raise SdkIterationError(
                        "workspace append is not authoritative"
                    )
                active_append_digest = hashlib.md5(
                    append_bytes,
                    usedforsecurity=False,
                ).hexdigest()

        recipes = workspace / "recipes"
        if recipes.exists():
            try:
                if recipes.is_symlink() or not recipes.is_dir() or any(recipes.iterdir()):
                    raise SdkIterationError("workspace contains unexpected residual state")
            except OSError as exc:
                raise SdkIterationError("workspace contains unsafe residual state") from exc

        checksum_state = workspace / ".devtool_md5"
        if checksum_state.exists():
            try:
                if (
                    checksum_state.is_symlink()
                    or not checksum_state.is_file()
                ):
                    raise SdkIterationError("workspace checksum state is unsafe")
                with checksum_state.open("rb") as handle:
                    checksum_bytes = handle.read(MAX_WORKSPACE_FILE_BYTES + 1)
            except OSError as exc:
                raise SdkIterationError("workspace checksum state is unavailable") from exc
            if len(checksum_bytes) > MAX_WORKSPACE_FILE_BYTES:
                raise SdkIterationError("workspace checksum state exceeds its byte bound")
            expected_checksum = b""
            if not resting and active_append_digest is not None:
                expected_checksum = (
                    f"{self.recipe}|appends/{workspace_append_name(self.recipe)}|"
                    f"{active_append_digest}\n"
                ).encode("ascii")
            if checksum_bytes != expected_checksum:
                raise SdkIterationError("workspace checksum state is not authoritative")
        elif not resting and active_append_digest is not None:
            raise SdkIterationError("workspace checksum state is unavailable")
        if require_active and active_append_digest is None:
            raise SdkIterationError("workspace active append is unavailable")

    def _verify_learner_root(self) -> None:
        """Reject a retained-source parent that could redirect later writes."""
        learner_root = self.source_dir.parent
        try:
            if learner_root.is_symlink() or (
                learner_root.exists() and not learner_root.is_dir()
            ):
                raise SdkIterationError("learner source root is not a regular directory")
            if learner_root.exists() and learner_root.resolve(strict=True) != learner_root:
                raise SdkIterationError("learner source root escapes the development root")
        except OSError as exc:
            raise SdkIterationError("learner source root is unavailable") from exc

    def _preflight_retained_outputs(self) -> None:
        """Reject caller-owned results before tooling or build mutation."""
        self._verify_learner_root()
        try:
            if self.ide_output.exists() or self.ide_output.is_symlink():
                raise SdkIterationError(
                    "retained IDE output must be moved before a new run"
                )
            if self.source_dir.exists() or self.source_dir.is_symlink():
                raise SdkIterationError(
                    "retained learner source must be moved before a new run"
                )
        except OSError as exc:
            raise SdkIterationError("retained SDK output is unavailable") from exc

    def _prepare_workspace(self) -> str:
        self._preflight_retained_outputs()
        if self.workspace.is_symlink() or (
            self.workspace.exists() and not self.workspace.is_dir()
        ):
            raise SdkIterationError("workspace is not a regular directory")
        if self.workspace.exists() and self.workspace.resolve(strict=True) != self.workspace:
            raise SdkIterationError("workspace escapes the selected development root")
        workspace_conf = self.workspace / "conf/layer.conf"
        if workspace_conf.is_file() and not workspace_conf.is_symlink():
            self._verify_workspace(resting=True)
            self._verify_devtool_config()
        elif self.workspace.exists():
            raise SdkIterationError("existing workspace is not a regular devtool layer")
        self._ensure_devtool_config()
        self.runner.run(["devtool", "create-workspace", str(self.workspace)])
        self.workspace_added = True
        configure_authoritative_build(
            self.repo,
            self.build_dir,
            self.manifest,
            workspace=self.workspace,
        )
        self._verify_closed_configuration("workspace")
        self._verify_workspace(resting=True)
        self._verify_devtool_config()
        if self.runner.output(["devtool", "-q", "status"]):
            raise SdkIterationError("development build already has modified recipes")

        template = self.repo / SOURCE_TEMPLATE
        try:
            if template.is_symlink() or not template.is_file():
                raise SdkIterationError("SDK sample source template is not a regular file")
            template_raw = template.read_bytes()
            if len(template_raw) > MAX_SOURCE_BYTES:
                raise SdkIterationError("SDK sample source template exceeds its byte bound")
            template_text = template_raw.decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise SdkIterationError("SDK sample source template is unavailable") from exc
        if template_text.count(BASELINE_TEXT) != 1:
            raise SdkIterationError("SDK sample source template is not recognized")
        workspace_text = template_text.replace(BASELINE_TEXT, WORKSPACE_TEXT)

        learner_root = self.source_dir.parent
        if not learner_root.exists():
            learner_root.mkdir()
        self._verify_learner_root()
        self.source_dir.mkdir()
        if self.source_dir.resolve(strict=True) != self.source_dir:
            raise SdkIterationError("SDK source directory escapes the selected workspace")
        temporary = self.source_file.with_suffix(".c.tmp")
        temporary.write_text(workspace_text, encoding="utf-8", newline="\n")
        os.replace(temporary, self.source_file)
        return hashlib.sha256(self.source_file.read_bytes()).hexdigest()

    def _retain_ide_output(self) -> None:
        """Move generated IDE output outside the authenticated metadata workspace."""
        generated = self.workspace / "ide-sdk"
        try:
            if generated.is_symlink() or not generated.is_dir():
                raise SdkIterationError("generated IDE output is unavailable")
            if generated.resolve(strict=True) != generated:
                raise SdkIterationError("generated IDE output escapes the workspace")
            if self.ide_output.exists() or self.ide_output.is_symlink():
                raise SdkIterationError("retained IDE output already exists")
            if self.ide_output.parent.resolve(strict=True) != self.build_dir:
                raise SdkIterationError("retained IDE output path is unavailable")
            os.replace(generated, self.ide_output)
            if generated.exists() or self.ide_output.resolve(strict=True) != self.ide_output:
                raise SdkIterationError("generated IDE output could not be retained")
        except OSError as exc:
            raise SdkIterationError("generated IDE output could not be retained") from exc

    def _deploy_arguments(self, command: str, port: int) -> list[str]:
        if self.ssh_wrapper is None or self.scp_wrapper is None:
            raise SdkIterationError("isolated SSH transport is unavailable")
        arguments = [
            "devtool",
            command,
            "-c",
            "-P",
            str(port),
            "-e",
            str(self.ssh_wrapper),
        ]
        if command == "deploy-target":
            arguments.append("--no-strip")
        return [*arguments, self.recipe, "root@127.0.0.1"]

    def _deploy_environment(self) -> dict[str, str]:
        if self.ssh_wrapper is None or self.scp_wrapper is None:
            raise SdkIterationError("isolated SSH transport is unavailable")
        directory = str(self.ssh_wrapper.parent)
        return {
            "PATH": directory + os.pathsep + os.environ.get("PATH", ""),
            "TMPDIR": directory,
            "TMP": directory,
            "TEMP": directory,
        }

    def _built_artifact_digest(self) -> str:
        """Bind deployment to the exact installed file produced by the recipe."""
        install_root = Path(
            self.runner.output(
                ["bitbake-getvar", "--value", "--recipe", self.recipe, "D"]
            )
        )
        bindir = self.runner.output(
            ["bitbake-getvar", "--value", "--recipe", self.recipe, "bindir"]
        )
        if bindir != "/usr/bin" or not install_root.is_absolute():
            raise SdkIterationError("built SDK artifact path is not authoritative")
        artifact = install_root / self.guest_binary.lstrip("/")
        try:
            build_root = self.build_dir.resolve(strict=True)
            if artifact.is_symlink() or not artifact.is_file():
                raise SdkIterationError("built SDK artifact is unavailable")
            artifact.resolve(strict=True).relative_to(build_root)
            with artifact.open("rb") as handle:
                raw = handle.read(MAX_ARTIFACT_BYTES + 1)
        except (OSError, ValueError) as exc:
            raise SdkIterationError("built SDK artifact is unavailable") from exc
        if len(raw) > MAX_ARTIFACT_BYTES:
            raise SdkIterationError("built SDK artifact exceeds its byte bound")
        return hashlib.sha256(raw).hexdigest()

    def _verify_remote_artifact(self, boot: BootSession, digest: str) -> None:
        output = boot.remote(["sha256sum", self.guest_binary])
        fields = output.split()
        if fields != [digest, self.guest_binary]:
            raise SdkIterationError("deployed artifact differs from the built artifact")

    def _cleanup_development_state(self) -> None:
        with DeferredCancellation():
            self._cleanup_development_state_uninterrupted()

    def _cleanup_development_state_uninterrupted(self) -> None:
        failures: list[str] = []
        cancellation: SdkCancellation | None = None

        def record_failure(label: str, exc: BaseException | None = None) -> None:
            nonlocal cancellation
            failures.append(label)
            if isinstance(exc, SdkCancellation) and cancellation is None:
                cancellation = exc
            elif isinstance(exc, KeyboardInterrupt) and cancellation is None:
                cancellation = SdkCancellation(signal.SIGINT)

        configuration = "unknown"
        composition_restored = False
        workspace_safe = True
        workspace_active = False

        generated_ide_output = self.workspace / "ide-sdk"
        if generated_ide_output.exists() or generated_ide_output.is_symlink():
            try:
                self._retain_ide_output()
            except SdkIterationError as exc:
                record_failure("workspace residual state", exc)
                workspace_safe = False

        try:
            configuration = self._configuration_state()
        except (Exception, KeyboardInterrupt) as exc:
            record_failure("configuration authority", exc)
        if configuration == "workspace":
            self.workspace_added = True

        if self.workspace.exists() or self.workspace.is_symlink():
            try:
                self._verify_workspace(
                    resting=False,
                    require_active=self.recipe_modified,
                )
                workspace_active = (
                    self.workspace
                    / "appends"
                    / workspace_append_name(self.recipe)
                ).is_file()
            except (SdkIterationError, KeyboardInterrupt) as exc:
                record_failure("workspace residual state", exc)
                workspace_safe = False
        elif self.workspace_added or self.recipe_modified:
            record_failure("workspace residual state")
            workspace_safe = False

        if configuration == "workspace" and workspace_safe:
            try:
                self._verify_devtool_config()
            except (SdkIterationError, KeyboardInterrupt) as exc:
                record_failure("devtool configuration", exc)
                workspace_safe = False

        can_use_devtool = configuration == "workspace" and workspace_safe
        if not can_use_devtool:
            if configuration == "unknown" and (
                self.workspace.exists()
                or self.workspace_added
                or self.recipe_modified
                or self.deployment_attempted
            ):
                record_failure("configuration authority")
            try:
                configure_authoritative_build(
                    self.repo,
                    self.build_dir,
                    self.manifest,
                )
                self.workspace_added = False
                configuration = "base"
            except (Exception, KeyboardInterrupt) as exc:
                record_failure("authoritative composition restoration", exc)

        if (
            self.deployment_attempted
            and self.active_boot is not None
            and self.active_boot.port is not None
        ):
            undeployed = False
            if can_use_devtool and (workspace_active or self.recipe_modified):
                try:
                    result = self.runner.run(
                        self._deploy_arguments(
                            "undeploy-target", self.active_boot.port
                        ),
                        check=False,
                        timeout=CLEANUP_TIMEOUT_SECONDS,
                        environment=self._deploy_environment(),
                    )
                    undeployed = result.returncode == 0
                except (Exception, KeyboardInterrupt) as exc:
                    if isinstance(exc, SdkCancellation):
                        cancellation = cancellation or exc
                    elif isinstance(exc, KeyboardInterrupt):
                        cancellation = cancellation or SdkCancellation(signal.SIGINT)
                    undeployed = False
            if not undeployed:
                try:
                    self.active_boot.remote(["rm", "-f", self.guest_binary])
                    self.active_boot.remote(["test", "!", "-e", self.guest_binary])
                    undeployed = True
                except (Exception, KeyboardInterrupt) as exc:
                    record_failure("target undeploy", exc)
            self.deployed = False
            self.deployment_attempted = False

        if self.active_boot is not None:
            try:
                self.active_boot.stop()
            except (Exception, KeyboardInterrupt) as exc:
                record_failure("runqemu stop", exc)
            else:
                self.active_boot = None

        if can_use_devtool:
            try:
                status_before = self.runner.output(["devtool", "-q", "status"])
                status_recipes = {
                    line.split(":", 1)[0]
                    for line in status_before.splitlines()
                    if line.strip()
                }
                if status_recipes == {self.recipe}:
                    self.recipe_modified = True
                elif status_recipes:
                    record_failure("unexpected workspace recipes")
            except (Exception, KeyboardInterrupt) as exc:
                record_failure("devtool state discovery", exc)
            if self.recipe_modified:
                try:
                    self._verify_workspace(resting=False, require_active=True)
                except SdkIterationError as exc:
                    record_failure("workspace residual state", exc)
                    can_use_devtool = False
            if self.recipe_modified and can_use_devtool:
                try:
                    result = self.runner.run(
                        ["devtool", "reset", "--no-clean", self.recipe],
                        check=False,
                        timeout=CLEANUP_TIMEOUT_SECONDS,
                    )
                    if result.returncode != 0:
                        record_failure("devtool reset")
                    else:
                        self.recipe_modified = False
                except (Exception, KeyboardInterrupt) as exc:
                    record_failure("devtool reset", exc)
            if can_use_devtool:
                try:
                    if self.runner.output(["devtool", "-q", "status"]):
                        record_failure("devtool status")
                except (Exception, KeyboardInterrupt) as exc:
                    record_failure("devtool status", exc)
                try:
                    self._verify_workspace(resting=True)
                except SdkIterationError as exc:
                    record_failure("workspace residual state", exc)
            if can_use_devtool:
                try:
                    result = self.runner.run(
                        ["bitbake-layers", "remove-layer", str(self.workspace)],
                        check=False,
                        timeout=CLEANUP_TIMEOUT_SECONDS,
                    )
                    if result.returncode != 0:
                        record_failure("workspace layer removal")
                except (Exception, KeyboardInterrupt) as exc:
                    record_failure("workspace layer removal", exc)

        if self.active_boot is not None:
            try:
                self.active_boot.stop()
            except (Exception, KeyboardInterrupt) as exc:
                record_failure("runqemu stop", exc)
            else:
                self.active_boot = None

        try:
            configure_authoritative_build(
                self.repo,
                self.build_dir,
                self.manifest,
            )
            self.workspace_added = False
            self._verify_closed_configuration("base")
            composition_restored = True
        except (Exception, KeyboardInterrupt) as exc:
            record_failure("authoritative composition restoration", exc)

        if self.workspace.exists() or self.workspace.is_symlink():
            try:
                self._verify_workspace(resting=True)
            except SdkIterationError:
                if "workspace residual state" not in failures:
                    record_failure("workspace residual state")
        if composition_restored:
            try:
                self._composition_preflight()
            except (Exception, KeyboardInterrupt) as exc:
                record_failure("cleanup verification", exc)
        if cancellation is not None:
            if failures:
                cancellation.add_note(
                    "SDK cleanup issues: " + ", ".join(dict.fromkeys(failures))
                )
            raise cancellation
        if failures:
            raise SdkIterationError(
                "SDK cleanup failed: " + ", ".join(dict.fromkeys(failures))
            )

    def _boot(self) -> BootSession:
        boot = self.boot_factory(self.runner, self.machine, self.image)
        self.active_boot = boot
        boot.start()
        return boot

    def execute(self) -> Path:
        completed = False
        tooling_ready = False
        transport_directory: tempfile.TemporaryDirectory[str] | None = None
        prepared_digest: str | None = None
        artifact_digest: str | None = None
        evidence: dict[str, Any] | None = None
        try:
            self.preflight_repository()
            self._preflight_retained_outputs()
            self.runner.locked_python_path = verify_tooling(self.repo)
            ssh_executable = resolve_host_executable("ssh")
            scp_executable = resolve_host_executable("scp")
            self.runner.ssh_executable = str(ssh_executable)
            (
                transport_directory,
                self.ssh_wrapper,
                self.scp_wrapper,
            ) = create_transport_wrappers(
                ssh_executable,
                scp_executable,
            )
            tooling_ready = True
            if self.workspace.exists() or self.workspace.is_symlink():
                self._cleanup_development_state()
            else:
                configure_authoritative_build(
                    self.repo,
                    self.build_dir,
                    self.manifest,
                )
            self._verify_closed_configuration("base")
            self._composition_preflight()
            self.runner.run(
                [
                    "bash",
                    str(self.repo / "scripts/qemu_security_preflight.sh"),
                    str(self.repo),
                    self.lab_id,
                    self.image,
                ]
            )
            self.runner.run(["bitbake", self.image])
            prepared_digest = self._prepare_workspace()
            self.runner.run(
                ["devtool", "modify", "-n", self.recipe, str(self.source_dir)]
            )
            self.recipe_modified = True
            self.runner.run(["devtool", "build", self.recipe])
            artifact_digest = self._built_artifact_digest()
            self.runner.run(
                [
                    "devtool", "ide-sdk", "--mode", "modified", "--ide", "none",
                    self.recipe, self.image,
                ]
            )
            self._retain_ide_output()

            boot = self._boot()
            boot.remote(["test", "!", "-e", self.guest_binary])
            if boot.remote(["uname", "-m"]) != self.identity["architecture"]:
                raise SdkIterationError("guest architecture does not match the selected lab")
            assert boot.port is not None
            self.deployment_attempted = True
            self.runner.run(
                self._deploy_arguments("deploy-target", boot.port),
                environment=self._deploy_environment(),
            )
            self.deployed = True
            self._verify_remote_artifact(boot, artifact_digest)
            if boot.remote([self.guest_binary]) != WORKSPACE_TEXT:
                raise SdkIterationError("deployed sample output is not recognized")
            self.runner.run(
                self._deploy_arguments("undeploy-target", boot.port),
                environment=self._deploy_environment(),
            )
            self.deployed = False
            self.deployment_attempted = False
            boot.remote(["test", "!", "-e", self.guest_binary])
            boot.stop()
            self.active_boot = None

            self._cleanup_development_state()
            if not self.source_file.is_file() or self.source_file.is_symlink():
                raise SdkIterationError("learner source was not retained after reset")
            retained_digest = hashlib.sha256(self.source_file.read_bytes()).hexdigest()
            if retained_digest != prepared_digest:
                raise SdkIterationError("retained learner source changed during reset")

            cold_boot = self._boot()
            cold_boot.remote(["test", "!", "-e", self.guest_binary])
            cold_boot.stop()
            self.active_boot = None

            evidence = build_evidence(
                self.repo,
                self.lab_id,
                retained_digest,
                artifact_digest,
            )
            revision, _ = project_state(self.repo)
            validate_evidence(
                evidence,
                require_pass=True,
                expected_revision=revision,
                current_repo=self.repo,
            )
            completed = True
        finally:
            active_error = sys.exception()
            finalization = DeferredCancellation(raise_on_exit=False)
            with finalization:
                cleanup_error: Exception | None = None
                if tooling_ready:
                    try:
                        self._cleanup_development_state()
                    except Exception as exc:  # every mutation path reaches restoration
                        cleanup_error = exc
                self.ssh_wrapper = None
                self.scp_wrapper = None
                if transport_directory is not None:
                    try:
                        transport_directory.cleanup()
                    except OSError:
                        if cleanup_error is None:
                            cleanup_error = SdkIterationError(
                                "temporary SSH wrapper cleanup failed"
                            )
                if cleanup_error is not None:
                    completed = False
                if not completed:
                    clear_evidence(self.output)
                if cleanup_error is not None:
                    if active_error is not None:
                        active_error.add_note(str(cleanup_error))
                    else:
                        raise cleanup_error
            if finalization.signum is not None:
                cancellation = SdkCancellation(finalization.signum)
                if active_error is not None:
                    active_error.add_note(str(cancellation))
                else:
                    raise cancellation
        if evidence is None or not completed:
            raise SdkIterationError("SDK evidence was not ready for publication")
        publication = DeferredCancellation(raise_on_exit=False)
        with publication:
            try:
                write_evidence(self.output, evidence)
                revision, _ = project_state(self.repo)
                validate_evidence(
                    read_evidence(self.output),
                    require_pass=True,
                    expected_revision=revision,
                    current_repo=self.repo,
                )
            except BaseException:
                clear_evidence(self.output)
                raise
            self.committed = True
        return self.output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="repository root")
    parser.add_argument("--lab", required=True, help="catalog-selected lab id")
    parser.add_argument("--build-dir", required=True, help="selected development build root")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("preflight-path", help="verify the selected build path before setup")
    subparsers.add_parser("run", help="execute the closed direct-eSDK lifecycle")
    args = parser.parse_args()
    previous_handlers: dict[int, Any] = {}
    try:
        if sys.platform != "linux":
            raise SdkIterationError("SDK iteration requires a native Linux host")
        for command in ("bash", "ssh", "scp"):
            if shutil.which(command) is None:
                raise SdkIterationError("a required SDK iteration command is unavailable")
        iteration = DirectSdkIteration(
            Path(args.repo), args.lab, Path(args.build_dir)
        )
        if args.command == "preflight-path":
            iteration.preflight_repository()
            iteration._preflight_retained_outputs()
            print("sdk-iteration: PASS: repository and build path")
            return 0
        def cancel(signum: int, _frame: Any) -> None:
            if iteration.committed:
                return
            raise SdkCancellation(signum)

        for name in ("SIGTERM", "SIGHUP", "SIGINT"):
            signum = getattr(signal, name, None)
            if signum is not None:
                previous_handlers[signum] = signal.signal(signum, cancel)
        output = iteration.execute()
        print(f"sdk-iteration: PASS: {output}")
        return 0
    except SdkCancellation as exc:
        print(f"sdk-iteration: FAIL: {exc}", file=sys.stderr)
        return 128 + exc.signum
    except KeyboardInterrupt:
        print("sdk-iteration: FAIL: SDK iteration interrupted", file=sys.stderr)
        return 130
    except LabError as exc:
        print(f"sdk-iteration: FAIL: {exc}", file=sys.stderr)
        return 2
    except (
        ConfigurationError,
        SdkIterationError,
        SdkEvidenceError,
        SdkToolingError,
        LockError,
        OSError,
        subprocess.SubprocessError,
    ) as exc:
        print(f"sdk-iteration: FAIL: {exc}", file=sys.stderr)
        return 1
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)


if __name__ == "__main__":
    raise SystemExit(main())
