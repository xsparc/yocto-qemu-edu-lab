# SPDX-License-Identifier: MIT

.PHONY: setup inspect build run runtime-test sbom-evidence rebuild-driver clean-driver check check-source-lock check-labs check-workflow check-ci check-qemu-security check-diagnostics-lock test-workflow checksums

setup:
	./setup.sh

inspect:
	./inspect.sh

build:
	./build.sh

run:
	./run.sh

runtime-test:
	./runtime-test.sh

sbom-evidence:
	./sbom-evidence.sh

rebuild-driver:
	bash -c 'source ./environment.sh && driver=$$(python3 "$$QEMU_EDU_ROOT/scripts/lab_config.py" --repo "$$QEMU_EDU_ROOT" --lab "$$QEMU_EDU_LAB" get build.driver_target) && target_text=$$(python3 "$$QEMU_EDU_ROOT/scripts/lab_config.py" --repo "$$QEMU_EDU_ROOT" --lab "$$QEMU_EDU_LAB" get build.targets --lines) && mapfile -t targets <<<"$$target_text" && bitbake "$$driver" -c compile -f && bitbake "$${targets[@]}"'

clean-driver:
	bash -c 'source ./environment.sh && driver=$$(python3 "$$QEMU_EDU_ROOT/scripts/lab_config.py" --repo "$$QEMU_EDU_ROOT" --lab "$$QEMU_EDU_LAB" get build.driver_target) && bitbake "$$driver" -c cleansstate'

check: check-source-lock check-labs check-workflow check-ci check-qemu-security check-diagnostics-lock test-workflow
	python3 scripts/update_checksums.py --check
	git diff --check

check-source-lock:
	python3 scripts/source_lock.py validate

check-labs:
	python3 scripts/lab_config.py validate

check-workflow:
	python3 scripts/validate_workflow.py

check-ci:
	python3 scripts/validate_ci.py

check-qemu-security:
	python3 scripts/verify_qemu_security.py static

check-diagnostics-lock:
	python3 scripts/verify_diagnostics_schema_lock.py

test-workflow:
	python3 -m unittest discover -s tests -p 'test_*.py'

checksums:
	python3 scripts/update_checksums.py
