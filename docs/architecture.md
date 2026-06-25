<!-- SPDX-License-Identifier: MIT -->

# Architecture walk-through

```text
qemu-edu-x86-64.conf
    |
    |-- reuses qemux86-64 compiler/kernel settings
    |-- appends: -device edu
    |-- requires package: qemu-edu-driver
    v
runqemu -> qemu-system-x86_64 -> virtual PCI bus -> EDU device (1234:11e8)
                                                    |
                                                    | PCI enumeration
                                                    v
Linux PCI core -> qemu_edu.ko -> probe()
                                  |
                                  |-- maps BAR0 (MMIO)
                                  |-- requests shared INTx IRQ
                                  |-- creates sysfs attributes
                                  v
/sys/bus/pci/drivers/qemu_edu/<PCI-address>/
                                  |
                                  v
qemu-edu-test
```

## What each boundary teaches

1. **Machine configuration** describes the target and makes QEMU instantiate the
   virtual hardware.
2. **The recipe** cross-compiles and packages the external kernel module.
3. **PCI enumeration** discovers the device without a Device Tree node.
4. **The ID table** connects PCI ID `1234:11e8` to this driver.
5. **probe()** obtains resources and makes the device usable.
6. **MMIO** accesses the device's register file through BAR0.
7. **Interrupt handling** acknowledges the device and wakes a waiting operation.
8. **sysfs** provides a deliberately small user-space control surface.
9. **The image recipe** chooses diagnostic tools, independently of hardware support.
