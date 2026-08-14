<!--
SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
SPDX-License-Identifier: MIT
-->

# Source lock contract

`config/sources.lock.json` is the source of truth for external metadata
repositories. Schema version 1 locks Yocto 6.0.2 as three upstream
repositories:

| Source | Release ref | Locked peeled commit |
|---|---|---|
| BitBake | `yocto-6.0.2` | `acfe02fa38b5da9e6a36c6cedcf91d4fcbefbfbd` |
| OpenEmbedded Core | `yocto-6.0.2` | `5d1aa5c806c061a2994f4decb59016610f093213` |
| meta-yocto | `yocto-6.0.2` | `24c24cef5d1523fefe43a3e3d34667b37ae551f3` |

This replaces the old `poky/` combo-checkout assumption. Yocto 6.0 Poky is a
composition of these repositories; the combo repository is not updated for
Wrynose.

## Commands

```bash
python3 scripts/source_lock.py validate
python3 scripts/source_lock.py status
python3 scripts/source_lock.py --format json status
python3 scripts/source_lock.py sync
python3 scripts/source_lock.py sync --offline
```

- `validate` checks the closed schema without accessing Git or the network.
- `status` verifies exact origins, object formats, commits, detached heads,
  cleanliness, and required paths without fetching.
- `sync` fetches the declared release and branch refs into project-namespaced
  Git refs, proves that the tag resolves to the locked commit and that the
  commit belongs to the declared branch, then creates a detached checkout.
- `sync --offline` never fetches and succeeds only when every locked commit is
  already available locally.
- `--format json` returns stable, versioned status fields for CI and later
  diagnostic adapters. Exit `0` is success, `1` is checkout drift reported by
  `status`, and `2` is an invalid contract or unsafe setup condition.

`./setup.sh` performs online sync and configuration. `./setup.sh --check` is a
read-only checkout check, and `./setup.sh --offline` configures from cached Git
objects. Repeated setup of the exact state is idempotent.

## Safety behavior

All source paths must be normalized repository-relative paths below `layers/`.
Origins must be credential-free HTTPS URLs, commits must be full lowercase
SHA-1 object IDs, and schema version 1 rejects unknown fields or source IDs.
Git is invoked with argument arrays, never a shell command string.

The helper refuses dirty trees, wrong origins, wrong object formats, attached
branches, and unexpected `HEAD` commits. It never runs `reset`, `clean`, or a
recursive delete, and it never replaces an existing checkout silently. A
failed first fetch may leave an initialized directory for diagnosis; the
operator decides whether to move or remove it.

Exact commits prevent ordinary branch and tag drift. They do not authenticate
an upstream Git server beyond HTTPS transport, make recipe downloads available
offline, prove bit-for-bit image reproducibility, or replace signatures and
provenance. Full offline builds additionally need a populated download mirror
and `BB_NO_NETWORK`; those are later evidence gates.

## Lab composition

`config/labs/index.json` binds closed lab manifests by SHA-256. A manifest owns
a top-level `build` or `build-<lab>` generated-output directory, distro,
machine, driver target, one image target, ordered layers,
emulator preflight, runtime suite, and evidence profile. Unknown fields,
profiles, paths, digests, duplicate build directories, and duplicate machines
fail closed. `pci-x86-64` is the no-argument default; `platform-arm64` is
selected with `--lab platform-arm64` and uses a separate build directory.

The source-lock schema-v1 `build` values remain an exact compatibility mirror
for the default PCI build directory, distro, machine, targets, and layers, so
existing source-lock consumers do not silently change behavior. The manifest
also names its driver target. New composition consumers use
`scripts/lab_config.py`; source identity remains solely in the source lock.
Platform evidence records source lock, lab index, and selected manifest digests
separately. Immutable PCI evidence schemas 1 through 3 remain unchanged and
therefore do not gain new fields.

Public commands remain `setup.sh`, `environment.sh`, `build.sh`, `inspect.sh`,
`run.sh`, and `runtime-test.sh`. Executable wrappers accept `--lab`; the sourced
environment selects through `QEMU_EDU_LAB`. `BUILD_DIR` may explicitly relocate
disposable output. Setup rewrites `bblayers.conf` to the selected exact order,
places its managed `local.conf` block last, and verifies effective `BBLAYERS`,
`DISTRO`, and `MACHINE` values.

## Evolution and rollback

The project-owned format is intentionally small, not a general orchestration
framework. Re-evaluate current kas and upstream `bitbake-setup` when an external
BSP or QEMU repository is added, several build configurations need includes or
matrices, or source-signature policy is introduced. Preserve a translation and
rollback plan before changing formats.

Reverting the M1 change restores the former scripts. It does not delete
`layers/`, `poky/`, downloads, shared state, or build output. The old `poky/`
path remains ignored solely to avoid data loss; it is not a supported Wrynose
fallback.

When a reviewed lock update changes a commit, first check each old checkout for
local work. Move a clean, detached old directory aside (for example,
`layers/openembedded-core` to `layers/openembedded-core-6.0.2`) and rerun
`setup.sh` so the locked path is created afresh. The helper deliberately will
not move, reset, or delete it for you. Use a fresh `BUILD_DIR` while proving the
new point release; remove old data only after deciding it is no longer needed.
