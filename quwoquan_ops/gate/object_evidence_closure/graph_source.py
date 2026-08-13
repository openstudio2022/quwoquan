"""ContractGraph 的现场派生、读取绑定与 canonical packet shape 校验。"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from .constants import (
    LEGACY_FLATTENED_EVIDENCE_FIELDS,
    PACKET_ALLOWED_FIELDS,
    PACKET_REQUIRED_FIELDS,
    PACKET_STRING_LIST_FIELDS,
    PRODUCER_ARTIFACT_FIELDS,
    PRODUCER_BOOLEAN_FIELDS,
    PRODUCER_STORAGE_FIELDS,
    ROOT,
    SERVICE_ROOT,
    SHA256_PATTERN,
)
from .models import display_path, sha256_file


#: derive work root 的保留窗口。
#:
#: 每次派生都必须独占一个 work root（见 derive_contract_graph 的说明），但没有任何一方
#: 负责回收：实测积压到 39 个、8GB。个数与时间两个条件必须同时满足才删，这样并行运行的
#: 另一个 gate 不会被删掉脚下正在读的 view。
RETAINED_WORK_ROOTS = 4
WORK_ROOT_RETENTION_SECONDS = 3600
WORK_ROOT_PREFIX = "derive-"


def prune_stale_work_roots(cache_root: Path) -> list[Path]:
    """回收 cache_root 下陈旧的 derive work root。"""
    cutoff = time.time() - WORK_ROOT_RETENTION_SECONDS
    roots: list[tuple[float, Path]] = []
    for entry in cache_root.iterdir():
        if entry.is_symlink() or not entry.is_dir():
            continue
        if not entry.name.startswith(WORK_ROOT_PREFIX):
            continue
        roots.append((entry.stat().st_mtime, entry))
    roots.sort(reverse=True)
    removed: list[Path] = []
    for index, (mtime, entry) in enumerate(roots):
        if index < RETAINED_WORK_ROOTS or mtime > cutoff:
            continue
        shutil.rmtree(entry, ignore_errors=True)
        removed.append(entry)
    return removed


def derive_contract_graph(report_dir: Path) -> Path:
    """用与 codegen 同一条管线重新派生 ContractGraph。

    metadata 视图只含 YAML，所以必须显式传 --repo-root，否则 loader 无法派生任何物理
    证据；这一点由 qwq_contract 自身 fail-closed 保证。
    """
    # 契约视图与派生图都只能落在 repo-local 可重建缓存，并且必须逐次隔离。
    # build_service_contract_view 会重建目标目录；共享固定 view 会让两个 gate
    # 互相删除 symlink 树。共享固定 graph 也会让一方在 load 前读到另一方覆盖的
    # 字节，所以两者必须处于同一个唯一 derive work root。
    cache_root = (
        ROOT
        / ".qwq_output"
        / "env"
        / "repo"
        / "local"
        / "object-evidence-closure"
        / "cache"
    )
    report_dir.mkdir(parents=True, exist_ok=True)
    cache_root.mkdir(parents=True, exist_ok=True)
    prune_stale_work_roots(cache_root)
    work_root = Path(tempfile.mkdtemp(prefix=WORK_ROOT_PREFIX, dir=cache_root))
    view = work_root / "view"
    graph_path = work_root / "contract_graph.json"
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    build_view = subprocess.run(
        [
            sys.executable,
            str(SERVICE_ROOT / "scripts" / "contracts" / "build_service_contract_view.py"),
            "--output",
            str(view),
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if build_view.returncode != 0:
        raise SystemExit(
            "GATE_BLOCK 无法构建服务契约视图:\n"
            f"{build_view.stdout}\n{build_view.stderr}"
        )
    generate = subprocess.run(
        [
            "go",
            "run",
            "./tools/qwq_contract",
            "generate",
            "--metadata-dir",
            str(view),
            "--repo-root",
            str(ROOT),
            "--profile",
            "baseline",
            "--output",
            str(graph_path),
        ],
        cwd=SERVICE_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if generate.returncode != 0:
        raise SystemExit(
            "GATE_BLOCK 无法派生 ContractGraph:\n"
            f"{generate.stdout}\n{generate.stderr}"
        )
    return graph_path

def _shape_block(location: str, detail: str) -> None:
    raise SystemExit(
        "GATE_BLOCK ContractGraph readinessEvidence 不是 canonical "
        f"producer-separated packet：{location} {detail}"
    )


def _validate_string_list(value: object, location: str) -> None:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        _shape_block(location, "必须是非空字符串组成的 list")


def _validate_artifact_shape(value: object, location: str) -> None:
    if not isinstance(value, dict):
        _shape_block(location, "必须是 Artifact {path, sha256}")
    if set(value) != {"path", "sha256"}:
        _shape_block(
            location,
            "必须且只能包含 path/sha256；EvidenceArtifact 不承载 storage 或兼容字段",
        )
    path_text = value.get("path")
    digest = value.get("sha256")
    if not isinstance(path_text, str) or not path_text.strip():
        _shape_block(f"{location}.path", "必须是非空 repository-relative 字符串")
    if not isinstance(digest, str) or not SHA256_PATTERN.fullmatch(digest):
        _shape_block(f"{location}.sha256", "必须是 64 位小写十六进制摘要")


def _validate_artifact_list(value: object, location: str) -> None:
    if not isinstance(value, list):
        _shape_block(location, "必须是 Artifact list")
    for index, artifact in enumerate(value):
        _validate_artifact_shape(artifact, f"{location}[{index}]")


def _validate_storage_evidence_shape(value: object, location: str) -> None:
    if not isinstance(value, dict):
        _shape_block(location, "必须是 StorageEvidence {storage, artifact}")
    if set(value) != {"storage", "artifact"}:
        _shape_block(
            location,
            "必须且只能包含 storage/artifact；旧扁平 storage/path/sha256 不可复用",
        )
    storage = value.get("storage")
    if not isinstance(storage, str) or not storage.strip():
        _shape_block(f"{location}.storage", "必须是非空字符串")
    _validate_artifact_shape(value.get("artifact"), f"{location}.artifact")


def _validate_storage_evidence_list(value: object, location: str) -> None:
    if not isinstance(value, list):
        _shape_block(location, "必须是 StorageEvidence list")
    for index, evidence in enumerate(value):
        _validate_storage_evidence_shape(evidence, f"{location}[{index}]")


def _validate_producer_shape(packet: dict, producer: str, location: str) -> None:
    value = packet.get(producer)
    if not isinstance(value, dict):
        _shape_block(f"{location}.{producer}", "必须是 map")
    expected = (
        set(PRODUCER_ARTIFACT_FIELDS.get(producer, ()))
        | set(PRODUCER_STORAGE_FIELDS.get(producer, ()))
        | set(PRODUCER_BOOLEAN_FIELDS.get(producer, ()))
    )
    missing = sorted(expected - set(value))
    unexpected = sorted(set(value) - expected)
    if missing or unexpected:
        _shape_block(
            f"{location}.{producer}",
            f"字段不闭合（missing={missing}, unexpected={unexpected}）",
        )
    for field in PRODUCER_ARTIFACT_FIELDS.get(producer, ()):
        _validate_artifact_list(value[field], f"{location}.{producer}.{field}")
    for field in PRODUCER_STORAGE_FIELDS.get(producer, ()):
        _validate_storage_evidence_list(
            value[field], f"{location}.{producer}.{field}"
        )
    for field in PRODUCER_BOOLEAN_FIELDS.get(producer, ()):
        if not isinstance(value[field], bool):
            _shape_block(f"{location}.{producer}.{field}", "必须是 bool")


def validate_contract_graph_shape(graph: object) -> None:
    """拒绝旧扁平证据和不完整 producer maps，避免缺字段被解释成空证据。"""
    if not isinstance(graph, dict):
        _shape_block("ContractGraph", "必须是 JSON object")
    packets = graph.get("readinessEvidence")
    if not isinstance(packets, list):
        _shape_block("readinessEvidence", "必须是 list")
    for index, packet in enumerate(packets):
        location = f"readinessEvidence[{index}]"
        if not isinstance(packet, dict):
            _shape_block(location, "必须是 object")
        legacy = sorted(set(packet) & LEGACY_FLATTENED_EVIDENCE_FIELDS)
        if legacy:
            _shape_block(
                location,
                f"包含旧扁平证据字段 {legacy}；证据必须归入 service/app/ops",
            )
        missing = sorted(PACKET_REQUIRED_FIELDS - set(packet))
        unexpected = sorted(set(packet) - PACKET_ALLOWED_FIELDS)
        if missing or unexpected:
            _shape_block(
                location,
                f"字段不闭合（missing={missing}, unexpected={unexpected}）",
            )
        for field in ("objectId", "sourcePath"):
            value = packet[field]
            if not isinstance(value, str) or not value.strip():
                _shape_block(f"{location}.{field}", "必须是非空字符串")
        for field in PACKET_STRING_LIST_FIELDS:
            if field in packet:
                _validate_string_list(packet[field], f"{location}.{field}")
        if "pythonImplementation" in packet and not isinstance(
            packet["pythonImplementation"], bool
        ):
            _shape_block(f"{location}.pythonImplementation", "必须是 bool")
        for producer in ("service", "app", "ops"):
            _validate_producer_shape(packet, producer, location)
        if "publicationDelivery" in packet:
            _validate_storage_evidence_list(
                packet["publicationDelivery"], f"{location}.publicationDelivery"
            )


def load_graph_with_digest(path: Path) -> tuple[dict, str]:
    """一次读取图字节并绑定摘要，避免解析内容与 report identity 来自两次读取。"""
    try:
        payload = path.read_bytes()
        graph = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SystemExit(f"GATE_BLOCK 无法读取 ContractGraph {path}: {error}") from error
    validate_contract_graph_shape(graph)
    return graph, hashlib.sha256(payload).hexdigest()


def load_graph(path: Path) -> dict:
    return load_graph_with_digest(path)[0]


def verify_graph_digest(path: Path, expected: str) -> None:
    """报告落盘前后都复核输入图；运行中漂移不得产生可复用 PASS report。"""
    try:
        actual = sha256_file(path)
    except OSError as error:
        raise SystemExit(f"GATE_BLOCK 无法复核 ContractGraph {path}: {error}") from error
    if actual != expected:
        raise SystemExit(
            "GATE_BLOCK ContractGraph 在对象证据判定期间发生漂移："
            f"expected={expected} actual={actual} path={display_path(path)}"
        )
