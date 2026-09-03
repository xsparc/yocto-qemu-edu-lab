# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "repository_trust", ROOT / "scripts/repository_trust.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def sample_observation() -> dict:
    policy = copy.deepcopy(MODULE.APPROVED_POLICY)
    return {
        "schema_version": 1,
        "observed_at": "2026-08-30T00:00:00Z",
        "repository": policy["repository"],
        "actions": policy["actions"],
        "ruleset": policy["ruleset"],
        "security": policy["security"],
    }


def sample_evidence() -> dict:
    observation = MODULE.validate_observation(sample_observation())
    return MODULE.build_evidence(
        "a" * 64,
        observation["observed_at"],
        MODULE.facts_from_observation(observation),
    )


class RepositoryTrustTests(unittest.TestCase):
    def temporary_root(self) -> tuple[tempfile.TemporaryDirectory, Path]:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        policy = root / MODULE.POLICY_PATH
        policy.parent.mkdir(parents=True)
        policy.write_bytes((ROOT / MODULE.POLICY_PATH).read_bytes())
        (root / MODULE.SECURITY_PATH).write_text(
            "Security contact: [@xsparc](https://github.com/xsparc)\n",
            encoding="utf-8",
        )
        return temporary, root

    def test_repository_policy_is_the_approved_exact_contract(self) -> None:
        policy, digest = MODULE.load_policy(ROOT)
        self.assertEqual(MODULE.APPROVED_POLICY, policy)
        self.assertRegex(digest, r"^[0-9a-f]{64}$")

    def test_a010_authority_version_and_design_records_are_explicit(self) -> None:
        self.assertEqual("0.9.0-dev\n", (ROOT / "VERSION").read_text(encoding="utf-8"))
        state = tomllib.loads(
            (ROOT / "docs/maintainers/tasks.toml").read_text(encoding="utf-8")
        )
        task = next(item for item in state["tasks"] if item["id"] == "A010")
        self.assertEqual("In Progress", task["status"])
        self.assertEqual("M9", task["milestone"])
        self.assertIn("explicitly approved A010/M9", task["approval"])
        decisions = (ROOT / "docs/maintainers/decisions.md").read_text(
            encoding="utf-8"
        )
        self.assertRegex(decisions, r"(?m)^## D-020: Treat repository settings")
        roadmap = (ROOT / "docs/roadmap.md").read_text(encoding="utf-8")
        self.assertRegex(roadmap, r"(?m)^## M9 — Verifiable public-repository trust")

    def test_ci_runs_local_policy_and_independent_schema_gates(self) -> None:
        workflow = (ROOT / ".github/workflows/fast-checks.yml").read_text(
            encoding="utf-8"
        )
        self.assertEqual(1, workflow.count("python3 scripts/repository_trust.py validate"))
        self.assertEqual(1, workflow.count("tests/validate_repository_trust_schema.py"))

    def test_complete_observation_passes_with_deterministic_bytes(self) -> None:
        observation = MODULE.validate_observation(sample_observation())
        facts = MODULE.facts_from_observation(observation)
        first = MODULE.build_evidence("b" * 64, observation["observed_at"], facts)
        second = MODULE.build_evidence("b" * 64, observation["observed_at"], facts)
        self.assertEqual("pass", first["result"])
        self.assertEqual(MODULE.CHECK_IDS, tuple(item["id"] for item in first["checks"]))
        self.assertEqual(MODULE.json_bytes(first), MODULE.json_bytes(second))

    def test_missing_observation_is_closed_unavailable_evidence(self) -> None:
        _, root = self.temporary_root()
        evidence, exit_code = MODULE.evaluate_repository(root)
        self.assertEqual(3, exit_code)
        self.assertEqual("unavailable", evidence["result"])
        self.assertIsNone(evidence["observed_at"])
        self.assertTrue(all(item["status"] == "unavailable" for item in evidence["checks"]))

    def test_fixed_observation_path_produces_passing_evidence(self) -> None:
        _, root = self.temporary_root()
        observation = root / MODULE.OBSERVATION_PATH
        observation.parent.mkdir(parents=True)
        observation.write_text(json.dumps(sample_observation()), encoding="utf-8")
        evidence, exit_code = MODULE.evaluate_repository(root)
        self.assertEqual(0, exit_code)
        self.assertEqual("pass", evidence["result"])

    def test_cli_exit_contract_is_observable_end_to_end(self) -> None:
        _, root = self.temporary_root()
        script = root / "scripts/repository_trust.py"
        script.parent.mkdir()
        shutil.copyfile(ROOT / "scripts/repository_trust.py", script)

        def invoke(command: str) -> subprocess.CompletedProcess[bytes]:
            return subprocess.run(
                [sys.executable, "-B", str(script), command],
                cwd=root,
                capture_output=True,
                check=False,
            )

        completed = invoke("validate")
        self.assertEqual(0, completed.returncode)
        self.assertEqual(["repository-trust: PASS"], completed.stdout.decode().splitlines())

        completed = invoke("evaluate")
        self.assertEqual(3, completed.returncode)
        self.assertEqual("unavailable", json.loads(completed.stdout)["result"])

        observation_path = root / MODULE.OBSERVATION_PATH
        observation_path.parent.mkdir(parents=True)
        observation = sample_observation()
        observation_path.write_text(json.dumps(observation), encoding="utf-8")
        completed = invoke("evaluate")
        self.assertEqual(0, completed.returncode)
        self.assertEqual("pass", json.loads(completed.stdout)["result"])

        observation["actions"]["default_workflow_permissions"] = "write"
        observation_path.write_text(json.dumps(observation), encoding="utf-8")
        completed = invoke("evaluate")
        self.assertEqual(1, completed.returncode)
        self.assertEqual("fail", json.loads(completed.stdout)["result"])

        observation["future"] = True
        observation_path.write_text(json.dumps(observation), encoding="utf-8")
        completed = invoke("evaluate")
        self.assertEqual(2, completed.returncode)
        self.assertEqual(b"", completed.stdout)
        self.assertIn(b"repository-trust: INVALID:", completed.stderr)

        completed = invoke("unknown")
        self.assertEqual(2, completed.returncode)
        self.assertEqual(b"", completed.stdout)

    def test_partial_observation_is_unavailable_not_a_false_pass(self) -> None:
        observation = {
            "schema_version": 1,
            "observed_at": "2026-08-30T00:00:00Z",
            "repository": {"visibility": "public"},
        }
        validated = MODULE.validate_observation(observation)
        evidence = MODULE.build_evidence(
            "c" * 64,
            validated["observed_at"],
            MODULE.facts_from_observation(validated),
        )
        self.assertEqual("unavailable", evidence["result"])
        statuses = {item["id"]: item["status"] for item in evidence["checks"]}
        self.assertEqual("pass", statuses["repository.public"])
        self.assertEqual("unavailable", statuses["repository.default_branch"])

    def test_partial_composite_conflicts_fail_before_unavailable(self) -> None:
        actions_conflict = sample_observation()
        actions_conflict["actions"]["selected_actions"] = {
            "github_owned_allowed": False
        }
        pull_request_conflict = sample_observation()
        pull_request_conflict["ruleset"]["pull_request"] = {"required": False}
        controls = []
        actions_incomplete = sample_observation()
        actions_incomplete["actions"]["selected_actions"] = {
            "github_owned_allowed": True
        }
        controls.append((actions_incomplete, "actions.github_owned_only"))
        pull_request_incomplete = sample_observation()
        pull_request_incomplete["ruleset"]["pull_request"] = {"required": True}
        controls.append((pull_request_incomplete, "ruleset.pull_request"))

        for observation, check_id in (
            (actions_conflict, "actions.github_owned_only"),
            (pull_request_conflict, "ruleset.pull_request"),
        ):
            with self.subTest(check=check_id, state="conflict"):
                validated = MODULE.validate_observation(observation)
                evidence = MODULE.build_evidence(
                    "c" * 64,
                    validated["observed_at"],
                    MODULE.facts_from_observation(validated),
                )
                statuses = {item["id"]: item["status"] for item in evidence["checks"]}
                self.assertEqual("fail", statuses[check_id])
                self.assertEqual("fail", evidence["result"])

        for observation, check_id in controls:
            with self.subTest(check=check_id, state="incomplete"):
                validated = MODULE.validate_observation(observation)
                evidence = MODULE.build_evidence(
                    "c" * 64,
                    validated["observed_at"],
                    MODULE.facts_from_observation(validated),
                )
                statuses = {item["id"]: item["status"] for item in evidence["checks"]}
                self.assertEqual("unavailable", statuses[check_id])
                self.assertEqual("unavailable", evidence["result"])

    def test_policy_drift_cases_fail_without_hiding_unavailable_facts(self) -> None:
        mutations = []

        observation = sample_observation()
        observation["ruleset"]["required_status_checks"]["checks"].pop()
        mutations.append((observation, "ruleset.exact_checks"))

        observation = sample_observation()
        observation["ruleset"]["required_status_checks"]["checks"].append(
            {"context": "third-party", "source": "external-app"}
        )
        mutations.append((observation, "ruleset.check_source"))

        observation = sample_observation()
        observation["ruleset"]["bypass_actor_count"] = 1
        mutations.append((observation, "ruleset.no_bypass"))

        observation = sample_observation()
        observation["actions"]["default_workflow_permissions"] = "write"
        mutations.append((observation, "actions.default_permissions"))

        observation = sample_observation()
        observation["actions"]["sha_pinning_required"] = False
        mutations.append((observation, "actions.sha_pinning"))

        observation = sample_observation()
        observation["actions"]["selected_actions"]["patterns_allowed"] = ["owner/action@*"]
        mutations.append((observation, "actions.github_owned_only"))

        security_checks = {
            "dependabot_alerts": "security.dependabot_alerts",
            "dependabot_security_updates": "security.dependabot_updates",
            "secret_scanning": "security.secret_scanning",
            "secret_scanning_push_protection": "security.push_protection",
            "private_vulnerability_reporting": "security.private_reporting",
        }
        for field, check_id in security_checks.items():
            observation = sample_observation()
            observation["security"][field] = False
            mutations.append((observation, check_id))

        observation = sample_observation()
        observation["ruleset"]["required_status_checks"]["checks"].append(
            {"context": "yocto-metadata", "source": "github-actions"}
        )
        mutations.append((observation, "ruleset.metadata_advisory"))

        for observation, failed_id in mutations:
            with self.subTest(failed_id=failed_id):
                validated = MODULE.validate_observation(observation)
                evidence = MODULE.build_evidence(
                    "d" * 64,
                    validated["observed_at"],
                    MODULE.facts_from_observation(validated),
                )
                self.assertEqual("fail", evidence["result"])
                statuses = {item["id"]: item["status"] for item in evidence["checks"]}
                self.assertEqual("fail", statuses[failed_id])

    def test_duplicate_unknown_malformed_and_unsafe_input_are_rejected(self) -> None:
        with self.assertRaisesRegex(MODULE.RepositoryTrustError, "duplicate JSON key"):
            MODULE.parse_json(
                b'{"schema_version":1,"schema_version":1}', "observation"
            )

        observation = sample_observation()
        observation["future"] = True
        with self.assertRaisesRegex(MODULE.RepositoryTrustError, "unknown fields"):
            MODULE.validate_observation(observation)

        observation = sample_observation()
        observation["schema_version"] = True
        with self.assertRaisesRegex(MODULE.RepositoryTrustError, "integer 1"):
            MODULE.validate_observation(observation)

        with self.assertRaisesRegex(MODULE.RepositoryTrustError, "unsafe character"):
            MODULE.parse_json(b'{"value":"line\\nfeed"}', "observation")

        with self.assertRaisesRegex(MODULE.RepositoryTrustError, "unsafe character"):
            MODULE.parse_json(b'{"value":"\\u202e"}', "observation")

        with self.assertRaisesRegex(MODULE.RepositoryTrustError, "keys must be strings"):
            MODULE.validate_observation({1: "not-json"})

        with self.assertRaisesRegex(MODULE.RepositoryTrustError, "floating-point"):
            MODULE.parse_json(b'{"value":1.5}', "observation")

    def test_reader_rejects_oversize_and_symbolic_link_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            oversized = root / "oversized.json"
            oversized.write_bytes(b"x" * 17)
            with self.assertRaisesRegex(MODULE.RepositoryTrustError, "exceeds 16 bytes"):
                MODULE.read_regular(oversized, 16, "fixture")

            target = root / "target.json"
            target.write_text("{}", encoding="utf-8")
            link = root / "link.json"
            try:
                os.symlink(target, link)
            except (OSError, NotImplementedError):
                self.skipTest("symbolic links are unavailable to this test account")
            with self.assertRaisesRegex(MODULE.RepositoryTrustError, "direct regular file"):
                MODULE.read_regular(link, 16, "fixture")

            redirected = root / "redirected"
            try:
                os.symlink(root, redirected, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("directory symbolic links are unavailable to this test account")
            with self.assertRaisesRegex(MODULE.RepositoryTrustError, "direct directories"):
                MODULE.read_regular(
                    redirected / "target.json",
                    16,
                    "fixture",
                    root=root,
                )

            observation_parent = root / "build" / "repository-trust"
            observation_parent.parent.mkdir()
            os.symlink(
                root,
                observation_parent,
                target_is_directory=True,
            )
            policy = root / MODULE.POLICY_PATH
            policy.parent.mkdir(exist_ok=True)
            policy.write_bytes((ROOT / MODULE.POLICY_PATH).read_bytes())
            (root / MODULE.SECURITY_PATH).write_text(
                "Security contact: [@xsparc](https://github.com/xsparc)\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(MODULE.RepositoryTrustError, "direct directories"):
                MODULE.evaluate_repository(root)

    def test_parent_redirects_are_rejected_without_host_symlink_privilege(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate = root / "redirected" / "observation.json"
            symlink_info = os.stat_result((stat.S_IFLNK, 0, 0, 0, 0, 0, 0, 0, 0, 0))
            with mock.patch.object(Path, "lstat", return_value=symlink_info):
                with self.assertRaisesRegex(
                    MODULE.RepositoryTrustError,
                    "direct director",
                ):
                    MODULE.direct_path(candidate, root, "fixture")

        reparse_point = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        if reparse_point:
            info = SimpleNamespace(
                st_mode=stat.S_IFDIR,
                st_file_attributes=reparse_point,
            )
            self.assertTrue(MODULE.is_redirect(info))

    def test_parent_replacement_cannot_redirect_an_open(self) -> None:
        with (
            tempfile.TemporaryDirectory() as trusted_temporary,
            tempfile.TemporaryDirectory() as outside_temporary,
        ):
            root = Path(trusted_temporary)
            parent = root / "input"
            parent.mkdir()
            candidate = parent / "observation.json"
            candidate.write_text("inside", encoding="utf-8")
            outside = Path(outside_temporary)
            (outside / candidate.name).write_text("outside", encoding="utf-8")
            original_direct_path = MODULE.direct_path
            redirect_created = False

            def replace_after_validation(*args, **kwargs):
                nonlocal redirect_created
                result = original_direct_path(*args, **kwargs)
                shutil.rmtree(parent)
                if os.name == "nt":
                    completed = subprocess.run(
                        [
                            "cmd.exe",
                            "/d",
                            "/c",
                            "mklink",
                            "/J",
                            str(parent),
                            str(outside),
                        ],
                        capture_output=True,
                        check=False,
                        text=True,
                    )
                    if completed.returncode != 0:
                        self.skipTest("directory junctions are unavailable to this test account")
                else:
                    os.symlink(outside, parent, target_is_directory=True)
                redirect_created = True
                return result

            try:
                with mock.patch.object(
                    MODULE,
                    "direct_path",
                    side_effect=replace_after_validation,
                ):
                    with self.assertRaisesRegex(
                        MODULE.RepositoryTrustError,
                        "resolved outside|cannot read fixture",
                    ):
                        MODULE.read_regular(
                            candidate,
                            16,
                            "fixture",
                            root=root,
                        )
            finally:
                if redirect_created and os.path.lexists(parent):
                    if os.name == "nt":
                        os.rmdir(parent)
                    else:
                        parent.unlink()

    def test_semantic_evidence_rejects_tampering(self) -> None:
        evidence = sample_evidence()
        evidence["result"] = "fail"
        with self.assertRaisesRegex(MODULE.RepositoryTrustError, "differ from their facts"):
            MODULE.validate_evidence(evidence)

        evidence = sample_evidence()
        evidence["checks"][0], evidence["checks"][1] = evidence["checks"][1], evidence["checks"][0]
        with self.assertRaisesRegex(MODULE.RepositoryTrustError, "check repository.public"):
            MODULE.validate_evidence(evidence)

        evidence = sample_evidence()
        evidence["facts"]["future"] = True
        with self.assertRaisesRegex(MODULE.RepositoryTrustError, "unknown fields"):
            MODULE.validate_evidence(evidence)

        evidence = sample_evidence()
        evidence["facts"]["ruleset"]["required_status_checks"].reverse()
        with self.assertRaisesRegex(MODULE.RepositoryTrustError, "must be sorted"):
            MODULE.validate_evidence(evidence)

        evidence = sample_evidence()
        evidence["facts"]["ruleset"]["name"] = "unsafe\nname"
        with self.assertRaisesRegex(MODULE.RepositoryTrustError, "unsafe character"):
            MODULE.validate_evidence(evidence)

    def test_policy_and_security_contact_drift_fail_closed(self) -> None:
        _, root = self.temporary_root()
        policy = json.loads((root / MODULE.POLICY_PATH).read_text(encoding="utf-8"))
        policy["actions"]["allowed_actions"] = "all"
        (root / MODULE.POLICY_PATH).write_text(json.dumps(policy), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.RepositoryTrustError, "approved exact contract"):
            MODULE.load_policy(root)

        (root / MODULE.POLICY_PATH).write_bytes((ROOT / MODULE.POLICY_PATH).read_bytes())
        (root / MODULE.SECURITY_PATH).write_text("No named contact\n", encoding="utf-8")
        policy, _ = MODULE.load_policy(root)
        with self.assertRaisesRegex(MODULE.RepositoryTrustError, "approved contact"):
            MODULE.validate_local_contract(root, policy)

    def test_security_contact_must_be_visible(self) -> None:
        _, root = self.temporary_root()
        policy, _ = MODULE.load_policy(root)
        (root / MODULE.SECURITY_PATH).write_text(
            "<!-- Security contact: [@xsparc](https://github.com/xsparc) -->\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(
            MODULE.RepositoryTrustError,
            "visible standalone line",
        ):
            MODULE.validate_local_contract(root, policy)

    def test_runtime_has_no_network_subprocess_or_credential_adapter(self) -> None:
        source = (ROOT / "scripts/repository_trust.py").read_text(encoding="utf-8")
        for forbidden in ("import subprocess", "import socket", "import urllib", "import requests", "GITHUB_TOKEN", "Authorization:"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)
        self.assertIn('OBSERVATION_PATH = Path("build/repository-trust/observation-v1.json")', source)
        self.assertNotIn("--repo", source)
        self.assertNotIn("--observation", source)


if __name__ == "__main__":
    unittest.main()
