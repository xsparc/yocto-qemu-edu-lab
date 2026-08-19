# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "sbom-evidence.sh"
SPEC = importlib.util.spec_from_file_location(
    "sbom_evidence_contract", ROOT / "scripts/sbom_evidence.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SbomContractTests(unittest.TestCase):
    def test_wrapper_is_fail_closed_and_removes_stale_evidence_before_task(self) -> None:
        text = WRAPPER.read_text(encoding="utf-8")
        verify = text.index('python3 "$CONFIGURE_TOOL"')
        preflight = text.index("preflight \"${SETTING_ARGS[@]}\"")
        remove = text.index('rm -f -- "$EVIDENCE_OUTPUT"')
        task = text.index('bitbake "$TARGET" -c create_image_sbom_spdx')
        collect = text.index('--build-dir "$BUILD_DIR" collect')
        validate = text.index("--require-pass")
        self.assertLess(verify, preflight)
        self.assertLess(preflight, remove)
        self.assertLess(remove, task)
        self.assertLess(task, collect)
        self.assertLess(collect, validate)
        self.assertIn('--require-revision "$REVISION"', text)
        self.assertIn("--require-current-inputs", text)
        self.assertGreaterEqual(text.count('--build-dir "$BUILD_DIR"'), 3)
        self.assertNotIn("SBOM_EVIDENCE_OUTPUT", text)

    def test_selected_evidence_paths_are_inside_separate_build_roots(self) -> None:
        pci_manifest, _, _, _, _, _ = MODULE.selected_contract(ROOT, "pci-x86-64")
        platform_manifest, _, _, _, _, _ = MODULE.selected_contract(
            ROOT, "platform-arm64"
        )
        self.assertEqual(
            ROOT / "build/evidence/qemu-edu-spdx-image-v1.json",
            MODULE.evidence_path(ROOT, pci_manifest),
        )
        self.assertEqual(
            ROOT / "build-platform-arm64/evidence/qemu-edu-spdx-image-v1.json",
            MODULE.evidence_path(ROOT, platform_manifest),
        )
        relocated = ROOT / "build-relocated"
        self.assertEqual(
            relocated / "evidence/qemu-edu-spdx-image-v1.json",
            MODULE.evidence_path(ROOT, pci_manifest, relocated),
        )
        self.assertEqual(
            relocated,
            MODULE.active_build_dir(ROOT, pci_manifest, "build-relocated"),
        )
        with self.assertRaisesRegex(MODULE.SbomEvidenceError, "non-empty"):
            MODULE.active_build_dir(ROOT, pci_manifest, "")

    def test_makefile_exposes_one_explicit_evidence_target(self) -> None:
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertIn("sbom-evidence:\n\t./sbom-evidence.sh", makefile)

    def test_core_rejects_explicit_empty_lab_as_invalid_arguments(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/sbom_evidence.py"),
                "--repo",
                str(ROOT),
                "--lab",
                "",
                "path",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("unknown lab", result.stderr)
        self.assertEqual("", result.stdout)

    @unittest.skipIf(sys.platform == "win32", "requires a native Linux Bash environment")
    def test_wrapper_rejects_explicit_empty_lab_before_dependencies(self) -> None:
        result = subprocess.run(
            ["bash", str(WRAPPER), "--lab", ""],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(2, result.returncode)
        self.assertEqual("--lab requires a non-empty value\n", result.stderr)


@unittest.skipIf(sys.platform == "win32", "requires a native Linux Bash environment")
class SbomWrapperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.bin_dir = self.root / "bin"
        self.scripts_dir = self.root / "scripts"
        self.bin_dir.mkdir()
        self.scripts_dir.mkdir()
        shutil.copy2(WRAPPER, self.root / "sbom-evidence.sh")
        (self.root / "sbom-evidence.sh").chmod(0o755)
        (self.root / "environment.sh").write_text(
            'QEMU_EDU_LAB=${QEMU_EDU_LAB:-pci-x86-64}\n'
            'BUILD_DIR="$ROOT_DIR/build"\n'
            'export QEMU_EDU_LAB BUILD_DIR\n',
            encoding="utf-8",
        )
        (self.scripts_dir / "lab_config.py").touch()
        (self.scripts_dir / "sbom_evidence.py").touch()
        (self.scripts_dir / "configure_build.py").touch()
        self.log = self.root / "calls.log"
        self.evidence = self.root / "build/evidence/qemu-edu-spdx-image-v1.json"
        self._write_command(
            "python3",
            r'''#!/usr/bin/env bash
case "$1" in
    */lab_config.py)
        case "$*" in
            *' get build.targets --lines') printf '%s\n' qemu-edu-image ;;
            *) exit 2 ;;
        esac
        ;;
    */sbom_evidence.py)
        case " $* " in
            *' preflight '*)
                printf 'preflight:%s\n' "$*" >> "$CALL_LOG"
                exit "${PREFLIGHT_STATUS:-0}"
                ;;
            *' path '*) printf '%s\n' "$FAKE_EVIDENCE" ;;
            *' collect '*)
                if [ -e "$FAKE_EVIDENCE" ]; then stale=yes; else stale=no; fi
                printf 'collect:stale=%s:%s\n' "$stale" "$*" >> "$CALL_LOG"
                [ "${COLLECT_STATUS:-0}" -eq 0 ] || exit "$COLLECT_STATUS"
                install -d "$(dirname "$FAKE_EVIDENCE")"
                printf '{}\n' > "$FAKE_EVIDENCE"
                ;;
            *' validate '*)
                printf 'validate:%s\n' "$*" >> "$CALL_LOG"
                [ -f "$FAKE_EVIDENCE" ] || exit 12
                exit "${VALIDATE_STATUS:-0}"
                ;;
            *) exit 2 ;;
        esac
        ;;
    */configure_build.py)
        printf 'verify:%s\n' "$*" >> "$CALL_LOG"
        exit "${VERIFY_STATUS:-0}"
        ;;
    *) exit 2 ;;
esac
''',
        )
        self._write_command(
            "bitbake-getvar",
            r'''#!/usr/bin/env bash
variable=${!#}
case "$variable" in
    DISTRO) printf '%s\n' poky ;;
    MACHINE) printf '%s\n' qemu-edu-x86-64 ;;
    BBLAYERS) printf '%s\n' "$FAKE_ROOT/layers/core $FAKE_ROOT/meta-qemu-edu" ;;
    SPDX_IMAGE_SUPPLIER_name|SPDX_PACKAGE_SUPPLIER_name) printf '\n' ;;
    SPDX_INCLUDE_BITBAKE_PARENT_BUILD|SPDX_INCLUDE_BUILD_VARIABLES|SPDX_INCLUDE_COMPILED_SOURCES|SPDX_INCLUDE_KERNEL_CONFIG|SPDX_INCLUDE_PACKAGECONFIG|SPDX_INCLUDE_SOURCES|SPDX_INCLUDE_TIMESTAMPS|SPDX_PRETTY) printf '%s\n' 0 ;;
    SPDX_INCLUDE_VEX) printf '%s\n' current ;;
    SPDX_PROFILES) printf '%s\n' 'core build software simpleLicensing security' ;;
    SPDX_VERSION) printf '%s\n' 3.0.1 ;;
    DEPLOY_DIR_IMAGE)
        if [ "${DEPLOY_EMPTY:-0}" -eq 0 ]; then
            printf '%s\n' "$FAKE_ROOT/build/deploy"
        fi
        ;;
    IMAGE_LINK_NAME) printf '%s\n' qemu-edu-image-machine ;;
    *) exit 2 ;;
esac
''',
        )
        self._write_command(
            "bitbake",
            r'''#!/usr/bin/env bash
printf 'bitbake:%s\n' "$*" >> "$CALL_LOG"
exit "${TASK_STATUS:-0}"
''',
        )
        self._write_command(
            "git",
            "#!/usr/bin/env bash\nprintf '%040d\\n' 1\n",
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
                "FAKE_EVIDENCE": str(self.evidence),
            }
        )
        environment.update(overrides)
        return subprocess.run(
            ["bash", str(self.root / "sbom-evidence.sh")],
            cwd=self.root,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )

    def calls(self) -> list[str]:
        if not self.log.exists():
            return []
        return self.log.read_text(encoding="utf-8").splitlines()

    def test_success_removes_stale_evidence_and_orders_all_stages(self) -> None:
        self.evidence.parent.mkdir(parents=True)
        self.evidence.write_text("stale\n", encoding="utf-8")
        result = self.run_wrapper()
        self.assertEqual(0, result.returncode, result.stderr)
        calls = self.calls()
        self.assertTrue(calls[0].startswith("verify:"))
        self.assertIn("--distro poky", calls[0])
        self.assertIn("--machine qemu-edu-x86-64", calls[0])
        self.assertTrue(calls[1].startswith("preflight:"))
        self.assertEqual("bitbake:qemu-edu-image -c create_image_sbom_spdx", calls[2])
        self.assertTrue(calls[3].startswith("collect:stale=no:"))
        self.assertTrue(calls[4].startswith("validate:"))
        self.assertIn("--require-current-inputs", calls[4])

    def test_configuration_failure_prevents_preflight_and_task(self) -> None:
        result = self.run_wrapper(VERIFY_STATUS="5")
        self.assertEqual(5, result.returncode)
        self.assertEqual(1, len(self.calls()))
        self.assertTrue(self.calls()[0].startswith("verify:"))

    def test_preflight_failure_prevents_task_and_preserves_stale_evidence(self) -> None:
        self.evidence.parent.mkdir(parents=True)
        self.evidence.write_text("stale\n", encoding="utf-8")
        result = self.run_wrapper(PREFLIGHT_STATUS="6")
        self.assertEqual(6, result.returncode)
        self.assertEqual(2, len(self.calls()))
        self.assertTrue(self.calls()[0].startswith("verify:"))
        self.assertTrue(self.calls()[1].startswith("preflight:"))
        self.assertEqual("stale\n", self.evidence.read_text(encoding="utf-8"))

    def test_task_exit_precedes_collection_and_stale_result_is_gone(self) -> None:
        self.evidence.parent.mkdir(parents=True)
        self.evidence.write_text("stale\n", encoding="utf-8")
        result = self.run_wrapper(TASK_STATUS="7", COLLECT_STATUS="9")
        self.assertEqual(7, result.returncode)
        self.assertFalse(self.evidence.exists())
        self.assertFalse(any(call.startswith("collect:") for call in self.calls()))

    def test_collector_validator_and_deploy_identity_failures_propagate(self) -> None:
        collected = self.run_wrapper(COLLECT_STATUS="9")
        self.assertEqual(9, collected.returncode)
        self.assertFalse(any(call.startswith("validate:") for call in self.calls()))

        self.log.unlink(missing_ok=True)
        validated = self.run_wrapper(VALIDATE_STATUS="8")
        self.assertEqual(8, validated.returncode)
        self.assertTrue(any(call.startswith("validate:") for call in self.calls()))

        self.log.unlink(missing_ok=True)
        missing = self.run_wrapper(DEPLOY_EMPTY="1")
        self.assertEqual(1, missing.returncode)
        self.assertIn("did not resolve", missing.stderr)
        self.assertFalse(any(call.startswith("collect:") for call in self.calls()))


if __name__ == "__main__":
    unittest.main()
