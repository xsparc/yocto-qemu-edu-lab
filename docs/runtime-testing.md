<!--
SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
SPDX-License-Identifier: MIT
-->

# Automated runtime testing and evidence

M2 uses the Yocto Project's native `testimage` and OEQA runtime framework. The
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

The wrapper builds the one locked image target, runs:

```bash
bitbake qemu-edu-image -c testimage
```

and converts the matching result from that invocation's fresh OEQA directory
into:

```text
build/evidence/qemu-edu-runtime-v1.json
```

Set `BUILD_DIR` to relocate build products or `EVIDENCE_OUTPUT` to choose a
different evidence filename. Both paths remain local; generated build and
evidence output is ignored by Git.

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
- legacy INTx allocation, interrupt count, acknowledgement, and zero rejection;
- the real factorial timeout path through bounded module-load fault injection;
- PCI removal, the resulting missing-device diagnostic, and successful PCI
  rescan/rebinding. This uses Linux hot removal rather than a second QEMU boot.

Negative tests use `try/finally` restoration. A failed restore is a test error,
not a skip. MSI, DMA, multiple devices, and real hardware remain outside M2.

## Evidence version 1

The closed schema is
`schemas/qemu-edu-runtime-evidence-v1.schema.json`. The dependency-free
collector additionally enforces semantic invariants that JSON Schema alone
does not express: every required case appears once and in order, summary counts
match statuses, and `result=passed` means every required case passed.

Evidence records only bounded facts:

- project version, Git revision, and dirty state;
- source-lock SHA-256, native OEQA result SHA-256, and declared Yocto
  version/series;
- guest-interface and suite contract names/versions plus `TEST_TYPE=runtime`;
- machine, image, distro, host distro, OEQA start identifier, and native
  `testimage` exit code;
- explicit timeout fault-injection and PCI hot-removal mechanisms, including
  that the absence case is not a cold boot without the device;
- required case IDs, statuses, durations, and summary counts.

Negative-path `exercised` and `fault_injected` flags are conservative completion
claims: they become true only when the corresponding required case passes. A
failure document therefore cannot claim that a mechanism completed merely
because its test was selected or began running.

Raw SSH output, boot logs, absolute paths, environment variables, source text,
credentials, and arbitrary OEQA extras are excluded. Use OEQA logs for local
diagnosis; do not mistake a schema-valid failure document for a passing run.

Validate an existing document with:

```bash
python3 scripts/runtime_evidence.py validate \
  build/evidence/qemu-edu-runtime-v1.json --require-pass
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
