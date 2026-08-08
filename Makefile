# SPDX-License-Identifier: MIT

.PHONY: setup inspect build run runtime-test rebuild-driver clean-driver check check-source-lock check-workflow check-qemu-security test-workflow checksums

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

rebuild-driver:
	bash -c 'source ./environment.sh && target_text=$$(python3 "$$QEMU_EDU_ROOT/scripts/source_lock.py" --repo "$$QEMU_EDU_ROOT" get build.targets --lines) && mapfile -t targets <<<"$$target_text" && bitbake qemu-edu-driver -c compile -f && bitbake "$${targets[@]}"'

clean-driver:
	bash -c 'source ./environment.sh && bitbake qemu-edu-driver -c cleansstate'

check: check-source-lock check-workflow check-qemu-security test-workflow
	python3 scripts/update_checksums.py --check
	git diff --check

check-source-lock:
	python3 scripts/source_lock.py validate

check-workflow:
	python3 scripts/validate_workflow.py

check-qemu-security:
	python3 scripts/verify_qemu_security.py static

test-workflow:
	python3 -m unittest discover -s tests -p 'test_*.py'

checksums:
	python3 scripts/update_checksums.py
