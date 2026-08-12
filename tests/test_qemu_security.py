# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import importlib.util
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_qemu_security", ROOT / "scripts/verify_qemu_security.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class QemuSecurityTests(unittest.TestCase):
    def repository_copy(self) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / "repository"
        shutil.copytree(ROOT / "meta-qemu-edu", root / "meta-qemu-edu")
        return root

    def source_tree(self) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / "qemu"
        source = root / "hw/misc/edu.c"
        source.parent.mkdir(parents=True)
        source.write_text(
            """static bool edu_check_range(void)
{
    if (ok) {
        return true;
    }
    return false;
}

static void edu_dma_timer(void)
{
    if (edu_check_range(dst, edu->dma.cnt, DMA_START, DMA_SIZE)) {
        pci_dma_read(&edu->pdev, guest, edu->dma_buf + dst, edu->dma.cnt);
    }
    if (edu_check_range(src, edu->dma.cnt, DMA_START, DMA_SIZE)) {
        pci_dma_write(&edu->pdev, guest, edu->dma_buf + src, edu->dma.cnt);
    }
}
""",
            encoding="utf-8",
        )
        return root

    def platform_source_tree(self) -> tuple[Path, dict[str, str]]:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / "qemu"
        texts = {path: f"reviewed {path}\n" for path in MODULE.PLATFORM_CHANGED_PATHS}
        texts["hw/misc/qemu_edu_platform.c"] = """TYPE_QEMU_EDU_PLATFORM
QEMU_EDU_PLATFORM_MMIO_SIZE
QEMU_EDU_PLATFORM_IRQ_RAISE_REG
QEMU_EDU_PLATFORM_IRQ_ACK_REG
TYPE_DYNAMIC_SYS_BUS_DEVICE
"""
        texts["include/hw/misc/qemu_edu_platform.h"] = """TYPE_QEMU_EDU_PLATFORM
QEMU_EDU_PLATFORM_MMIO_SIZE
"""
        for relative, text in texts.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        digests = {
            relative: MODULE.canonical_text_digest(text)
            for relative, text in texts.items()
        }
        return root, digests

    def metadata_arguments(self, root: Path) -> dict[str, str | Path]:
        append = (root / MODULE.APPEND_RELATIVE).resolve().as_posix()
        return {
            "root": root,
            "show_appends": f"=== qemu-system-native_10.2.0.bb ===\n  {append}\n",
            "pn": "qemu-system-native",
            "pv": "10.2.0",
            "recipe_file": (
                "/work/repo/layers/openembedded-core/meta/recipes-devtools/"
                "qemu/qemu-system-native_10.2.0.bb"
            ),
            "src_uri": (
                f"file://powerpc_rom.bin file://{MODULE.PATCH_NAME} "
                f"file://{MODULE.PLATFORM_PATCH_NAME}"
            ),
            "testimage_depends": (
                "qemu-native:do_populate_sysroot "
                "qemu-helper-native:do_populate_sysroot "
                "qemu-helper-native:do_addto_recipe_sysroot"
            ),
            "helper_depends": "glib-2.0-native qemu-system-native pseudo-native",
        }

    def test_repository_static_integration_passes(self) -> None:
        result = MODULE.static_checks(ROOT)
        self.assertEqual("static", result["check"])
        self.assertEqual(MODULE.UPSTREAM_COMMIT, result["upstream_commit"])
        self.assertRegex(result["patch_sha256"], r"^[0-9a-f]{64}$")

    def test_static_check_rejects_wildcard_or_duplicate_append(self) -> None:
        root = self.repository_copy()
        extra = (
            root
            / "meta-qemu-edu/recipes-devtools/qemu/qemu-system-native_%.bbappend"
        )
        extra.write_text("# unexpected\n", encoding="utf-8")
        with self.assertRaisesRegex(MODULE.VerificationError, "one exact 10.2.0"):
            MODULE.static_checks(root)

    def test_static_check_rejects_changed_upstream_identity(self) -> None:
        root = self.repository_copy()
        patch = root / MODULE.PATCH_RELATIVE
        text = patch.read_text(encoding="utf-8")
        patch.write_text(
            text.replace(MODULE.UPSTREAM_COMMIT, "0" * 40), encoding="utf-8"
        )
        with self.assertRaisesRegex(MODULE.VerificationError, "commit header"):
            MODULE.static_checks(root)

    def test_static_check_rejects_unscoped_or_wrong_machine_append(self) -> None:
        cases = {
            "unconditional": (
                "# SPDX-License-" "Identifier: MIT\n\n"
                'FILESEXTRAPATHS:prepend := "${THISDIR}/files:"\n\n'
                f'SRC_URI:append = " file://{MODULE.PATCH_NAME}"\n'
            ),
            "wrong machine": MODULE.EXPECTED_APPEND_TEXT.replace(
                MODULE.QEMU_MACHINE, "qemux86-64"
            ),
            "additional global entry": (
                MODULE.EXPECTED_APPEND_TEXT
                + f'\nSRC_URI:append = " file://{MODULE.PATCH_NAME}"\n'
            ),
        }
        for name, append_text in cases.items():
            with self.subTest(name=name):
                root = self.repository_copy()
                (root / MODULE.APPEND_RELATIVE).write_text(
                    append_text, encoding="utf-8"
                )
                with self.assertRaisesRegex(
                    MODULE.VerificationError, "patch-set integration"
                ):
                    MODULE.static_checks(root)

    def test_static_check_rejects_extra_file_or_tampered_hunk(self) -> None:
        for name in ("extra file", "tampered hunk"):
            with self.subTest(name=name):
                root = self.repository_copy()
                patch_path = root / MODULE.PATCH_RELATIVE
                text = patch_path.read_text(encoding="utf-8")
                if name == "extra file":
                    text += (
                        "\ndiff --git a/meson.build b/meson.build\n"
                        "--- a/meson.build\n+++ b/meson.build\n"
                        "@@ -1 +1 @@\n-a\n+b\n"
                    )
                else:
                    text = text.replace(
                        "+    return false;", "+    return true;", 1
                    )
                patch_path.write_text(text, encoding="utf-8")
                with self.assertRaises(MODULE.VerificationError):
                    MODULE.static_checks(root)

    def test_platform_patch_rejects_extra_path_or_tampering(self) -> None:
        for name in ("extra path", "tampered model"):
            with self.subTest(name=name):
                root = self.repository_copy()
                patch_path = root / MODULE.PLATFORM_PATCH_RELATIVE
                text = patch_path.read_text(encoding="utf-8")
                if name == "extra path":
                    text += (
                        "\ndiff --git a/meson.build b/meson.build\n"
                        "--- a/meson.build\n+++ b/meson.build\n"
                        "@@ -1 +1 @@\n-a\n+b\n"
                    )
                else:
                    text = text.replace("0x0100a64e", "0x0100a64f", 1)
                patch_path.write_text(text, encoding="utf-8")
                with self.assertRaises(MODULE.VerificationError):
                    MODULE.static_checks(root)

    def test_metadata_selection_and_dependency_chain_pass(self) -> None:
        arguments = self.metadata_arguments(ROOT)
        result = MODULE.metadata_checks(**arguments)
        self.assertTrue(result["selected"])
        self.assertTrue(result["testimage_dependency_verified"])

    def test_both_profiles_require_the_shared_project_patch_set(self) -> None:
        arguments = self.metadata_arguments(ROOT)
        arguments["profile"] = MODULE.PLATFORM_PROFILE
        result = MODULE.metadata_checks(**arguments)
        self.assertEqual(result["profile"], MODULE.PLATFORM_PROFILE)
        self.assertEqual(result["qemu_machine"], MODULE.PLATFORM_MACHINE)

        arguments["src_uri"] = (
            f"file://powerpc_rom.bin file://{MODULE.PLATFORM_PATCH_NAME}"
        )
        with self.assertRaisesRegex(MODULE.VerificationError, "every project-machine"):
            MODULE.metadata_checks(**arguments)

    def test_metadata_rejects_ambiguous_or_wrong_inputs(self) -> None:
        base = self.metadata_arguments(ROOT)
        cases = {
            "duplicate append": {
                "show_appends": base["show_appends"] + str(base["show_appends"])
            },
            "foreign append": {
                "show_appends": base["show_appends"] + "  /tmp/other.bbappend\n"
            },
            "wrong PN": {"pn": "qemu-native"},
            "wrong PV": {"pv": "10.2.1"},
            "wrong FILE": {"recipe_file": "/tmp/qemu-system-native_10.2.0.bb"},
            "missing patch": {"src_uri": "file://powerpc_rom.bin"},
            "missing platform patch": {
                "src_uri": f"file://powerpc_rom.bin file://{MODULE.PATCH_NAME}"
            },
            "duplicate bounds patch": {
                "src_uri": (
                    str(base["src_uri"]) + f" file://{MODULE.PATCH_NAME}"
                )
            },
            "missing testimage helper": {"testimage_depends": "qemu-native:do_populate_sysroot"},
            "missing system emulator": {"helper_depends": "pseudo-native"},
        }
        for name, changes in cases.items():
            with self.subTest(name=name):
                arguments = dict(base)
                arguments.update(changes)
                with self.assertRaises(MODULE.VerificationError):
                    MODULE.metadata_checks(**arguments)

    def test_patched_source_requires_both_guarded_directions(self) -> None:
        source_tree = self.source_tree()
        source = (source_tree / "hw/misc/edu.c").read_text(encoding="utf-8")
        with patch.object(
            MODULE,
            "EXPECTED_EDU_SOURCE_SHA256",
            MODULE.canonical_text_digest(source),
        ):
            result = MODULE.source_checks(source_tree)
        self.assertTrue(result["source_guard_verified"])

        path = source_tree / "hw/misc/edu.c"
        path.write_text(
            """static bool edu_check_range(void)
{
    return true;
    return false;
}
static void edu_dma_timer(void)
{
    if (edu_check_range(dst, edu->dma.cnt, DMA_START, DMA_SIZE)) {
    }
    if (edu_check_range(src, edu->dma.cnt, DMA_START, DMA_SIZE)) {
    }
    pci_dma_read(&edu->pdev, guest, edu->dma_buf + dst, edu->dma.cnt);
    pci_dma_write(&edu->pdev, guest, edu->dma_buf + src, edu->dma.cnt);
}
""",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(MODULE.VerificationError, "must remain inside"):
            MODULE.source_checks(source_tree)

    def test_source_check_rejects_noncanonical_patched_source(self) -> None:
        with self.assertRaisesRegex(MODULE.VerificationError, "reviewed QEMU 10.2.0"):
            MODULE.source_checks(self.source_tree())

    def test_platform_source_group_is_exact_and_dma_free(self) -> None:
        source_tree, digests = self.platform_source_tree()
        with patch.object(MODULE, "PLATFORM_SOURCE_SHA256", digests):
            result = MODULE.source_checks(source_tree, MODULE.PLATFORM_PROFILE)
        self.assertTrue(result["source_guard_verified"])

        device = source_tree / "hw/misc/qemu_edu_platform.c"
        device.write_text(device.read_text(encoding="utf-8") + "DMA\n", encoding="utf-8")
        updated = dict(digests)
        updated["hw/misc/qemu_edu_platform.c"] = MODULE.canonical_text_digest(
            device.read_text(encoding="utf-8")
        )
        with patch.object(MODULE, "PLATFORM_SOURCE_SHA256", updated):
            with self.assertRaisesRegex(MODULE.VerificationError, "must not expose DMA"):
                MODULE.source_checks(source_tree, MODULE.PLATFORM_PROFILE)

    def test_consumer_requires_native_executable_and_ignores_host_path(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        staging = (root / "recipe-sysroot-native/usr/bin").resolve()
        staging.mkdir(parents=True)
        binary = staging / MODULE.QEMU_BINARY
        binary.write_bytes(b"reviewed-qemu\n")
        binary.chmod(0o755)

        result = MODULE.consumer_checks(staging)
        self.assertTrue(result["runqemu_consumer_verified"])
        self.assertEqual(binary.resolve(), Path(result["qemu_binary"]))

        binary.unlink()
        host = root / "host-bin"
        host.mkdir()
        host_binary = host / MODULE.QEMU_BINARY
        host_binary.write_bytes(b"unreviewed-host-qemu\n")
        host_binary.chmod(0o755)
        with patch.dict(os.environ, {"PATH": str(host)}):
            with self.assertRaisesRegex(
                MODULE.VerificationError, "host fallback prohibited"
            ):
                MODULE.consumer_checks(staging)

    def test_platform_consumer_requires_native_aarch64_binary(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        staging = (Path(temporary.name) / "recipe-sysroot-native/usr/bin").resolve()
        staging.mkdir(parents=True)
        binary = staging / "qemu-system-aarch64"
        binary.write_bytes(b"reviewed-platform-qemu\n")
        binary.chmod(0o755)
        result = MODULE.consumer_checks(staging, MODULE.PLATFORM_PROFILE)
        self.assertEqual(Path(result["qemu_binary"]), binary.resolve())


if __name__ == "__main__":
    unittest.main()
