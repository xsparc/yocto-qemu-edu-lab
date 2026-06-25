<!-- SPDX-License-Identifier: MIT -->

# Yocto + QEMU EDU driver lab

This is a PC-only example BSP project for learning how Yocto, QEMU, Linux
hardware discovery, a kernel driver, packages, and an image fit together.

The virtual target is an x86-64 machine with QEMU's **EDU educational PCI
peripheral**.  EDU was specifically designed for kernel-driver exercises.  It
has a 1 MiB MMIO BAR, identification and liveness registers, asynchronous
factorial hardware, legacy/MSI interrupts, and a small DMA engine.

This first lab implements:

- A derived Yocto machine: `qemu-edu-x86-64`
- QEMU hardware selection through `QB_OPT_APPEND`
- An out-of-tree PCI kernel module
- PCI ID matching and `probe()`
- BAR/MMIO mapping
- A shared legacy interrupt handler
- sysfs controls
- Automatic module loading
- A user-space test package
- A custom minimal image

It does **not** emulate a new instruction set.  It uses a normal x86-64 CPU and
adds a custom-like peripheral.  That is the fastest way to learn the BSP and
driver workflow without first writing a CPU model or a QEMU board model.

## 1. Host requirements

Use a native Linux host, a Linux VM, or WSL2.  Ubuntu 24.04 LTS is a convenient
choice.  For Ubuntu or Debian:

```bash
sudo apt-get update
sudo apt-get install build-essential chrpath cpio debianutils diffstat file \
    gawk gcc git iputils-ping libacl1 libcrypt-dev locales python3 \
    python3-git python3-jinja2 python3-pexpect python3-pip python3-subunit \
    socat texinfo unzip wget xz-utils zstd
```

Ensure `en_US.UTF-8` is available:

```bash
locale --all-locales | grep -i en_US.utf8
```

Yocto 6.0's official baseline is 140 GB free disk and 32 GB RAM.  This minimal
lab is smaller than a graphical reference image, but a roomy SSD still matters.

## 2. Set up the build

```bash
cd yocto-qemu-edu-lab
./setup.sh
```

The script clones Poky on the `wrynose` branch, creates `build/`, adds
`meta-qemu-edu`, selects the custom machine, and enables development login
settings.

Inspect the metadata before compiling:

```bash
./inspect.sh
```

Look especially for:

```text
MACHINE="qemu-edu-x86-64"
QB_OPT_APPEND="... -device edu"
```

## 3. Build

```bash
./build.sh
```

The first build downloads and compiles the toolchain, QEMU, Linux, BusyBox, the
module, and the root filesystem.  Subsequent builds reuse downloaded and
shared-state artifacts.

The important output directory is:

```text
build/tmp/deploy/images/qemu-edu-x86-64/
```

## 4. Boot in QEMU

```bash
./run.sh
```

The script uses unprivileged SLIRP networking, a serial console, and snapshot
mode.  Log in as `root`; the development image has no password.

Inside the guest, run:

```bash
qemu-edu-test
```

Expected highlights resemble:

```text
1234:11e8
input=0x12345678 result=0xedcba987 expected=0xedcba987
5! = 120
All EDU driver checks completed.
```

Also inspect the system manually:

```bash
lspci -nn -d 1234:11e8
lsmod | grep qemu_edu
dmesg | grep qemu_edu
ls -l /sys/bus/pci/drivers/qemu_edu/
cat /proc/interrupts | grep qemu_edu
```

If the module did not autoload:

```bash
modprobe qemu_edu
```

## 5. Follow one operation end to end

For factorial `5`:

```text
qemu-edu-test
  -> writes "5" to the driver's factorial sysfs attribute
  -> factorial_store() enables factorial IRQ generation
  -> driver writes 5 to MMIO offset 0x08
  -> QEMU's virtual hardware computes asynchronously
  -> QEMU raises the virtual PCI interrupt
  -> qemu_edu_irq() reads and acknowledges IRQ status
  -> completion wakes factorial_store()
  -> driver reads 120 from MMIO offset 0x08
  -> user space reads "5! = 120"
```

That is the same basic path used with physical hardware; only the device model
is software rather than RTL/silicon.

## 6. Where to read the project

Read files in this order:

1. `meta-qemu-edu/conf/machine/qemu-edu-x86-64.conf`
2. `meta-qemu-edu/recipes-kernel/qemu-edu-driver/qemu-edu-driver_1.0.bb`
3. `meta-qemu-edu/recipes-kernel/qemu-edu-driver/files/qemu_edu.c`
4. `meta-qemu-edu/recipes-support/qemu-edu-tools/qemu-edu-tools_1.0.bb`
5. `meta-qemu-edu/recipes-core/images/qemu-edu-image.bb`
6. `docs/architecture.md`
7. `docs/mapping-to-real-hardware.md`

## 7. Edit/rebuild loop

Change `qemu_edu.c`, then run:

```bash
make rebuild-driver
./run.sh
```

For normal source changes, BitBake notices changed `file://` inputs.  Do not
habitually delete the whole build directory.

Useful commands after sourcing the environment:

```bash
source poky/oe-init-build-env build
bitbake -e qemu-edu-driver | less
bitbake qemu-edu-driver -c devshell
bitbake qemu-edu-driver -c compile -f
bitbake qemu-edu-image
```

## 8. Exercises

### Exercise A: Break hardware discovery

Remove `-device edu` from the machine file and rebuild the image metadata.  QEMU
will no longer expose `1234:11e8`, so the module loads but `probe()` never runs.
This separates **driver registration** from **device discovery**.

### Exercise B: Break driver matching

Change `QEMU_EDU_DEVICE_ID` in the driver.  The device remains visible in
`lspci`, but Linux cannot match it to the driver.

### Exercise C: Observe MMIO

Add `dev_info()` calls around the liveness register access, rebuild, and compare
`dmesg` with the sysfs result.

### Exercise D: Convert INTx to MSI

Replace the direct use of `pdev->irq` with `pci_alloc_irq_vectors()`,
`pci_irq_vector()`, and `pci_free_irq_vectors()`.  QEMU EDU supports MSI, but
its interrupt acknowledge register must still be written.

### Exercise E: Add DMA

Implement the EDU DMA registers at offsets `0x80` through `0x98`.  Allocate
coherent memory, honour the device's 28-bit DMA mask, copy data to the EDU's
4 KiB internal buffer at offset `0x40000`, and verify the round trip.

### Exercise F: Move the driver in-tree

Put the source under the appropriate Linux source directory, add Kconfig and
Makefile entries, enable it with a kernel configuration fragment, and carry the
change through a `linux-yocto_%.bbappend`.  This is closer to long-term product
maintenance.

## 9. What QEMU cannot prove

QEMU is the right first step, but it cannot validate DDR initialization,
electrical behavior, clock/reset sequencing, pin multiplexing, analogue
interfaces, real DMA coherency bugs, interrupt wiring mistakes, or silicon
errata.  Use it to learn and automate the software architecture; use FPGA or
real hardware later for physical bring-up.

## 10. Licensing

This repository is mixed-license:

- Project scaffolding, documentation, Yocto layer metadata, helper scripts, and
  the user-space test utility are MIT-licensed. See `LICENSES/MIT.txt`.
- The example Linux kernel module source and its kernel-module build file are
  GPL-2.0-only. See `LICENSES/GPL-2.0-only.txt`.

Individual files may carry `SPDX-License-Identifier` comments that state the
applicable license for that file.
