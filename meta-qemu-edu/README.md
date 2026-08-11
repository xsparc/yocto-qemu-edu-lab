<!-- SPDX-License-Identifier: MIT -->

# meta-qemu-edu

This layer contains two independent learning machines and one shared image.
`qemu-edu-x86-64` teaches PCI discovery, MMIO, MSI/INTx, and a length-only
bounded coherent-DMA round trip. `qemu-edu-platform-arm64` derives from
`qemuarm64` and teaches generated Device Tree discovery, platform resources,
MMIO, one level interrupt, and managed driver lifecycle without DMA.

The exact native QEMU 10.2.0 append is machine scoped. The PCI machine selects
the attributed upstream EDU bounds backport; the ARM64 machine selects the
project-local `qemu-edu-platform` model/FDT patch. Each boot path verifies its
selected patch, post-patch source group, and architecture-specific executable
in `qemu-helper-native`'s consumer sysroot before `runqemu` can start.

See the repository-level `README.md` for the learning path and host setup,
`CONTRIBUTING.md` for maintainer and patch-submission guidance, `SECURITY.md`
for private vulnerability reporting, and `docs/licensing.md` for the
mixed-license file boundary.

The layer depends on the OpenEmbedded Core `core` collection. Its supported
Yocto series is declared in `conf/layer.conf`; compatibility is expanded only
after build evidence exists.
