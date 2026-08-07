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
| Documentation, scripts, tests, agent state, Yocto metadata, image recipe, test utility | MIT | Permissive reuse of educational and build material |
| `qemu_edu.c` and its external-module `Makefile` | GPL-2.0-only | Linux kernel module implementation and build source |
| Third-party checkouts and build output | Their own licenses; not vendored here | `poky/`, downloads, shared state, and build output are ignored |

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
- Keep GPL-only kernel implementation out of MIT files unless the resulting
  file and repository boundary are deliberately relicensed and reviewed.

## REUSE policy

`REUSE.toml` supplies project copyright and fallback license information while
preserving more specific file headers. `LICENSES/MIT.txt` and
`LICENSES/GPL-2.0-only.txt` are the only license texts needed by the current
tree. Run `reuse lint` in CI once the tool is introduced in M1. Until then,
review the mapping whenever files or license boundaries change.

## Dependencies, artifacts, and releases

- Prefer dependencies already supplied by supported Yocto/Poky revisions.
- Record licenses for any new host tool or vendored component before adoption.
- Yocto-generated SPDX SBOMs describe image contents; they complement rather
  than replace repository file licensing.
- Release artifacts should include source revision, build input identity,
  checksums, SBOM location, and provenance. Do not claim reproducibility or a
  SLSA level without the prescribed evidence.
- `SHA256SUMS` protects source-tree transfer integrity only. It is not a
  signature, SBOM, license report, or proof of build provenance.
