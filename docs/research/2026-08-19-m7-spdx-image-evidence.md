<!--
SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
SPDX-License-Identifier: MIT
-->

# M7 research: bounded SPDX image-composition evidence

Date: 2026-08-19

Decision affected: D-018 and task A008.

## Question

What is the smallest truthful, maintainable supply-chain evidence stage after
the dual-lab runtime and diagnostics milestones?

The project needs a machine-consumable answer about its own package composition
and generated image hashes. It does not yet need a signing service, hosted SBOM
database, vulnerability platform, or release attestation system.

## Exact compatibility authority

The source lock selects Yocto 6.0.2 and OE-Core commit
`5d1aa5c806c061a2994f4decb59016610f093213`. The Yocto 6.0.2 release notes
publish that exact revision and release artifact. The locked implementation,
not a newer branch or generic SPDX tutorial, is the compatibility authority.

Primary sources:

- [Yocto 6.0.2 release notes](https://docs.yoctoproject.org/next/migration-guides/release-notes-6.0.2.html)
- [locked `create-spdx-3.0.bbclass`](https://git.openembedded.org/openembedded-core/plain/meta/classes/create-spdx-3.0.bbclass?id=5d1aa5c806c061a2994f4decb59016610f093213)
- [locked SPDX task implementation](https://git.openembedded.org/openembedded-core/plain/meta/lib/oe/spdx30_tasks.py?id=5d1aa5c806c061a2994f4decb59016610f093213)
- [locked SPDX model entry point](https://git.openembedded.org/openembedded-core/plain/meta/lib/oe/spdx30/__init__.py?id=5d1aa5c806c061a2994f4decb59016610f093213)
- [SPDX 3.0.1 specification](https://spdx.github.io/spdx-spec/v3.0.1/)

## Findings from the locked implementation

`create-spdx.bbclass` selects SPDX 3 through `create-spdx-3.0`. Its default
document version is 3.0.1 and its default profiles are `core build software
simpleLicensing security`. The privacy and reproducibility-sensitive switches
for build variables, parent-build identity, timestamps, kernel configuration,
PACKAGECONFIG, sources, and compiled sources default to disabled. The default
VEX selection is `current`; that value is a generator input, not proof of
freshness.

`create_rootfs_spdx()` represents the image rootfs as an archive-purpose
software package. It creates a BitBake rootfs build, relates the directly
installed packages as build-scoped inputs, and filters those packages by
install purpose. Package SPDX graphs relate installed packages to declared
license expressions.

`create_image_sbom_spdx()` combines the rootfs graph and image-build graphs into
one build SBOM. The SBOM roots are the rootfs package and generated image files;
the image files carry SHA-256 values in `verifiedUsing`. The stable
`${IMAGE_LINK_NAME}.spdx.json` deployment link points at the selected image
document.

The model exposes `SHACLObjectSet` and `JSONLDDeserializer`, so the project can
validate the exact locked shape without vendoring another model. OE-Core's own
selftests use model loading, root-type counts, and missing-ID checks. Those
checks are necessary but not sufficient for this project's package/license and
artifact-hash claim.

## Options considered

### Commit or upload the raw SBOM

Rejected for M7. Raw documents can be large, include the complete image graph,
and are tied to one build. Committing or uploading them would expand retention,
privacy, and review scope without improving the bounded project claim.

### Add a general SPDX library from PyPI

Rejected. It would create a second model and dependency/version boundary even
though the exact locked builder already provides its generated SHACL model.
The projected evidence validator should remain standard-library-only.

### Use text or JSON-path matching over raw JSON-LD

Rejected. JSON-LD links and typed objects should be resolved by the exact model.
String matching could miss unresolved identifiers, aliases, relationship
direction, purpose, or profile errors.

### Start with signing, attestations, or SLSA

Deferred. Those features require a threat model, builder identity, key or OIDC
trust, immutable publication, retention, and verification policy. A local
unsigned projection cannot honestly imply any of them.

### Closed local projection over the locked model

Selected. It preserves the raw SPDX document as build output while producing a
small contract for project package/license presence and image-file hashes. The
projection can later become one input to separately approved provenance work
without pretending to be that provenance today.

## Security and privacy conclusions

- Read the raw SBOM once and bound it to 128 MiB.
- Import the model only from the exact locked OE-Core path.
- Accept only a catalog-selected build and deployment directory.
- Reject stable SBOM links or image artifacts that escape that directory.
- Reject artifact symlinks and independently stream each file's SHA-256 under
  an 8 GiB per-file limit.
- Project no raw paths, timestamps, build variables, environment, supplier,
  creator, package list beyond the project allowlist, or arbitrary JSON-LD.
- Keep evidence below 1 MiB and reject duplicate keys, unsafe strings, unknown
  fields, aliases, inconsistent counts, and stale/current identity drift.
- Never execute malformed or adversarial image content as a validation method.

## CI and qualification conclusion

Fast public CI can validate the manifest, semantic contract, external Draft
2020-12 schema, wrappers, licensing, and metadata preflight. The hosted runner
does not have the documented capacity for two full Yocto image graphs, so it
must not claim image-composition evidence.

A008 closes only after an adequately sized, isolated Linux worker builds both
selected images at one clean revision, runs the wrapper for each lab, and
validates both documents with current-input and revision binding. Raw SBOMs and
images stay local. Publication, merge, signing, attestation, tag, and release
remain separate decisions.
