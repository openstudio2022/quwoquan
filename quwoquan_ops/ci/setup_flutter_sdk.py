#!/usr/bin/env python3
"""Resolve and install an official Flutter SDK without an unpinned nested Action."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Any, Mapping


MANIFEST_BASE_URL = "https://storage.googleapis.com/flutter_infra_release/releases"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
OS_NAMES = {"linux": "linux", "Linux": "linux"}
ARCH_NAMES = {"x64": "x64", "X64": "x64", "amd64": "x64", "AMD64": "x64"}


def _download_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "quwoquan-ci/1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def select_current_release(
    manifest: Mapping[str, Any], *, channel: str, architecture: str
) -> dict[str, str]:
    current_release = manifest.get("current_release")
    releases = manifest.get("releases")
    if not isinstance(current_release, Mapping) or not isinstance(releases, list):
        raise ValueError("Flutter release manifest is missing current_release/releases")
    release_hash = str(current_release.get(channel, "")).strip()
    if not release_hash:
        raise ValueError(f"Flutter release manifest has no current {channel} hash")

    selected: Mapping[str, Any] | None = None
    for candidate in releases:
        if not isinstance(candidate, Mapping) or candidate.get("hash") != release_hash:
            continue
        candidate_arch = str(candidate.get("dart_sdk_arch") or "x64")
        if candidate_arch == architecture:
            selected = candidate
            break
    if selected is None:
        raise ValueError(
            f"Flutter release {release_hash} has no archive for architecture {architecture}"
        )

    archive = str(selected.get("archive", "")).strip()
    checksum = str(selected.get("sha256", "")).strip().lower()
    version = str(selected.get("version", "")).strip()
    archive_path = PurePosixPath(archive)
    if not archive or archive_path.is_absolute() or ".." in archive_path.parts:
        raise ValueError("Flutter release archive must be a safe relative path")
    if not SHA256_RE.fullmatch(checksum):
        raise ValueError("Flutter release archive has no canonical sha256")
    if not version:
        raise ValueError("Flutter release archive has no version")
    return {
        "archive": archive,
        "hash": release_hash,
        "sha256": checksum,
        "version": version,
    }


def _append_lines(path_value: str | None, lines: list[str]) -> None:
    if not path_value:
        return
    with Path(path_value).open("a", encoding="utf-8") as handle:
        for line in lines:
            handle.write(f"{line}\n")


def resolve(args: argparse.Namespace) -> int:
    runner_os = OS_NAMES.get(args.os)
    architecture = ARCH_NAMES.get(args.architecture)
    if runner_os is None or architecture is None:
        raise ValueError(
            f"unsupported Flutter CI runner: os={args.os!r} arch={args.architecture!r}"
        )
    manifest_url = f"{MANIFEST_BASE_URL}/releases_{runner_os}.json"
    release = select_current_release(
        _download_json(manifest_url), channel=args.channel, architecture=architecture
    )
    tool_cache = Path(args.tool_cache).resolve()
    cache_path = tool_cache / "quwoquan-flutter" / f"{release['hash']}-{architecture}"
    outputs = {
        "archive_url": f"{MANIFEST_BASE_URL}/{release['archive']}",
        "cache_path": str(cache_path),
        "sha256": release["sha256"],
        "version": release["version"],
    }
    _append_lines(args.github_output, [f"{key}={value}" for key, value in outputs.items()])
    print(
        f"Resolved Flutter {release['version']} ({architecture}) "
        f"with sha256={release['sha256']}"
    )
    return 0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def install(args: argparse.Namespace) -> int:
    if not SHA256_RE.fullmatch(args.sha256):
        raise ValueError("--sha256 must be 64 lowercase hexadecimal characters")
    if not args.archive_url.startswith(f"{MANIFEST_BASE_URL}/"):
        raise ValueError("--archive-url must use the official Flutter release origin")
    cache_path = Path(args.cache_path).resolve()
    tool_cache = Path(args.tool_cache).resolve()
    if cache_path != tool_cache and tool_cache not in cache_path.parents:
        raise ValueError("--cache-path must stay inside RUNNER_TOOL_CACHE")
    flutter_root = cache_path / "flutter"
    flutter_binary = flutter_root / "bin" / "flutter"

    if not flutter_binary.is_file():
        cache_path.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="quwoquan-flutter-", dir=args.runner_temp) as temp:
            archive = Path(temp) / "flutter-sdk.tar.xz"
            request = urllib.request.Request(
                args.archive_url, headers={"User-Agent": "quwoquan-ci/1"}
            )
            print(f"Downloading verified Flutter SDK from {args.archive_url}")
            with urllib.request.urlopen(request, timeout=60) as response, archive.open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
            actual_sha256 = _sha256(archive)
            if actual_sha256 != args.sha256:
                raise ValueError(
                    f"Flutter SDK checksum mismatch: expected {args.sha256}, got {actual_sha256}"
                )
            subprocess.run(["tar", "xf", str(archive), "-C", str(cache_path)], check=True)
        if not flutter_binary.is_file():
            raise ValueError("verified Flutter archive did not contain flutter/bin/flutter")

    pub_cache = Path(os.environ.get("PUB_CACHE", str(Path.home() / ".pub-cache"))).resolve()
    _append_lines(
        args.github_env,
        [f"FLUTTER_ROOT={flutter_root}", f"PUB_CACHE={pub_cache}"],
    )
    _append_lines(
        args.github_path,
        [str(flutter_root / "bin"), str(flutter_root / "bin" / "cache" / "dart-sdk" / "bin"), str(pub_cache / "bin")],
    )
    print(f"Flutter SDK ready at {flutter_root}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    resolve_parser = subparsers.add_parser("resolve")
    resolve_parser.add_argument("--channel", default="stable")
    resolve_parser.add_argument("--os", default=os.environ.get("RUNNER_OS", sys.platform))
    resolve_parser.add_argument(
        "--architecture", default=os.environ.get("RUNNER_ARCH", "x64")
    )
    resolve_parser.add_argument(
        "--tool-cache", default=os.environ.get("RUNNER_TOOL_CACHE", "")
    )
    resolve_parser.add_argument("--github-output", default=os.environ.get("GITHUB_OUTPUT"))
    resolve_parser.set_defaults(func=resolve)

    install_parser = subparsers.add_parser("install")
    install_parser.add_argument("--archive-url", required=True)
    install_parser.add_argument("--cache-path", required=True)
    install_parser.add_argument("--sha256", required=True)
    install_parser.add_argument(
        "--tool-cache", default=os.environ.get("RUNNER_TOOL_CACHE", "")
    )
    install_parser.add_argument(
        "--runner-temp", default=os.environ.get("RUNNER_TEMP", tempfile.gettempdir())
    )
    install_parser.add_argument("--github-env", default=os.environ.get("GITHUB_ENV"))
    install_parser.add_argument("--github-path", default=os.environ.get("GITHUB_PATH"))
    install_parser.set_defaults(func=install)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.tool_cache:
        raise ValueError("RUNNER_TOOL_CACHE is required")
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
