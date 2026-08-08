<!--
SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
SPDX-License-Identifier: MIT
-->

# Project context

- Active task: A007, the approved M3.1 host-emulator bounds hardening slice.
- Current branch: focused A007 implementation branch.
- Baseline: one x86-64 Yocto 6.0 (`wrynose`) learning machine using QEMU EDU PCI device `1234:11e8`.
- Existing merged runtime features: PCI discovery, BAR0 MMIO, managed MSI/INTx
  selection, sysfs, factorial/liveness operations, and automated guest
  verification.
- Current license boundary: infrastructure and learning material are MIT; kernel module source and its module Makefile are GPL-2.0-only.
- Yocto 6.0 uses separate BitBake, OE-Core, and meta-yocto repositories; the old Poky combo repository is not a valid Wrynose source.
- M1 locks Yocto 6.0.2 source metadata through `config/sources.lock.json`; recipe downloads, full image output, and runtime evidence remain separate claims.
- Full Yocto builds require Linux/WSL2 and substantial disk/time; the present Windows session can run repository-local checks and Git Bash syntax checks, while GitHub-hosted Linux validates source resolution and metadata.
- M0 was squash-merged through pull request #1 as commit `cc72890cb2fc5258bec1fbdd8c58e2ed44458749`.
- M1 resolves exact Yocto 6.0.2 sources, reconciles locked build configuration, and provides green fast and Linux metadata evidence through pull request #2.
- Pull request #2 passed repository, static, licensing, source sync, setup, parse, inspection, and native layer checks, then squash-merged as `b269b002500059ee31754b7868c0b5a250089f0a`; no release was published.
- A002 clean-revision validation at `64796817412a4b582723165f0413be6edf3891c1` built the complete image and passed ping, SSH, and all 11 project OEQA cases under software QEMU. The closed version-1 evidence records `dirty=false` and was independently verified.
- Pull request #3 passed its hosted fast and metadata gates, then squash-merged
  as `d40e2db33e74b7b91ee07ad389a99cdf405b98df`; no tag or release was
  published.
- M3 uses one managed PCI IRQ vector with a read-only `auto`, `msi`, or `intx`
  load policy. Runtime tests use the endpoint-scoped Linux `msi_bus` testing
  ABI to prove real fallback and strict-MSI failure without a synthetic driver
  fault hook.
- A003 clean commit `3ea020489152f4c0080a37c5a04918cf7c888b0f`
  passed the exact locked image path, software-QEMU boot, ping, SSH, and all 14
  project cases. Closed evidence version 2 records `dirty=false` and validates
  with every interrupt and negative-path completion claim true.
- Pull request #4 passed its hosted fast and metadata gates, then squash-merged
  as `2daea1223775c8aff91a0a7db3b8cdd693f74195`; no tag or release was
  published.
- Exact locked QEMU 10.2.0 only logs an invalid EDU DMA buffer range before
  continuing the copy. Upstream commit
  `42f599172ae023924f288e20af0ceed681674747` makes the check fail closed in
  both directions. Released QEMU 10.2.4 predates that fix.
- A007 backports the fix only to `qemu-system-native`, which reaches testimage
  through `qemu-helper-native`. Manual and OEQA boot paths share an exact
  patch/source and consumer-executable gate, refusing `runqemu` host fallback.
  Unsafe out-of-bounds input is never executed as a validation method.
- A007 clean commit `46e2280` passed patched-emulator compilation, exact
  consumer verification, a warning-free image rebuild, all 14 project runtime
  cases, licensing, and independent review.
- Next safe action: publish the focused A007 pull request, pass hosted fast and
  metadata checks, review, and merge. M4, M5, and M6 remain Proposed and
  unapproved.
- Public workflow state uses tool-neutral maintainer paths while preserving the same task, approval, validation, review, and handoff semantics.
