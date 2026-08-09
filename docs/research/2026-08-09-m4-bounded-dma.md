<!--
SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
SPDX-License-Identifier: MIT
-->

# M4 bounded DMA research — 2026-08-09

This note records the platform facts and safety boundary used to design A004.
It is a decision input, not build or runtime evidence.

## Device and kernel facts

QEMU EDU exposes DMA source, destination, count, and command registers at
offsets `0x80`, `0x88`, `0x90`, and `0x98`. Command bit 0 starts a transfer,
bit 1 selects EDU-to-RAM direction, and bit 2 requests a completion interrupt.
DMA completion reports interrupt status bit `0x100`. The device has a fixed
4,096-byte internal buffer beginning at offset `0x40000` and defaults to a
28-bit DMA mask.

The Linux DMA API requires the driver to establish an appropriate DMA mask
before allocation. A coherent allocation returns both a CPU pointer and a DMA
address; coherent memory still needs the documented ordering barriers around
device ownership and doorbells. Device-managed coherent memory simplifies
lifetime, but the driver remains responsible for stopping device access before
the managed allocation is released. Clearing PCI bus mastering is therefore a
teardown boundary, not a substitute for validating transfer bounds.

Primary sources:

- [QEMU EDU specification](https://www.qemu.org/docs/master/specs/edu.html)
- [Linux DMA API HOWTO](https://kernel.org/doc/html/next/core-api/dma-api-howto.html)
- [Linux device-resource management](https://cdn.kernel.org/doc/html/latest/driver-api/driver-model/devres.html)
- [Linux PCI driver API](https://www.kernel.org/doc/html/latest/driver-api/pci/pci.html)
- [Linux memory barriers](https://cdn.kernel.org/doc/html/latest/core-api/wrappers/memory-barriers.html)

The repository's exact host-emulator input remains QEMU 10.2.0 plus the A007
backport. The preflight verifies the attributed upstream patch, resulting
source, compiled native recipe, and runqemu consumer before a guest can boot.
No out-of-bounds transfer is executed as a test.

## Chosen boundary

The public interface accepts one unsigned length from 1 through 4096. The
driver owns one managed coherent allocation and its DMA address; neither the
address nor a device offset crosses sysfs. A request uses the fixed EDU buffer,
performs RAM-to-EDU then EDU-to-RAM under one mutex, overwrites the CPU buffer
with a sentinel between directions, and verifies a deterministic pattern after
the second completion. Each direction requests and acknowledges the exact DMA
completion interrupt.

The missing-completion test seam is read-only after module load. It suppresses
the completion-interrupt request while allowing the real bounded copy to run,
so its evidence is a missing-IRQ timeout rather than a stuck-engine claim.
Removal excludes new sysfs work, serializes with an active operation, clears
interrupt state and PCI bus mastering, and waits a bounded interval for the run
bit before managed cleanup.

Rejected alternatives include user-provided DMA addresses, mmap, arbitrary EDU
offsets, streaming mappings, scatter-gather, and a host-side out-of-bounds
probe. They widen the kernel or emulator attack surface without improving this
curriculum stage. A second allocation was also unnecessary: a sentinel between
directions proves the return transfer using one bounded buffer.

## Compatibility and evidence

A004 changes the guest interface and required runtime cases, so it advances the
development identity to `0.4.0-dev`, guest interface to 3, runtime suite to 3,
and evidence schema to 3. Schemas 1 and 2 and their exact test lists remain
immutable validator inputs. The new schema records only case-bound facts and
cannot claim a DMA path completed unless its dedicated case passed.

QEMU evidence cannot qualify physical cache coherency, IOMMU isolation,
interconnect ordering, electrical behavior, or silicon error recovery. Those
claims require a separately designed physical-hardware stage.
