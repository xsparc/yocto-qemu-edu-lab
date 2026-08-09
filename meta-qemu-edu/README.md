<!-- SPDX-License-Identifier: MIT -->

# meta-qemu-edu

This layer contains the `qemu-edu-x86-64` learning machine, image, example
driver recipe, guest test utility, and the version-specific upstream bounds
backport for the native QEMU system emulator used by `runqemu`. The current
driver curriculum includes PCI discovery, MMIO, MSI/INTx, and a length-only
bounded coherent-DMA round trip; the guest never supplies a DMA address.

See the repository-level `README.md` for the learning path and host setup,
`CONTRIBUTING.md` for maintainer and patch-submission guidance, `SECURITY.md`
for private vulnerability reporting, and `docs/licensing.md` for the
mixed-license file boundary.

The layer depends on the OpenEmbedded Core `core` collection. Its supported
Yocto series is declared in `conf/layer.conf`; compatibility is expanded only
after build evidence exists.
