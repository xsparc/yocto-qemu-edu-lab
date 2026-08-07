<!--
SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
SPDX-License-Identifier: MIT
-->

# Project context

- Active task: none. A001 is Done in pull request #2; A002 remains Proposed and unapproved.
- Current branch: `milestone/m1-reproducible-setup`.
- Baseline: one x86-64 Yocto 6.0 (`wrynose`) learning machine using QEMU EDU PCI device `1234:11e8`.
- Existing runtime features: PCI discovery, BAR0 MMIO, legacy INTx, sysfs, factorial/liveness operations, and a guest smoke test.
- Current license boundary: infrastructure and learning material are MIT; kernel module source and its module Makefile are GPL-2.0-only.
- Yocto 6.0 uses separate BitBake, OE-Core, and meta-yocto repositories; the old Poky combo repository is not a valid Wrynose source.
- M1 locks Yocto 6.0.2 source metadata through `config/sources.lock.json`; recipe downloads, full image output, and runtime evidence remain separate claims.
- Full Yocto builds require Linux/WSL2 and substantial disk/time; the present Windows session can run repository-local checks and Git Bash syntax checks, while GitHub-hosted Linux validates source resolution and metadata.
- M0 was squash-merged through pull request #1 as commit `cc72890cb2fc5258bec1fbdd8c58e2ed44458749`.
- M1 resolves exact Yocto 6.0.2 sources, reconciles locked build configuration, and provides green fast and Linux metadata evidence through pull request #2.
- Pull request #2 passed repository, static, licensing, source sync, setup, parse, inspection, and native layer checks at `09344b334d9ccbf74242b572ea6718adbc36830c`; it is not merged or released.
- Next safe action: maintainer review and merge decision for pull request #2. M2 requires that merge plus separate explicit approval.
- Public workflow state uses tool-neutral maintainer paths while preserving the same task, approval, validation, review, and handoff semantics.
