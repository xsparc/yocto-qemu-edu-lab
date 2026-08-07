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
- Build scripts fetch declared public source and must never require embedded
  credentials.
- Guest input reaches a kernel module and is treated as untrusted.
- Full Yocto builds and generated images are not sandbox guarantees.
- Optional future agent integrations begin read-only and require separate
  review before gaining state-changing tools.

Do not report ordinary setup questions as vulnerabilities; use a normal issue
and remove secrets from logs first.
