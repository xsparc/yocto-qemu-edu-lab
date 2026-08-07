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
| A002 | M2 | In Progress | Automated QEMU guest verification | A001 | Clean-revision runtime evidence and independent review |
| A003 | M3 | Proposed | Observable MSI learning stage | A002 | M2 merged and explicit approval |
| A004 | M4 | Proposed | Bounded EDU DMA support | A003 | M3 merged and explicit approval |
| A005 | M5 | Proposed | Portable platform-driver lab | A002 | Architecture choice and explicit approval |
| A006 | M6 | Proposed | Provider-neutral lab diagnostics | A002 | Stable evidence contract and explicit approval |
