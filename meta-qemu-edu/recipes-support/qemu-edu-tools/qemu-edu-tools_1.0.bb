# SPDX-License-Identifier: MIT

SUMMARY = "User-space test utility for the QEMU EDU learning driver"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://qemu-edu-test;beginline=2;endline=2;md5=b2dccaa94b3629a08bfb4f983cad6f89 \
                    file://qemu-edu-write.c;beginline=1;endline=1;md5=6ec41034e04432ee375d0e14fba596f4"

SRC_URI = "file://qemu-edu-test file://qemu-edu-write.c"
S = "${UNPACKDIR}"

RDEPENDS:${PN} += "pciutils"

do_compile() {
    ${CC} ${CFLAGS} ${CPPFLAGS} ${LDFLAGS} \
        ${S}/qemu-edu-write.c -o ${B}/qemu-edu-write
}

do_install() {
    install -d ${D}${bindir}
    install -m 0755 ${S}/qemu-edu-test ${D}${bindir}/qemu-edu-test
    install -m 0755 ${B}/qemu-edu-write ${D}${bindir}/qemu-edu-write
}
