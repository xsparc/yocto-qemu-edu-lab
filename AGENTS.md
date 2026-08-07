<!--
SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
SPDX-License-Identifier: MIT
-->

# Repository operating contract

This project is a public educational Yocto/QEMU lab. Prefer small changes that
can be taught, tested, reviewed, and reverted independently.

## Start every session

1. Inspect `git status --short --branch` and do not overwrite unrelated work.
2. Read `.agents/memory.md`, `.agents/tasks.toml`, and `.agents/ledger.md`.
3. Run `python3 scripts/validate_workflow.py`.
4. Select the single `In Progress` task, or orient on Proposed work without
   implementing it.
5. Read only the relevant vision, architecture, roadmap, code, and tests.

## Source-of-truth order

1. `docs/vision.md` — users, outcomes, principles, and non-goals.
2. `docs/architecture.md` — current system and target boundaries.
3. `docs/roadmap.md` — milestone sequence and acceptance gates.
4. `.agents/tasks.toml` — executable state, approvals, dependencies, evidence.
5. `.agents/ledger.md` — readable view of task state.
6. `.agents/decisions.md` and `.agents/memory.md` — durable choices and facts.
7. Code, recipes, tests, and observed build/runtime evidence.
8. Supporting documentation.

When sources disagree, preserve safe behavior and record the conflict. Do not
silently pick the convenient answer.

## Task and pull-request policy

- Proposed work is not approved work.
- Ready and In Progress require user approval recorded in `tasks.toml`.
- Keep at most one task In Progress.
- Implement one milestone per branch and pull request.
- A task is Done only after acceptance criteria, validation, independent review,
  documentation, ledger, decisions, and memory agree with reality.
- Do not merge, publish a release, alter production, incur costs, or perform a
  destructive action unless the user explicitly authorized that scope.

## Engineering boundaries

- Keep the lab usable offline after its declared sources are available.
- Prefer deterministic commands and versioned machine-readable output.
- Treat optional AI or MCP support as an adapter over the same local contracts;
  never require an LLM to build, boot, test, or understand the lab.
- Declare Yocto, QEMU, kernel, architecture, and hardware compatibility only
  when supported by recorded evidence.
- Unknown, skipped, or unavailable validation is a gap, not a pass.

## Licensing and public history

- Follow `docs/licensing.md` and `REUSE.toml` before copying any external work.
- Project infrastructure is MIT. The kernel module source and its module
  Makefile are GPL-2.0-only. Recipe `LICENSE` metadata describes packaged
  content and does not automatically license the recipe file itself.
- Do not vendor content whose provenance or redistribution rights are unclear.
- Keep commits and pull requests concise, natural, and reviewable. Never invent
  a person, human review, test result, provenance, or required disclosure.

## Validation and closeout

Run the commands in `.agents/config.toml`, then inspect `git diff` and
`git diff --check`. Record exact commands and results in the active task. Update
`SHA256SUMS` last with `python3 scripts/update_checksums.py`.

Final handoff must state the task and status, outcome, changed areas, commands
actually run, review findings, unresolved risks, and the next safe action.
