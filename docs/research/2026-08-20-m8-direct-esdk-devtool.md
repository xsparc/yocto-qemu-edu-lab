<!--
SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
SPDX-License-Identifier: MIT
-->

# M8 direction brief: isolated direct-eSDK application iteration

## DirectionBriefV1

- `schema_version`: `1`
- `baseline_commit`: `c457cfc8a7b362ceeee50c74722916a7f65453bc`
- `scanned_at`: `2026-08-20`
- `coverage`: locked Yocto compatibility, direct and standalone eSDK models,
  devtool source modification, IDE-neutral sysroots, live-target deployment,
  rollback, licensing, public-CI capacity, and future automation adapters.

## Findings

### 1. Prefer the direct eSDK environment already inside the Yocto build

- `finding`: Yocto documents two eSDK models. The direct model reuses a regular
  build directory and avoids producing, distributing, and maintaining a large
  installer archive; the standalone installer is useful when a binary artifact
  cache is required for smaller developer hosts.
- `source_event_date`: `2026-08-20` scan of the 6.0.2 documentation.
- `sources`: [Yocto 6.0.2 eSDK manual](https://docs.yoctoproject.org/6.0.2/sdk-manual/extensible.html),
  [Yocto 6.0.2 release notes](https://docs.yoctoproject.org/next/migration-guides/release-notes-6.0.2.html).
- `confidence`: high.
- `relevance`: direct support for the approved M8 learning loop.
- `direction_alignment`: matches the existing locked build and offline-first
  architecture.
- `opportunity_or_risk`: one metadata and source authority is easier to teach;
  a shared normal build directory would risk workspace and configuration drift.
- `engineering_cost`: medium because each lab needs a disposable development
  build root and full Linux qualification.
- `disposition`: adopt.
- `roadmap_delta`: add M8 with one direct-eSDK profile per lab; do not create a
  standalone installer in this milestone.
- `verification_needed`: exact metadata, sysroot, build, deploy, execute,
  undeploy, reset, and dual-lab regression evidence.

### 2. Use devtool only for one closed, libc-only sample

- `finding`: `devtool modify` makes an existing recipe use a developer-owned
  source tree, `devtool build` populates its sysroot output, and
  `deploy-target`/`undeploy-target` provide a reversible live-target loop.
  Deploy does not install runtime dependencies and bypasses target package
  management.
- `source_event_date`: `2026-08-20` scan of the 6.0.2 documentation and exact
  locked OE-Core commit.
- `sources`: [devtool quick reference](https://docs.yoctoproject.org/6.0.2/ref-manual/devtool-reference.html),
  [locked standard plugin](https://git.openembedded.org/openembedded-core/plain/scripts/lib/devtool/standard.py?id=5d1aa5c806c061a2994f4decb59016610f093213),
  [locked deploy plugin](https://git.openembedded.org/openembedded-core/plain/scripts/lib/devtool/deploy.py?id=5d1aa5c806c061a2994f4decb59016610f093213).
- `confidence`: high.
- `relevance`: defines the smallest reversible application exercise.
- `direction_alignment`: preserves Yocto-native tooling and avoids a parallel
  deployment mechanism.
- `opportunity_or_risk`: a libc-only sample keeps dependencies already present
  in the base image; arbitrary recipes or targets would broaden SSH, path, and
  package-management risk.
- `engineering_cost`: medium.
- `disposition`: adopt.
- `roadmap_delta`: bind one recipe, source directory, guest binary, and evidence
  filename in manifest schema 3.
- `verification_needed`: prove the binary is absent from both base images,
  appears only after deploy, executes with the expected architecture/output,
  disappears after undeploy, and stays absent after a cold reboot.

### 3. Keep IDE and provider choice outside the executable contract

- `finding`: the locked `ide-sdk` command supports generated SDKs independently
  of a particular editor. M8 needs the cross-development environment, not an
  editor integration or hosted agent.
- `source_event_date`: `2026-08-20` scan of the 6.0.2 documentation and exact
  locked plugin.
- `sources`: [devtool IDE-SDK reference](https://docs.yoctoproject.org/6.0.2/ref-manual/devtool-reference.html#generate-an-ide-configuration-for-a-recipe),
  [locked IDE-SDK plugin](https://git.openembedded.org/openembedded-core/plain/scripts/lib/devtool/ide_sdk.py?id=5d1aa5c806c061a2994f4decb59016610f093213).
- `confidence`: high.
- `relevance`: keeps the learning workflow portable.
- `direction_alignment`: follows the provider-neutral and deterministic-core
  decisions already accepted for diagnostics.
- `opportunity_or_risk`: future IDE, MCP, A2A, or agent adapters can consume
  closed local evidence, but must not acquire implicit build or SSH authority.
- `engineering_cost`: low for the boundary; future adapters are separate work.
- `disposition`: adopt.
- `roadmap_delta`: select the IDE-neutral mode and explicitly exclude adapters
  from M8.
- `verification_needed`: run the locked source/interface verifier in both
  metadata profiles and qualify the fail-closed host controller with fixed
  argv and no user-supplied QEMU or SSH arguments.

### 4. Do not publish SDKs or run full iteration on standard public runners

- `finding`: a direct eSDK still consumes the full Yocto build graph and live
  software-QEMU target. The project's established public-runner capacity
  boundary remains lower than the documented full-build baseline.
- `source_event_date`: `2026-08-20` project and upstream capacity review.
- `sources`: [Yocto system requirements](https://docs.yoctoproject.org/6.0.2/ref-manual/system-requirements.html),
  [direct eSDK setup](https://docs.yoctoproject.org/6.0.2/sdk-manual/extensible.html#setting-up-the-extensible-sdk-environment-directly-in-a-yocto-build).
- `confidence`: high.
- `relevance`: prevents metadata CI from being mislabeled as SDK evidence.
- `direction_alignment`: preserves the fast/metadata/full-evidence separation.
- `opportunity_or_risk`: local isolated qualification is slower but avoids
  publishing build trees, SDK installers, keys, or SSH material.
- `engineering_cost`: high for final qualification, low for public CI.
- `disposition`: no-change.
- `roadmap_delta`: keep public CI at repository, licensing, and metadata gates;
  require an adequately sized isolated Linux worker for acceptance.
- `verification_needed`: record exact worker limits, commands, hashes, clean
  revision, dual-lab results, and retained closed evidence only.

### 5. Keep retained learner source outside the executable workspace layer

- `finding`: exact locked `devtool` prepends every layer `BBPATH` to its plugin
  search path. A retained workspace can therefore override devtool plugins if
  it contains `lib/devtool` content. Exact locked `devtool reset` also moves a
  non-empty source tree below `workspace/sources` into a timestamped `attic`.
- `source_event_date`: `2026-08-28` exact-source lifecycle recheck.
- `sources`: [locked devtool entry point](https://git.openembedded.org/openembedded-core/plain/scripts/devtool?id=5d1aa5c806c061a2994f4decb59016610f093213),
  [locked standard plugin reset](https://git.openembedded.org/openembedded-core/plain/scripts/lib/devtool/standard.py?id=5d1aa5c806c061a2994f4decb59016610f093213).
- `confidence`: high.
- `relevance`: controls both executable plugin authority and truthful retained
  source evidence.
- `direction_alignment`: preserves the exact locked toolchain and keeps one
  stable learner-owned file outside generated layer metadata.
- `opportunity_or_risk`: reusing an unvalidated workspace could execute stale
  plugin code; placing learner source below it would make reset change its
  location and invalidate the documented lifecycle.
- `engineering_cost`: low because the existing disposable build root can hold
  a sibling `learner-source` directory and a closed residual-tree validator.
- `disposition`: adopt.
- `roadmap_delta`: pin the generated Wrynose `layer.conf`, reject unknown or
  executable retained workspace state before and after use, require the
  generated append's exact locked-source form as well as its closed checksum
  record, recover with `reset --no-clean`, and keep the fixed learner source in
  a manifest-selected sibling directory.
- `verification_needed`: negative plugin/layer/symlink/residual tests plus a
  real clean-revision reset that retains the source at the exact declared path.

### 6. Treat a workspace checksum as integrity, not metadata authority

- `finding`: locked `devtool modify -n` writes a BitBake-parsed bbappend and
  records that file's MD5 in `.devtool_md5`. The record detects a later byte
  change, but a matching attacker-controlled append and checksum remain
  self-consistent; the checksum alone does not prove that the metadata came
  from the locked modify implementation.
- `source_event_date`: `2026-08-28` exact-source cleanup review.
- `sources`: [locked standard plugin modify and reset](https://git.openembedded.org/openembedded-core/plain/scripts/lib/devtool/standard.py?id=5d1aa5c806c061a2994f4decb59016610f093213).
- `confidence`: high.
- `relevance`: cleanup must not parse retained executable metadata before it
  proves that metadata is the one closed form generated for the fixed recipe
  and learner-source path.
- `direction_alignment`: preserves standard devtool behavior without trusting
  mutable generated state as policy.
- `opportunity_or_risk`: a self-consistent untrusted bbappend could otherwise
  be parsed while `devtool status` or reset reconstructs workspace state.
- `engineering_cost`: low because M8 has one recipe, one exact source path, one
  locked OE-Core revision, and one deterministic generated append form.
- `disposition`: adopt.
- `roadmap_delta`: compare the active append byte-for-byte with the
  locked-source-derived form before any recovery subcommand, then separately
  verify its exact recipe-relative checksum record.
- `verification_needed`: reject a malicious but self-consistent append/checksum
  pair without invoking devtool, then confirm the expected form in the final
  clean native-Linux direct-eSDK run.

### 7. Replace ambient Python module authority for locked child tools

- `finding`: the locked OE environment prepends BitBake's library to an
  existing `PYTHONPATH` rather than replacing it. The locked devtool entry point
  then appends its own plugin library after existing import paths. An inherited
  module path or Python user site can therefore shadow a locked module even
  when the executable itself resolves to the exact checkout. The initializer
  also honors ambient OE source/build roots, BitBake directories, and template
  configuration before the controller starts.
- `source_event_date`: `2026-08-28` exact-source environment recheck.
- `sources`: [locked OE initializer](https://git.openembedded.org/openembedded-core/plain/oe-init-build-env?id=5d1aa5c806c061a2994f4decb59016610f093213),
  [locked OE build environment](https://git.openembedded.org/openembedded-core/plain/scripts/oe-buildenv-internal?id=5d1aa5c806c061a2994f4decb59016610f093213),
  [locked devtool entry point](https://git.openembedded.org/openembedded-core/plain/scripts/devtool?id=5d1aa5c806c061a2994f4decb59016610f093213).
- `confidence`: high.
- `relevance`: all A009 build, metadata, deployment, and runqemu commands are
  Python or shell entry points whose executable identity alone is insufficient.
- `direction_alignment`: keeps the existing locked source model authoritative
  without adding a dependency or copying upstream code.
- `opportunity_or_risk`: ambient Python modules or shell startup files could
  redirect the bounded workflow before its fixed arguments are enforced.
- `engineering_cost`: low because the closed source graph already identifies
  the one exact BitBake library required by the initialized build environment.
- `disposition`: adopt.
- `roadmap_delta`: no new milestone; clear ambient OE setup redirects before
  sourcing the exact initializer, then give every A009 child process and
  runqemu session only the verified BitBake library path, disable Python
  user-site and bytecode behavior, and remove Python and shell startup-injection
  variables.
- `verification_needed`: environment-negative unit tests and exact
  clean-revision metadata, build, direct-eSDK, and runqemu execution for both
  labs.

## Overall recommendation

Adopt a schema-3 `development` profile and an MIT, libc-only sample recipe as
the M8 foundation. Implement the state-changing workflow through one
standard-library host controller that owns a disposable build root, fixed
closed workspace, separate learner source, loopback-only SSH target, bounded
output, cleanup, and evidence.
Keep normal build directories authoritative and untouched. Do not build a
standalone SDK installer, add arbitrary recipe/target inputs, or introduce a
provider integration in M8.

## Evidence gaps

- Exact clean-revision direct-eSDK and devtool execution has not yet run for
  either lab.
- The controller now verifies the locked build-facing executable and devtool
  plugin interface, parses only locked runqemu's loopback guest-SSH mapping,
  closes generated devtool configuration, isolates direct and devtool SSH/SCP
  from host configuration and temporary-path overrides, bounds startup output,
  rejects retained workspace plugin or metadata drift, authenticates the exact
  generated append before recovery, replaces ambient Python and shell startup
  authority for child tools, keeps learner source outside the executable layer,
  owns the emulator process group, and restores target, recipe, layer, source,
  and evidence state. Exact clean dual-lab execution and independent review
  remain open.
- No SDK, deployment, or new runtime result is implied by this foundation
  slice; both historical runtime and SPDX evidence inputs become stale after
  manifest digest changes and require proportional requalification.
