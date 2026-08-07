<!--
SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
SPDX-License-Identifier: MIT
-->

# Maintenance workflow

This plan makes long-running work resumable without granting any person or
automation tool unlimited authority. The same evidence and approval rules apply
regardless of how a change is prepared.

## Control loop

1. **Orient:** inspect the branch and worktree, read `MAINTAINERS.md` and
   `docs/maintainers/`, then run the workflow validator.
2. **Research:** check time-sensitive claims against primary sources. Record the
   date, source, conclusion, and affected decision under `docs/research/`.
3. **Select:** resume the one In Progress task. If none exists, propose or groom
   work; do not infer approval from roadmap order.
4. **Plan one slice:** state outcome, acceptance criteria, scope, non-scope,
   dependencies, affected files, compatibility, licensing, security, rollback,
   and validation.
5. **Implement:** make the smallest coherent change. Preserve unrelated work and
   current public interfaces unless the task explicitly migrates them.
6. **Validate:** run targeted checks, then broader checks proportional to risk.
   Record exact output categories and gaps.
7. **Review:** perform an independent findings-first diff review. Kernel,
   licensing, CI, public interface, security, and documentation changes receive
   their relevant specialist view.
8. **Close:** reconcile task evidence, ledger, context, decisions, docs, and
   checksums. Mark Done only when all required evidence exists.
9. **Publish the milestone proposal:** create a concise commit, push its branch,
   and open one pull request. Do not merge or release unless separately asked.

## Milestone branch and PR contract

- Branch: `milestone/m<N>-<short-purpose>` or an equivalent contributor branch
  that names the milestone.
- Commit subject: imperative, specific, and free of unsupported claims.
- Pull-request body: problem, outcome, scope, non-scope, architecture and license
  impact, tests actually run, gaps, rollback, and follow-up milestone.
- Keep generated evidence out of git unless it is stable, reviewable, useful to
  learners, and covered by the licensing policy.
- A dependent milestone waits until the prerequisite PR is merged or a human
  explicitly approves parallel work with a conflict plan.

## Review responsibilities

| Concern | Questions |
|---|---|
| Product | Does the change improve a named learner job with observable acceptance? |
| Architecture | Are boundaries and dependency direction preserved? |
| Kernel | Are lifetime, locking, MMIO, IRQ, DMA, error, and teardown paths safe? |
| Quality | Do positive, negative, regression, and compatibility tests support the claim? |
| Security | Are inputs, paths, subprocesses, credentials, network, and privileges bounded? |
| Licensing | Are source, copyright, SPDX expression, recipe metadata, and redistribution rights clear? |
| Operations | Can CI/build failures be diagnosed and rolled back without hidden state? |
| Documentation | Can a learner reproduce and understand the new behavior? |

One reviewer may cover several concerns, but review evidence must name the
concern and finding; generic “looks good” is insufficient.

## Research cadence

Refresh research when a milestone begins and whenever a claim depends on active
Yocto releases, QEMU/kernel interfaces, CI services, security standards, SBOM
formats, SLSA, or MCP. Prefer official manuals, specifications, and upstream
repositories. Record disagreement or uncertainty rather than blending sources.

## Optional automation and AI integration

AI readiness means high-quality interfaces, not adding a chatbot first:

- commands have stable exit codes and `--json` output;
- schemas carry versions and reject unknown unsafe input;
- evidence links to source revision and validation context;
- read-only inspection is separated from state changes;
- every side effect has a narrow name, bounded arguments, and approval policy;
- logs and source stay local unless the user deliberately selects a provider;
- no prompt or model output becomes approval, test evidence, or project truth.

An MCP adapter is a possible M6 integration because MCP standardizes resources
and tools, but it must remain thin and replaceable. The lab CLI and evidence
schema are the primary contract.

## Stop and escalate conditions

Stop before continuing when work would require unclear redistribution rights,
credentials, paid services, destructive migration, production access, public
release, unsupported compatibility claims, or a product/architecture choice
that materially changes the roadmap. Record the exact decision needed.
