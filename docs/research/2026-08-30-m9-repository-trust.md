<!--
SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
SPDX-License-Identifier: MIT
-->

# M9 repository-trust direction brief

- `schema_version`: `1`
- `baseline_commit`: `f76402409e2d9706ead07f71282876a27fe91cc0`
- `scanned_at`: `2026-08-30`
- `coverage`: public open-source maintenance, GitHub repository and Actions
  controls, branch rulesets, vulnerability reporting, supply-chain guidance,
  and the current OpenSSF OSPS Baseline

This brief is advisory support for the already approved A010 boundary. It does
not authorize live settings changes or claim standards compliance.

## Findings

### 1. Immutable, least-privilege Actions policy

- `finding`: GitHub documents full-length commit SHA pinning as the immutable
  action reference and exposes repository policy for selected actions, SHA
  pinning, read-only default workflow permission, and pull-request approval
  permission. The current project workflows already use full SHAs and an exact
  read-only token boundary.
- `source_event_date`: `2026-08-30` documentation observation
- `citations`: [GitHub secure-use reference](https://docs.github.com/en/actions/reference/security/secure-use),
  [Actions permissions REST API](https://docs.github.com/en/rest/actions/permissions?apiVersion=2026-03-10)
- `confidence`: high
- `relevance`: direct repository supply-chain boundary
- `direction_alignment`: reinforces deterministic, secret-free public CI
- `opportunity_or_risk`: repository-level enforcement can prevent a workflow
  edit from silently widening the action namespace or using a mutable tag
- `engineering_cost`: low local policy cost; moderate settings rollout and
  rollback care
- `disposition`: adopt
- `roadmap_delta`: encode selected GitHub-owned actions, full-SHA enforcement,
  and read-only workflow defaults in M9
- `verification_needed`: re-read the effective settings and rerun all four Fast
  jobs after a separately authorized change

### 2. Source-bound strict required checks

- `finding`: GitHub rulesets can require an exact check and bind it to the
  expected GitHub App. Strict mode requires the topic branch to be current with
  the base. Linear history, pull requests, deletion protection, and blocked
  force pushes are separate rules. The metadata job is path-scoped, so making
  it universal would block unrelated pull requests that never create that job.
- `source_event_date`: `2026-08-30` documentation observation
- `citations`: [GitHub ruleset rules](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets)
- `confidence`: high
- `relevance`: direct merge-integrity and availability boundary
- `direction_alignment`: matches the project's exact evidence tiers and
  one-milestone-per-PR policy
- `opportunity_or_risk`: source binding limits forged status contexts; an
  accidental universal metadata requirement would create an availability bug
- `engineering_cost`: low after stable job IDs are locally enforced
- `disposition`: adopt
- `roadmap_delta`: require only `repository`, `static`, `diagnostics-schema`,
  and `licensing` from the GitHub Actions app; keep metadata advisory
- `verification_needed`: verify the app source of current check runs before the
  ruleset update and confirm a new pull-request head passes afterward

### 3. Coordinated vulnerability intake and dependency alerts

- `finding`: GitHub recommends Dependabot alerts and security updates for
  vulnerable dependencies, secret scanning and push protection for public
  repositories, a `SECURITY.md`, and private vulnerability reporting as a
  structured confidential intake path.
- `source_event_date`: `2026-08-30` documentation observation
- `citations`: [GitHub repository security quickstart](https://docs.github.com/en/code-security/getting-started/quickstart-for-securing-your-repository),
  [private vulnerability reporting](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/configure-vulnerability-reporting/configure-for-a-repository)
- `confidence`: high
- `relevance`: direct maintainer and reporter safety
- `direction_alignment`: adds hosting-service detection and intake without a
  project runtime dependency
- `opportunity_or_risk`: confidential reporting and automated alerts close
  current operational gaps; notifications still depend on maintainer settings
- `engineering_cost`: low, with a separate administrative transaction
- `disposition`: adopt
- `roadmap_delta`: name `@xsparc`, require the five selected feature states,
  and document that notification delivery is outside the evidence claim
- `verification_needed`: enable and re-read each feature separately; test the
  public reporting affordance without submitting a false vulnerability

### 4. Use OSPS as guidance, not a badge

- `finding`: the current OSPS Baseline is `v2026.08.28`; its release adds no
  controls, and Level 1 control OSPS-VM-02.01 requires documented security
  contacts. The baseline describes minimum controls by maturity, but a partial
  project mapping is not a self-certification.
- `source_event_date`: `2026-08-28`
- `citations`: [OSPS Baseline current version](https://baseline.openssf.org/),
  [2026-08-28 release notes](https://baseline.openssf.org/release_notes.html),
  [2026-08-28 control catalog](https://baseline.openssf.org/versions/2026-08-28.html)
- `confidence`: high
- `relevance`: open-source security expectations and security-contact gap
- `direction_alignment`: supports explicit evidence limits and actionable
  controls over marketing claims
- `opportunity_or_risk`: the named contact is a useful control; claiming broad
  compliance without evaluating account, collaborator, release, and other
  controls would be misleading
- `engineering_cost`: low for the contact; high and out of scope for a complete
  assessment
- `disposition`: adopt
- `roadmap_delta`: add the named contact and cite OSPS only as rationale; do not
  add an OSPS badge or compliance statement
- `verification_needed`: reassess the complete applicable control set before
  any future compliance claim

## Overall recommendation

Proceed with M9 as a closed desired-state policy plus a standard-library,
read-only evaluator over a fixed sanitized observation. Stage any live setting
changes only after a green draft pull request, preserve an exact recovery
record locally, update the ruleset last, and roll back in reverse order on any
failure. This improves source and merge trust while preserving CI portability,
provider neutrality, and honest evidence semantics.

## Evidence gaps

- The scan does not verify account MFA, collaborator permissions, notification
  delivery, or the hosting platform's internal enforcement.
- Live settings remain a point-in-time observation and may drift afterward.
- The repository has no release workflow, so release provenance, signing,
  SLSA, and artifact retention remain outside M9.
- A complete OSPS assessment and any code-scanning policy require separate
  scope, evidence, and maintainer approval.
