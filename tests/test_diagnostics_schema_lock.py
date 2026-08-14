# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_diagnostics_schema_lock",
    ROOT / "scripts/verify_diagnostics_schema_lock.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class DiagnosticsSchemaLockTests(unittest.TestCase):
    def test_repository_lock_is_exact_and_test_only(self) -> None:
        lock = MODULE.load(ROOT / MODULE.LOCK_PATH)
        self.assertFalse(lock["runtime_dependency"])
        self.assertEqual(6, len(lock["packages"]))
        self.assertTrue(all(item["size"] <= MODULE.MAXIMUM_WHEEL_BYTES for item in lock["packages"]))
        self.assertEqual({"MIT", "PSF-2.0"}, {item["license_expression"] for item in lock["packages"]})

    def test_tampered_url_digest_dependency_and_license_fail(self) -> None:
        original = json.loads((ROOT / MODULE.LOCK_PATH).read_text(encoding="utf-8"))
        mutations = (
            ("url", "https://files.pythonhosted.org/packages/changed.whl"),
            ("sha256", "0" * 64),
            ("dependencies", ["surprise>=1"]),
            ("license_sha256", "1" * 64),
        )
        for key, value in mutations:
            with self.subTest(key=key), tempfile.TemporaryDirectory() as temporary:
                changed = copy.deepcopy(original)
                changed["packages"][0][key] = value
                path = Path(temporary) / "lock.json"
                path.write_text(json.dumps(changed), encoding="utf-8")
                with self.assertRaises(MODULE.LockError):
                    MODULE.load(path)

    def test_literal_spdx_fixture_does_not_confuse_reuse(self) -> None:
        marker = b"# SPDX-License-" b"Identifier: MIT\n"
        self.assertTrue(marker.startswith(b"# SPDX-"))

    def test_workflow_uses_only_locked_urls_and_install_options(self) -> None:
        lock = MODULE.load(ROOT / MODULE.LOCK_PATH)
        workflow = (ROOT / ".github/workflows/fast-checks.yml").read_text(encoding="utf-8")
        for package in lock["packages"]:
            self.assertEqual(1, workflow.count(package["url"]))
            output_argument = '--output "$wheel_root/' + package["filename"] + '"'
            self.assertIn(output_argument, workflow)
        for option in lock["installation"]["required_options"]:
            self.assertIn(option, workflow)
        self.assertNotIn("pip download", workflow)
        self.assertNotIn("--index-url", workflow)
        self.assertEqual(6, workflow.count('--max-filesize "$MAX_WHEEL_BYTES"'))


if __name__ == "__main__":
    unittest.main()
