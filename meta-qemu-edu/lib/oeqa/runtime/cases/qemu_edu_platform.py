# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT
"""Runtime contract tests for the QEMU EDU ARM64 platform device."""

from __future__ import annotations

from oeqa.core.decorator.depends import OETestDepends
from oeqa.runtime.case import OERuntimeTestCase


DRIVER_DIR = "/sys/bus/platform/drivers/qemu_edu_platform"
DEVICE_ROOT = "/sys/bus/platform/devices"
EXPECTED_ATTRIBUTES = frozenset(
    {
        "identification",
        "scratch",
        "interrupt_count",
        "last_irq_status",
        "raise_irq",
    }
)


class QemuEduPlatformRuntimeTests(OERuntimeTestCase):
    """Exercise FDT discovery, bounded MMIO, IRQ, and driver lifecycle."""

    def run_ok(self, command: str, timeout: int = 30) -> str:
        status, output = self.target.run(command, timeout=timeout)
        self.assertEqual(
            status,
            0,
            msg=f"command failed with status {status}: {command}\n{output}",
        )
        return output.strip()

    def device_name(self) -> str:
        output = self.run_ok(
            f"for path in {DRIVER_DIR}/*; do "
            '[ -L "$path" ] && [ "$(basename "$path")" != module ] && '
            'basename "$path"; done; true'
        )
        devices = [line.strip() for line in output.splitlines() if line.strip()]
        self.assertEqual(
            len(devices),
            1,
            msg=f"exactly one platform teaching device must be bound: {devices}",
        )
        return devices[0]

    def attribute(self, name: str) -> str:
        return f"{DEVICE_ROOT}/{self.device_name()}/{name}"

    def regular_device_files(self, device: str) -> set[str]:
        output = self.run_ok(
            f"for path in {DEVICE_ROOT}/{device}/*; do "
            '[ -f "$path" ] && basename "$path"; done; true'
        )
        return {line.strip() for line in output.splitlines() if line.strip()}

    def assert_interrupt(self, mask: int) -> None:
        count_path = self.attribute("interrupt_count")
        status_path = self.attribute("last_irq_status")
        before = int(self.run_ok(f"cat {count_path}"))
        self.run_ok(f"printf '0x{mask:x}\\n' > {self.attribute('raise_irq')}")
        self.run_ok(
            "attempt=0; "
            f"while [ \"$(cat {count_path})\" -le {before} ]; do "
            "attempt=$((attempt + 1)); [ $attempt -lt 50 ] || exit 1; "
            "sleep 0.1; done"
        )
        self.assertEqual(int(self.run_ok(f"cat {count_path}")), before + 1)
        self.assertEqual(self.run_ok(f"cat {status_path}"), f"0x{mask:08x}")

    def restore_module(self) -> None:
        remove_status, remove_output = self.target.run(
            "if test -d /sys/module/qemu_edu_platform; then "
            "modprobe -r qemu_edu_platform; fi",
            timeout=30,
        )
        load_status, load_output = self.target.run(
            "modprobe qemu_edu_platform", timeout=30
        )
        self.assertEqual(
            remove_status,
            0,
            msg=f"could not quiesce platform module: {remove_output}",
        )
        self.assertEqual(
            load_status,
            0,
            msg=f"could not restore platform module: {load_output}",
        )
        self.assertEqual(
            self.run_ok(f"cat {self.attribute('identification')}"), "0x0100a64e"
        )

    @OETestDepends(["ssh.SSHTest.test_ssh"])
    def test_00_driver_registered(self) -> None:
        self.run_ok(f"test -d {DRIVER_DIR}")
        self.run_ok("grep -w qemu_edu_platform /proc/modules")

    def test_01_generated_device_tree_contract(self) -> None:
        device = self.device_name()
        node = self.run_ok(f"readlink -f {DEVICE_ROOT}/{device}/of_node")
        self.assertIn("/platform-bus@c000000/qemu-edu@0", node)
        self.assertEqual(
            self.run_ok(f"tr -d '\\000' < {node}/compatible"),
            "qemu,edu-platform",
        )
        self.assertEqual(
            self.run_ok(f"hexdump -v -e '1/1 \"%02x\"' {node}/reg"),
            "0000000000001000",
        )
        self.assertEqual(
            self.run_ok(f"hexdump -v -e '1/1 \"%02x\"' {node}/interrupts"),
            "000000000000007000000004",
        )

    def test_02_platform_binding_and_resources(self) -> None:
        device = self.device_name()
        driver = self.run_ok(
            f"basename $(readlink -f {DEVICE_ROOT}/{device}/driver)"
        )
        self.assertEqual(driver, "qemu_edu_platform")
        self.run_ok(f"test -d {DEVICE_ROOT}/{device}/of_node")
        self.run_ok(f"grep -F '{device}' /proc/interrupts")
        self.assertEqual(
            self.regular_device_files(device) & EXPECTED_ATTRIBUTES,
            EXPECTED_ATTRIBUTES,
        )

    def test_03_identification_and_initial_state(self) -> None:
        self.assertEqual(
            self.run_ok(f"cat {self.attribute('identification')}"), "0x0100a64e"
        )
        self.assertEqual(self.run_ok(f"cat {self.attribute('scratch')}"), "0x00000000")
        self.assertEqual(self.run_ok(f"cat {self.attribute('interrupt_count')}"), "0")
        self.assertEqual(
            self.run_ok(f"cat {self.attribute('last_irq_status')}"), "0x00000000"
        )

    def test_04_bounded_scratch_roundtrip(self) -> None:
        path = self.attribute("scratch")
        for value in (0, 1, 0x12345678, 0xFFFFFFFF):
            self.run_ok(f"printf '0x{value:x}\\n' > {path}")
            self.assertEqual(self.run_ok(f"cat {path}"), f"0x{value:08x}")

    def test_05_invalid_scratch_preserves_value(self) -> None:
        path = self.attribute("scratch")
        self.run_ok(f"printf '0x13579bdf\\n' > {path}")
        for value in ("-1", "0x100000000", "malformed"):
            status, _ = self.target.run(f"printf '{value}\\n' > {path}")
            self.assertNotEqual(status, 0, msg=f"invalid scratch value accepted: {value}")
            self.assertEqual(self.run_ok(f"cat {path}"), "0x13579bdf")

    def test_06_distinct_interrupt_acknowledgement_cycles(self) -> None:
        self.assert_interrupt(0x400)
        self.assert_interrupt(0x800)

    def test_07_zero_interrupt_is_rejected(self) -> None:
        count_path = self.attribute("interrupt_count")
        status_path = self.attribute("last_irq_status")
        before_count = self.run_ok(f"cat {count_path}")
        before_status = self.run_ok(f"cat {status_path}")
        status, _ = self.target.run(f"printf '0\\n' > {self.attribute('raise_irq')}")
        self.assertNotEqual(status, 0)
        self.assertEqual(self.run_ok(f"cat {count_path}"), before_count)
        self.assertEqual(self.run_ok(f"cat {status_path}"), before_status)

    def test_08_unload_cleanup_and_rebind_recovery(self) -> None:
        device = self.device_name()
        bound_files = self.regular_device_files(device)
        try:
            self.run_ok("modprobe -r qemu_edu_platform")
            self.run_ok("test ! -d /sys/module/qemu_edu_platform")
            self.run_ok(f"test ! -L {DEVICE_ROOT}/{device}/driver")
            self.run_ok(f"! grep -F '{device}' /proc/interrupts")
            unbound_files = self.regular_device_files(device)
            self.assertEqual(
                bound_files - unbound_files,
                EXPECTED_ATTRIBUTES,
                msg=(
                    "driver-created regular sysfs files differ from the closed "
                    f"guest contract: bound={sorted(bound_files)}, "
                    f"unbound={sorted(unbound_files)}"
                ),
            )
        finally:
            self.restore_module()
        self.assert_interrupt(0x1000)
