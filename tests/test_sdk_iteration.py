# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import importlib.util
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "sdk_iteration_contract", ROOT / "scripts/sdk_iteration.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class FakeRunner:
    def __init__(self, root: Path, manifest: dict, *, fail: tuple[str, ...] | None = None):
        self.root = root
        self.manifest = manifest
        self.fail = fail
        self.calls: list[tuple[str, ...]] = []
        self.environments: list[tuple[tuple[str, ...], dict[str, str] | None]] = []
        self._workspace_in_layers = False
        self.modified_recipe = False
        self.leave_workspace_residual = False
        self.bbpath_override: str | None = None
        self.locked_python_path: Path | None = None
        self.workspace_in_layers = False

    @property
    def workspace_in_layers(self) -> bool:
        build_dir = self.root / self.manifest["development"]["build_dir"]
        path = build_dir / "conf/bblayers.conf"
        if not path.is_file():
            return False
        return path.read_text(encoding="utf-8") == MODULE.render_sdk_bblayers(
            self.root,
            self.manifest,
            workspace=build_dir / "workspace",
        )

    @workspace_in_layers.setter
    def workspace_in_layers(self, value: bool) -> None:
        self._workspace_in_layers = value
        build_dir = self.root / self.manifest["development"]["build_dir"]
        if (build_dir / "conf").is_dir():
            MODULE.configure_authoritative_build(
                self.root,
                build_dir,
                self.manifest,
                workspace=(build_dir / "workspace") if value else None,
            )

    def run(
        self,
        arguments,
        *,
        capture=False,
        check=True,
        timeout=MODULE.COMMAND_TIMEOUT_SECONDS,
        environment=None,
    ):
        del capture, timeout
        command = tuple(str(item) for item in arguments)
        self.calls.append(command)
        self.environments.append((command, environment))
        returncode = 1 if self.fail and command[: len(self.fail)] == self.fail else 0
        if returncode and check:
            raise MODULE.SdkIterationError("a required command failed")
        if command[:2] == ("devtool", "create-workspace") and returncode == 0:
            workspace = Path(command[2])
            if not (workspace / "conf/layer.conf").exists():
                (workspace / "conf").mkdir(parents=True)
                (workspace / "conf/layer.conf").write_bytes(
                    b"# generated workspace metadata\n" + MODULE.WORKSPACE_LAYER_CONF
                )
                (workspace / "README").write_text(
                    "Generated development workspace.\n",
                    encoding="utf-8",
                    newline="\n",
                )
            devtool_config = (
                self.root
                / self.manifest["development"]["build_dir"]
                / "conf/devtool.conf"
            )
            devtool_config.parent.mkdir(parents=True, exist_ok=True)
            devtool_config.write_text(
                f"[General]\nworkspace_path = {workspace}\n",
                encoding="utf-8",
                newline="\n",
            )
            self.workspace_in_layers = True
        if command[:2] == ("bitbake-layers", "add-layer") and returncode == 0:
            self.workspace_in_layers = True
        if command[:3] == ("devtool", "modify", "-n") and returncode == 0:
            self.modified_recipe = True
            workspace = self.root / self.manifest["development"]["build_dir"] / "workspace"
            source_dir = (
                self.root
                / self.manifest["development"]["build_dir"]
                / self.manifest["development"]["source_dir"]
            )
            (workspace / "appends").mkdir(exist_ok=True)
            append_path = (
                workspace
                / "appends"
                / MODULE.workspace_append_name("qemu-edu-sdk-sample")
            )
            append_path.write_bytes(
                b"# generated recipe metadata\n"
                + MODULE.expected_workspace_append(
                    "qemu-edu-sdk-sample",
                    source_dir,
                )
            )
            append_digest = MODULE.hashlib.md5(
                append_path.read_bytes(),
                usedforsecurity=False,
            ).hexdigest()
            (workspace / ".devtool_md5").write_text(
                "qemu-edu-sdk-sample|appends/"
                f"{MODULE.workspace_append_name('qemu-edu-sdk-sample')}|"
                f"{append_digest}\n",
                encoding="utf-8",
                newline="\n",
            )
        if command[:2] == ("devtool", "build") and returncode == 0:
            artifact = (
                self.root
                / self.manifest["development"]["build_dir"]
                / "tmp/work/qemu-edu-sdk-sample/1.0-r0/image/usr/bin/"
                "qemu-edu-sdk-sample"
            )
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_bytes(b"closed SDK artifact\n")
        if command[:2] == ("devtool", "ide-sdk") and returncode == 0:
            ide_output = (
                self.root
                / self.manifest["development"]["build_dir"]
                / "workspace/ide-sdk/qemu-edu-sdk-sample/scripts"
            )
            ide_output.mkdir(parents=True)
            (ide_output / "generated-helper").write_text(
                "generated IDE-neutral helper\n",
                encoding="utf-8",
                newline="\n",
            )
        if command[:2] == ("devtool", "reset") and returncode == 0:
            self.modified_recipe = False
            workspace = self.root / self.manifest["development"]["build_dir"] / "workspace"
            if not self.leave_workspace_residual:
                append = (
                    workspace
                    / "appends"
                    / MODULE.workspace_append_name("qemu-edu-sdk-sample")
                )
                if append.exists():
                    append.unlink()
                (workspace / ".devtool_md5").write_bytes(b"")
        if command[:2] == ("bitbake-layers", "remove-layer") and returncode == 0:
            self.workspace_in_layers = False
        return subprocess.CompletedProcess(command, returncode, "", "")

    def output(self, arguments, *, timeout=120):
        del timeout
        command = tuple(str(item) for item in arguments)
        self.calls.append(command)
        if command == ("bitbake-getvar", "--value", "DISTRO"):
            return self.manifest["build"]["distro"]
        if command == ("bitbake-getvar", "--value", "MACHINE"):
            return self.manifest["build"]["machine"]
        if command == ("bitbake-getvar", "--value", "BBLAYERS"):
            layers = [str(self.root / item) for item in self.manifest["build"]["layers"]]
            if self.workspace_in_layers:
                layers.append(str(self.root / self.manifest["development"]["build_dir"] / "workspace"))
            return " ".join(layers)
        if command == ("bitbake-getvar", "--value", "BBPATH"):
            if self.bbpath_override is not None:
                return self.bbpath_override
            entries = [
                str(MODULE.sdk_configuration_root(self.root, self.manifest)),
                *(str(self.root / item) for item in self.manifest["build"]["layers"]),
            ]
            return os.pathsep.join(entries)
        if command == ("devtool", "-q", "status"):
            if self.modified_recipe:
                return "qemu-edu-sdk-sample:/tmp/source"
            return ""
        if command == (
            "bitbake-getvar", "--value", "--recipe", "qemu-edu-sdk-sample", "D"
        ):
            return str(
                self.root
                / self.manifest["development"]["build_dir"]
                / "tmp/work/qemu-edu-sdk-sample/1.0-r0/image"
            )
        if command == (
            "bitbake-getvar", "--value", "--recipe", "qemu-edu-sdk-sample", "bindir"
        ):
            return "/usr/bin"
        raise AssertionError(f"unexpected captured command: {command}")


class FakeBoot:
    fail_execution = False
    bad_artifact_digest = False
    instances: list["FakeBoot"] = []

    def __init__(self, runner, machine, image):
        self.runner = runner
        self.machine = machine
        self.image = image
        self.port = None
        self.stopped = False
        self.remote_calls: list[tuple[str, ...]] = []
        self.__class__.instances.append(self)

    def start(self):
        self.port = 2222

    def remote(self, arguments):
        command = tuple(arguments)
        self.remote_calls.append(command)
        if command == ("uname", "-m"):
            return "x86_64"
        if command == ("/usr/bin/qemu-edu-sdk-sample",):
            if self.fail_execution:
                raise MODULE.SdkIterationError("deployed sample failed")
            return MODULE.WORKSPACE_TEXT
        if command == ("sha256sum", "/usr/bin/qemu-edu-sdk-sample"):
            digest = (
                "0" * 64
                if self.bad_artifact_digest
                else MODULE.hashlib.sha256(b"closed SDK artifact\n").hexdigest()
            )
            return f"{digest}  /usr/bin/qemu-edu-sdk-sample"
        if command == ("rm", "-f", "/usr/bin/qemu-edu-sdk-sample"):
            return ""
        if command == ("test", "!", "-e", "/usr/bin/qemu-edu-sdk-sample"):
            return ""
        raise AssertionError(f"unexpected remote command: {command}")

    def stop(self):
        self.stopped = True
        self.port = None


class FailingStartBoot(FakeBoot):
    def start(self):
        self.port = 2222
        raise MODULE.SdkIterationError("runqemu startup failed")


def manifest() -> dict:
    return {
        "build": {
            "distro": "poky",
            "machine": "qemu-edu-x86-64",
            "targets": ["qemu-edu-image"],
            "layers": ["layers/core", "meta-qemu-edu"],
        },
        "development": {
            "profile": "direct-esdk-devtool-v1",
            "build_dir": "build-sdk-pci-x86-64",
            "recipe": "qemu-edu-sdk-sample",
            "source_dir": "learner-source/qemu-edu-sdk-sample",
            "ide": "none",
            "guest_binary": "/usr/bin/qemu-edu-sdk-sample",
            "evidence_filename": "qemu-edu-sdk-evidence-v1.json",
            "evidence_schema_version": 1,
        },
    }


class SdkIterationTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeBoot.instances = []
        FakeBoot.fail_execution = False
        FakeBoot.bad_artifact_digest = False

    def test_runqemu_port_parser_is_loopback_guest_ssh_only(self) -> None:
        self.assertEqual(
            2222,
            MODULE.parse_ssh_port(
                "runqemu - INFO - Port forward: "
                "hostfwd=tcp:127.0.0.1:2222-:22,hostfwd=tcp:127.0.0.1:2323-:23"
            ),
        )
        for invalid in (
            "hostfwd=tcp:0.0.0.0:2222-:22",
            "hostfwd=tcp:127.0.0.1:2222-:23",
        ):
            with self.subTest(invalid=invalid):
                self.assertIsNone(MODULE.parse_ssh_port(invalid))
        for invalid_port in (
            "hostfwd=tcp:127.0.0.1:22-:22",
            "hostfwd=tcp:127.0.0.1:70000-:22",
        ):
            with self.subTest(invalid_port=invalid_port):
                with self.assertRaisesRegex(MODULE.SdkIterationError, "invalid"):
                    MODULE.parse_ssh_port(invalid_port)
        with self.assertRaisesRegex(MODULE.SdkIterationError, "conflicting"):
            MODULE.parse_ssh_port(
                "hostfwd=tcp:127.0.0.1:2222-:22 "
                "hostfwd=tcp:127.0.0.1:2223-:22"
            )

    def test_ssh_arguments_are_fixed_batch_loopback_options(self) -> None:
        arguments = MODULE.ssh_arguments(2222, ["uname", "-m"])
        self.assertEqual("ssh", arguments[0])
        self.assertEqual(MODULE.os.devnull, arguments[arguments.index("-F") + 1])
        self.assertIn("BatchMode=yes", arguments)
        self.assertIn("StrictHostKeyChecking=no", arguments)
        self.assertIn("UserKnownHostsFile=/dev/null", arguments)
        self.assertIn("Hostname=127.0.0.1", arguments)
        self.assertIn("ProxyCommand=none", arguments)
        self.assertIn("ProxyJump=none", arguments)
        self.assertIn("IdentitiesOnly=yes", arguments)
        self.assertIn("IdentityAgent=none", arguments)
        self.assertIn("IdentityFile=none", arguments)
        self.assertIn("ForwardAgent=no", arguments)
        self.assertIn("ClearAllForwardings=yes", arguments)
        self.assertEqual(["root@127.0.0.1", "uname", "-m"], arguments[-3:])
        with self.assertRaises(MODULE.SdkIterationError):
            MODULE.ssh_arguments(22, ["true"])

    def test_devtool_ssh_wrapper_uses_the_same_isolated_transport(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "ssh-native"
            executable.write_text("#!/bin/sh\n", encoding="utf-8", newline="\n")
            executable.chmod(0o700)
            directory, wrapper, scp_wrapper = MODULE.create_transport_wrappers(
                executable,
                executable,
            )
            try:
                payload = wrapper.read_text(encoding="utf-8")
                self.assertIn("-F", payload)
                self.assertIn(MODULE.os.devnull, payload)
                self.assertIn("Hostname=127.0.0.1", payload)
                self.assertIn("ProxyCommand=none", payload)
                self.assertIn("ProxyJump=none", payload)
                self.assertIn("IdentityAgent=none", payload)
                self.assertIn("ForwardAgent=no", payload)
                self.assertIn('"$@"', payload)
                self.assertIn(str(executable), scp_wrapper.read_text(encoding="utf-8"))
            finally:
                directory.cleanup()
            self.assertFalse(wrapper.exists())
            self.assertFalse(scp_wrapper.exists())

    @unittest.skipUnless(os.name == "posix", "SSH wrapper execution requires POSIX")
    def test_devtool_ssh_wrapper_executes_fixed_options_before_caller_args(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "ssh-native"
            executable.write_text(
                "#!/bin/sh\nprintf '%s\\n' \"$@\"\n",
                encoding="utf-8",
                newline="\n",
            )
            executable.chmod(0o700)
            directory, wrapper, scp_wrapper = MODULE.create_transport_wrappers(
                executable,
                executable,
            )
            try:
                result = subprocess.run(
                    [str(wrapper), "-p", "2222", "root@127.0.0.1"],
                    capture_output=True,
                    check=True,
                    text=True,
                )
                arguments = result.stdout.splitlines()
                self.assertEqual("-F", arguments[0])
                self.assertEqual(MODULE.os.devnull, arguments[1])
                self.assertLess(
                    arguments.index("Hostname=127.0.0.1"),
                    arguments.index("-p"),
                )
                self.assertIn("IdentityAgent=none", arguments)
                self.assertEqual("root@127.0.0.1", arguments[-1])
                scp_result = subprocess.run(
                    [str(scp_wrapper), "-S", str(wrapper), "source", "target"],
                    capture_output=True,
                    check=True,
                    text=True,
                )
                self.assertEqual(
                    ["-S", str(wrapper), "source", "target"],
                    scp_result.stdout.splitlines(),
                )
            finally:
                directory.cleanup()

    def test_command_capture_is_bounded_before_return(self) -> None:
        runner = MODULE.CommandRunner()
        with self.assertRaisesRegex(MODULE.SdkIterationError, "bounded output"):
            runner.run(
                [
                    sys.executable,
                    "-c",
                    f"print('x' * {MODULE.MAX_CAPTURE_BYTES + 1})",
                ],
                capture=True,
                timeout=10,
            )

    def test_command_failure_reports_only_sanitized_name_and_status(self) -> None:
        class FailedProcess:
            stdout = None
            returncode = 7

            def poll(self):
                return self.returncode

        runner = MODULE.CommandRunner()
        with (
            patch.object(MODULE.subprocess, "Popen", return_value=FailedProcess()),
            self.assertRaises(MODULE.SdkIterationError) as raised,
        ):
            runner.run([str(Path("C:/private/build/bitbake-getvar")), "secret-value"])
        self.assertEqual(
            "bitbake-getvar failed with exit status 7",
            str(raised.exception),
        )
        self.assertNotIn("private", str(raised.exception))
        self.assertNotIn("secret-value", str(raised.exception))

    def test_command_runner_reaps_child_on_base_exception(self) -> None:
        class InterruptedProcess:
            stdout = None
            returncode = None

            def __init__(self) -> None:
                self.killed = False

            def poll(self):
                return self.returncode

            def kill(self) -> None:
                self.killed = True
                self.returncode = -9

            def wait(self, timeout=None):
                del timeout
                self.returncode = -9
                return self.returncode

        process = InterruptedProcess()
        runner = MODULE.CommandRunner()
        with (
            patch.object(MODULE.subprocess, "Popen", return_value=process),
            patch.object(MODULE.os, "name", "nt"),
            patch.object(MODULE.time, "sleep", side_effect=KeyboardInterrupt),
            self.assertRaises(KeyboardInterrupt),
        ):
            runner.run(["fixed-command"])
        self.assertTrue(process.killed)

    def test_command_runner_kills_group_after_its_leader_has_exited(self) -> None:
        class ExitedLeader:
            pid = 4242

            def __init__(self) -> None:
                self.waited = False

            def poll(self):
                return 0

            def wait(self, timeout=None):
                del timeout
                self.waited = True
                return 0

        process = ExitedLeader()
        group_alive = True
        signals: list[int] = []

        def group_exists(_group_id: int) -> bool:
            return group_alive

        def kill_group(_group_id: int, signum: int) -> None:
            nonlocal group_alive
            signals.append(signum)
            if signum == 9:
                group_alive = False

        with (
            patch.object(MODULE.os, "name", "posix"),
            patch.object(MODULE.signal, "SIGKILL", 9, create=True),
            patch.object(MODULE, "STOP_TIMEOUT_SECONDS", 0),
            patch.object(MODULE, "_process_group_exists", side_effect=group_exists),
            patch.object(MODULE.os, "killpg", side_effect=kill_group, create=True),
        ):
            MODULE.CommandRunner._terminate(process)
        self.assertEqual([MODULE.signal.SIGTERM, 9], signals)
        self.assertTrue(process.waited)

    def test_deferred_cancellation_is_raised_after_critical_section(self) -> None:
        deferred = MODULE.DeferredCancellation()
        with self.assertRaises(MODULE.SdkCancellation):
            with deferred:
                deferred._record(MODULE.signal.SIGTERM, None)

    def test_boot_stop_retains_process_handle_until_group_stop_completes(self) -> None:
        class Process:
            stdout = None

        with tempfile.TemporaryDirectory() as temporary:
            runner = FakeRunner(Path(temporary), manifest())
        boot = MODULE.BootSession(runner, "machine", "image")
        process = Process()
        boot.process = process
        boot.port = 2222
        with (
            patch.object(MODULE.os, "name", "posix"),
            patch.object(
                MODULE,
                "_terminate_process_group",
                side_effect=KeyboardInterrupt,
            ),
            self.assertRaises(KeyboardInterrupt),
        ):
            boot.stop()
        self.assertIs(process, boot.process)
        self.assertEqual(2222, boot.port)
        with (
            patch.object(MODULE.os, "name", "posix"),
            patch.object(MODULE, "_terminate_process_group"),
        ):
            boot.stop()
        self.assertIsNone(boot.process)
        self.assertIsNone(boot.port)

    def test_child_environment_replaces_module_and_shell_startup_injection(self) -> None:
        locked = ROOT / "layers/bitbake/lib"
        injected = {
            key: "untrusted"
            for key in MODULE.UNSAFE_CHILD_ENVIRONMENT
        }
        with patch.dict(MODULE.os.environ, injected, clear=False):
            environment = MODULE.command_environment(
                {"TMPDIR": "/tmp/qemu-edu-sdk"},
                locked_python_path=locked,
            )
        for key in MODULE.UNSAFE_CHILD_ENVIRONMENT - {"PYTHONPATH", "PYTHONNOUSERSITE"}:
            self.assertNotIn(key, environment)
        self.assertEqual(str(locked), environment["PYTHONPATH"])
        self.assertEqual("1", environment["PYTHONNOUSERSITE"])
        self.assertEqual("1", environment["PYTHONDONTWRITEBYTECODE"])
        self.assertEqual("/tmp/qemu-edu-sdk", environment["TMPDIR"])

    def iteration_fixture(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        sample = root / MODULE.SOURCE_TEMPLATE
        sample.parent.mkdir(parents=True)
        sample.write_text(
            '/* SPDX-License-' 'Identifier: MIT */\n'
            '#include <stdio.h>\n'
            'int main(void) { puts("qemu-edu-sdk-sample baseline"); return 0; }\n',
            encoding="utf-8",
            newline="\n",
        )
        selected = manifest()
        locked_python_path = root / "layers/bitbake/lib"
        locked_python_path.mkdir(parents=True)
        (root / selected["development"]["build_dir"] / "conf").mkdir(parents=True)
        runner = FakeRunner(root, selected)
        output = root / "build-sdk-pci-x86-64/evidence/qemu-edu-sdk-evidence-v1.json"
        patches = (
            patch.object(
                MODULE,
                "selected_contract",
                return_value=(
                    selected,
                    "pci-x86-64",
                    "a" * 64,
                    "b" * 64,
                    {"machine": "qemu-edu-x86-64", "architecture": "x86_64"},
                ),
            ),
            patch.object(MODULE, "evidence_path", return_value=output),
            patch.object(MODULE, "source_authority", return_value=({}, "c" * 64, "d" * 40)),
            patch.object(MODULE, "project_state", return_value=("e" * 40, False)),
            patch.object(MODULE, "build_evidence", return_value={"result": "passed"}),
            patch.object(
                MODULE,
                "write_evidence",
                side_effect=lambda path, _document: (
                    path.parent.mkdir(parents=True, exist_ok=True),
                    path.write_text("{}\n", encoding="utf-8"),
                ),
            ),
            patch.object(MODULE, "read_evidence", return_value={}),
            patch.object(MODULE, "validate_evidence"),
            patch.object(
                MODULE,
                "verify_tooling",
                return_value=locked_python_path,
            ),
        )
        return root, selected, runner, output, patches

    @staticmethod
    def write_resting_workspace(workspace: Path) -> None:
        (workspace / "conf").mkdir(parents=True)
        (workspace / "conf/layer.conf").write_bytes(
            b"# generated workspace metadata\n" + MODULE.WORKSPACE_LAYER_CONF
        )
        (workspace / "README").write_text(
            "Generated development workspace.\n",
            encoding="utf-8",
            newline="\n",
        )
        devtool_config = workspace.parent / "conf/devtool.conf"
        devtool_config.parent.mkdir(parents=True, exist_ok=True)
        devtool_config.write_text(
            f"[General]\nworkspace_path = {workspace}\n",
            encoding="utf-8",
            newline="\n",
        )

    @staticmethod
    def write_active_workspace(workspace: Path, source_dir: Path) -> None:
        SdkIterationTests.write_resting_workspace(workspace)
        appends = workspace / "appends"
        appends.mkdir()
        append = appends / MODULE.workspace_append_name("qemu-edu-sdk-sample")
        append.write_bytes(
            b"# generated recipe metadata\n"
            + MODULE.expected_workspace_append(
                "qemu-edu-sdk-sample",
                source_dir,
            )
        )
        digest = MODULE.hashlib.md5(
            append.read_bytes(),
            usedforsecurity=False,
        ).hexdigest()
        (workspace / ".devtool_md5").write_text(
            "qemu-edu-sdk-sample|appends/"
            f"{MODULE.workspace_append_name('qemu-edu-sdk-sample')}|"
            f"{digest}\n",
            encoding="utf-8",
            newline="\n",
        )

    def test_complete_lifecycle_uses_exact_devtool_commands_and_two_boots(self) -> None:
        root, selected, runner, output, patches = self.iteration_fixture()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8]:
            result = MODULE.DirectSdkIteration(
                root,
                "pci-x86-64",
                root / selected["development"]["build_dir"],
                runner=runner,
                boot_factory=FakeBoot,
            ).execute()
        self.assertEqual(output, result)
        self.assertEqual(root / "layers/bitbake/lib", runner.locked_python_path)
        self.assertTrue(output.is_file())
        self.assertEqual(2, len(FakeBoot.instances))
        self.assertTrue(all(item.stopped for item in FakeBoot.instances))
        calls = runner.calls
        expected_commands = (
            ("devtool", "modify", "-n", "qemu-edu-sdk-sample"),
            ("devtool", "build", "qemu-edu-sdk-sample"),
            (
                "devtool", "ide-sdk", "--mode", "modified", "--ide", "none",
                "qemu-edu-sdk-sample", "qemu-edu-image",
            ),
            ("devtool", "deploy-target", "-c", "-P", "2222"),
            ("devtool", "undeploy-target", "-c", "-P", "2222"),
            ("devtool", "reset", "--no-clean", "qemu-edu-sdk-sample"),
        )
        for prefix in expected_commands:
            self.assertTrue(
                any(command[: len(prefix)] == prefix for command in calls),
                prefix,
            )
        self.assertGreaterEqual(calls.count(("devtool", "-q", "status")), 3)
        self.assertNotIn(("devtool", "status"), calls)
        deployment_calls = [
            command
            for command in calls
            if command[:2]
            in {
                ("devtool", "deploy-target"),
                ("devtool", "undeploy-target"),
            }
        ]
        self.assertGreaterEqual(len(deployment_calls), 2)
        for command in deployment_calls:
            self.assertIn("-e", command)
            wrapper = Path(command[command.index("-e") + 1])
            self.assertFalse(wrapper.exists())
            if command[1] == "deploy-target":
                self.assertIn("--no-strip", command)
            else:
                self.assertNotIn("--no-strip", command)
            environment = next(
                value
                for recorded, value in runner.environments
                if recorded == command and value is not None
            )
            assert environment is not None
            self.assertEqual(str(wrapper.parent), environment["TMPDIR"])
            self.assertEqual(str(wrapper.parent), environment["TMP"])
            self.assertEqual(str(wrapper.parent), environment["TEMP"])
            self.assertEqual(str(wrapper.parent), environment["PATH"].split(os.pathsep)[0])
        source = (
            root
            / "build-sdk-pci-x86-64/learner-source/"
            "qemu-edu-sdk-sample/qemu-edu-sdk-sample.c"
        ).read_text(encoding="utf-8")
        self.assertIn(MODULE.WORKSPACE_TEXT, source)
        self.assertNotIn(MODULE.BASELINE_TEXT, source)
        self.assertFalse((root / "build-sdk-pci-x86-64/workspace/sources").exists())
        self.assertTrue(
            (root / "build-sdk-pci-x86-64/learner-ide-sdk/"
             "qemu-edu-sdk-sample/scripts/generated-helper").is_file()
        )
        self.assertFalse((root / "build-sdk-pci-x86-64/workspace/ide-sdk").exists())
        config = (
            root
            / selected["development"]["build_dir"]
            / "conf/devtool.conf"
        ).read_text(encoding="utf-8")
        self.assertEqual(
            "[General]\n"
            f"workspace_path = {root / selected['development']['build_dir'] / 'workspace'}\n",
            config,
        )

    def test_existing_devtool_config_must_bind_only_the_declared_workspace(self) -> None:
        root, selected, runner, _output, patches = self.iteration_fixture()
        workspace = root / selected["development"]["build_dir"] / "workspace"
        self.write_resting_workspace(workspace)
        devtool_config = workspace.parent / "conf/devtool.conf"
        devtool_config.parent.mkdir(parents=True, exist_ok=True)
        devtool_config.write_text(
            "[General]\nworkspace_path = /tmp/other-workspace\n"
            "[Deploy]\nstrip = true\n",
            encoding="utf-8",
            newline="\n",
        )
        with patches[0], patches[1]:
            iteration = MODULE.DirectSdkIteration(
                root,
                "pci-x86-64",
                workspace.parent,
                runner=runner,
                boot_factory=FakeBoot,
            )
            with self.assertRaisesRegex(
                MODULE.SdkIterationError, "not authoritative"
            ):
                iteration._prepare_workspace()
        self.assertFalse(runner.calls)

    def test_existing_workspace_refuses_plugin_override_before_devtool(self) -> None:
        root, selected, runner, _output, patches = self.iteration_fixture()
        workspace = root / selected["development"]["build_dir"] / "workspace"
        self.write_resting_workspace(workspace)
        override = workspace / "lib/devtool/deploy.py"
        override.parent.mkdir(parents=True)
        override.write_text("raise RuntimeError('override')\n", encoding="utf-8")
        devtool_config = workspace.parent / "conf/devtool.conf"
        devtool_config.write_text(
            f"[General]\nworkspace_path = {workspace}\n",
            encoding="utf-8",
            newline="\n",
        )
        with patches[0], patches[1]:
            iteration = MODULE.DirectSdkIteration(
                root,
                "pci-x86-64",
                workspace.parent,
                runner=runner,
                boot_factory=FakeBoot,
            )
            with self.assertRaisesRegex(
                MODULE.SdkIterationError, "unexpected residual state"
            ):
                iteration._prepare_workspace()
        self.assertFalse(runner.calls)

    def test_existing_workspace_refuses_altered_layer_metadata(self) -> None:
        root, selected, runner, _output, patches = self.iteration_fixture()
        workspace = root / selected["development"]["build_dir"] / "workspace"
        self.write_resting_workspace(workspace)
        (workspace / "conf/layer.conf").write_text(
            'BBPATH =. "${LAYERDIR}:"\nBBPATH =. "/tmp/override:"\n',
            encoding="utf-8",
            newline="\n",
        )
        devtool_config = workspace.parent / "conf/devtool.conf"
        devtool_config.write_text(
            f"[General]\nworkspace_path = {workspace}\n",
            encoding="utf-8",
            newline="\n",
        )
        with patches[0], patches[1]:
            iteration = MODULE.DirectSdkIteration(
                root,
                "pci-x86-64",
                workspace.parent,
                runner=runner,
                boot_factory=FakeBoot,
            )
            with self.assertRaisesRegex(
                MODULE.SdkIterationError, "metadata is not authoritative"
            ):
                iteration._prepare_workspace()
        self.assertFalse(runner.calls)

    @unittest.skipUnless(os.name == "posix", "symlink contract requires POSIX")
    def test_symlinked_learner_root_is_rejected_before_devtool(self) -> None:
        root, selected, runner, _output, patches = self.iteration_fixture()
        workspace = root / selected["development"]["build_dir"] / "workspace"
        self.write_resting_workspace(workspace)
        devtool_config = workspace.parent / "conf/devtool.conf"
        devtool_config.write_text(
            f"[General]\nworkspace_path = {workspace}\n",
            encoding="utf-8",
            newline="\n",
        )
        outside = root / "outside-source"
        outside.mkdir()
        (workspace.parent / "learner-source").symlink_to(
            outside,
            target_is_directory=True,
        )
        with patches[0], patches[1]:
            iteration = MODULE.DirectSdkIteration(
                root,
                "pci-x86-64",
                workspace.parent,
                runner=runner,
                boot_factory=FakeBoot,
            )
            with self.assertRaisesRegex(
                MODULE.SdkIterationError, "learner source root"
            ):
                iteration._prepare_workspace()
        self.assertFalse(runner.calls)
        self.assertEqual([], list(outside.iterdir()))

    @unittest.skipUnless(os.name == "posix", "symlink contract requires POSIX")
    def test_build_path_preflight_refuses_a_symlinked_development_root(self) -> None:
        root, selected, runner, _output, patches = self.iteration_fixture()
        outside = root / "outside"
        outside.mkdir()
        build_dir = root / selected["development"]["build_dir"]
        (build_dir / "conf/local.conf").unlink()
        (build_dir / "conf/bblayers.conf").unlink()
        (build_dir / "conf").rmdir()
        (build_dir / ".qemu-edu-config/conf/local.conf").unlink()
        (build_dir / ".qemu-edu-config/conf").rmdir()
        (build_dir / ".qemu-edu-config").rmdir()
        build_dir.rmdir()
        build_dir.symlink_to(outside, target_is_directory=True)
        with patches[0]:
            with self.assertRaisesRegex(
                MODULE.SdkIterationError, "not a regular directory"
            ):
                MODULE.DirectSdkIteration(
                    root,
                    "pci-x86-64",
                    build_dir,
                    runner=runner,
                    boot_factory=FakeBoot,
                )
        self.assertFalse(runner.calls)

    @unittest.skipUnless(os.name == "posix", "devtool shell path contract requires POSIX")
    def test_build_path_preflight_refuses_shell_metacharacters(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "unsafe;repository"
            root.mkdir()
            with self.assertRaisesRegex(
                MODULE.SdkIterationError, "unsafe for locked devtool"
            ):
                MODULE.DirectSdkIteration(
                    root,
                    "pci-x86-64",
                    root / "build-sdk-pci-x86-64",
                )

    def test_execution_failure_undeploys_stops_resets_and_leaves_no_evidence(self) -> None:
        root, selected, runner, output, patches = self.iteration_fixture()
        FakeBoot.fail_execution = True
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8]:
            iteration = MODULE.DirectSdkIteration(
                root,
                "pci-x86-64",
                root / selected["development"]["build_dir"],
                runner=runner,
                boot_factory=FakeBoot,
            )
            with self.assertRaisesRegex(MODULE.SdkIterationError, "sample failed"):
                iteration.execute()
        self.assertFalse(output.exists())
        self.assertTrue(FakeBoot.instances[0].stopped)
        self.assertTrue(
            any(command[:2] == ("devtool", "undeploy-target") for command in runner.calls)
        )
        self.assertIn(
            ("devtool", "reset", "--no-clean", "qemu-edu-sdk-sample"),
            runner.calls,
        )

    def test_repeated_signal_during_evidence_removal_cannot_skip_finalization(self) -> None:
        root, selected, runner, output, patches = self.iteration_fixture()
        FakeBoot.fail_execution = True
        original_clear = MODULE.clear_evidence
        clear_calls = 0

        def interrupt_final_clear(path: Path) -> None:
            nonlocal clear_calls
            clear_calls += 1
            if clear_calls == 2:
                handler = MODULE.signal.getsignal(MODULE.signal.SIGTERM)
                if not callable(handler):
                    raise AssertionError("cleanup cancellation handler is unavailable")
                handler(MODULE.signal.SIGTERM, None)
            original_clear(path)

        with (
            patches[0], patches[1], patches[2], patches[3], patches[4],
            patches[5], patches[6], patches[7], patches[8],
            patch.object(MODULE, "clear_evidence", side_effect=interrupt_final_clear),
        ):
            iteration = MODULE.DirectSdkIteration(
                root,
                "pci-x86-64",
                root / selected["development"]["build_dir"],
                runner=runner,
                boot_factory=FakeBoot,
            )
            with self.assertRaisesRegex(
                MODULE.SdkIterationError, "sample failed"
            ) as raised:
                iteration.execute()
        self.assertEqual(2, clear_calls)
        self.assertFalse(output.exists())
        self.assertTrue(FakeBoot.instances[0].stopped)
        self.assertTrue(
            any("interrupted by signal" in note for note in raised.exception.__notes__)
        )
        self.assertTrue(
            any(command[:2] == ("bitbake-layers", "remove-layer") for command in runner.calls)
        )

    def test_signal_during_success_finalization_clears_success_evidence(self) -> None:
        root, selected, runner, output, patches = self.iteration_fixture()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8]:
            iteration = MODULE.DirectSdkIteration(
                root,
                "pci-x86-64",
                root / selected["development"]["build_dir"],
                runner=runner,
                boot_factory=FakeBoot,
            )
            original_cleanup = iteration._cleanup_development_state
            cleanup_calls = 0

            def interrupt_final_cleanup() -> None:
                nonlocal cleanup_calls
                cleanup_calls += 1
                if cleanup_calls == 2:
                    handler = MODULE.signal.getsignal(MODULE.signal.SIGTERM)
                    if not callable(handler):
                        raise AssertionError("cleanup cancellation handler is unavailable")
                    handler(MODULE.signal.SIGTERM, None)
                original_cleanup()

            with patch.object(
                iteration,
                "_cleanup_development_state",
                side_effect=interrupt_final_cleanup,
            ):
                with self.assertRaisesRegex(
                    MODULE.SdkCancellation, "interrupted by signal"
                ):
                    iteration.execute()
        self.assertEqual(2, cleanup_calls)
        self.assertFalse(output.exists())
        self.assertTrue(all(boot.stopped for boot in FakeBoot.instances))

    def test_signal_at_validated_evidence_publication_commits_success(self) -> None:
        root, selected, runner, output, patches = self.iteration_fixture()

        def publish_and_signal(path: Path, _document: dict) -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}\n", encoding="utf-8")
            handler = MODULE.signal.getsignal(MODULE.signal.SIGTERM)
            if not callable(handler):
                raise AssertionError("publication cancellation handler is unavailable")
            handler(MODULE.signal.SIGTERM, None)

        with (
            patches[0], patches[1], patches[2], patches[3], patches[4],
            patch.object(MODULE, "write_evidence", side_effect=publish_and_signal),
            patches[6], patches[7], patches[8],
        ):
            iteration = MODULE.DirectSdkIteration(
                root,
                "pci-x86-64",
                root / selected["development"]["build_dir"],
                runner=runner,
                boot_factory=FakeBoot,
            )
            self.assertEqual(output, iteration.execute())
        self.assertTrue(iteration.committed)
        self.assertTrue(output.is_file())
        self.assertTrue(all(boot.stopped for boot in FakeBoot.instances))

    def test_publication_validation_failure_removes_evidence(self) -> None:
        root, selected, runner, output, patches = self.iteration_fixture()
        with (
            patches[0], patches[1], patches[2], patches[3], patches[4],
            patches[5], patches[6],
            patch.object(
                MODULE,
                "validate_evidence",
                side_effect=[None, MODULE.SdkEvidenceError("invalid publication")],
            ),
            patches[8],
        ):
            iteration = MODULE.DirectSdkIteration(
                root,
                "pci-x86-64",
                root / selected["development"]["build_dir"],
                runner=runner,
                boot_factory=FakeBoot,
            )
            with self.assertRaisesRegex(
                MODULE.SdkEvidenceError, "invalid publication"
            ):
                iteration.execute()
        self.assertFalse(iteration.committed)
        self.assertFalse(output.exists())
        self.assertTrue(all(boot.stopped for boot in FakeBoot.instances))

    def test_deployed_artifact_must_match_the_built_file_digest(self) -> None:
        root, selected, runner, output, patches = self.iteration_fixture()
        FakeBoot.bad_artifact_digest = True
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8]:
            iteration = MODULE.DirectSdkIteration(
                root,
                "pci-x86-64",
                root / selected["development"]["build_dir"],
                runner=runner,
                boot_factory=FakeBoot,
            )
            with self.assertRaisesRegex(
                MODULE.SdkIterationError, "differs from the built artifact"
            ):
                iteration.execute()
        self.assertFalse(output.exists())
        self.assertTrue(FakeBoot.instances[0].stopped)
        self.assertIn(
            ("devtool", "reset", "--no-clean", "qemu-edu-sdk-sample"),
            runner.calls,
        )

    def test_tooling_preflight_fails_before_build_or_workspace_mutation(self) -> None:
        root, selected, runner, output, patches = self.iteration_fixture()
        patches = list(patches)
        patches[8] = patch.object(
            MODULE,
            "verify_tooling",
            side_effect=MODULE.SdkToolingError("locked command mismatch"),
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8]:
            iteration = MODULE.DirectSdkIteration(
                root,
                "pci-x86-64",
                root / selected["development"]["build_dir"],
                runner=runner,
                boot_factory=FakeBoot,
            )
            with self.assertRaisesRegex(MODULE.SdkToolingError, "mismatch"):
                iteration.execute()
        self.assertFalse(output.exists())
        self.assertEqual([], runner.calls)
        self.assertEqual([], FakeBoot.instances)

    def test_retained_ide_output_fails_before_tooling_or_build_mutation(self) -> None:
        root, selected, runner, output, patches = self.iteration_fixture()
        retained = root / selected["development"]["build_dir"] / MODULE.IDE_OUTPUT_DIRNAME
        retained.mkdir()
        (retained / "environment-setup").write_text(
            "retained output\n", encoding="utf-8", newline="\n"
        )
        output.parent.mkdir(parents=True)
        output.write_text('{"result":"passed"}\n', encoding="utf-8", newline="\n")
        with patches[0], patches[1], patches[2], patches[3]:
            iteration = MODULE.DirectSdkIteration(
                root,
                "pci-x86-64",
                root / selected["development"]["build_dir"],
                runner=runner,
                boot_factory=FakeBoot,
            )
            with self.assertRaisesRegex(
                MODULE.SdkIterationError, "retained IDE output must be moved"
            ):
                iteration.execute()
        self.assertFalse(output.exists())
        self.assertEqual([], runner.calls)
        self.assertEqual([], FakeBoot.instances)

    def test_retained_learner_output_fails_before_tooling_or_build_mutation(self) -> None:
        root, selected, runner, output, patches = self.iteration_fixture()
        source_dir = (
            root
            / selected["development"]["build_dir"]
            / selected["development"]["source_dir"]
        )
        source_dir.mkdir(parents=True)
        (source_dir / "qemu-edu-sdk-sample.c").write_text(
            "retained source\n", encoding="utf-8", newline="\n"
        )
        (source_dir / "qemu-edu-sdk-sample").write_bytes(b"retained binary\n")
        (source_dir / "oe-workdir").mkdir()
        with patches[0], patches[1], patches[2], patches[3]:
            iteration = MODULE.DirectSdkIteration(
                root,
                "pci-x86-64",
                root / selected["development"]["build_dir"],
                runner=runner,
                boot_factory=FakeBoot,
            )
            with self.assertRaisesRegex(
                MODULE.SdkIterationError, "retained learner source must be moved"
            ):
                iteration.execute()
        self.assertFalse(output.exists())
        self.assertEqual([], runner.calls)
        self.assertEqual([], FakeBoot.instances)

    def test_source_only_retained_output_is_preserved_before_mutation(self) -> None:
        root, selected, runner, output, patches = self.iteration_fixture()
        source_dir = (
            root
            / selected["development"]["build_dir"]
            / selected["development"]["source_dir"]
        )
        source_dir.mkdir(parents=True)
        source = source_dir / "qemu-edu-sdk-sample.c"
        retained_bytes = b"/* learner edit */\nint main(void) { return 7; }\n"
        source.write_bytes(retained_bytes)
        output.parent.mkdir(parents=True)
        output.write_text('{"result":"passed"}\n', encoding="utf-8", newline="\n")
        with patches[0], patches[1], patches[2], patches[3]:
            iteration = MODULE.DirectSdkIteration(
                root,
                "pci-x86-64",
                root / selected["development"]["build_dir"],
                runner=runner,
                boot_factory=FakeBoot,
            )
            with self.assertRaisesRegex(
                MODULE.SdkIterationError, "retained learner source must be moved"
            ):
                iteration.execute()
        self.assertEqual(retained_bytes, source.read_bytes())
        self.assertFalse(output.exists())
        self.assertEqual([], runner.calls)
        self.assertEqual([], FakeBoot.instances)

    def test_empty_retained_source_directory_fails_before_mutation(self) -> None:
        root, selected, runner, output, patches = self.iteration_fixture()
        source_dir = (
            root
            / selected["development"]["build_dir"]
            / selected["development"]["source_dir"]
        )
        source_dir.mkdir(parents=True)
        with patches[0], patches[1], patches[2], patches[3]:
            iteration = MODULE.DirectSdkIteration(
                root,
                "pci-x86-64",
                root / selected["development"]["build_dir"],
                runner=runner,
                boot_factory=FakeBoot,
            )
            with self.assertRaisesRegex(
                MODULE.SdkIterationError, "retained learner source must be moved"
            ):
                iteration.execute()
        self.assertTrue(source_dir.is_dir())
        self.assertEqual([], list(source_dir.iterdir()))
        self.assertFalse(output.exists())
        self.assertEqual([], runner.calls)
        self.assertEqual([], FakeBoot.instances)

    def test_moved_retained_outputs_allow_a_second_complete_lifecycle(self) -> None:
        root, selected, runner, output, patches = self.iteration_fixture()
        build_dir = root / selected["development"]["build_dir"]
        with (
            patches[0], patches[1], patches[2], patches[3], patches[4],
            patches[5], patches[6], patches[7], patches[8],
        ):
            first = MODULE.DirectSdkIteration(
                root,
                "pci-x86-64",
                build_dir,
                runner=runner,
                boot_factory=FakeBoot,
            )
            self.assertEqual(output, first.execute())
            archive = root / "retained-sdk-output"
            archive.mkdir()
            shutil.move(str(first.source_dir), str(archive / "learner-source"))
            shutil.move(str(first.ide_output), str(archive / "learner-ide-sdk"))
            runner.calls.clear()
            FakeBoot.instances.clear()
            second = MODULE.DirectSdkIteration(
                root,
                "pci-x86-64",
                build_dir,
                runner=runner,
                boot_factory=FakeBoot,
            )
            self.assertEqual(output, second.execute())
        self.assertEqual(2, len(FakeBoot.instances))
        self.assertTrue(
            any(command[:2] == ("bitbake", "qemu-edu-image") for command in runner.calls)
        )

    def test_effective_bbpath_rejects_build_root_before_build(self) -> None:
        root, selected, runner, output, patches = self.iteration_fixture()
        configuration_root = MODULE.sdk_configuration_root(root, selected)
        runner.bbpath_override = os.pathsep.join(
            [
                str(configuration_root),
                str(root / selected["development"]["build_dir"]),
                *(str(root / item) for item in selected["build"]["layers"]),
            ]
        )
        with (
            patches[0], patches[1], patches[2], patches[3], patches[4],
            patches[5], patches[6], patches[7], patches[8],
        ):
            iteration = MODULE.DirectSdkIteration(
                root,
                "pci-x86-64",
                root / selected["development"]["build_dir"],
                runner=runner,
                boot_factory=FakeBoot,
            )
            with self.assertRaisesRegex(
                MODULE.SdkIterationError, "composition is not authoritative"
            ):
                iteration.execute()
        self.assertFalse(output.exists())
        self.assertFalse(any(command[0] == "bitbake" for command in runner.calls))

    def test_repository_preflight_clears_stale_evidence_and_rejects_dirty_subject(self) -> None:
        root, selected, runner, output, patches = self.iteration_fixture()
        output.parent.mkdir(parents=True)
        output.write_text('{"result":"passed"}\n', encoding="utf-8")
        with patches[0], patches[1], patches[2], patch.object(
            MODULE, "project_state", return_value=("e" * 40, True)
        ):
            iteration = MODULE.DirectSdkIteration(
                root,
                "pci-x86-64",
                root / selected["development"]["build_dir"],
                runner=runner,
                boot_factory=FakeBoot,
            )
            with self.assertRaisesRegex(MODULE.SdkIterationError, "clean repository"):
                iteration.preflight_repository()
        self.assertFalse(output.exists())
        self.assertEqual([], runner.calls)

    def test_post_write_validation_failure_removes_success_shaped_evidence(self) -> None:
        root, selected, runner, output, patches = self.iteration_fixture()
        patches = list(patches)
        patches[7] = patch.object(
            MODULE,
            "validate_evidence",
            side_effect=MODULE.SdkEvidenceError("current inputs changed"),
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8]:
            iteration = MODULE.DirectSdkIteration(
                root,
                "pci-x86-64",
                root / selected["development"]["build_dir"],
                runner=runner,
                boot_factory=FakeBoot,
            )
            with self.assertRaisesRegex(MODULE.SdkEvidenceError, "inputs changed"):
                iteration.execute()
        self.assertFalse(output.exists())
        self.assertTrue(all(item.stopped for item in FakeBoot.instances))

    def test_final_cleanup_failure_removes_success_shaped_evidence(self) -> None:
        root, selected, runner, output, patches = self.iteration_fixture()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8]:
            iteration = MODULE.DirectSdkIteration(
                root,
                "pci-x86-64",
                root / selected["development"]["build_dir"],
                runner=runner,
                boot_factory=FakeBoot,
            )
            original_cleanup = iteration._cleanup_development_state
            cleanup_calls = 0

            def fail_final_cleanup() -> None:
                nonlocal cleanup_calls
                cleanup_calls += 1
                if cleanup_calls == 2:
                    raise MODULE.SdkIterationError("final cleanup verification failed")
                original_cleanup()

            with patch.object(
                iteration,
                "_cleanup_development_state",
                side_effect=fail_final_cleanup,
            ):
                with self.assertRaisesRegex(
                    MODULE.SdkIterationError, "final cleanup verification failed"
                ):
                    iteration.execute()
        self.assertEqual(2, cleanup_calls)
        self.assertFalse(output.exists())
        self.assertTrue(all(item.stopped for item in FakeBoot.instances))

    def test_workspace_residual_after_reset_fails_and_removes_evidence(self) -> None:
        root, selected, runner, output, patches = self.iteration_fixture()
        runner.leave_workspace_residual = True
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8]:
            iteration = MODULE.DirectSdkIteration(
                root,
                "pci-x86-64",
                root / selected["development"]["build_dir"],
                runner=runner,
                boot_factory=FakeBoot,
            )
            with self.assertRaisesRegex(
                MODULE.SdkIterationError, "workspace residual state"
            ):
                iteration.execute()
        self.assertFalse(output.exists())
        self.assertFalse(runner.workspace_in_layers)

    def test_cleanup_never_invokes_devtool_from_an_unsafe_workspace(self) -> None:
        root, selected, runner, _output, patches = self.iteration_fixture()
        with patches[0], patches[1]:
            iteration = MODULE.DirectSdkIteration(
                root,
                "pci-x86-64",
                root / selected["development"]["build_dir"],
                runner=runner,
                boot_factory=FakeBoot,
            )
            self.write_resting_workspace(iteration.workspace)
            override = iteration.workspace / "lib/devtool/deploy.py"
            override.parent.mkdir(parents=True)
            override.write_text("raise RuntimeError('override')\n", encoding="utf-8")
            runner.workspace_in_layers = True
            with self.assertRaisesRegex(
                MODULE.SdkIterationError, "workspace residual state"
            ):
                iteration._cleanup_development_state()
        self.assertFalse(any(command[0] == "devtool" for command in runner.calls))
        self.assertFalse(
            any(command[:2] == ("bitbake-layers", "remove-layer") for command in runner.calls)
        )

    def test_cleanup_restores_raw_configuration_before_any_bitbake_parse(self) -> None:
        root, selected, runner, _output, patches = self.iteration_fixture()
        with patches[0], patches[1]:
            iteration = MODULE.DirectSdkIteration(
                root,
                "pci-x86-64",
                root / selected["development"]["build_dir"],
                runner=runner,
                boot_factory=FakeBoot,
            )
            self.write_resting_workspace(iteration.workspace)
            runner.workspace_in_layers = True
            (iteration.build_dir / "conf/local.conf").write_text(
                'BBPATH = "/tmp/untrusted"\n', encoding="utf-8"
            )
            with self.assertRaisesRegex(
                MODULE.SdkIterationError, "configuration authority"
            ):
                iteration._cleanup_development_state()
        self.assertFalse(any(command[0] == "devtool" for command in runner.calls))
        self.assertFalse(
            any(command[:2] == ("bitbake-layers", "remove-layer") for command in runner.calls)
        )
        self.assertEqual(
            MODULE.render_sdk_local_conf(selected),
            (iteration.build_dir / "conf/local.conf").read_text(encoding="utf-8"),
        )

    def test_cleanup_rejects_automatic_configuration_before_any_parser(self) -> None:
        root, selected, runner, _output, patches = self.iteration_fixture()
        with patches[0], patches[1]:
            iteration = MODULE.DirectSdkIteration(
                root,
                "pci-x86-64",
                root / selected["development"]["build_dir"],
                runner=runner,
                boot_factory=FakeBoot,
            )
            self.write_resting_workspace(iteration.workspace)
            runner.workspace_in_layers = True
            (iteration.build_dir / "conf/bblock.conf").write_text(
                'BBPATH = "/tmp/untrusted"\n', encoding="utf-8"
            )
            with self.assertRaisesRegex(
                MODULE.SdkIterationError, "configuration authority"
            ):
                iteration._cleanup_development_state()
        self.assertFalse(runner.calls)

    def test_cleanup_refuses_untrusted_devtool_configuration(self) -> None:
        root, selected, runner, _output, patches = self.iteration_fixture()
        with patches[0], patches[1]:
            iteration = MODULE.DirectSdkIteration(
                root,
                "pci-x86-64",
                root / selected["development"]["build_dir"],
                runner=runner,
                boot_factory=FakeBoot,
            )
            self.write_resting_workspace(iteration.workspace)
            runner.workspace_in_layers = True
            iteration.devtool_config.write_text(
                "[General]\nworkspace_path = /tmp/untrusted-workspace\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                MODULE.SdkIterationError, "devtool configuration"
            ):
                iteration._cleanup_development_state()
        self.assertFalse(any(command[0] == "devtool" for command in runner.calls))
        self.assertFalse(
            any(command[:2] == ("bitbake-layers", "remove-layer") for command in runner.calls)
        )

    def test_early_cleanup_cancellation_still_removes_target_and_stops_boot(self) -> None:
        root, selected, runner, _output, patches = self.iteration_fixture()
        with patches[0], patches[1]:
            iteration = MODULE.DirectSdkIteration(
                root,
                "pci-x86-64",
                root / selected["development"]["build_dir"],
                runner=runner,
                boot_factory=FakeBoot,
            )
            (iteration.build_dir / "conf/local.conf").write_text(
                'BBPATH = "/tmp/untrusted"\n', encoding="utf-8"
            )
            boot = FakeBoot(runner, iteration.machine, iteration.image)
            boot.start()
            iteration.active_boot = boot
            iteration.deployment_attempted = True
            with (
                patch.object(
                    MODULE,
                    "configure_authoritative_build",
                    side_effect=MODULE.SdkCancellation(MODULE.signal.SIGTERM),
                ),
                self.assertRaises(MODULE.SdkCancellation),
            ):
                iteration._cleanup_development_state()
        self.assertTrue(boot.stopped)
        self.assertIsNone(iteration.active_boot)
        self.assertIn(("rm", "-f", iteration.guest_binary), boot.remote_calls)

    def test_failed_layer_removal_falls_back_to_exact_direct_configuration(self) -> None:
        root, selected, runner, _output, patches = self.iteration_fixture()
        runner.fail = ("bitbake-layers", "remove-layer")
        with patches[0], patches[1]:
            iteration = MODULE.DirectSdkIteration(
                root,
                "pci-x86-64",
                root / selected["development"]["build_dir"],
                runner=runner,
                boot_factory=FakeBoot,
            )
            self.write_resting_workspace(iteration.workspace)
            runner.workspace_in_layers = True
            with self.assertRaisesRegex(
                MODULE.SdkIterationError, "workspace layer removal"
            ):
                iteration._cleanup_development_state()
        self.assertFalse(runner.workspace_in_layers)
        self.assertEqual(
            MODULE.render_sdk_bblayers(root, selected),
            (iteration.build_dir / "conf/bblayers.conf").read_text(encoding="utf-8"),
        )

    def test_cleanup_preserves_cancellation_after_restoring_composition(self) -> None:
        root, selected, runner, _output, patches = self.iteration_fixture()
        original_output = runner.output
        interrupted = False

        def interrupt_once(arguments, *, timeout=120):
            nonlocal interrupted
            if tuple(arguments) == ("devtool", "-q", "status") and not interrupted:
                interrupted = True
                raise MODULE.SdkCancellation(MODULE.signal.SIGTERM)
            return original_output(arguments, timeout=timeout)

        with patches[0], patches[1]:
            iteration = MODULE.DirectSdkIteration(
                root,
                "pci-x86-64",
                root / selected["development"]["build_dir"],
                runner=runner,
                boot_factory=FakeBoot,
            )
            self.write_resting_workspace(iteration.workspace)
            runner.workspace_in_layers = True
            with patch.object(runner, "output", side_effect=interrupt_once):
                with self.assertRaises(MODULE.SdkCancellation):
                    iteration._cleanup_development_state()
        self.assertTrue(interrupted)
        self.assertFalse(runner.workspace_in_layers)

    def test_cleanup_refuses_workspace_checksum_path_traversal(self) -> None:
        root, selected, runner, _output, patches = self.iteration_fixture()
        with patches[0], patches[1]:
            iteration = MODULE.DirectSdkIteration(
                root,
                "pci-x86-64",
                root / selected["development"]["build_dir"],
                runner=runner,
                boot_factory=FakeBoot,
            )
            self.write_resting_workspace(iteration.workspace)
            appends = iteration.workspace / "appends"
            appends.mkdir()
            append = appends / MODULE.workspace_append_name("qemu-edu-sdk-sample")
            append.write_text(
                "EXTERNALSRC:pn-qemu-edu-sdk-sample = \"/tmp/source\"\n",
                encoding="utf-8",
                newline="\n",
            )
            digest = MODULE.hashlib.md5(
                append.read_bytes(),
                usedforsecurity=False,
            ).hexdigest()
            (iteration.workspace / ".devtool_md5").write_text(
                f"qemu-edu-sdk-sample|../../outside|{digest}\n",
                encoding="utf-8",
                newline="\n",
            )
            runner.workspace_in_layers = True
            with self.assertRaisesRegex(
                MODULE.SdkIterationError, "workspace residual state"
            ):
                iteration._cleanup_development_state()
        self.assertFalse(any(command[0] == "devtool" for command in runner.calls))

    def test_cleanup_refuses_self_consistent_untrusted_append(self) -> None:
        root, selected, runner, _output, patches = self.iteration_fixture()
        with patches[0], patches[1]:
            iteration = MODULE.DirectSdkIteration(
                root,
                "pci-x86-64",
                root / selected["development"]["build_dir"],
                runner=runner,
                boot_factory=FakeBoot,
            )
            self.write_resting_workspace(iteration.workspace)
            appends = iteration.workspace / "appends"
            appends.mkdir()
            append = appends / MODULE.workspace_append_name("qemu-edu-sdk-sample")
            append.write_text(
                'python () { bb.fatal("untrusted workspace metadata") }\n',
                encoding="utf-8",
                newline="\n",
            )
            digest = MODULE.hashlib.md5(
                append.read_bytes(),
                usedforsecurity=False,
            ).hexdigest()
            (iteration.workspace / ".devtool_md5").write_text(
                "qemu-edu-sdk-sample|appends/"
                f"{MODULE.workspace_append_name('qemu-edu-sdk-sample')}|"
                f"{digest}\n",
                encoding="utf-8",
                newline="\n",
            )
            runner.workspace_in_layers = True
            with self.assertRaisesRegex(
                MODULE.SdkIterationError, "workspace residual state"
            ):
                iteration._cleanup_development_state()
        self.assertFalse(any(command[0] == "devtool" for command in runner.calls))

    def test_cleanup_rediscovers_partial_workspace_and_recipe_state(self) -> None:
        root, selected, runner, _output, patches = self.iteration_fixture()
        with patches[0], patches[1]:
            iteration = MODULE.DirectSdkIteration(
                root,
                "pci-x86-64",
                root / selected["development"]["build_dir"],
                runner=runner,
                boot_factory=FakeBoot,
            )
            self.write_active_workspace(iteration.workspace, iteration.source_dir)
            runner.workspace_in_layers = True
            runner.modified_recipe = True
            iteration.active_boot = FakeBoot(
                runner,
                selected["build"]["machine"],
                selected["build"]["targets"][0],
            )
            iteration.active_boot.start()
            iteration.ssh_wrapper = root / "transport/ssh"
            iteration.scp_wrapper = root / "transport/scp"
            iteration.deployment_attempted = True
            iteration._cleanup_development_state()
        self.assertFalse(runner.workspace_in_layers)
        self.assertFalse(runner.modified_recipe)
        self.assertTrue(FakeBoot.instances[0].stopped)
        self.assertTrue(
            any(
                command[:2] == ("devtool", "undeploy-target")
                for command in runner.calls
            )
        )
        self.assertIn(
            ("devtool", "reset", "--no-clean", "qemu-edu-sdk-sample"),
            runner.calls,
        )
        self.assertTrue(
            any(command[:2] == ("bitbake-layers", "remove-layer") for command in runner.calls)
        )

    def test_cleanup_retains_generated_ide_output_outside_workspace(self) -> None:
        root, selected, runner, _output, patches = self.iteration_fixture()
        with patches[0], patches[1]:
            iteration = MODULE.DirectSdkIteration(
                root,
                "pci-x86-64",
                root / selected["development"]["build_dir"],
                runner=runner,
                boot_factory=FakeBoot,
            )
            self.write_active_workspace(iteration.workspace, iteration.source_dir)
            generated = iteration.workspace / "ide-sdk/sample/scripts"
            generated.mkdir(parents=True)
            (generated / "helper").write_text(
                "generated output\n", encoding="utf-8", newline="\n"
            )
            runner.workspace_in_layers = True
            runner.modified_recipe = True
            iteration._cleanup_development_state()
        self.assertFalse((iteration.workspace / "ide-sdk").exists())
        self.assertEqual(
            "generated output\n",
            (iteration.ide_output / "sample/scripts/helper").read_text(
                encoding="utf-8"
            ),
        )

    def test_cleanup_never_resets_known_modified_recipe_without_active_append(self) -> None:
        root, selected, runner, _output, patches = self.iteration_fixture()
        with patches[0], patches[1]:
            iteration = MODULE.DirectSdkIteration(
                root,
                "pci-x86-64",
                root / selected["development"]["build_dir"],
                runner=runner,
                boot_factory=FakeBoot,
            )
            self.write_resting_workspace(iteration.workspace)
            runner.workspace_in_layers = True
            runner.modified_recipe = True
            iteration.recipe_modified = True
            with self.assertRaisesRegex(
                MODULE.SdkIterationError, "workspace residual state"
            ):
                iteration._cleanup_development_state()
        self.assertFalse(any(command[0] == "devtool" for command in runner.calls))

    def test_failed_deploy_command_still_attempts_undeploy_and_reset(self) -> None:
        root, selected, runner, output, patches = self.iteration_fixture()
        runner.fail = ("devtool", "deploy-target")
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8]:
            iteration = MODULE.DirectSdkIteration(
                root,
                "pci-x86-64",
                root / selected["development"]["build_dir"],
                runner=runner,
                boot_factory=FakeBoot,
            )
            with self.assertRaisesRegex(MODULE.SdkIterationError, "command failed"):
                iteration.execute()
        self.assertFalse(output.exists())
        self.assertTrue(
            any(command[:2] == ("devtool", "undeploy-target") for command in runner.calls)
        )
        self.assertIn(
            ("devtool", "reset", "--no-clean", "qemu-edu-sdk-sample"),
            runner.calls,
        )

    def test_partial_runqemu_start_is_stopped_and_workspace_is_reset(self) -> None:
        root, selected, runner, output, patches = self.iteration_fixture()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8]:
            iteration = MODULE.DirectSdkIteration(
                root,
                "pci-x86-64",
                root / selected["development"]["build_dir"],
                runner=runner,
                boot_factory=FailingStartBoot,
            )
            with self.assertRaisesRegex(MODULE.SdkIterationError, "startup failed"):
                iteration.execute()
        self.assertFalse(output.exists())
        self.assertTrue(FailingStartBoot.instances[-1].stopped)
        self.assertIn(
            ("devtool", "reset", "--no-clean", "qemu-edu-sdk-sample"),
            runner.calls,
        )

    def test_wrapper_declares_fixed_build_root_and_no_passthrough_arguments(self) -> None:
        wrapper = (ROOT / "sdk-test.sh").read_text(encoding="utf-8")
        self.assertIn("get development.build_dir", wrapper)
        self.assertTrue(wrapper.startswith("#!/bin/bash -p\n"))
        self.assertIn('BUILD_DIR="$ROOT_DIR/$SDK_BUILD_DIR"', wrapper)
        self.assertIn('--build-dir "$BUILD_DIR" preflight-path', wrapper)
        self.assertNotIn("CONFIGURE_TOOL", wrapper)
        self.assertIn('--build-dir "$BUILD_DIR" run', wrapper)
        self.assertLess(
            wrapper.index("preflight-path"),
            wrapper.index('source "$ROOT_DIR/environment.sh"'),
        )
        environment_guard = wrapper.index(
            "The direct-eSDK entrypoint owns environment initialization"
        )
        environment_source = wrapper.index('source "$ROOT_DIR/environment.sh"')
        controller = wrapper.index('python3 "$ITERATION_TOOL"', environment_source)
        self.assertLess(environment_guard, environment_source)
        self.assertLess(environment_guard, wrapper.index("ROOT_DIR="))
        self.assertIn("CDPATH='' builtin cd -- \"$SCRIPT_DIR\"", wrapper)
        self.assertIn("builtin pwd -P", wrapper)
        self.assertNotIn('dirname "${BASH_SOURCE[0]}"', wrapper)
        native_git = wrapper.index("NATIVE_GIT=$(type -P git)")
        native_git_path = wrapper.index('PATH="$NATIVE_GIT_DIR:$PATH"')
        self.assertLess(native_git, environment_source)
        self.assertGreater(native_git_path, environment_source)
        self.assertLess(native_git_path, controller)
        self.assertIn("unset NATIVE_GIT NATIVE_GIT_DIR", wrapper)
        self.assertLess(wrapper.index("unset PYTHONPATH", environment_source), controller)
        for variable in (
            "BDIR",
            "BITBAKEDIR",
            "GIT_CONFIG_COUNT",
            "GIT_DIR",
            "OEROOT",
            "PYTHONHOME",
            "PYTHONPATH",
            "TEMPLATECONF",
        ):
            self.assertIn(variable, wrapper[environment_guard:environment_source])
        self.assertIn("export PYTHONNOUSERSITE=1", wrapper)
        self.assertIn("export PYTHONDONTWRITEBYTECODE=1", wrapper)
        self.assertNotIn('"$@"', wrapper)
        self.assertNotIn("SDK_EVIDENCE_OUTPUT", wrapper)
        setup = (ROOT / "setup.sh").read_text(encoding="utf-8")
        self.assertIn('"$ROOT_DIR/sdk-test.sh" "$QEMU_EDU_LAB"', setup)

    def test_main_rejects_darwin_before_constructing_the_iteration(self) -> None:
        argv = [
            "sdk_iteration.py", "--repo", str(ROOT), "--lab", "pci-x86-64",
            "--build-dir", str(ROOT / "build-sdk-pci-x86-64"), "preflight-path",
        ]
        with (
            patch.object(MODULE.sys, "argv", argv),
            patch.object(MODULE.sys, "platform", "darwin"),
            patch.object(MODULE, "DirectSdkIteration") as constructor,
        ):
            self.assertEqual(1, MODULE.main())
        constructor.assert_not_called()

    def test_main_bounds_configuration_failures_without_a_traceback(self) -> None:
        argv = [
            "sdk_iteration.py", "--repo", str(ROOT), "--lab", "pci-x86-64",
            "--build-dir", str(ROOT / "build-sdk-pci-x86-64"), "run",
        ]
        stderr = io.StringIO()
        with (
            patch.object(MODULE.sys, "argv", argv),
            patch.object(MODULE.sys, "platform", "linux"),
            patch.object(MODULE.shutil, "which", return_value="/usr/bin/tool"),
            patch.object(MODULE.sys, "stderr", stderr),
            patch.object(MODULE, "DirectSdkIteration") as constructor,
        ):
            constructor.return_value.execute.side_effect = MODULE.ConfigurationError(
                "SDK configuration root is unsafe"
            )
            self.assertEqual(1, MODULE.main())
        self.assertEqual(
            "sdk-iteration: FAIL: SDK configuration root is unsafe\n",
            stderr.getvalue(),
        )

    @unittest.skipUnless(sys.platform == "linux", "privileged shebang is a Linux contract")
    def test_wrapper_shebang_ignores_bash_env_before_script_start(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "injected"
            payload = Path(temporary) / "bash-env"
            payload.write_text(f"touch {marker}\n", encoding="utf-8")
            environment = os.environ.copy()
            environment["BASH_ENV"] = str(payload)
            result = subprocess.run(
                [str(ROOT / "sdk-test.sh"), "--help"],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            injected = marker.exists()
        self.assertEqual(0, result.returncode)
        self.assertFalse(injected)

    @unittest.skipIf(sys.platform == "win32", "requires native Bash")
    def test_wrapper_rejects_empty_lab_before_dependencies(self) -> None:
        result = subprocess.run(
            ["bash", str(ROOT / "sdk-test.sh"), "--lab", ""],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(2, result.returncode)
        self.assertEqual("--lab requires a non-empty value\n", result.stderr)


if __name__ == "__main__":
    unittest.main()
