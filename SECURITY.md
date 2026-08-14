<!--
SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
SPDX-License-Identifier: MIT
-->

# Security policy

## Supported code

Security fixes target the default branch and the currently documented Yocto
series. This educational lab is not a production BSP and does not promise
backports to historical commits or unlisted environments.

## Reporting a vulnerability

Use GitHub's private vulnerability-reporting or Security Advisory interface if
it is available for this repository. If it is unavailable, open a minimal issue
requesting a private contact channel and do not include exploit details,
credentials, private paths, or sensitive logs in the issue.

Include the affected revision, lab stage, impact, prerequisites, and a minimal
reproduction when safe. Maintainers will acknowledge the report, determine
scope, and coordinate a fix and disclosure appropriate to the educational
project.

## Security boundaries

- The default QEMU path uses unprivileged SLIRP networking and snapshot mode.
- QEMU remains a host process consuming guest-controlled device input. The EDU
  machine requires the reviewed native-system recipe and upstream bounds
  backport. Both public boot wrappers require the reviewed helper-native
  executable and refuse host-`PATH` fallback; validation must not execute an
  out-of-bounds exploit against an unpatched emulator.
- Build scripts fetch declared public source and must never require embedded
  credentials.
- Guest input reaches a kernel module and is treated as untrusted.
- Full Yocto builds and generated images are not sandbox guarantees.
- Optional future automation integrations begin read-only and require separate
  review before gaining state-changing tools.
- `qemu-edu-lab` performs only bounded local reads. It accepts no arbitrary
  path or URL, emits no raw logs or local identity, and uses fixed no-shell Git
  queries with hooks, prompting, paging, optional writes, and network operations
  disabled. Its host Git executable and concurrently mutable local filesystem
  remain documented trust boundaries.

Do not report ordinary setup questions as vulnerabilities; use a normal issue
and remove secrets from logs first.
