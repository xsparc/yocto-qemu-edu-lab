<!--
SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
SPDX-License-Identifier: MIT
-->

# Development roadmap

The roadmap describes outcomes and gates. `docs/maintainers/tasks.toml` owns
executable task state. Every milestone uses one focused pull request; a
dependency is not approval to begin the next milestone.

## M0 — Project foundation and trustworthy execution

Outcome: maintainers and automation share one vision, architecture, license
boundary, task state, research trail, and public change process.

Acceptance gate:

- vision, architecture, milestones, contribution, security, and licensing
  policies agree with the repository;
- machine-readable tasks validate with at most one active slice;
- checksum and workflow checks pass;
- independent review findings are resolved or recorded;
- one M0 pull request is opened without merging or releasing automatically.

Rollback: revert the M0 PR; it does not change guest runtime behavior.

## M1 — Reproducible setup and fast validation

Outcome: a pull request can prove source identity and catch inexpensive failures
before a full Yocto build.

Delivered scope:

- lock the official split BitBake, OE-Core, and meta-yocto repositories after
  comparing a project format, kas, and upstream `bitbake-setup`;
- make setup idempotent, fail closed on local drift, and report resolved
  revisions in human and JSON forms;
- add shell, SPDX/REUSE, checksum, workflow, BitBake syntax/parse, and
  `yocto-check-layer` gates where practical;
- add immutable, secret-free fast PR checks and a distinct Linux metadata lane;
- document why a full build/runtime lane needs a larger protected runner;
- define project SemVer and Yocto-series compatibility policy.

Acceptance evidence: pull request #2 resolves the declared inputs on a clean
Linux runner, passes documented fast checks and native metadata/layer checks,
and reports unavailable full-build/runtime evidence honestly. Merge and release
remain separate maintainer decisions.

Rollback: revert M1 scripts and workflows without deleting `layers/`, `poky/`,
downloads, shared state, or build output. The former Poky combo path is not kept
as a Wrynose fallback because upstream no longer updates it for new series.

## M2 — Automated baseline runtime evidence

Outcome: the existing PCI/MMIO/INTx lab is verified without an interactive
guest login.

Delivered scope:

- document the current sysfs contract and failure semantics;
- integrate OEQA/testimage coverage for PCI discovery, identification,
  liveness, factorial, interrupt count, invalid range, timeout, and absent
  device behavior;
- emit a versioned result document for CI and local diagnosis.

Acceptance evidence: clean commit `6479681` passed locked build-composition
verification, the complete image build, software-QEMU boot, SSH, and all 11
project runtime cases. The closed version-1 result records exact revision,
dirty state, native input digest, task exit, and positive and negative outcomes.
It remains an unsigned local report, not hosted provenance or physical-hardware
evidence.

Rollback: retain `qemu-edu-test` as a manual teaching tool even after OEQA owns
the automated gate.

## M3 — MSI learning stage

Outcome: the lab teaches modern PCI vector allocation and compares it with INTx.

Delivered scope:

- select `auto`, required MSI, or explicit INTx at module load and report the
  resolved per-device mode;
- allocate one managed PCI vector without double-freeing the locked Linux 6.18
  managed lifecycle;
- prove default and strict MSI, explicit INTx, actual PCI-core fallback,
  strict-MSI failure, acknowledgement, cleanup, and default recovery;
- emit evidence schema 2 while preserving version-1 validation.

Acceptance evidence: clean commit `3ea0204` passed the exact locked image path,
software-QEMU boot, SSH, and all 14 project cases without skips or failures.
The closed version-2 evidence records the exact revision, clean tree, native
result digest, and conservative completion claims for every interrupt and
negative path. Independent review found no remaining P0-P2 issue. QEMU evidence
remains distinct from physical-hardware qualification.

Rollback: load `interrupt_mode=intx`, or revert the focused M3 change. Retain
the immutable version-1 schema and validator path for historical M2 evidence.

## M3.1 — Host EDU DMA bounds hardening

Outcome: the QEMU process used by the lab rejects guest-controlled EDU DMA
ranges outside the device's internal buffer before the curriculum exposes DMA.

Approved scope:

- backport exact upstream commit
  `42f599172ae023924f288e20af0ceed681674747` to
  `qemu-system-native_10.2.0`;
- fail closed if another host-emulator recipe version is selected;
- verify append selection, exact patch and patched-source digests, guarded copy
  placement, compilation, fail-closed native-sysroot consumption in both public
  boot paths, and the existing 14-case runtime suite;
- preserve upstream authorship and the MIT license of `hw/misc/edu.c`.

Acceptance gate: A007 records a clean patched-emulator build and version-2
runtime pass, exact upstream and patch identities, repository and metadata
checks, REUSE compliance, and independent security review. Invalid DMA ranges
are verified by source inspection, never by running an exploit against an
unpatched QEMU process.

Qualification status: clean commit `46e2280` satisfies the local build,
consumer, runtime, licensing, and independent-review gates. Pull request #5
passed hosted fast and native metadata/layer gates and squash-merged as
`083ddf5e1207dac34bdaf12e04a41f1f1faa8d7f`; no tag or release was published.

Rollback: do not restore the vulnerable emulator. If the backport cannot be
maintained, remove `-device edu` and suspend the runtime lab until a supported
QEMU input containing the fix is qualified.

## M4 — Bounded DMA learning stage

Outcome: the driver safely demonstrates both EDU DMA directions, coherent
memory, the default 28-bit mask, transfer bounds, completion, and cleanup.

Dependency: M3 and M3.1 are Done. A004 received separate implementation
approval on 2026-08-09 and is Done.

Approved boundary: one managed 4,096-byte coherent buffer under the EDU 28-bit
mask; a length-only 1..4096 sysfs request; fixed device-buffer addressing; a
verified RAM-to-EDU-to-RAM transfer; DMA-interrupt completion and exact
acknowledgement; bounded timeout; and bus-master quiescence before managed
memory release. The guest never provides or receives a DMA address.

Acceptance gate: lengths 1, an odd value, and 4096 pass both directions with
two exact DMA completion interrupts; 0, 4097, negative, and malformed inputs
fail without corrupting state; the missing-completion seam times out and a
default reload recovers; unload/rebind restores the default MSI and DMA paths;
all prior cases remain green; closed version-3 evidence is clean and complete;
and repository, metadata, licensing, build, runtime, and review gates pass.

Qualification status: clean implementation commit `8574eaf` passed the full
94-test Linux repository suite, all 4,738 exact Yocto 6.0.2 image tasks, and a
software-QEMU run containing ping, SSH, and all 19 project cases. All 21 tests
passed without skips, failures, or errors. The isolated exact-lock
`yocto-check-layer` run completed 13 BSP/common checks: 12 passed, with
only the expected distro-class skip for a BSP layer. Closed version-3 evidence
records a clean tree and successful testimage exit; its SHA-256 is
`f97b24335cd9579eaf825cf1c06e54ae1742f069f1afa2a4c8e6fa2f162856c2`, and
the bound native OEQA SHA-256 is
`1f8b1756faf079a0996070846f4e4aee5535e71d205f5e232c9cbeff395e07c5`.
Pull request #6 passed hosted Fast checks run `31312516815` and Yocto metadata
run `31312516778` at `fbb2cab55ea6fc6a9000a1e172d71ef82a892a4b`, then
squash-merged as `918efaa392486af73f03ac9d1e216c2a2ed421da`. The
correction strengthens the address-free oracle with an exact source allowlist
and a bound-versus-unbound sysfs comparison. Clean correction commit `fe08e73`
passed the complete 94-test
Linux suite, locked setup and QEMU-consumer preflight, all 4,738 cached image
tasks, and a fresh software-QEMU run containing ping, SSH, and all 19 project
cases. All 21 tests passed in 172.305 seconds with no skips, failures, or errors.
The corrected evidence SHA-256 is `c51de37dc60c69e5f697fb0ae8ab74fbc1c0520724554b73904783533ca2b4ea`, and
the bound native OEQA SHA-256 is `918a7ade794afbc958c428eff358e2f5740e6e89bb63f8bb90d063b014a419a9`.
Quality, architecture, security, and independent frozen-diff reviews approved
the correction with no P0-P2 findings. Review-record commit `a3a42b6` passed
hosted Fast checks run `31397396385` and Yocto metadata run `31397396470`.
Final pull-request head `89a4be3` passed Fast checks run `31404164447` and Yocto
metadata run `31404164649`, then pull request #7 squash-merged as
`ebbf1db0a5f8f2b30d7580a2435f67e9db5cc940`. Documentation closeout pull request
#8 passed hosted Fast checks and squash-merged as `01ff717` without changing the
qualified implementation. A004 is Done. The local runtime result is not a
hosted attestation, physical-hardware result, tag, or release.

Rollback: keep DMA opt-in and preserve the M3 image as a known-good stage.

## M5 — Portable platform-driver lab

Outcome: one non-PCI lab teaches Device Tree discovery and a platform driver
without weakening the original PCI lesson.

Approved on 2026-08-11: use ARM64 `virt`, one project-local
`qemu-edu-platform` SysBus device, and a generated `qemu,edu-platform` node.
ARM64 reuses OE-Core's direct `qemuarm64` path and keeps the new lesson focused
on Device Tree, MMIO, interrupts, and platform-driver lifecycle. RISC-V remains
deferred because its additional OpenSBI/U-Boot boot chain does not improve this
stage's learning objective.

Approved composition: closed lab manifests select an independent build
directory, machine, driver, image, preflight, runtime suite, and evidence profile. The
existing PCI lab remains the default for every no-argument command. The ARM64
lab adds no DMA and does not modify PCI guest or evidence contracts.

Acceptance gate: both labs parse, build, and boot independently from the exact
Yocto 6.0.2/QEMU 10.2.0 inputs; the ARM64 lab verifies the generated FDT node,
platform-device binding, identification, bounded scratch MMIO, two exact
interrupt acknowledgement cycles, unload cleanup, and rebind recovery; PCI
evidence versions 1 through 3 remain valid; closed platform evidence version 1
is clean and complete; licensing and all required reviews pass; shared and
architecture-specific concepts are explicit.

Qualification status: clean exact revision `3244a0c` passed all 141 Linux tests
without skips, pinned static and licensing checks, both metadata profiles, and
the fresh dual-machine layer audit. The previously failing machine-signature
check now passes because both project machines select the same reviewed native
QEMU patch set. After clean project driver/image invalidation, the PCI graph
completed all 4,738 tasks and the ARM64 graph completed all 4,702 tasks. The
software-QEMU results passed 21/21 PCI tests and 11/11 ARM64 tests with zero
skips, failures, or errors. Platform-v1 evidence SHA-256 is
`432e391555346582f7ccd2a8572fadd3f9c8200058d9a180f17a10fe46928824`; PCI-v3
evidence SHA-256 is
`823bffd64153516c928b108ce23a695e9d50d34bcc6754578edf3519cbb1d79e`.
Following review corrections, clean revision `340621a` passed all 144 Linux
tests without skips and REUSE 95/95. The affected ARM64 tool and driver were
rebuilt from cleansstate, the image completed 4,702 tasks, and software QEMU
passed 11/11 tests. The no-argument wrapper selected the default PCI lab and
passed 21/21 tests. Fresh platform-v1 evidence SHA-256 is
`40550c299ec26e216c62ef5489774b53dc37c74658fab14d79588946fc311a9e`;
fresh PCI-v3 evidence SHA-256 is
`1a443dd4183eb843511e97f7751e72aa4e57b249dca545bc0c2dbba6e640a94d`.
All six required reviews approved with no remaining P0-P2 findings. Published
pull-request head `205384a62ca2a6f0738492aeedfddf850bc8529f` passed Fast
checks run `31788645763` and Yocto metadata run `31788645797`. Pull request #9
then squash-merged as `e2d703ecd017c6c8a2d94a23280bdb9d9da5f361`. A005 is
Done; the local runtime reports remain unsigned evidence rather than hosted
attestations, and no tag or release was published.

Rollback: remove the ARM manifest, machine, patch, driver, test, and evidence
profile. The default PCI manifest and its existing build directory remain the
known-good path. No source-version rollback or evidence translation is needed.

## M6 — Provider-neutral diagnostics and optional tool access

Outcome: `status`, `doctor`, `inspect`, and test evidence are safe and structured enough
for people, CI, and optional assistants.

Approved on 2026-08-14: implement a standard-library-only, read-only
`0.6.0-dev` diagnostics core. Its version-1 schema has exact check order,
deterministic bytes, bounded single-read inputs, fixed Git queries, and honest
current-versus-historical evidence binding.

Scope:

- add the four local commands with deterministic text and closed JSON schema 1;
- preserve pass, warning, fail, and unavailable states with exact exit
  precedence;
- bind evidence only from the selected manifest path and reuse the existing
  source, catalog, workflow, and evidence semantic validators;
- run independent schema conformance through six exact hash-locked test-only
  wheels on Linux CPython 3.12;
- document paths, subprocesses, secrets, untrusted inputs, licensing, rollback,
  and future-adapter approval boundaries.

Non-scope: MCP, A2A, model or provider SDKs, diagnostic networking, mutation,
repair, setup, build, boot, test execution, alternate evidence paths, and input
version updates.

The dated primary-source rationale is recorded in
[`research/2026-08-14-m6-diagnostics.md`](research/2026-08-14-m6-diagnostics.md).

Acceptance gate: the complete lab remains usable without AI; schema and security
tests pass; state-changing tools are absent or separately approved.

Clean implementation revision `25109d4f471492c0f2e101deca4f0a86c61c49a0`
passes 203 Windows tests with 16 expected native-Linux skips and all 203 tests in
a network-disabled, capability-free Linux CPython 3.12 environment with a
read-only repository. The exact six-wheel Draft 2020-12 oracle and pinned REUSE
108/108 gate pass. All seven required reviews approved with no remaining P0-P2
finding. Draft pull request #11 published focused workflow-correction head
`b68033923d6bc42eca06e1538aef0d745c1acd25`, which passed Fast checks run
`32210876009` and Yocto metadata run `32210876013`. Final head
`900c82f3936d9ffdf5a5499391abc368689332f6` passed Fast checks run
`32212167852` and Yocto metadata run `32212167855`; pull request #11 then
squash-merged as `b569199513418fc6fc8a62453dca4751d3cf8969`. No tag or
release was published.

Rollback: revert the complete focused A006 milestone change. A partial
retirement must also revert the project version decision, maintainer
configuration, workflow validator requirements, Makefile targets, CI job,
checksums, tests, and documentation rather than deleting only the CLI and
schema. Existing build wrappers, lab manifests, guest interfaces, and
PCI/platform runtime-evidence formats remain unchanged.

## M7 — SPDX image-composition evidence

Outcome: each supported lab can turn the locked Yocto SPDX 3 image SBOM into a
small, closed evidence document that proves the project packages and generated
image files actually selected for that build.

Approved on 2026-08-19: advance the development identity to `0.7.0-dev`, move
the lab catalog to manifest schema 2, and add one supply-chain profile shared
by both labs. The profile names required project packages and their exact
declared license expressions, forbids packages from the other lab, and fixes
the generated evidence filename. Collection uses the SPDX 3.0.1 SHACL model
from the exact locked OE-Core checkout; validation of the projected result
remains standard-library-only.

The bounded collector must prove:

- exact clean project revision, source lock, OE-Core commit, lab index,
  selected manifest, machine, image, and privacy-oriented generator settings;
- one SPDX document and one build SBOM, no unresolved internal identifiers,
  the exact rootfs build type and build-scoped installed-package inputs;
- required project packages with exact declared licenses, no forbidden
  cross-lab packages, and package purposes consistent with image installation;
- every image artifact basename, bounded size, declared SHA-256, and an
  independently recomputed SHA-256 from a regular file inside the selected
  deployment directory.

The raw SBOM and image files remain ignored build output. The checked-in schema
covers only the bounded project projection; it does not claim full SPDX
specification conformance, CVE freshness, reproducible bytes, a signature,
attestation, SLSA level, release, or physical-hardware result. Public PR CI
runs repository, schema, licensing, and metadata preflight only. Final
acceptance requires clean, adequately sized Linux builds for both lab profiles
and validated evidence bound to that exact revision.

Qualification status: clean revision `8588e29` passed all 228 isolated Linux
tests, the exact external Draft 2020-12 oracle, and REUSE 116/116. After each
image recipe was invalidated through `cleansstate`, the normal PCI graph
completed 4,667 tasks and the normal ARM64 graph completed 4,631 tasks; both
reran rootfs, image, and complete SPDX generation without warnings or failures.
Closed PCI evidence SHA-256
`d4b6f88023a45888b32a875a106d27efca4e720d24313d5395091e81f1f1c05d`
binds raw SPDX SHA-256
`2717b9c20b34bb1511ecfe091690e129003665fd0523fa3bdb69aa1562587b5a`,
55 installed packages, and two image artifacts. Closed ARM64 evidence SHA-256
`02f6fe4d06df2a63780e0a859c51ddbc53dff0721d9c4ad96575c8463742140e`
binds raw SPDX SHA-256
`9ac51c30d5a74b3538afaeea80d63831b9993f153c13e514f04b03005e1dee61`,
49 installed packages, and two image artifacts. The normally rebuilt images
then passed 21/21 PCI and 11/11 ARM64 software-QEMU tests with zero skips,
failures, or errors. Post-qualification hardening through code candidate
`b092b48` passed all 234 isolated Linux tests and retained both qualified graph
results. All seven required review roles approved exact review head `31142b6`
with no remaining P0-P2 finding. Published head `82d9970` passed Fast checks
run `32231165395` and Yocto metadata run `32231165336`; pull request #12
squash-merged as `00ad952`. A008 is Done. No tag or release was published.

The dated source analysis and compatibility boundary are recorded in
[`research/2026-08-19-m7-spdx-image-evidence.md`](research/2026-08-19-m7-spdx-image-evidence.md).

Rollback: revert the complete focused A008 change, including project version,
manifest schema and digests, evidence collector/schema/wrapper, CI preflight,
tests, maintainer configuration, checksums, and documentation. Existing guest
interfaces and historical runtime-evidence schemas remain immutable and need
no translation.

## M8 — Isolated direct-eSDK application iteration

Outcome: each supported lab can use the exact locked Yocto development tools to
modify, cross-build, deploy, execute, undeploy, and reset one small userspace
application without changing the authoritative base image.

Approved on 2026-08-20: advance the development identity to `0.8.0-dev`, move
the lab catalog to manifest schema 3, and add one
`direct-esdk-devtool-v1` profile per lab. Each profile selects a disposable
development build root, fixed MIT/libc-only sample recipe and source path,
IDE-neutral mode, guest binary, and local evidence filename. The sample stays
forbidden from both base images.

The implemented host controller is bounded to this sequence:

- verify exact source locks, selected lab composition, patched QEMU consumer,
  build directory, fixed development profile, and clean repository before OE
  environment setup; then atomically own the complete SDK configuration before
  the first BitBake parse;
- create exactly one closed generated workspace layer in the disposable build
  root, keep the build root and empty components out of `BBPATH`, reject
  retained executable or metadata drift, and authenticate the one generated
  `devtool.conf` before devtool can consume the workspace,
  prepare the declared learner source outside that layer, and use locked
  `devtool modify -n`, `devtool build`, and
  `devtool ide-sdk --mode modified --ide none`;
- start the selected locked `runqemu` path in snapshot/slirp mode and accept
  only its bounded loopback SSH endpoint;
- prove the binary is absent, deploy only the fixed recipe, verify target
  architecture, built/deployed SHA-256 identity, and exact output, undeploy it,
  and prove absence again;
- stop QEMU, authenticate the exact locked-source-derived active append and its
  checksum state, reset the devtool recipe without a metadata clean task,
  revalidate inert workspace metadata, retain the separate learner source in
  place, remove unqualified evidence, and prove cold-boot base-image absence.

Non-scope: standalone SDK installers, arbitrary recipes or targets, user QEMU
or SSH arguments, non-loopback targets, package-manager operations, production
updates, raw logs, build trees, images, binaries, public SDK artifacts, MCP,
A2A, provider SDKs, hosted services, releases, signing, attestations, and
physical hardware.

Public pull-request CI remains repository, licensing, and metadata evidence.
The metadata lane verifies the exact locked SDK executable/plugin authority,
forbids project devtool/sample-append overrides, and checks the effective sample
PN/PV/license/machine/source contract for both profiles without
compiling the sample or claiming a direct-eSDK run.
Final acceptance requires an adequately sized isolated Linux worker, exact
clean-revision direct-eSDK loops for both labs, a closed immutable
`qemu-edu-sdk-evidence-v1` document per lab, and proportional requalification
of the base image's SPDX and historical runtime evidence after schema-3 digest
changes. A009 is Done. Repository-local controller and schema checks alone are
not dual-lab SDK, deployment, image, SPDX, or runtime qualification evidence.

Qualification status: clean publication implementation candidate
`86daf481ff69f3e515887997aff519393239e56a` is exactly one A009 commit over
the squash-merged A008 closeout `8f498899cb71615b99ccd210f1eecd95ebfe69a9`,
has tree
`d38260ffab599dd3c575510fa326bfcc93a304bb`, and does not contain the known
non-publishable `733169d` history. That tree is byte-identical to qualified
implementation `03840b93aed2cbddb6301eb82643bae655c81486`. The complete
native-Linux suite passed 320/320 at that qualified revision. After the
history-only re-anchor, the closeout tree passed all 320 Windows-visible tests
with 34 expected POSIX skips, all three exact schema oracles, source, lab,
workflow, CI, QEMU, checksum, whitespace, and digest-pinned REUSE 130/130
gates. Both ordinary metadata profiles and cross-architecture sample builds
remain qualified. The final correction performs a read-only retained-
output preflight that rejects every pre-existing learner source directory or IDE
result before tooling, configuration, QEMU, or image-build mutation.

Both network-disabled direct-eSDK loops passed their full
absent-build-deploy-execute-undeploy-reset-cold-absence sequence. PCI completed
or reused 4,738 image tasks and ARM64 completed or reused 4,702; their closed
SDK evidence SHA-256 values are
`049964cae352006c172b02f2226d8126ff39eb95ed88224de81b702f17e363d1`
and `b960e3af52eb09125d7681b48025ee4594a64be6556b4e3e53907f351515a09d`.
Those revision-bound documents remain attributed to `03840b93`; the re-anchor
does not relabel or regenerate them.
Normal image/SPDX requalification then completed 4,667 PCI tasks and 4,631
ARM64 tasks. The current-input evidence hashes are
`c7c6a0b4efb2646580cacfaa4001721aa53aa924bbdb3f8df80c70f5423d5d58`
and `033760973a635fcc3e21999cc7da72bcb777b51fbe3e39ecabb7e8ddef11ff3c`.
Software QEMU passed all 21 PCI and 11 ARM64 runtime tests with no skips,
failures, or errors; evidence hashes are
`56ddda2d3dfc418eb6dbbfce192c27afcf6661774c4e470614cad22a45149e91`
and `52722c5745a9d56e3c767a3c516657cafc1f854ef503ea2623c0173a77e876c3`.
All seven delegated reviews are complete. Pull request #14 published the
explicit reconstructed clean branch. Initial Fast checks passed all four jobs;
the metadata lane parsed 956 recipes with zero errors, then its sample verifier
failed closed because the OE environment had changed into the build directory
and the workflow omitted the explicit repository root. Corrected code-bearing
head `2dd9cd0` passed all four jobs in Fast checks run `33246698811` and every
step in Yocto metadata run `33246698836`, including both profiles, both closed
SDK configurations, and the layer audit. Final head `5ca21b1` passed Fast
checks run `33247507794` and Yocto metadata run `33247507795`. Pull request
#14 squash-merged as `4dd8c792`; the resulting `main` revision passed Fast
checks run `33253594345` and Yocto metadata run `33253594300`. A009 is Done.
No tag, release, standalone SDK, build artifact, image, SBOM, runtime document,
signing claim, or attestation was published.

The dated primary-source rationale and provider-neutral direction brief are in
[`research/2026-08-20-m8-direct-esdk-devtool.md`](research/2026-08-20-m8-direct-esdk-devtool.md).

Rollback: revert the complete focused A009 change, including project version,
manifest schema/digests, sample recipe, controller, evidence schema, CI/tests,
checksums, and documentation. Remove only generated disposable development
roots and ignored evidence after resolving their absolute paths; do not delete
normal build roots, learner source, or retained IDE output. Move or archive
both `learner-source/qemu-edu-sdk-sample` and `learner-ide-sdk` outside the
selected development root before a later run.
Historical runtime, diagnostics, and SPDX evidence schemas remain immutable.

## M9 — Verifiable public-repository trust

Outcome: maintainers can compare the public repository's server-side security
state with a reviewed desired-state contract and produce a small deterministic
evidence document without giving the project validator network or credential
access.

Approved on 2026-08-30: advance the development identity to `0.9.0-dev` and
add one closed repository-trust policy. It covers public visibility,
squash-only merging, automatic topic-branch deletion, least-privilege Actions,
GitHub-owned immutable actions, the protected default branch, the exact four
stable Fast job contexts, Dependabot alerts and security updates, secret
scanning and push protection, private vulnerability reporting, and a named
security contact. The path-scoped Yocto metadata job remains advisory.

The evaluator is standard-library-only, offline, and read-only. It reads one
fixed ignored observation path, rejects unbounded or structurally open input,
and emits closed schema-1 evidence containing only allowlisted facts, the
policy SHA-256, an observer-supplied timestamp, ordered check results, and an
aggregate `pass`, `fail`, or `unavailable` result. It neither calls GitHub nor
retains raw API responses, actor identities, numeric IDs, URLs, credentials,
or local paths.

Acceptance gate: local policy, semantic, CI, schema, licensing, checksum, and
adversarial tests pass; all required reviews complete; then a separately
authorized staged live-settings transaction is re-read and rolled back on any
failure. A passing sanitized observation and the same four hosted Fast checks
under the strengthened ruleset are required before A010 is Done. The result is
point-in-time configuration evidence, not an attestation, certification,
release, account-security proof, or guarantee of continuing state.

The dated primary-source rationale is recorded in
[`research/2026-08-30-m9-repository-trust.md`](research/2026-08-30-m9-repository-trust.md).

Rollback: revert the focused M9 source change. Any later live setting rollback
must restore the pre-change snapshot in reverse order while preserving the
existing no-bypass default-branch protection. Never weaken the active ruleset
merely to make a pull request mergeable.

## Horizon — Physical target bridge and course ecosystem

Potential work after evidence from M0–M7:

- FPGA or supported development-board mapping with explicit QEMU/physical
  evidence separation;
- instructor exercise packs with expected failure signatures;
- driver-oriented SDK iteration beyond the bounded M8 userspace sample;
- signed or attestable release provenance, only after its own threat model and
  approval boundary;
- community-contributed labs that pass the same compatibility and license gates.

These are horizons, not commitments or approved tasks.
