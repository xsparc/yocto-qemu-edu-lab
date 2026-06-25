# SPDX-License-Identifier: MIT

.PHONY: setup inspect build run rebuild-driver clean-driver

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
