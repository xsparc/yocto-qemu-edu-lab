<!--
SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
SPDX-License-Identifier: MIT
-->

# Intake

## 2026-08-07 project direction request

Source: repository owner `/goal` request.

Requested outcomes:

- understand and document the long-term project vision;
- continue development autonomously through coherent milestones;
- maintain design, roadmap, implementation, and agent handoff material;
- keep the public repository professional and contributor-friendly;
- prevent licensing problems;
- use one properly scoped pull request per milestone;
- continuously research scalability, interoperability, longevity, and
  AI-oriented opportunities.

Constraints and interpretation:

- Do not fabricate human identity, reviews, testing, or authorship. Public work
  should read naturally and professionally, and attribution must remain true.
- Public changes, releases, destructive actions, credentials, and production
  systems remain approval-gated to the scope the user actually authorized.
- AI integration is optional and replaceable. Deterministic local commands and
  stable machine-readable contracts come first.
- The repository is mixed-license. MIT covers project infrastructure and
  learning material; the kernel module source and its module Makefile remain
  GPL-2.0-only.

Open questions retained for later milestones:

- Whether the first portability target after x86-64 should be ARM64 `virt`,
  RISC-V `virt`, or a real FPGA board.
- Whether reproducible source orchestration should adopt kas or remain a small
  project-owned lock manifest.
- Which CI budget can support full Yocto image builds versus scheduled builds
  and fast pull-request checks.
