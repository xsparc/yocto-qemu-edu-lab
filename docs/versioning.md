<!--
SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
SPDX-License-Identifier: MIT
-->

# Versioning and compatibility

The project follows Semantic Versioning 2.0.0 for tagged releases. `VERSION`
currently contains `0.2.0-dev`, a development identity rather than a published
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
| `0.2.0-dev` | 6.0.2 | `wrynose` | Repository, static, licensing, exact-source, parse, inspection, and native layer CI; M2 discovery completed a full image build and all 11 project runtime cases, with clean-revision qualification pending |

Compatibility is declared only after evidence. A newer Wrynose point release
can be proposed with source-resolution, metadata, build, and regression results.
A new Yocto series requires a pre-1.0 minor-version decision, layer metadata
review, migration notes, and the full relevant gates; changing only
`LAYERSERIES_COMPAT` is insufficient.

Schema versioning is independent of project SemVer. Unknown source-lock schema
versions fail closed. A schema change must state whether old readers can
continue safely and provide a deterministic migration or rollback.
