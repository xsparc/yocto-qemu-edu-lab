// SPDX-License-Identifier: MIT
/* Report a sysfs write errno without depending on shell diagnostic wording. */

#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

static int report_errno(const char *operation)
{
	int saved_errno = errno;

	fprintf(stderr, "qemu-edu-write: %s: errno=%d\n", operation,
		saved_errno);
	return 1;
}

int main(int argc, char **argv)
{
	ssize_t written;
	size_t length;
	int fd;

	if (argc != 3) {
		fprintf(stderr, "usage: qemu-edu-write SYSFS_PATH VALUE\n");
		return 2;
	}

	fd = open(argv[1], O_WRONLY | O_CLOEXEC);
	if (fd < 0)
		return report_errno("open");

	length = strlen(argv[2]);
	written = write(fd, argv[2], length);
	if (written < 0) {
		int result = report_errno("write");

		close(fd);
		return result;
	}
	if ((size_t)written != length) {
		int result;

		errno = EIO;
		result = report_errno("short write");
		close(fd);
		return result;
	}
	if (close(fd) < 0)
		return report_errno("close");

	return 0;
}
