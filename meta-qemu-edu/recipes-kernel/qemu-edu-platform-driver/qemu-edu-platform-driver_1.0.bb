# SPDX-License-Identifier: MIT
# The recipe metadata is MIT; LICENSE describes the packaged module source.

SUMMARY = "Learning driver for the QEMU EDU ARM64 platform device"
DESCRIPTION = "Out-of-tree platform driver demonstrating Device Tree discovery, resource mapping, MMIO, interrupts, sysfs, and managed lifecycle."
LICENSE = "GPL-2.0-only"
LIC_FILES_CHKSUM = "file://qemu_edu_platform.c;beginline=1;endline=1;md5=fcab174c20ea2e2bc0be64b493708266"

SRC_URI = " \
    file://Makefile \
    file://qemu_edu_platform.c \
    file://qemu,edu-platform.yaml \
"

S = "${UNPACKDIR}"

inherit module

KERNEL_MODULE_AUTOLOAD += "qemu_edu_platform"

COMPATIBLE_MACHINE = "^qemu-edu-platform-arm64$"
