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
| A004 | M4 | Done | Bounded EDU DMA support | A003, A007 | Documentation closeout squash-merged through pull request #8 as `01ff717` |
| A005 | M5 | Done | Portable ARM64 platform-driver lab | A004 | Squash-merged through pull request #9 as `e2d703e` |
| A006 | M6 | Done | Provider-neutral lab diagnostics | A005 | Squash-merged through pull request #11 as `b569199` |
| A008 | M7 | In Progress | SPDX 3 image-composition evidence | A006 | Separately authorize publication and hosted checks |
