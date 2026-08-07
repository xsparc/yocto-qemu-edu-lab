<!--
SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
SPDX-License-Identifier: MIT
-->

# Project vision

## North star

Yocto QEMU EDU Lab should become a progressive, evidence-driven path from a
first virtual PCI driver to maintainable embedded Linux board-support work.
Every stage should be small enough to understand end to end, realistic enough
to transfer to physical hardware, and reproducible enough for a learner,
teacher, maintainer, CI runner, or software agent to reach the same conclusion.

The project is successful when a learner can answer not only “did it work?” but
also “which layer made it work, what evidence proves it, what would change on
real hardware, and how can I safely extend it?”

## People and jobs

Primary users:

- embedded Linux learners who know C or Linux but not the complete BSP path;
- driver developers who want a disposable environment for PCI, MMIO, IRQ, and
  DMA experiments;
- educators who need repeatable exercises and observable failure modes;
- maintainers who need a compact reference layer for Yocto/QEMU automation.

Secondary users include CI systems and coding agents. They consume the same
versioned diagnostics and test evidence as humans; they are not a separate
source of truth.

## Product principles

1. **Teach one boundary at a time.** New labs add one concept and preserve a
   clear comparison with the previous stage.
2. **Evidence over assertion.** Compatibility and completion require build or
   runtime evidence. A skipped check is visible.
3. **Deterministic core, optional intelligence.** Local commands, schemas, and
   logs remain useful without an AI provider. AI can explain or orchestrate
   those contracts later.
4. **Portable concepts, explicit differences.** PCI, Device Tree, platform
   devices, FPGA, and real boards share patterns but are never presented as
   interchangeable.
5. **Safe by default.** No root-only networking, hosted service, secret, or
   destructive host operation is required for the default learning path.
6. **Open-source clarity.** Provenance, licensing, contribution expectations,
   and public change history are easy to inspect.
7. **Bounded growth.** A new architecture or tool earns its maintenance cost by
   teaching a distinct concept or improving reproducible evidence.

## Long-term experience

The intended progression is:

```text
reproducible setup
  -> x86-64 PCI discovery and MMIO
  -> automated interrupt and failure-path evidence
  -> MSI
  -> bounded DMA
  -> Device Tree and platform-driver lab
  -> optional FPGA/physical target bridge
  -> provider-neutral diagnostics and optional agent adapters
```

Each stage should expose:

- a human-readable explanation;
- the exact source and configuration boundary;
- a deterministic build and test entry point;
- structured evidence with a versioned schema;
- deliberate break/fix exercises;
- a mapping to real hardware and limits QEMU cannot prove.

## Success signals

- A clean supported Linux host can resolve pinned inputs and reproduce the
  declared lab configuration.
- Pull requests receive fast metadata, workflow, shell, and license checks;
  scheduled or release gates perform expensive image and runtime validation.
- Supported labs pass automated QEMU runtime tests, including negative paths.
- `yocto-check-layer` and declared `LAYERSERIES_COMPAT` evidence agree.
- A learner can add or complete a lab without reverse-engineering maintainer
  intent from commit history.
- Machine-readable output is stable enough for CI and optional agent tools
  without parsing prose or granting broad host access.

## Non-goals

- Replacing the Yocto Project manuals, Linux kernel documentation, or QEMU
  device specifications.
- Supporting every architecture, board, distribution, or Yocto release.
- Claiming QEMU proves electrical, timing, coherency, or silicon behavior.
- Becoming a production BSP, fleet-management platform, or autonomous release
  system.
- Requiring cloud services, an LLM, or a proprietary IDE.
- Hiding provenance, fabricating human participation, or accepting unclear
  redistribution rights to make the project appear more mature.
