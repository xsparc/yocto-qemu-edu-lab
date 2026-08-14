#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT
"""Validate and materialize the versioned Yocto source lock."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit


SCHEMA_VERSION = 1
DEFAULT_LOCK = "config/sources.lock.json"
MAX_JSON_BYTES = 64 * 1024
MAX_STRING_LENGTH = 4096
MAX_JSON_DEPTH = 64
MAX_JSON_ITEMS = 100_000
PROJECT_REF_PREFIX = "refs/yocto-qemu-edu-lab"
SOURCE_IDS = {"bitbake", "openembedded-core", "meta-yocto"}
SOURCE_URLS = {
    "bitbake": "https://git.openembedded.org/bitbake",
    "openembedded-core": "https://git.openembedded.org/openembedded-core",
    "meta-yocto": "https://git.yoctoproject.org/meta-yocto",
}
ROOT_KEYS = {"schema_version", "release", "build", "sources"}
RELEASE_KEYS = {"project", "version", "series"}
BUILD_KEYS = {
    "build_system",
    "environment_script",
    "bitbake_bin",
    "build_dir",
    "distro",
    "machine",
    "targets",
    "layers",
}
SOURCE_KEYS = {
    "id",
    "type",
    "url",
    "branch_ref",
    "release_ref",
    "commit",
    "object_format",
    "path",
    "required_paths",
}
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]*\Z")
SOURCE_ID = re.compile(r"[a-z0-9][a-z0-9-]*\Z")
COMMIT_SHA1 = re.compile(r"[0-9a-f]{40}\Z")
GIT_REF = re.compile(r"refs/(?:heads|tags)/[A-Za-z0-9][A-Za-z0-9._/-]*\Z")


class LockError(ValueError):
    """A source lock or checkout failed a closed validation rule."""


def _duplicate_guard(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise LockError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _reject_constant(value: str) -> Any:
    raise LockError(f"unsupported JSON constant: {value}")


def _validate_json_shape(value: Any) -> None:
    pending = [(value, 1)]
    items = 0
    while pending:
        current, depth = pending.pop()
        items += 1
        if items > MAX_JSON_ITEMS:
            raise LockError(f"JSON input exceeds {MAX_JSON_ITEMS} values")
        if depth > MAX_JSON_DEPTH:
            raise LockError(f"JSON input exceeds depth {MAX_JSON_DEPTH}")
        if isinstance(current, str):
            if len(current) > MAX_STRING_LENGTH:
                raise LockError(f"JSON string exceeds {MAX_STRING_LENGTH} characters")
            if any(0xD800 <= ord(character) <= 0xDFFF for character in current):
                raise LockError("JSON contains an invalid Unicode surrogate")
        elif isinstance(current, dict):
            pending.extend((item, depth + 1) for item in current.keys())
            pending.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            pending.extend((item, depth + 1) for item in current)


def parse_lock_bytes(raw: bytes, where: str = "source lock") -> tuple[dict[str, Any], str]:
    """Parse and validate one already-bounded source-lock byte sequence."""
    if len(raw) > MAX_JSON_BYTES:
        raise LockError(f"{where} exceeds {MAX_JSON_BYTES} bytes")
    try:
        text = raw.decode("utf-8")
        data = json.loads(
            text,
            object_pairs_hook=_duplicate_guard,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise LockError(f"invalid JSON in {where}: {exc}") from exc
    _validate_json_shape(data)
    if not isinstance(data, dict):
        raise LockError("lock root must be a JSON object")
    validate_lock(data)
    return data, hashlib.sha256(raw).hexdigest()


def read_lock(path: Path) -> tuple[dict[str, Any], str]:
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_JSON_BYTES + 1)
    except OSError as exc:
        raise LockError(f"cannot read {path}: {exc}") from exc
    return parse_lock_bytes(raw, str(path))


def exact_keys(value: dict[str, Any], expected: set[str], where: str) -> None:
    actual = set(value)
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    if missing:
        raise LockError(f"{where} is missing fields: {', '.join(missing)}")
    if unknown:
        raise LockError(f"{where} has unknown fields: {', '.join(unknown)}")


def object_value(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise LockError(f"{where} must be an object")
    return value


def string_value(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value:
        raise LockError(f"{where} must be a non-empty string")
    if len(value) > MAX_STRING_LENGTH:
        raise LockError(f"{where} exceeds {MAX_STRING_LENGTH} characters")
    return value


def string_list(value: Any, where: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise LockError(f"{where} must be a non-empty array")
    result: list[str] = []
    for index, item in enumerate(value):
        result.append(string_value(item, f"{where}[{index}]"))
    if len(result) != len(set(result)):
        raise LockError(f"{where} contains duplicates")
    return result


def relative_path(value: Any, where: str, *, under: str | None = None) -> str:
    text = string_value(value, where)
    if "\\" in text:
        raise LockError(f"{where} must use forward slashes")
    if any(character.isspace() for character in text):
        raise LockError(f"{where} must not contain whitespace")
    path = PurePosixPath(text)
    if path.is_absolute() or text != path.as_posix() or any(
        part in {"", ".", ".."} for part in path.parts
    ):
        raise LockError(f"{where} must be a normalized repository-relative path")
    if under is not None and (not path.parts or path.parts[0] != under):
        raise LockError(f"{where} must be under {under}/")
    return text


def git_ref(value: Any, where: str, prefix: str) -> str:
    text = string_value(value, where)
    if (
        not GIT_REF.fullmatch(text)
        or not text.startswith(prefix)
        or ".." in text
        or "@{" in text
        or text.endswith((".", "/"))
        or "//" in text
    ):
        raise LockError(f"{where} is not a safe {prefix} reference")
    return text


def validate_lock(data: dict[str, Any]) -> None:
    exact_keys(data, ROOT_KEYS, "lock")
    version = data["schema_version"]
    if type(version) is not int or version != SCHEMA_VERSION:
        raise LockError(
            f"unsupported schema_version {version!r}; expected {SCHEMA_VERSION}"
        )

    release = object_value(data["release"], "release")
    exact_keys(release, RELEASE_KEYS, "release")
    for field in RELEASE_KEYS:
        value = string_value(release[field], f"release.{field}")
        if not TOKEN.fullmatch(value):
            raise LockError(f"release.{field} contains unsupported characters")
    if release["project"] != "yocto":
        raise LockError("release.project must be 'yocto' in schema version 1")

    build = object_value(data["build"], "build")
    exact_keys(build, BUILD_KEYS, "build")
    if build["build_system"] != "openembedded":
        raise LockError("build.build_system must be 'openembedded'")
    relative_path(build["environment_script"], "build.environment_script")
    relative_path(build["bitbake_bin"], "build.bitbake_bin")
    build_dir = relative_path(build["build_dir"], "build.build_dir")
    if PurePosixPath(build_dir).parts[0] == "layers":
        raise LockError("build.build_dir must not overlap locked sources")
    for field in ("distro", "machine"):
        if not TOKEN.fullmatch(string_value(build[field], f"build.{field}")):
            raise LockError(f"build.{field} contains unsupported characters")
    for index, target in enumerate(string_list(build["targets"], "build.targets")):
        if not TOKEN.fullmatch(target):
            raise LockError(f"build.targets[{index}] contains unsupported characters")
    for index, layer in enumerate(string_list(build["layers"], "build.layers")):
        relative_path(layer, f"build.layers[{index}]")

    sources = data["sources"]
    if not isinstance(sources, list) or not sources:
        raise LockError("sources must be a non-empty array")
    ids: set[str] = set()
    paths: set[str] = set()
    for index, raw_source in enumerate(sources):
        where = f"sources[{index}]"
        source = object_value(raw_source, where)
        exact_keys(source, SOURCE_KEYS, where)
        source_id = string_value(source["id"], f"{where}.id")
        if not SOURCE_ID.fullmatch(source_id):
            raise LockError(f"{where}.id contains unsupported characters")
        if source_id in ids:
            raise LockError(f"duplicate source id: {source_id}")
        ids.add(source_id)
        if source["type"] != "git":
            raise LockError(f"{where}.type must be 'git'")

        url = urlsplit(string_value(source["url"], f"{where}.url"))
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username is not None
            or url.password is not None
            or url.query
            or url.fragment
        ):
            raise LockError(f"{where}.url must be a credential-free HTTPS URL")
        if source["url"] != SOURCE_URLS.get(source_id):
            raise LockError(f"{where}.url is not the schema version 1 upstream")
        branch_ref = git_ref(
            source["branch_ref"], f"{where}.branch_ref", "refs/heads/"
        )
        if source_id != "bitbake" and branch_ref != f"refs/heads/{release['series']}":
            raise LockError(f"{where}.branch_ref does not match release.series")
        release_ref = git_ref(
            source["release_ref"], f"{where}.release_ref", "refs/tags/"
        )
        if release_ref != f"refs/tags/yocto-{release['version']}":
            raise LockError(f"{where}.release_ref does not match release.version")
        if source["object_format"] != "sha1":
            raise LockError(f"{where}.object_format must be 'sha1'")
        if not COMMIT_SHA1.fullmatch(
            string_value(source["commit"], f"{where}.commit")
        ):
            raise LockError(f"{where}.commit must be a full lowercase SHA-1")
        path = relative_path(source["path"], f"{where}.path", under="layers")
        if path in paths:
            raise LockError(f"duplicate source path: {path}")
        if any(
            path.startswith(existing + "/") or existing.startswith(path + "/")
            for existing in paths
        ):
            raise LockError(f"overlapping source path: {path}")
        paths.add(path)
        for required_index, required in enumerate(
            string_list(source["required_paths"], f"{where}.required_paths")
        ):
            relative_path(required, f"{where}.required_paths[{required_index}]")

    if ids != SOURCE_IDS:
        missing = sorted(SOURCE_IDS - ids)
        extra = sorted(ids - SOURCE_IDS)
        details = []
        if missing:
            details.append(f"missing {', '.join(missing)}")
        if extra:
            details.append(f"unexpected {', '.join(extra)}")
        raise LockError("schema version 1 source set is invalid: " + "; ".join(details))


def locked_path(root: Path, relative: str) -> Path:
    target = (root / relative).resolve(strict=False)
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise LockError(f"resolved path escapes repository: {relative}") from exc
    return target


def git(path: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", "--no-replace-objects", "-C", str(path), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise LockError(f"git {' '.join(arguments)} failed in {path}: {detail}")
    return result


def git_output(path: Path, *arguments: str) -> str:
    return git(path, *arguments).stdout.strip()


def origin_url(path: Path) -> str | None:
    """Return exactly one raw local origin URL without includes or rewrites."""
    result = git(
        path,
        "config",
        "--local",
        "--no-includes",
        "--null",
        "--get-all",
        "remote.origin.url",
        check=False,
    )
    if result.returncode or not result.stdout.endswith("\0"):
        return None
    values = result.stdout.split("\0")
    if len(values) != 2 or values[1] != "":
        return None
    return values[0]


def inspect_source(root: Path, source: dict[str, Any]) -> dict[str, Any]:
    path = locked_path(root, source["path"])
    result: dict[str, Any] = {
        "id": source["id"],
        "path": source["path"],
        "expected_commit": source["commit"],
        "actual_commit": None,
        "clean": None,
        "detached": None,
        "origin": None,
        "state": "missing",
        "errors": [],
    }
    errors: list[str] = result["errors"]
    if not path.exists():
        errors.append("checkout is missing; run ./setup.sh")
        return result
    if not path.is_dir() or git(path, "rev-parse", "--is-inside-work-tree", check=False).returncode:
        result["state"] = "invalid"
        errors.append("path exists but is not a Git worktree")
        return result

    result["state"] = "drifted"
    result["origin"] = origin_url(path)
    if result["origin"] != source["url"]:
        errors.append(f"origin must be {source['url']}")

    object_format = git(path, "rev-parse", "--show-object-format", check=False)
    if object_format.returncode or object_format.stdout.strip() != source["object_format"]:
        errors.append(f"Git object format must be {source['object_format']}")

    head = git(path, "rev-parse", "--verify", "HEAD", check=False)
    if head.returncode == 0:
        result["actual_commit"] = head.stdout.strip()
        if result["actual_commit"] != source["commit"]:
            errors.append(f"HEAD must be {source['commit']}")
        symbolic = git(path, "symbolic-ref", "-q", "HEAD", check=False)
        result["detached"] = symbolic.returncode != 0
        if not result["detached"]:
            errors.append("HEAD must be detached")
    else:
        errors.append("checkout has no HEAD")

    dirty = git_output(path, "status", "--porcelain=v1", "--untracked-files=normal")
    result["clean"] = not bool(dirty)
    if dirty:
        errors.append("checkout has modified or untracked files")

    for required in source["required_paths"]:
        if not locked_path(path, required).exists():
            errors.append(f"required path is missing: {required}")

    if not errors:
        result["state"] = "ready"
    return result


def preflight_existing(root: Path, source: dict[str, Any]) -> tuple[Path, bool]:
    path = locked_path(root, source["path"])
    if not path.exists():
        return path, False
    if not path.is_dir() or git(path, "rev-parse", "--is-inside-work-tree", check=False).returncode:
        raise LockError(f"{source['id']}: existing path is not a Git worktree")
    if origin_url(path) != source["url"]:
        raise LockError(f"{source['id']}: refusing checkout with a different origin")
    if git_output(path, "rev-parse", "--show-object-format") != source["object_format"]:
        raise LockError(f"{source['id']}: refusing checkout with a different object format")
    if git_output(path, "status", "--porcelain=v1", "--untracked-files=normal"):
        raise LockError(f"{source['id']}: refusing to modify a dirty checkout")
    head = git(path, "rev-parse", "--verify", "HEAD", check=False)
    if head.returncode == 0:
        if head.stdout.strip() != source["commit"]:
            raise LockError(f"{source['id']}: refusing to replace an unexpected HEAD")
        if git(path, "symbolic-ref", "-q", "HEAD", check=False).returncode == 0:
            raise LockError(f"{source['id']}: expected a detached HEAD")
    return path, head.returncode == 0


def sync_source(
    root: Path, source: dict[str, Any], *, offline: bool
) -> dict[str, Any]:
    path, has_head = preflight_existing(root, source)
    created = False
    if not path.exists():
        if offline:
            raise LockError(f"{source['id']}: checkout is missing in offline mode")
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "init", "--quiet", "--object-format=sha1", str(path)],
            check=True,
            capture_output=True,
            text=True,
        )
        git(path, "remote", "add", "origin", source["url"])
        created = True

    if offline:
        if git(path, "cat-file", "-e", f"{source['commit']}^{{commit}}", check=False).returncode:
            raise LockError(f"{source['id']}: locked commit is unavailable offline")
    else:
        branch_target = f"{PROJECT_REF_PREFIX}/{source['id']}/branch"
        release_target = f"{PROJECT_REF_PREFIX}/{source['id']}/release"
        git(
            path,
            "fetch",
            "--no-tags",
            "origin",
            f"+{source['branch_ref']}:{branch_target}",
            f"+{source['release_ref']}:{release_target}",
        )
        release_commit = git_output(path, "rev-parse", f"{release_target}^{{commit}}")
        if release_commit != source["commit"]:
            raise LockError(
                f"{source['id']}: release ref resolves to {release_commit}, "
                f"not {source['commit']}"
            )
        if git(
            path,
            "merge-base",
            "--is-ancestor",
            source["commit"],
            branch_target,
            check=False,
        ).returncode:
            raise LockError(
                f"{source['id']}: locked commit is not on {source['branch_ref']}"
            )

    if not has_head:
        git(path, "checkout", "--quiet", "--detach", source["commit"])
    result = inspect_source(root, source)
    if result["state"] != "ready":
        raise LockError(f"{source['id']}: " + "; ".join(result["errors"]))
    result["created"] = created
    return result


def status_result(
    root: Path, data: dict[str, Any], digest: str, *, offline: bool | None = None
) -> dict[str, Any]:
    sources = [inspect_source(root, source) for source in data["sources"]]
    result: dict[str, Any] = {
        "schema_version": data["schema_version"],
        "lock_sha256": digest,
        "release": data["release"],
        "ok": all(source["state"] == "ready" for source in sources),
        "sources": sources,
    }
    if offline is not None:
        result["offline"] = offline
    return result


def sync_result(
    root: Path, data: dict[str, Any], digest: str, *, offline: bool
) -> dict[str, Any]:
    sources = [sync_source(root, source, offline=offline) for source in data["sources"]]
    return {
        "schema_version": data["schema_version"],
        "lock_sha256": digest,
        "release": data["release"],
        "offline": offline,
        "ok": True,
        "sources": sources,
    }


def print_result(result: dict[str, Any], output_format: str, action: str) -> None:
    if output_format == "json":
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return
    if action == "validate":
        print(f"source-lock: PASS ({result['lock_sha256']})")
        return
    for source in result["sources"]:
        actual = source.get("actual_commit") or "-"
        print(f"{source['id']}: {source['state']} {actual}")
        for error in source.get("errors", []):
            print(f"  {error}", file=sys.stderr)
    print(f"source-lock: {'PASS' if result['ok'] else 'FAIL'}")


def get_field(data: dict[str, Any], dotted: str) -> Any:
    value: Any = data
    for part in dotted.split("."):
        if not isinstance(value, dict) or part not in value:
            raise LockError(f"unknown lock field: {dotted}")
        value = value[part]
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="repository root")
    parser.add_argument("--lock", default=DEFAULT_LOCK, help="lock path under repository")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate", help="validate the lock schema without Git access")
    subparsers.add_parser("status", help="verify existing source checkouts without fetching")
    sync_parser = subparsers.add_parser("sync", help="materialize the locked source checkouts")
    sync_parser.add_argument("--offline", action="store_true", help="forbid network fetches")
    get_parser = subparsers.add_parser("get", help="print a validated lock field")
    get_parser.add_argument("field", help="dot-separated object field")
    get_parser.add_argument("--lines", action="store_true", help="print list items one per line")
    args = parser.parse_args()

    root = Path(args.repo).resolve()
    try:
        lock_path = locked_path(root, args.lock)
        data, digest = read_lock(lock_path)
        if args.command == "validate":
            print_result(
                {"schema_version": SCHEMA_VERSION, "lock_sha256": digest, "ok": True},
                args.format,
                "validate",
            )
            return 0
        if args.command == "status":
            result = status_result(root, data, digest)
            print_result(result, args.format, "status")
            return 0 if result["ok"] else 1
        if args.command == "sync":
            result = sync_result(root, data, digest, offline=args.offline)
            print_result(result, args.format, "sync")
            return 0
        value = get_field(data, args.field)
        if args.lines:
            if not isinstance(value, list):
                raise LockError(f"{args.field} is not an array")
            for item in value:
                if not isinstance(item, str):
                    raise LockError(f"{args.field} contains a non-string value")
                print(item)
            return 0
        if not isinstance(value, (str, int)) or isinstance(value, bool):
            raise LockError(f"{args.field} is not a scalar field")
        print(value)
        return 0
    except (LockError, OSError, subprocess.SubprocessError) as exc:
        if args.format == "json":
            print(
                json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
                file=sys.stderr,
            )
        else:
            print(f"source-lock: FAIL: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
