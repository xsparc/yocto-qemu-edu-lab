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
            "src_uri": f"file://powerpc_rom.bin file://{MODULE.PATCH_NAME}",
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

    def test_metadata_selection_and_dependency_chain_pass(self) -> None:
        arguments = self.metadata_arguments(ROOT)
        result = MODULE.metadata_checks(**arguments)
        self.assertTrue(result["selected"])
        self.assertTrue(result["testimage_dependency_verified"])

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


if __name__ == "__main__":
    unittest.main()
