# SPDX-License-Identifier: MIT

SUMMARY = "Minimal console image for the QEMU EDU driver lab"
LICENSE = "MIT"

require recipes-core/images/core-image-minimal.bb

inherit testimage

# qemu-edu-driver enters through MACHINE_ESSENTIAL_EXTRA_RDEPENDS.  The image
# chooses user-facing tools, which is a separate policy decision.
IMAGE_INSTALL:append:qemu-edu-x86-64 = " qemu-edu-tools pciutils kmod"
IMAGE_INSTALL:append:qemu-edu-platform-arm64 = " qemu-edu-platform-tools kmod"

# Runtime tests use SSH over runqemu's unprivileged user networking. The empty
# development root password is configured by the project setup contract.
IMAGE_FEATURES += "ssh-server-dropbear"
TEST_SUITES:qemu-edu-x86-64 = "ping ssh qemu_edu"
TEST_SUITES:qemu-edu-platform-arm64 = "ping ssh qemu_edu_platform"
TEST_RUNQEMUPARAMS = "slirp"
QEMU_USE_KVM = ""
TEST_QEMUBOOT_TIMEOUT = "600"
TEST_OVERALL_TIMEOUT = "900"

COMPATIBLE_MACHINE = "^(qemu-edu-x86-64|qemu-edu-platform-arm64)$"
