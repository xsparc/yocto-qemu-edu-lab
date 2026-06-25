SUMMARY = "Learning driver for QEMU's EDU PCI device"
DESCRIPTION = "Out-of-tree PCI driver demonstrating discovery, BAR mapping, MMIO, legacy interrupts, sysfs, and Yocto module packaging."
LICENSE = "GPL-2.0-only"
LIC_FILES_CHKSUM = "file://qemu_edu.c;beginline=1;endline=1;md5=fcab174c20ea2e2bc0be64b493708266"

SRC_URI = " \
    file://Makefile \
    file://qemu_edu.c \
"

S = "${UNPACKDIR}"

inherit module

# Generate modules-load.d metadata in the split kernel-module package.
KERNEL_MODULE_AUTOLOAD += "qemu_edu"

COMPATIBLE_MACHINE = "^qemu-edu-x86-64$"
