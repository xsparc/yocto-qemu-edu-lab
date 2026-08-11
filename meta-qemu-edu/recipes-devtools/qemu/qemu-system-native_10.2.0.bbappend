# SPDX-License-Identifier: MIT

QEMU_EDU_BACKPORT_FILESPATH := "${THISDIR}/files:"

python __anonymous() {
    patches = {
        "qemu-edu-x86-64": "0001-hw-misc-edu-restrict-dma-access-to-dma-buffer.patch",
        "qemu-edu-platform-arm64": "0002-hw-misc-add-qemu-edu-platform-device.patch",
    }
    patch = patches.get(d.getVar("MACHINE"))
    if patch is None:
        return
    d.prependVar("FILESEXTRAPATHS", d.getVar("QEMU_EDU_BACKPORT_FILESPATH"))
    d.appendVar("SRC_URI", " file://" + patch)
}
