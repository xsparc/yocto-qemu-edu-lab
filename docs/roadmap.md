<!--
SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
SPDX-License-Identifier: MIT
-->

# Development roadmap

The roadmap describes outcomes and gates. `docs/maintainers/tasks.toml` owns
executable task state. Every milestone uses one focused pull request; a
dependency is not approval to begin the next milestone.

## M0 — Project foundation and trustworthy execution

Outcome: maintainers and automation share one vision, architecture, license
boundary, task state, research trail, and public change process.

Acceptance gate:

- vision, architecture, milestones, contribution, security, and licensing
  policies agree with the repository;
- machine-readable tasks validate with at most one active slice;
- checksum and workflow checks pass;
- independent review findings are resolved or recorded;
- one M0 pull request is opened without merging or releasing automatically.

Rollback: revert the M0 PR; it does not change guest runtime behavior.

## M1 — Reproducible setup and fast validation

Outcome: a pull request can prove source identity and catch inexpensive failures
before a full Yocto build.

Delivered scope:

- lock the official split BitBake, OE-Core, and meta-yocto repositories after
  comparing a project format, kas, and upstream `bitbake-setup`;
- make setup idempotent, fail closed on local drift, and report resolved
  revisions in human and JSON forms;
- add shell, SPDX/REUSE, checksum, workflow, BitBake syntax/parse, and
  `yocto-check-layer` gates where practical;
- add immutable, secret-free fast PR checks and a distinct Linux metadata lane;
- document why a full build/runtime lane needs a larger protected runner;
- define project SemVer and Yocto-series compatibility policy.

Acceptance evidence: pull request #2 resolves the declared inputs on a clean
Linux runner, passes documented fast checks and native metadata/layer checks,
and reports unavailable full-build/runtime evidence honestly. Merge and release
remain separate maintainer decisions.

Rollback: revert M1 scripts and workflows without deleting `layers/`, `poky/`,
downloads, shared state, or build output. The former Poky combo path is not kept
as a Wrynose fallback because upstream no longer updates it for new series.

## M2 — Automated baseline runtime evidence

Outcome: the existing PCI/MMIO/INTx lab is verified without an interactive
guest login.

Delivered scope:

- document the current sysfs contract and failure semantics;
- integrate OEQA/testimage coverage for PCI discovery, identification,
  liveness, factorial, interrupt count, invalid range, timeout, and absent
  device behavior;
- emit a versioned result document for CI and local diagnosis.

Acceptance evidence: clean commit `6479681` passed locked build-composition
verification, the complete image build, software-QEMU boot, SSH, and all 11
project runtime cases. The closed version-1 result records exact revision,
dirty state, native input digest, task exit, and positive and negative outcomes.
It remains an unsigned local report, not hosted provenance or physical-hardware
evidence.

Rollback: retain `qemu-edu-test` as a manual teaching tool even after OEQA owns
the automated gate.

## M3 — MSI learning stage

Outcome: the lab teaches modern PCI vector allocation and compares it with INTx.

Delivered scope:

- select `auto`, required MSI, or explicit INTx at module load and report the
  resolved per-device mode;
- allocate one managed PCI vector without double-freeing the locked Linux 6.18
  managed lifecycle;
- prove default and strict MSI, explicit INTx, actual PCI-core fallback,
  strict-MSI failure, acknowledgement, cleanup, and default recovery;
- emit evidence schema 2 while preserving version-1 validation.

Acceptance evidence: clean commit `3ea0204` passed the exact locked image path,
software-QEMU boot, SSH, and all 14 project cases without skips or failures.
The closed version-2 evidence records the exact revision, clean tree, native
result digest, and conservative completion claims for every interrupt and
negative path. Independent review found no remaining P0-P2 issue. QEMU evidence
remains distinct from physical-hardware qualification.

Rollback: load `interrupt_mode=intx`, or revert the focused M3 change. Retain
the immutable version-1 schema and validator path for historical M2 evidence.

## M4 — Bounded DMA learning stage

Outcome: the driver safely demonstrates both EDU DMA directions, coherent
memory, the default 28-bit mask, transfer bounds, completion, and cleanup.

Acceptance gate: automated round-trip, bounds, timeout, and teardown tests pass;
the interface and real-hardware limitations are documented.

Rollback: keep DMA opt-in and preserve the M3 image as a known-good stage.

## M5 — Portable platform-driver lab

Outcome: one non-PCI lab teaches Device Tree discovery and a platform driver
without weakening the original PCI lesson.

Decision gate: compare ARM64 `virt`, RISC-V `virt`, and the cost of maintaining a
small QEMU device patch. Choose one based on learning value, upstream fit,
runtime cost, and maintenance burden.

Acceptance gate: both labs build and boot independently; the new lab proves
Device Tree, MMIO, interrupt, and teardown behavior; shared and different
concepts are explicit.

Rollback: the new lab is additive and can be removed without changing x86-64.

## M6 — Provider-neutral diagnostics and optional tool access

Outcome: `doctor`, `inspect`, and test evidence are safe and structured enough
for people, CI, and optional assistants.

Candidate scope:

- add a dependency-light local CLI with versioned JSON schemas;
- expose read-only project state and evidence through an adapter only after the
  CLI contract is stable;
- evaluate MCP against the current specification without coupling the lab to a
  particular SDK or model;
- threat-model paths, subprocess arguments, secrets, untrusted logs, and tool
  approval boundaries.

Acceptance gate: the complete lab remains usable without AI; schema and security
tests pass; state-changing tools are absent or separately approved.

Rollback: remove the adapter while preserving the CLI and evidence format.

## Horizon — Physical target bridge and course ecosystem

Potential work after evidence from M0–M6:

- FPGA or supported development-board mapping with explicit QEMU/physical
  evidence separation;
- instructor exercise packs with expected failure signatures;
- SDK/eSDK workflows for application and driver iteration;
- reproducible release images with Yocto SPDX SBOMs and verifiable provenance;
- community-contributed labs that pass the same compatibility and license gates.

These are horizons, not commitments or approved tasks.
