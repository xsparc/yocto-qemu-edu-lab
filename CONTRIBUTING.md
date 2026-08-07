<!--
SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
SPDX-License-Identifier: MIT
-->

# Contributing

Thanks for helping make the lab clearer, safer, and more reproducible.

## Before starting

- Read `docs/vision.md`, `docs/architecture.md`, and `docs/roadmap.md`.
- Check `.agents/ledger.md` for active or overlapping work.
- Open an issue or discussion before a new architecture, external dependency,
  public interface, or broad milestone.
- Keep a change focused on one learning outcome or milestone.

## Development

Use a supported Linux host, Linux VM, or WSL2 for Yocto builds. Repository-local
checks require Python 3.11 or newer:

```bash
python3 scripts/validate_workflow.py
python3 -m unittest discover -s tests -p 'test_*.py'
python3 scripts/update_checksums.py --check
git diff --check
```

Run the build and runtime commands relevant to your change. If a full Yocto
build is unavailable, say so in the pull request; do not report it as passed.

## Pull requests

- Explain the learner problem and observable outcome.
- State scope, non-scope, compatibility impact, license impact, tests actually
  run, evidence gaps, and rollback.
- Add positive and negative tests for behavior changes.
- Update explanations and exercises in the same pull request as behavior.
- Stage the complete intended source change, then regenerate `SHA256SUMS` last
  with `python3 scripts/update_checksums.py`. The generator hashes staged Git
  blobs, so unstaged and untracked files are deliberately excluded.

Automation and coding assistants are allowed, but the submitting contributor is
responsible for understanding the change, verifying its provenance and license,
and reporting validation truthfully. Do not invent reviewers, test results,
authorship, or disclosures.

## Licensing

By contributing, you confirm that you have the right to submit the work under
the license shown for its destination in `docs/licensing.md`. Add SPDX headers
to new files and preserve upstream notices. Do not submit copied material with
unclear terms.
