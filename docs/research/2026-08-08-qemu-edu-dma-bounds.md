<!--
SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
SPDX-License-Identifier: MIT
-->

# QEMU EDU DMA bounds research — 2026-08-08

This focused review establishes the host-emulator prerequisite for A007. The
baseline is merged M3 commit `2daea1223775c8aff91a0a7db3b8cdd693f74195`.

## Exact exposure and upstream fix

The locked OE-Core commit selects QEMU 10.2.0. Its `edu_check_range()` logs an
invalid internal DMA-buffer range, but the timer callback continues to subtract
the buffer base and calls `pci_dma_read()` or `pci_dma_write()`. The project
always instantiates that device with `-device edu`.

QEMU tracks this as guest-reachable arbitrary QEMU process memory access and
merged commit `42f599172ae023924f288e20af0ceed681674747`. The fix changes the
range helper to return a boolean and guards both copy directions. The commit was
authored by Torin Carey on 2025-11-05 and committed upstream on 2026-07-07. The
official patch bytes inspected for this decision have SHA-256
`8943a5b1cc549795f47f4915d74ade20d4f3d159cf359b409d8af912fe2ffe8a`;
the repository copy has a different digest because it adds Yocto's required
`Upstream-Status` field. Its normalized SHA-256 is
`73689608fcf9d8826ca95a105562c9962c79f207fb11a65e1a7451ab6085a72c`.
Applying it to the exact QEMU 10.2.0 source produces `hw/misc/edu.c` SHA-256
`32e2a035df36c25410d843e902cb4057aa43e83c047f682589d6f8539036ca2a`.

Primary sources:

- [QEMU security work item](https://gitlab.com/qemu-project/qemu/-/work_items/3852)
- [upstream fixing commit](https://gitlab.com/qemu-project/qemu/-/commit/42f599172ae023924f288e20af0ceed681674747)
- [QEMU 10.2.4 tag](https://gitlab.com/qemu-project/qemu/-/tags/v10.2.4)

QEMU 10.2.4 was released on 2026-06-25, before the fix was committed. No
released 10.2 point containing the fix was available during this review. No CVE
identifier was verified, so the project does not claim one.

## Exact Yocto consumer

The locked OE-Core metadata has distinct `qemu-native_10.2.0` and
`qemu-system-native_10.2.0` recipes. The former builds user-mode targets. The
latter builds the system emulators. `testimage.bbclass` depends on
`qemu-helper-native`; that helper depends on `qemu-system-native`, and
`runqemu` selects `qemu-system-x86_64` from its native staging bindir.

The narrow integration is therefore an exact
`qemu-system-native_10.2.0.bbappend`, not a wildcard or a target-QEMU append.
The EDU machine also requires version 10.2.0 so a future recipe selection
cannot silently drop the backport.

Primary locked sources:

- [qemu-system-native 10.2.0 recipe](https://github.com/openembedded/openembedded-core/blob/5d1aa5c806c061a2994f4decb59016610f093213/meta/recipes-devtools/qemu/qemu-system-native_10.2.0.bb)
- [qemu-helper-native recipe](https://github.com/openembedded/openembedded-core/blob/5d1aa5c806c061a2994f4decb59016610f093213/meta/recipes-devtools/qemu/qemu-helper-native_1.0.bb)
- [locked testimage class](https://github.com/openembedded/openembedded-core/blob/5d1aa5c806c061a2994f4decb59016610f093213/meta/classes-recipe/testimage.bbclass)
- [locked runqemu](https://github.com/openembedded/openembedded-core/blob/5d1aa5c806c061a2994f4decb59016610f093213/scripts/runqemu)

## Safety and licensing disposition

The affected `hw/misc/edu.c` carries the MIT license. The project preserves the
upstream patch author and trailers, adds only `Upstream-Status`, and maps the
patch to MIT in `REUSE.toml`. Project-owned recipe metadata, verification code,
tests, and documentation remain MIT.

The disposition is **adopt**: land A007 as a contract-preserving `0.3.1-dev`
security maintenance change before M4. Verification uses metadata selection,
an exact normalized patch digest, the exact post-patch source digest plus
guarded-copy placement, compilation, and the executable in `qemu-helper-native`'s
consumer sysroot before either public boot path. This closes locked `runqemu`'s
otherwise-permitted host-`PATH` fallback. The normal 14-case M3 suite then runs;
verification deliberately does not execute invalid-range or exploit input
against an unpatched host process.
