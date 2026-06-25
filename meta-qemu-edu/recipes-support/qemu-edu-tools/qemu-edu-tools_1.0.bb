SUMMARY = "User-space test utility for the QEMU EDU learning driver"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://qemu-edu-test;beginline=2;endline=2;md5=b2dccaa94b3629a08bfb4f983cad6f89"

SRC_URI = "file://qemu-edu-test"
S = "${UNPACKDIR}"

RDEPENDS:${PN} += "pciutils"

do_install() {
    install -d ${D}${bindir}
    install -m 0755 ${S}/qemu-edu-test ${D}${bindir}/qemu-edu-test
}
