# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "update_checksums", ROOT / "scripts/update_checksums.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ChecksumManifestTests(unittest.TestCase):
    def repository(self) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        subprocess.run(["git", "init", "--quiet"], cwd=root, check=True)
        subprocess.run(
            ["git", "config", "user.email", "tests@example.invalid"],
            cwd=root,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Checksum Tests"], cwd=root, check=True
        )
        return root

    def test_render_hashes_staged_bytes_not_worktree_line_endings(self) -> None:
        root = self.repository()
        path = root / "sample.txt"
        staged = b"staged line\n"
        path.write_bytes(staged)
        subprocess.run(["git", "add", "sample.txt"], cwd=root, check=True)
        path.write_bytes(b"unstaged line\r\n")
        expected = hashlib.sha256(staged).hexdigest()
        self.assertIn(f"{expected}  ./sample.txt", MODULE.render(root))

    def test_untracked_files_are_excluded(self) -> None:
        root = self.repository()
        (root / "tracked.txt").write_text("tracked\n", encoding="utf-8")
        (root / "private-notes.txt").write_text("not for commit\n", encoding="utf-8")
        subprocess.run(["git", "add", "tracked.txt"], cwd=root, check=True)
        self.assertEqual(["tracked.txt"], MODULE.source_files(root))

    def test_staged_deletion_is_removed_from_manifest(self) -> None:
        root = self.repository()
        path = root / "removed.txt"
        path.write_text("remove me\n", encoding="utf-8")
        subprocess.run(["git", "add", "removed.txt"], cwd=root, check=True)
        subprocess.run(["git", "commit", "--quiet", "-m", "fixture"], cwd=root, check=True)
        subprocess.run(["git", "rm", "--quiet", "removed.txt"], cwd=root, check=True)
        self.assertNotIn("removed.txt", MODULE.source_files(root))


if __name__ == "__main__":
    unittest.main()
