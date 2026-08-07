<!--
SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
SPDX-License-Identifier: MIT
-->

# Project context

- Active task: none. A002, M2 automated QEMU guest verification, is Done on its focused branch.
- Current branch: `milestone/m2-runtime-verification`.
- Baseline: one x86-64 Yocto 6.0 (`wrynose`) learning machine using QEMU EDU PCI device `1234:11e8`.
- Existing runtime features: PCI discovery, BAR0 MMIO, legacy INTx, sysfs, factorial/liveness operations, and a guest smoke test.
- Current license boundary: infrastructure and learning material are MIT; kernel module source and its module Makefile are GPL-2.0-only.
- Yocto 6.0 uses separate BitBake, OE-Core, and meta-yocto repositories; the old Poky combo repository is not a valid Wrynose source.
- M1 locks Yocto 6.0.2 source metadata through `config/sources.lock.json`; recipe downloads, full image output, and runtime evidence remain separate claims.
- Full Yocto builds require Linux/WSL2 and substantial disk/time; the present Windows session can run repository-local checks and Git Bash syntax checks, while GitHub-hosted Linux validates source resolution and metadata.
- M0 was squash-merged through pull request #1 as commit `cc72890cb2fc5258bec1fbdd8c58e2ed44458749`.
- M1 resolves exact Yocto 6.0.2 sources, reconciles locked build configuration, and provides green fast and Linux metadata evidence through pull request #2.
- Pull request #2 passed repository, static, licensing, source sync, setup, parse, inspection, and native layer checks, then squash-merged as `b269b002500059ee31754b7868c0b5a250089f0a`; no release was published.
- A002 clean-revision validation at `64796817412a4b582723165f0413be6edf3891c1` built the complete image and passed ping, SSH, and all 11 project OEQA cases under software QEMU. The closed version-1 evidence records `dirty=false` and was independently verified.
- Next safe action: publish the one focused A002 pull request and observe its hosted fast and metadata gates. M3, M5, and M6 remain Proposed and unapproved.
- Public workflow state uses tool-neutral maintainer paths while preserving the same task, approval, validation, review, and handoff semantics.
