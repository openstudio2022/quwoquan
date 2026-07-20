#!/usr/bin/env python3
"""验证 App-only emitter 固定输入与可重建输出清单。"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "quwoquan_app"
SERVICE = ROOT / "quwoquan_service"
GRAPH = SERVICE / "generated/contract_graph.json"
LOCK = APP / "tool/cloud_codegen/contract_graph.lock.json"
MANIFEST = APP / "tool/cloud_codegen/generated_manifest.json"
GENERATOR = "app-only-emitter"
ALLOWED_PREFIXES = (
    "lib/app/navigation/generated/",
    "lib/application/content/media/generated/",
    "lib/assistant/generated/",
    "lib/cloud/runtime/generated/",
    "lib/cloud/assistant/generated/",
    "lib/cloud/chat/generated/",
    "lib/cloud/circle/generated/",
    "lib/cloud/content/generated/",
    "lib/cloud/entity/generated/",
    "lib/cloud/rtc/generated/",
    "lib/cloud/user/generated/",
    "packages/quwoquan_cloud_contracts/lib/src/generated/",
)
GENERATOR_ROOT = SERVICE / "tools/codegen_app_metadata"


def load_json(path: Path) -> dict:
    if not path.is_file():
        raise AssertionError(f"缺少文件: {path.relative_to(ROOT)}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError(f"{path.relative_to(ROOT)} 必须是 JSON object")
    return value


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_manifest(app_root: Path, manifest: dict, lock: dict) -> set[str]:
    for retired_field in ("version", "schemaVersion", "registryRevision"):
        if retired_field in manifest:
            raise AssertionError(f"generated manifest 禁止退休字段: {retired_field}")
    if manifest.get("generator") != GENERATOR:
        raise AssertionError("generated manifest generator 漂移")
    graph_sha = lock.get("contractGraph", {}).get("sha256")
    if manifest.get("contractGraphSha256") != graph_sha:
        raise AssertionError("generated manifest 未绑定当前 ContractGraph lock")
    outputs = manifest.get("outputs")
    if not isinstance(outputs, list) or not outputs:
        raise AssertionError("generated manifest outputs 不能为空")

    seen: set[str] = set()
    for output in outputs:
        if not isinstance(output, dict):
            raise AssertionError("generated manifest output 必须是 object")
        relative = str(output.get("path", ""))
        if (
            not relative
            or relative.startswith("/")
            or ".." in Path(relative).parts
            or not relative.startswith(ALLOWED_PREFIXES)
        ):
            raise AssertionError(f"非法 App generated output path: {relative}")
        if relative in seen:
            raise AssertionError(f"重复 App generated output: {relative}")
        seen.add(relative)
        if output.get("owner") != "app-only-emitter":
            raise AssertionError(f"App generated output owner 漂移: {relative}")
        if output.get("generator") != GENERATOR:
            raise AssertionError(f"App generated output generator 漂移: {relative}")
        if output.get("contractGraphSha256") != graph_sha:
            raise AssertionError(f"App generated output Graph hash 漂移: {relative}")
        path = app_root / relative
        if not path.is_file():
            raise AssertionError(f"App generated output 缺失: {relative}")
        payload = path.read_bytes()
        if len(payload) != output.get("bytes"):
            raise AssertionError(f"App generated output 大小漂移: {relative}")
        if hashlib.sha256(payload).hexdigest() != output.get("sha256"):
            raise AssertionError(f"App generated output hash 漂移: {relative}")
    return seen


def discover_generated_files() -> set[str]:
    discovered: set[str] = set()
    for prefix in ALLOWED_PREFIXES:
        root = APP / prefix
        if not root.is_dir():
            continue
        for path in root.rglob("*.dart"):
            header = path.read_text(encoding="utf-8", errors="replace")[:300]
            normalized = header.lower()
            if "generated" in normalized and "do not edit" in normalized:
                discovered.add(path.relative_to(APP).as_posix())
    return discovered


def verify_rebuild(committed: dict) -> None:
    with tempfile.TemporaryDirectory(prefix="qwq-app-codegen-") as temp:
        temp_app = Path(temp) / "quwoquan_app"
        temp_manifest = temp_app / "tool/cloud_codegen/generated_manifest.json"
        command = [
            "go",
            "run",
            "./tools/codegen_app_metadata",
            "--metadata-dir",
            "contracts/metadata",
            "--contract-graph",
            str(GRAPH),
            "--contract-graph-lock",
            str(LOCK),
            "--app-dir",
            str(temp_app),
            "--generated-manifest",
            str(temp_manifest),
        ]
        result = subprocess.run(
            command,
            cwd=SERVICE,
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        if result.returncode != 0:
            raise AssertionError(
                "App generated clean rebuild 失败:\n"
                f"{result.stdout}\n{result.stderr}"
            )
        rebuilt = load_json(temp_manifest)
        validate_manifest(temp_app, rebuilt, load_json(LOCK))
        if rebuilt != committed:
            committed_outputs = {
                item["path"]: item for item in committed.get("outputs", [])
            }
            rebuilt_outputs = {
                item["path"]: item for item in rebuilt.get("outputs", [])
            }
            changed = sorted(
                path
                for path in committed_outputs.keys() | rebuilt_outputs.keys()
                if committed_outputs.get(path) != rebuilt_outputs.get(path)
            )
            raise AssertionError(
                "删除 generated 后全量重建结果与 committed manifest 不一致: "
                f"{changed[:20]}"
            )

def verify_emitter_boundary() -> None:
    main_text = (GENERATOR_ROOT / "main.go").read_text(encoding="utf-8")
    service_makefile = (SERVICE / "Makefile").read_text(encoding="utf-8")
    if "initializeContractGraphBundle(" not in main_text:
        raise AssertionError("App emitter 未消费固定 ContractGraph bundle")
    if "initializeContractGraph(metadataDir)" in main_text:
        raise AssertionError("App emitter 仍在运行时编译 metadata YAML")
    if "--integration-service-dir" in service_makefile:
        raise AssertionError("codegen-app 仍可写领域服务输出")
    for source in sorted(GENERATOR_ROOT.glob("*.go")):
        if source.name.endswith("_test.go") or source.name == "contract_graph_source.go":
            continue
        text = source.read_text(encoding="utf-8")
        if "os.ReadFile(" in text:
            raise AssertionError(
                f"App emitter 禁止读取 Graph/lock 之外的文件: {source.name}"
            )


def main() -> int:
    lock = load_json(LOCK)
    if digest(GRAPH) != lock.get("contractGraph", {}).get("sha256"):
        raise AssertionError("ContractGraph bundle 与 App lock hash 不一致")
    manifest = load_json(MANIFEST)
    listed = validate_manifest(APP, manifest, lock)
    discovered = discover_generated_files()
    missing = sorted(discovered - listed)
    stale = sorted(listed - discovered)
    if missing or stale:
        raise AssertionError(
            "App generated manifest 覆盖不完整: "
            f"未登记={missing}, 非生成项={stale}"
        )
    verify_emitter_boundary()
    verify_rebuild(manifest)
    print(
        "PASS: App-only emitter fixed Graph + clean rebuild "
        f"(outputs={len(listed)}, graph={manifest['contractGraphSha256']})"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"FAIL: {exc}")
        raise SystemExit(1)
