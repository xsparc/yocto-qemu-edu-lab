# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipIf(os.name == "nt", "shell contract runs on the Linux CI host")
class EnvironmentTests(unittest.TestCase):
    def test_relative_build_dir_is_normalized_after_environment_changes_cwd(self) -> None:
        bash = shutil.which("bash")
        if bash is None:
            self.skipTest("bash is unavailable")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            (root / "scripts").mkdir()
            (root / "layers/openembedded-core").mkdir(parents=True)
            (root / "layers/bitbake/bin").mkdir(parents=True)
            shutil.copy2(ROOT / "environment.sh", root / "environment.sh")
            (root / "scripts/source_lock.py").write_text(
                '''import sys

if "status" in sys.argv:
    raise SystemExit(0)

key = sys.argv[-1]
values = {
    "build.environment_script": "layers/openembedded-core/oe-init-build-env",
    "build.bitbake_bin": "layers/bitbake/bin",
    "build.build_dir": "build",
}
print(values[key])
''',
                encoding="utf-8",
            )
            (root / "layers/openembedded-core/oe-init-build-env").write_text(
                '''#!/usr/bin/env bash
mkdir -p "$1"
cd "$1"
BUILDDIR=$PWD
export BUILDDIR
''',
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    bash,
                    "-c",
                    'set -eo pipefail; BUILD_DIR=build-alt; '
                    'source ./environment.sh; printf "%s\\n%s\\n" "$BUILD_DIR" "$PWD"',
                ],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )

        build_dir, current_dir = result.stdout.splitlines()
        expected = str(root / "build-alt")
        self.assertEqual(expected, build_dir)
        self.assertEqual(expected, current_dir)


if __name__ == "__main__":
    unittest.main()
