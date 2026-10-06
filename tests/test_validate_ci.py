# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import importlib.util
import json
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

    def test_canonical_make_check_includes_ci_policy(self) -> None:
        text = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertIn("check: check-source-lock check-labs check-workflow check-ci check-repository-trust", text)
        self.assertIn("check-ci:\n\tpython3 scripts/validate_ci.py", text)
        self.assertIn(
            "check-repository-trust:\n\tpython3 scripts/repository_trust.py validate",
            text,
        )

    def test_fast_jobs_and_trust_policy_are_bound_exactly(self) -> None:
        text = (ROOT / ".github/workflows/fast-checks.yml").read_text(
            encoding="utf-8"
        )
        self.assertEqual([], MODULE.validate_trust_policy_binding(ROOT, text))
        changed = text.replace(
            "  licensing:\n",
            "  extra:\n    timeout-minutes: 5\n    runs-on: ubuntu-24.04\n  licensing:\n",
            1,
        )
        self.assertTrue(
            any(
                "job IDs must be exactly" in error
                for error in MODULE.validate_trust_policy_binding(ROOT, changed)
            )
        )

    def test_fast_triggers_are_exact_and_unfiltered(self) -> None:
        text = (ROOT / ".github/workflows/fast-checks.yml").read_text(
            encoding="utf-8"
        )
        for changed in (
            text.replace("  pull_request:\n", "", 1),
            text.replace(
                "  pull_request:\n",
                "  pull_request:\n    paths: [scripts/**]\n",
                1,
            ),
            text.replace("    branches: [main]\n", "    branches: [topic]\n", 1),
            text.replace("  workflow_dispatch:\n", "", 1),
        ):
            with self.subTest():
                errors = MODULE.validate_trust_policy_binding(ROOT, changed)
                self.assertTrue(
                    any("triggers must be exactly" in error for error in errors)
                )

    def test_required_fast_jobs_cannot_change_context_or_execution(self) -> None:
        text = (ROOT / ".github/workflows/fast-checks.yml").read_text(
            encoding="utf-8"
        )
        for name, block in MODULE.job_blocks(text):
            with self.subTest(job=name, mutation="display-name"):
                changed = text.replace(
                    block,
                    block.replace(
                        f"  {name}:\n",
                        f"  {name}:\n    name: renamed-context\n",
                        1,
                    ),
                    1,
                )
                errors = MODULE.validate_trust_policy_binding(ROOT, changed)
                self.assertTrue(any("job-level name" in error for error in errors))
            with self.subTest(job=name, mutation="condition"):
                changed = text.replace(
                    block,
                    block.replace(
                        f"  {name}:\n",
                        f"  {name}:\n    if: false\n",
                        1,
                    ),
                    1,
                )
                errors = MODULE.validate_trust_policy_binding(ROOT, changed)
                self.assertTrue(any("job-level if" in error for error in errors))
            for key, value in (
                ("needs", "repository"),
                ("strategy", "{matrix: {python: [3.12]}}"),
            ):
                with self.subTest(job=name, mutation=key):
                    changed = text.replace(
                        block,
                        block.replace(
                            f"  {name}:\n",
                            f"  {name}:\n    {key}: {value}\n",
                            1,
                        ),
                        1,
                    )
                    errors = MODULE.validate_trust_policy_binding(ROOT, changed)
                    self.assertTrue(
                        any(f"job-level {key}" in error for error in errors)
                    )
            with self.subTest(job=name, mutation="commands"):
                changed = text.replace(
                    block,
                    block.replace("steps:", "steps: []", 1),
                    1,
                )
                errors = MODULE.validate_trust_policy_binding(ROOT, changed)
                self.assertTrue(
                    any("reviewed command surface" in error for error in errors)
                )

    def test_complete_fast_execution_envelope_is_bound(self) -> None:
        text = (ROOT / ".github/workflows/fast-checks.yml").read_text(
            encoding="utf-8"
        )
        mutations = {
            "bash-env": text.replace(
                "jobs:\n",
                "env:\n  BASH_ENV: ./ci-bootstrap.sh\njobs:\n",
                1,
            ),
            "python-path": text.replace(
                "jobs:\n",
                "env:\n  PYTHONPATH: ./shadow-modules\njobs:\n",
                1,
            ),
            "working-directory": text.replace(
                "    shell: bash\n",
                "    shell: bash\n    working-directory: ./alternate\n",
                1,
            ),
            "alternate-shell": text.replace("    shell: bash\n", "    shell: pwsh\n", 1),
        }
        for name, changed in mutations.items():
            with self.subTest(mutation=name):
                errors = MODULE.validate_workflow(self.workflow(changed))
                errors.extend(MODULE.validate_trust_policy_binding(ROOT, changed))
                self.assertTrue(
                    any("execution surface" in error for error in errors),
                    errors,
                )

    def test_underscore_job_ids_cannot_escape_runner_enforcement(self) -> None:
        text = (ROOT / ".github/workflows/fast-checks.yml").read_text(
            encoding="utf-8"
        )
        changed = text.replace(
            "jobs:\n",
            "jobs:\n"
            "  _escape:\n"
            "    timeout-minutes: 5\n"
            "    runs-on:\n"
            "      group: persistent-runners\n"
            "      labels: linux\n"
            "    steps:\n"
            "      - run: echo persistent\n",
            1,
        )
        errors = MODULE.validate_workflow(self.workflow(changed))
        errors.extend(MODULE.validate_trust_policy_binding(ROOT, changed))
        self.assertTrue(any("_escape" in error for error in errors), errors)
        self.assertTrue(any("hosted runner" in error for error in errors), errors)

    def test_path_scoped_metadata_is_not_a_required_fast_context(self) -> None:
        policy = json.loads(
            (ROOT / MODULE.TRUST_POLICY).read_text(encoding="utf-8")
        )
        contexts = {
            item["context"]
            for item in policy["ruleset"]["required_status_checks"]["checks"]
        }
        self.assertEqual(MODULE.FAST_JOB_IDS, contexts)
        self.assertNotIn("yocto-metadata", contexts)

    def test_required_contexts_are_reserved_to_the_fast_workflow(self) -> None:
        cases = {
            "reserved-job-id": SAFE.replace(
                "  test:\n",
                "  repository:\n    if: false\n",
                1,
            ),
            "static-display-name": SAFE.replace(
                "  test:\n",
                "  test:\n    name: repository\n",
                1,
            ),
            "dynamic-display-name": SAFE.replace(
                "  test:\n",
                "  test:\n    name: ${{ github.event.action }}\n",
                1,
            ),
        }
        for name, text in cases.items():
            with self.subTest(case=name):
                path = self.workflow(text)
                additional = path.with_name("additional.yml")
                path.rename(additional)
                errors = MODULE.validate_workflow(additional)
                self.assertTrue(
                    any(
                        "context" in error and "fast-checks.yml" in error
                        for error in errors
                    ),
                    errors,
                )

    def test_repository_inventory_rejects_a_shadow_required_context(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in (
                ".github/workflows/fast-checks.yml",
                ".github/workflows/yocto-metadata.yml",
                MODULE.TRUST_POLICY,
            ):
                source = ROOT / relative
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(source.read_bytes())
            shadow = SAFE.replace(
                "  test:\n",
                "  licensing:\n    if: false\n",
                1,
            )
            (root / ".github/workflows/shadow.yml").write_text(
                shadow,
                encoding="utf-8",
            )
            errors = MODULE.validate(root)
            self.assertTrue(
                any(
                    error.startswith(".github/workflows/shadow.yml:")
                    and "reserved for fast-checks.yml" in error
                    for error in errors
                ),
                errors,
            )

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
        for path in (
            'config/labs/**',
            "scripts/lab_config.py",
            "runtime-test.sh",
            "scripts/sbom_evidence.py",
            "sbom-evidence.sh",
            "scripts/sdk_evidence.py",
            "scripts/sdk_iteration.py",
            "scripts/sdk_tooling.py",
            "sdk-test.sh",
            "schemas/qemu-edu-sdk-evidence-v1.schema.json",
        ):
            with self.subTest(path=path):
                errors = MODULE.validate_metadata_paths(
                    text.replace(f'      - "{path}"\n', "", 1)
                )
                self.assertTrue(
                    any("pull_request paths omit" in error for error in errors)
                )

    def test_metadata_lane_parses_both_closed_sdk_configurations(self) -> None:
        text = (ROOT / ".github/workflows/yocto-metadata.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("Parse closed direct-eSDK configurations", text)
        self.assertIn("for lab in pci-x86-64 platform-arm64", text)
        self.assertIn("configure-sdk --build-dir", text)
        self.assertIn("SDK_BBPATH=$(bitbake-getvar --value BBPATH)", text)
        self.assertIn("verify-sdk --build-dir", text)

    def test_full_action_sha_is_required(self) -> None:
        path = self.workflow(SAFE.replace(
            "de0fac2e4500dabe0009e67214ff5f5447ce83dd", "v6"
        ))
        errors = MODULE.validate_workflow(path)
        self.assertTrue(any("full commit SHA" in error for error in errors))

    def test_non_github_action_owner_is_rejected_even_when_pinned(self) -> None:
        path = self.workflow(SAFE.replace("actions/checkout@", "third-party/checkout@"))
        errors = MODULE.validate_workflow(path)
        self.assertTrue(any("not GitHub-owned" in error for error in errors))

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

    def test_privileged_flow_sequence_triggers_are_rejected(self) -> None:
        for event, reason in (
            ("pull_request_target", "privileged context"),
            ("workflow_run", "privileged boundary"),
        ):
            with self.subTest(event=event):
                path = self.workflow(
                    SAFE.replace("on: [pull_request]", f"on: [{event}]", 1)
                )
                self.assertTrue(
                    any(reason in error for error in MODULE.validate_workflow(path))
                )

    def test_quoted_or_escaped_flow_triggers_are_rejected(self) -> None:
        for declaration in (
            'on: ["pull_request"]',
            r'on: ["pull_request\u005ftarget"]',
            r'on: ["workflow\x5frun"]',
        ):
            with self.subTest(declaration=declaration):
                path = self.workflow(
                    SAFE.replace("on: [pull_request]", declaration, 1)
                )
                self.assertTrue(
                    any(
                        "unquoted ASCII event names" in error
                        for error in MODULE.validate_workflow(path)
                    )
                )

    def test_trigger_words_in_comments_do_not_change_event_validation(self) -> None:
        path = self.workflow(
            SAFE + "# pull_request_target and workflow_run are not configured\n"
        )
        errors = MODULE.validate_workflow(path)
        self.assertFalse(any("privileged" in error for error in errors), errors)

    def test_bracket_form_secret_is_rejected(self) -> None:
        path = self.workflow(SAFE + "# ${{ secrets['TOKEN'] }}\n")
        self.assertTrue(
            any("repository secrets" in error for error in MODULE.validate_workflow(path))
        )

    def test_bare_secrets_and_github_token_are_rejected(self) -> None:
        for expression, expected in (
            ("${{ toJSON(secrets) }}", "repository secrets"),
            ("${{ github.token }}", "GitHub expressions"),
        ):
            with self.subTest(expression=expression):
                path = self.workflow(
                    SAFE.replace(
                        "    steps:\n",
                        f"    env:\n      UNTRUSTED: {expression}\n    steps:\n",
                        1,
                    )
                )
                self.assertTrue(
                    any(expected in error for error in MODULE.validate_workflow(path))
                )

    def test_whole_or_dynamic_github_context_is_rejected(self) -> None:
        for expression in (
            "${{ toJSON(github) }}",
            "${{ github['token'] }}",
            '${{ GITHUB [ "token" ] }}',
            "${{ github.*.token }}",
        ):
            with self.subTest(expression=expression):
                path = self.workflow(
                    SAFE.replace(
                        "    steps:\n",
                        f"    env:\n      PROBE: {expression}\n    steps:\n",
                        1,
                    )
                )
                self.assertTrue(
                    any(
                        "GitHub expressions" in error
                        for error in MODULE.validate_workflow(path)
                    )
                )

    def test_duplicate_mapping_keys_are_rejected_in_their_scope(self) -> None:
        cases = {
            "trigger": SAFE.replace(
                "permissions:\n",
                "on: [workflow_dispatch]\npermissions:\n",
                1,
            ),
            "runner": SAFE.replace(
                "    runs-on: ubuntu-24.04\n",
                "    runs-on: ubuntu-24.04\n    runs-on: persistent-runner\n",
                1,
            ),
            "checkout": SAFE.replace(
                "          persist-credentials: false\n",
                "          persist-credentials: false\n"
                "          persist-credentials: true\n",
                1,
            ),
        }
        for name, text in cases.items():
            with self.subTest(case=name):
                errors = MODULE.validate_workflow(self.workflow(text))
                self.assertTrue(
                    any("repeats mapping key" in error for error in errors),
                    errors,
                )

    def test_noncanonical_yaml_cannot_hide_security_mappings(self) -> None:
        cases = {
            "spaced uses": SAFE.replace("uses:", "uses :", 1),
            "quoted uses": SAFE.replace("uses:", '"uses":', 1),
            "spaced trigger": SAFE.replace(
                "on: [pull_request]", "on:\n  pull_request_target :"
            ),
            "quoted trigger": SAFE.replace(
                "on: [pull_request]", 'on:\n  "pull_request_target":'
            ),
            "quoted permissions": SAFE.replace(
                "    steps:\n",
                '    "permissions":\n      contents: "write"\n    steps:\n',
                1,
            ),
            "anchor": SAFE.replace("  test:\n", "  test: &shared\n", 1),
            "alias": SAFE.replace("    steps:\n", "    steps: *shared\n", 1),
            "mapping merge": SAFE.replace(
                "    steps:\n", "    <<: *shared\n    steps:\n", 1
            ),
            "tag": SAFE.replace(
                "runs-on: ubuntu-24.04", "runs-on: !!str ubuntu-24.04", 1
            ),
            "flow mapping": SAFE.replace(
                "runs-on: ubuntu-24.04",
                "runs-on: {group: persistent-runners, labels: linux}",
                1,
            ),
            "explicit key": SAFE.replace(
                "      - uses:", "      - ? uses\n        :", 1
            ),
            "multiline key": SAFE.replace(
                "      - uses:", "      - uses\n        :", 1
            ),
        }
        for name, text in cases.items():
            with self.subTest(case=name):
                errors = MODULE.validate_workflow(self.workflow(text))
                self.assertTrue(
                    any("unsupported noncanonical YAML" in error for error in errors),
                    errors,
                )

    def test_sequence_block_scalar_does_not_hide_sibling_mappings(self) -> None:
        checkout = (
            "      - uses: "
            "actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd\n"
        )
        cases = {
            "spaced-action-key": SAFE.replace(
                checkout,
                "      - name: |\n"
                "          Display text\n"
                "        uses : attacker/example@v1\n",
                1,
            ),
            "quoted-action-key": SAFE.replace(
                checkout,
                "      - name: >\n"
                "          Display text\n"
                '        "uses": attacker/example@v1\n',
                1,
            ),
            "multi-space-quoted-action-key": SAFE.replace(
                checkout,
                "      -   name: |\n"
                "            Display text\n"
                '          "uses": attacker/example@v1\n',
                1,
            ),
            "tagged-action-value": SAFE.replace(
                checkout,
                "      - name: |\n"
                "          Display text\n"
                "        uses: !external attacker/example@v1\n",
                1,
            ),
            "anchored-action-value": SAFE.replace(
                checkout,
                "      - name: |\n"
                "          Display text\n"
                "        uses: &external attacker/example@v1\n",
                1,
            ),
            "duplicate-step-key": SAFE.replace(
                checkout,
                "      - name: |\n"
                "          Display text\n"
                "        name: Hidden duplicate\n"
                + checkout.replace("      - ", "        ", 1),
                1,
            ),
            "multi-space-duplicate-step-key": SAFE.replace(
                checkout,
                "      -   name: |\n"
                "            Display text\n"
                "          name: Hidden duplicate\n"
                + checkout.replace("      - ", "          ", 1),
                1,
            ),
        }
        for name, text in cases.items():
            with self.subTest(case=name):
                errors = MODULE.validate_workflow(self.workflow(text))
                if name == "spaced-action-key":
                    self.assertTrue(
                        any(
                            "whitespace before mapping colons" in error
                            for error in errors
                        ),
                        errors,
                    )
                elif name in {
                    "duplicate-step-key",
                    "multi-space-duplicate-step-key",
                }:
                    self.assertTrue(
                        any("repeats mapping key" in error for error in errors),
                        errors,
                    )
                else:
                    self.assertTrue(
                        any("unsupported noncanonical YAML" in error for error in errors),
                        errors,
                    )

    def test_sequence_block_scalar_exposes_allowed_sibling_keys(self) -> None:
        cases = {
            "ordinary": (
                "      - run: |\n          printf '%s\\n' safe\n",
                "        env:",
            ),
            "wide-sequence": (
                "      -   run: >\n            printf '%s\\n' safe\n",
                "          shell: bash",
            ),
            "conditional": (
                "      - run: |\n          printf '%s\\n' safe\n",
                "        if: true",
            ),
        }
        for name, (prefix, sibling) in cases.items():
            with self.subTest(case=name):
                lines = [
                    line
                    for _, line in MODULE.structural_lines(prefix + sibling + "\n")
                ]
                self.assertIn(sibling, lines)

    def test_persistent_runner_groups_are_rejected(self) -> None:
        path = self.workflow(
            SAFE.replace(
                "    runs-on: ubuntu-24.04\n",
                "    runs-on:\n      group: persistent-runners\n      labels: linux\n",
                1,
            )
        )
        self.assertTrue(
            any(
                "ubuntu-24.04 hosted runner" in error
                for error in MODULE.validate_workflow(path)
            )
        )

    def test_banned_features_remain_rejected_with_alternate_key_spelling(self) -> None:
        cases = (
            SAFE.replace("uses:", '"uses":', 1).replace(
                "actions/checkout@", "actions/cache@", 1
            ),
            SAFE.replace("uses:", "uses :", 1).replace(
                "actions/checkout@", "actions/upload-artifact@", 1
            ),
            SAFE.replace(
                "    steps:\n",
                "    continue-on-error : true\n    steps:\n",
                1,
            ),
        )
        for text in cases:
            with self.subTest():
                self.assertNotEqual([], MODULE.validate_workflow(self.workflow(text)))

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

    def test_malformed_policy_values_return_bounded_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            policy_path = root / MODULE.TRUST_POLICY
            policy_path.parent.mkdir(parents=True)
            policy = json.loads(
                (ROOT / MODULE.TRUST_POLICY).read_text(encoding="utf-8")
            )
            policy["ruleset"]["required_status_checks"]["checks"][0][
                "context"
            ] = ["repository"]
            policy_path.write_text(json.dumps(policy), encoding="utf-8")
            text = (ROOT / ".github/workflows/fast-checks.yml").read_text(
                encoding="utf-8"
            )
            errors = MODULE.validate_trust_policy_binding(root, text)
            self.assertTrue(
                any("required check values must be strings" in error for error in errors)
            )

    def test_policy_binding_rejects_boolean_integer_substitution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            policy_path = root / MODULE.TRUST_POLICY
            policy_path.parent.mkdir(parents=True)
            policy = json.loads(
                (ROOT / MODULE.TRUST_POLICY).read_text(encoding="utf-8")
            )
            policy["actions"]["enabled"] = 1
            policy_path.write_text(json.dumps(policy), encoding="utf-8")
            text = (ROOT / ".github/workflows/fast-checks.yml").read_text(
                encoding="utf-8"
            )
            errors = MODULE.validate_trust_policy_binding(root, text)
            self.assertTrue(
                any("Actions policy differs" in error for error in errors),
                errors,
            )


if __name__ == "__main__":
    unittest.main()
