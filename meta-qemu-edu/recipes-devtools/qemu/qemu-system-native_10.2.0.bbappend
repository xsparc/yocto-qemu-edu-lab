# SPDX-License-Identifier: MIT

QEMU_EDU_BACKPORT_FILESPATH := "${THISDIR}/files:"

python __anonymous() {
    supported_machines = {
        "qemu-edu-x86-64",
        "qemu-edu-platform-arm64",
    }
    if d.getVar("MACHINE") not in supported_machines:
        return
    d.prependVar("FILESEXTRAPATHS", d.getVar("QEMU_EDU_BACKPORT_FILESPATH"))
    d.appendVar(
        "SRC_URI",
        " file://0001-hw-misc-edu-restrict-dma-access-to-dma-buffer.patch"
        " file://0002-hw-misc-add-qemu-edu-platform-device.patch",
    )
}
