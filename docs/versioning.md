<!--
SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
SPDX-License-Identifier: MIT
-->

# Versioning and compatibility

The project follows Semantic Versioning 2.0.0 for tagged releases. `VERSION`
currently contains `0.4.0-dev`, a development identity rather than a published
release. Creating a tag, release, or artifact remains a separate maintainer
decision.

## Pre-1.0 policy

- `0.MINOR.0` may add a curriculum stage or deliberately change a documented
  command, schema, guest interface, or supported Yocto series. The pull request
  must include migration and rollback guidance.
- `0.MINOR.PATCH` preserves documented contracts while fixing defects,
  explanations, tests, or compatible locked point releases.
- Pre-release suffixes such as `-dev` and `-rc.1` identify non-final states.
- Milestone numbers and versions are related planning concepts but are not
  automatically identical. Completing a milestone does not publish a version.

After `1.0.0`, incompatible public-contract changes require a major version.

## Public compatibility contracts

Version review applies to:

- source-lock schema and machine-readable JSON status fields;
- documented command names, arguments, exit meanings, and configuration paths;
- Yocto series, machine, layer, image target, and required host claims;
- guest-visible interfaces and runtime evidence schemas.

Implementation details, prose corrections, and non-normative examples are not
automatically public APIs.

## Compatibility matrix

| Project line | Yocto release lock | Series | Evidence available |
|---|---|---|---|
| `0.2.0-dev` | 6.0.2 | `wrynose` | Repository, static, licensing, exact-source, parse, inspection, and native layer CI; clean commit `6479681` completed the full image build and passed all 11 project runtime cases under software QEMU with validated version-1 evidence |
| `0.3.0-dev` | 6.0.2 | `wrynose` | Clean commit `3ea0204` completed the exact locked image path and passed ping, SSH, and all 14 project cases under software QEMU with validated version-2 evidence; no physical-hardware or release claim is implied |
| `0.3.1-dev` | 6.0.2 | `wrynose` | Clean commit `46e2280` compiled and staged the exact patched native emulator, rebuilt the driver/image without taint, and passed ping, SSH, and all 14 project cases with validated version-2 evidence; pull request #5 passed hosted gates and squash-merged as `083ddf5`, with no tag or release |
| `0.4.0-dev` | 6.0.2 | `wrynose` | Clean implementation commit `8574eaf` completed the exact locked image path and passed all 19 project cases; clean correction commit `fe08e73` then passed the strengthened sysfs oracle and complete 19-case suite with validated version-3 evidence. Pull request #6 squash-merged as `918efaa`; pull request #7 review-record commit `a3a42b6` passed hosted Fast checks run `31397396385` and Yocto metadata run `31397396470`, and every required review passes. GitHub's check state for the then-current merge head is the authoritative final hosted gate; merge, tag, and release remain pending |

Runtime documents are unsigned local reports. Their task records state whether
a digest was independently recomputed. They are not hosted provenance
attestations or physical-hardware results.

`0.3.1-dev` was a pre-release patch line because A007 corrected the host emulator
without changing the guest contract, runtime evidence schema, or curriculum
interface. `0.4.0-dev` is the current minor development line because bounded
DMA adds a curriculum stage, guest-interface version 3, five required runtime
cases, and evidence schema 3. Neither identity implies a tag or release.

Compatibility is declared only after evidence. A newer Wrynose point release
can be proposed with source-resolution, metadata, build, and regression results.
A new Yocto series requires a pre-1.0 minor-version decision, layer metadata
review, migration notes, and the full relevant gates; changing only
`LAYERSERIES_COMPAT` is insufficient.

Schema versioning is independent of project SemVer. Unknown source-lock and
runtime-evidence schema versions fail closed. Runtime evidence version 1 is an
immutable M2 contract and version 2 is an immutable M3 contract. The current
validator accepts versions 1, 2, and 3, while the collector emits only version
3. Older readers reject unknown versions and can roll back to their matching
project revision without translating claims. Any later schema change must state
whether old readers can continue safely and provide a deterministic migration
or rollback.
