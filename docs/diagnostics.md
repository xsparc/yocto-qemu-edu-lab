<!--
SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
SPDX-License-Identifier: MIT
-->

# Deterministic lab diagnostics

`qemu-edu-lab` is a local, read-only view of declared project state. It serves
people and CI from the same standard-library-only runtime contract; it does not
set up sources, build, boot, test, repair, fetch, or mutate anything.

## Commands

From the repository root:

```bash
./qemu-edu-lab status
./qemu-edu-lab doctor
./qemu-edu-lab inspect
./qemu-edu-lab evidence

./qemu-edu-lab --lab platform-arm64 --format json inspect
```

From another directory, invoke the same executable through its absolute path
or a path to the repository checkout. The executable derives its repository
root from that path rather than from the current working directory.

An omitted lab selects the catalog default, `pci-x86-64`. The only formats are
`text` and `json`; text is the default. Empty or unknown arguments exit 2,
write a bounded usage message to stderr, and emit no diagnostic document.
An unexpected internal exception exits 1 with one fixed stderr line and no
document; tracebacks and exception text are never exposed by the entry point.
A closed or failed output sink also exits 1 with the fixed `output unavailable`
line. The guarded write and flush disable a failed buffered stream before
interpreter shutdown, so it cannot emit a later traceback or exit outside the
declared codes.

- `status` validates the project version, repository identity, maintenance
  task model, source lock, lab catalog, selection, and worktree cleanliness.
- `doctor` adds host Git and SSH availability, exact locked checkout state,
  declared build-file presence, and selected runtime evidence.
- `inspect` projects the locked release, three ordered sources, selected build,
  emulator, and runtime identities. It does not parse effective BitBake state.
- `evidence` validates the one manifest-selected evidence file and projects
  only its allowlisted identity, result, counts, and digests. Evidence identity
  is projected only after its project version, machine, and image match the
  trusted current project and selected manifest; mismatched raw values are not
  copied to output.

Doctor is a declared-precondition diagnostic, not a general host-capacity or
future-build guarantee. Missing checkouts, configuration files, or evidence are
`unavailable`; a present invalid or inconsistent input is `fail`.

## Results and exits

Every non-usage invocation whose output sink remains available emits one closed
version-1 document. Checks have the exact fields `id`, `status`, `required`, and
`summary` in command-defined order. Output-sink failure is a transport error,
not a diagnostic aggregate result.

| Exit | Aggregate result | Meaning |
|---:|---|---|
| 0 | `pass` | Every check passed |
| 0 | `warning` | A non-blocking warning or optional unavailable check exists |
| 1 | `fail` | At least one declared invariant failed |
| 3 | `unavailable` | No check failed, but a required precondition is unavailable |

Failure takes precedence over unavailable, which takes precedence over
warning. Because warnings exit 0, automation that requires a clean current
subject must inspect JSON rather than relying on the process exit alone.

JSON serialization is UTF-8 with LF, sorted object keys, compact separators,
no non-finite values, and one final newline. It is a project byte contract, not
RFC 8785 JCS and not a signing format. The schema is
`schemas/qemu-edu-diagnostics-v1.schema.json`.
Schema 1 accepts ASCII Semantic Versioning project versions independently of
the project minor line. An incompatible diagnostic contract requires a new
schema and SemVer decision.

For strict evidence consumption, require all of the following:

```text
command == "evidence"
result == "pass"
project.dirty == false
data.subject_matches_head == true
```

The evidence command deliberately does not add a second cleanliness check to
its fixed sequence; it always exposes the repository fact in `project.dirty`.
Ignoring that field can mistake an evidence document for qualification of
uncommitted source changes that share the same HEAD.

Platform evidence records current lab-index and manifest digests and therefore
reports `lab_binding=bound`. Immutable PCI evidence schemas 1 through 3 did not
record those catalog fields. A valid current PCI-v3 document instead reports
`lab_binding=not-recorded`, null lab digests, and an explicit warning; the
current source-lock digest, selected machine, image, and evidence profile must
still agree, as must the evidence and current project versions. This warning is
an honest historical format limit, not a failed runtime suite.

## Read-only and privacy boundary

The command derives the repository root from its executable and accepts no
alternate root, file path, environment override, URL, or free-form selector.
It reads only bounded repository files selected by closed source and lab
contracts. Evidence is limited to one MiB and opened once from:

```text
<selected build_dir>/<selected evidence_filename>
```

Symbolic links, reparse points, non-regular files, traversal, oversized files,
duplicate JSON keys, non-finite constants, excessive strings/structure, and
Unicode surrogate code points fail closed. Output never includes local paths,
usernames, hostnames, timestamps, raw logs, exception messages, Git porcelain
paths, or arbitrary evidence fields.

The Git adapter is the only subprocess boundary. It resolves a native Git 2.36
or newer executable, uses no shell, applies fixed read-only queries, disables
hooks, paging, prompting, optional locks, fsmonitor, untracked-cache updates,
maintenance, replacement refs, system/global configuration, and network
operations. Included or worktree-scoped configuration and partial or promisor
repositories are rejected from the raw local configuration before object
queries, removing the lazy-fetch path; the adapter also exports Git's
no-lazy-fetch guard. Locked origin checks read the one raw local URL without
`url.*.insteadOf` expansion or configuration includes. Time and combined
output are bounded. The selected host executable remains a host trust boundary.
POSIX uses a new process group for termination; Windows guarantees direct-child
termination for these fixed Git built-ins, not arbitrary process-tree
containment. File controls detect stable and observable replacement but do not
claim protection against a privileged concurrently mutating host.

## Independent schema dependency boundary

The diagnostic runtime imports only the Python standard library and existing
project modules. Independent Draft 2020-12 tests use `jsonschema==4.26.0` only
inside the `diagnostics-schema` CI job. The complete six-wheel Linux CPython
3.12 dependency closure is recorded in
`config/diagnostics-schema-validator.lock.json` with exact file URLs, wheel
hashes, embedded-license paths and hashes, versions, and dependency metadata.

CI limits each download to one MiB, requires its exact recorded file size,
verifies it before installation, disables
the package index and resolver, forbids source distributions, installs into an
ephemeral environment, checks installed versions, runs positive and adversarial
schema cases, and publishes no artifact. Five wheels are MIT and
`typing-extensions` is PSF-2.0; no wheel is redistributed in this source tree.

MCP, A2A, provider SDKs, model access, diagnostic networking, and state-changing
tools are not part of schema version 1. A future transport requires a separate
approved milestone and must remain a replaceable adapter over this contract.
