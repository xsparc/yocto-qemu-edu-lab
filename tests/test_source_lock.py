# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "source_lock", ROOT / "scripts/source_lock.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SourceLockTests(unittest.TestCase):
    def lock(self) -> dict:
        return json.loads((ROOT / "config/sources.lock.json").read_text(encoding="utf-8"))

    def temporary_root(self) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        return Path(temporary.name).resolve()

    def git(self, path: Path, *arguments: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(path), *arguments],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    def create_checkout(self, root: Path, source: dict) -> str:
        path = root / source["path"]
        path.mkdir(parents=True)
        subprocess.run(
            ["git", "init", "--quiet", "--object-format=sha1", str(path)],
            check=True,
        )
        self.git(path, "config", "user.email", "tests@example.invalid")
        self.git(path, "config", "user.name", "Source Lock Tests")
        for relative in source["required_paths"]:
            required = path / relative
            required.parent.mkdir(parents=True, exist_ok=True)
            required.write_text(f"fixture for {source['id']}\n", encoding="utf-8")
        self.git(path, "add", ".")
        self.git(path, "commit", "--quiet", "-m", "fixture")
        commit = self.git(path, "rev-parse", "HEAD")
        source["commit"] = commit
        self.git(path, "remote", "add", "origin", source["url"])
        self.git(path, "checkout", "--quiet", "--detach", commit)
        return commit

    def test_repository_lock_is_valid(self) -> None:
        MODULE.validate_lock(self.lock())

    def test_unknown_fields_fail_closed(self) -> None:
        lock = self.lock()
        lock["future"] = True
        with self.assertRaisesRegex(MODULE.LockError, "unknown fields"):
            MODULE.validate_lock(lock)

    def test_duplicate_source_paths_are_rejected(self) -> None:
        lock = self.lock()
        lock["sources"][1]["path"] = lock["sources"][0]["path"]
        with self.assertRaisesRegex(MODULE.LockError, "duplicate source path"):
            MODULE.validate_lock(lock)

    def test_overlapping_source_paths_are_rejected(self) -> None:
        lock = self.lock()
        lock["sources"][1]["path"] = lock["sources"][0]["path"] + "/nested"
        with self.assertRaisesRegex(MODULE.LockError, "overlapping source path"):
            MODULE.validate_lock(lock)

    def test_release_ref_must_match_declared_version(self) -> None:
        lock = self.lock()
        lock["sources"][0]["release_ref"] = "refs/tags/yocto-6.0.1"
        with self.assertRaisesRegex(MODULE.LockError, "release.version"):
            MODULE.validate_lock(lock)

    def test_oe_branch_ref_must_match_declared_series(self) -> None:
        lock = self.lock()
        lock["sources"][1]["branch_ref"] = "refs/heads/other"
        with self.assertRaisesRegex(MODULE.LockError, "release.series"):
            MODULE.validate_lock(lock)

    def test_escaping_source_path_is_rejected(self) -> None:
        lock = self.lock()
        lock["sources"][0]["path"] = "layers/../outside"
        with self.assertRaisesRegex(MODULE.LockError, "normalized"):
            MODULE.validate_lock(lock)

    def test_source_path_with_control_whitespace_is_rejected(self) -> None:
        lock = self.lock()
        lock["sources"][0]["path"] = "layers/bitbake\nother"
        with self.assertRaisesRegex(MODULE.LockError, "whitespace"):
            MODULE.validate_lock(lock)

    def test_non_https_origin_is_rejected(self) -> None:
        lock = self.lock()
        lock["sources"][0]["url"] = "git://example.invalid/bitbake"
        with self.assertRaisesRegex(MODULE.LockError, "HTTPS"):
            MODULE.validate_lock(lock)

    def test_short_or_uppercase_commit_is_rejected(self) -> None:
        for commit in ("abc123", "A" * 40):
            with self.subTest(commit=commit):
                lock = self.lock()
                lock["sources"][0]["commit"] = commit
                with self.assertRaisesRegex(MODULE.LockError, "lowercase SHA-1"):
                    MODULE.validate_lock(lock)

    def test_cached_clean_detached_sources_pass_offline(self) -> None:
        root = self.temporary_root()
        lock = self.lock()
        for source in lock["sources"]:
            self.create_checkout(root, source)
        MODULE.validate_lock(lock)
        result = MODULE.sync_result(root, lock, "fixture-digest", offline=True)
        self.assertTrue(result["ok"])
        self.assertTrue(all(source["state"] == "ready" for source in result["sources"]))

    def test_online_sync_verifies_branch_and_tag_before_checkout(self) -> None:
        root = self.temporary_root()
        upstream = root / "upstream"
        upstream.mkdir()
        subprocess.run(
            ["git", "init", "--quiet", "--object-format=sha1", str(upstream)],
            check=True,
        )
        self.git(upstream, "config", "user.email", "tests@example.invalid")
        self.git(upstream, "config", "user.name", "Source Lock Tests")
        required = upstream / "bin/bitbake"
        required.parent.mkdir(parents=True)
        required.write_text("fixture\n", encoding="utf-8")
        self.git(upstream, "add", ".")
        self.git(upstream, "commit", "--quiet", "-m", "locked")
        self.git(upstream, "branch", "-M", "locked")
        self.git(upstream, "tag", "yocto-test")
        commit = self.git(upstream, "rev-parse", "HEAD")
        remote = root / "remote.git"
        subprocess.run(
            ["git", "clone", "--quiet", "--bare", str(upstream), str(remote)],
            check=True,
        )

        source = copy.deepcopy(self.lock()["sources"][0])
        source.update(
            {
                "url": "https://example.invalid/upstream",
                "branch_ref": "refs/heads/locked",
                "release_ref": "refs/tags/yocto-test",
                "commit": commit,
                "required_paths": ["bin/bitbake"],
            }
        )
        checkout = root / source["path"]
        checkout.mkdir(parents=True)
        subprocess.run(
            ["git", "init", "--quiet", "--object-format=sha1", str(checkout)],
            check=True,
        )
        self.git(checkout, "remote", "add", "origin", source["url"])
        original_git = MODULE.git

        def local_fetch(path: Path, *arguments: str, check: bool = True):
            if arguments and arguments[0] == "fetch":
                result = subprocess.run(
                    [
                        "git",
                        "-C",
                        str(path),
                        "-c",
                        f"url.{remote.as_uri()}.insteadOf={source['url']}",
                        *arguments,
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if check and result.returncode:
                    raise MODULE.LockError(result.stderr.strip())
                return result
            return original_git(path, *arguments, check=check)

        with mock.patch.object(MODULE, "git", side_effect=local_fetch):
            result = MODULE.sync_source(root, source, offline=False)
        self.assertEqual("ready", result["state"])
        self.assertEqual(commit, result["actual_commit"])
        self.assertTrue(result["detached"])

    def test_dirty_checkout_is_refused_without_overwrite(self) -> None:
        root = self.temporary_root()
        source = copy.deepcopy(self.lock()["sources"][0])
        self.create_checkout(root, source)
        marker = root / source["path"] / source["required_paths"][0]
        marker.write_text("local work\n", encoding="utf-8")
        with self.assertRaisesRegex(MODULE.LockError, "dirty checkout"):
            MODULE.sync_source(root, source, offline=True)
        self.assertEqual("local work\n", marker.read_text(encoding="utf-8"))

    def test_wrong_origin_is_refused(self) -> None:
        root = self.temporary_root()
        source = copy.deepcopy(self.lock()["sources"][0])
        self.create_checkout(root, source)
        self.git(root / source["path"], "remote", "set-url", "origin", "https://example.invalid/wrong")
        with self.assertRaisesRegex(MODULE.LockError, "different origin"):
            MODULE.sync_source(root, source, offline=True)

    def test_unexpected_head_is_refused(self) -> None:
        root = self.temporary_root()
        source = copy.deepcopy(self.lock()["sources"][0])
        self.create_checkout(root, source)
        path = root / source["path"]
        marker = path / source["required_paths"][0]
        marker.write_text("second commit\n", encoding="utf-8")
        self.git(path, "add", ".")
        self.git(path, "commit", "--quiet", "-m", "unexpected")
        self.git(path, "checkout", "--quiet", "--detach", "HEAD")
        with self.assertRaisesRegex(MODULE.LockError, "unexpected HEAD"):
            MODULE.sync_source(root, source, offline=True)


if __name__ == "__main__":
    unittest.main()
