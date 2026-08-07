# SPDX-License-Identifier: MIT

.PHONY: setup inspect build run rebuild-driver clean-driver check check-source-lock check-workflow test-workflow checksums

setup:
	./setup.sh

inspect:
	./inspect.sh

build:
	./build.sh

run:
	./run.sh

rebuild-driver:
	bash -c 'source ./environment.sh && target_text=$$(python3 "$$QEMU_EDU_ROOT/scripts/source_lock.py" --repo "$$QEMU_EDU_ROOT" get build.targets --lines) && mapfile -t targets <<<"$$target_text" && bitbake qemu-edu-driver -c compile -f && bitbake "$${targets[@]}"'

clean-driver:
	bash -c 'source ./environment.sh && bitbake qemu-edu-driver -c cleansstate'

check: check-source-lock check-workflow test-workflow
	python3 scripts/update_checksums.py --check
	git diff --check

check-source-lock:
	python3 scripts/source_lock.py validate

check-workflow:
	python3 scripts/validate_workflow.py

test-workflow:
	python3 -m unittest discover -s tests -p 'test_*.py'

checksums:
	python3 scripts/update_checksums.py
