# SPDX-License-Identifier: MIT

.PHONY: setup inspect build run rebuild-driver clean-driver check check-workflow test-workflow checksums

setup:
	./setup.sh

inspect:
	./inspect.sh

build:
	./build.sh

run:
	./run.sh

rebuild-driver:
	bash -c 'source poky/oe-init-build-env build >/dev/null && bitbake qemu-edu-driver -c compile -f && bitbake qemu-edu-image'

clean-driver:
	bash -c 'source poky/oe-init-build-env build >/dev/null && bitbake qemu-edu-driver -c cleansstate'

check: check-workflow test-workflow
	python3 scripts/update_checksums.py --check
	git diff --check

check-workflow:
	python3 scripts/validate_workflow.py

test-workflow:
	python3 -m unittest discover -s tests -p 'test_*.py'

checksums:
	python3 scripts/update_checksums.py
