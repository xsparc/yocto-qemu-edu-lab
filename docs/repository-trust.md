<!--
SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
SPDX-License-Identifier: MIT
-->

# Repository trust policy and evidence

The repository contains source-controlled security policy, but Git cannot show
whether the hosting service is currently enforcing that policy. M9 therefore
separates three things:

1. `config/repository-trust-policy.json` is the reviewed desired state.
2. `build/repository-trust/observation-v1.json` is a fixed, ignored,
   point-in-time input prepared from a separately authorized settings read.
3. `scripts/repository_trust.py evaluate` produces a deterministic, sanitized
   evidence projection on standard output.

The project command is not a GitHub client. It has no URL, token, network,
subprocess, mutation, or arbitrary-path interface. People, CI systems, or later
read-only adapters may prepare the same normalized observation without changing
the evidence contract.

## Desired state

The exact policy requires:

- a public repository with `main` as default, squash-only merge, and automatic
  topic-branch deletion;
- Actions enabled with read-only default workflow permission, no pull-request
  approval permission, full-SHA enforcement, and only GitHub-owned external
  actions;
- the selected active `Protect main` default-branch ruleset with no bypass
  actors, deletion and force-push protection, linear history, pull requests,
  and enforcement on branch creation;
- strict source-bound required contexts `diagnostics-schema`, `licensing`,
  `repository`, and `static`, all produced by the GitHub Actions app;
- no universal requirement for the path-scoped Yocto metadata job;
- Dependabot alerts and security updates, secret scanning and push protection,
  private vulnerability reporting, and the named contact `@xsparc`.

`scripts/validate_ci.py` binds the four policy contexts to the exact job IDs,
unchanged job-name semantics, reviewed command-surface fingerprints, and exact
unfiltered pull-request/main-push/manual triggers in
`.github/workflows/fast-checks.yml`. Required jobs cannot use job-level names,
conditions, dependencies, or strategies. Every job uses the approved GitHub-
hosted runner. The validator accepts a closed canonical YAML form and rejects
quoted or otherwise ambiguous mapping keys, mapping merges, aliases, tags, and
flow mappings before checking action ownership and pins, permissions, secrets,
tokens, privileged triggers, and prohibited workflow features. The digest-
pinned REUSE container is an external command executed by the workflow, not a
reusable GitHub Action. A deliberate workflow change must update its reviewed
fingerprint in the same inspectable change.

## Observation contract

The observation path is fixed:

```text
build/repository-trust/observation-v1.json
```

`build/` is ignored. Every path component must be a direct directory rather
than a symbolic link, junction, or other reparse point, and the file must be a
direct regular UTF-8 file no larger than 64 KiB. The read stays bound to that
path during opening: POSIX hosts traverse no-follow directory descriptors,
while Windows verifies the junction-resolved path of the opened file handle.
JSON objects reject duplicate, non-string, and unknown keys; strings are
restricted to printable ASCII so direction-changing and other hidden Unicode
controls cannot enter evidence. Integer width, nesting, total values, arrays,
and enums are bounded. A present field with the wrong shape is invalid input.
An unavailable setting is represented by omitting that field, which makes the
corresponding evidence check `unavailable` unless another known component of
the same check already conflicts with policy.

A complete normalized observation has this shape:

```json
{
  "schema_version": 1,
  "observed_at": "2026-08-30T00:00:00Z",
  "repository": {
    "visibility": "public",
    "default_branch": "main",
    "merge_methods": ["squash"],
    "delete_branch_on_merge": true
  },
  "actions": {
    "enabled": true,
    "allowed_actions": "selected",
    "sha_pinning_required": true,
    "default_workflow_permissions": "read",
    "can_approve_pull_request_reviews": false,
    "selected_actions": {
      "github_owned_allowed": true,
      "verified_allowed": false,
      "patterns_allowed": []
    }
  },
  "ruleset": {
    "name": "Protect main",
    "enforcement": "active",
    "target": "default_branch",
    "bypass_actor_count": 0,
    "deletion": true,
    "non_fast_forward": true,
    "linear_history": true,
    "do_not_enforce_on_create": false,
    "pull_request": {
      "required": true,
      "required_approving_review_count": 0,
      "allowed_merge_methods": ["squash"]
    },
    "required_status_checks": {
      "strict_required_status_checks_policy": true,
      "checks": [
        {"context": "diagnostics-schema", "source": "github-actions"},
        {"context": "licensing", "source": "github-actions"},
        {"context": "repository", "source": "github-actions"},
        {"context": "static", "source": "github-actions"}
      ]
    }
  },
  "security": {
    "dependabot_alerts": true,
    "dependabot_security_updates": true,
    "secret_scanning": true,
    "secret_scanning_push_protection": true,
    "private_vulnerability_reporting": true,
    "contact": "@xsparc"
  }
}
```

Before writing this file, normalize hosting-service responses outside the
repository command:

- select the intended repository-owned `Protect main` ruleset by its private
  identifier, then reduce its target to `default_branch` or `other`;
- replace the bypass-actor array with its count and discard actor identities;
- replace required-check application IDs and URLs with the reviewed source
  slug `github-actions`, after verifying the app that produced each current
  check;
- sort merge methods, selected-action patterns, and required checks by context;
- convert feature statuses to booleans; and
- discard numeric repository/ruleset/app IDs, users, teams, API URLs, raw
  responses, headers, tokens, local paths, and unrelated settings.

The timestamp is supplied by the observer and must be a whole-second UTC value.
It describes collection time; the evidence does not authenticate that clock.

## Commands and exit meanings

Validate the tracked policy, named security contact, workflow binding, and
tests with:

```bash
python3 scripts/repository_trust.py validate
python3 scripts/validate_ci.py
python3 -m unittest tests.test_repository_trust tests.test_validate_ci
```

Evaluate the fixed observation with:

```bash
python3 scripts/repository_trust.py evaluate
```

The evaluator always writes one canonical JSON document for a valid or absent
observation. Exit meanings are:

| Exit | Meaning |
|---|---|
| `0` | every required observed fact matches the policy |
| `1` | at least one observed fact conflicts with the policy |
| `2` | command usage, policy, local contract, or observation input is invalid |
| `3` | the observation is absent or at least one required fact is unavailable, with no observed conflict |

Schema 1 is closed and immutable after merge. Its `policy_sha256` is the
SHA-256 of the exact tracked policy bytes. Facts are the complete allowlisted
projection with `null` for unavailable values. Checks have fixed IDs and order;
failure outranks unavailable, and unavailable outranks pass. The existing exact
six-wheel, test-only CPython 3.12 oracle validates the JSON Schema independently
without becoming a runtime dependency.

## Live settings transaction

Live mutation is not implied by local implementation or pull-request approval.
After a draft pull request has passed the four Fast jobs, a maintainer may
separately authorize this bounded sequence:

1. Preflight administrative permission, public-repository feature eligibility
   and cost, and the identity and ownership of the intended `Protect main`
   ruleset. Inventory every applicable repository, organization, enterprise,
   and legacy branch-protection source.
2. Read and retain the exact pre-change repository, Actions, workflow,
   security, and protection state, including private identifiers, in an
   untracked local recovery file.
3. Verify all four current check runs came from the GitHub Actions app.
4. Set squash-only merging and automatic branch deletion, then re-read both.
5. Set Actions to `selected` with full-SHA enforcement, then allow GitHub-owned
   actions only and re-read the complete Actions state. Restore changes in this
   stage immediately if its second operation fails.
6. Enable Dependabot alerts and re-read, then enable Dependabot security
   updates and re-read.
7. Enable secret scanning and re-read it before enabling and re-reading push
   protection.
8. Enable private vulnerability reporting and re-read it.
9. Update the selected ruleset last, preserving its private identity,
   no-bypass policy, branch target, deletion, non-fast-forward, linear-history,
   and pull-request rules while adding strict source-bound checks and
   squash-only merge; re-read the complete ruleset.
10. Create only the sanitized observation, evaluate it, and run a fresh commit
    through the hosted Fast checks. Confirm exact context names, GitHub Actions
    source, non-skipped execution, and strict up-to-date behavior.

Treat an already-correct value as a verified no-op. On any error, stop and
restore only changed settings in this exact reverse order: selected ruleset,
private vulnerability reporting, push protection, secret scanning, Dependabot
security updates, Dependabot alerts, Actions, then merge settings. Re-read each
restoration and retain protection throughout. Rehearse at least one harmless
no-op or partial-failure rollback before claiming the live boundary complete.
Never disable active default-branch protection to bypass a merge problem. Raw
recovery data stays local and untracked. Publishing a sanitized evidence
document also needs an explicit scope decision; the fixed build output is not
automatically a public attestation.

## Evidence limits

A passing document proves only that every allowlisted fact in one normalized
observation matched the exact policy bytes. It does not prove:

- who collected the observation or that the timestamp is trusted;
- that the correct repository was queried beyond the observer's allowlisted
  project assertion;
- account security, MFA, collaborator permissions, check implementation
  correctness, or absence of hosting-service compromise;
- uniqueness or complete effect of protection: schema 1 observes only the
  selected ruleset, not additional applicable repository, organization, or
  enterprise rulesets or legacy branch protection;
- review independence, human authorship, continuous compliance, a release,
  provenance, signature, attestation, or OpenSSF/SLSA certification.

Consumers must treat old evidence as historical. A later provider-neutral
adapter may expose validation and evaluation results, but it must use the same
fixed paths and read-only semantics and needs its own approval.
