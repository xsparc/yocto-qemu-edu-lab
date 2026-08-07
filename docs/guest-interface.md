<!--
SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
SPDX-License-Identifier: MIT
-->

# QEMU EDU guest interface contract

This document defines version 2 of the pre-1.0 guest-visible contract for the
`qemu_edu` learning driver. It describes the current stage; it is not a
promise that a later pre-1.0 minor version will never change the interface.

The driver binds QEMU PCI device `1234:11e8`. A bound device is represented by
one symbolic link under:

```text
/sys/bus/pci/drivers/qemu_edu/<domain:bus:slot.function>/
```

The PCI address is discovered at runtime and must not be hard-coded. The M2
baseline expects exactly one device, but the path shape remains valid if a
future lab deliberately adds multi-device coverage.

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

Factorial and explicit-interrupt writes use a 2000 ms kernel wait budget; the
system call can return later because of scheduling and teardown overhead. If
the expected interrupt does not arrive, the write fails with `ETIMEDOUT`. An
interrupted wait returns the signal error. All operation paths disable
factorial interrupt requests before returning.

The module-load-only Boolean parameter `force_factorial_timeout` is a bounded
test seam. Its default is false and its sysfs permission is read-only. When the
module is loaded with `force_factorial_timeout=1`, the driver starts the real
factorial computation without requesting its completion interrupt, allowing
the automated suite to prove the existing timeout path. It is not an
application feature and must be restored to its default after the test.

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

## Interrupt lifecycle

Version 2 allocates exactly one PCI IRQ vector. The locked QEMU EDU device
supports one MSI vector, so the default `auto` policy resolves to MSI. Both MSI
and INTx report `qemu_edu` in `/proc/interrupts`, increment `irq_count`, and
acknowledge each device status in `last_irq_status`. A resolved MSI binding has
exactly one entry under the PCI function's `msi_irqs` directory; a resolved
INTx binding has none.

The driver uses the managed vector lifecycle installed by
`pcim_enable_device()` in the locked Linux 6.18 kernel. It requests the handler
after vector allocation, quiesces and acknowledges the device before request
and during removal, and does not manually free the managed vector.

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

## Compatibility and security

Only root can write the writable attributes in the development image. Sysfs input is
untrusted kernel input: range checks, serialized operations, bounded waits,
interrupt acknowledgement, and safe teardown remain required. QEMU evidence
does not imply electrical, timing, coherency, or physical-hardware behavior.
