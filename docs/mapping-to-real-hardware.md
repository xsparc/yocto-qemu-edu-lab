<!-- SPDX-License-Identifier: MIT -->

# Mapping this lab to a real custom SoC

| QEMU lesson | Real custom SoC |
|---|---|
| `-device edu` | RTL/peripheral physically present in the SoC |
| PCI enumeration | Device Tree or ACPI description |
| PCI vendor/device ID | Device Tree `compatible` string |
| BAR0 | `reg` entry containing the MMIO range |
| PCI interrupt routing | Device Tree `interrupts` entry |
| `struct pci_driver` | Usually `struct platform_driver` |
| `pcim_iomap_region()` | Usually `devm_platform_ioremap_resource()` |
| `pci_irq_vector()` | Usually `platform_get_irq()` |
| `qemu-edu-platform` dynamic SysBus device | A peripheral integrated into the SoC address map |
| Generated `qemu,edu-platform` node | Board/SoC Device Tree maintained with the hardware description |
| `devm_platform_ioremap_resource()` | Managed mapping of the described peripheral resource |
| `platform_get_irq()` | Resolve an interrupt described by firmware |
| Machine `.conf` | Your board/SoC machine `.conf` |
| QEMU firmware | Boot ROM, TF-A/OpenSBI, SPL, U-Boot on the board |
| `dma_set_mask_and_coherent()` | Negotiate the address width implemented by the device and interconnect |
| `dmam_alloc_coherent()` | Allocate a device-visible control/data buffer with managed lifetime |
| EDU fixed 4 KiB buffer | A documented peripheral SRAM window, FIFO, or descriptor/data aperture |
| EDU DMA completion IRQ | A hardware completion/error status that software must acknowledge |

The software lifecycle concepts transfer, but QEMU does not prove real cache
coherency, IOMMU translation, interconnect ordering, DMA security domains, or
silicon error handling. The ARM64 platform lab now teaches generated Device
Tree discovery, managed MMIO resources, one level interrupt, and platform
driver lifecycle on QEMU `virt`. It deliberately omits DMA and does not prove a
physical interrupt controller, real firmware handoff, or board integration.

The major pieces still absent are DDR bring-up, clocks, resets, pin control,
secure and non-secure boot firmware, board-specific Device Tree ownership, and
real signal/timing problems. Treat the ARM64 lab as a clearer software mapping
exercise, not as hardware qualification.
