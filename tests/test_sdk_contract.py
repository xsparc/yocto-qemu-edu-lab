# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
import json
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RECIPE = (
    ROOT
    / "meta-qemu-edu/recipes-support/qemu-edu-sdk-sample/"
    "qemu-edu-sdk-sample_1.0.bb"
)
SOURCE = (
    ROOT
    / "meta-qemu-edu/recipes-support/qemu-edu-sdk-sample/files/"
    "qemu-edu-sdk-sample.c"
)
IMAGE = ROOT / "meta-qemu-edu/recipes-core/images/qemu-edu-image.bb"


class SdkFoundationContractTests(unittest.TestCase):
    def manifests(self) -> dict[str, dict]:
        index = json.loads(
            (ROOT / "config/labs/index.json").read_text(encoding="utf-8")
        )
        return {
            entry["id"]: json.loads(
                (ROOT / entry["manifest"]).read_text(encoding="utf-8")
            )
            for entry in index["labs"]
        }

    def test_sample_recipe_is_mit_libc_only_and_dual_lab_compatible(self) -> None:
        recipe = RECIPE.read_text(encoding="utf-8")
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn('LICENSE = "MIT"', recipe)
        self.assertIn('SRC_URI = "file://qemu-edu-sdk-sample.c"', recipe)
        self.assertIn('${CC} ${CFLAGS} ${CPPFLAGS}', recipe)
        self.assertIn('${LDFLAGS}', recipe)
        self.assertIn('install -m 0755', recipe)
        self.assertIn(
            'COMPATIBLE_MACHINE = "^(qemu-edu-x86-64|qemu-edu-platform-arm64)$"',
            recipe,
        )
        self.assertNotRegex(recipe, r"(?m)^\s*(?:R?DEPENDS|RRECOMMENDS)")
        self.assertEqual(1, source.count("#include"))
        self.assertIn("#include <stdio.h>", source)
        self.assertIn('puts("qemu-edu-sdk-sample baseline")', source)

    def test_recipe_license_checksum_matches_lf_source_header(self) -> None:
        recipe = RECIPE.read_text(encoding="utf-8")
        selected = SOURCE.read_bytes().splitlines(keepends=True)[0]
        marker = b"/* SPDX-License-" b"Identifier: MIT */\n"
        self.assertEqual(marker, selected)
        checksum = hashlib.md5(selected, usedforsecurity=False).hexdigest()
        self.assertIn(f"md5={checksum}", recipe)
        attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
        self.assertIn("*.c text eol=lf", attributes)
        self.assertIn("*.bb text eol=lf", attributes)

    def test_sample_is_declared_but_absent_from_both_base_images(self) -> None:
        image = IMAGE.read_text(encoding="utf-8")
        self.assertNotIn("qemu-edu-sdk-sample", image)
        for lab_id, manifest in self.manifests().items():
            with self.subTest(lab=lab_id):
                self.assertEqual(3, manifest["schema_version"])
                development = manifest["development"]
                self.assertEqual("qemu-edu-sdk-sample", development["recipe"])
                self.assertEqual(
                    "learner-source/qemu-edu-sdk-sample",
                    development["source_dir"],
                )
                self.assertEqual(
                    "/usr/bin/qemu-edu-sdk-sample",
                    development["guest_binary"],
                )
                self.assertIn(
                    development["recipe"],
                    manifest["supply_chain"]["forbidden_packages"],
                )

    def test_a009_authority_and_version_are_explicit(self) -> None:
        self.assertEqual("0.8.0-dev\n", (ROOT / "VERSION").read_text(encoding="utf-8"))
        state = tomllib.loads(
            (ROOT / "docs/maintainers/tasks.toml").read_text(encoding="utf-8")
        )
        task = next(item for item in state["tasks"] if item["id"] == "A009")
        self.assertEqual("In Progress", task["status"])
        self.assertEqual("M8", task["milestone"])
        self.assertIn("explicitly approved A009/M8", task["approval"])
        decisions = (ROOT / "docs/maintainers/decisions.md").read_text(
            encoding="utf-8"
        )
        self.assertRegex(decisions, r"(?m)^## D-019: Isolate direct-eSDK iteration")
        roadmap = (ROOT / "docs/roadmap.md").read_text(encoding="utf-8")
        self.assertRegex(roadmap, r"(?m)^## M8 — Isolated direct-eSDK")

    def test_metadata_lane_verifies_locked_tools_and_sample_for_both_labs(self) -> None:
        workflow = (ROOT / ".github/workflows/yocto-metadata.yml").read_text(
            encoding="utf-8"
        )
        self.assertEqual(2, workflow.count('--repo "$GITHUB_WORKSPACE" verify'))
        self.assertEqual(
            2,
            workflow.count(
                'scripts/sdk_tooling.py" \\\n'
                '            --repo "$GITHUB_WORKSPACE" metadata \\\n'
                "            --lab"
            ),
        )
        for lab_id in ("pci-x86-64", "platform-arm64"):
            self.assertIn(f"--lab {lab_id}", workflow)
        for variable in ("PN", "PV", "LICENSE", "COMPATIBLE_MACHINE", "FILE"):
            self.assertEqual(
                2,
                workflow.count(
                    f"bitbake-getvar --value --recipe qemu-edu-sdk-sample {variable}"
                ),
            )


if __name__ == "__main__":
    unittest.main()
