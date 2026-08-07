<!--
SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
SPDX-License-Identifier: MIT
-->

# Decisions

## D-001: Deterministic core before AI adapters

- Status: Accepted on 2026-08-07.
- Decision: Build stable local commands and versioned evidence formats first.
  AI and MCP integrations may later adapt those contracts but must not become a
  build, test, or learning prerequisite.
- Reason: This preserves offline use, provider choice, testability, and a clear
  safety boundary.

## D-002: One milestone per pull request

- Status: Accepted on 2026-08-07 from the repository owner request.
- Decision: Each milestone gets one focused branch and pull request. Dependent
  milestones start only after prerequisite state is reconciled.
- Reason: Public review, rollback, bisectability, and licensing inspection stay
  bounded.

## D-003: No ambiguous-license vendoring

- Status: Accepted on 2026-08-07.
- Decision: Do not copy tools, skills, templates, snippets, media, or generated
  assets into the repository unless their source and redistribution terms are
  known and recorded. Reimplement small project-specific utilities under the
  project license when appropriate.
- Reason: An attempted workflow bootstrap exposed an installer bundle without
  redistribution terms; its generated files were removed before staging.

## D-004: Compatibility is declared only with evidence

- Status: Accepted on 2026-08-07.
- Decision: `LAYERSERIES_COMPAT`, host support, architectures, interrupt modes,
  and hardware claims may be expanded only when the corresponding build or
  runtime evidence exists.
- Reason: Unknown or unavailable checks are evidence gaps, not passes.

## D-005: Public workflow state is tool-neutral

- Status: Accepted on 2026-08-07 from the repository owner request.
- Decision: Keep the operating contract in `MAINTAINERS.md` and durable state
  under `docs/maintainers/`. People and automation consume the same task,
  approval, evidence, and review model without requiring tool-specific public
  scaffolding or making unsupported authorship claims.
- Reason: A public open-source workflow should remain understandable and useful
  when contributors use different editors, automation, or no automation at all.

## D-006: Lock the split Yocto source repositories in a project format

- Status: Accepted on 2026-08-07 for M1.
- Decision: Resolve Yocto 6.0.2 from exact BitBake, OE-Core, and meta-yocto
  commits in a closed, versioned JSON schema. Keep kas and upstream
  `bitbake-setup` as migration candidates rather than M1 dependencies.
- Reason: The Poky combo repository stopped receiving new series after Yocto
  5.2. Three fixed repositories do not yet justify another host dependency,
  while a small transparent contract is easier to teach and translate later.
- Revisit when: an external BSP or QEMU repository is added, multiple build
  configurations need composition, or signed-source policy is introduced.

## D-007: Separate fast, metadata, and full runtime evidence

- Status: Accepted on 2026-08-07 for M1.
- Decision: Run secret-free fast checks on every pull request and a path-scoped
  Linux metadata lane for locked checkout, parse, environment, and layer
  validation. Do not call those checks a full image build or runtime test.
- Reason: Standard public runners are useful for metadata but do not meet the
  documented storage and memory baseline for honest full Yocto evidence.

## D-008: Begin with a pre-release SemVer identity

- Status: Accepted on 2026-08-07 for M1.
- Decision: Record `0.1.0-dev` as the development identity. A version string
  does not create a release; tags and publication remain separately approved.
- Reason: Source-lock and command contracts need a compatibility vocabulary
  before integrations consume them, without implying that the unvalidated
  runtime curriculum has already been released.

## D-009: Bound the BitBake namespace exception to disposable metadata CI

- Status: Accepted on 2026-08-08 for M1.
- Decision: On Ubuntu 24.04, disable the AppArmor unprivileged-user-namespace
  restriction only inside the disposable GitHub-hosted metadata VM and verify
  the combined user/network namespace operation before running BitBake. Do not
  apply this exception to persistent runners or production hosts by default.
- Reason: BitBake requires namespaces for task isolation, while Ubuntu 24.04
  enables a conflicting mitigation. The public PR job has read-only permission,
  no secrets or persisted credentials, no artifacts, and no durable host state.
- Revisit when: the runner image or BitBake behavior changes, or metadata moves
  to a persistent runner with a narrower AppArmor profile.

## D-010: Version the M2 contracts as 0.2.0-dev

- Status: Accepted on 2026-08-08 for A002; no tag or release is authorized.
- Decision: Advance the development identity from `0.1.0-dev` to `0.2.0-dev`
  because M2 adds a curriculum stage, documents the guest interface, exposes a
  read-only module-load test seam, and introduces runtime evidence schema 1.
- Reason: The pre-1.0 policy assigns new curriculum stages and public contracts
  to a minor line. Schema versioning remains independent of project SemVer.
