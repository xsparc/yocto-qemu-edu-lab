<!--
SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
SPDX-License-Identifier: MIT
-->

# M2 runtime-testing research — 2026-08-08

Primary sources and the exact locked OE-Core 6.0.2 implementation were checked
before designing A002.

## Findings

### Native Yocto runtime path

- Yocto 6.0 documents `testimage` as the supported image-build, QEMU-boot, and
  Python/OEQA runtime-test path. Layer tests belong under
  `lib/oeqa/runtime/cases`, and `TEST_SUITES` names required modules in order.
  Source: <https://docs.yoctoproject.org/6.0/test-manual/runtime-testing.html>
- The exact locked `testimage.bbclass` writes machine-readable OEQA results to
  `${LOG_DIR}/oeqa/testresults.json`, records statuses and durations, and fails
  the BitBake task when required tests fail. Source:
  <https://git.openembedded.org/openembedded-core/plain/meta/classes-recipe/testimage.bbclass?id=5d1aa5c806c061a2994f4decb59016610f093213>
- The locked loader discovers each layer's
  `lib/oeqa/runtime/cases` directory directly. The locked tree uses Python
  namespace directories rather than copied package initializers, so M2 adds
  only the uniquely named `qemu_edu.py` case. Source: same locked class above.

### Device contract and negative paths

- The QEMU 10.2 EDU specification documents PCI ID `1234:11e8`, a one-MiB
  MMIO BAR, version-shaped identification value, inversion liveness register,
  asynchronous factorial, explicit interrupt raise/acknowledge registers, and
  INTx as the default. The corresponding implementation initializes version
  1.0, yielding `0x010000ed` for this locked build.
  Sources: <https://gitlab.com/qemu-project/qemu/-/blob/v10.2.0/docs/specs/edu.rst>
  and <https://gitlab.com/qemu-project/qemu/-/blob/v10.2.0/hw/misc/edu.c>
- The existing driver already returns `ERANGE` above 12 and `ETIMEDOUT` after a
  two-second missing interrupt. The virtual device normally completes, so a
  read-only, false-by-default module-load seam is the smallest deterministic
  way to exercise the timeout without changing the successful baseline.
- Missing-device behavior can be tested through Linux's PCI remove/rescan
  controls. The case asserts that the function disappears from sysfs and
  `lspci`, then restores enumeration in `finally`. This proves guest-visible
  removal, not a second boot in which QEMU omits the hardware entirely.

### Evidence and runner capacity

- OEQA JSON includes arbitrary upstream result data and host-layer paths. M2
  converts only an allowlisted subset into a closed project schema so future CI
  and optional tools do not need to scrape prose or ingest raw logs.
- OEQA result files are cumulative. Each wrapper invocation therefore passes a
  fresh result directory through BitBake's environment allowlist and records
  both the native JSON SHA-256 and `testimage` exit code. An older pass cannot
  be selected after a new invocation fails.
- GitHub documents 14 GB SSD storage for standard public Linux runners. Yocto
  6.0 documents a 140 GB/32 GB general build-host baseline. The project has no
  repository runner, and no qualified WSL distribution/capacity was available
  in the current session. An isolated Docker Linux worker did provide user
  namespaces and sufficient disk for local software-emulated validation, but
  its roughly 15 GiB RAM remains below the broad Yocto recommendation. A
  standard PR job cannot truthfully be declared an adequate runtime gate.
  Sources:
  <https://docs.github.com/en/actions/reference/runners/github-hosted-runners>
  and
  <https://docs.yoctoproject.org/6.0/ref-manual/system-requirements.html>
- GitHub's current upload-artifact implementation describes version-4-and-newer
  artifacts as immutable and returns a SHA-256 artifact digest. If a protected
  runtime lane is added, only the small closed JSON document should be retained
  with short expiry. Source: <https://github.com/actions/upload-artifact>

### Validation discoveries

- The first complete local image attempt ran the roughly 15 GiB worker at its
  16-way default and `clang-native` was killed by the kernel during C++
  compilation. Limiting both `BB_NUMBER_THREADS` and `PARALLEL_MAKE` to four
  allowed all 4,738 image tasks to complete while preserving the cached work.
  This is resource evidence for this worker, not a new general host-support
  claim.
- The image booted under the exact locked QEMU and Dropbear reached the login
  prompt, but the first OEQA transport attempt found no host `ssh` executable.
  The runtime wrapper now checks that prerequisite before building and the
  Debian/Ubuntu package list includes `openssh-client`.
- BusyBox `ash` returned failed sysfs writes without diagnostic prose. A small
  guest helper now reports numeric Linux errno, allowing the suite to assert
  `ERANGE`, `EINVAL`, and `ETIMEDOUT` without locale or shell coupling.

## Decisions influenced

- Use one native OEQA module and preserve `qemu-edu-test` for manual learning.
- Require SLIRP and software emulation so runtime evidence does not depend on
  root networking or KVM.
- Make timeout injection inert, root/module-load-only, and independently
  restored.
- Treat OEQA output as upstream input, not the stable public project schema.
- Do not label metadata CI, an unexecuted workflow, or a resource-starved build
  as runtime evidence.
