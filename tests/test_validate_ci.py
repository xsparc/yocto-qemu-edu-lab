# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_ci", ROOT / "scripts/validate_ci.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


SAFE = """name: Test
on: [pull_request]
permissions:
  contents: read
jobs:
  test:
    timeout-minutes: 5
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd
        with:
          fetch-depth: 0
          persist-credentials: false
"""


class CiValidationTests(unittest.TestCase):
    def workflow(self, text: str) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "workflow.yml"
        path.write_text(text, encoding="utf-8")
        return path

    def test_repository_workflows_are_safe(self) -> None:
        self.assertEqual([], MODULE.validate(ROOT))

    def test_metadata_inputs_must_trigger_both_hosted_runs(self) -> None:
        text = (ROOT / ".github/workflows/yocto-metadata.yml").read_text(
            encoding="utf-8"
        )
        self.assertEqual([], MODULE.validate_metadata_paths(text))
        errors = MODULE.validate_metadata_paths(
            text.replace('      - "scripts/configure_build.py"\n', "", 1)
        )
        self.assertTrue(any("pull_request paths omit" in error for error in errors))
        errors = MODULE.validate_metadata_paths(
            text.replace('      - "scripts/verify_qemu_security.py"\n', "", 1)
        )
        self.assertTrue(any("pull_request paths omit" in error for error in errors))
        errors = MODULE.validate_metadata_paths(
            text.replace('      - "scripts/qemu_security_preflight.sh"\n', "", 1)
        )
        self.assertTrue(any("pull_request paths omit" in error for error in errors))

    def test_full_action_sha_is_required(self) -> None:
        path = self.workflow(SAFE.replace(
            "de0fac2e4500dabe0009e67214ff5f5447ce83dd", "v6"
        ))
        errors = MODULE.validate_workflow(path)
        self.assertTrue(any("full commit SHA" in error for error in errors))

    def test_checkout_credentials_must_not_persist(self) -> None:
        path = self.workflow(SAFE.replace("persist-credentials: false", "persist-credentials: true"))
        self.assertIn(
            "Checkout must set persist-credentials: false",
            MODULE.validate_workflow(path),
        )

    def test_privileged_triggers_and_secrets_are_rejected(self) -> None:
        path = self.workflow(SAFE.replace(
            "on: [pull_request]", "on:\n  pull_request_target:\n"
        ) + "# ${{ secrets.DEPLOY_KEY }}\n")
        errors = MODULE.validate_workflow(path)
        self.assertTrue(any("privileged context" in error for error in errors))
        self.assertTrue(any("repository secrets" in error for error in errors))

    def test_bracket_form_secret_is_rejected(self) -> None:
        path = self.workflow(SAFE + "# ${{ secrets['TOKEN'] }}\n")
        self.assertTrue(
            any("repository secrets" in error for error in MODULE.validate_workflow(path))
        )

    def test_extra_top_level_read_permission_is_rejected(self) -> None:
        path = self.workflow(SAFE.replace(
            "  contents: read\n", "  contents: read\n  issues: read\n"
        ))
        self.assertIn(
            "top-level permissions must contain only 'contents: read'",
            MODULE.validate_workflow(path),
        )

    def test_job_level_permissions_are_rejected(self) -> None:
        path = self.workflow(SAFE.replace(
            "    steps:\n", "    permissions: {contents: write}\n    steps:\n"
        ))
        errors = MODULE.validate_workflow(path)
        self.assertIn("job test must not override permissions", errors)

    def test_every_job_requires_timeout(self) -> None:
        path = self.workflow(SAFE.replace("    timeout-minutes: 5\n", ""))
        self.assertIn("job test has no positive timeout-minutes", MODULE.validate_workflow(path))


if __name__ == "__main__":
    unittest.main()
