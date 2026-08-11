<!--
SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
SPDX-License-Identifier: MIT
-->

# M5 ARM64 platform-lab research — 2026-08-11

This note records the platform, configuration, provenance, and licensing facts
used to design A005. It is a decision input, not build or runtime evidence.

## Architecture choice

OE-Core treats `qemuarm64` and `qemuriscv64` as primary QEMU targets. The exact
Yocto 6.0.2 `qemuarm64` machine directly selects `qemu-system-aarch64` and
`-machine virt`. The RISC-V path additionally depends on OpenSBI, uses a jump
firmware image, and includes U-Boot in the image dependency chain. Those are
valuable subjects, but they obscure M5's intended comparison between PCI
discovery and Device Tree/platform discovery. ARM64 is therefore the bounded
second architecture; RISC-V is deferred.

Primary sources:

- [OE-Core QEMU target policy](https://github.com/openembedded/openembedded-core)
- [Exact Yocto 6.0.2 qemuarm64 machine](https://github.com/openembedded/openembedded-core/blob/5d1aa5c806c061a2994f4decb59016610f093213/meta/conf/machine/qemuarm64.conf)
- [Exact Yocto 6.0.2 qemuriscv include](https://github.com/openembedded/openembedded-core/blob/5d1aa5c806c061a2994f4decb59016610f093213/meta/conf/machine/include/riscv/qemuriscv.inc)

## QEMU and Device Tree boundary

QEMU 10.2.0 ARM `virt` reserves a dynamic platform-bus MMIO window and connects
that bus to a range of GIC interrupts. Its generated-FDT code accepts only an
explicit list of dynamic SysBus device types; an unknown device terminates
machine construction. The project must therefore add both a new independent
SysBus model and its FDT-node generator. A custom board fork or a handwritten
complete DTB would duplicate `virt` policy and make the lesson harder to
maintain.

The device contract is deliberately small: a read-only identification
register, a scratch register, an interrupt-raise register, interrupt status,
and write-one acknowledgement. All accesses are exactly 32-bit little-endian.
There is one level interrupt and no DMA, queue, shared-memory, or arbitrary
host-side access surface. Reset lowers the interrupt and restores register
defaults.

Primary sources:

- [QEMU 10.2.0 ARM virt machine](https://github.com/qemu/qemu/blob/v10.2.0/hw/arm/virt.c)
- [QEMU 10.2.0 dynamic platform bus](https://github.com/qemu/qemu/blob/v10.2.0/hw/core/platform-bus.c)
- [QEMU 10.2.0 dynamic SysBus FDT bindings](https://github.com/qemu/qemu/blob/v10.2.0/hw/core/sysbus-fdt.c)
- [Linux Device Tree usage model](https://docs.kernel.org/6.1/devicetree/usage-model.html)
- [Linux Device Tree binding schema guidance](https://docs.kernel.org/6.15/devicetree/bindings/writing-schema.html)

## Composition and compatibility

A versioned lab index binds each closed manifest by SHA-256. The manifest owns
the build directory, machine, driver, image, ordered layers, emulator preflight,
runtime suite, and evidence profile. Source repository identity remains a
separate lock. Runtime evidence records both digests so a source lock cannot be
mistaken for build-composition evidence.

`pci-x86-64` remains the default and retains `build/`. Existing no-argument
commands and PCI evidence schemas 1 through 3 remain compatible. The ARM64 lab
uses an independent build directory, guest contract version 1, runtime suite,
and closed evidence schema version 1. Unknown lab, manifest, profile, or schema
values fail closed.

Yocto 6.0.3 is planned for the week commencing 2026-08-24. It is monitored as a
separate point-update candidate and is not mixed into M5.

- [Yocto release calendar](https://wiki.yoctoproject.org/wiki/Release_calendar)

## Licensing and upstream boundary

QEMU contains code under several compatible licenses. The project-local patch
touches GPL-compatible integration files and adds a model intentionally
licensed GPL-2.0-only; the patch is therefore mapped as GPL-2.0-only. The
external Linux module is also GPL-2.0-only. The Device Tree schema uses the
kernel-preferred `(GPL-2.0-only OR BSD-2-Clause)` expression, and project
metadata remains MIT. REUSE must cover every new file and include the
additional license text before the slice can close.

The QEMU patch is an educational, project-local input and will not be submitted
upstream. This avoids making unsupported provenance, DCO, review, or long-term
maintainership claims; upstream contribution would require a separate process
that satisfies QEMU's current code-provenance policy.

- [QEMU licensing](https://www.qemu.org/docs/master/about/license.html)
- [QEMU code-provenance policy](https://www.qemu.org/docs/master/devel/code-provenance.html)
- [Linux Device Tree binding submission and licensing](https://docs.kernel.org/devicetree/bindings/submitting-patches.html)

## Required evidence

M5 remains unqualified until a clean adequate Linux host proves both build and
runtime paths. ARM evidence must include exact patch and post-patch source
digests, recipe selection, compiled and consumed native emulator, generated DTB
validation, platform binding, MMIO, two interrupt acknowledgement cycles,
unload cleanup, and rebind recovery. The existing 19-case PCI suite must pass
unchanged on the same source revision. Public CI can provide fast and metadata
evidence but must not be described as a full build or runtime gate.
