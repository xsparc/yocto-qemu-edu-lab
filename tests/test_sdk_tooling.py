# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "sdk_tooling_contract", ROOT / "scripts/sdk_tooling.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SdkToolingTests(unittest.TestCase):
    def source_fixture(self) -> tuple[tempfile.TemporaryDirectory, dict[str, Path]]:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        sources = {
            "bitbake": root / "layers/bitbake",
            "openembedded-core": root / "layers/openembedded-core",
        }
        (sources["bitbake"] / "lib").mkdir(parents=True)
        for source_id, files in MODULE.SOURCE_INTERFACES.items():
            for relative, literals in files.items():
                path = sources[source_id] / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    "TOKENS = " + repr(tuple(sorted(literals))) + "\n",
                    encoding="utf-8",
                    newline="\n",
                )
        return temporary, sources

    def test_locked_source_interfaces_are_closed_and_parseable(self) -> None:
        _temporary, sources = self.source_fixture()
        MODULE.verify_source_interfaces(sources)
        standard = sources["openembedded-core"] / "scripts/lib/devtool/standard.py"
        standard.write_text("TOKENS = ('modify',)\n", encoding="utf-8")
        with self.assertRaisesRegex(MODULE.SdkToolingError, "incompatible"):
            MODULE.verify_source_interfaces(sources)

    def test_locked_source_interface_rejects_oversized_and_non_file_inputs(self) -> None:
        _temporary, sources = self.source_fixture()
        devtool = sources["openembedded-core"] / "scripts/devtool"
        devtool.write_bytes(b"x" * (MODULE.MAX_TOOL_SOURCE_BYTES + 1))
        with self.assertRaisesRegex(MODULE.SdkToolingError, "byte bound"):
            MODULE.verify_source_interfaces(sources)
        devtool.unlink()
        devtool.mkdir()
        with self.assertRaisesRegex(MODULE.SdkToolingError, "regular file"):
            MODULE.verify_source_interfaces(sources)

    def test_python_interface_is_exact_and_rejects_non_directory_state(self) -> None:
        _temporary, sources = self.source_fixture()
        expected = (sources["bitbake"] / "lib").resolve()
        self.assertEqual(expected, MODULE.verify_python_interface(sources))
        expected.rmdir()
        expected.write_text("not a library directory\n", encoding="utf-8")
        with self.assertRaisesRegex(MODULE.SdkToolingError, "Python library"):
            MODULE.verify_python_interface(sources)

    @unittest.skipIf(os.name != "posix", "executable identity is a native-Linux contract")
    def test_executables_must_resolve_to_locked_regular_files(self) -> None:
        _temporary, sources = self.source_fixture()
        expected: dict[str, Path] = {}
        for command, (source_id, relative) in MODULE.EXECUTABLE_INTERFACES.items():
            path = sources[source_id] / relative
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("#!/bin/sh\n", encoding="utf-8", newline="\n")
            path.chmod(0o755)
            expected[command] = path
        MODULE.verify_executable_interfaces(
            sources, which=lambda command: str(expected[command])
        )
        with self.assertRaisesRegex(MODULE.SdkToolingError, "devtool does not resolve"):
            MODULE.verify_executable_interfaces(
                sources,
                which=lambda command: (
                    "/usr/bin/devtool" if command == "devtool" else str(expected[command])
                ),
            )

    def test_effective_sample_metadata_is_exact_for_both_labs(self) -> None:
        recipe_file = str(
            ROOT
            / "meta-qemu-edu/recipes-support/qemu-edu-sdk-sample/"
            "qemu-edu-sdk-sample_1.0.bb"
        )
        arguments = {
            "pn": MODULE.SDK_RECIPE,
            "pv": MODULE.SDK_RECIPE_VERSION,
            "license_expression": MODULE.SDK_RECIPE_LICENSE,
            "compatible_machine": MODULE.SDK_COMPATIBLE_MACHINE,
            "source_uri": MODULE.SDK_SOURCE_URI,
            "recipe_file": recipe_file,
        }
        for lab_id in MODULE.SDK_LABS:
            with self.subTest(lab=lab_id):
                MODULE.verify_recipe_metadata(ROOT, lab_id, **arguments)
        for field, bad in (
            ("pn", "other"),
            ("pv", "2.0"),
            ("license_expression", "CLOSED"),
            ("compatible_machine", ".*"),
            ("source_uri", "https://example.invalid/source.c"),
            ("recipe_file", "/tmp/other.bb"),
        ):
            with self.subTest(field=field):
                changed = dict(arguments)
                changed[field] = bad
                with self.assertRaisesRegex(MODULE.SdkToolingError, "incompatible"):
                    MODULE.verify_recipe_metadata(ROOT, "pci-x86-64", **changed)

    def test_project_layer_cannot_override_devtool_or_append_the_sample(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            layer = root / "meta-qemu-edu"
            layer.mkdir()
            MODULE.verify_project_layer_authority(root)
            plugin = layer / "lib/devtool/deploy.py"
            plugin.parent.mkdir(parents=True)
            plugin.write_text("raise RuntimeError\n", encoding="utf-8")
            with self.assertRaisesRegex(MODULE.SdkToolingError, "devtool plugins"):
                MODULE.verify_project_layer_authority(root)
            plugin.unlink()
            plugin.parent.rmdir()
            plugin.parent.parent.rmdir()
            append = layer / "recipes-support/sample/qemu-edu-sdk-sample_%.bbappend"
            append.parent.mkdir(parents=True)
            append.write_text('FILESEXTRAPATHS:prepend := "/tmp:"\n', encoding="utf-8")
            with self.assertRaisesRegex(MODULE.SdkToolingError, "append"):
                MODULE.verify_project_layer_authority(root)

    def test_source_lock_requires_every_build_facing_tool_source(self) -> None:
        lock = json.loads(
            (ROOT / "config/sources.lock.json").read_text(encoding="utf-8")
        )
        required = {
            source["id"]: set(source["required_paths"])
            for source in lock["sources"]
        }
        for command, (source_id, relative) in MODULE.EXECUTABLE_INTERFACES.items():
            with self.subTest(command=command):
                self.assertIn(relative, required[source_id])
        for source_id, files in MODULE.SOURCE_INTERFACES.items():
            self.assertLessEqual(set(files), required[source_id])


if __name__ == "__main__":
    unittest.main()
