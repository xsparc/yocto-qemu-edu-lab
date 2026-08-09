<!--
SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
SPDX-License-Identifier: MIT
-->

# Delivery ledger

`tasks.toml` is authoritative. This view is kept compact for maintainers.

| ID | Milestone | Status | Outcome | Dependency | Next gate |
|---|---|---|---|---|---|
| A000 | M0 | Done | Project vision and trustworthy execution | - | Merged through pull request #1 |
| A001 | M1 | Done | Reproducible setup and fast validation | A000 | Merged through pull request #2 |
| A002 | M2 | Done | Automated QEMU guest verification | A001 | Merged through pull request #3 |
| A003 | M3 | Done | Observable MSI learning stage | A002 | Merged through pull request #4 |
| A007 | M3.1 | Done | Harden the host EDU DMA bounds | A003 | Squash-merged through pull request #5 as `083ddf5` |
| A004 | M4 | In Progress | Bounded EDU DMA support | A003, A007 | Pull request #7 runtime and hosted gates pass; complete required reviews |
| A005 | M5 | Proposed | Portable platform-driver lab | A002 | Architecture choice and explicit approval |
| A006 | M6 | Proposed | Provider-neutral lab diagnostics | A002 | Stable evidence contract and explicit approval |
