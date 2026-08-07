# SPDX-License-Identifier: MIT

SUMMARY = "Minimal console image for the QEMU EDU driver lab"
LICENSE = "MIT"

require recipes-core/images/core-image-minimal.bb

inherit testimage

# qemu-edu-driver enters through MACHINE_ESSENTIAL_EXTRA_RDEPENDS.  The image
# chooses user-facing tools, which is a separate policy decision.
IMAGE_INSTALL:append = " qemu-edu-tools pciutils kmod"

# Runtime tests use SSH over runqemu's unprivileged user networking. The empty
# development root password is configured by the project setup contract.
IMAGE_FEATURES += "ssh-server-dropbear"
TEST_SUITES = "ping ssh qemu_edu"
TEST_RUNQEMUPARAMS = "slirp"
QEMU_USE_KVM = ""
TEST_QEMUBOOT_TIMEOUT = "600"
TEST_OVERALL_TIMEOUT = "900"
