# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT
"""Runtime contract tests for the QEMU EDU learning device."""

from __future__ import annotations

import re

from oeqa.core.decorator.depends import OETestDepends
from oeqa.runtime.case import OERuntimeTestCase


DRIVER_DIR = "/sys/bus/pci/drivers/qemu_edu"
BDF_PATTERN = re.compile(r"^[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]$")


class QemuEduRuntimeTests(OERuntimeTestCase):
    """Exercise the documented PCI, MMIO, INTx, and failure baseline."""

    def run_ok(self, command: str, timeout: int = 30) -> str:
        status, output = self.target.run(command, timeout=timeout)
        self.assertEqual(
            status,
            0,
            msg=f"command failed with status {status}: {command}\n{output}",
        )
        return output.strip()

    def device_bdf(self) -> str:
        output = self.run_ok(
            f"for path in {DRIVER_DIR}/*:*; do "
            '[ -L "$path" ] && basename "$path"; done'
        )
        devices = [line.strip() for line in output.splitlines() if line.strip()]
        self.assertEqual(
            len(devices), 1, msg=f"exactly one EDU device must be bound: {devices}"
        )
        self.assertRegex(devices[0], BDF_PATTERN)
        return devices[0]

    def attribute(self, name: str) -> str:
        return f"{DRIVER_DIR}/{self.device_bdf()}/{name}"

    @OETestDepends(["ssh.SSHTest.test_ssh"])
    def test_00_driver_registered(self) -> None:
        self.run_ok(f"test -d {DRIVER_DIR}")
        self.run_ok("grep -w qemu_edu /proc/modules")

    def test_01_pci_device_bound(self) -> None:
        bdf = self.device_bdf()
        output = self.run_ok(f"lspci -Dnns {bdf}")
        self.assertIn("1234:11e8", output.lower())
        driver = self.run_ok(f"basename $(readlink /sys/bus/pci/devices/{bdf}/driver)")
        self.assertEqual(driver, "qemu_edu")

    def test_02_identification_register(self) -> None:
        identification = self.run_ok(f"cat {self.attribute('identification')}")
        self.assertEqual(identification, "0x010000ed")

    def test_03_initial_operation_state(self) -> None:
        self.assertEqual(self.run_ok(f"cat {self.attribute('liveness')}"), "not-run")
        self.assertEqual(self.run_ok(f"cat {self.attribute('factorial')}"), "not-run")
        self.assertEqual(self.run_ok(f"cat {self.attribute('irq_count')}"), "0")
        bdf = self.device_bdf()
        attributes = (
            "identification",
            "liveness",
            "factorial",
            "trigger_irq",
            "irq_count",
            "last_irq_status",
        )
        attribute_paths = " ".join(
            f"{DRIVER_DIR}/{bdf}/{name}" for name in attributes
        )
        modes = self.run_ok(f"stat -c '%a %n' {attribute_paths}")
        self.assertEqual(
            modes.splitlines(),
            [
                f"444 {DRIVER_DIR}/{bdf}/identification",
                f"644 {DRIVER_DIR}/{bdf}/liveness",
                f"644 {DRIVER_DIR}/{bdf}/factorial",
                f"200 {DRIVER_DIR}/{bdf}/trigger_irq",
                f"444 {DRIVER_DIR}/{bdf}/irq_count",
                f"444 {DRIVER_DIR}/{bdf}/last_irq_status",
            ],
        )

    def test_04_liveness_inversion(self) -> None:
        path = self.attribute("liveness")
        self.run_ok(f"printf '0x12345678\\n' > {path}")
        self.assertEqual(
            self.run_ok(f"cat {path}"),
            "input=0x12345678 result=0xedcba987 expected=0xedcba987",
        )

    def test_05_factorial_boundaries(self) -> None:
        path = self.attribute("factorial")
        count_path = self.attribute("irq_count")
        for value, expected in ((0, 1), (5, 120), (12, 479001600)):
            before = int(self.run_ok(f"cat {count_path}"))
            self.run_ok(f"printf '{value}\\n' > {path}", timeout=10)
            self.assertEqual(self.run_ok(f"cat {path}"), f"{value}! = {expected}")
            after = int(self.run_ok(f"cat {count_path}"))
            self.assertEqual(after, before + 1)

    def test_06_invalid_factorial_inputs(self) -> None:
        path = self.attribute("factorial")
        self.run_ok(f"printf '5\\n' > {path}", timeout=10)
        for value, expected_errno in (
            ("13", 34),
            ("0x100000000", 34),
            ("invalid", 22),
        ):
            status, output = self.target.run(
                f"qemu-edu-write {path} '{value}'", timeout=10
            )
            self.assertNotEqual(status, 0, msg=f"{value!r} was unexpectedly accepted")
            self.assertIn(f"errno={expected_errno}", output)
            self.assertEqual(self.run_ok(f"cat {path}"), "5! = 120")

    def test_07_legacy_interrupt(self) -> None:
        bdf = self.device_bdf()
        msi_dir = f"/sys/bus/pci/devices/{bdf}/msi_irqs"
        self.run_ok(f'test ! -d {msi_dir} || test -z "$(ls -A {msi_dir})"')
        self.run_ok("grep -w qemu_edu /proc/interrupts")
        count_path = f"{DRIVER_DIR}/{bdf}/irq_count"
        before = int(self.run_ok(f"cat {count_path}"))
        self.run_ok(f"printf '0x400\\n' > {DRIVER_DIR}/{bdf}/trigger_irq")
        after = int(self.run_ok(f"cat {count_path}"))
        self.assertEqual(after, before + 1)
        self.assertEqual(
            self.run_ok(f"cat {DRIVER_DIR}/{bdf}/last_irq_status"),
            "0x00000400",
        )

    def test_08_zero_interrupt_rejected(self) -> None:
        bdf = self.device_bdf()
        count_path = f"{DRIVER_DIR}/{bdf}/irq_count"
        before = self.run_ok(f"cat {count_path}")
        status, output = self.target.run(
            f"qemu-edu-write {DRIVER_DIR}/{bdf}/trigger_irq 0", timeout=10
        )
        self.assertNotEqual(status, 0, msg="zero interrupt request was accepted")
        self.assertIn("errno=22", output)
        self.assertEqual(self.run_ok(f"cat {count_path}"), before)

    def test_09_factorial_timeout(self) -> None:
        self.run_ok("modprobe -r qemu_edu")
        fault_loaded = False
        try:
            self.run_ok("modprobe qemu_edu force_factorial_timeout=1")
            fault_loaded = True
            path = self.attribute("factorial")
            status, output = self.target.run(
                f"qemu-edu-write {path} 5", timeout=10
            )
            self.assertNotEqual(status, 0, msg="fault-injected operation did not time out")
            self.assertIn("errno=110", output)
            self.assertEqual(self.run_ok(f"cat {path}"), "not-run")
        finally:
            if fault_loaded:
                remove_status, remove_output = self.target.run(
                    "modprobe -r qemu_edu", timeout=30
                )
            else:
                remove_status, remove_output = 0, ""
            reload_status, reload_output = self.target.run(
                "modprobe qemu_edu", timeout=30
            )
            self.assertEqual(
                remove_status,
                0,
                msg=f"could not unload fault-injected module: {remove_output}",
            )
            self.assertEqual(
                reload_status,
                0,
                msg=f"could not restore default module: {reload_output}",
            )
        parameter = self.run_ok(
            "cat /sys/module/qemu_edu/parameters/force_factorial_timeout"
        )
        self.assertIn(parameter, ("N", "0"))
        path = self.attribute("factorial")
        self.run_ok(f"printf '5\\n' > {path}", timeout=10)
        self.assertEqual(self.run_ok(f"cat {path}"), "5! = 120")

    def test_10_removed_device_diagnostic(self) -> None:
        bdf = self.device_bdf()
        self.run_ok(f"printf '1\\n' > /sys/bus/pci/devices/{bdf}/remove")
        try:
            self.run_ok(f"test ! -e /sys/bus/pci/devices/{bdf}")
            status, output = self.target.run(
                "lspci -Dnn -d 1234:11e8", timeout=30
            )
            self.assertEqual(status, 0, msg=output)
            self.assertEqual(output.strip(), "")
            status, output = self.target.run("qemu-edu-test", timeout=30)
            self.assertEqual(status, 1, msg=f"unexpected diagnostic status: {output}")
            self.assertIn("no EDU PCI device is bound", output)
        finally:
            self.run_ok("printf '1\\n' > /sys/bus/pci/rescan")
        self.assertEqual(self.device_bdf(), bdf)
