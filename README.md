<!-- SPDX-License-Identifier: MIT -->

# Yocto + QEMU EDU driver lab

This is a multi-architecture example BSP project for learning how Yocto, QEMU,
Linux hardware discovery, kernel drivers, packages, and an image fit together.

The long-term direction is a progressive, evidence-driven curriculum from this
first virtual PCI driver through automated runtime testing, MSI, DMA, a
Device-Tree/platform-driver lab, and optional provider-neutral diagnostics. The
core build and learning path will remain usable without an AI service. See
[`docs/vision.md`](docs/vision.md) and [`docs/roadmap.md`](docs/roadmap.md).

The current development identity is `0.5.0-dev`; no release is implied. Yocto
metadata inputs are locked to the 6.0.2 Wrynose point release.

Two closed lab manifests share the same locked sources and image target while
keeping their hardware contracts independent:

| Lab | Machine | Learning boundary | Build directory |
|---|---|---|---|
| `pci-x86-64` (default) | `qemu-edu-x86-64` | PCI discovery, BAR MMIO, MSI/INTx, bounded DMA | `build/` |
| `platform-arm64` | `qemu-edu-platform-arm64` | generated Device Tree, platform discovery, MMIO, one level IRQ | `build-platform-arm64/` |

The default remains QEMU's EDU educational PCI peripheral. The ARM64 lab uses
an independent project-local SysBus model on QEMU `virt`; it does not expose
DMA or reinterpret the PCI EDU ABI as a portable hardware contract.

This first lab implements:

- A derived Yocto machine: `qemu-edu-x86-64`
- QEMU hardware selection through `QB_OPT_APPEND`
- An exact upstream EDU DMA bounds backport for the native system emulator,
  scoped to the `qemu-edu-x86-64` machine
- An out-of-tree PCI kernel module
- PCI ID matching and `probe()`
- BAR/MMIO mapping
- One managed PCI interrupt vector with MSI-preferred, strict-MSI, and explicit
  INTx learning policies
- One managed 4 KiB coherent buffer and a length-only, two-direction bounded
  DMA round trip under the EDU 28-bit mask
- sysfs controls
- Automatic module loading
- A user-space test package
- A custom minimal image

The additive ARM64 lab implements:

- A machine derived from OE-Core `qemuarm64`
- A machine-scoped QEMU 10.2.0 patch for `qemu-edu-platform`
- One generated `qemu,edu-platform` FDT node with a 4 KiB resource and one
  level-high interrupt
- A managed out-of-tree platform driver with bounded scratch and IRQ controls
- A separate diagnostic command, OEQA suite, and closed evidence schema v1

Neither lab implements a CPU or board model. The PCI lab uses QEMU's existing
x86-64 PC machine, and the platform lab uses its existing ARM64 `virt` machine;
each adds only the teaching peripheral selected by its manifest. This keeps the
lesson on BSP composition and driver bring-up rather than instruction-set
emulation.

## 1. Host requirements

Use a native Linux host, a Linux VM, or WSL2.  Ubuntu 24.04 LTS is a convenient
choice.  For Ubuntu or Debian:

```bash
sudo apt-get update
sudo apt-get install build-essential chrpath cpio debianutils diffstat file \
    gawk gcc git iproute2 iputils-ping libacl1 libcrypt-dev locales openssh-client python3 \
    python3-git python3-jinja2 python3-pexpect python3-pip python3-subunit \
    socat sysstat texinfo unzip wget xz-utils zstd
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
# Or select the independent ARM64 path:
./setup.sh --lab platform-arm64
```

The script resolves the exact BitBake, OpenEmbedded Core, and meta-yocto commits
declared in `config/sources.lock.json`, validates the digest-bound manifest in
`config/labs/`, creates that lab's build directory, adds the ordered layers,
selects the declared machine, and enables development login settings. It
refuses dirty, wrong-origin, unexpected source checkouts and unknown or altered
lab manifests.

Verify existing checkouts without fetching, or configure from already-cached
Git objects:

```bash
./setup.sh --check
./setup.sh --offline
python3 scripts/source_lock.py --format json status
python3 scripts/lab_config.py validate
python3 scripts/lab_config.py list
```

Offline source checkout does not make recipe downloads available offline. See
[`docs/source-lock.md`](docs/source-lock.md) for the exact contract and limits.

Inspect the metadata before compiling:

```bash
./inspect.sh
./inspect.sh --lab platform-arm64
```

Look especially for:

```text
MACHINE="qemu-edu-x86-64"
QB_OPT_APPEND="... -device edu"
REQUIRED_VERSION_qemu-system-native="10.2.0"
```

For `platform-arm64`, expect `MACHINE="qemu-edu-platform-arm64"`,
`QB_SYSTEM_NAME="qemu-system-aarch64"`, and
`QB_OPT_APPEND="... -device qemu-edu-platform"`.

## 3. Build

```bash
./build.sh
./build.sh --lab platform-arm64
```

The first build downloads and compiles the toolchain, QEMU, Linux, BusyBox, the
module, and the root filesystem.  Subsequent builds reuse downloaded and
shared-state artifacts.

The important output directory is:

```text
build/tmp/deploy/images/qemu-edu-x86-64/
build-platform-arm64/tmp/deploy/images/qemu-edu-platform-arm64/
```

## 4. Boot in QEMU

```bash
./run.sh
./run.sh --lab platform-arm64
```

The script uses unprivileged SLIRP networking, a serial console, and snapshot
mode. Before `runqemu`, it uses the same fail-closed emulator preflight as the
automated runtime path. The selected machine's exact patch and patched source
must match their reviewed digests, the helper-native consumer sysroot is
populated, and the matching x86-64 or AArch64 executable must exist there.
Host-QEMU fallback is refused for both labs. Log in as `root`; the development
image has no password.

Inside the guest, run:

```bash
qemu-edu-test
```

For the ARM64 platform lab, use the bounded interface:

```bash
qemu-edu-platform-test identify
qemu-edu-platform-test scratch 0x12345678
qemu-edu-platform-test raise 0x400
qemu-edu-platform-test status
```

Expected highlights resemble:

```text
1234:11e8
input=0x12345678 result=0xedcba987 expected=0xedcba987
5! = 120
length=64 result=passed
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

## 5. Run the automated runtime suite

On a supported Linux build host, build, boot, and verify the complete baseline
without an interactive guest login:

```bash
./runtime-test.sh
./runtime-test.sh --lab platform-arm64
```

Before boot, the wrapper verifies the exact `qemu-system-native` append,
selected patch digest, effective recipe and dependency chain, the profile's
exact patched source, and the architecture-matching executable in
`qemu-helper-native`'s consumer sysroot. The PCI profile proves both guarded
DMA copies; the ARM64 profile pins its complete source group and proves that
the model has no DMA surface. It then runs Yocto's native `testimage`/OEQA path
over unprivileged SLIRP. The PCI suite
asserts PCI discovery, identification, liveness, factorial boundaries, default
and strict MSI, explicit INTx, real automatic fallback, strict-MSI failure,
cleanup, invalid inputs, timeout handling, the removed-device diagnostic,
bounded DMA in both directions, DMA completion, timeout recovery, and
unload/rebind cleanup. The
manual `qemu-edu-test` command remains available for teaching and rollback.

A successful run creates a closed, versioned result document at:

```text
build/evidence/qemu-edu-runtime-v3.json
build-platform-arm64/evidence/qemu-edu-platform-runtime-v1.json
```

See [`docs/guest-interface.md`](docs/guest-interface.md) for the sysfs contract
and [`docs/runtime-testing.md`](docs/runtime-testing.md) for test and evidence
semantics. The repository does not treat metadata-only CI or an unexecuted
runtime command as passing runtime evidence.

## 6. Follow one operation end to end

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

## 7. Where to read the project

Read files in this order:

1. `config/labs/index.json` and the selected manifest
2. `meta-qemu-edu/conf/machine/qemu-edu-x86-64.conf`
3. `meta-qemu-edu/conf/machine/qemu-edu-platform-arm64.conf`
4. `meta-qemu-edu/recipes-devtools/qemu/qemu-system-native_10.2.0.bbappend`
5. The selected driver recipe and source under `recipes-kernel/`
6. The selected diagnostic tool and OEQA case
7. `meta-qemu-edu/recipes-core/images/qemu-edu-image.bb`
8. `docs/architecture.md`
9. `docs/guest-interface.md`
10. `docs/runtime-testing.md`
11. `docs/mapping-to-real-hardware.md`

## 8. Edit/rebuild loop

For the default PCI lab, change `qemu_edu.c`, then run:

```bash
make rebuild-driver
./run.sh
```

For normal source changes, BitBake notices changed `file://` inputs.  Do not
habitually delete the whole build directory.

The same helper resolves the architecture-specific driver from the selected
manifest:

```bash
QEMU_EDU_LAB=platform-arm64 make rebuild-driver
./run.sh --lab platform-arm64
```

Useful commands after sourcing the environment:

```bash
source ./environment.sh
bitbake -e qemu-edu-driver | less
bitbake qemu-edu-driver -c devshell
bitbake qemu-edu-driver -c compile -f
bitbake qemu-edu-image
```

## 9. Exercises

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

### Exercise D: Compare MSI and INTx

The driver requests one vector with `pci_alloc_irq_vectors()` and resolves it
with `pci_irq_vector()`. Observe the default MSI path, then select legacy INTx:

```bash
cat /sys/bus/pci/drivers/qemu_edu/*:*/interrupt_mode
modprobe -r qemu_edu
modprobe qemu_edu interrupt_mode=intx
cat /sys/bus/pci/drivers/qemu_edu/*:*/interrupt_mode
```

Restore the default with `modprobe -r qemu_edu && modprobe qemu_edu`. Both paths
must acknowledge the EDU interrupt status. Because this driver combines
`pcim_enable_device()` with the locked Linux 6.18 managed-vector lifecycle, it
must not call `pci_free_irq_vectors()` itself.

### Exercise E: Trace bounded DMA

Write a length from 1 through 4096 to `dma_roundtrip`, then read the result,
interrupt count, and last status:

```bash
DEVICE=/sys/bus/pci/drivers/qemu_edu/*:*
cat $DEVICE/dma_mask_bits $DEVICE/dma_buffer_size
echo 64 > $DEVICE/dma_roundtrip
cat $DEVICE/dma_roundtrip $DEVICE/irq_count $DEVICE/last_irq_status
```

Follow the fixed registers at offsets `0x80` through `0x98`, the coherent
allocation, the 28-bit mask, the sentinel overwrite, and both completion IRQs
in `qemu_edu.c`. The interface intentionally accepts no DMA address. Keep the
A007 host-emulator bounds backport enabled; source verification, not unsafe
out-of-bounds input, is the host-side security gate.

### Exercise F: Move the driver in-tree

Put the source under the appropriate Linux source directory, add Kconfig and
Makefile entries, enable it with a kernel configuration fragment, and carry the
change through a `linux-yocto_%.bbappend`.  This is closer to long-term product
maintenance.

## 10. What QEMU cannot prove

QEMU is the right first step, but it cannot validate DDR initialization,
electrical behavior, clock/reset sequencing, pin multiplexing, analogue
interfaces, real DMA coherency bugs, interrupt wiring mistakes, or silicon
errata.  Use it to learn and automate the software architecture; use FPGA or
real hardware later for physical bring-up.

## 11. Licensing

This repository is mixed-license:

- Project scaffolding, documentation, Yocto layer metadata, helper scripts, and
  the user-space test utility are MIT-licensed. See `LICENSES/MIT.txt`.
- The attributed QEMU EDU bounds patch changes MIT-licensed upstream source and
  is mapped to MIT in `REUSE.toml`.
- The project-local QEMU platform-device patch and both example Linux kernel
  module sources/build files are GPL-2.0-only. See
  `LICENSES/GPL-2.0-only.txt`.
- The project-local Device Tree schema is dual licensed
  `(GPL-2.0-only OR BSD-2-Clause)` following kernel binding convention; see
  `LICENSES/BSD-2-Clause.txt`.

Individual files may carry `SPDX-License-Identifier` comments that state the
applicable license for that file.

The full file map, contribution rules, and REUSE policy are documented in
[`docs/licensing.md`](docs/licensing.md). Do not copy external material into the
repository unless its source and redistribution terms are clear.

## 12. Project development

Public development is milestone-driven. Each milestone uses one focused pull
request with explicit scope, validation evidence, licensing impact, and
rollback. The durable plan is in [`docs/maintenance-workflow.md`](docs/maintenance-workflow.md), and
contribution guidance is in [`CONTRIBUTING.md`](CONTRIBUTING.md).
Maintainer conventions begin in [`MAINTAINERS.md`](MAINTAINERS.md), with
machine-readable task state under [`docs/maintainers/`](docs/maintainers/).

Fast repository checks require Python 3.11 or newer:

```bash
make check
```

Fast checks do not replace Linux source/metadata validation, a full image build,
or QEMU runtime gates. [`docs/ci.md`](docs/ci.md) defines those evidence tiers;
[`docs/versioning.md`](docs/versioning.md) defines SemVer and Yocto compatibility.
