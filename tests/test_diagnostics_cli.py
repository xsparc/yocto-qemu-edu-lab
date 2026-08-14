# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "qemu-edu-lab"


class DiagnosticsCliTests(unittest.TestCase):
    def run_cli(self, *arguments: str, cwd: Path | None = None) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            [sys.executable, "-B", str(CLI), *arguments],
            cwd=cwd or ROOT,
            capture_output=True,
            check=False,
        )

    def test_inspect_is_root_derived_and_byte_deterministic_for_both_labs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            for lab in ("pci-x86-64", "platform-arm64"):
                first = self.run_cli("--lab", lab, "--format", "json", "inspect", cwd=Path(temporary))
                second = self.run_cli("--lab", lab, "--format", "json", "inspect", cwd=Path(temporary))
                self.assertEqual(0, first.returncode, first.stderr.decode(errors="replace"))
                self.assertEqual(first.stdout, second.stdout)
                self.assertEqual(b"", first.stderr)
                self.assertEqual(lab, json.loads(first.stdout)["lab"]["id"])
                self.assertNotIn(b"\r\n", first.stdout)

    def test_explicit_empty_and_unknown_arguments_emit_no_document(self) -> None:
        for arguments in (("--lab", "", "status"), ("--format", "yaml", "status"), ("unknown",)):
            with self.subTest(arguments=arguments):
                result = self.run_cli(*arguments)
                self.assertEqual(2, result.returncode)
                self.assertEqual(b"", result.stdout)
                self.assertIn(b"qemu-edu-lab", result.stderr)

    def test_text_and_json_reach_the_same_aggregate_result(self) -> None:
        json_result = self.run_cli("--format", "json", "status")
        text_result = self.run_cli("--format", "text", "status")
        document = json.loads(json_result.stdout)
        self.assertEqual(json_result.returncode, text_result.returncode)
        self.assertTrue(text_result.stdout.startswith(f"qemu-edu-lab status: {document['result']}\n".encode()))
        self.assertEqual(b"", text_result.stderr)

    def test_internal_failure_does_not_emit_traceback_or_local_identity(self) -> None:
        sys.path.insert(0, str(ROOT))
        try:
            import importlib.machinery
            import importlib.util

            loader = importlib.machinery.SourceFileLoader("qemu_edu_lab_cli", str(CLI))
            spec = importlib.util.spec_from_loader(loader.name, loader)
            assert spec is not None
            module = importlib.util.module_from_spec(spec)
            loader.exec_module(module)
            with patch.object(module, "command_document", side_effect=RuntimeError(str(ROOT))):
                with patch.object(sys, "argv", ["qemu-edu-lab", "status"]):
                    with patch.object(sys, "stdout") as stdout, patch.object(sys, "stderr") as stderr:
                        stdout.buffer.write = unittest.mock.Mock()
                        stderr.buffer.write = unittest.mock.Mock()
                        self.assertEqual(1, module.main())
                        stdout.buffer.write.assert_not_called()
                        stderr.buffer.write.assert_called_once_with(
                            b"qemu-edu-lab: internal diagnostic failure\n"
                        )
        finally:
            sys.path.remove(str(ROOT))

    @unittest.skipUnless(os.name == "posix", "direct executable contract requires POSIX")
    def test_posix_checkout_runs_the_entry_point_directly(self) -> None:
        result = subprocess.run(
            [str(CLI), "--format", "json", "inspect"],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr.decode(errors="replace"))
        self.assertEqual("inspect", json.loads(result.stdout)["command"])


if __name__ == "__main__":
    unittest.main()
