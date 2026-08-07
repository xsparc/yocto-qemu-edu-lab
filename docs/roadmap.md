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

Candidate scope:

- choose a pinned source strategy after comparing a project lock file with kas;
- make setup idempotent and report resolved revisions;
- add shell, SPDX/REUSE, checksum, workflow, BitBake syntax/parse, and
  `yocto-check-layer` gates where practical;
- add CI with fast PR checks and an explicit scheduled/full-build lane;
- define project SemVer and Yocto-series compatibility policy.

Acceptance gate: a clean supported Linux environment resolves the same inputs,
fast checks are documented and green, and unavailable full-build evidence is
reported honestly.

Rollback: keep the current `setup.sh` path available for one milestone while the
new source declaration proves equivalence.

## M2 — Automated baseline runtime evidence

Outcome: the existing PCI/MMIO/INTx lab is verified without an interactive
guest login.

Candidate scope:

- document the current sysfs contract and failure semantics;
- integrate OEQA/testimage coverage for PCI discovery, identification,
  liveness, factorial, interrupt count, invalid range, timeout, and absent
  device behavior;
- emit a versioned result document for CI and local diagnosis.

Acceptance gate: `bitbake qemu-edu-image -c testimage` boots the image and
produces reproducible pass/fail evidence for positive and negative paths.

Rollback: retain `qemu-edu-test` as a manual teaching tool even after OEQA owns
the automated gate.

## M3 — MSI learning stage

Outcome: the lab teaches modern PCI vector allocation and compares it with INTx.

Acceptance gate: tests prove the selected mode, interrupt acknowledgement,
fallback or failure behavior, and cleanup; documentation explains both paths.

Rollback: make the interrupt mode a lab selection until MSI evidence is stable.

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
