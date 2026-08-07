<!--
SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
SPDX-License-Identifier: MIT
-->

# Project direction research — 2026-08-07

Primary sources were checked on 2026-08-07. Recheck time-sensitive items at the
start of the milestone they affect.

## Findings

### Yocto support and compatibility

- The Yocto Project's supported manuals list 6.0 (`wrynose`) and 5.0
  (`scarthgap`) as supported series. The repository's current single-series
  declaration is therefore current but should not be widened without evidence.
  Source: <https://docs.yoctoproject.org/dev/releases.html>
- Yocto recommends `yocto-check-layer`; its checks include a non-empty layer
  README, security policy, parse/environment/world builds, patch status,
  signatures, and `LAYERSERIES_COMPAT`. This shapes M1 validation.
  Source: <https://docs.yoctoproject.org/dev-manual/layers.html>
- Yocto runtime testing boots images with `runqemu` and runs OEQA cases through
  `testimage`, making it the native direction for M2 rather than a parallel host
  harness. Source:
  <https://docs.yoctoproject.org/current/test-manual/runtime-testing.html>
- Yocto can generate SPDX image and recipe SBOM data, including build-agent
  attribution fields. This is the preferred release-SBOM path.
  Source: <https://docs.yoctoproject.org/6.0/dev-manual/sbom.html>

### QEMU EDU and kernel boundaries

- QEMU documents EDU as a teaching device with PCI ID `1234:11e8`, a 1 MiB
  MMIO region, INTx/MSI, a default 28-bit DMA mask, and a 4 KiB internal DMA
  buffer. These facts support the M3 and M4 sequence.
  Source: <https://www.qemu.org/docs/master/specs/edu.html>
- Linux requires precise SPDX identifiers in source; `MODULE_LICENSE()` is
  loader metadata and not the exact source license. The existing GPL-2.0-only
  source header plus `MODULE_LICENSE("GPL")` is coherent.
  Source: <https://docs.kernel.org/process/license-rules.html>

### Licensing and supply chain

- REUSE 3.3 defines per-file copyright/license association through headers or
  `REUSE.toml`, and requires an SPDX-named license text for every referenced
  license. This project uses its TOML fallback to cover files whose formats or
  existing headers do not carry complete information.
  Source: <https://reuse.software/spec-3.3/>
- Yocto defines reproducibility as identical output across time, paths, and host
  environments for identical input configuration, and warns that adding layers
  requires testing that claim. M1 therefore pins inputs before claiming a
  reproducible lab. Source:
  <https://docs.yoctoproject.org/4.0/test-manual/reproducible-builds.html>
- SLSA 1.2 treats provenance as an incremental supply-chain guarantee. The
  roadmap adopts provenance concepts without claiming a level prematurely.
  Source: <https://slsa.dev/spec/v1.2/build-requirements>

### AI and interoperability direction

- MCP's tool model uses named tools with schemas. The 2026-07-28 specification
  emphasizes stateless requests, deterministic/cacheable lists, and explicit
  authorization context. These are useful adapter properties, but MCP remains
  downstream of the lab's own CLI and evidence schema.
  Sources:
  <https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/server/tools.mdx>
  and <https://blog.modelcontextprotocol.io/posts/2026-07-28/>
- MCP authorization and security continue to evolve. Any future adapter starts
  read-only, keeps credentials outside project state, and receives a separate
  threat model. Source:
  <https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization>

## Decisions influenced

- Keep `wrynose` as the only declared series until CI proves another series.
- Put native Yocto layer/runtime/SBOM mechanisms ahead of custom equivalents.
- Sequence baseline runtime automation before MSI and DMA.
- Create deterministic, versioned local evidence before an MCP adapter.
- Treat SBOM, checksums, reproducibility, provenance, and signatures as distinct
  controls with distinct claims.
