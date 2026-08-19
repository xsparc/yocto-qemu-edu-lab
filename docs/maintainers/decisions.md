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

## D-006: Lock the split Yocto source repositories in a project format

- Status: Accepted on 2026-08-07 for M1.
- Decision: Resolve Yocto 6.0.2 from exact BitBake, OE-Core, and meta-yocto
  commits in a closed, versioned JSON schema. Keep kas and upstream
  `bitbake-setup` as migration candidates rather than M1 dependencies.
- Reason: The Poky combo repository stopped receiving new series after Yocto
  5.2. Three fixed repositories do not yet justify another host dependency,
  while a small transparent contract is easier to teach and translate later.
- Revisit when: an external BSP or QEMU repository is added, multiple build
  configurations need composition, or signed-source policy is introduced.

## D-007: Separate fast, metadata, and full runtime evidence

- Status: Accepted on 2026-08-07 for M1.
- Decision: Run secret-free fast checks on every pull request and a path-scoped
  Linux metadata lane for locked checkout, parse, environment, and layer
  validation. Do not call those checks a full image build or runtime test.
- Reason: Standard public runners are useful for metadata but do not meet the
  documented storage and memory baseline for honest full Yocto evidence.

## D-008: Begin with a pre-release SemVer identity

- Status: Accepted on 2026-08-07 for M1.
- Decision: Record `0.1.0-dev` as the development identity. A version string
  does not create a release; tags and publication remain separately approved.
- Reason: Source-lock and command contracts need a compatibility vocabulary
  before integrations consume them, without implying that the unvalidated
  runtime curriculum has already been released.

## D-009: Bound the BitBake namespace exception to disposable metadata CI

- Status: Accepted on 2026-08-08 for M1.
- Decision: On Ubuntu 24.04, disable the AppArmor unprivileged-user-namespace
  restriction only inside the disposable GitHub-hosted metadata VM and verify
  the combined user/network namespace operation before running BitBake. Do not
  apply this exception to persistent runners or production hosts by default.
- Reason: BitBake requires namespaces for task isolation, while Ubuntu 24.04
  enables a conflicting mitigation. The public PR job has read-only permission,
  no secrets or persisted credentials, no artifacts, and no durable host state.
- Revisit when: the runner image or BitBake behavior changes, or metadata moves
  to a persistent runner with a narrower AppArmor profile.

## D-010: Version the M2 contracts as 0.2.0-dev

- Status: Accepted on 2026-08-08 for A002; no tag or release is authorized.
- Decision: Advance the development identity from `0.1.0-dev` to `0.2.0-dev`
  because M2 adds a curriculum stage, documents the guest interface, exposes a
  read-only module-load test seam, and introduces runtime evidence schema 1.
- Reason: The pre-1.0 policy assigns new curriculum stages and public contracts
  to a minor line. Schema versioning remains independent of project SemVer.

## D-011: Make MSI preferred but keep interrupt policy observable

- Status: Accepted on 2026-08-08 for A003; no tag or release is authorized.
- Decision: Advance the development identity to `0.3.0-dev`. Request one PCI
  vector through a read-only `interrupt_mode=auto|msi|intx` module policy,
  defaulting to `auto`, and expose the resolved `msi` or `intx` mode per device.
  Use Linux's endpoint-scoped `msi_bus` testing ABI only while EDU is unbound to
  prove real automatic fallback and required-MSI failure. Emit runtime evidence
  schema 2 and retain validation of immutable version-1 evidence.
- Reason: This teaches the modern PCI allocation lifecycle, preserves an
  explicit comparison and operational rollback, avoids a synthetic driver fault
  control, and keeps old evidence consumable. The locked Linux 6.18 managed
  lifecycle installed after `pcim_enable_device()` means the driver must not
  manually free its allocated vector.

## D-012: Backport the upstream EDU DMA bounds fix before M4

- Status: Accepted on 2026-08-08 for A007; no merge, tag, or release is
  authorized by this decision.
- Decision: Backport QEMU commit
  `42f599172ae023924f288e20af0ceed681674747` to the exact
  `qemu-system-native_10.2.0` recipe consumed by `runqemu`. Require that
  reviewed version for the EDU machine, verify both patched DMA guards before
  boot, and advance the contract-preserving development identity to
  `0.3.1-dev`. Never execute the out-of-bounds proof of concept as a gate.
- Reason: The locked QEMU source only logs an invalid EDU device-buffer range
  and then continues the DMA copy. The upstream fix makes the range check
  return a boolean and skips both transfer directions on failure. The latest
  released 10.2 point predates the fix, while M4 will intentionally exercise
  the EDU DMA engine.
- Revisit when: the supported QEMU recipe includes the fix upstream. Remove the
  backport only after exact recipe selection, patch/source digests, guarded copy
  placement, compilation, fail-closed native-sysroot consumption, and the full
  runtime regression are reverified.

## D-013: Keep the DMA curriculum length-only and bounded

- Status: Accepted on 2026-08-09 for A004; no publication, merge, tag, or
  release is authorized by this decision.
- Decision: Advance the development identity to `0.4.0-dev`, guest interface
  to version 3, and runtime evidence to schema 3 while retaining validation of
  immutable schema 1 and 2 records. Allocate one managed 4,096-byte coherent
  buffer under the EDU 28-bit mask. Accept only a transfer length from 1
  through 4096, use the fixed EDU buffer offset, and perform a verified
  RAM-to-EDU-to-RAM round trip under one operation lock. Never expose or accept
  a DMA address. Require exact DMA-interrupt acknowledgement, bounded waits,
  barriers, and bus-master quiescence before managed memory release.
- Reason: A length-only teaching interface demonstrates coherent allocation,
  mask negotiation, both transfer directions, interrupt completion, bounds,
  and teardown without turning sysfs into an arbitrary DMA primitive. The
  already-qualified A007 host-emulator guard remains a mandatory prerequisite.
- Revisit when: a later curriculum stage has a separately reviewed need for
  streaming mappings or physical hardware. Such work must use a new interface
  version and must not weaken this bounded contract.

## D-014: Add the platform-driver lesson on ARM64 virt

- Status: Accepted on 2026-08-11 for A005; no publication, merge, tag, release,
  or upstream submission is authorized by this decision.
- Decision: Advance the development identity to `0.5.0-dev`. Add one ARM64
  machine derived from OE-Core `qemuarm64`, one independent
  `qemu-edu-platform` SysBus device on QEMU `virt`'s dynamic platform bus, and
  one generated `qemu,edu-platform` Device Tree binding. Add a GPL-2.0-only
  platform driver and a separate closed platform guest/runtime evidence
  contract version 1. Keep the PCI guest contract and evidence versions 1
  through 3 unchanged.
- Reason: ARM64 provides a direct, well-tested OE-Core QEMU path and teaches
  Device Tree discovery, resource mapping, interrupts, and platform lifecycle
  without adding the OpenSBI/U-Boot chain required by the RISC-V alternative.
  An independent device avoids pretending the PCI EDU register model is a
  portable hardware specification.
- Provenance boundary: the QEMU device patch is project-local and is not
  intended for upstream submission. Its source and integration use
  GPL-2.0-only; the external kernel module remains GPL-2.0-only; the Device
  Tree schema uses the kernel-preferred `(GPL-2.0-only OR BSD-2-Clause)`; project
  metadata remains MIT.
- Revisit when: the ARM64 lab has clean build/runtime evidence and a distinct
  RISC-V learning objective justifies the additional firmware and maintenance
  path.

## D-015: Select labs through closed manifests

- Status: Accepted on 2026-08-11 for A005.
- Decision: Add a versioned lab index with digest-bound manifests. A manifest
  selects build directory, machine, driver, image, layer order, emulator preflight,
  runtime suite, and evidence profile. All public wrappers accept `--lab`; an
  omitted selector means `pci-x86-64` and preserves the existing `build/` path.
  External Git identity remains in the source lock. New platform evidence
  records it separately from the selected manifest digest; immutable PCI
  evidence schemas 1 through 3 remain unchanged.
- Reason: A closed data contract scales to additional labs without duplicating
  entry points or spreading machine conditionals through shell scripts. Keeping
  PCI as the default preserves the current learning and command contracts.
- Revisit when: a third lab or external BSP makes composition expressive enough
  to justify translating these manifests to kas or upstream `bitbake-setup`.

## D-016: Keep the native QEMU input set invariant across project machines

- Status: Accepted on 2026-08-12 for A005.
- Decision: Apply both reviewed QEMU 10.2.0 patches—the attributed EDU bounds
  backport and project-local platform device—to `qemu-system-native` for both
  project machines. Apply neither patch to unrelated machines. Keep each lab's
  boot arguments and profile-specific post-patch source verification separate.
- Reason: `qemu-system-native` and `qemu-helper-native` are shared host-native
  providers. Machine-dependent recipe inputs give shared tasks different
  signatures and fail the BSP cross-machine contract. The two patches are
  independent and non-overlapping, so one exact project-machine input set
  preserves reproducibility without conflating the guest device interfaces.
- Revisit when: a later QEMU version includes either change, or upstream recipe
  structure provides a machine-independent equivalent. Any change must retain
  exact source verification and unrelated-machine signature neutrality.

## D-017: Make diagnostics deterministic, read-only, and provider-neutral

- Status: Accepted on 2026-08-14 for A006; publication, merge, tag, and release
  are not authorized by this decision.
- Decision: Advance the development identity to `0.6.0-dev`. Add a
  standard-library-only `qemu-edu-lab` command with `status`, `doctor`,
  `inspect`, and `evidence` reads, deterministic text and closed JSON schema 1,
  fixed aggregate exit precedence, bounded single-read repository inputs, and
  a hardened native Git adapter. Keep the command offline and free of mutation,
  setup, build, boot, test execution, arbitrary paths, MCP, A2A, and model SDKs.
  Resolve default and explicit lab IDs through the manifest catalog. Accept
  ASCII Semantic Versioning project identities independently of schema 1 so an
  unrelated project minor advance does not force a content-identical schema.
  Validate its schema independently only in an isolated Linux CPython 3.12 job
  using the six exact hash-verified wheels in the test-only dependency lock.
- Reason: One stable local contract serves maintainers, CI, dashboards, and
  future optional adapters without making a hosted provider or third-party
  package part of the lab runtime. Explicit `unavailable`, `fail`, `warning`,
  and `pass` states prevent missing inputs or historical evidence from being
  mislabeled as current readiness.
- Revisit when: the version-1 CLI has merged evidence and a separately approved
  use case justifies a replaceable read-only transport adapter. Such an adapter
  must consume the same command model and cannot broaden its authority.

## D-018: Derive image-composition evidence from locked SPDX 3 output

- Status: Accepted on 2026-08-19 for A008; publication, merge, tag, release,
  signing, and attestation are not authorized by this decision.
- Decision: Advance the development identity to `0.7.0-dev` and the lab
  manifest contract to schema 2. Generate SPDX 3.0.1 through the exact locked
  OpenEmbedded classes, validate the graph with the locked MIT-licensed
  `oe.spdx30` model, and retain only a closed project evidence document. Bind
  each lab to its direct installed project packages, exact declared licenses,
  cross-lab exclusions, and independently recomputed SHA-256 values for every
  SBOM root image artifact. Keep raw SBOMs and images as ignored build output.
- Reason: OpenEmbedded already constructs the authoritative rootfs package and
  image-artifact relationships. A bounded project projection makes those facts
  reviewable without introducing a parallel SBOM generator, vendored schema,
  hosted provider, or runtime dependency. Separating structural model
  validation from the project evidence contract preserves interoperability and
  makes unsupported claims explicit.
- Evidence boundary: this proves selected image composition and integrity at
  one clean revision. It is not complete SPDX specification conformance,
  vulnerability-freshness analysis, reproducible-build proof, an attestation,
  a signature, SLSA provenance, a release, or a physical-hardware result.
- Revisit when: a newer locked OE-Core changes its SPDX producer or model, the
  supported lab package sets change, or a protected release workflow has a
  separately approved signing and publication requirement. Any revision must
  preserve historical schema-1 evidence validation and requalify both labs.
