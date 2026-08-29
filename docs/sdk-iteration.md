<!--
SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
SPDX-License-Identifier: MIT
-->

# Direct-eSDK application iteration

M8 adds one deliberately narrow application-development loop to each declared
lab. It demonstrates the Yocto direct extensible SDK and `devtool` without
creating a standalone SDK installer or changing the base image.

## Supported command

First materialize the exact locked sources with `setup.sh`. Then run the
selected development profile on an adequately sized native Linux host:

```bash
./sdk-test.sh
./sdk-test.sh --lab platform-arm64
```

The command always selects `build-sdk-<lab>` from the digest-bound manifest.
It does not honor a caller-supplied build directory, recipe, source path,
target, guest path, emulator argument, SSH endpoint, key, or guest command.
Normal `build` and `build-platform-arm64` roots are not used as workspaces.

The development root is local build output and remains ignored by Git. It can
be large: the direct model still uses the complete Yocto build graph. Public
pull-request runners perform contract and metadata checks only; they do not
claim that this state-changing loop ran.

## Closed lifecycle

`scripts/sdk_iteration.py` owns the complete transition:

1. On native Linux, remove the selected stale evidence file, then require a
   clean Git subject and ready exact source checkouts before sourcing the OE
   environment. Parse the
   locked devtool entry point and standard, deployment, and IDE-SDK plugins
   for the fixed command surface, then require `bitbake`, `bitbake-getvar`,
   `bitbake-layers`, `devtool`, and `runqemu` to resolve to their declared
   locked checkouts. Before sourcing the locked OE environment, clear ambient
   internal root, template, BitBake-passthrough, Python, and Git object/config
   overrides that could redirect setup. The fixed `/bin/bash -p` entry point
   ignores `BASH_ENV` and imported shell functions before script startup.
   Refuse symbolic-link or shell-unsafe
   repository, development-root, and configuration paths before environment
   setup. Resolve regular native `git`, `ssh`, and `scp` prerequisites, and keep
   the resolved Git directory ahead of OE-Core's `scripts/git` helper after
   environment setup. Replace the inherited `PYTHONPATH` with the verified
   locked BitBake library, disable user-site
   imports and bytecode writes, and remove Python and shell startup-injection
   variables from every child command and runqemu session. After locked OE
   setup, atomically replace `local.conf` and `bblayers.conf` with the complete
   profile-owned forms, reject automatically parsed `site.conf`, `auto.conf`,
   `toolcfg.conf`, or `bblock.conf`,
   seed `BBPATH` with a controller-owned configuration root containing only
   the exact `conf/local.conf`, rather than the build root or an empty search
   component,
   and only then require authoritative DISTRO/MACHINE/BBLAYERS values and the
   selected patched native-QEMU consumer.
2. Build the unchanged base image, create or reattach one generated workspace
   layer, require the closed `devtool.conf` to select only that exact workspace,
   pin the generated Wrynose `layer.conf` executable statements, and reject
   any retained plugin,
   recipe, append, symbolic link, or unknown workspace entry before the layer
   joins `BBPATH`. The project layer may not provide a devtool plugin or a
   sample-recipe append; metadata CI also requires the one effective sample
   `SRC_URI`.
3. Copy the fixed MIT sample into the manifest-selected `learner-source`
   directory outside the executable workspace layer and change its one baseline
   output to `qemu-edu-sdk-sample workspace`.
4. Run the exact locked commands `devtool modify -n`, `devtool build`, and
   `devtool ide-sdk --mode modified --ide none` for only the declared recipe
   and image. Hash the bounded regular file under the effective recipe install
   root before deployment.
5. Start locked `runqemu` in snapshot, SLIRP, and serial-console mode. Accept
   only its bounded `127.0.0.1:<ephemeral>-:22` forward. Direct checks use a
   resolved native OpenSSH executable with an empty user configuration and
   fixed loopback, proxy, identity, forwarding, batch, timeout, and host-key
   options.
   `devtool deploy-target` and `undeploy-target` receive temporary executable
   `ssh` and `scp` wrappers, a shell-safe temporary root, and the same policy
   through their locked `--ssh-exec` option. Deployment explicitly disables
   stripping. Host SSH configuration, `TMPDIR`, and a different `scp` on the
   later search path therefore cannot redirect or alter the fixed transfer.
   The selected development image intentionally permits the empty root account
   used by the existing local runtime lab.
6. Prove the guest path is absent, prove `uname -m`, deploy only the sample
   with locked `devtool deploy-target`, require the guest SHA-256 to match the
   locally built installed file, execute it, undeploy it, and prove the path is
   absent again.
7. Stop the emulator process group, reset the recipe, require an empty
   `devtool status` and an inert generated workspace tree, remove the workspace
   layer from effective composition, retain the separately stored learner
   source, and boot once more to prove cold-image absence.
8. Finish target, emulator, recipe, and workspace restoration before publishing
   a pass-only evidence document atomically. Any earlier error or interruption
   leaves no selected evidence. `SIGTERM`, `SIGHUP`, and keyboard interruption
   terminate and reap the complete child process group before the same cleanup
   state machine runs. Repeated cancellation is recorded and deferred until
   restoration and evidence removal have been attempted. The final validated
   evidence replacement is the atomic completion boundary: a signal recorded
   inside that short publication transaction is treated as arriving after
   successful completion, and the command returns the committed success.

The retained source remains under the disposable development root, but outside
the workspace layer, so locked `devtool reset` leaves it in place and a learner
can inspect the result. IDE-neutral output is atomically retained in the fixed
`learner-ide-sdk` sibling before reset; it is neither traversed nor executed by
the controller. Cleanup does not recursively delete a build directory, learner
source, or generated IDE output. A maintainer removing generated roots must
first resolve and verify the exact manifest-selected paths.

Before another `sdk-test.sh` run for the same lab, move or archive both
`build-sdk-<lab>/learner-source/qemu-edu-sdk-sample` and
`build-sdk-<lab>/learner-ide-sdk` outside the selected development build root.
The learner source retains its compiled binary and devtool inspection links in
addition to the edited source. The controller intentionally rejects unexpected
retained source content and an existing IDE destination before mutation; it
never overwrites or deletes either result.

Status checks use locked `devtool -q status`, so only workspace recipe records
are interpreted; informational logger output cannot be mistaken for a modified
recipe. Cleanup classifies bounded raw `local.conf` and `bblayers.conf` bytes and
validates the closed `devtool.conf` plus active workspace before invoking any
devtool subcommand. It requires the single versioned generated append's exact locked-source form
and binds those bytes to its exact recipe-relative `.devtool_md5` record, uses
`reset --no-clean` so recovery does not run a
metadata clean task, and requires the checksum file and append directory to be
empty afterward. A recipe already known to be modified cannot reach even
`devtool status` without that authenticated active state. If a closed inert
workspace reveals a modified recipe during status discovery, cleanup repeats
the active-state authentication before reset. If a retained layer contains an
unknown file, plugin path,
metadata change, symbolic link, unsafe checksum record, or unknown
configuration, the controller does not load devtool from that `BBPATH`; it
atomically restores the manifest-owned build composition directly and fails
the run. A failed `bitbake-layers remove-layer` receives the same direct
restoration fallback. Cleanup steps are exception-isolated so QEMU termination
and later restoration are still attempted after an earlier cleanup failure.

## Evidence contract

Successful runs write:

```text
build-sdk-<lab>/evidence/qemu-edu-sdk-evidence-v1.json
```

Validate a retained document with the dependency-free semantic validator:

```bash
python3 scripts/sdk_evidence.py validate \
  build-sdk-pci-x86-64/evidence/qemu-edu-sdk-evidence-v1.json \
  --require-pass --require-revision "$(git rev-parse HEAD)" \
  --require-current-inputs
```

Schema version 1 is immutable and pass-only. Its 20 ordered checks include the
locked-tooling preflight and bind the clean project
revision and version, source-lock digest, exact OE-Core commit, lab index and
manifest digests, selected development identity, retained source digest,
architecture, built/deployed artifact SHA-256, expected output, and the
complete ordered lifecycle. It records
no timestamp, duration, host identity, port, credential, key, host path, raw
log, image, binary, SDK tree, or arbitrary command output.

Fast CI validates the same documents independently with the exact hash-locked
Draft 2020-12 test-only dependency set already used for the diagnostics and
SPDX schemas. The project runtime remains Python-standard-library-only.

## Trust and licensing boundary

The sample, controller, tooling verifier, wrapper, schema, tests, and projected
evidence are MIT. `devtool` and its plugins are parsed and executed from the
exact locked OE-Core checkout
under GPL-2.0-only; their source and expressive generated comments are not
copied, repackaged, or redistributed here. The controller compares only the
executable metadata statements it independently owns; full-line generated
comments are inert. Host OpenSSH is an external `SSH-OpenSSH` prerequisite,
and Bash is external GPL-3.0-or-later. The guest `sha256sum` provider and
license remain image/SBOM-derived rather than assumed.
`deploy-target` is a development file-transfer mechanism, not a package
manager, production updater, release artifact, or attestation.

SLIRP exposes only the dynamically selected loopback forwarding recorded by
locked `runqemu`. The direct and devtool transports force the same loopback
host and disable user SSH configuration, identity agents/files, proxies,
forwarding, and local commands; the evidence deliberately omits the ephemeral
port. The workflow accepts no network destination and must never be repurposed
for a physical target without a new manifest contract, threat review, and
approval.
The active build tree is owned by the invoking account; the controller does
not claim protection from a hostile same-UID process racing its local files.

## Qualification status

Repository-local controller, cleanup, and schema tests are implementation
evidence only. The earlier uncommitted candidate passed all 283 repository
tests in native Linux with no skips. Clean local baseline `733169d` then passed
286 Windows-visible tests with 32 expected native-Linux skips before delegated
architecture, quality, and security review. The focused review correction is
now committed locally after passing 314 Windows-visible tests with 34 expected
native-Linux skips and closes all four auto-configuration paths through a dedicated
configuration root, build-root `BBPATH` authority, explicit Linux selection,
complete process-group reaping, deferred cancellation and restorative cleanup,
devtool-configuration and project-layer override, effective
`SRC_URI`, and built/deployed artifact binding findings. Earlier architecture,
quality, DevOps, security, licensing, documentation, and independent-diff
reviews approved the pre-qualification snapshot. Final delegated re-review
remains pending after the real-loop corrections; the corrected native-Linux
unit suite most recently passed all 314 tests with no skips.
The hash-locked manylinux schema oracle and clean-revision Yocto metadata,
build, direct-eSDK, image, SPDX, runtime, and hosted gates remain open. Neither
unit result is qualified SDK, deployment, image, SPDX, or runtime evidence.
A009 remains In Progress until one clean adequately sized Linux revision
completes both lab loops, historical runtime and SPDX requalification, hosted
gates, and public pull-request review.
No standalone SDK, release, tag,
physical-hardware result, signing claim, or attestation follows from this
interface.
