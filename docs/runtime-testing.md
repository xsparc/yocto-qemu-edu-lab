<!--
SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
SPDX-License-Identifier: MIT
-->

# Automated runtime testing and evidence

The PCI M4 suite and ARM64 M5 suite use the Yocto Project's native `testimage`
and OEQA runtime framework. The image inherits `testimage`, enables Dropbear
for the development-only empty-root login, selects the manifest's suite, uses
unprivileged SLIRP networking, and disables KVM for portable evidence. Under
SLIRP, OEQA's `ping` bootstrap sees a localhost target and does not send ICMP;
`ssh` is the actual transport check.

Run the complete path on a supported Linux build host after setup:

```bash
./setup.sh
./runtime-test.sh

# Independent ARM64 platform path
./setup.sh --lab platform-arm64
./runtime-test.sh --lab platform-arm64
```

The host must provide the OpenSSH `ssh` client used by OEQA. The wrapper checks
for it before starting an expensive image build and reports the missing package
directly.

Before the default PCI guest boots, the wrapper fails closed through five
host-emulator checks:

1. the exact `qemu-system-native_10.2.0.bbappend` is selected once;
2. effective `PN`, `PV`, `FILE`, and `SRC_URI` identify the reviewed recipe and
   backport;
3. testimage reaches that recipe through `qemu-helper-native`;
4. the normalized patch and post-patch `edu.c` match reviewed digests, and both
   DMA copies remain inside their range guards;
5. `do_populate_sysroot` and `qemu-helper-native:do_addto_recipe_sysroot`
   complete, then `qemu-system-x86_64` is required to be an executable inside
   that exact consumer sysroot before the image or tests run.

The verifier intentionally inspects source instead of executing invalid-range
input. An unpatched EDU DMA out-of-bounds test could corrupt the QEMU host
process and is outside the supported validation boundary.

For `platform-arm64`, the shared preflight dispatches to a separate closed
profile. It requires only the machine-scoped project-local platform patch in
effective `SRC_URI`, pins all seven post-patch QEMU source files, proves the
model has no DMA surface, populates the same helper-native consumer, and
requires `qemu-system-aarch64` inside that sysroot. The PCI patch must be absent
from the ARM recipe selection, and the ARM patch must be absent from PCI
selection.

After that preflight, the wrapper builds the one locked image target and runs:

```bash
bitbake qemu-edu-image -c testimage
```

and converts the matching result from that invocation's fresh OEQA directory
into:

```text
build/evidence/qemu-edu-runtime-v3.json
build-platform-arm64/evidence/qemu-edu-platform-runtime-v1.json
```

Set `BUILD_DIR` to relocate build products or `EVIDENCE_OUTPUT` to choose a
different evidence filename. The default `build/` output is ignored by Git.
Custom paths are caller-owned. Prefer locations outside the repository or
covered by ignore rules; otherwise generated files may appear in Git status.

## Required cases

The project layer supplies `qemu_edu.QemuEduRuntimeTests`, which asserts:

- module registration, one bound PCI device, and ID `1234:11e8`;
- the locked QEMU identification value `0x010000ed`;
- initial operation state, documented sysfs access modes, and MMIO liveness
  inversion;
- factorial values at 0, 5, and the 32-bit boundary 12, each with one handled
  completion interrupt;
- malformed, above-12, and unsigned-32-bit overflow failures without corrupting
  the last good result, using numeric Linux errno rather than localized shell
  diagnostics;
- default automatic and required MSI allocation, with exactly one vector,
  interrupt count, and two distinct acknowledged status values;
- explicit INTx selection with no MSI vector and equivalent delivery behavior;
- real PCI-core `auto` fallback and required-MSI probe failure after temporarily
  disabling MSI through the unbound endpoint's root-only `msi_bus` testing ABI;
- successful managed-vector cleanup, restoration of the original `msi_bus`
  value, and return to the known-good default MSI binding;
- zero interrupt rejection;
- the real factorial timeout path through bounded module-load fault injection;
- PCI removal, the resulting missing-device diagnostic, and successful PCI
  rescan/rebinding. This uses Linux hot removal rather than a second QEMU boot.
- the reported 28-bit mask, 4,096-byte buffer, length-only sysfs mode, and
  disabled-by-default missing-completion seam. A bound-versus-unbound sysfs
  comparison requires the exact documented driver attribute set, so an added
  driver-created DMA-address file fails the contract rather than escaping the
  evidence projection;
- verified RAM-to-EDU-to-RAM transfers at lengths 1, 3, and 4096, with exactly
  two handled `0x00000100` completion interrupts per round trip;
- rejection of zero, over-limit, negative, and malformed lengths without
  changing the last successful result;
- a bounded missing-completion timeout, followed by default module, MSI, and
  DMA recovery; and
- unload cleanup and a known-good default MSI plus DMA rebind.

Policy and negative tests use `try/finally` restoration. A failed unload,
`msi_bus` restore, or default-MSI rebind is a test error, not a skip. Arbitrary
DMA addresses, streaming DMA, multiple devices, and real hardware remain out of
scope.

### ARM64 platform suite

`qemu_edu_platform` has nine exact, ordered cases:

- module registration;
- the single generated FDT node, exact `qemu,edu-platform` compatible,
  4 KiB `reg`, and level-high interrupt specifier;
- one bound Linux platform device, one MMIO resource, and one requested IRQ;
- exact identification `0x0100a64e` and zeroed initial state;
- 32-bit scratch boundaries and rejection of negative, overflow, and malformed
  inputs without changing the last valid value;
- two distinct `0x00000400` and `0x00000800` interrupt
  raise/status/acknowledgement cycles;
- rejection of a zero interrupt mask without a count change; and
- unload cleanup followed by module rebind and a known-good interrupt.

The suite does not exercise DMA, claim a physical interrupt controller, or
generalize QEMU `virt` timing to hardware.

## Evidence versions

The collector emits the closed version-3 schema at
`schemas/qemu-edu-runtime-evidence-v3.schema.json`. Version-1 and version-2
schemas remain unchanged, and the validator continues to accept historical M2
and M3 documents. Old readers correctly reject unknown versions; use the
current dependency-free validator or retain the corresponding historical
revision as the rollback path.

The collector additionally enforces semantic invariants that JSON Schema alone
does not express: every required case appears once and in order, summary counts
match statuses, and `result=passed` means every required case passed.

Evidence records only bounded facts:

- project version, Git revision, and dirty state;
- source-lock SHA-256, native OEQA result SHA-256, and declared Yocto
  version/series;
- guest-interface and suite contract names/versions plus `TEST_TYPE=runtime`;
- conservative, case-bound claims for default MSI, explicit INTx, automatic
  fallback, required-MSI failure, and cleanup recovery;
- conservative, case-bound claims for the length-only DMA interface, both
  transfer directions and bounds, exact completion status, rejected input,
  missing-completion recovery, and teardown/rebind;
- machine, image, distro, host distro, OEQA start identifier, and native
  `testimage` exit code;
- explicit timeout fault-injection and PCI hot-removal mechanisms, including
  that the absence case is not a cold boot without the device;
- required case IDs, statuses, durations, and summary counts.

The project revision binds the runtime result to the exact committed implementation.
The shared preflight output proves effective QEMU selection, exact patched
source, and the native executable that locked `runqemu` selects. The same gate
protects `run.sh`, and it rejects the locked script's otherwise-permitted host
`PATH` fallback. Historical runtime schemas 1 and 2 remain unchanged; M4 uses a
new version because the guest contract and required case list change.

The ARM64 path emits the separate closed
`qemu-edu-platform-runtime-evidence-v1.schema.json` kind. It records the
source-lock, lab-index, selected-manifest, and native OEQA digests; the exact
nine cases; and conservative Device Tree, scratch, interrupt, negative-input,
and lifecycle completion claims. A failed, skipped, missing, reordered, or
stale case cannot produce a passing document. This new kind does not translate
or mutate historical PCI evidence versions 1 through 3. M5 runtime evidence is
not claimed until the clean ARM64 suite and the existing PCI regression both
complete on adequate Linux capacity.

A007 was qualified locally at clean commit
`46e2280448cf2a857f8599f677f1b1bd0284fa13`. After clearing an inherited forced
driver task, the final warning-free rebuild passed ping, SSH, and all 14 project
cases with no skips, failures, or errors. The closed evidence SHA-256 is
`861de3b963d0e2c89a17dc84f001914e7f1680a97fe476c04b7f3f00f971b5fe`; its
native OEQA input SHA-256 is
`c95ad4c9f7ec51b78d0c5b4db8a27c661c93f32745d8f7810f76f6300712089e`.
This is a local software-QEMU result, not a hosted attestation, physical-hardware
result, merge, tag, or release.

That A007 record remains the known-good pre-DMA baseline. A004/M4 was qualified
locally at clean implementation commit
`8574eaffe206f8235a5da57461ded0ecbdbbf60b`. A Debian 12 worker used
`BB_NUMBER_THREADS=4`, `PARALLEL_MAKE=-j 4`, software QEMU, and no `/dev/kvm`.
The exact Yocto 6.0.2 build completed all 4,738 image tasks, and the final run
passed ping, SSH, and all 19 project cases in 165.509 seconds. The complete
result was 21/21 with no skips, failures, or errors.

The closed version-3 evidence records `dirty=false`, `testimage_exit_code=0`,
19/19 project passes, and all five conservative DMA completion claims true.
Its SHA-256 is
`f97b24335cd9579eaf825cf1c06e54ae1742f069f1afa2a4c8e6fa2f162856c2`; the
bound native OEQA input SHA-256 is
`1f8b1756faf079a0996070846f4e4aee5535e71d205f5e232c9cbeff395e07c5`.
This is local software-QEMU qualification, not a hosted attestation,
physical-hardware result, independent review, publication, merge, tag, or
release.

The post-merge evidence-oracle correction was separately qualified at clean
commit `fe08e738107b9f69567e95d547e8b81de9a92444`. The correction changes the
host-side OEQA contract rather than the driver or image, so the retained exact
image tasks were verified from cache rather than mislabeled as a new rebuild.
Offline setup, effective build composition, patched QEMU source, and the actual
`qemu-helper-native` consumer passed their fail-closed checks before a fresh
testimage invocation. Ping, SSH, and all 19 project cases passed in 172.305
seconds; the complete result was 21/21 with no skips, failures, or errors.

The corrected version-3 evidence records `dirty=false`, exact revision
`fe08e738107b9f69567e95d547e8b81de9a92444`, `testimage_exit_code=0`, and all
five conservative DMA completion claims true. Its SHA-256 is
`c51de37dc60c69e5f697fb0ae8ab74fbc1c0520724554b73904783533ca2b4ea`; the
bound native OEQA input SHA-256 is
`918a7ade794afbc958c428eff358e2f5740e6e89bb63f8bb90d063b014a419a9`.
The ignored local copies are
`build/evidence/qemu-edu-runtime-v3-fe08e73.json` and
`build/evidence/qemu-edu-runtime-v3-fe08e73.oeqa.json` so a reviewer can
recompute both hashes without treating them as published artifacts.

Interrupt-path, negative-path, and DMA-path completion flags are conservative claims: they
become true only when the corresponding required case passes. A failure
document therefore cannot claim that a mechanism completed merely because its
test was selected or began running.

Raw SSH output, boot logs, absolute paths, environment variables, source text,
credentials, and arbitrary OEQA extras are excluded. Use OEQA logs for local
diagnosis; do not mistake a schema-valid failure document for a passing run.

Validate an existing document with:

```bash
python3 scripts/runtime_evidence.py validate \
  build/evidence/qemu-edu-runtime-v3.json --require-pass
```

## Host and CI boundary

Yocto documents a broad 140 GB free-disk and 32 GB RAM baseline. A standard
GitHub-hosted Linux runner exposes 14 GB storage, and this repository currently
has no protected larger runner. Fast and metadata CI therefore continue to
prove only their named tiers until an actual full build and `testimage` run is
recorded. Unknown or resource-blocked runtime evidence is not a pass.

If runtime evidence is later retained by CI, publish only the closed JSON file
as an immutable, short-retention artifact and record its SHA-256 digest. Never
upload build trees, downloads, shared state, raw environment dumps, or logs that
have not been reviewed for secrets.

On a lower-memory local worker, set conservative BitBake and make concurrency
in the generated `local.conf` and record it with the result. For example, the
M2 validation worker used:

```bitbake
BB_NUMBER_THREADS = "4"
PARALLEL_MAKE = "-j 4"
```

These are worker-capacity settings, not source-lock inputs. An out-of-memory
task remains a failed build even if a later resource-capped retry succeeds.
