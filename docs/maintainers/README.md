<!--
SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
SPDX-License-Identifier: MIT
-->

# Maintainer workspace

This directory contains durable project state for maintainers and automation.
It is not a private transcript. Keep it compact, factual, and safe to publish.
Start with the repository-level `MAINTAINERS.md` operating contract.

## Lifecycle

`Proposed -> Ready -> In Progress -> Done`

Any executable state requires recorded user approval. A task can move to
`Blocked` from any non-Done state when its exact unblock condition is recorded.
Only one task may be `In Progress`.

## Files

- `config.toml` defines paths, invariants, and validation commands.
- `intake.md` preserves unsorted requests, assumptions, and open questions.
- `tasks.toml` is the machine-readable task source of truth.
- `ledger.md` is the human-readable task view.
- `context.md` contains compact current facts, not a session diary.
- `decisions.md` records consequential choices and their status.

Run `python3 scripts/validate_workflow.py` after changing this directory.
