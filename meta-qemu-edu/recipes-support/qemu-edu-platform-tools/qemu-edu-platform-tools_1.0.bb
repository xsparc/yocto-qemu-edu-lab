# SPDX-License-Identifier: MIT

SUMMARY = "Bounded diagnostic tool for the QEMU EDU platform driver"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://qemu-edu-platform-test;beginline=2;endline=2;md5=b2dccaa94b3629a08bfb4f983cad6f89"

SRC_URI = "file://qemu-edu-platform-test"
S = "${UNPACKDIR}"

do_install() {
    install -d ${D}${bindir}
    install -m 0755 ${S}/qemu-edu-platform-test ${D}${bindir}/qemu-edu-platform-test
}

COMPATIBLE_MACHINE = "^qemu-edu-platform-arm64$"
