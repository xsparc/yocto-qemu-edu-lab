<!--
SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
SPDX-License-Identifier: MIT
-->

# Licensing and provenance policy

This is project policy, not legal advice. Contributors remain responsible for
having the right to submit their work.

## Repository license map

| Area | License | Reason |
|---|---|---|
| Documentation, scripts, tests, maintainer state, Yocto metadata, image recipes, test utilities | MIT | Permissive reuse of educational and build material |
| Both example kernel-module sources and their external-module `Makefile` files | GPL-2.0-only | Linux kernel module implementation and build source |
| QEMU EDU bounds backport | MIT | Upstream patch to MIT-licensed `hw/misc/edu.c`, retaining the original author and commit provenance |
| Project-local QEMU platform-device patch | GPL-2.0-only | A project-maintained teaching model and ARM `virt` integration; not an upstream contribution |
| `qemu,edu-platform.yaml` | GPL-2.0-only OR BSD-2-Clause | Dual license follows the Linux Device Tree binding convention |
| Third-party checkouts and build output | Their own licenses; not vendored here | `layers/`, legacy `poky/`, downloads, shared state, and build output are ignored |
| Diagnostics schema validator wheels | Five MIT packages and one PSF-2.0 package; test execution only | Exact wheels are hash-locked for an isolated CI oracle and are not redistributed in this repository |

The top-level `LICENSE` summarizes the mixed-license repository and `LICENSES/`
contains the corresponding SPDX-named license texts.

## File and recipe metadata are different

A BitBake recipe's `LICENSE` and `LIC_FILES_CHKSUM` describe the software the
recipe packages. They do not automatically declare the copyright license of the
recipe file. This repository treats its recipe metadata as MIT while the driver
recipe correctly packages GPL-2.0-only source.

`MODULE_LICENSE("GPL")` informs the kernel module loader; Linux kernel
documentation explicitly says it does not replace the source file's precise
SPDX license. `qemu_edu.c` therefore retains the `GPL-2.0-only` SPDX identifier.

## Contribution requirements

- New commentable files should place `SPDX-FileCopyrightText` and
  `SPDX-License-Identifier` near the top, after a required shebang if present.
- Use an existing identifier from the SPDX License List. Do not invent license
  abbreviations.
- When copying or adapting external work, record its source, revision, license,
  copyright, and material changes in the same pull request.
- Do not copy content from a package, generated output, website, answer, image,
  or model response if its redistribution rights are unclear.
- Preserve upstream notices and compatible license terms. Ask for a licensing
  decision when compatibility is uncertain.
- Backported patches must retain their upstream author, commit message,
  review/sign-off trailers, immutable source URL, and `Upstream-Status`. REUSE
  metadata covers the patch under the license of the changed upstream file;
  it does not replace those provenance fields.
- Project-local patches must identify their project ownership, intended
  maintenance boundary, license, and truthful `Upstream-Status`. They must not
  reuse backport provenance or be described as upstream-ready without a
  separate contribution decision and the upstream project's policy checks.
- Keep GPL-only kernel implementation out of MIT files unless the resulting
  file and repository boundary are deliberately relicensed and reviewed.

## REUSE policy

`REUSE.toml` supplies project copyright and fallback license information while
preserving more specific file headers. The current tree uses
`LICENSES/MIT.txt`, `LICENSES/GPL-2.0-only.txt`, and
`LICENSES/BSD-2-Clause.txt`. Fast CI runs REUSE from a digest-pinned,
network-disabled container. Review the mapping whenever files or license
boundaries change.

## Dependencies, artifacts, and releases

- Prefer dependencies already supplied by the supported Yocto source lock.
- Record licenses for any new host tool or vendored component before adoption.
- Locked external Git checkouts retain their upstream licensing and are not
  covered by this repository's REUSE report. CI tools are fetched for execution
  and are not redistributed in the source tree.
- The diagnostics runtime has no third-party Python dependency. Its independent
  schema job temporarily installs exact wheels for `attrs`, `jsonschema`,
  `jsonschema-specifications`, `referencing`, and `rpds-py` under MIT, plus
  `typing-extensions` under PSF-2.0. The lock records wheel and embedded-license
  hashes; the job uses no package index or dependency resolver and retains no
  wheel or environment artifact.
- Yocto-generated SPDX SBOMs describe image contents; they complement rather
  than replace repository file licensing.
- Release artifacts should include source revision, build input identity,
  checksums, SBOM location, and provenance. Do not claim reproducibility or a
  SLSA level without the prescribed evidence.
- `SHA256SUMS` protects source-tree transfer integrity only. It is not a
  signature, SBOM, license report, or proof of build provenance.
