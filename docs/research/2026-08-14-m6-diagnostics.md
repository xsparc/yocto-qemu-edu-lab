<!--
SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
SPDX-License-Identifier: MIT
-->

# M6 diagnostics research — 2026-08-14

Primary specifications, implementation documentation, and package metadata were
checked before freezing the A006 diagnostics boundary.

## Deterministic local interface

- JSON Schema Draft 2020-12 provides the closed tuple and object vocabulary
  needed to fix command names, check order, result shapes, and extension points
  without accepting undeclared fields. Source:
  <https://json-schema.org/draft/2020-12>
- Python 3.12's `json` module sorts object keys when `sort_keys` is enabled and
  can reject non-finite numbers with `allow_nan=False`. Its defaults otherwise
  accept non-standard non-finite values and repeated object names, so the
  project parser adds duplicate-name, depth, item-count, scalar-size, and
  surrogate checks before semantic validation. Source:
  <https://docs.python.org/3.12/library/json.html>
- Python exposes a binary buffer beneath standard output. The command writes
  one explicitly encoded UTF-8 document with one LF to that buffer, avoiding
  locale-dependent text-stream encoding and newline conversion. Source:
  <https://docs.python.org/3.12/library/sys.html#sys.stdout>
- Git supports disabling system and global configuration, prompting, and
  optional locks through documented environment variables. It also supports an
  exact `safe.directory`; the wildcard form would trust every repository. The
  diagnostics Git adapter therefore executes a fixed read-only query set with
  isolated configuration, bounded output, and bounded time rather than
  importing repository state through a library or shell. Sources:
  <https://git-scm.com/docs/git> and
  <https://git-scm.com/docs/git-config/2.54.0#Documentation/git-config.txt-safedirectory>

## Independent schema oracle

- `jsonschema` 4.26.0 is an MIT-licensed Draft 2020-12 implementation supporting
  Python 3.10 and newer. It remains a CI/test oracle only; the shipped command
  uses the Python standard library and the project's closed semantic validator.
  Source: <https://pypi.org/project/jsonschema/4.26.0/>
- A resolver-selected dependency set would make the test oracle change over
  time. M6 instead records six exact CPython 3.12 Linux wheels, their SHA-256
  digests, embedded metadata, license-file digests, and direct dependency
  relationships. CI downloads those URLs directly, installs with no index and
  no dependency resolution, disables schema retrieval, and deletes the
  temporary environment on exit.
- The lock is specific to Linux CPython 3.12. It is not a runtime dependency,
  a general-purpose package lock, or evidence that another platform can install
  the same binary wheel set.

## Agent interoperability direction

- The Model Context Protocol specification dated 2026-07-28 made substantial
  changes including a stateless core, formal extensions, updated authorization,
  and transport-independent semantics. Its tool surface is model-controlled
  and may invoke external systems. Sources:
  <https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/blog/content/posts/2026-07-28-spec-ga/index.md>,
  <https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/basic/transports/index.mdx>,
  and
  <https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/server/tools.mdx>
- A2A 1.0 defines peer-agent discovery and stateful task operations over
  multiple protocol bindings. Its normative data model is Protocol Buffers and
  its Agent Card includes endpoints and authentication requirements. Source:
  <https://github.com/a2aproject/A2A/blob/main/docs/specification.md>
- These protocols solve transport, discovery, authorization, and task-lifecycle
  problems that do not belong in a local read-only lab inspector. Adding either
  protocol in M6 would expand the trust boundary from bounded local files and
  fixed Git queries to network listeners, credentials, remote inputs, and
  protocol-version negotiation.
- M6 therefore establishes a provider-neutral JSON document and deterministic
  exit contract first. A later approved adapter can translate that stable local
  contract into MCP resources/tools, A2A artifacts, or another protocol without
  changing diagnostic meaning. Such an adapter must preserve read-only
  semantics, declare authentication and consent behavior, pin its protocol
  version, and receive its own threat model and compatibility tests.

## Decisions influenced

- Keep the shipped command standard-library-only, offline, and read-only.
- Use one closed schema and an internal semantic validator, plus an independent
  exact-dependency CI oracle.
- Bound every untrusted file and subprocess response before parsing it.
- Treat unavailable required evidence differently from a failed check so
  automation can distinguish an incomplete workspace from a diagnosed defect.
- Defer MCP, A2A, SDKs, models, transports, and mutation to separately approved
  work after the local contract has public usage evidence.
