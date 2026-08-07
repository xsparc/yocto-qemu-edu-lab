<!--
SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
SPDX-License-Identifier: MIT
-->

# Durable memory

- Active task: A000.
- Current branch: `codex/m0-project-foundation`.
- Baseline: one x86-64 Yocto 6.0 (`wrynose`) learning machine using QEMU EDU PCI device `1234:11e8`.
- Existing runtime features: PCI discovery, BAR0 MMIO, legacy INTx, sysfs, factorial/liveness operations, and a guest smoke test.
- Current license boundary: infrastructure and learning material are MIT; kernel module source and its module Makefile are GPL-2.0-only.
- Full Yocto builds require Linux/WSL2 and substantial disk/time; the present Windows session can run only repository-local fast checks.
- OpenSteward has not audited this repository: no absolute private fixture sidecar config exists, and the plugin cannot perform live GitHub or repository inspection.
- M0 local validation and independent review are complete with no remaining findings; full Yocto/QEMU runtime evidence is unavailable on this Windows host.
- Pull request #1 is open from `codex/m0-project-foundation`; GitHub reports it ready, mergeable, and in a clean merge state, with no repository checks configured yet.
