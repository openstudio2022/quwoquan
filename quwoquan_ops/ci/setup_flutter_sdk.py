#!/usr/bin/env python3
"""Resolve and install a checksum-bound repository-pinned Flutter SDK."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

MANIFEST_BASE_URL = "https://storage.googleapis.com/flutter_infra_release/releases"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MANIFEST_ATTEMPTS = 4
_MANIFEST_RETRY_BASE_SECONDS = 2
OS_NAMES = {
    "linux": "linux",
    "Linux": "linux",
    "macos": "macos",
    "macOS": "macos",
    "Darwin": "macos",
}
ARCH_NAMES = {
    "x64": "x64",
    "X64": "x64",
    "amd64": "x64",
    "AMD64": "x64",
    "arm64": "arm64",
    "ARM64": "arm64",
    "aarch64": "arm64",
}


def _download_json(url: str) -> dict[str, Any]:
    """取 release manifest；只对传输层瞬时故障退避重试。

    self-hosted runner 到 Flutter 镜像会出现 TLS 半连接被对端切断
    (`SSLEOFError`)。manifest 是纯读取且后续仍按 sha256 校验归档，重试不放松
    任何完整性约束；解析失败与 HTTP 状态错误不重试，那是确定性失败。
    """

    request = urllib.request.Request(url, headers={"User-Agent": "quwoquan-ci/1"})
    last_error: OSError | None = None
    for attempt in range(_MANIFEST_ATTEMPTS):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError:
            raise
        except (urllib.error.URLError, ssl.SSLError, TimeoutError) as error:
            last_error = error
            if attempt + 1 == _MANIFEST_ATTEMPTS:
                break
            delay = _MANIFEST_RETRY_BASE_SECONDS * (2**attempt)
            print(
                f"Flutter release manifest attempt {attempt + 1}/"
                f"{_MANIFEST_ATTEMPTS} failed ({error}); retrying in {delay}s",
                file=sys.stderr,
            )
            time.sleep(delay)
    raise RuntimeError(
        f"Flutter release manifest is unreachable after {_MANIFEST_ATTEMPTS} "
        f"attempts: {last_error}"
    )


def select_current_release(
    manifest: Mapping[str, Any],
    *,
    channel: str,
    architecture: str,
    version: str = "",
) -> dict[str, str]:
    current_release = manifest.get("current_release")
    releases = manifest.get("releases")
    if not isinstance(current_release, Mapping) or not isinstance(releases, list):
        raise TypeError("Flutter release manifest is missing current_release/releases")
    requested_version = version.strip()
    current_hash = str(current_release.get(channel, "")).strip()
    if not requested_version and not current_hash:
        raise ValueError(f"Flutter release manifest has no current {channel} hash")

    selected: Mapping[str, Any] | None = None
    for candidate in releases:
        if not isinstance(candidate, Mapping):
            continue
        candidate_arch = str(candidate.get("dart_sdk_arch") or "x64")
        candidate_channel = str(candidate.get("channel") or channel)
        if candidate_arch != architecture or candidate_channel != channel:
            continue
        if requested_version:
            if str(candidate.get("version") or "").strip() != requested_version:
                continue
        elif candidate.get("hash") != current_hash:
            continue
        selected = candidate
        break
    if selected is None:
        identity = f"version {requested_version}" if requested_version else current_hash
        raise ValueError(
            f"Flutter release {identity} has no {channel} archive for {architecture}"
        )

    archive = str(selected.get("archive", "")).strip()
    checksum = str(selected.get("sha256", "")).strip().lower()
    selected_version = str(selected.get("version", "")).strip()
    release_hash = str(selected.get("hash", "")).strip()
    archive_path = PurePosixPath(archive)
    if not archive or archive_path.is_absolute() or ".." in archive_path.parts:
        raise ValueError("Flutter release archive must be a safe relative path")
    if not SHA256_RE.fullmatch(checksum):
        raise ValueError("Flutter release archive has no canonical sha256")
    if not selected_version or not release_hash:
        raise ValueError("Flutter release archive has no version/hash")
    return {
        "archive": archive,
        "hash": release_hash,
        "sha256": checksum,
        "version": selected_version,
    }


def _append_lines(path_value: str | None, lines: list[str]) -> None:
    if not path_value:
        return
    with Path(path_value).open("a", encoding="utf-8") as handle:
        handle.writelines(f"{line}\n" for line in lines)


def _read_version(path_value: str) -> str:
    version = Path(path_value).read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise ValueError("Flutter version file must contain one exact semver")
    return version


def resolve(args: argparse.Namespace) -> int:
    runner_os = OS_NAMES.get(args.os)
    architecture = ARCH_NAMES.get(args.architecture)
    if runner_os is None or architecture is None:
        raise ValueError(
            f"unsupported Flutter CI runner: os={args.os!r} arch={args.architecture!r}"
        )
    version = _read_version(args.version_file)
    manifest_url = f"{MANIFEST_BASE_URL}/releases_{runner_os}.json"
    release = select_current_release(
        _download_json(manifest_url),
        channel=args.channel,
        architecture=architecture,
        version=version,
    )
    tool_cache = Path(args.tool_cache).resolve()
    cache_path = tool_cache / "quwoquan-flutter" / f"{release['hash']}-{architecture}"
    outputs = {
        "archive_url": f"{MANIFEST_BASE_URL}/{release['archive']}",
        "cache_path": str(cache_path),
        "sha256": release["sha256"],
        "version": release["version"],
    }
    _append_lines(
        args.github_output, [f"{key}={value}" for key, value in outputs.items()]
    )
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
        with tempfile.TemporaryDirectory(
            prefix="quwoquan-flutter-", dir=args.runner_temp
        ) as temp:
            archive = Path(temp) / "flutter-sdk.tar.xz"
            request = urllib.request.Request(
                args.archive_url, headers={"User-Agent": "quwoquan-ci/1"}
            )
            print(f"Downloading verified Flutter SDK from {args.archive_url}")
            with (
                urllib.request.urlopen(request, timeout=60) as response,
                archive.open("wb") as output,
            ):
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
            actual_sha256 = _sha256(archive)
            if actual_sha256 != args.sha256:
                raise ValueError(
                    "Flutter SDK checksum mismatch: "
                    f"expected {args.sha256}, got {actual_sha256}"
                )
            subprocess.run(
                ["tar", "xf", str(archive), "-C", str(cache_path)], check=True
            )
        if not flutter_binary.is_file():
            raise ValueError(
                "verified Flutter archive did not contain flutter/bin/flutter"
            )

    pub_cache = Path(
        os.environ.get("PUB_CACHE", str(Path.home() / ".pub-cache"))
    ).resolve()
    _append_lines(
        args.github_env,
        [f"FLUTTER_ROOT={flutter_root}", f"PUB_CACHE={pub_cache}"],
    )
    _append_lines(
        args.github_path,
        [
            str(flutter_root / "bin"),
            str(flutter_root / "bin" / "cache" / "dart-sdk" / "bin"),
            str(pub_cache / "bin"),
        ],
    )
    print(f"Flutter SDK ready at {flutter_root}")
    return 0


def _gradle_wrapper_tools() -> tuple[Any, Any, Any, Any]:
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from quwoquan_app.scripts.tools.flutter_facade.flutter_facade import (
        FacadeError,
        resolved_flutter_identity,
    )
    from quwoquan_ops.cli.lib.package_reuse.android_gradle_store import (
        canonical_android_uat_gradle_invocations,
        materialize_pinned_flutter_gradle_wrappers,
    )

    return (
        FacadeError,
        resolved_flutter_identity,
        canonical_android_uat_gradle_invocations,
        materialize_pinned_flutter_gradle_wrappers,
    )


def materialize_gradle_wrappers(args: argparse.Namespace) -> int:
    project_root = Path(args.project_root).expanduser().resolve(strict=True)
    (
        facade_error,
        resolve_flutter_identity,
        gradle_invocations,
        materialize_wrappers,
    ) = _gradle_wrapper_tools()
    try:
        flutter_identity = resolve_flutter_identity(dict(os.environ))
    except facade_error as error:
        raise ValueError(f"App CI Flutter identity is invalid: {error}") from error
    invocations = gradle_invocations(project_root)
    identities = materialize_wrappers(
        project_root,
        [invocation.gradle_root for invocation in invocations],
        flutter_identity,
    )
    print(f"Materialized {len(identities)} pinned Flutter Gradle wrappers")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    resolve_parser = subparsers.add_parser("resolve")
    resolve_parser.add_argument("--channel", default="stable")
    resolve_parser.add_argument(
        "--os", default=os.environ.get("RUNNER_OS", sys.platform)
    )
    resolve_parser.add_argument(
        "--architecture", default=os.environ.get("RUNNER_ARCH", "x64")
    )
    resolve_parser.add_argument(
        "--tool-cache", default=os.environ.get("RUNNER_TOOL_CACHE", "")
    )
    resolve_parser.add_argument(
        "--version-file", default="quwoquan_app/.flutter-version"
    )
    resolve_parser.add_argument(
        "--github-output", default=os.environ.get("GITHUB_OUTPUT")
    )
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

    wrappers_parser = subparsers.add_parser("materialize-gradle-wrappers")
    wrappers_parser.add_argument("--project-root", default=str(REPO_ROOT))
    wrappers_parser.set_defaults(func=materialize_gradle_wrappers)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command in {"resolve", "install"} and not args.tool_cache:
        raise ValueError("RUNNER_TOOL_CACHE is required")
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
