<!-- SPDX-License-Identifier: MIT -->

# Architecture

## Current end-to-end path

```text
qemu-edu-x86-64.conf
    |
    |-- reuses qemux86-64 compiler settings and kernel BSP metadata
    |-- appends: -device edu
    |-- requires package: qemu-edu-driver
    v
runqemu -> qemu-system-x86_64 -> virtual PCI bus -> EDU device (1234:11e8)
                                                    |
                                                    | PCI enumeration
                                                    v
Linux PCI core -> qemu_edu.ko -> probe()
                                  |
                                  |-- maps BAR0 (MMIO)
                                  |-- requests shared INTx IRQ
                                  |-- creates sysfs attributes
                                  v
/sys/bus/pci/drivers/qemu_edu/<PCI-address>/
                                  |
                                  v
qemu-edu-test
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
9. **The image recipe** chooses diagnostic tools, independently of hardware support.

## Current constraints

- The layer declares compatibility only with Yocto 6.0 (`wrynose`).
- `config/sources.lock.json` pins BitBake, OE-Core, and meta-yocto at Yocto
  6.0.2. The source helper verifies tag identity, branch ancestry, origins, and
  clean detached checkouts.
- The lock guarantees metadata source identity, not recipe-download
  availability, authenticated upstream origin, bit-for-bit output, or runtime
  behavior.
- M2 adds a native OEQA/testimage suite and a closed version-1 result schema.
  A full build/runtime pass remains an evidence claim only after it executes on
  an adequate Linux host; the manual guest script remains the teaching path.
- The driver deliberately starts with legacy INTx and has not implemented the
  EDU DMA engine.
- The user-facing sysfs control surface is documented as guest-interface
  contract version 1. It remains pre-1.0 and may evolve only with an explicit
  project-version and compatibility decision.
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
The current version-1 declaration is project-owned and intentionally maps to
kas and upstream `bitbake-setup` concepts if the source graph later justifies a
migration.

### Boundary 2: lab modules

Each lab is a coherent machine/device/driver/test combination. The x86-64 PCI
lab remains usable when later labs add Device Tree or another architecture.
Shared helpers must not erase the distinctions the project is teaching.

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

Runtime evidence version 1 is a lossy, allowlisted projection of native OEQA
JSON. It records exact required case statuses, durations, source-lock identity,
project revision/dirty state, and the native task exit. Raw logs and arbitrary
upstream fields remain diagnostic inputs rather than public schema fields.

### Boundary 5: integrations

CI, dashboards, and optional MCP or other automation tools consume the same
read-only evidence and invoke the same bounded commands as a person. Provider,
transport, credentials, and hosted storage remain outside the core lab.

## Scalability and interoperability rules

- Scale through lab manifests and reusable tests, not conditional logic spread
  through shell scripts.
- Version contracts at repository boundaries: source locks, lab definitions,
  guest interfaces, and evidence schemas.
- Keep machine-specific metadata in machine or BSP layers and image policy in
  image recipes.
- Add architectures only with a documented learning objective, maintenance
  owner, and build/runtime gate.
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
- Guest input is untrusted at kernel boundaries. Range, timeout, teardown, and
  concurrent removal behavior require tests as features expand.
- Optional automation tools start read-only. Any state-changing capability must
  be separately named, approval-gated, and safe against path or argument
  injection.
- Release artifacts should eventually carry SBOM and provenance evidence, but
  the project will not claim a SLSA level until it meets and verifies that
  level's requirements.

## Replaceability

Source orchestration, CI vendor, evidence storage, and AI provider are
replaceable. The enduring project assets are the Yocto metadata, lab contracts,
tests, schemas, research trail, and learning explanations.
