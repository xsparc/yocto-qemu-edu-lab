<!--
SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
SPDX-License-Identifier: MIT
-->

# Continuous integration and evidence tiers

CI reports the strongest evidence it actually ran. It does not turn skipped,
resource-constrained, or metadata-only checks into build or runtime claims.

| Tier | Trigger and environment | Evidence | Not proved |
|---|---|---|---|
| Fast checks | Every PR, main push, or manual run on `ubuntu-24.04` | Source-lock, lab-manifest, workflow, CI, repository-trust policy, diagnostics, SPDX image-evidence, direct-eSDK evidence, and QEMU security contracts; unit tests; independent Draft 2020-12 validation of the diagnostics, SPDX, SDK, and repository-trust schemas in the external oracle lane; checksums; changed-line whitespace; ShellCheck; actionlint; REUSE | Live repository settings, upstream availability, BitBake parse, image build, guest runtime, generated SBOM content, direct-eSDK execution |
| Yocto metadata | Relevant PR/main changes or manual run on `ubuntu-24.04` | Exact source resolution, cached offline recheck, both manifest compositions, locked SDK executable/plugin authority, exact sample PN/PV/license/machine metadata, `bitbake -p`, expanded image metadata, exact SPDX generator settings, per-machine QEMU append/recipe/dependency isolation, both machine checks through `yocto-check-layer` | Patched source, compiled sample/image/emulator, generated SDK or SPDX graph, QEMU boot, guest behavior, offline recipe fetches, bit-for-bit output |
| Full build/runtime | Local/manual on an adequately sized Linux host; no hosted runner currently configured | A completed lab-specific `runtime-test.sh` run builds, boots, executes its required OEQA cases, and emits PCI version-3 or platform version-1 evidence | Nothing until the command actually completes; one lab's result does not qualify the other and metadata CI is not runtime proof |
| SPDX image evidence | Local/manual on the same adequately sized Linux boundary | `sbom-evidence.sh` completes the selected image's SPDX task and emits schema-1 package/license and artifact-hash evidence | Nothing until the command completes for that lab; it is not runtime, signing, attestation, vulnerability-freshness, reproducibility, release, or physical-hardware proof |
| Direct-eSDK iteration | Local/manual on the same adequately sized native-Linux boundary | `sdk-test.sh` completes one fixed workspace/build/deploy/execute/undeploy/reset/cold-absence loop and emits schema-1 pass evidence | Nothing until the command completes for that lab; repository/schema tests are not SDK, deployment, image, runtime, release, or physical-hardware proof |

The stable fast job IDs are `repository`, `static`, `diagnostics-schema`, and
`licensing`. The metadata
job is path-scoped and initially advisory; path-filtered checks should not be
made universally required because unrelated pull requests may not create them.
For native layer checking, CI creates a separate core-only build directory with
OE-Core's weak `qemux86-64` default. It proves that base composition before
asking `yocto-check-layer` to add the project layer and test both project
machines. The weak default allows the checker to select each machine during
its BSP tests. The native QEMU append is scoped to the exact set of two project
machines. Both receive the same reviewed bounds and platform patch set because
`qemu-system-native` is a shared host-native provider; unrelated machines such
as the `qemux86-64` baseline receive neither patch and remain signature-neutral.
The metadata verifier requires both inputs exactly once for either profile.

## Public-repository trust boundary

- Workflows have read-only `contents` permission and do not use secrets.
- External actions use immutable 40-character commit SHAs. Checkout does not
  persist credentials and fetches history only for patch comparison.
- Static tools are downloaded from their official HTTPS release pages and
  checked against committed SHA-256 values before execution.
- The diagnostics schema job uses CPython 3.12 and downloads only the six exact
  wheels in `config/diagnostics-schema-validator.lock.json`. It verifies wheel,
  embedded-license, identity, and dependency metadata before installing with no
  index, resolver, source distribution, cache, or artifact publication. The
  same isolated Draft 2020-12 oracle validates the diagnostics, SPDX
  image-evidence, direct-eSDK evidence, and repository-trust evidence schemas;
  none gains a runtime dependency.
- REUSE runs from a digest-pinned container with no network, no capabilities,
  a read-only filesystem, and a read-only repository mount.
- Workflows do not use `pull_request_target`, privileged follow-up events,
  caches, artifact uploads, or persistent self-hosted runners.
- `scripts/validate_ci.py` first restricts workflow structure to a canonical
  YAML subset with scoped duplicate-key rejection, then fails closed on
  unpinned actions, write permissions, secrets or credential-bearing GitHub
  context access, non-hosted runners, or jobs without timeouts. It binds the
  complete Fast execution envelope, exact triggers, and reviewed non-skippable
  job command surfaces to the four required contexts. Those context names are
  reserved to the Fast workflow; other workflows cannot reuse their job IDs or
  override job display names.
- `scripts/repository_trust.py validate` enforces the exact desired-state
  policy and named security contact. It does not claim live settings were read.
  The evaluator consumes only the fixed ignored sanitized observation and
  returns `unavailable` when that input or a required fact is absent.

Hosted runner packages and images remain mutable. Metadata results therefore
record the GitHub runner image identity and prove compatibility with that
observed environment, not a hermetic host distribution.

Ubuntu 24.04 restricts unprivileged user namespaces through AppArmor, while
BitBake uses them to isolate tasks. The metadata job disables that one kernel
restriction only inside its disposable GitHub-hosted VM and immediately probes
the required namespace operation. The exception is not applied to persistent
runners, carries no secrets or write token, and does not broaden workflow
permissions.

## Local checks

Run the dependency-free repository suite with Python 3.11 or newer:

```bash
python3 scripts/source_lock.py validate
python3 scripts/lab_config.py validate
python3 scripts/validate_workflow.py
python3 scripts/validate_ci.py
python3 scripts/repository_trust.py validate
python3 scripts/verify_qemu_security.py static
python3 scripts/verify_diagnostics_schema_lock.py
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 scripts/update_checksums.py --check
git diff --check
```

ShellCheck, actionlint, and REUSE run in CI with pinned tool identities. A Linux
maintainer may run equivalent local tools but must record their versions.

## Full-build lane gate

Yocto 6.0 documents a 140 GB free-disk and 32 GB RAM baseline, while a standard
GitHub-hosted runner is smaller. Do not add a nominal full build that is
predictably resource-starved. A future lane needs an ephemeral or protected,
main-only Linux runner with at least 150 GB usable storage, preferably 32 GB
RAM, no exposure to fork code, and bounded download/shared-state retention.
M2 added OEQA/testimage runtime evidence; M3 extends it with MSI/INTx policy and
cleanup coverage while retaining historical version-1 validation.
A007 makes that full runtime command verify the selected host-emulator recipe,
exact normalized patch and patched-source digests, guarded DMA-copy placement,
and the executable in `qemu-helper-native`'s consumer sysroot before boot. The
manual `run.sh` command shares that gate, so neither path can fall back to a
host QEMU. The metadata lane proves only selection and the dependency chain;
it does not claim the patch compiled.

M5 applies the same boundary to both lab profiles. The PCI profile pins the
reviewed `edu.c` source and `qemu-system-x86_64`; the ARM64 profile pins the
complete project-local platform source group, proves that the model exposes no
DMA path, and requires `qemu-system-aarch64` from the exact helper-native
consumer sysroot. A clean ARM64 result does not replace the required PCI
regression, and neither result is a physical-hardware claim.

M7 adds a second full-build consumer without adding a hosted full-build lane.
For each selected lab, `sbom-evidence.sh` fail-closes on the exact source lock,
manifest digest, effective SPDX 3.0.1 settings, locked OE-Core SHACL model,
rootfs package graph, project package/license rules, and recomputed artifact
hashes. The metadata lane proves only that both image recipes parse with the
required settings. Public workflows do not retain raw SBOMs, image files, or
the local projected evidence.

M8 adds a state-changing direct-eSDK consumer without adding a hosted
full-build lane. `sdk-test.sh` uses only the catalog-selected disposable build
root and fixed sample. Its native-Linux preflight removes stale evidence and
requires exact sources plus a clean subject before locked OE setup. The
controller then atomically replaces the complete SDK configuration before any
BitBake parse, seeds `BBPATH` at a closed root containing only its exact
`conf/local.conf` rather than the build directory or an empty component, and rejects all four automatically
included side-configuration files. It parses the required devtool command surface
from the exact clean OE-Core checkout and requires each build-facing command
to resolve to its locked BitBake or OE-Core entry point. Host Git is resolved
before OE setup, kept ahead of OE-Core's `scripts/git` helper, and revalidated
by the hardened repository adapter. Project-layer devtool
plugins and sample appends are forbidden. The metadata lane proves those
identities and the effective sample recipe, including `SRC_URI`, for both
machines without compiling it. It also performs a real locked BitBake parse of
both closed SDK configurations, requires the closed configuration root exactly
once, and rejects any undeclared, empty, or build-root `BBPATH` component. The
full command verifies current
source/composition/QEMU inputs,
accepts only runqemu's loopback guest-SSH mapping, and restores target, QEMU,
recipe, and workspace composition on failure. It also requires the deployed
guest binary SHA-256 to match the locally built installed file. Public CI checks the controller,
cleanup behavior, wrapper, and closed schema but does not execute devtool,
publish an SDK, or retain local evidence.

The project provides the executable runtime path and closed evidence formats, but does
not weaken this capacity gate. The repository currently has no self-hosted or
larger runner. Use `docs/runtime-testing.md` on a suitable local or protected
Linux worker, including an isolated Linux container only when its namespace,
storage, memory, and software-emulation limits are recorded with the result. If
a future CI lane retains evidence, it may publish only the allowlisted JSON
result with a short immutable-artifact retention period and recorded digest;
raw build trees, shared state, downloads, and environment dumps remain
excluded.

M9 records the desired setting state and a staged rollback plan. The local
source change does not alter GitHub. After a draft M9 pull request passes all
four stable Fast jobs, a maintainer may separately authorize the bounded live
transaction documented in `docs/repository-trust.md`. A passing normalized
observation and new hosted run are required before the task can claim the live
boundary; the path-scoped metadata job remains advisory.
