<!--
SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
SPDX-License-Identifier: MIT
-->

# Source lock contract

`config/sources.lock.json` is the source of truth for the external metadata
repositories and build composition used by this lab. Schema version 1 locks
Yocto 6.0.2 as three upstream repositories:

| Source | Release ref | Locked commit |
|---|---|---|
| BitBake | `yocto-6.0.2` | `178b39316042fd71d46e82ba6889e3b824024bb0` |
| OpenEmbedded Core | `yocto-6.0.2` | `8ecd6056805602dc99c4cd110b04e39ae5424610` |
| meta-yocto | `yocto-6.0.2` | `c81e26bda0cacc3e13b1fee7a98faadc449841bc` |

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

## Build composition

The lock also declares the environment script, BitBake binary path, build
directory default, distro, machine, target, and ordered layers. Public commands
remain `setup.sh`, `environment.sh`, `build.sh`, `inspect.sh`, and `run.sh`.
`BUILD_DIR` may relocate disposable build output; source URL, commit, distro,
machine, and target overrides are intentionally absent from the reproducible
path. `setup.sh` rewrites generated `bblayers.conf` to the exact locked order,
places its managed `local.conf` block last, and checks the effective `BBLAYERS`,
`DISTRO`, and `MACHINE` values. Use a separate `BUILD_DIR` for experimental
layers or overrides.

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
