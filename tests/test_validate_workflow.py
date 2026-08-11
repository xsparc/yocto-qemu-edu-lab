# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import importlib.util
import json
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


def lab_build_roots() -> set[str]:
    roots = set()
    for manifest in (ROOT / "config/labs").glob("*.json"):
        if manifest.name == "index.json":
            continue
        data = json.loads(manifest.read_text(encoding="utf-8"))
        roots.add(Path(data["build"]["build_dir"]).parts[0])
    return roots


class WorkflowValidationTests(unittest.TestCase):
    def copy_repository(self) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        destination = Path(temporary.name) / "repository"
        shutil.copytree(
            ROOT,
            destination,
            ignore=shutil.ignore_patterns(
                ".git",
                "__pycache__",
                "*.pyc",
                "downloads",
                "layers",
                "poky",
                "sstate-cache",
                *sorted(lab_build_roots()),
            ),
        )
        return destination

    def test_repository_copy_excludes_every_lab_build_root(self) -> None:
        self.assertEqual({"build", "build-platform-arm64"}, lab_build_roots())

    def replace_in_task(
        self, text: str, task_id: str, old: str, new: str
    ) -> str:
        marker = f'[[tasks]]\nid = "{task_id}"'
        start = text.index(marker)
        end = text.find("\n[[tasks]]", start + len(marker))
        if end == -1:
            end = len(text)
        block = text[start:end]
        replaced = block.replace(old, new, 1)
        self.assertNotEqual(block, replaced)
        return text[:start] + replaced + text[end:]

    def test_repository_workflow_is_valid(self) -> None:
        self.assertEqual([], MODULE.validate(ROOT))

    def test_task_ids_are_unique(self) -> None:
        state = MODULE.load_toml(ROOT / "docs/maintainers/tasks.toml")
        ids = [task["id"] for task in state["tasks"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_only_one_task_is_in_progress(self) -> None:
        state = MODULE.load_toml(ROOT / "docs/maintainers/tasks.toml")
        active = [task["id"] for task in state["tasks"] if task["status"] == "In Progress"]
        self.assertLessEqual(len(active), 1)

    def test_missing_approval_is_rejected(self) -> None:
        root = self.copy_repository()
        path = root / "docs/maintainers/tasks.toml"
        text = path.read_text(encoding="utf-8")
        text = text.replace(
            'approval = "Repository owner request on 2026-08-07 explicitly authorized this planning, licensing, documentation, maintenance workflow, and milestone pull-request scope."',
            'approval = ""',
            1,
        )
        path.write_text(text, encoding="utf-8")
        self.assertIn("A000 is executable without approval evidence", MODULE.validate(root))

    def test_unknown_dependency_is_reported_without_crashing(self) -> None:
        root = self.copy_repository()
        path = root / "docs/maintainers/tasks.toml"
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
        state = MODULE.load_toml(root / "docs/maintainers/tasks.toml")
        task = state["tasks"][0]
        path = root / "docs/maintainers/ledger.md"
        text = path.read_text(encoding="utf-8").replace(
            f'| {task["id"]} | {task["milestone"]} | {task["status"]} |',
            f'| {task["id"]} | {task["milestone"]} | Ready |',
            1,
        )
        path.write_text(text, encoding="utf-8")
        self.assertIn(f'ledger is missing {task["id"]}', MODULE.validate(root))

    def test_done_task_requires_every_review_category(self) -> None:
        root = self.copy_repository()
        tasks_path = root / "docs/maintainers/tasks.toml"
        state = MODULE.load_toml(tasks_path)
        task = next(task for task in state["tasks"] if task["status"] == "Proposed")
        task_id = task["id"]
        text = tasks_path.read_text(encoding="utf-8")
        text = self.replace_in_task(
            text, task_id, 'status = "Proposed"', 'status = "Done"'
        )
        text = self.replace_in_task(
            text, task_id, 'approval = ""', 'approval = "Test approval"'
        )
        text = self.replace_in_task(
            text,
            task_id,
            "reviews_completed = []",
            'reviews_completed = ["quality"]',
        )
        text = self.replace_in_task(
            text,
            task_id,
            "validation_evidence = []",
            'validation_evidence = ["tests passed"]',
        )
        text = self.replace_in_task(
            text,
            task_id,
            "review_evidence = []",
            'review_evidence = ["quality reviewed"]',
        )
        text = self.replace_in_task(
            text, task_id, 'result = ""', 'result = "complete"'
        )
        tasks_path.write_text(text, encoding="utf-8")
        ledger_path = root / "docs/maintainers/ledger.md"
        ledger_path.write_text(
            ledger_path.read_text(encoding="utf-8").replace(
                f'| {task_id} | {task["milestone"]} | Proposed |',
                f'| {task_id} | {task["milestone"]} | Done |',
                1,
            ),
            encoding="utf-8",
        )
        errors = MODULE.validate(root)
        missing = sorted(set(task["reviews_required"]) - {"quality"})
        self.assertIn(
            f"{task_id} is Done without completed reviews: " + ", ".join(missing),
            errors,
        )


if __name__ == "__main__":
    unittest.main()
