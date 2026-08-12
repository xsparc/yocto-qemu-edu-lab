<!--
SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
SPDX-License-Identifier: MIT
-->

# Continuous integration and evidence tiers

CI reports the strongest evidence it actually ran. It does not turn skipped,
resource-constrained, or metadata-only checks into build or runtime claims.

| Tier | Trigger and environment | Evidence | Not proved |
|---|---|---|---|
| Fast checks | Every PR, main push, or manual run on `ubuntu-24.04` | Source-lock and lab-manifest schemas, workflow/CI policy, unit tests, both QEMU patch identities, checksums, changed-line whitespace, ShellCheck, actionlint, REUSE | Upstream availability, BitBake parse, image build, guest runtime |
| Yocto metadata | Relevant PR/main changes or manual run on `ubuntu-24.04` | Exact source resolution, cached offline recheck, both manifest compositions, `bitbake -p`, expanded image metadata, per-machine QEMU append/recipe/dependency isolation, both machine checks through `yocto-check-layer` | Patched source, compiled image or emulator, QEMU boot, guest behavior, offline recipe fetches, bit-for-bit output |
| Full build/runtime | Local/manual on an adequately sized Linux host; no hosted runner currently configured | A completed lab-specific `runtime-test.sh` run builds, boots, executes its required OEQA cases, and emits PCI version-3 or platform version-1 evidence | Nothing until the command actually completes; one lab's result does not qualify the other and metadata CI is not runtime proof |

The stable fast job IDs are `repository`, `static`, and `licensing`. The metadata
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
- REUSE runs from a digest-pinned container with no network, no capabilities,
  a read-only filesystem, and a read-only repository mount.
- Workflows do not use `pull_request_target`, privileged follow-up events,
  caches, artifact uploads, or persistent self-hosted runners.
- `scripts/validate_ci.py` enforces these local invariants and fails closed on
  unpinned actions, write permissions, secrets, or jobs without timeouts.

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
python3 scripts/verify_qemu_security.py static
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

The project provides the executable runtime path and closed evidence formats, but does
not weaken this capacity gate. The repository currently has no self-hosted or
larger runner. Use `docs/runtime-testing.md` on a suitable local or protected
Linux worker, including an isolated Linux container only when its namespace,
storage, memory, and software-emulation limits are recorded with the result. If
a future CI lane retains evidence, it may publish only the allowlisted JSON
result with a short immutable-artifact retention period and recorded digest;
raw build trees, shared state, downloads, and environment dumps remain
excluded.

After the first green M1 runs, maintainers should separately consider making
the three stable fast jobs required, enabling repository-wide action SHA
enforcement, restricting allowed actions, and enabling Dependabot security
updates. These are repository-setting changes, not implied by this pull request.
