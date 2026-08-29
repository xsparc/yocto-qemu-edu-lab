# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "configure_build", ROOT / "scripts/configure_build.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ConfigureBuildTests(unittest.TestCase):
    def manifest(self, lab: str = "pci-x86-64") -> dict:
        return json.loads(
            (ROOT / f"config/labs/{lab}.json").read_text(encoding="utf-8")
        )

    def fixture(
        self,
        local_conf: str = 'CONF_VERSION = "2"\n',
        *,
        sdk: bool = False,
    ) -> tuple[Path, Path]:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        build_dir = (
            root / self.manifest()["development"]["build_dir"]
            if sdk
            else root / "build"
        )
        conf_dir = build_dir / "conf"
        conf_dir.mkdir(parents=True)
        (conf_dir / "local.conf").write_text(local_conf, encoding="utf-8")
        (conf_dir / "bblayers.conf").write_text("old layers\n", encoding="utf-8")
        return root, build_dir

    def test_configure_replaces_layers_with_exact_locked_order(self) -> None:
        root, build_dir = self.fixture()
        data = self.manifest()
        MODULE.configure(root, build_dir, data)
        text = (build_dir / "conf/bblayers.conf").read_text(encoding="utf-8")
        positions = [text.index(layer) for layer in MODULE.expected_layers(root, data)]
        self.assertEqual(sorted(positions), positions)
        self.assertNotIn("old layers", text)

    def test_sdk_configuration_replaces_all_parsed_input_and_pins_workspace(self) -> None:
        root, build_dir = self.fixture('require conf/untrusted.conf\n', sdk=True)
        data = self.manifest()
        workspace = build_dir / "workspace"
        MODULE.configure_sdk(root, build_dir, data, workspace=workspace)
        self.assertEqual(
            MODULE.render_sdk_local_conf(data),
            (build_dir / "conf/local.conf").read_text(encoding="utf-8"),
        )
        self.assertEqual(
            MODULE.render_sdk_bblayers(root, data, workspace=workspace),
            (build_dir / "conf/bblayers.conf").read_text(encoding="utf-8"),
        )
        sdk_layers = (build_dir / "conf/bblayers.conf").read_text(encoding="utf-8")
        self.assertIn(
            f'BBPATH = "{MODULE.sdk_configuration_root(root, data)}"',
            sdk_layers,
        )
        self.assertNotIn('BBPATH = "${TOPDIR}"', sdk_layers)
        self.assertNotIn('BBPATH = ""', sdk_layers)
        configuration_root = MODULE.sdk_configuration_root(root, data)
        self.assertEqual(
            MODULE.render_sdk_local_conf(data),
            (configuration_root / "conf/local.conf").read_text(encoding="utf-8"),
        )
        self.assertFalse((configuration_root / "lib/devtool").exists())

    def test_sdk_configuration_rejects_automatic_side_configuration(self) -> None:
        for name in MODULE.AUTOMATIC_BUILD_CONFIGURATION:
            with self.subTest(name=name):
                root, build_dir = self.fixture(sdk=True)
                (build_dir / f"conf/{name}").write_text(
                    'BBPATH = "/tmp/untrusted"\n', encoding="utf-8"
                )
                with self.assertRaisesRegex(MODULE.ConfigurationError, name):
                    MODULE.configure_sdk(root, build_dir, self.manifest())
                self.assertEqual(
                    "old layers\n",
                    (build_dir / "conf/bblayers.conf").read_text(encoding="utf-8"),
                )

    @unittest.skipUnless(os.name == "posix", "symlink contract requires POSIX")
    def test_sdk_configuration_rejects_symlinked_automatic_configuration(self) -> None:
        for name in MODULE.AUTOMATIC_BUILD_CONFIGURATION:
            with self.subTest(name=name):
                root, build_dir = self.fixture(sdk=True)
                outside = root / f"outside-{name}"
                outside.write_text('BBPATH = "/tmp/untrusted"\n', encoding="utf-8")
                (build_dir / f"conf/{name}").symlink_to(outside)
                with self.assertRaisesRegex(MODULE.ConfigurationError, name):
                    MODULE.configure_sdk(root, build_dir, self.manifest())
                self.assertEqual(
                    "old layers\n",
                    (build_dir / "conf/bblayers.conf").read_text(encoding="utf-8"),
                )

    def test_sdk_configuration_rejects_unexpected_bbpath_root_state(self) -> None:
        root, build_dir = self.fixture(sdk=True)
        data = self.manifest()
        override = MODULE.sdk_configuration_root(root, data) / "lib/devtool"
        override.mkdir(parents=True)
        (override / "deploy.py").write_text("raise RuntimeError\n", encoding="utf-8")
        with self.assertRaisesRegex(MODULE.ConfigurationError, "unexpected state"):
            MODULE.configure_sdk(root, build_dir, data)
        self.assertEqual(
            "old layers\n",
            (build_dir / "conf/bblayers.conf").read_text(encoding="utf-8"),
        )

    def test_managed_local_values_are_last(self) -> None:
        data = self.manifest()
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
            MODULE.configure(root, build_dir, self.manifest())
        self.assertEqual(
            "old layers\n",
            (build_dir / "conf/bblayers.conf").read_text(encoding="utf-8"),
        )

    def test_reversed_managed_markers_are_rejected(self) -> None:
        data = self.manifest()
        with self.assertRaisesRegex(MODULE.ConfigurationError, "invalid managed block"):
            MODULE.render_local_conf(f"{MODULE.END}\n{MODULE.START}\n", data)

    def test_managed_local_uses_explicit_development_image_features(self) -> None:
        rendered = MODULE.render_local_conf('CONF_VERSION = "2"\n', self.manifest())
        self.assertNotIn("debug-tweaks", rendered)
        for feature in (
            "allow-empty-password",
            "allow-root-login",
            "empty-root-password",
            "post-install-logging",
        ):
            self.assertIn(feature, rendered)

    def test_effective_values_reject_extra_or_reordered_layers(self) -> None:
        root, _ = self.fixture()
        data = self.manifest()
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
        data = self.manifest()
        errors = MODULE.effective_errors(
            root,
            data,
            distro="poky",
            machine="other",
            bblayers=" ".join(MODULE.expected_layers(root, data)),
        )
        self.assertTrue(any("MACHINE resolved" in error for error in errors))

    def test_sdk_effective_values_require_closed_nonempty_bbpath(self) -> None:
        data = self.manifest()
        root, build_dir = self.fixture(sdk=True)
        configuration_path = Path("/repository/build-sdk/.qemu-edu-config")
        configuration_root = str(configuration_path)
        layers = ["/repository/layers/core", "/repository/meta-qemu-edu"]
        with (
            patch.object(MODULE, "expected_layers", return_value=layers),
            patch.object(
                MODULE,
                "sdk_configuration_root",
                return_value=configuration_path,
            ),
        ):
            self.assertEqual(
                [],
                MODULE.sdk_effective_errors(
                    root,
                    data,
                    build_dir=build_dir,
                    distro=data["build"]["distro"],
                    machine=data["build"]["machine"],
                    bblayers=" ".join(layers),
                    bbpath=os.pathsep.join(
                        [layers[0], configuration_root, layers[1]]
                    ),
                ),
            )
            for bbpath in (
                os.pathsep + os.pathsep.join(layers),
                os.pathsep.join([str(build_dir), *layers]),
                os.pathsep.join([configuration_root, str(build_dir), *layers]),
                os.pathsep.join([configuration_root, "/tmp/undeclared", *layers]),
                os.pathsep.join(
                    [configuration_root, *layers, configuration_root]
                ),
            ):
                with self.subTest(bbpath=bbpath):
                    self.assertTrue(
                        MODULE.sdk_effective_errors(
                            root,
                            data,
                            build_dir=build_dir,
                            distro=data["build"]["distro"],
                            machine=data["build"]["machine"],
                            bblayers=" ".join(layers),
                            bbpath=bbpath,
                        )
                    )

    def test_arm_manifest_selects_independent_machine_and_same_layer_order(self) -> None:
        root, build_dir = self.fixture()
        data = self.manifest("platform-arm64")
        MODULE.configure(root, build_dir, data)
        local = (build_dir / "conf/local.conf").read_text(encoding="utf-8")
        layers = (build_dir / "conf/bblayers.conf").read_text(encoding="utf-8")
        self.assertIn('MACHINE = "qemu-edu-platform-arm64"', local)
        positions = [layers.index(layer) for layer in MODULE.expected_layers(root, data)]
        self.assertEqual(sorted(positions), positions)


if __name__ == "__main__":
    unittest.main()
