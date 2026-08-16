from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse


class WebOfficialReleaseError(RuntimeError):
    pass


def package_web_official_release(
    *,
    repo_root: Path,
    environment: str,
    package_root: Path,
    public_origin: str,
) -> dict[str, object]:
    environment = environment.strip()
    if environment not in {"alpha", "beta", "gamma", "prod"}:
        raise WebOfficialReleaseError(f"unsupported Web environment: {environment}")
    public_origin = _trusted_web_origin(environment, public_origin)
    flutter = shutil.which("flutter")
    if not flutter:
        raise WebOfficialReleaseError("flutter is required to package the Web application")

    defines = _runtime_defines(repo_root, environment)
    defines["CLOUD_GATEWAY_BASE_URL"] = public_origin + "/api"
    defines["APP_LEGAL_BASE_URL"] = public_origin + "/legal"
    defines["PUBLIC_WEB_BASE_URL"] = public_origin
    package_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="web-build-",
        dir=str(package_root),
    ) as temporary:
        build_root = Path(temporary) / "public"
        command = [
            flutter,
            "build",
            "web",
            "--release",
            "--pwa-strategy=offline-first",
            f"--output={build_root}",
        ]
        command.extend(
            f"--dart-define={key}={value}"
            for key, value in sorted(defines.items())
        )
        result = subprocess.run(
            command,
            cwd=repo_root / "quwoquan_app",
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, "LC_ALL": "C.UTF-8"},
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise WebOfficialReleaseError(f"flutter build web failed: {detail}")
        _verify_web_build(build_root)
        if environment != "prod":
            _inject_noindex(build_root / "index.html")
        digest = _tree_sha256(build_root)
        release_id = digest[:20]
        release_root = package_root / release_id
        if release_root.exists():
            shutil.rmtree(release_root)
        shutil.copytree(build_root, release_root / "public")

    manifest = {
        "schema": "client-app.web.official-release",
        "environment": environment,
        "publicOrigin": public_origin,
        "releaseId": release_id,
        "contentSHA256": digest,
        "noindex": environment != "prod",
        "spaFallback": "/index.html",
        "htmlContentType": "text/html; charset=utf-8",
        "assetCacheControl": "public, max-age=31536000, immutable",
        "serviceWorker": "flutter_service_worker.js",
    }
    manifest_path = release_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    current = package_root / "current"
    if current.is_symlink() or current.is_file():
        current.unlink()
    elif current.exists():
        shutil.rmtree(current)
    current.symlink_to(release_root.name, target_is_directory=True)
    return {
        **manifest,
        "manifestPath": str(manifest_path),
        "releasePath": str(release_root),
        "currentPath": str(current),
    }


def _runtime_defines(repo_root: Path, environment: str) -> dict[str, str]:
    command = [
        "python3",
        str(repo_root / "quwoquan_app/scripts/env/print_app_env_dart_defines.py"),
        "--env",
        environment,
        "--format",
        "json",
    ]
    result = subprocess.run(
        command,
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise WebOfficialReleaseError(
            "read Web runtime package failed: " + (result.stderr or result.stdout).strip()
        )
    decoded = json.loads(result.stdout)
    if not isinstance(decoded, dict):
        raise WebOfficialReleaseError("Web runtime defines must be a JSON object")
    return {str(key): str(value) for key, value in decoded.items()}


def _trusted_web_origin(environment: str, raw: str) -> str:
    value = raw.strip().rstrip("/")
    parsed = urlparse(value)
    expected = {
        "alpha": "alpha.quwoquan.com",
        "beta": "beta.quwoquan.com",
        "gamma": "gamma.quwoquan.com",
        "prod": "quwoquan.com",
    }[environment]
    try:
        parsed.port
    except ValueError as error:
        raise WebOfficialReleaseError(
            f"{environment} Web origin must be https://{expected}"
        ) from error
    if (
        parsed.scheme != "https"
        or parsed.hostname != expected
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise WebOfficialReleaseError(
            f"{environment} Web origin must be https://{expected}"
        )
    # Local runtime targets expose the canonical host through an isolated
    # workstation port.  A distributable Web package is host-bound, so remove
    # that transport-only port instead of persisting it as release identity.
    return f"https://{expected}"


def _verify_web_build(build_root: Path) -> None:
    required = (
        "index.html",
        "main.dart.js",
        "manifest.json",
        "flutter_service_worker.js",
    )
    missing = [name for name in required if not (build_root / name).is_file()]
    if missing:
        raise WebOfficialReleaseError(
            "Web build is incomplete: " + ", ".join(missing)
        )
    noto_sans_sc = tuple(build_root.rglob("NotoSansSC*.ttf"))
    if len(noto_sans_sc) != 1 or noto_sans_sc[0].is_symlink():
        raise WebOfficialReleaseError(
            "Web build must contain exactly one bundled Noto Sans SC font"
        )
    index = (build_root / "index.html").read_text(encoding="utf-8")
    for token in ('<html lang="zh-CN">', '<meta charset="utf-8">'):
        if token not in index:
            raise WebOfficialReleaseError(f"Web index is missing {token}")
    manifest = json.loads((build_root / "manifest.json").read_text(encoding="utf-8"))
    if (
        manifest.get("display") != "standalone"
        or manifest.get("start_url") != "/"
        or manifest.get("scope") != "/"
    ):
        raise WebOfficialReleaseError("Web manifest is not an installable root PWA")


def _inject_noindex(index_path: Path) -> None:
    text = index_path.read_text(encoding="utf-8")
    marker = '  <meta name="description"'
    if marker not in text:
        raise WebOfficialReleaseError("Web index description marker is unavailable")
    text = text.replace(
        marker,
        '  <meta name="robots" content="noindex,nofollow">\n' + marker,
        1,
    )
    index_path.write_text(text, encoding="utf-8")


def _tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()
