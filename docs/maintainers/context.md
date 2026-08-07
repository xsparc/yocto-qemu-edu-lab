<!--
SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
SPDX-License-Identifier: MIT
-->

# Project context

- Active task: A000.
- Current public work: pull request #1 tracks the M0 project foundation.
- Baseline: one x86-64 Yocto 6.0 (`wrynose`) learning machine using QEMU EDU PCI device `1234:11e8`.
- Existing runtime features: PCI discovery, BAR0 MMIO, legacy INTx, sysfs, factorial/liveness operations, and a guest smoke test.
- Current license boundary: infrastructure and learning material are MIT; kernel module source and its module Makefile are GPL-2.0-only.
- Full Yocto builds require Linux/WSL2 and substantial disk/time; the present Windows session can run only repository-local fast checks.
- M0 local validation and independent review are complete with no remaining findings; full Yocto/QEMU runtime evidence is unavailable on this Windows host.
- Pull request #1 is open; GitHub reports it ready, mergeable, and in a clean merge state, with no repository checks configured yet.
- Public workflow state uses tool-neutral maintainer paths while preserving the same task, approval, validation, review, and handoff semantics.
