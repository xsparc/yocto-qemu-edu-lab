<!-- SPDX-License-Identifier: MIT -->

# Architecture

## Current end-to-end path

```text
qemu-edu-x86-64.conf
    |
    |-- reuses qemux86-64 compiler settings and kernel BSP metadata
    |-- appends: -device edu
    |-- requires package: qemu-edu-driver
    |-- requires reviewed qemu-system-native 10.2.0
    v
qemu-system-native append -> upstream EDU DMA bounds backport
    v
runqemu -> qemu-system-x86_64 -> virtual PCI bus -> EDU device (1234:11e8)
                                                    |
                                                    | PCI enumeration
                                                    v
Linux PCI core -> qemu_edu.ko -> probe()
                                  |
                                  |-- maps BAR0 (MMIO)
                                  |-- allocates one managed MSI/INTx vector
                                  |-- allocates one managed 4 KiB coherent buffer
                                  |-- creates sysfs attributes
                                  v
/sys/bus/pci/drivers/qemu_edu/<PCI-address>/
                                  |
                                  v
qemu-edu-test
```

The independent ARM64 path reuses the same source lock and wrappers but keeps
its hardware contract separate:

```text
qemu-edu-platform-arm64.conf
    |
    |-- derives from qemuarm64 / QEMU virt
    |-- appends: -device qemu-edu-platform
    |-- consumes the shared project-machine native-QEMU patch set
    v
qemu-system-aarch64 -> dynamic platform bus -> generated qemu,edu-platform FDT
                                                       |
                                                       v
Linux OF/platform core -> qemu_edu_platform.ko -> managed MMIO + level IRQ
                                                       |
                                                       v
/sys/bus/platform/devices/<generated-name>/ -> qemu-edu-platform-test
```

## What each boundary teaches

1. **Machine configuration** describes the target and makes QEMU instantiate the
   virtual hardware.
2. **The recipe** cross-compiles and packages the external kernel module.
3. **PCI enumeration** discovers the device without a Device Tree node.
4. **The ID table** connects PCI ID `1234:11e8` to this driver.
5. **probe()** obtains resources and makes the device usable.
6. **MMIO** accesses the device's register file through BAR0.
7. **Interrupt handling** acknowledges the device and wakes a waiting operation.
8. **sysfs** provides a deliberately small user-space control surface.
9. **Coherent DMA** demonstrates a 28-bit mask, fixed device-buffer addressing,
   two transfer directions, completion, verification, and quiescence.
10. **The image recipe** chooses diagnostic tools, independently of hardware support.

## Current constraints

- The layer declares compatibility only with Yocto 6.0 (`wrynose`).
- `config/sources.lock.json` pins BitBake, OE-Core, and meta-yocto at Yocto
  6.0.2. The source helper verifies tag identity, branch ancestry, origins, and
  clean detached checkouts.
- The lock guarantees metadata source identity, not recipe-download
  availability, authenticated upstream origin, bit-for-bit output, or runtime
  behavior.
- M2 added a native OEQA/testimage suite and a closed version-1 result schema;
  M3 retained its validator while adding version 2 for interrupt-mode evidence;
  M4 retains both while adding version 3 for bounded DMA evidence.
  A full build/runtime pass remains an evidence claim only after it executes on
  an adequate Linux host; the manual guest script remains the teaching path.
- The driver defaults to automatic MSI-preferred allocation, exposes strict MSI
  and explicit INTx policies for comparison, and implements only a length-only
  1..4096 coherent DMA round trip. It does not expose DMA addresses, arbitrary
  device offsets, streaming mappings, scatter-gather, or queues.
- The host emulator is a build input as well as a teaching tool. Both machines
  require `qemu-system-native` 10.2.0. Its exact append applies the same reviewed
  upstream EDU bounds backport and project-local platform-device patch to both
  project machines, and nothing to unrelated machines. Keeping a machine-invariant
  input set across the two labs preserves shared native-task signatures; boot
  arguments still select only the device each lab teaches. The append is kept
  separate from target and user-mode QEMU recipes because only the system-mode
  native binary crosses the `runqemu` boundary. A shared profile-aware preflight
  pins the complete integration and its profile-relevant post-patch source,
  populates `qemu-helper-native`'s consumer sysroot, and requires the matching
  x86-64 or AArch64 executable before either manual or OEQA boot; host-`PATH`
  fallback is outside the project boundary.
- The PCI sysfs surface is guest-interface contract version 3. The independent
  ARM64 platform sysfs surface begins at version 1. Both remain pre-1.0 and may
  evolve only with an explicit project-version and compatibility decision.
- The repository has no physical-hardware target and must not imply QEMU
  validates electrical or silicon behavior.
- Public CI has fast and Linux metadata lanes. A full image/runtime lane is not
  yet available on an adequately sized protected runner.

## Target architecture

The project grows as independent layers around a deterministic lab core:

```text
versioned source/build declaration
                |
                v
Yocto layer -> image + kernel module + test payload
                |
                v
QEMU target -> observable device/driver behavior
                |
                v
runtime tests -> versioned evidence document
                |
       +--------+---------+
       |                  |
       v                  v
human learning       CI / optional tool adapter
```

### Boundary 1: source and build declaration

External repositories and revisions must be explicit and lockable. The build
declaration owns source identity, layer order, machine, image, and configuration
fragments; caches remain replaceable performance aids, not source of truth.
The current source-lock version 1 and lab-manifest version 3 declarations are
project-owned and intentionally map to kas and upstream `bitbake-setup`
concepts if the source graph later justifies a migration.

Recipe-local backports are also explicit inputs. A version-specific append,
upstream commit identity, patch digest, effective `SRC_URI`, patched-source
guards, and compilation result are verified independently of the Git source
lock. A future QEMU version update must prove that the fix is present before
removing the append.

### Boundary 2: lab modules

Each lab is a coherent machine/device/driver/test combination. The x86-64 PCI
lab remains usable when later labs add Device Tree or another architecture.
Shared helpers must not erase the distinctions the project is teaching.

The approved M5 composition uses a closed lab index and digest-bound manifests.
Each manifest owns its build directory, machine, driver, image, emulator
preflight, runtime suite, and evidence profile. `pci-x86-64` remains the no-argument
default and retains `build/`; `platform-arm64` uses a separate build directory.
The source lock continues to identify external repositories independently of a
lab's build composition.

The ARM64 lab derives from OE-Core `qemuarm64` and QEMU `virt`. A project-local
`qemu-edu-platform` SysBus model is placed on `virt`'s dynamic platform bus, and
the reviewed QEMU patch adds its explicit generated-FDT binding. Linux discovers
the resulting `qemu,edu-platform` node as a platform device with one MMIO
resource and one level interrupt. It is an independent device contract, not an
adaptation of the PCI EDU ABI, and it has no DMA surface.

### Boundary 3: guest interface

Driver interfaces are small and documented. Existing sysfs files remain the
human learning surface. Automated tests may wrap them, but must not make prose
formatting the only machine contract. If structured guest output is added, it
must carry an explicit schema version.

### Boundary 4: evidence

Build metadata, test results, supported versions, and skipped checks are emitted
as evidence. Evidence records the source revision, machine, image, test suite,
result, and environment needed to interpret it. It never upgrades “unknown” to
“pass.”

Runtime evidence versions 1, 2, and 3 are lossy, allowlisted projections of native
OEQA JSON. Version 1 remains immutable for the M2 INTx baseline. Version 2 adds
conservative, case-bound claims for MSI, explicit INTx, automatic fallback,
strict-MSI failure, and cleanup recovery. Version 3 preserves those claims and
adds case-bound facts for the length-only interface, both DMA directions,
boundary and negative input, exact completion status, missing-completion
timeout recovery, and teardown/rebind. All versions record exact required case
statuses, durations, source-lock identity, project revision/dirty state, and the
native task exit. Raw logs and arbitrary upstream fields remain diagnostic
inputs rather than public schema fields.

The ARM64 lab emits a different closed evidence kind at version 1. It binds the
source lock, lab index, selected manifest, native OEQA input, exact nine-case
platform suite, Device Tree contract, bounded scratch behavior, interrupt
acknowledgement, and lifecycle restoration. It neither extends nor translates
PCI evidence versions 1 through 3.

### Boundary 5: integrations

CI, dashboards, and optional MCP or other automation tools consume the same
read-only evidence and invoke the same bounded commands as a person. Provider,
transport, credentials, and hosted storage remain outside the core lab.

### Boundary 6: diagnostics core

`qemu-edu-lab` projects source-lock, selected-lab, maintenance, repository, and
runtime-evidence state through four deterministic reads. Repository files enter
through bounded single-read adapters and existing semantic validators; fixed
Git queries enter through the only subprocess adapter. Rendering consumes the
same typed document for text and JSON. The dependency direction is therefore:

```text
CLI rendering -> diagnostics orchestration -> bounded inputs / fixed Git
                                      -> existing project validators
```

The core has no network or mutation capability and accepts no arbitrary path.
Its Draft 2020-12 schema oracle is a test-only CI consumer, not a runtime
dependency. MCP, A2A, and provider SDKs remain outside this boundary.

### Boundary 7: image-composition evidence

Lab manifest schema 2 introduced a closed `supply_chain` contract beside build,
runtime, and emulator selection. Schema 3 retains that object unchanged while
adding the separate development profile described below. Supply-chain fields
name the evidence profile and filename, required project package/license pairs,
and forbidden packages. The catalog and manifest digests remain the authority
used by every wrapper.

`sbom-evidence.sh` is the only build-facing adapter. It verifies exact BitBake
SPDX settings, removes stale evidence, invokes the selected image's
`create_image_sbom_spdx` task, and gives the resulting deployment identity to
the collector. The collector imports `oe.spdx30` only from the exact locked
OE-Core checkout, validates the SHACL object graph, and projects an allowlisted
standard-library JSON contract:

```text
lab manifest v2 + source lock + effective SPDX settings
                              -> locked create-spdx task
                              -> bounded raw SPDX graph + image files
                              -> semantic collector
                              -> closed evidence schema v1
```

The raw graph is not the project API. It can be large and can evolve with the
locked Yocto input. The evidence document records only source identity,
selected-lab identity, generator settings, graph counts, required project
packages/licenses, and independently recomputed image artifact hashes. Raw
SBOMs, image files, package lists outside the project allowlist, host paths,
timestamps, build variables, logs, and arbitrary SPDX fields are not copied
into the projection.

### Boundary 8: isolated direct-eSDK application iteration

Lab manifest schema 3 adds one closed `development` profile beside build,
emulator, runtime, and supply-chain selection. It names a disposable
`build-sdk-<lab>` root, the fixed `qemu-edu-sdk-sample` recipe and source
directory, IDE-neutral SDK mode, one `/usr/bin` guest binary, and a versioned
local evidence filename. The sample is deliberately forbidden from both base
images, so deployment cannot be confused with image composition.

The direct eSDK uses the exact locked OE-Core build environment rather than a
standalone installer. The standard-library controller owns the only
state-changing path:

```text
lab manifest v3 + exact source/tool/composition preflight
                  -> closed generated workspace + separate learner source
                  -> devtool modify/build + IDE-neutral sysroot
                  -> locked runqemu snapshot/slirp + loopback SSH
                  -> absent -> deploy -> execute -> undeploy -> absent
                  -> devtool reset + inert workspace + retained learner source
                  -> second cold-absence boot + closed pass evidence schema v1
```

Normal build directories remain authoritative and are never reused as the
development workspace. The controller atomically removes stale evidence before
mutation. The tooling preflight parses the fixed command/option literals from
the exact locked OE-Core sources and requires all build-facing executables to
resolve to their locked BitBake or OE-Core files; host Bash and OpenSSH remain
explicit host prerequisites. The fixed `/bin/bash -p` A009 wrapper ignores
pre-start `BASH_ENV` and imported shell functions, then clears ambient OE build-root,
source-root, template, BitBake-passthrough, Python, and Git object/config
overrides before sourcing the locked environment. A repository/source/evidence
preflight runs before setup. After setup, the controller atomically owns the
complete SDK `local.conf` and `bblayers.conf` and refuses `site.conf` and
`auto.conf`, plus BitBake's `toolcfg.conf` and `bblock.conf`, before any
BitBake parse. The SDK configuration seeds `BBPATH` with a structurally closed,
controller-owned root containing only the exact `conf/local.conf`. Effective
`BBPATH` must contain that root exactly once and otherwise contain only declared
locked layer roots, never the disposable build root or an empty component. The
locked metadata lane parses both SDK profiles and verifies their effective
DISTRO, MACHINE, BBLAYERS, and BBPATH. The entrypoint resolves host Git before
OE setup and keeps that directory ahead of OE-Core's `scripts/git` helper; the
hardened repository adapter then revalidates the selected executable. Child processes receive only
the verified locked BitBake library on `PYTHONPATH`, cannot import user-site
modules or write bytecode into source checkouts, and do not inherit Python or
shell startup injection variables. The controller accepts only locked runqemu's
bounded loopback SSH forward. Direct guest checks use a resolved native SSH
executable with user configuration, identities, proxies, forwarding, and local
commands disabled. A closed generated `devtool.conf` owns the workspace and is
reauthenticated before cleanup may invoke devtool.
Before the layer joins `BBPATH`, the controller pins the exact executable
statements in the generated Wrynose `layer.conf` and rejects retained plugin code, recipes, appends,
symbolic links, and unknown entries. The project layer is also forbidden from
providing a devtool plugin or sample append. The learner-owned source is stored beside,
not inside, that executable layer so locked `devtool reset` cannot move it into
a timestamped workspace attic. Recovery validates the exact locked-source form
of the one generated append and its recipe-relative checksum record before any
devtool subcommand when the recipe is already known to be modified. A recipe
rediscovered through the closed inert workspace is reauthenticated before
reset. Recovery uses `reset --no-clean` and restores the authoritative manifest
composition without loading an unsafe workspace. The controller hashes the
bounded regular installed file under the effective recipe `D` root and requires
the deployed guest path to have the same SHA-256 before execution.
Devtool deployment uses resolved native `ssh` and `scp` programs through
temporary wrappers, a shell-safe temporary root, explicit no-strip behavior,
and the locked `--ssh-exec` option. The controller restores
recipe/layer/QEMU state on every exit path. Cleanup authenticates bounded raw
configuration before BitBake or devtool, directly restores the exact base
composition when layer removal fails, and reaps active children on controlled
signals. Restorative cleanup completes before pass evidence is published. The
retained learner source and IDE-neutral output are caller-owned and must be
moved or archived outside `build-sdk-<lab>` before another run; the controller
refuses any pre-existing retained source directory or IDE destination and
does not recursively delete either. The
validated atomic evidence replacement is the completion boundary; signals
deferred inside that final transaction are treated as post-completion once the
document is written and revalidated. It accepts no arbitrary recipe,
target, path, QEMU argument, SSH host, port, key, or guest command. Deployment
is a development-only file transfer, not a package-manager transaction or an
image update. Standalone SDK installers, raw logs, build trees, binaries,
images, provider adapters, and remote services stay outside the milestone.

### Boundary 9: public-repository trust evidence

Server-side repository settings are an external security input rather than a
property Git history can prove. M9 keeps the desired state in one closed policy
and evaluates one fixed ignored sanitized observation:

```text
tracked policy + local workflow/security contract
                  -> separately authorized settings observation
                  -> bounded normalized facts
                  -> ordered pass/fail/unavailable checks
                  -> closed evidence schema v1
```

The standard-library evaluator performs no network, credential, subprocess, or
mutation operation and accepts no arbitrary path. It rejects symbolic links,
junctions and other reparse points anywhere in the input path, oversize input,
duplicate or unknown keys, non-printable or non-ASCII strings, and open arrays.
The projection binds exact policy bytes but omits raw API responses, numeric
IDs, actors, URLs, tokens, and local paths. A missing observation or fact is
`unavailable`; an observed conflict is `fail`. The fixed Fast job IDs and
GitHub-owned action namespace are also enforced locally so the desired status
checks cannot drift independently from the workflow files.

Live setting changes remain a separate administrative transaction with a
pre-change recovery record, re-read after each stage, reverse-order rollback,
and the active default-branch ruleset updated last. The result is historical
configuration evidence, not a trusted timestamp, attestation, continuous
monitor, release-provenance claim, or OpenSSF certification.

## Scalability and interoperability rules

- Scale through lab manifests and reusable tests, not conditional logic spread
  through shell scripts.
- Version contracts at repository boundaries: source locks, lab definitions,
  guest interfaces, runtime evidence, diagnostics, supply-chain evidence, and
  development-loop evidence schemas.
- Keep machine-specific metadata in machine or BSP layers and image policy in
  image recipes.
- Add architectures only with a documented learning objective, maintenance
  owner, and build/runtime gate.
- Keep source identity separate from lab composition. Lab manifests are closed,
  digest-bound inputs; wrappers select one manifest and fail closed on unknown
  fields, paths, profiles, or effective BitBake values.
- Prefer Yocto-native validation (`yocto-check-layer`, BitBake parse, OEQA
  runtime tests, SPDX output) before inventing parallel tooling.
- Preserve command-line and JSON/TOML interfaces so alternative CI systems and
  automation frameworks can integrate without repository-specific screen
  scraping.

## Security and trust boundaries

- Setup may fetch only declared public HTTPS Git sources; validation reports
  exact resolved revisions. No credentials belong in project configuration.
- Existing source trees are never reset, cleaned, or silently replaced. Dirty,
  wrong-origin, attached, or unexpected checkouts fail closed.
- QEMU runs unprivileged with SLIRP and snapshot mode by default.
- QEMU is still a host process parsing untrusted guest-controlled device input.
  The EDU DMA range check must abort both copies when the internal buffer range
  is invalid. Source inspection and safe regression tests prove that invariant;
  an out-of-bounds exploit is not a supported test technique.
- Guest input is untrusted at kernel boundaries. Range, timeout, teardown, and
  concurrent removal behavior require tests as features expand.
- DMA input is deliberately length-only. The driver owns the coherent address,
  validates the complete allocation under the 28-bit mask, uses only the fixed
  EDU buffer, serializes the round trip, and clears bus mastering before managed
  memory release.
- Optional automation tools start read-only. Any state-changing capability must
  be separately named, approval-gated, and safe against path or argument
  injection.
- Repository-trust evaluation consumes only the fixed ignored sanitized
  observation. It cannot read hosting credentials or mutate settings. A later
  transport adapter must preserve that boundary and remain optional.
- Direct-eSDK mutation is confined to a catalog-selected disposable build root,
  closed generated workspace layer, separate retained learner source, loopback
  QEMU target, and fixed sample. Cleanup must undeploy, stop QEMU, reset and
  revalidate inert workspace metadata, preserve learner source, and remove
  unqualified evidence on every failure path.
- Release artifacts should eventually carry SBOM and provenance evidence, but
  the project will not claim a SLSA level until it meets and verifies that
  level's requirements.
- SPDX image evidence reads only exact catalog-selected paths, bounds its raw
  and projected inputs, rejects duplicate JSON keys and unsafe strings, refuses
  symlink or deploy-directory escapes, and never uploads raw build output.

## Replaceability

Source orchestration, CI vendor, evidence storage, and AI provider are
replaceable. The enduring project assets are the Yocto metadata, lab contracts,
tests, schemas, research trail, and learning explanations.
