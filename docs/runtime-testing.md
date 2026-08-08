<!--
SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
SPDX-License-Identifier: MIT
-->

# Automated runtime testing and evidence

The M3 suite uses the Yocto Project's native `testimage` and OEQA runtime framework. The
image inherits `testimage`, enables Dropbear for the development-only empty-root
login, selects `ping ssh qemu_edu`, uses unprivileged SLIRP networking, and
disables KVM for portable evidence. Under SLIRP, OEQA's `ping` bootstrap sees a
localhost target and does not send ICMP; `ssh` is the actual transport check.

Run the complete path on a supported Linux build host after setup:

```bash
./setup.sh
./runtime-test.sh
```

The host must provide the OpenSSH `ssh` client used by OEQA. The wrapper checks
for it before starting an expensive image build and reports the missing package
directly.

Before any guest boot, the wrapper fails closed through five host-emulator
checks:

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

After that preflight, the wrapper builds the one locked image target and runs:

```bash
bitbake qemu-edu-image -c testimage
```

and converts the matching result from that invocation's fresh OEQA directory
into:

```text
build/evidence/qemu-edu-runtime-v2.json
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

Policy and negative tests use `try/finally` restoration. A failed unload,
`msi_bus` restore, or default-MSI rebind is a test error, not a skip. DMA,
multiple devices, and real hardware remain outside M3.

## Evidence versions

The collector emits the closed version-2 schema at
`schemas/qemu-edu-runtime-evidence-v2.schema.json`. The version-1 schema remains
unchanged, and the validator continues to accept historical M2 documents. Old
version-1 readers correctly reject version 2; use the current dependency-free
validator or retain the M2 revision as the rollback path.

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
- machine, image, distro, host distro, OEQA start identifier, and native
  `testimage` exit code;
- explicit timeout fault-injection and PCI hot-removal mechanisms, including
  that the absence case is not a cold boot without the device;
- required case IDs, statuses, durations, and summary counts.

The project revision binds the runtime result to the committed A007 integration.
The shared preflight output proves effective QEMU selection, exact patched
source, and the native executable that locked `runqemu` selects. The same gate
protects `run.sh`, and it rejects the locked script's otherwise-permitted host
`PATH` fallback. Runtime schema 2 remains unchanged because the guest contract
and its 14 cases do not change.

A007 was qualified locally at clean commit
`46e2280448cf2a857f8599f677f1b1bd0284fa13`. After clearing an inherited forced
driver task, the final warning-free rebuild passed ping, SSH, and all 14 project
cases with no skips, failures, or errors. The closed evidence SHA-256 is
`861de3b963d0e2c89a17dc84f001914e7f1680a97fe476c04b7f3f00f971b5fe`; its
native OEQA input SHA-256 is
`c95ad4c9f7ec51b78d0c5b4db8a27c661c93f32745d8f7810f76f6300712089e`.
This is a local software-QEMU result, not a hosted attestation, physical-hardware
result, merge, tag, or release.

Interrupt-path and negative-path completion flags are conservative claims: they
become true only when the corresponding required case passes. A failure
document therefore cannot claim that a mechanism completed merely because its
test was selected or began running.

Raw SSH output, boot logs, absolute paths, environment variables, source text,
credentials, and arbitrary OEQA extras are excluded. Use OEQA logs for local
diagnosis; do not mistake a schema-valid failure document for a passing run.

Validate an existing document with:

```bash
python3 scripts/runtime_evidence.py validate \
  build/evidence/qemu-edu-runtime-v2.json --require-pass
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
