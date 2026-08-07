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
