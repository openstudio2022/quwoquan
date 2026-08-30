from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

from quwoquan_ops.cli.commands.package_app_artifact_helpers import artifact_digest
from quwoquan_ops.cli.lib.app_launch_manifest_contract import (
    load_launch_manifest_contract,
    runtime_config_package_digest,
    runtime_config_trust_envelope_digest,
    validate_runtime_config_package,
    validate_runtime_config_trust_envelope,
)

ACTIVE_POINTER_NAME = "active.json"
ACTIVE_POINTER_SCHEMA = "client-app.web.active-release"
WEB_RUNTIME_CONFIG_FILENAMES = (
    "runtime-config-trust.json",
    "runtime-config-package.json",
)


class WebOfficialReleaseError(RuntimeError):
    pass


def package_web_official_release(
    *,
    repo_root: Path,
    environment: str,
    target: str,
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

    package_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="web-build-",
        dir=str(package_root),
    ) as temporary:
        build_root = Path(temporary) / "public"
        command = _web_build_command(flutter, build_root)
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
        validate_web_official_artifact(build_root)
        digest = web_official_content_digest(build_root)
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
        "assetCacheControl": "no-cache, must-revalidate",
        "serviceWorker": "flutter_service_worker.js",
    }
    manifest_path = release_root / "manifest.json"
    manifest_bytes = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    manifest_path.write_bytes(manifest_bytes)
    manifest_sha256 = "sha256:" + hashlib.sha256(manifest_bytes).hexdigest()

    # exact 指针是身份真相源：它固定 releaseId、内容摘要与 manifest 摘要三者，
    # 消费方据此绑定唯一 immutable release。
    active_path = package_root / ACTIVE_POINTER_NAME
    active_path.write_text(
        json.dumps(
            {
                "schema": ACTIVE_POINTER_SCHEMA,
                "environment": environment,
                "publicOrigin": public_origin,
                "releaseId": release_id,
                "contentSHA256": digest,
                "manifestSHA256": manifest_sha256,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    # current 只是 exact 指针的兼容投影，保留给尚未迁移的挂载与脚本。
    current = package_root / "current"
    if current.is_symlink() or current.is_file():
        current.unlink()
    elif current.exists():
        shutil.rmtree(current)
    current.symlink_to(release_root.name, target_is_directory=True)
    return {
        **manifest,
        "manifestPath": str(manifest_path),
        "manifestSHA256": manifest_sha256,
        "releasePath": str(release_root),
        "activePath": str(active_path),
        "currentPath": str(current),
    }


def _web_build_command(flutter: str, build_root: Path) -> list[str]:
    return [
        flutter,
        "build",
        "web",
        "--release",
        "--pwa-strategy=offline-first",
        f"--output={build_root}",
    ]


def _trusted_web_origin(environment: str, raw: str) -> str:
    value = raw.strip().rstrip("/")
    parsed = urlparse(value)
    expected = {
        "alpha": ("alpha.quwoquan.com", 17000),
        "beta": ("beta.quwoquan.com", 18000),
        "gamma": ("gamma.quwoquan.com", 19000),
        "prod": ("quwoquan.com", None),
    }[environment]
    expected_host, expected_port = expected
    try:
        parsed_port = parsed.port
    except ValueError as error:
        raise WebOfficialReleaseError(
            f"{environment} Web origin must be "
            f"https://{expected_host}{f':{expected_port}' if expected_port else ''}"
        ) from error
    if (
        parsed.scheme != "https"
        or parsed.hostname != expected_host
        or parsed_port != expected_port
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise WebOfficialReleaseError(
            f"{environment} Web origin must be "
            f"https://{expected_host}{f':{expected_port}' if expected_port else ''}"
        )
    return f"https://{expected_host}{f':{expected_port}' if expected_port else ''}"


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
    # 引擎前 bootstrap surface 产物（DEC-005）必须随包交付。
    bootstrap_missing = [
        name
        for name in ("qwq_bootstrap.css", "qwq_bootstrap.js")
        if not (build_root / name).is_file()
    ]
    if bootstrap_missing:
        raise WebOfficialReleaseError(
            "Web build is missing bootstrap surface assets: "
            + ", ".join(bootstrap_missing)
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
    _verify_font_manifest(build_root)


def _verify_runtime_config_is_external(build_root: Path) -> None:
    embedded = [
        name for name in WEB_RUNTIME_CONFIG_FILENAMES if (build_root / name).exists()
    ]
    if embedded:
        raise WebOfficialReleaseError(
            "Web shared artifact must not contain hosting runtime configuration: "
            + ", ".join(embedded)
        )


def validate_web_official_artifact(existing_dir: Path) -> None:
    """Validate one existing immutable Web directory before release minting."""

    if existing_dir.is_symlink() or not existing_dir.is_dir():
        raise WebOfficialReleaseError(
            "Web official artifact must be an existing regular directory"
        )
    _verify_web_build(existing_dir)
    _verify_runtime_config_is_external(existing_dir)


def web_official_content_digest(existing_dir: Path) -> str:
    """Return the canonical unprefixed content identity used by Web deploy."""

    return artifact_digest(existing_dir).removeprefix("sha256:")


def materialize_web_runtime_config(
    *,
    hosting_root: Path,
    trust_envelope: dict[str, object],
    runtime_package: dict[str, object],
    expected_environment: str,
    expected_target: str,
) -> dict[str, str]:
    """将环境配置写入 hosting composition，而非 immutable Web artifact。"""

    if expected_environment not in {"alpha", "beta", "gamma", "prod"}:
        raise WebOfficialReleaseError(
            f"unsupported Web hosting environment: {expected_environment}"
        )
    if hosting_root.is_symlink() or not hosting_root.is_dir():
        raise WebOfficialReleaseError(
            "Web hosting root must be an existing regular directory"
        )
    expected_profile = "prod" if expected_environment == "prod" else "nonprod"
    contract = load_launch_manifest_contract()
    trust_issues = validate_runtime_config_trust_envelope(
        trust_envelope,  # type: ignore[arg-type]
        contract,
    )
    if trust_issues or trust_envelope.get("buildProfile") != expected_profile:
        detail = "; ".join(trust_issues) or "buildProfile does not match environment"
        raise WebOfficialReleaseError(
            "Web hosting runtime trust envelope is missing or invalid: " + detail
        )
    package_issues = validate_runtime_config_package(
        runtime_package,  # type: ignore[arg-type]
        trust_envelope,  # type: ignore[arg-type]
        contract,
    )
    if (
        package_issues
        or runtime_package.get("environment") != expected_environment
        or runtime_package.get("target") != expected_target
        or runtime_package.get("buildProfile") != expected_profile
    ):
        detail = "; ".join(package_issues) or "target/environment/profile mismatch"
        raise WebOfficialReleaseError(
            "Web hosting runtime package does not match its composition: " + detail
        )

    payloads = {
        "runtime-config-trust.json": trust_envelope,
        "runtime-config-package.json": runtime_package,
    }
    file_digests: dict[str, str] = {}
    for name, payload in payloads.items():
        encoded = (
            json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
        destination = hosting_root / name
        temporary = hosting_root / f".{name}.tmp"
        temporary.write_bytes(encoded)
        os.replace(temporary, destination)
        file_digests[name] = "sha256:" + hashlib.sha256(encoded).hexdigest()
    return {
        **file_digests,
        "runtimeConfigTrustEnvelopeDigest": runtime_config_trust_envelope_digest(
            trust_envelope,  # type: ignore[arg-type]
            contract,
        ),
        "runtimeConfigPackageDigest": runtime_config_package_digest(
            runtime_package,  # type: ignore[arg-type]
            contract,
        ),
    }


def _verify_font_manifest(build_root: Path) -> None:
    # 静态服务器会先对请求 URL 做百分号解码再查磁盘，因此字体 asset 路径必须
    # 全程 URL-safe：解码后指向产物内唯一的常规文件，且不含需要编码的字符
    # （方括号、空格等），否则线上 404、中文渲染成 tofu。
    manifest_path = build_root / "assets" / "FontManifest.json"
    if not manifest_path.is_file():
        raise WebOfficialReleaseError("Web build is missing assets/FontManifest.json")
    families = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(families, list) or not families:
        raise WebOfficialReleaseError(
            "Web FontManifest.json must be a non-empty JSON array"
        )
    problems: list[str] = []
    for family in families:
        if not isinstance(family, dict):
            problems.append("font family entry is not an object")
            continue
        fonts = family.get("fonts")
        if not isinstance(fonts, list) or not fonts:
            problems.append(f"font family {family.get('family')!r} declares no fonts")
            continue
        for font in fonts:
            asset = str(font.get("asset", "")).strip() if isinstance(font, dict) else ""
            if not asset:
                problems.append(
                    f"font family {family.get('family')!r} has an empty asset URL"
                )
                continue
            decoded = unquote(asset)
            if quote(decoded, safe="/") != decoded:
                problems.append(f"font asset needs URL encoding: {asset}")
                continue
            target = build_root / "assets" / decoded
            if not target.is_file():
                problems.append(f"font asset file is missing: {asset}")
                continue
            if decoded != asset and (build_root / "assets" / asset).exists():
                problems.append(f"font asset URL maps to more than one file: {asset}")
    if problems:
        raise WebOfficialReleaseError(
            "Web font assets are not URL-safe: " + "; ".join(problems)
        )


def _tree_sha256(root: Path) -> str:
    """Compatibility projection of the canonical Web content identity."""

    return web_official_content_digest(root)
