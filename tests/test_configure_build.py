# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "configure_build", ROOT / "scripts/configure_build.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ConfigureBuildTests(unittest.TestCase):
    def lock(self) -> dict:
        return json.loads((ROOT / "config/sources.lock.json").read_text(encoding="utf-8"))

    def fixture(self, local_conf: str = 'CONF_VERSION = "2"\n') -> tuple[Path, Path]:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        build_dir = root / "build"
        conf_dir = build_dir / "conf"
        conf_dir.mkdir(parents=True)
        (conf_dir / "local.conf").write_text(local_conf, encoding="utf-8")
        (conf_dir / "bblayers.conf").write_text("old layers\n", encoding="utf-8")
        return root, build_dir

    def test_configure_replaces_layers_with_exact_locked_order(self) -> None:
        root, build_dir = self.fixture()
        data = self.lock()
        MODULE.configure(root, build_dir, data)
        text = (build_dir / "conf/bblayers.conf").read_text(encoding="utf-8")
        positions = [text.index(layer) for layer in MODULE.expected_layers(root, data)]
        self.assertEqual(sorted(positions), positions)
        self.assertNotIn("old layers", text)

    def test_managed_local_values_are_last(self) -> None:
        data = self.lock()
        old = f'''CONF_VERSION = "2"
{MODULE.START}
DISTRO = "old"
MACHINE = "old"
{MODULE.END}
MACHINE = "experimental"
'''
        rendered = MODULE.render_local_conf(old, data)
        self.assertLess(rendered.index('MACHINE = "experimental"'), rendered.rindex('MACHINE = "qemu-edu-x86-64"'))
        self.assertTrue(rendered.rstrip().endswith(MODULE.END))

    def test_invalid_managed_blocks_do_not_rewrite_bblayers(self) -> None:
        root, build_dir = self.fixture(f"{MODULE.START}\n{MODULE.START}\n{MODULE.END}\n")
        with self.assertRaisesRegex(MODULE.ConfigurationError, "invalid managed block"):
            MODULE.configure(root, build_dir, self.lock())
        self.assertEqual(
            "old layers\n",
            (build_dir / "conf/bblayers.conf").read_text(encoding="utf-8"),
        )

    def test_reversed_managed_markers_are_rejected(self) -> None:
        data = self.lock()
        with self.assertRaisesRegex(MODULE.ConfigurationError, "invalid managed block"):
            MODULE.render_local_conf(f"{MODULE.END}\n{MODULE.START}\n", data)

    def test_effective_values_reject_extra_or_reordered_layers(self) -> None:
        root, _ = self.fixture()
        data = self.lock()
        layers = MODULE.expected_layers(root, data)
        self.assertEqual(
            [],
            MODULE.effective_errors(
                root,
                data,
                distro="poky",
                machine="qemu-edu-x86-64",
                bblayers=" ".join(layers),
            ),
        )
        errors = MODULE.effective_errors(
            root,
            data,
            distro="poky",
            machine="qemu-edu-x86-64",
            bblayers=" ".join(reversed(layers)) + " /extra",
        )
        self.assertTrue(any("locked order" in error for error in errors))

    def test_effective_values_reject_machine_override(self) -> None:
        root, _ = self.fixture()
        data = self.lock()
        errors = MODULE.effective_errors(
            root,
            data,
            distro="poky",
            machine="other",
            bblayers=" ".join(MODULE.expected_layers(root, data)),
        )
        self.assertTrue(any("MACHINE resolved" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
