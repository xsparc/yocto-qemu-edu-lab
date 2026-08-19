<!--
SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
SPDX-License-Identifier: MIT
-->

# Project context

- Active task: A008, SPDX image-composition evidence. Its manifest-schema-2,
  locked OE-Core parser, bounded local collector, and standard-library-only
  evidence-validator boundary were approved on 2026-08-19. Publication,
  merge, tag, and release remain unapproved.
- Current public baseline: A006 pull request #11 squash-merge
  `b569199513418fc6fc8a62453dca4751d3cf8969`. Historical dual-lab runtime
  qualification remains bound to clean A005 revision
  `340621afe3108d074e03f638b238d724bc10de5c`.
- Baseline: two Yocto 6.0 (`wrynose`) labs: the default x86-64 QEMU EDU PCI
  device `1234:11e8`, and an independent ARM64 `virt` platform device selected
  with `--lab platform-arm64`.
- Existing merged runtime features: PCI discovery, BAR0 MMIO, managed MSI/INTx,
  bounded DMA, Device Tree discovery, platform-driver MMIO and interrupts,
  sysfs diagnostics, and automated guest verification for both labs.
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
  completion claims true. The isolated exact-lock layer check ran 13
  BSP/common checks: 12 passed and the distro-class check was skipped as
  expected for a BSP layer. The evidence SHA-256 is
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
  RISC-V, platform-device DMA, physical validation, source-version upgrades,
  upstream QEMU submission, tag, and release remain outside A005.
- A005 implementation qualification covers clean commit `3244a0c` after
  replay onto public A004 closeout `01ff717`. All 141 Linux tests ran without
  skips; pinned static checks, REUSE 6.2.0 over 95/95 files, both metadata
  profiles, and the fresh dual-machine layer audit passed. The layer audit's
  machine-signature test confirms that both project machines select the same
  reviewed native QEMU patch set.
- The clean project driver/image reruns completed all 4,738 PCI tasks and all
  4,702 ARM64 tasks. Software QEMU passed 21/21 PCI tests and 11/11 ARM64 tests
  with no skips, failures, or errors. Platform-v1 evidence SHA-256 is
  `432e391555346582f7ccd2a8572fadd3f9c8200058d9a180f17a10fe46928824`; PCI-v3
  evidence SHA-256 is
  `823bffd64153516c928b108ce23a695e9d50d34bcc6754578edf3519cbb1d79e`.
  Following review corrections, clean final implementation revision `340621a`
  passed all 144 Linux tests without skips and REUSE 95/95. The affected ARM64
  tool and driver were rebuilt from cleansstate; the image completed 4,702
  tasks and software QEMU passed 11/11 tests. The no-argument wrapper selected
  PCI and passed 21/21 tests. Fresh platform-v1 evidence SHA-256 is
  `40550c299ec26e216c62ef5489774b53dc37c74658fab14d79588946fc311a9e`;
  fresh PCI-v3 evidence SHA-256 is
  `1a443dd4183eb843511e97f7751e72aa4e57b249dca545bc0c2dbba6e640a94d`.
  Architecture, quality, DevOps, security, licensing, and independent-diff
  reviews approved with no remaining P0-P2 findings. Published pull-request
  head `205384a62ca2a6f0738492aeedfddf850bc8529f` passed Fast checks run
  `31788645763` and Yocto metadata run `31788645797`; pull request #9 then
  squash-merged as `e2d703ecd017c6c8a2d94a23280bdb9d9da5f361`. A005 is
  Done; its documentation closeout then squash-merged through pull request #10
  as `5f1ba4d29e842723029764c290ec3a4e7dff68c9`. No tag or release was published.
- A006 advances the development identity to `0.6.0-dev` and adds four local,
  standard-library-only read commands over current project inputs and retained
  evidence. MCP, A2A, diagnostic network access, mutation, build orchestration,
  alternate evidence paths, publication, merge, tag, and release remain out of
  scope. The independent schema oracle is isolated to CI and may download only
  the six exact wheels in the checked-in lock after SHA-256 verification.
- Clean A006 implementation revision `25109d4f471492c0f2e101deca4f0a86c61c49a0`
  passes all 203 Windows-host tests with 16 expected native-Linux skips and all
  203 tests in a network-disabled,
  capability-free Linux CPython 3.12 environment with no skips and a read-only
  repository. Approval and closeout policy cannot be disabled by configuration;
  inspect source order is canonical; project-module import failures are
  sanitized; and the external schema oracle exercises populated evidence for
  both labs. Every JSON command emits a valid document with its declared exit,
  and the exact six-wheel size/digest/metadata/license verifier, ephemeral
  installed Draft 2020-12 oracle, actionlint, ShellCheck, and pinned REUSE
  108/108 gates pass. All seven required reviews approved with no remaining
  P0-P2 finding. Draft pull request #11 published the milestone; focused
  workflow-correction head `b68033923d6bc42eca06e1538aef0d745c1acd25`
  passed Fast checks run `32210876009` and Yocto metadata run `32210876013`.
  Final head `900c82f3936d9ffdf5a5499391abc368689332f6` passed Fast checks
  run `32212167852` and Yocto metadata run `32212167855`; pull request #11
  squash-merged as `b569199513418fc6fc8a62453dca4751d3cf8969`. A006 is Done.
  No tag or release was published.
- A008 advances the development identity to `0.7.0-dev` and changes lab
  manifests to schema 2. Each selected manifest names the exact required
  project packages and declared licenses, forbids the other lab's packages,
  and selects one generated evidence filename. The collector imports only the
  exact locked OE-Core SPDX 3.0.1 SHACL model, reads the raw SBOM once under a
  128 MiB bound, validates one document/build SBOM and its rootfs graph, and
  independently hashes every selected image artifact. The closed evidence
  document stays below 1 MiB and its validator remains standard-library-only.
  Raw SBOMs, images, build trees, and environment dumps stay ignored and are
  not public-CI artifacts. Full SPDX conformance, VEX freshness, reproducible
  builds, signing, attestations, SLSA, releases, physical hardware, source-lock
  updates, and network services are outside A008.
- Clean implementation revision
  `8588e29f86c30578df99a8ffacba598479130a0a` passed all 228 isolated Linux
  tests, the exact external schema oracle, REUSE 116/116, and every local
  source/lab/workflow/CI/QEMU/checksum gate. Real build execution corrected
  optional supplier-variable querying and pinned the exact versioned Yocto
  module package names before qualification.
- Both image recipes were rebuilt normally from `cleansstate` at that revision.
  The PCI graph completed 4,667 tasks and ARM64 completed 4,631; each reran 20
  image-recipe tasks including rootfs, image, and SPDX generation without
  warnings or failures. PCI evidence SHA-256 is
  `d4b6f88023a45888b32a875a106d27efca4e720d24313d5395091e81f1f1c05d`;
  ARM64 evidence SHA-256 is
  `02f6fe4d06df2a63780e0a859c51ddbc53dff0721d9c4ad96575c8463742140e`.
  Their raw SPDX digests are
  `2717b9c20b34bb1511ecfe091690e129003665fd0523fa3bdb69aa1562587b5a`
  and `9ac51c30d5a74b3538afaeea80d63831b9993f153c13e514f04b03005e1dee61`;
  both closed documents validate with clean-subject and current-input binding.
- The normally rebuilt images also passed the proportional software-QEMU
  requalification: PCI 21/21 in 174.238 seconds and ARM64 11/11 in 42.057
  seconds, with zero skips, failures, or errors. Fresh runtime evidence hashes
  are `e456a16f1369da9a60ed5aa661e954ee7d200f3780570a260c4923a3500f7b65`
  and `5519538f609f70a937e8dab7c66764aa9dddf42a2b66e460f95d38b67526eaa0`.
  Post-qualification hardening through final code candidate `b092b48` passed
  all 234 isolated Linux tests and preserved both retained graph results. All
  seven required review roles approved exact review head `31142b6` with no
  remaining P0-P2 finding. Publication, hosted gates, merge, tag, and release
  remain pending.
- Public workflow state uses tool-neutral maintainer paths while preserving the same task, approval, validation, review, and handoff semantics.
