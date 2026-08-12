<!--
SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
SPDX-License-Identifier: MIT
-->

# Project context

- Active task: A005, the approved M5 ARM64 platform-driver learning slice.
- Current public baseline: A004 documentation closeout commit `01ff717`; the
  last runtime-affecting A004 baseline remains correction commit
  `ebbf1db0a5f8f2b30d7580a2435f67e9db5cc940`.
- Baseline: one x86-64 Yocto 6.0 (`wrynose`) learning machine using QEMU EDU PCI device `1234:11e8`.
- Existing merged runtime features: PCI discovery, BAR0 MMIO, managed MSI/INTx
  selection, sysfs, factorial/liveness operations, and automated guest
  verification.
- Current license boundary: infrastructure, learning material, recipes, and
  user-space tools are MIT; both example kernel-module implementations and the
  project-local QEMU platform patch are GPL-2.0-only; the platform Device Tree
  binding is dual licensed GPL-2.0-only OR BSD-2-Clause; the attributed QEMU
  EDU bounds backport remains MIT.
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
- A007 originally scoped the bounds fix to `qemu-edu-x86-64`. A005 composes it
  with the platform-device patch as one identical `qemu-system-native` input set
  for both project machines, while unrelated machines remain signature-neutral.
  The native recipe reaches testimage through `qemu-helper-native`. Manual and
  OEQA boot paths share an exact append,
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
  remain out of scope.
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
  `918efaa392486af73f03ac9d1e216c2a2ed421da` without a tag or release. The
  focused post-merge correction strengthens
  `test_14_dma_contract` so an added driver-created sysfs file invalidates the
  address-free evidence claim. Clean correction commit `fe08e73` passed all 94
  Linux repository tests, locked setup and QEMU-consumer preflight, all 4,738
  cached image tasks, and a fresh software-QEMU run containing ping, SSH, and
  all 19 project cases. The result was 21/21 in 172.305 seconds with no skips,
  failures, or errors. Its evidence SHA-256 is `c51de37dc60c69e5f697fb0ae8ab74fbc1c0520724554b73904783533ca2b4ea`;
  the bound native OEQA SHA-256 is `918a7ade794afbc958c428eff358e2f5740e6e89bb63f8bb90d063b014a419a9`.
  Quality, architecture, security, and independent frozen-diff reviews approved
  the correction with no P0-P2 findings. Review-record commit `a3a42b6` passed
  hosted Fast checks run `31397396385` and Yocto metadata run `31397396470`.
  Final pull-request head `89a4be3` passed Fast checks run `31404164447` and
  Yocto metadata run `31404164649`; pull request #7 then squash-merged as
  `ebbf1db0a5f8f2b30d7580a2435f67e9db5cc940`. A004 is Done. No tag or release
  was published. Focused documentation closeout commit `5506322` then passed
  repository, static, and licensing jobs in Fast checks run `31491533350`;
  pull request #8 squash-merged that record as `01ff717` without changing the
  qualified implementation.
- A005 is approved as an additive ARM64 `virt` lab. It introduces a separate
  project-local SysBus device and generated `qemu,edu-platform` Device Tree
  node, a platform driver, versioned lab manifests, and separate platform
  evidence while preserving the x86-64 PCI lab as the no-argument default.
  RISC-V, DMA, physical validation, source-version upgrades, upstream QEMU
  submission, publication, merge, tag, and release remain outside A005.
- A005 clean build revision `782eb6d` compiled and packaged the ARM64 platform
  driver, completed all 4,702 image tasks, and verified the patched
  helper-native AArch64 emulator. Test-only corrections then produced clean
  runtime subject `2e4f87d`, where the ARM64 lab passed ping, SSH, and all nine
  project cases and the unchanged PCI lab completed all 4,738 image tasks and
  passed ping, SSH, and all 19 project cases. Both runs used software QEMU with
  no skips, failures, or errors. Platform evidence SHA-256 is `a4cb66bd7e57541d79df12a9deea8d9891fa34587b1c24e5314c01a4bae2fe40`;
  PCI evidence SHA-256 is `730ec74fbc4492cc574b93c50dccbae65bca2e8c1dba9fe30edb73caf15fe03c`.
- A005 host validation now passes 141 tests, both exact QEMU patch profiles,
  checksum and workflow gates, Device Tree schema 2026.6, and REUSE 6.2.0 over
  95/95 files. Thirteen native-Linux contract tests, final metadata/layer
  evidence, and the required independent reviews remain open; A005 therefore
  stays In Progress and unpublished.
- The unpublished A005 history was replayed onto public A004 closeout
  `01ff717`. The earlier `782eb6d` and `2e4f87d` runs remain useful
  pre-reconciliation local evidence, but they are not final evidence for the
  reconciled A005 branch. Exact-revision Linux qualification must be repeated
  before review or publication.
- Public workflow state uses tool-neutral maintainer paths while preserving the same task, approval, validation, review, and handoff semantics.
