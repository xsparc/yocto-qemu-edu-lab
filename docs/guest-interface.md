<!--
SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
SPDX-License-Identifier: MIT
-->

# QEMU EDU guest interface contracts

This document defines two independent pre-1.0 guest-visible contracts: PCI
contract version 3 for `qemu_edu`, and ARM64 platform contract version 1 for
`qemu_edu_platform`. They share teaching concepts, but neither contract is a
translation of the other. A later pre-1.0 minor version may deliberately
change either interface with corresponding version, migration, and rollback
documentation.

## PCI contract version 3

The driver binds QEMU PCI device `1234:11e8`. A bound device is represented by
one symbolic link under:

```text
/sys/bus/pci/drivers/qemu_edu/<domain:bus:slot.function>/
```

The PCI address is discovered at runtime and must not be hard-coded. The
current automated baseline expects exactly one device, but the path shape
remains valid if a future lab deliberately adds multi-device coverage.

## Attributes

All writes use Linux `kstrtou32()` base-0 parsing: decimal and `0x`-prefixed
hexadecimal values are accepted, while malformed or out-of-range unsigned
32-bit values fail with `EINVAL` or `ERANGE` as supplied by the kernel parser.

| Attribute | Access | Contract |
|---|---|---|
| `identification` | read | `0x010000ed` for the locked Yocto 6.0.2 QEMU; the QEMU format is `0xRRrr00ed`, where `RR` and `rr` are major and minor versions |
| `liveness` | read/write | Before a successful write: `not-run`. After writing `N`: `input=0xNNNNNNNN result=0xRRRRRRRR expected=0xRRRRRRRR`, where result and expected are the 32-bit inverse of `N` |
| `factorial` | read/write | Before a successful operation, or after timeout: `not-run`. Inputs `0..12` return `N! = R`; larger inputs fail with `ERANGE` because the device result register is 32-bit |
| `trigger_irq` | write | A nonzero bit mask raises and waits for one device interrupt; zero fails with `EINVAL` |
| `irq_count` | read | Decimal count of handled device interrupts since this binding began |
| `last_irq_status` | read | Last acknowledged EDU interrupt status as eight-digit hexadecimal |
| `interrupt_mode` | read | Resolved interrupt mode: `msi` or `intx`; this is never the requested policy value `auto` |
| `dma_mask_bits` | read | Decimal `28`, the negotiated EDU DMA-address width; this file is provided by the Linux DMA core rather than duplicated by the driver group |
| `dma_buffer_size` | read | Decimal `4096`, the size of both the managed coherent allocation and EDU's fixed internal DMA buffer |
| `dma_roundtrip` | read/write | Before a request: `not-run`. Writing a length from 1 through 4096 performs a verified RAM-to-EDU-to-RAM transfer. Readback is `length=N result=passed`, `timeout`, `verify-failed`, or `faulted` |

Factorial, explicit-interrupt, and each DMA completion use a 2000 ms kernel
wait budget; the system call can return later because of scheduling and
teardown overhead. If the expected interrupt does not arrive, the write fails
with `ETIMEDOUT`. Factorial and explicit-interrupt waits are interruptible and
return the signal error; the DMA wait is bounded but uninterruptible. All
factorial operation paths disable factorial interrupt requests before
returning.

`dma_roundtrip` accepts only a length. The guest never provides or reads a DMA
address or EDU buffer offset. The driver allocates one managed 4,096-byte
coherent buffer after negotiating the 28-bit mask, and always uses EDU's fixed
internal buffer at offset `0x40000`. A successful request fills a deterministic
pattern, transfers it RAM-to-EDU, overwrites the CPU buffer with a sentinel,
transfers EDU-to-RAM, and verifies every requested byte. Each successful round
trip handles exactly two DMA completion interrupts with EDU status
`0x00000100`. Zero and lengths above 4096 fail with `ERANGE`; negative,
malformed, and unsigned-overflow text fails through the unsigned parser. Input
validation happens before state changes, so rejected input preserves the last
successful result.

Linux publishes the negotiated mask through the PCI device's generic
`dma_mask_bits` attribute after `dma_set_mask_and_coherent()`. The driver uses
that existing file in the guest contract and does not create a colliding sysfs
attribute of its own.

The module-load-only Boolean parameter `force_factorial_timeout` is a bounded
test seam. Its default is false and its sysfs permission is read-only. When the
module is loaded with `force_factorial_timeout=1`, the driver starts the real
factorial computation without requesting its completion interrupt, allowing
the automated suite to prove the existing timeout path. It is not an
application feature and must be restored to its default after the test.

The read-only module-load Boolean `force_dma_timeout` is the corresponding DMA
test seam. When true, the driver starts the real first-direction transfer but
does not request its completion interrupt. The device normally finishes the
copy, while the bounded wait proves the missing-completion path and reports
`length=N result=timeout`. This does not claim stuck hardware. Tests unload the
fault-selected module and prove that the default false value, MSI binding, and
round trip recover. A missing or malformed completion clears bus mastering and
faults that binding's DMA path, so another DMA request is rejected until the
module is reloaded.

The module-load-only string parameter `interrupt_mode` selects the interrupt
policy. It is read-only after load and accepts only `auto`, `msi`, or `intx`:

- `auto` is the default and asks the PCI core for MSI with INTx fallback;
- `msi` requires MSI and leaves the device unbound if a vector cannot be
  allocated;
- `intx` deliberately selects shared legacy INTx for comparison and rollback.

The requested policy is visible at
`/sys/module/qemu_edu/parameters/interrupt_mode`; the resolved per-device mode
is the `interrupt_mode` attribute in the table above. An invalid policy fails
probe with `EINVAL` and does not bind the device.

## Interrupt and DMA lifecycle

The driver allocates exactly one PCI IRQ vector. The locked QEMU EDU device
supports one MSI vector, so the default `auto` policy resolves to MSI. Both MSI
and INTx report `qemu_edu` in `/proc/interrupts`, increment `irq_count`, and
acknowledge each device status in `last_irq_status`. A resolved MSI binding has
exactly one entry under the PCI function's `msi_irqs` directory; a resolved
INTx binding has none.

The driver uses the managed vector lifecycle installed by
`pcim_enable_device()` in the locked Linux 6.18 kernel. It requests the handler
after vector allocation, quiesces and acknowledges the device before request
and during removal, and does not manually free the managed vector.

The coherent buffer is device-managed, but hardware is quiesced explicitly:
removal first removes the sysfs entry, serializes with any operation, disables
factorial interrupt requests, acknowledges pending status, clears PCI bus
mastering, and waits a bounded interval for the DMA run bit to clear. A
persistent active engine is warned and remains fail-closed; the bound instance
does not resume DMA. Pending completion state is acknowledged and the IRQ is
synchronized before managed cleanup. The normal timeout seam completes the copy
before removal and does not exercise a permanently stuck device.

OEQA temporarily uses Linux's root-only, endpoint-scoped `msi_bus` testing ABI
while the driver is unbound to prove real PCI-core fallback and strict-MSI
failure. The test saves and restores the original value. `msi_bus` is neither a
driver attribute nor part of this guest contract, and disabling MSI this way is
not general application guidance.

## Diagnostic command

Running `qemu-edu-test` with one bound device exercises the readable learning
path. It exits nonzero with a diagnostic when the driver is not registered or
no EDU device is bound. Automated tests retain this command as the manual
teaching and rollback path; they do not replace it.

`qemu-edu-write SYSFS_PATH VALUE` is a small test-support command. It performs
one write and reports the numeric Linux `errno` on failure, allowing OEQA to
assert kernel behavior without depending on shell, locale, or libc prose. It is
not a privileged bypass: normal file permissions and kernel validation apply.

## ARM64 platform contract version 1

The independent `platform-arm64` lab creates one dynamic SysBus device under
QEMU's ARM `virt` platform bus. QEMU generates one Device Tree node with:

```text
compatible = "qemu,edu-platform"
reg size = 4096 bytes
interrupt = SPI 112, level-high
```

Linux discovers the generated node and binds the `qemu_edu_platform` driver.
The generated platform-device name contains its allocated address and must not
be hard-coded. Discover the one bound device through:

```text
/sys/bus/platform/drivers/qemu_edu_platform/<generated-device-name>/
```

The driver-owned attributes are published on the corresponding device under
`/sys/bus/platform/devices/<generated-device-name>/`:

| Attribute | Mode | Contract |
|---|---:|---|
| `identification` | `0444` | Exact model identifier `0x0100a64e` |
| `scratch` | `0644` | One unsigned 32-bit scratch register, rendered as eight-digit hexadecimal |
| `interrupt_count` | `0444` | Decimal count of handled device interrupts since this binding began |
| `last_irq_status` | `0444` | Last acknowledged interrupt mask as eight-digit hexadecimal |
| `raise_irq` | `0200` | A nonzero unsigned 32-bit mask raises the level interrupt; zero is rejected with `EINVAL` |

Writes use Linux `kstrtou32()` base-0 parsing. Decimal and `0x`-prefixed
hexadecimal values are accepted. Negative, malformed, and unsigned-overflow
text is rejected without changing the prior scratch value. The model contains
no DMA engine, guest-address input, shared-memory window, or arbitrary MMIO
access surface.

The interrupt handler reads the pending mask, returns `IRQ_NONE` for zero,
acknowledges the exact nonzero mask, records it, and increments the count once.
Removal acknowledges pending state and synchronizes the IRQ before managed
resources are released. The runtime contract proves two distinct masks,
unload cleanup, module rebind, and a known-good interrupt after recovery.

`qemu-edu-platform-test identify|status|scratch VALUE|raise MASK` is the bounded
manual interface. It discovers the single bound device and uses only these
sysfs files; it does not map `/dev/mem`, `resource0`, or another raw address.

## Compatibility and security

Only root can write the writable attributes in the development image. Sysfs
input is untrusted kernel input: range checks, serialized operations where
needed, bounded waits, interrupt acknowledgement, and safe teardown remain
required. QEMU evidence does not imply electrical, timing, cache-coherency,
IOMMU, interrupt-controller, firmware, or physical-hardware behavior. PCI
contract versions 1 and 2 remain historical evidence inputs; the PCI driver
and collector emit version 3. The ARM64 platform contract and evidence kind
begin independently at version 1.
