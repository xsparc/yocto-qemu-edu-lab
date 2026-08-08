# SPDX-License-Identifier: MIT

QEMU_EDU_BACKPORT_FILESPATH := "${THISDIR}/files:"

python __anonymous() {
    if d.getVar("MACHINE") != "qemu-edu-x86-64":
        return
    d.prependVar("FILESEXTRAPATHS", d.getVar("QEMU_EDU_BACKPORT_FILESPATH"))
    d.appendVar("SRC_URI", " file://0001-hw-misc-edu-restrict-dma-access-to-dma-buffer.patch")
}
