<!--
SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
SPDX-License-Identifier: MIT
-->

# Project context

- Active task: A004, the approved M4 bounded DMA learning slice.
- Current branch: `docs/a004-merge-record`.
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
- A007 backports the fix only to `qemu-system-native` when the configured
  machine is `qemu-edu-x86-64`; adding the layer to an unrelated machine must
  remain signature-neutral. The native recipe reaches testimage through
  `qemu-helper-native`. Manual and OEQA boot paths share an exact append,
  patch/source, and consumer-executable gate, refusing `runqemu` host fallback.
  Unsafe out-of-bounds input is never executed as a validation method.
- A007 clean commit `46e2280` passed patched-emulator compilation, exact
  consumer verification, a warning-free image rebuild, all 14 project runtime
  cases, licensing, and independent review.
- Pull request #5 passed its hosted fast and metadata gates, then squash-merged
  as `083ddf5e1207dac34bdaf12e04a41f1f1faa8d7f`; no tag or release was
  published.
- A004 is approved as a length-only bounded DMA curriculum. It adds one managed
  4,096-byte coherent buffer under the 28-bit mask, a fixed-offset two-direction
  round trip, DMA completion and timeout handling, fail-closed teardown, guest
  interface version 3, and closed runtime evidence version 3. Arbitrary DMA
  addresses, streaming DMA, physical-hardware claims, and source-lock updates
  remain out of scope. M5 and M6 remain Proposed and unapproved.
- A004 clean implementation commit
  `8574eaffe206f8235a5da57461ded0ecbdbbf60b` passed the complete 94-test Linux
  repository suite, the exact Yocto 6.0.2 driver and image build, software-QEMU
  boot, ping, SSH, and all 19 project cases. Closed version-3 evidence records
  `dirty=false`, `testimage_exit_code=0`, 19/19 project passes, and all five DMA
  completion claims true. The isolated exact-lock layer check also passed all
  13 applicable BSP/common checks. The evidence SHA-256 is
  `f97b24335cd9579eaf825cf1c06e54ae1742f069f1afa2a4c8e6fa2f162856c2`; the
  bound native OEQA SHA-256 is
  `1f8b1756faf079a0996070846f4e4aee5535e71d205f5e232c9cbeff395e07c5`.
  Pull request #6 passed Hosted Fast checks run `31312516815` and Yocto
  metadata run `31312516778` at
  `fbb2cab55ea6fc6a9000a1e172d71ef82a892a4b`, then squash-merged as
  `918efaa392486af73f03ac9d1e216c2a2ed421da`. Required reviews, tag, and
  release remain pending.
- Public workflow state uses tool-neutral maintainer paths while preserving the same task, approval, validation, review, and handoff semantics.
