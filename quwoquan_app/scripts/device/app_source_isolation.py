"""构建前 source closure 审计与 fresh Alpha/在线 App 输入投影；不拥有启动协议。

spec_ref: runtime/runtime-config/environment-topology-and-packaging/spec.md#GWT-007
投影只证明输入字节隔离，不代替 snapshot 验签、native/linker 或最终制品验证。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys

sys.dont_write_bytecode = True

from pathlib import Path
import re
import shutil
from typing import Any

import yaml

# 保留字符串 token，避免 URL 中的 // 被误删；conditional URI 全部进入闭包。
_TOKENS = re.compile(r"/\*[\s\S]*?\*/|//[^\n]*|(?:r)?(?:\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*')|[A-Za-z_$][\w$]*|[^\s]", re.MULTILINE)
_TEST_PATH = re.compile(r"(^|/)(test|tests|test_host|test_fixtures|fixtures?|mocks?|patrol|integration_test|runners)(/|$)|(^|[/_.-])(fixtures?|mocks?|patrol|integration_test)([/_.-]|$)", re.I)
_ALPHA_PATH = re.compile(r"(^|[/_.-])(alpha|bundled|offline_content_bundle)([/_.-]|$)", re.I)
_TEST_CODE = re.compile(r"\b(?:class|mixin|typedef)\s+(?:Mock|Fake|Fixture)[A-Z]\w*|package:(?:flutter_test|integration_test|patrol|mockito|mocktail)/")
_ALPHA_ASSETS = ("assets/content/alpha/manifest.json", "assets/content/alpha/bundle_identity.json", "assets/content/alpha/media/")


class SourceIsolationError(ValueError):
    """隔离闭包不完整；不签发 production 纯度成功。"""


def _fail(detail: str) -> None:
    raise SourceIsolationError("APP.PACKAGE.production_test_dependency_leak: " + detail)


def _tokens(text: str) -> list[str]:
    return [token for token in _TOKENS.findall(text) if not token.startswith(("//", "/*"))]


def _uris(tokens: list[str]) -> list[str]:
    result = []
    for index, token in enumerate(tokens):
        if token not in {"import", "export", "part"}:
            continue
        following = tokens[index + 1:index + 2]
        if not following or not following[0].lstrip("r").startswith(("'", '"')):
            continue
        for value in tokens[index + 1:]:
            if value == ";":
                break
            literal = value[1:] if value.startswith("r") else value
            if literal.startswith(("'", '"')):
                uri = literal[1:-1]
                if "\\" in uri or "$" in uri:
                    _fail("non-literal dependency URI")
                result.append(uri)
    return result


def _regular(path: Path, boundary: Path) -> Path:
    if not path.absolute().is_relative_to(boundary):
        _fail(f"source escape: {path}")
    current = path
    while current != boundary:
        if current.is_symlink():
            _fail(f"source symlink: {path}")
        current = current.parent
    resolved = path.resolve()
    if not resolved.is_relative_to(boundary) or not resolved.is_file():
        _fail(f"source missing or escape: {path}")
    return resolved


def _manifest(root: Path, boundary: Path, alpha: bool) -> dict[str, Any]:
    path = _regular(root / "pubspec.yaml", boundary)
    value = yaml.safe_load(path.read_text())
    if not isinstance(value, dict) or not isinstance(value.get("name"), str):
        _fail(f"invalid pubspec: {path}")
    flutter = value.get("flutter") or {}
    for asset in flutter.get("assets", []):
        name = asset.get("path", "") if isinstance(asset, dict) else asset
        if not isinstance(name, str) or _TEST_PATH.search(name) or (not alpha and _ALPHA_PATH.search(name)):
            _fail(f"forbidden pubspec asset: {name}")
        declared_path = root / name
        if declared_path.is_dir():
            for resource in declared_path.rglob("*"):
                relative = resource.relative_to(root).as_posix()
                if resource.is_symlink() or _TEST_PATH.search(relative) or (not alpha and _ALPHA_PATH.search(relative)):
                    _fail(f"forbidden pubspec resource: {relative}")
    for name in (value.get("dependencies") or {}):
        if _TEST_PATH.search(name) or name in {"flutter_test", "mockito", "mocktail"}:
            _fail(f"forbidden pub dependency: {name}")
    return value


def audit_source_closure(app_dir: Path, entrypoint: str, *, alpha: bool = False) -> dict[str, Any]:
    """逐边追踪第一方源码与 path package；第三方包仅记录，须另验锁定依赖图。"""
    app = app_dir.resolve()
    boundary = app.parent
    manifest = _manifest(app, boundary, alpha)
    packages: dict[str, Path] = {manifest["name"]: app}
    manifests = {app: manifest}
    external: set[str] = set()
    pending = [(app, manifest)]
    while pending:
        owner, document = pending.pop()
        dependencies = dict(document.get("dependencies") or {})
        dependencies.update(document.get("dependency_overrides") or {})
        for name, declaration in dependencies.items():
            if not isinstance(declaration, dict) or "path" not in declaration:
                continue
            raw = owner / declaration["path"]
            root = _regular(raw / "pubspec.yaml", boundary).parent
            if name in packages and packages[name] != root:
                _fail(f"ambiguous path package: {name}")
            packages[name] = root
            if root not in manifests:
                child = _manifest(root, boundary, alpha)
                if child["name"] != name:
                    _fail(f"path package identity mismatch: {name}")
                manifests[root] = child
                pending.append((root, child))
    queue = [(app / entrypoint, [entrypoint])]
    visited: set[Path] = set()
    digests: dict[str, str] = {}
    while queue:
        raw, chain = queue.pop()
        path = _regular(raw, boundary)
        if path in visited:
            continue
        visited.add(path)
        relative = Path(os.path.relpath(path, app)).as_posix()
        if _TEST_PATH.search(relative) or (not alpha and _ALPHA_PATH.search(relative)):
            _fail(" -> ".join(chain))
        encoded = path.read_bytes()
        tokens = _tokens(encoded.decode("utf-8"))
        if _TEST_CODE.search(" ".join(tokens)):
            _fail(" -> ".join(chain) + " contains test implementation")
        digests[relative] = "sha256:" + hashlib.sha256(encoded).hexdigest()
        for uri in _uris(tokens):
            if uri.startswith("dart:"):
                continue
            if uri.startswith("package:"):
                name, separator, suffix = uri[8:].partition("/")
                if not separator or _TEST_PATH.search(name) or name in {"flutter_test", "mockito", "mocktail"}:
                    _fail(" -> ".join([*chain, uri]))
                if name not in packages:
                    declared = any(name in (doc.get("dependencies") or {}) for doc in manifests.values())
                    if not declared:
                        _fail("undeclared package: " + " -> ".join([*chain, uri]))
                    external.add(name)
                    continue
                dependency = packages[name] / "lib" / suffix
            elif ":" in uri or uri.startswith("/"):
                _fail("unsupported dependency URI: " + uri)
            else:
                dependency = path.parent / uri
                owner = max((root for root in packages.values() if path.is_relative_to(root)), key=lambda root: len(root.parts))
                if not dependency.resolve().is_relative_to(owner):
                    _fail("relative source escape: " + " -> ".join([*chain, uri]))
            queue.append((dependency, [*chain, uri]))
    return {"sourceFiles": sorted(digests), "sourceDigests": digests,
            "externalPackages": sorted(external), "alpha": alpha,
            "artifactVerified": False, "thirdPartyGraphVerified": False}


def project_source_inputs(app_dir: Path, destination: Path, *, entrypoint: str, alpha: bool = False) -> dict[str, Any]:
    """生成 fresh 输入目录，不覆盖 live/既有 projection，不自选内容或改变信任。"""
    app = app_dir.resolve()
    target = destination.absolute()
    if target.exists() or target.is_symlink() or target.resolve().is_relative_to(app):
        _fail("projection must be fresh and outside source")
    report = audit_source_closure(app, entrypoint, alpha=alpha)
    if any(name.startswith("../") for name in report["sourceFiles"]):
        _fail("sibling path package requires repository-scoped capsule projection")
    # 先验证全部输入，失败不留下可被误认为完整的投影。
    files: set[Path] = set()
    for path in app.rglob("*"):
        relative = path.relative_to(app).as_posix()
        if path.is_symlink():
            _fail(f"projection source symlink: {relative}")
        if not path.is_file():
            continue
        if relative.startswith((".dart_tool/", "build/", ".git/")) or _TEST_PATH.search(relative):
            continue
        if relative.startswith("lib/") and relative not in report["sourceFiles"]:
            continue
        if not alpha and _ALPHA_PATH.search(relative):
            continue
        files.add(path)
    if alpha:
        for required in _ALPHA_ASSETS[:2]:
            _regular(app / required, app)
        media = app / _ALPHA_ASSETS[2]
        if not media.is_dir() or not any(p.is_file() for p in media.rglob("*")):
            _fail("Alpha snapshot media is missing")
    target.mkdir(parents=True)
    for path in sorted(files):
        output = target / path.relative_to(app)
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, output)
    if alpha:
        document = yaml.safe_load((target / "pubspec.yaml").read_text())
        assets = document.setdefault("flutter", {}).setdefault("assets", [])
        for asset in _ALPHA_ASSETS:
            if asset not in assets:
                assets.append(asset)
        (target / "pubspec.yaml").write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True))
    return report


def project_repository_inputs(repository: Path, destination: Path, *, entrypoint: str, _cohort: bool = False) -> dict[str, Any]:
    """保留仓库相对布局与兄弟 path packages，只复制版本控制输入及当前新增源码。"""
    repository = repository.resolve()
    destination = destination.absolute()
    if destination.exists() or destination.is_symlink() or destination.resolve().is_relative_to(repository):
        _fail("repository projection must be fresh and outside source")
    from quwoquan_ops.cli.lib.app_launch_manifest_contract import load_launch_manifest_contract
    contract = load_launch_manifest_contract()
    mapping = contract["content_source_entrypoints"]
    if entrypoint not in mapping.values():
        _fail("entrypoint is not owned by launch metadata")
    alpha = entrypoint == mapping["bundled_snapshot"]
    report = audit_source_closure(repository / "quwoquan_app", entrypoint, alpha=alpha)
    if _cohort:
        other = audit_source_closure(repository / "quwoquan_app", mapping["remote"])
        report["sourceDigests"].update(other["sourceDigests"])
        report["sourceFiles"] = sorted(report["sourceDigests"])
    tracked = subprocess.check_output(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=repository,
    ).decode().split("\0")
    paths = []
    for relative in sorted(set(filter(None, tracked))):
        if not relative.startswith(("quwoquan_app/", "quwoquan_ops/", "quwoquan_service/", "quwoquan_data/", "specs/")) and relative not in {"Makefile", "go.work", "go.work.sum"}:
            continue
        if any(part in {".dart_tool", "build", "node_modules", "__pycache__", ".pytest_cache", ".venv"} for part in Path(relative).parts):
            continue
        path = repository / relative
        if not path.exists():
            continue
        if path.is_symlink():
            # test host 的 source links 不参与 production projection。
            if relative.startswith("quwoquan_app/test_host/"):
                continue
            resolved = path.resolve()
            if not resolved.is_relative_to(repository) or not resolved.is_file():
                _fail(f"repository source symlink escape: {relative}")
            path = resolved
        if not path.is_file() or relative.startswith((".git/", ".qwq_output/")):
            continue
        if relative.startswith("quwoquan_app/lib/"):
            dart_relative = relative.removeprefix("quwoquan_app/")
            if path.suffix == ".dart" and dart_relative not in report["sourceFiles"]:
                continue
        if relative.startswith("quwoquan_app/") and _TEST_PATH.search(relative):
            continue
        if not alpha and relative.startswith("quwoquan_app/assets/content/alpha/"):
            continue
        paths.append((relative, path.read_bytes()))
    captured = dict(paths)
    for relative, expected in report["sourceDigests"].items():
        repository_relative = Path(os.path.normpath("quwoquan_app/" + relative)).as_posix()
        payload = captured.get(repository_relative)
        if payload is None or "sha256:" + hashlib.sha256(payload).hexdigest() != expected:
            _fail("source changed during projection capture: " + relative)
    destination.mkdir(parents=True)
    for relative, data in paths:
        output = destination / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(data)
        output.chmod((repository / relative).stat().st_mode & 0o777)
    if alpha and not _cohort:
        pubspec = destination / "quwoquan_app/pubspec.yaml"
        document = yaml.safe_load(pubspec.read_text())
        assets = document.setdefault("flutter", {}).setdefault("assets", [])
        assets.extend(asset for asset in _ALPHA_ASSETS if asset not in assets)
        pubspec.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True))
    # pub/Pod 必须从新投影自行离线解析，不继承指向 live 的 package_config。
    report["projectionRoot"] = str(destination.resolve())
    report["sourceRepository"] = str(repository)
    report["sourceGitSha"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository, text=True).strip()
    report["sourceTreeDigest"] = "sha1:" + subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=repository, text=True).strip()
    report["pubspecDigest"] = "sha256:" + hashlib.sha256((destination / "quwoquan_app/pubspec.yaml").read_bytes()).hexdigest()
    report["entrypoint"] = entrypoint
    (destination / "source-isolation.json").write_text(json.dumps(report, sort_keys=True))
    return report


def _bytes_digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def freeze_repository_inputs(repository: Path, destination: Path) -> dict[str, Any]:
    """一次冻结两个 composition 并集；本地证据不签发候选/发布资格。"""
    report = project_repository_inputs(repository, destination / "repo", entrypoint="lib/main_alpha.dart", _cohort=True)
    root = destination.resolve()
    files = {p.relative_to(root / "repo").as_posix(): _bytes_digest(p.read_bytes())
             for p in sorted((root / "repo").rglob("*")) if p.is_file()}
    manifest = {"sourceGitSha": report["sourceGitSha"], "sourceTreeDigest": report["sourceTreeDigest"],
                "files": files, "releaseAuthority": False}
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    (root / "frozen-source.json").write_bytes(encoded)
    for path in sorted(root.rglob("*"), reverse=True):
        path.chmod(0o555 if path.is_dir() else (path.stat().st_mode & 0o555) | 0o444)
    root.chmod(0o555)
    return {"manifest": str(root / "frozen-source.json"), "digest": _bytes_digest(encoded), **manifest}


def _verify_frozen_source(manifest_path: Path, expected_digest: str) -> dict[str, Any]:
    if manifest_path.is_symlink():
        _fail("frozen manifest symlink")
    encoded = manifest_path.read_bytes()
    if _bytes_digest(encoded) != expected_digest:
        _fail("frozen manifest digest drifted")
    manifest = json.loads(encoded)
    root = manifest_path.parent / "repo"
    for relative, digest in manifest["files"].items():
        path = _regular(root / relative, root.resolve())
        if _bytes_digest(path.read_bytes()) != digest:
            _fail("frozen input bytes drifted: " + relative)
    return manifest


def derive_frozen_projection(frozen_root: Path, destination: Path, *, entrypoint: str) -> dict[str, Any]:
    """只读取冻结输入；无 live Git/subprocess，不覆盖已有投影。"""
    manifest_path = frozen_root.resolve() / "frozen-source.json"
    digest = _bytes_digest(manifest_path.read_bytes())
    manifest = _verify_frozen_source(manifest_path, digest)
    source = frozen_root.resolve() / "repo"
    contract = json.loads((source / "quwoquan_app/tool/app_launch_contract_codegen/app_launch_contract.generated.json").read_bytes())["appLaunchManifest"]
    mapping = contract["content_source_entrypoints"]
    if entrypoint not in mapping.values():
        _fail("entrypoint absent from frozen metadata")
    alpha = entrypoint == mapping["bundled_snapshot"]
    report = audit_source_closure(source / "quwoquan_app", entrypoint, alpha=alpha)
    target = destination.resolve()
    if target.exists() or target.is_relative_to(source):
        _fail("derived projection must be fresh")
    target.mkdir(parents=True)
    for relative in manifest["files"]:
        if relative == "source-isolation.json":
            continue
        if relative.startswith("quwoquan_app/lib/") and relative.endswith(".dart") and relative.removeprefix("quwoquan_app/") not in report["sourceFiles"]:
            continue
        if not alpha and relative.startswith("quwoquan_app/assets/content/alpha/"):
            continue
        path = source / relative
        output = target / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, output)
        output.chmod(path.stat().st_mode | 0o600)
    pubspec = target / "quwoquan_app/pubspec.yaml"
    if alpha:
        document = yaml.safe_load(pubspec.read_text())
        assets = document.setdefault("flutter", {}).setdefault("assets", [])
        assets.extend(asset for asset in _ALPHA_ASSETS if asset not in assets)
        pubspec.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True))
    report.update(projectionRoot=str(target), sourceGitSha=manifest["sourceGitSha"],
                  sourceTreeDigest=manifest["sourceTreeDigest"], pubspecDigest=_bytes_digest(pubspec.read_bytes()),
                  entrypoint=entrypoint, frozenSourceManifest=str(manifest_path), frozenSourceManifestDigest=digest)
    (target / "source-isolation.json").write_text(json.dumps(report, sort_keys=True))
    return report


def verify_projection_identity(repository: Path) -> tuple[str, str]:
    """私有 direct 投影仍消费原仓 audited Git identity，并重验复制的 source exact bytes。"""
    repository = repository.resolve()
    report_path = repository / "source-isolation.json"
    if report_path.is_symlink():
        _fail("projection report symlink")
    report = json.loads(report_path.read_bytes())
    if Path(report["projectionRoot"]).resolve() != repository.resolve():
        _fail("projection root drifted")
    if "frozenSourceManifest" in report:
        frozen = _verify_frozen_source(Path(report["frozenSourceManifest"]), report["frozenSourceManifestDigest"])
        revision, tree = frozen["sourceGitSha"], frozen["sourceTreeDigest"]
    else:
        origin = Path(report["sourceRepository"])
        revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=origin, text=True).strip()
        tree = "sha1:" + subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=origin, text=True).strip()
    if (revision, tree) != (report["sourceGitSha"], report["sourceTreeDigest"]):
        _fail("audited origin identity drifted")
    app = repository / "quwoquan_app"
    for relative, digest in report["sourceDigests"].items():
        path = _regular(app / relative, repository.resolve())
        if "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            _fail("projection source bytes drifted: " + relative)
    if "sha256:" + hashlib.sha256((app / "pubspec.yaml").read_bytes()).hexdigest() != report["pubspecDigest"]:
        _fail("projection pubspec drifted")
    return revision, tree


def materialize_alpha_assets(app_dir: Path, output: Path, *, entrypoint: str) -> None:
    """原生 raw SDK build 也从同一 canonical snapshot 供给 Flutter asset lookup。"""
    app_dir = app_dir.resolve()
    from quwoquan_ops.cli.lib.app_launch_manifest_contract import load_launch_manifest_contract
    mapping = load_launch_manifest_contract()["content_source_entrypoints"]
    if Path(entrypoint).is_absolute():
        entrypoint = Path(entrypoint).resolve().relative_to(app_dir.resolve()).as_posix()
    if entrypoint == "lib/main.dart":
        entrypoint = mapping["bundled_snapshot"]
    if entrypoint not in mapping.values():
        _fail("native entrypoint not declared by launch metadata")
    audit_source_closure(app_dir, entrypoint, alpha=entrypoint == mapping["bundled_snapshot"])
    root = output / "assets/content/alpha"
    if entrypoint != mapping["bundled_snapshot"]:
        if root.exists():
            _fail("online build output contains stale Alpha resources; use a fresh projection")
        return
    source = app_dir / "assets/content/alpha"
    identity = json.loads((source / "bundle_identity.json").read_bytes())
    manifest = (source / "manifest.json").read_bytes()
    if "sha256:" + hashlib.sha256(manifest).hexdigest() != identity["manifestDigest"]:
        _fail("Alpha manifest digest mismatch")
    document = json.loads(manifest)
    for media in document["media"]:
        path = _regular(app_dir / media["assetPath"], app_dir.resolve())
        data = path.read_bytes()
        expected = media.get("sha256") or media.get("digest")
        if expected not in {hashlib.sha256(data).hexdigest(), "sha256:" + hashlib.sha256(data).hexdigest()}:
            _fail("Alpha media digest mismatch: " + media["assetPath"])
    root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, root, dirs_exist_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--entrypoint", required=True)
    parser.add_argument("--native-assets", action="store_true")
    args = parser.parse_args()
    if args.native_assets:
        materialize_alpha_assets(args.repository / "quwoquan_app", args.destination, entrypoint=args.entrypoint)
    else:
        print(json.dumps(project_repository_inputs(args.repository, args.destination, entrypoint=args.entrypoint), sort_keys=True))


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    main()
