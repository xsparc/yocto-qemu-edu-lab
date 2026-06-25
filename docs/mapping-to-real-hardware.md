<!-- SPDX-License-Identifier: MIT -->

# Mapping this lab to a real custom SoC

| QEMU EDU lab | Real custom SoC |
|---|---|
| `-device edu` | RTL/peripheral physically present in the SoC |
| PCI enumeration | Device Tree or ACPI description |
| PCI vendor/device ID | Device Tree `compatible` string |
| BAR0 | `reg` entry containing the MMIO range |
| PCI interrupt routing | Device Tree `interrupts` entry |
| `struct pci_driver` | Usually `struct platform_driver` |
| `pcim_iomap_region()` | Usually `devm_platform_ioremap_resource()` |
| `pdev->irq` | Usually `platform_get_irq()` |
| Machine `.conf` | Your board/SoC machine `.conf` |
| QEMU firmware | Boot ROM, TF-A/OpenSBI, SPL, U-Boot on the board |

The concepts transfer directly.  The major pieces absent from this first lab are
DDR bring-up, clocks, resets, pin control, boot firmware, Device Tree, and real
signal/timing problems.

A useful second lab is an ARM64 QEMU `virt` machine with a custom QEMU SysBus
peripheral, a Device Tree node, and a platform driver.  That is closer to a
custom SoC, but it also requires maintaining a QEMU patch, so it is better after
this project is comfortable.
