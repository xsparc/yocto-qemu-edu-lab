# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MACHINE = ROOT / "meta-qemu-edu/conf/machine/qemu-edu-platform-arm64.conf"
DRIVER = (
    ROOT
    / "meta-qemu-edu/recipes-kernel/qemu-edu-platform-driver/files/qemu_edu_platform.c"
)
DRIVER_MAKEFILE = (
    ROOT / "meta-qemu-edu/recipes-kernel/qemu-edu-platform-driver/files/Makefile"
)
RECIPE = (
    ROOT
    / "meta-qemu-edu/recipes-kernel/qemu-edu-platform-driver/qemu-edu-platform-driver_1.0.bb"
)
BINDING = (
    ROOT
    / "meta-qemu-edu/recipes-kernel/qemu-edu-platform-driver/files/qemu,edu-platform.yaml"
)
TOOL = (
    ROOT
    / "meta-qemu-edu/recipes-support/qemu-edu-platform-tools/files/qemu-edu-platform-test"
)


class PlatformContractTests(unittest.TestCase):
    def test_machine_derives_exact_qemuarm64_path_and_instantiates_one_device(self) -> None:
        text = MACHINE.read_text(encoding="utf-8")
        self.assertIn("require conf/machine/qemuarm64.conf", text)
        self.assertIn('MACHINEOVERRIDES =. "qemuarm64:"', text)
        self.assertIn('KMACHINE = "qemuarm64"', text)
        self.assertEqual(text.count("-device qemu-edu-platform"), 1)
        self.assertIn('REQUIRED_VERSION_qemu-system-native = "10.2.0"', text)
        self.assertIn("qemu-edu-platform-driver", text)

    def test_driver_uses_managed_platform_resources_and_level_irq_ack(self) -> None:
        text = DRIVER.read_text(encoding="utf-8")
        for token in (
            "platform_get_resource",
            "devm_ioremap_resource",
            "platform_get_irq",
            "devm_request_irq",
            "device_add_group",
            "device_remove_group",
            "QEMU_EDU_PLATFORM_IRQ_STATUS_REG",
            "QEMU_EDU_PLATFORM_IRQ_ACK_REG",
            "synchronize_irq",
        ):
            self.assertIn(token, text)
        for unsafe in ("ioremap(", "free_irq(", "dma_"):
            self.assertNotIn(unsafe, text)
        self.assertNotRegex(text, r"(?<!devm_)request_irq\(")
        self.assertLess(text.index("device_remove_group"), text.index("synchronize_irq"))

    def test_guest_contract_is_small_bounded_and_exactly_named(self) -> None:
        text = DRIVER.read_text(encoding="utf-8")
        self.assertIn("0x0100a64e", text)
        attributes = set(re.findall(r"DEVICE_ATTR_(?:RO|RW|WO)\(([^)]+)\)", text))
        self.assertEqual(
            attributes,
            {
                "identification",
                "scratch",
                "interrupt_count",
                "last_irq_status",
                "raise_irq",
            },
        )
        self.assertIn("if (!value)", text)
        self.assertIn("return -EINVAL", text)

    def test_binding_declares_one_mmio_resource_one_irq_and_no_dma(self) -> None:
        text = BINDING.read_text(encoding="utf-8")
        self.assertIn("compatible:\n    const: qemu,edu-platform", text)
        self.assertRegex(text, r"reg:\n    maxItems: 1")
        self.assertRegex(text, r"interrupts:\n    maxItems: 1")
        self.assertIn("additionalProperties: false", text)
        self.assertIn("Louijie Compo <louijie.compo@gmail.com>", text)
        self.assertNotRegex(text.lower(), r"(?m)^  dmas?:")

    def test_recipe_license_checksum_matches_driver_spdx_line(self) -> None:
        recipe = RECIPE.read_text(encoding="utf-8")
        source_line = DRIVER.read_text(encoding="utf-8").splitlines(keepends=True)[0]
        checksum = hashlib.md5(source_line.encode("utf-8")).hexdigest()
        self.assertIn(f"md5={checksum}", recipe)
        self.assertIn('LICENSE = "GPL-2.0-only"', recipe)
        self.assertIn('COMPATIBLE_MACHINE = "^qemu-edu-platform-arm64$"', recipe)

    def test_driver_makefile_exposes_module_class_targets(self) -> None:
        text = DRIVER_MAKEFILE.read_text(encoding="utf-8")
        self.assertIn("obj-m += qemu_edu_platform.o", text)
        self.assertIn("all:\n\t$(MAKE) -C $(KERNEL_SRC) M=$(CURDIR) modules", text)
        self.assertIn(
            "modules_install:\n\t$(MAKE) -C $(KERNEL_SRC) M=$(CURDIR) modules_install",
            text,
        )
        self.assertIn("clean:\n\t$(MAKE) -C $(KERNEL_SRC) M=$(CURDIR) clean", text)

    def test_diagnostic_tool_is_sysfs_bounded_and_address_free(self) -> None:
        text = TOOL.read_text(encoding="utf-8")
        self.assertIn("/sys/bus/platform/devices", text)
        self.assertIn("identify|status|scratch VALUE|raise MASK", text)
        for unsafe in ("/dev/mem", "mmap", "debugfs", "resource0"):
            self.assertNotIn(unsafe, text)

    def test_image_keeps_architecture_specific_packages_and_suites_separate(self) -> None:
        image = (
            ROOT / "meta-qemu-edu/recipes-core/images/qemu-edu-image.bb"
        ).read_text(encoding="utf-8")
        self.assertIn("IMAGE_INSTALL:append:qemu-edu-x86-64", image)
        self.assertIn("IMAGE_INSTALL:append:qemu-edu-platform-arm64", image)
        self.assertIn('TEST_SUITES:qemu-edu-x86-64 = "ping ssh qemu_edu"', image)
        self.assertIn(
            'TEST_SUITES:qemu-edu-platform-arm64 = "ping ssh qemu_edu_platform"',
            image,
        )


if __name__ == "__main__":
    unittest.main()
