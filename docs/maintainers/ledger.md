<!--
SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
SPDX-License-Identifier: MIT
-->

# Delivery ledger

`tasks.toml` is authoritative. This view is kept compact for maintainers.

| ID | Milestone | Status | Outcome | Dependency | Next gate |
|---|---|---|---|---|---|
| A000 | M0 | In Progress | Project vision and trustworthy execution | - | Review and merge pull request #1, then explicitly approve A001 |
| A001 | M1 | Proposed | Reproducible setup and fast validation | A000 | M0 merged and explicit approval |
| A002 | M2 | Proposed | Automated QEMU guest verification | A001 | M1 merged and explicit approval |
| A003 | M3 | Proposed | Observable MSI learning stage | A002 | M2 merged and explicit approval |
| A004 | M4 | Proposed | Bounded EDU DMA support | A003 | M3 merged and explicit approval |
| A005 | M5 | Proposed | Portable platform-driver lab | A002 | Architecture choice and explicit approval |
| A006 | M6 | Proposed | Provider-neutral lab diagnostics | A002 | Stable evidence contract and explicit approval |
