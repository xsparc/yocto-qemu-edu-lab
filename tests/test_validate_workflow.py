# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_workflow", ROOT / "scripts/validate_workflow.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class WorkflowValidationTests(unittest.TestCase):
    def copy_repository(self) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        destination = Path(temporary.name) / "repository"
        shutil.copytree(
            ROOT,
            destination,
            ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"),
        )
        return destination

    def test_repository_workflow_is_valid(self) -> None:
        self.assertEqual([], MODULE.validate(ROOT))

    def test_task_ids_are_unique(self) -> None:
        state = MODULE.load_toml(ROOT / ".agents/tasks.toml")
        ids = [task["id"] for task in state["tasks"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_only_one_task_is_in_progress(self) -> None:
        state = MODULE.load_toml(ROOT / ".agents/tasks.toml")
        active = [task["id"] for task in state["tasks"] if task["status"] == "In Progress"]
        self.assertLessEqual(len(active), 1)

    def test_missing_approval_is_rejected(self) -> None:
        root = self.copy_repository()
        path = root / ".agents/tasks.toml"
        text = path.read_text(encoding="utf-8")
        text = text.replace(
            'approval = "Repository owner /goal request on 2026-08-07 explicitly requested this planning, licensing, documentation, autonomous workflow, and milestone PR scope."',
            'approval = ""',
            1,
        )
        path.write_text(text, encoding="utf-8")
        self.assertIn("A000 is executable without approval evidence", MODULE.validate(root))

    def test_unknown_dependency_is_reported_without_crashing(self) -> None:
        root = self.copy_repository()
        path = root / ".agents/tasks.toml"
        text = path.read_text(encoding="utf-8").replace(
            'dependencies = ["A000"]', 'dependencies = ["A999"]', 1
        ).replace('status = "Proposed"', 'status = "Ready"', 1).replace(
            'approval = ""', 'approval = "Test approval"', 1
        )
        path.write_text(text, encoding="utf-8")
        errors = MODULE.validate(root)
        self.assertIn("A001 has unknown dependency: A999", errors)

    def test_ledger_status_drift_is_rejected(self) -> None:
        root = self.copy_repository()
        path = root / ".agents/ledger.md"
        text = path.read_text(encoding="utf-8").replace(
            "| A000 | M0 | In Progress |", "| A000 | M0 | Ready |", 1
        )
        path.write_text(text, encoding="utf-8")
        self.assertIn("ledger is missing A000", MODULE.validate(root))

    def test_done_task_requires_every_review_category(self) -> None:
        root = self.copy_repository()
        tasks_path = root / ".agents/tasks.toml"
        text = tasks_path.read_text(encoding="utf-8")
        text = text.replace('status = "In Progress"', 'status = "Done"', 1)
        text = text.replace(
            'reviews_completed = ["architecture", "documentation", "independent-diff", "licensing", "quality"]',
            'reviews_completed = ["quality"]',
            1,
        )
        text = text.replace(
            "validation_evidence = []", 'validation_evidence = ["tests passed"]', 1
        )
        text = text.replace(
            "review_evidence = []", 'review_evidence = ["quality reviewed"]', 1
        )
        text = text.replace('result = ""', 'result = "complete"', 1)
        tasks_path.write_text(text, encoding="utf-8")
        ledger_path = root / ".agents/ledger.md"
        ledger_path.write_text(
            ledger_path.read_text(encoding="utf-8").replace(
                "| A000 | M0 | In Progress |", "| A000 | M0 | Done |", 1
            ),
            encoding="utf-8",
        )
        errors = MODULE.validate(root)
        self.assertIn(
            "A000 is Done without completed reviews: architecture, documentation, independent-diff, licensing",
            errors,
        )


if __name__ == "__main__":
    unittest.main()
