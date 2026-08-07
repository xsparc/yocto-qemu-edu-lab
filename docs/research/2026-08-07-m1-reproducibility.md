<!--
SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
SPDX-License-Identifier: MIT
-->

# M1 reproducibility and CI research — 2026-08-07

Primary sources and live upstream refs were checked on 2026-08-07. Recheck
release status, action identities, runner capacity, and security guidance when
updating the lock or CI.

## Source layout and release identity

- Yocto's 5.3 migration guide states that the Poky combo repository is no
  longer updated for new releases. The 6.0 manual assembles Poky from separate
  BitBake, OpenEmbedded Core, and meta-yocto repositories.
  Sources: <https://docs.yoctoproject.org/6.0/migration-guides/migration-5.3.html>
  and <https://docs.yoctoproject.org/6.0/dev-manual/poky-manual-setup.html>.
- The Yocto release page identifies 6.0 Wrynose as LTS and 6.0.2 as its current
  point release. Source: <https://www.yoctoproject.org/development/releases/>.
- Live `git ls-remote` checks of the official release tags resolved to the three
  commits recorded in `config/sources.lock.json`. The lock records both branch
  and release refs but the full commit alone drives checkout.

## Orchestration choice

- Upstream `bitbake-setup` provides configuration and fixed-revision concepts
  close to this project's direction. Source:
  <https://docs.yoctoproject.org/bitbake/2.18/bitbake-user-manual/bitbake-user-manual-environment-setup.html>.
- kas 5.4 supports repository locks, includes, configuration composition, and
  optional signer policy. It is MIT-licensed, but introduces a separately
  versioned host tool and Python dependency graph. Sources:
  <https://kas.readthedocs.io/en/latest/userguide/project-configuration.html>
  and <https://github.com/siemens/kas>.
- With three repositories and one build configuration, a small project-owned
  closed JSON contract is lower-cost and more transparent for learners. Its
  fields deliberately map to later kas or `bitbake-setup` concepts. This choice
  must be revisited rather than expanded into a general build framework.

## Reproducibility limits

- Git `rev-parse`, `cat-file`, and ancestry checks can prove the locally
  resolved object identity and ref relationship. Sources:
  <https://git-scm.com/docs/git-rev-parse>,
  <https://git-scm.com/docs/git-cat-file>, and
  <https://git-scm.com/docs/git-merge-base>.
- A commit lock is not cryptographic origin authentication. HTTPS and the
  official upstream endpoints remain trust assumptions.
- Yocto's offline procedure separately requires pre-fetched recipe sources,
  mirrors, and `BB_NO_NETWORK`. Source:
  <https://docs.yoctoproject.org/dev-manual/building.html#replicating-a-build-offline>.
- M1 therefore claims reproducible source metadata resolution, not offline
  image availability or identical image output.

## CI and capacity

- GitHub recommends pinning third-party actions to full commit SHAs and using
  least privilege. Sources:
  <https://docs.github.com/en/actions/reference/security/secure-use> and
  <https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/find-and-customize-actions#using-shas>.
- Standard public Linux runners provide less disk and memory than Yocto 6.0's
  documented 140 GB/32 GB baseline. Sources:
  <https://docs.github.com/en/actions/reference/runners/github-hosted-runners>
  and <https://docs.yoctoproject.org/6.0/ref-manual/system-requirements.html>.
- `yocto-check-layer` covers README/security policy, parse, environment, world
  signatures, patch metadata, compatibility, and BSP-machine checks without
  compiling the full image. Source:
  <https://docs.yoctoproject.org/6.0/dev-manual/layers.html#yocto-check-layer-script>.

## Decisions influenced

- Replace the invalid Poky combo assumption rather than preserving it as a
  supported rollback path.
- Use exact split-repository commits and explicit `DISTRO = "poky"`.
- Keep fast checks secret-free and immutable; keep the Linux metadata lane
  distinct from future full build/runtime evidence.
- Add a layer README and explicit `core` dependency so native layer validation
  describes the actual metadata relationship. `qemux86-64.conf` is supplied by
  OE-Core; meta-yocto-bsp is not required by this lab.
- Start at `0.1.0-dev`; do not publish a release from M1 without separate
  approval and evidence.
