# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load_runtime_evidence():
    spec = importlib.util.spec_from_file_location(
        "runtime_evidence_contract", ROOT / "scripts/runtime_evidence.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_oeqa_case():
    oeqa = types.ModuleType("oeqa")
    core = types.ModuleType("oeqa.core")
    decorator = types.ModuleType("oeqa.core.decorator")
    depends = types.ModuleType("oeqa.core.decorator.depends")
    runtime = types.ModuleType("oeqa.runtime")
    runtime_case = types.ModuleType("oeqa.runtime.case")

    def identity_decorator(_dependencies):
        return lambda function: function

    depends.OETestDepends = identity_decorator
    runtime_case.OERuntimeTestCase = unittest.TestCase
    modules = {
        "oeqa": oeqa,
        "oeqa.core": core,
        "oeqa.core.decorator": decorator,
        "oeqa.core.decorator.depends": depends,
        "oeqa.runtime": runtime,
        "oeqa.runtime.case": runtime_case,
    }
    path = ROOT / "meta-qemu-edu/lib/oeqa/runtime/cases/qemu_edu.py"
    spec = importlib.util.spec_from_file_location("qemu_edu", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(module)
    return module


class RuntimeContractTests(unittest.TestCase):
    def test_oeqa_cases_match_evidence_contract(self) -> None:
        evidence = load_runtime_evidence()
        oeqa_case = load_oeqa_case()
        methods = unittest.defaultTestLoader.getTestCaseNames(
            oeqa_case.QemuEduRuntimeTests
        )
        actual = tuple(
            f"qemu_edu.QemuEduRuntimeTests.{method}" for method in methods
        )
        self.assertEqual(actual, evidence.EXPECTED_TESTS)

    def test_image_enables_native_bounded_runtime_testing(self) -> None:
        recipe = (ROOT / "meta-qemu-edu/recipes-core/images/qemu-edu-image.bb").read_text(
            encoding="utf-8"
        )
        self.assertIn("inherit testimage", recipe)
        self.assertIn('IMAGE_FEATURES += "ssh-server-dropbear"', recipe)
        self.assertIn('TEST_SUITES = "ping ssh qemu_edu"', recipe)
        self.assertIn('TEST_RUNQEMUPARAMS = "slirp"', recipe)
        self.assertIn('QEMU_USE_KVM = ""', recipe)

    def test_derived_machine_reuses_the_supported_kernel_bsp(self) -> None:
        machine = (
            ROOT / "meta-qemu-edu/conf/machine/qemu-edu-x86-64.conf"
        ).read_text(encoding="utf-8")
        self.assertIn('require conf/machine/qemux86-64.conf', machine)
        self.assertIn('MACHINEOVERRIDES =. "qemux86-64:"', machine)
        self.assertIn('KMACHINE = "qemux86-64"', machine)

    def test_timeout_fault_switch_is_read_only_and_disabled_by_default(self) -> None:
        source = (
            ROOT
            / "meta-qemu-edu/recipes-kernel/qemu-edu-driver/files/qemu_edu.c"
        ).read_text(encoding="utf-8")
        self.assertIn("static bool force_factorial_timeout;", source)
        self.assertIn("module_param(force_factorial_timeout, bool, 0400);", source)
        self.assertNotIn("force_factorial_timeout = true", source)

    def test_runtime_wrapper_fails_fast_without_host_ssh(self) -> None:
        wrapper = (ROOT / "runtime-test.sh").read_text(encoding="utf-8")
        self.assertIn("command -v ssh", wrapper)
        self.assertLess(wrapper.index("command -v ssh"), wrapper.index("bitbake"))

    def test_errno_helper_is_built_into_the_guest_tools(self) -> None:
        recipe = (
            ROOT
            / "meta-qemu-edu/recipes-support/qemu-edu-tools/qemu-edu-tools_1.0.bb"
        ).read_text(encoding="utf-8")
        helper = (
            ROOT
            / "meta-qemu-edu/recipes-support/qemu-edu-tools/files/qemu-edu-write.c"
        ).read_text(encoding="utf-8")
        self.assertIn("file://qemu-edu-write.c", recipe)
        self.assertIn("${CC} ${CFLAGS} ${CPPFLAGS} ${LDFLAGS}", recipe)
        self.assertIn("errno=%d", helper)

    def test_schema_is_closed_and_covers_every_case(self) -> None:
        schema = json.loads(
            (ROOT / "schemas/qemu-edu-runtime-evidence-v1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            set(schema["required"]),
            set(schema["properties"]),
        )
        self.assertEqual(
            set(schema["properties"]["contract"]["required"]),
            set(schema["properties"]["contract"]["properties"]),
        )
        self.assertFalse(schema["properties"]["tests"]["items"]["additionalProperties"])
        self.assertEqual(schema["properties"]["tests"]["minItems"], 11)
        self.assertEqual(schema["properties"]["tests"]["maxItems"], 11)
        evidence = load_runtime_evidence()
        self.assertEqual(
            set(schema["properties"]["tests"]["items"]["properties"]["status"]["enum"]),
            evidence.OEQA_STATUSES,
        )

        def string_schemas(value):
            if isinstance(value, dict):
                if value.get("type") == "string":
                    yield value
                for child in value.values():
                    yield from string_schemas(child)
            elif isinstance(value, list):
                for child in value:
                    yield from string_schemas(child)

        for definition in string_schemas(schema):
            self.assertEqual(definition.get("maxLength"), evidence.MAX_STRING_LENGTH)


@unittest.skipIf(sys.platform == "win32", "requires a native Linux Bash environment")
class RuntimeWrapperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.bin_dir = self.root / "bin"
        self.scripts_dir = self.root / "scripts"
        self.bin_dir.mkdir()
        self.scripts_dir.mkdir()
        shutil.copy2(ROOT / "runtime-test.sh", self.root / "runtime-test.sh")
        (self.root / "runtime-test.sh").chmod(0o755)
        (self.root / "environment.sh").write_text(
            'BUILD_DIR="$ROOT_DIR/build"\nexport BUILD_DIR\n', encoding="utf-8"
        )
        for name in ("source_lock.py", "configure_build.py", "runtime_evidence.py"):
            (self.scripts_dir / name).touch()
        self.log = self.root / "calls.log"
        self._write_command(
            "ssh",
            "#!/usr/bin/env bash\nexit 0\n",
        )
        self._write_command(
            "bitbake-getvar",
            """#!/usr/bin/env bash
case "$2" in
    DISTRO) printf '%s\\n' poky ;;
    MACHINE) printf '%s\\n' qemu-edu-x86-64 ;;
    BBLAYERS) printf '%s\\n' "$FAKE_LAYERS" ;;
    *) exit 2 ;;
esac
""",
        )
        self._write_command(
            "bitbake",
            """#!/usr/bin/env bash
printf 'bitbake:%s:oeqa=%s\\n' "$*" "${OEQA_JSON_RESULT_DIR:-}" >> "$CALL_LOG"
if [ "${2:-}" = "-c" ]; then
    install -d "$OEQA_JSON_RESULT_DIR"
    printf '{}\\n' > "$OEQA_JSON_RESULT_DIR/testresults.json"
    exit "${TESTIMAGE_STATUS:-0}"
fi
exit 0
""",
        )
        self._write_command(
            "python3",
            """#!/usr/bin/env bash
case "$1" in
    */source_lock.py)
        case "$*" in
            *' get build.machine') printf '%s\\n' qemu-edu-x86-64 ;;
            *' get build.targets --lines') printf '%s\\n' qemu-edu-image ;;
            *) exit 2 ;;
        esac
        ;;
    */configure_build.py)
        printf 'verify:%s\\n' "$*" >> "$CALL_LOG"
        exit "${VERIFY_STATUS:-0}"
        ;;
    */runtime_evidence.py)
        printf 'evidence:%s:oeqa=%s\\n' "$*" "${OEQA_JSON_RESULT_DIR:-}" >> "$CALL_LOG"
        case "$*" in
            *' collect '*) exit "${COLLECT_STATUS:-0}" ;;
            *' validate '*) exit "${VALIDATE_STATUS:-0}" ;;
            *) exit 2 ;;
        esac
        ;;
    *) exit 2 ;;
esac
""",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write_command(self, name: str, text: str) -> None:
        path = self.bin_dir / name
        path.write_text(text, encoding="utf-8", newline="\n")
        path.chmod(0o755)

    def run_wrapper(self, **overrides: str) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment.update(
            {
                "PATH": f"{self.bin_dir}{os.pathsep}{environment['PATH']}",
                "CALL_LOG": str(self.log),
                "FAKE_LAYERS": f"{self.root}/layers/core {self.root}/meta-qemu-edu",
            }
        )
        environment.update(overrides)
        return subprocess.run(
            ["bash", str(self.root / "runtime-test.sh")],
            cwd=self.root,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_wrapper_verifies_configuration_and_uses_fresh_oeqa_directory(self) -> None:
        stale = self.root / "build/evidence/oeqa.stale"
        stale.mkdir(parents=True)
        (stale / "testresults.json").write_text("{}\n", encoding="utf-8")
        result = self.run_wrapper()
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.log.read_text(encoding="utf-8")
        self.assertIn("verify:", calls)
        self.assertIn("--distro poky", calls)
        self.assertIn("--machine qemu-edu-x86-64", calls)
        testimage_call = next(
            line for line in calls.splitlines() if "-c testimage" in line
        )
        self.assertNotIn(str(stale), testimage_call)
        self.assertRegex(testimage_call, r"oeqa=.*[/\\]oeqa\.[A-Za-z0-9]+")

    def test_configuration_failure_prevents_build(self) -> None:
        result = self.run_wrapper(VERIFY_STATUS="6")
        self.assertEqual(result.returncode, 6)
        calls = self.log.read_text(encoding="utf-8")
        self.assertIn("verify:", calls)
        self.assertNotIn("bitbake:", calls)

    def test_testimage_exit_wins_over_collector_failure(self) -> None:
        result = self.run_wrapper(TESTIMAGE_STATUS="7", COLLECT_STATUS="9")
        self.assertEqual(result.returncode, 7)

    def test_collector_and_validator_failures_propagate(self) -> None:
        collected = self.run_wrapper(COLLECT_STATUS="9")
        self.assertEqual(collected.returncode, 9)
        self.log.unlink(missing_ok=True)
        validated = self.run_wrapper(VALIDATE_STATUS="8")
        self.assertEqual(validated.returncode, 8)


if __name__ == "__main__":
    unittest.main()
