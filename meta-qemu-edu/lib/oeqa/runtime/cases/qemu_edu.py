# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT
"""Runtime contract tests for the QEMU EDU learning device."""

from __future__ import annotations

import re

from oeqa.core.decorator.depends import OETestDepends
from oeqa.runtime.case import OERuntimeTestCase


DRIVER_DIR = "/sys/bus/pci/drivers/qemu_edu"
BDF_PATTERN = re.compile(r"^[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]$")
DRIVER_ATTRIBUTES = frozenset(
    {
        "identification",
        "liveness",
        "factorial",
        "trigger_irq",
        "irq_count",
        "last_irq_status",
        "interrupt_mode",
        "dma_buffer_size",
        "dma_roundtrip",
    }
)


class QemuEduRuntimeTests(OERuntimeTestCase):
    """Exercise the documented PCI, MMIO, IRQ, and bounded DMA contract."""

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

    def pci_device_bdf(self) -> str:
        output = self.run_ok(
            "for path in /sys/bus/pci/devices/*; do "
            'vendor=$(cat "$path/vendor" 2>/dev/null) || continue; '
            'device=$(cat "$path/device" 2>/dev/null) || continue; '
            '[ "$vendor:$device" = "0x1234:0x11e8" ] && basename "$path"; '
            "done; true"
        )
        devices = [line.strip() for line in output.splitlines() if line.strip()]
        self.assertEqual(
            len(devices), 1, msg=f"exactly one EDU PCI function must exist: {devices}"
        )
        self.assertRegex(devices[0], BDF_PATTERN)
        return devices[0]

    def attribute(self, name: str) -> str:
        return f"{DRIVER_DIR}/{self.device_bdf()}/{name}"

    def regular_pci_files(self, bdf: str) -> set[str]:
        output = self.run_ok(
            f"for path in /sys/bus/pci/devices/{bdf}/*; do "
            '[ -f "$path" ] && basename "$path"; done; true'
        )
        return {line.strip() for line in output.splitlines() if line.strip()}

    def assert_interrupt_mode(self, expected: str) -> str:
        bdf = self.device_bdf()
        self.assertEqual(
            self.run_ok(f"cat {DRIVER_DIR}/{bdf}/interrupt_mode"), expected
        )
        irq = self.run_ok(f"cat /sys/bus/pci/devices/{bdf}/irq")
        self.assertRegex(irq, r"^[1-9][0-9]*$")
        self.run_ok(f"grep -E '^[[:space:]]*{irq}:' /proc/interrupts | grep -w qemu_edu")
        msi_dir = f"/sys/bus/pci/devices/{bdf}/msi_irqs"
        if expected == "msi":
            entries = self.run_ok(f"find {msi_dir} -mindepth 1 -maxdepth 1 -type f")
            self.assertEqual(entries, f"{msi_dir}/{irq}")
            self.assertEqual(self.run_ok(f"cat {msi_dir}/{irq}"), "msi")
        else:
            self.run_ok(f'test ! -d {msi_dir} || test -z "$(ls -A {msi_dir})"')
        return bdf

    def assert_interrupt_delivery(self, bdf: str) -> None:
        count_path = f"{DRIVER_DIR}/{bdf}/irq_count"
        status_path = f"{DRIVER_DIR}/{bdf}/last_irq_status"
        trigger_path = f"{DRIVER_DIR}/{bdf}/trigger_irq"
        for mask in (0x400, 0x800):
            before = int(self.run_ok(f"cat {count_path}"))
            self.run_ok(f"printf '0x{mask:x}\\n' > {trigger_path}")
            after = int(self.run_ok(f"cat {count_path}"))
            self.assertEqual(after, before + 1)
            self.assertEqual(self.run_ok(f"cat {status_path}"), f"0x{mask:08x}")

    def assert_default_msi(self) -> str:
        self.assertEqual(
            self.run_ok("cat /sys/module/qemu_edu/parameters/interrupt_mode"),
            "auto",
        )
        return self.assert_interrupt_mode("msi")

    def assert_dma_roundtrip(self, length: int) -> None:
        bdf = self.device_bdf()
        count_path = f"{DRIVER_DIR}/{bdf}/irq_count"
        status_path = f"{DRIVER_DIR}/{bdf}/last_irq_status"
        roundtrip_path = f"{DRIVER_DIR}/{bdf}/dma_roundtrip"
        before = int(self.run_ok(f"cat {count_path}"))
        self.run_ok(f"printf '{length}\\n' > {roundtrip_path}", timeout=10)
        self.assertEqual(
            self.run_ok(f"cat {roundtrip_path}"),
            f"length={length} result=passed",
        )
        self.assertEqual(int(self.run_ok(f"cat {count_path}")), before + 2)
        self.assertEqual(self.run_ok(f"cat {status_path}"), "0x00000100")

    def unload_module(self) -> None:
        self.run_ok("modprobe -r qemu_edu")

    def restore_default_module(self) -> None:
        remove_status, remove_output = self.target.run(
            "if test -d /sys/module/qemu_edu; then modprobe -r qemu_edu; fi",
            timeout=30,
        )
        reload_status, reload_output = self.target.run(
            "modprobe qemu_edu", timeout=30
        )
        self.assertEqual(
            remove_status,
            0,
            msg=f"could not unload selected interrupt mode: {remove_output}",
        )
        self.assertEqual(
            reload_status,
            0,
            msg=f"could not restore default module: {reload_output}",
        )
        self.assert_default_msi()

    def restore_msi_bus_and_default(self, bdf: str, previous: str) -> None:
        remove_status, remove_output = self.target.run(
            "if test -d /sys/module/qemu_edu; then modprobe -r qemu_edu; fi",
            timeout=30,
        )
        restore_status, restore_output = self.target.run(
            f"printf '{previous}\\n' > /sys/bus/pci/devices/{bdf}/msi_bus",
            timeout=30,
        )
        reload_status, reload_output = self.target.run(
            "modprobe qemu_edu", timeout=30
        )
        self.assertEqual(
            remove_status,
            0,
            msg=f"could not unload MSI policy test module: {remove_output}",
        )
        self.assertEqual(
            restore_status,
            0,
            msg=f"could not restore msi_bus={previous}: {restore_output}",
        )
        self.assertEqual(
            reload_status,
            0,
            msg=f"could not restore default module: {reload_output}",
        )
        self.assert_default_msi()

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
        self.assertEqual(
            self.run_ok(f"cat {self.attribute('dma_roundtrip')}"), "not-run"
        )
        self.assertEqual(self.run_ok(f"cat {self.attribute('irq_count')}"), "0")
        bdf = self.device_bdf()
        attributes = (
            "identification",
            "liveness",
            "factorial",
            "trigger_irq",
            "irq_count",
            "last_irq_status",
            "interrupt_mode",
            "dma_mask_bits",
            "dma_buffer_size",
            "dma_roundtrip",
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
                f"444 {DRIVER_DIR}/{bdf}/interrupt_mode",
                f"444 {DRIVER_DIR}/{bdf}/dma_mask_bits",
                f"444 {DRIVER_DIR}/{bdf}/dma_buffer_size",
                f"644 {DRIVER_DIR}/{bdf}/dma_roundtrip",
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

    def test_07_default_and_required_msi(self) -> None:
        bdf = self.assert_default_msi()
        self.assert_interrupt_delivery(bdf)
        try:
            self.unload_module()
            self.run_ok("modprobe qemu_edu interrupt_mode=msi")
            self.assertEqual(
                self.run_ok("cat /sys/module/qemu_edu/parameters/interrupt_mode"),
                "msi",
            )
            bdf = self.assert_interrupt_mode("msi")
            self.assert_interrupt_delivery(bdf)
        finally:
            self.restore_default_module()

    def test_08_explicit_intx_comparison(self) -> None:
        try:
            self.unload_module()
            self.run_ok("modprobe qemu_edu interrupt_mode=intx")
            bdf = self.assert_interrupt_mode("intx")
            self.assert_interrupt_delivery(bdf)
        finally:
            self.restore_default_module()

    def test_09_automatic_intx_fallback(self) -> None:
        bdf = self.pci_device_bdf()
        previous_msi_bus = self.run_ok(
            f"cat /sys/bus/pci/devices/{bdf}/msi_bus"
        )
        self.assertEqual(previous_msi_bus, "1")
        try:
            self.unload_module()
            self.run_ok(f"printf '0\\n' > /sys/bus/pci/devices/{bdf}/msi_bus")
            self.run_ok("modprobe qemu_edu interrupt_mode=auto")
            self.assert_interrupt_delivery(self.assert_interrupt_mode("intx"))
        finally:
            self.restore_msi_bus_and_default(bdf, previous_msi_bus)

    def test_10_required_msi_failure_and_cleanup(self) -> None:
        bdf = self.assert_default_msi()
        previous_msi_bus = self.run_ok(
            f"cat /sys/bus/pci/devices/{bdf}/msi_bus"
        )
        self.assertEqual(previous_msi_bus, "1")
        irq = self.run_ok(f"cat /sys/bus/pci/devices/{bdf}/irq")
        try:
            self.unload_module()
            self.run_ok(f"test ! -e /sys/bus/pci/devices/{bdf}/driver")
            self.run_ok(
                f'test ! -d /sys/bus/pci/devices/{bdf}/msi_irqs || '
                f'test -z "$(ls -A /sys/bus/pci/devices/{bdf}/msi_irqs)"'
            )
            self.run_ok(
                f"! grep -E '^[[:space:]]*{irq}:' /proc/interrupts | "
                "grep -w qemu_edu"
            )
            self.target.run("modprobe qemu_edu interrupt_mode=invalid", timeout=30)
            self.run_ok("test -d /sys/module/qemu_edu")
            self.run_ok(f"test ! -e /sys/bus/pci/devices/{bdf}/driver")
            self.unload_module()
            self.run_ok(f"printf '0\\n' > /sys/bus/pci/devices/{bdf}/msi_bus")
            self.target.run("modprobe qemu_edu interrupt_mode=msi", timeout=30)
            self.run_ok("test -d /sys/module/qemu_edu")
            self.run_ok(f"test ! -e /sys/bus/pci/devices/{bdf}/driver")
            self.run_ok(
                f'test ! -d /sys/bus/pci/devices/{bdf}/msi_irqs || '
                f'test -z "$(ls -A /sys/bus/pci/devices/{bdf}/msi_irqs)"'
            )
            self.run_ok("! grep -w qemu_edu /proc/interrupts")
        finally:
            self.restore_msi_bus_and_default(bdf, previous_msi_bus)
        self.assert_interrupt_delivery(self.device_bdf())

    def test_11_zero_interrupt_rejected(self) -> None:
        bdf = self.device_bdf()
        count_path = f"{DRIVER_DIR}/{bdf}/irq_count"
        before = self.run_ok(f"cat {count_path}")
        status, output = self.target.run(
            f"qemu-edu-write {DRIVER_DIR}/{bdf}/trigger_irq 0", timeout=10
        )
        self.assertNotEqual(status, 0, msg="zero interrupt request was accepted")
        self.assertIn("errno=22", output)
        self.assertEqual(self.run_ok(f"cat {count_path}"), before)

    def test_12_factorial_timeout(self) -> None:
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
        self.assert_default_msi()
        path = self.attribute("factorial")
        self.run_ok(f"printf '5\\n' > {path}", timeout=10)
        self.assertEqual(self.run_ok(f"cat {path}"), "5! = 120")

    def test_13_removed_device_diagnostic(self) -> None:
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
        self.assertEqual(self.assert_default_msi(), bdf)

    def test_14_dma_contract(self) -> None:
        self.assertEqual(self.run_ok(f"cat {self.attribute('dma_mask_bits')}"), "28")
        self.assertEqual(
            self.run_ok(f"cat {self.attribute('dma_buffer_size')}"), "4096"
        )
        parameter = self.run_ok(
            "cat /sys/module/qemu_edu/parameters/force_dma_timeout"
        )
        self.assertIn(parameter, ("N", "0"))
        self.assertEqual(
            self.run_ok(f"cat {self.attribute('dma_roundtrip')}"), "not-run"
        )
        bdf = self.device_bdf()
        bound_files = self.regular_pci_files(bdf)
        try:
            self.unload_module()
            self.run_ok(f"test ! -e /sys/bus/pci/devices/{bdf}/driver")
            unbound_files = self.regular_pci_files(bdf)
            self.assertEqual(bound_files - unbound_files, DRIVER_ATTRIBUTES)
        finally:
            self.restore_default_module()

    def test_15_dma_roundtrip_boundaries(self) -> None:
        for length in (1, 3, 4096):
            self.assert_dma_roundtrip(length)

    def test_16_invalid_dma_inputs(self) -> None:
        path = self.attribute("dma_roundtrip")
        self.assert_dma_roundtrip(17)
        expected_state = "length=17 result=passed"
        for value, expected_errno in (
            ("0", 34),
            ("4097", 34),
            ("-1", 22),
            ("invalid", 22),
        ):
            status, output = self.target.run(
                f"qemu-edu-write {path} '{value}'", timeout=10
            )
            self.assertNotEqual(status, 0, msg=f"{value!r} was unexpectedly accepted")
            self.assertIn(f"errno={expected_errno}", output)
            self.assertEqual(self.run_ok(f"cat {path}"), expected_state)

    def test_17_dma_timeout_and_recovery(self) -> None:
        try:
            self.unload_module()
            self.run_ok("modprobe qemu_edu force_dma_timeout=1")
            bdf = self.device_bdf()
            path = f"{DRIVER_DIR}/{bdf}/dma_roundtrip"
            count_path = f"{DRIVER_DIR}/{bdf}/irq_count"
            before = self.run_ok(f"cat {count_path}")
            status, output = self.target.run(
                f"qemu-edu-write {path} 64", timeout=10
            )
            self.assertNotEqual(status, 0, msg="missing DMA completion did not time out")
            self.assertIn("errno=110", output)
            self.assertEqual(
                self.run_ok(f"cat {path}"), "length=64 result=timeout"
            )
            self.assertEqual(self.run_ok(f"cat {count_path}"), before)
        finally:
            self.restore_default_module()
        parameter = self.run_ok(
            "cat /sys/module/qemu_edu/parameters/force_dma_timeout"
        )
        self.assertIn(parameter, ("N", "0"))
        self.assert_dma_roundtrip(64)

    def test_18_dma_teardown_and_rebind(self) -> None:
        bdf = self.assert_default_msi()
        irq = self.run_ok(f"cat /sys/bus/pci/devices/{bdf}/irq")
        self.assert_dma_roundtrip(32)
        try:
            self.unload_module()
            self.run_ok(f"test ! -e /sys/bus/pci/devices/{bdf}/driver")
            self.run_ok(f"test ! -e {DRIVER_DIR}/{bdf}/dma_roundtrip")
            self.run_ok(
                f'test ! -d /sys/bus/pci/devices/{bdf}/msi_irqs || '
                f'test -z "$(ls -A /sys/bus/pci/devices/{bdf}/msi_irqs)"'
            )
            self.run_ok(
                f"! grep -E '^[[:space:]]*{irq}:' /proc/interrupts | "
                "grep -w qemu_edu"
            )
        finally:
            self.restore_default_module()
        self.assert_dma_roundtrip(32)
