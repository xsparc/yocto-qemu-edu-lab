SUMMARY = "Minimal console image for the QEMU EDU driver lab"
LICENSE = "MIT"

require recipes-core/images/core-image-minimal.bb

# qemu-edu-driver enters through MACHINE_ESSENTIAL_EXTRA_RDEPENDS.  The image
# chooses user-facing tools, which is a separate policy decision.
IMAGE_INSTALL:append = " qemu-edu-tools pciutils kmod"
