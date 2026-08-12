# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SETUP = ROOT / "setup.sh"
SPEC = importlib.util.spec_from_file_location(
    "lab_config", ROOT / "scripts/lab_config.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class LabConfigTests(unittest.TestCase):
    def repository_data(self) -> tuple[dict, dict[str, dict], dict]:
        index = json.loads((ROOT / "config/labs/index.json").read_text(encoding="utf-8"))
        manifests = {
            entry["id"]: json.loads(
                (ROOT / entry["manifest"]).read_text(encoding="utf-8")
            )
            for entry in index["labs"]
        }
        source_lock = json.loads(
            (ROOT / "config/sources.lock.json").read_text(encoding="utf-8")
        )
        return index, manifests, source_lock

    def fixture(self) -> tuple[Path, dict, dict[str, dict], dict]:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        index, manifests, source_lock = self.repository_data()
        return root, copy.deepcopy(index), copy.deepcopy(manifests), copy.deepcopy(source_lock)

    def write_catalog(
        self,
        root: Path,
        index: dict,
        manifests: dict[str, dict],
        source_lock: dict,
    ) -> None:
        (root / "config/labs").mkdir(parents=True)
        (root / "config/sources.lock.json").write_text(
            json.dumps(source_lock, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        for entry in index["labs"]:
            path = root / entry["manifest"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(manifests[entry["id"]], indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            entry["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        (root / "config/labs/index.json").write_text(
            json.dumps(index, indent=2) + "\n", encoding="utf-8", newline="\n"
        )

    def test_repository_catalog_is_valid_and_default_is_pci(self) -> None:
        index, _, manifests, digests = MODULE.read_catalog(ROOT)
        self.assertEqual("pci-x86-64", index["default_lab"])
        self.assertEqual({"pci-x86-64", "platform-arm64"}, set(manifests))
        self.assertTrue(all(len(digest) == 64 for digest in digests.values()))

    def test_all_generated_lab_build_roots_are_ignored(self) -> None:
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("\nbuild/\n", ignore)
        self.assertIn("\nbuild-*/\n", ignore)

    def test_setup_handoff_preserves_lab_and_relocated_build_directory(self) -> None:
        text = SETUP.read_text(encoding="utf-8")
        for wrapper in ("inspect.sh", "build.sh", "run.sh", "runtime-test.sh"):
            with self.subTest(wrapper=wrapper):
                self.assertIn(
                    f'"$BUILD_DIR" "$ROOT_DIR/{wrapper}" "$QEMU_EDU_LAB"',
                    text,
                )
        self.assertEqual(text.count("BUILD_DIR=%q %q --lab %q"), 4)
        self.assertNotIn('echo "  Build: $ROOT_DIR/build.sh"', text)

    def test_default_selection_preserves_existing_build_contract(self) -> None:
        selected, manifest, _, _ = MODULE.select_lab(ROOT, None)
        self.assertEqual("pci-x86-64", selected)
        self.assertEqual("build", manifest["build"]["build_dir"])
        self.assertEqual("qemu-edu-x86-64", manifest["build"]["machine"])
        self.assertEqual("qemu-edu-driver", manifest["build"]["driver_target"])
        self.assertEqual(["qemu-edu-image"], manifest["build"]["targets"])

    def test_unknown_lab_fails_closed(self) -> None:
        with self.assertRaisesRegex(MODULE.LabError, "unknown lab"):
            MODULE.select_lab(ROOT, "future-lab")

    def test_unknown_manifest_field_fails_closed(self) -> None:
        _, manifests, _ = self.repository_data()
        manifest = copy.deepcopy(manifests["platform-arm64"])
        manifest["future"] = True
        with self.assertRaisesRegex(MODULE.LabError, "unknown fields"):
            MODULE.validate_manifest(manifest, "platform-arm64")

    def test_boolean_schema_version_is_rejected(self) -> None:
        _, manifests, _ = self.repository_data()
        manifest = copy.deepcopy(manifests["platform-arm64"])
        manifest["schema_version"] = True
        with self.assertRaisesRegex(MODULE.LabError, "unsupported schema_version"):
            MODULE.validate_manifest(manifest, "platform-arm64")

    def test_profile_contract_cannot_be_mixed(self) -> None:
        _, manifests, _ = self.repository_data()
        manifest = copy.deepcopy(manifests["platform-arm64"])
        manifest["emulator"]["system_binary"] = "qemu-system-x86_64"
        with self.assertRaisesRegex(MODULE.LabError, "system_binary"):
            MODULE.validate_manifest(manifest, "platform-arm64")

        manifest = copy.deepcopy(manifests["platform-arm64"])
        manifest["build"]["driver_target"] = "qemu-edu-driver"
        with self.assertRaisesRegex(MODULE.LabError, "driver_target"):
            MODULE.validate_manifest(manifest, "platform-arm64")

    def test_manifest_digest_tampering_is_rejected(self) -> None:
        root, index, manifests, source_lock = self.fixture()
        self.write_catalog(root, index, manifests, source_lock)
        path = root / "config/labs/platform-arm64.json"
        path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        with self.assertRaisesRegex(MODULE.LabError, "SHA-256"):
            MODULE.read_catalog(root)

    def test_manifest_path_traversal_is_rejected(self) -> None:
        root, index, manifests, source_lock = self.fixture()
        index["labs"][0]["manifest"] = "config/labs/../outside.json"
        self.write_catalog(root, index, manifests, source_lock)
        with self.assertRaisesRegex(MODULE.LabError, "normalized"):
            MODULE.read_catalog(root)

    def test_duplicate_build_directory_is_rejected(self) -> None:
        root, index, manifests, source_lock = self.fixture()
        manifests["platform-arm64"]["build"]["build_dir"] = "build"
        self.write_catalog(root, index, manifests, source_lock)
        with self.assertRaisesRegex(MODULE.LabError, "duplicate lab build directory"):
            MODULE.read_catalog(root)

    def test_default_manifest_must_match_source_lock_compatibility_values(self) -> None:
        root, index, manifests, source_lock = self.fixture()
        manifests["pci-x86-64"]["build"]["machine"] = "other-machine"
        self.write_catalog(root, index, manifests, source_lock)
        with self.assertRaisesRegex(MODULE.LabError, "source-lock compatibility"):
            MODULE.read_catalog(root)

    def test_duplicate_json_keys_are_rejected(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "duplicate.json"
        path.write_text('{"schema_version":1,"schema_version":1}\n', encoding="utf-8")
        with self.assertRaisesRegex(MODULE.LabError, "duplicate JSON key"):
            MODULE.read_json(path, "duplicate")

    def test_build_directory_is_limited_to_generated_output_roots(self) -> None:
        _, manifests, _ = self.repository_data()
        for invalid in (
            "downloads",
            "sstate-cache",
            "layers/build",
            "build/platform-arm64",
            "README.md",
        ):
            with self.subTest(build_dir=invalid):
                manifest = copy.deepcopy(manifests["platform-arm64"])
                manifest["build"]["build_dir"] = invalid
                with self.assertRaisesRegex(
                    MODULE.LabError, "top-level build or build-<lab>"
                ):
                    MODULE.validate_manifest(manifest, "platform-arm64")

    def test_manifest_rejects_rendering_and_terminal_control_characters(self) -> None:
        _, manifests, _ = self.repository_data()
        path_injection = copy.deepcopy(manifests["platform-arm64"])
        path_injection["build"]["layers"][0] = 'layers/core";INJECTED="'
        with self.assertRaisesRegex(MODULE.LabError, "unsupported path characters"):
            MODULE.validate_manifest(path_injection, "platform-arm64")

        for description in (
            "unsafe\u001b[31moutput",
            "reversed\u202etext",
            "split\u2028line",
        ):
            with self.subTest(description=repr(description)):
                terminal_control = copy.deepcopy(manifests["platform-arm64"])
                terminal_control["description"] = description
                with self.assertRaisesRegex(MODULE.LabError, "control characters"):
                    MODULE.validate_manifest(terminal_control, "platform-arm64")


if __name__ == "__main__":
    unittest.main()
