# SPDX-License-Identifier: MIT

SUMMARY = "Minimal userspace sample for direct eSDK and devtool iteration"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://qemu-edu-sdk-sample.c;beginline=1;endline=1;md5=234d7d4edd08962c0144e4604050e0b6"

SRC_URI = "file://qemu-edu-sdk-sample.c"
S = "${UNPACKDIR}"

do_compile() {
    ${CC} ${CFLAGS} ${CPPFLAGS} ${S}/qemu-edu-sdk-sample.c \
        -o qemu-edu-sdk-sample ${LDFLAGS}
}

do_install() {
    install -d ${D}${bindir}
    install -m 0755 qemu-edu-sdk-sample ${D}${bindir}/qemu-edu-sdk-sample
}

COMPATIBLE_MACHINE = "^(qemu-edu-x86-64|qemu-edu-platform-arm64)$"
