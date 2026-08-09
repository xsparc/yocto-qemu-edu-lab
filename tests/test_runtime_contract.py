# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


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
        self.assertIn("static bool force_dma_timeout;", source)
        self.assertIn("module_param(force_dma_timeout, bool, 0400);", source)
        self.assertNotIn("force_dma_timeout = true", source)

    def test_dma_interface_is_coherent_bounded_and_address_free(self) -> None:
        source = (
            ROOT
            / "meta-qemu-edu/recipes-kernel/qemu-edu-driver/files/qemu_edu.c"
        ).read_text(encoding="utf-8")
        self.assertIn("EDU_DMA_BUFFER_SIZE         4096", source)
        self.assertIn("EDU_DMA_MASK_BITS           28", source)
        self.assertIn("dmam_alloc_coherent", source)
        self.assertIn("dma_set_mask_and_coherent", source)
        self.assertIn("if (!length || length > EDU_DMA_BUFFER_SIZE)", source)
        self.assertIn("dma_wmb();", source)
        self.assertIn("dma_rmb();", source)
        self.assertIn("READ_ONCE(edu->last_irq_status) == EDU_IRQ_DMA", source)
        self.assertIn("edu->dma_faulted = true;", source)
        self.assertIn("pci_clear_master(edu->pdev);", source)
        self.assertIn("synchronize_irq(edu->irq);", source)
        self.assertIn("readl_poll_timeout", source)
        self.assertNotIn("DEVICE_ATTR_RO(dma_mask_bits)", source)
        self.assertNotIn("dma_address", source)
        self.assertNotIn("DEVICE_ATTR_RW(dma_source", source)
        self.assertNotIn("DEVICE_ATTR_RW(dma_destination", source)

    def test_interrupt_policy_uses_managed_modern_pci_vectors(self) -> None:
        source = (
            ROOT
            / "meta-qemu-edu/recipes-kernel/qemu-edu-driver/files/qemu_edu.c"
        ).read_text(encoding="utf-8")
        self.assertIn('static char *interrupt_mode = "auto";', source)
        self.assertIn("module_param(interrupt_mode, charp, 0400);", source)
        self.assertIn("PCI_IRQ_MSI | PCI_IRQ_INTX", source)
        self.assertIn("pci_alloc_irq_vectors(pdev, 1, 1, interrupt_flags)", source)
        self.assertIn("pci_irq_vector(pdev, 0)", source)
        self.assertIn("pci_dev_msi_enabled(pdev)", source)
        self.assertNotIn("pci_free_irq_vectors", source)
        self.assertNotIn("pci_intx(pdev", source)
        self.assertNotIn("pdev->irq", source)

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

    def test_guest_tool_license_checksums_match_selected_lines(self) -> None:
        recipe_dir = ROOT / "meta-qemu-edu/recipes-support/qemu-edu-tools"
        recipe = (recipe_dir / "qemu-edu-tools_1.0.bb").read_text(encoding="utf-8")
        entries = re.findall(
            r"file://([^;\s]+);beginline=(\d+);endline=(\d+);md5=([0-9a-f]{32})",
            recipe,
        )
        self.assertEqual(len(entries), 2)
        for filename, begin_text, end_text, expected in entries:
            with self.subTest(filename=filename):
                begin = int(begin_text)
                end = int(end_text)
                lines = (recipe_dir / "files" / filename).read_bytes().splitlines(
                    keepends=True
                )
                selected = b"".join(lines[begin - 1 : end])
                self.assertEqual(
                    hashlib.md5(selected, usedforsecurity=False).hexdigest(),
                    expected,
                )

    def test_extensionless_guest_tool_is_lf_normalized_and_syntax_checked(self) -> None:
        guest_tool = (
            "meta-qemu-edu/recipes-support/qemu-edu-tools/files/qemu-edu-test"
        )
        attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
        workflow = (ROOT / ".github/workflows/fast-checks.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn(f"{guest_tool} text eol=lf", attributes)
        self.assertIn(f"sh -n {guest_tool}", workflow)

    def test_schema_is_closed_and_covers_every_case(self) -> None:
        evidence = load_runtime_evidence()

        def string_schemas(value):
            if isinstance(value, dict):
                if value.get("type") == "string":
                    yield value
                for child in value.values():
                    yield from string_schemas(child)
            elif isinstance(value, list):
                for child in value:
                    yield from string_schemas(child)

        for version, count in (
            (1, 11),
            (2, len(evidence.V2_EXPECTED_TESTS)),
            (3, len(evidence.EXPECTED_TESTS)),
        ):
            with self.subTest(version=version):
                schema = json.loads(
                    (
                        ROOT
                        / f"schemas/qemu-edu-runtime-evidence-v{version}.schema.json"
                    ).read_text(encoding="utf-8")
                )
                self.assertFalse(schema["additionalProperties"])
                self.assertEqual(set(schema["required"]), set(schema["properties"]))
                self.assertEqual(
                    set(schema["properties"]["contract"]["required"]),
                    set(schema["properties"]["contract"]["properties"]),
                )
                self.assertFalse(
                    schema["properties"]["tests"]["items"]["additionalProperties"]
                )
                self.assertEqual(schema["properties"]["tests"]["minItems"], count)
                self.assertEqual(schema["properties"]["tests"]["maxItems"], count)
                self.assertEqual(
                    set(
                        schema["properties"]["tests"]["items"]["properties"][
                            "status"
                        ]["enum"]
                    ),
                    evidence.OEQA_STATUSES,
                )
                for definition in string_schemas(schema):
                    self.assertEqual(
                        definition.get("maxLength"), evidence.MAX_STRING_LENGTH
                    )

    def test_msi_policy_failures_still_attempt_restoration(self) -> None:
        oeqa_case = load_oeqa_case()
        bdf = "0000:00:05.0"

        fallback = oeqa_case.QemuEduRuntimeTests(
            "test_09_automatic_intx_fallback"
        )
        fallback.pci_device_bdf = MagicMock(return_value=bdf)
        fallback.run_ok = MagicMock(return_value="1")
        fallback.unload_module = MagicMock(side_effect=AssertionError("unload"))
        fallback.restore_msi_bus_and_default = MagicMock()
        with self.assertRaisesRegex(AssertionError, "unload"):
            fallback.test_09_automatic_intx_fallback()
        fallback.restore_msi_bus_and_default.assert_called_once_with(bdf, "1")

        cleanup = oeqa_case.QemuEduRuntimeTests(
            "test_10_required_msi_failure_and_cleanup"
        )
        cleanup.assert_default_msi = MagicMock(return_value=bdf)
        cleanup.unload_module = MagicMock()
        cleanup.run_ok = MagicMock(
            side_effect=("1", "34", AssertionError("cleanup assertion"))
        )
        cleanup.restore_msi_bus_and_default = MagicMock()
        with self.assertRaisesRegex(AssertionError, "cleanup assertion"):
            cleanup.test_10_required_msi_failure_and_cleanup()
        cleanup.restore_msi_bus_and_default.assert_called_once_with(bdf, "1")

    def test_dma_mode_failures_still_attempt_restoration(self) -> None:
        oeqa_case = load_oeqa_case()

        timeout = oeqa_case.QemuEduRuntimeTests(
            "test_17_dma_timeout_and_recovery"
        )
        timeout.unload_module = MagicMock(side_effect=AssertionError("unload"))
        timeout.restore_default_module = MagicMock()
        with self.assertRaisesRegex(AssertionError, "unload"):
            timeout.test_17_dma_timeout_and_recovery()
        timeout.restore_default_module.assert_called_once_with()

        teardown = oeqa_case.QemuEduRuntimeTests(
            "test_18_dma_teardown_and_rebind"
        )
        teardown.assert_default_msi = MagicMock(return_value="0000:00:05.0")
        teardown.assert_dma_roundtrip = MagicMock()
        teardown.run_ok = MagicMock(
            side_effect=("34", AssertionError("post-unload assertion"))
        )
        teardown.unload_module = MagicMock()
        teardown.restore_default_module = MagicMock()
        with self.assertRaisesRegex(AssertionError, "post-unload assertion"):
            teardown.test_18_dma_teardown_and_rebind()
        teardown.restore_default_module.assert_called_once_with()


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
        shutil.copy2(ROOT / "run.sh", self.root / "run.sh")
        (self.root / "run.sh").chmod(0o755)
        shutil.copy2(
            ROOT / "scripts/qemu_security_preflight.sh",
            self.scripts_dir / "qemu_security_preflight.sh",
        )
        (self.root / "environment.sh").write_text(
            'BUILD_DIR="$ROOT_DIR/build"\nexport BUILD_DIR\n', encoding="utf-8"
        )
        for name in (
            "source_lock.py",
            "configure_build.py",
            "runtime_evidence.py",
            "verify_qemu_security.py",
        ):
            (self.scripts_dir / name).touch()
        self.log = self.root / "calls.log"
        self._write_command(
            "ssh",
            "#!/usr/bin/env bash\nexit 0\n",
        )
        self._write_command(
            "bitbake-getvar",
            """#!/usr/bin/env bash
variable=${!#}
case "$variable" in
    DISTRO) printf '%s\\n' poky ;;
    MACHINE) printf '%s\\n' qemu-edu-x86-64 ;;
    BBLAYERS) printf '%s\\n' "$FAKE_LAYERS" ;;
    PN) printf '%s\\n' qemu-system-native ;;
    PV) printf '%s\\n' 10.2.0 ;;
    FILE) printf '%s\\n' "$FAKE_ROOT/layers/openembedded-core/meta/recipes-devtools/qemu/qemu-system-native_10.2.0.bb" ;;
    SRC_URI) printf '%s\\n' 'file://0001-hw-misc-edu-restrict-dma-access-to-dma-buffer.patch' ;;
    TESTIMAGEDEPENDS) printf '%s\\n' 'qemu-helper-native:do_populate_sysroot qemu-helper-native:do_addto_recipe_sysroot' ;;
    DEPENDS) printf '%s\\n' 'qemu-system-native pseudo-native' ;;
    S) printf '%s\\n' "$FAKE_ROOT/build/work/qemu-10.2.0" ;;
    STAGING_BINDIR_NATIVE) printf '%s\\n' "$FAKE_ROOT/build/work/qemu-helper/recipe-sysroot-native/usr/bin" ;;
    *) exit 2 ;;
esac
""",
        )
        self._write_command(
            "bitbake-layers",
            """#!/usr/bin/env bash
printf '=== qemu-system-native_10.2.0.bb ===\\n  %s\\n' \\
    "$FAKE_ROOT/meta-qemu-edu/recipes-devtools/qemu/qemu-system-native_10.2.0.bbappend"
""",
        )
        self._write_command(
            "bitbake",
            """#!/usr/bin/env bash
printf 'bitbake:%s:oeqa=%s\\n' "$*" "${OEQA_JSON_RESULT_DIR:-}" >> "$CALL_LOG"
if [ "${1:-}" = "qemu-system-native" ]; then
    case "${3:-}" in
        patch) exit "${QEMU_PATCH_STATUS:-${QEMU_TASK_STATUS:-0}}" ;;
        populate_sysroot) exit "${QEMU_POPULATE_STATUS:-${QEMU_TASK_STATUS:-0}}" ;;
        *) exit 2 ;;
    esac
fi
if [ "${1:-}" = "qemu-helper-native" ]; then
    case "${3:-}" in
        addto_recipe_sysroot) exit "${QEMU_HELPER_STATUS:-0}" ;;
        *) exit 2 ;;
    esac
fi
if [ "${2:-}" = "-c" ] && [ "${3:-}" = "testimage" ]; then
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
    */verify_qemu_security.py)
        printf 'security:%s\\n' "$*" >> "$CALL_LOG"
        case "$*" in
            *' metadata '*) exit "${SECURITY_METADATA_STATUS:-${SECURITY_STATUS:-0}}" ;;
            *' source '*) exit "${SECURITY_SOURCE_STATUS:-${SECURITY_STATUS:-0}}" ;;
            *' consumer '*) exit "${SECURITY_CONSUMER_STATUS:-${SECURITY_STATUS:-0}}" ;;
            *) exit 2 ;;
        esac
        ;;
    *) exit 2 ;;
esac
""",
        )
        self._write_command(
            "runqemu",
            "#!/usr/bin/env bash\nprintf 'runqemu:%s\\n' \"$*\" >> \"$CALL_LOG\"\nexit 0\n",
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
                "FAKE_ROOT": str(self.root),
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

    def run_manual_wrapper(self, **overrides: str) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment.update(
            {
                "PATH": f"{self.bin_dir}{os.pathsep}{environment['PATH']}",
                "CALL_LOG": str(self.log),
                "FAKE_ROOT": str(self.root),
                "FAKE_LAYERS": f"{self.root}/layers/core {self.root}/meta-qemu-edu",
            }
        )
        environment.update(overrides)
        return subprocess.run(
            ["bash", str(self.root / "run.sh")],
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
        metadata = next(line for line in calls.splitlines() if "security:" in line)
        self.assertIn(" metadata ", metadata)
        self.assertIn("--pv 10.2.0", metadata)
        self.assertIn(" source --source-tree ", calls)
        call_lines = calls.splitlines()
        patch_index = next(
            index for index, line in enumerate(call_lines)
            if "bitbake:qemu-system-native -c patch" in line
        )
        source_index = next(
            index for index, line in enumerate(call_lines)
            if "security:" in line and " source " in line
        )
        populate_index = next(
            index for index, line in enumerate(call_lines)
            if "bitbake:qemu-system-native -c populate_sysroot" in line
        )
        helper_index = next(
            index for index, line in enumerate(call_lines)
            if "bitbake:qemu-helper-native -c addto_recipe_sysroot" in line
        )
        consumer_index = next(
            index for index, line in enumerate(call_lines)
            if "security:" in line and " consumer " in line
        )
        image_index = next(
            index for index, line in enumerate(call_lines)
            if line.startswith("bitbake:qemu-edu-image:")
        )
        self.assertLess(patch_index, source_index)
        self.assertLess(source_index, populate_index)
        self.assertLess(populate_index, helper_index)
        self.assertLess(helper_index, consumer_index)
        self.assertLess(consumer_index, image_index)
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

    def test_security_failure_prevents_any_qemu_or_image_build(self) -> None:
        result = self.run_wrapper(SECURITY_STATUS="5")
        self.assertEqual(result.returncode, 5)
        calls = self.log.read_text(encoding="utf-8")
        self.assertIn("security:", calls)
        self.assertNotIn("bitbake:", calls)

    def test_qemu_preflight_task_failure_prevents_image_build(self) -> None:
        result = self.run_wrapper(QEMU_TASK_STATUS="6")
        self.assertEqual(result.returncode, 6)
        calls = self.log.read_text(encoding="utf-8")
        self.assertIn("bitbake:qemu-system-native -c patch", calls)
        self.assertNotIn("bitbake:qemu-edu-image", calls)

    def test_qemu_populate_failure_prevents_consumer_and_image(self) -> None:
        result = self.run_wrapper(QEMU_POPULATE_STATUS="6")
        self.assertEqual(result.returncode, 6)
        calls = self.log.read_text(encoding="utf-8")
        self.assertIn("bitbake:qemu-system-native -c populate_sysroot", calls)
        self.assertNotIn("bitbake:qemu-helper-native", calls)
        self.assertNotIn(" consumer ", calls)
        self.assertNotIn("bitbake:qemu-edu-image", calls)

    def test_native_consumer_failure_prevents_image_build(self) -> None:
        result = self.run_wrapper(SECURITY_CONSUMER_STATUS="7")
        self.assertEqual(result.returncode, 7)
        calls = self.log.read_text(encoding="utf-8")
        self.assertIn("bitbake:qemu-helper-native -c addto_recipe_sysroot", calls)
        self.assertIn(" consumer ", calls)
        self.assertNotIn("bitbake:qemu-edu-image", calls)

    def test_patched_source_failure_prevents_sysroot_and_image_build(self) -> None:
        result = self.run_wrapper(SECURITY_SOURCE_STATUS="7")
        self.assertEqual(result.returncode, 7)
        calls = self.log.read_text(encoding="utf-8")
        self.assertIn("bitbake:qemu-system-native -c patch", calls)
        self.assertNotIn("bitbake:qemu-system-native -c populate_sysroot", calls)
        self.assertNotIn("bitbake:qemu-edu-image", calls)

    def test_testimage_exit_wins_over_collector_failure(self) -> None:
        result = self.run_wrapper(TESTIMAGE_STATUS="7", COLLECT_STATUS="9")
        self.assertEqual(result.returncode, 7)

    def test_collector_and_validator_failures_propagate(self) -> None:
        collected = self.run_wrapper(COLLECT_STATUS="9")
        self.assertEqual(collected.returncode, 9)
        self.log.unlink(missing_ok=True)
        validated = self.run_wrapper(VALIDATE_STATUS="8")
        self.assertEqual(validated.returncode, 8)

    def test_manual_run_never_reaches_runqemu_after_preflight_failure(self) -> None:
        for variable in (
            "SECURITY_METADATA_STATUS",
            "SECURITY_SOURCE_STATUS",
            "QEMU_POPULATE_STATUS",
            "QEMU_HELPER_STATUS",
            "SECURITY_CONSUMER_STATUS",
        ):
            with self.subTest(variable=variable):
                self.log.unlink(missing_ok=True)
                result = self.run_manual_wrapper(**{variable: "9"})
                self.assertEqual(result.returncode, 9, result.stderr)
                calls = self.log.read_text(encoding="utf-8")
                self.assertNotIn("runqemu:", calls)

        self.log.unlink(missing_ok=True)
        result = self.run_manual_wrapper()
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.log.read_text(encoding="utf-8")
        self.assertIn(" consumer ", calls)
        self.assertIn("runqemu:qemu-edu-x86-64 qemu-edu-image", calls)


if __name__ == "__main__":
    unittest.main()
