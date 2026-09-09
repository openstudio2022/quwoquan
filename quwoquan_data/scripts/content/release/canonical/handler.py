"""CLI handlers for generic immutable content releases."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from content.release.canonical.object_transaction_contract import ObjectTransactionError
from content.release.canonical.producer_release_handoff import (
    ProducerReleaseHandoffError,
    read_producer_release_handoff,
    write_producer_release_handoff,
)
from core.paths import OUTPUT_ROOT, PUBLISH_ROOT, REFERENCE_RELEASES_ROOT, REPO_ROOT
from core.schema import assert_valid


def handle_publish_object(args: argparse.Namespace) -> None:
    from content.release.canonical.publish_object import handle_publish_object as handle

    handle(args)


_CANONICAL_COHORT_NAME = "cohort.json"
_COHORT_CARRIER_PREFIXES = (
    ("homepage", "entities/"),
    ("article", "posts/article/"),
    ("image", "posts/image/"),
    ("video", "posts/video/"),
)


def _normalize_cohort(raw: dict, *, milestone: str, release_root: Path, release_id: str) -> Path:
    """AI 只声明 objectRefs/milestone/producerBaselineRevision；排序、
    expectedCarrierCounts 与 canonical 字节由这里补齐，并 create-once 写入 release 目录。"""

    refs = raw.get("objectRefs")
    if not isinstance(refs, list) or not refs:
        raise ObjectTransactionError("DATA.RELEASE.COHORT_INVALID: objectRefs must be a non-empty list")
    object_refs = sorted({str(ref).strip().strip("/") for ref in refs})
    counts = {carrier: 0 for carrier, _prefix in _COHORT_CARRIER_PREFIXES}
    for ref in object_refs:
        carrier = next((name for name, prefix in _COHORT_CARRIER_PREFIXES if ref.startswith(prefix)), None)
        if carrier is None:
            raise ObjectTransactionError(f"DATA.RELEASE.COHORT_REF_INVALID: {ref}")
        counts[carrier] += 1
    cohort = {
        **raw,
        "schema": "quwoquan_data.release_cohort",
        "milestone": str(raw.get("milestone") or milestone),
        "objectRefs": object_refs,
        "expectedCarrierCounts": dict(raw.get("expectedCarrierCounts") or counts),
    }
    assert_valid(cohort, "release", "release_cohort", label="explicit cohort")
    data = (json.dumps(cohort, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    target = release_root / release_id / _CANONICAL_COHORT_NAME
    if target.exists() and target.read_bytes() != data:
        # payload 已封存则 cohort 不可变；build 尚未成功的 release 目录允许用修正后的 cohort 重来。
        if (release_root / release_id / "payload" / "release.json").is_file():
            raise ObjectTransactionError("DATA.RELEASE.COHORT_CONFLICT: canonical cohort already frozen with different bytes")
        target.unlink()
    if target.exists():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    temporary.write_bytes(data)
    os.replace(temporary, target)
    return target


def handle_pool_query(args: argparse.Namespace) -> None:
    """只读：列出 publish 池 eligible/excluded 对象；选择权仍在调用方。"""

    from content.release.canonical.pool_query import query_pool

    publish_root = Path(args.publish_root or PUBLISH_ROOT).resolve()
    result = query_pool(publish_root)
    if args.json_output:
        target = Path(args.json_output).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"schema": result["schema"], "counts": result["counts"], "excludedCount": len(result["excluded"]), "output": target.as_posix()}, ensure_ascii=False))
        return
    print(json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True))


def handle_release_finalize(args: argparse.Namespace) -> None:
    """pool-build → release-integrity → create-once handoff，一次完成并固定 producer END。"""

    from content.release.canonical.aggregate_release import build_pool_release
    from content.release.canonical.integrity import scan_release_integrity

    output_root = Path(OUTPUT_ROOT).resolve()
    publish_root = Path(args.publish_root or PUBLISH_ROOT).resolve()
    release_root = Path(args.release_root or output_root / "data/releases").resolve()
    release_id = str(args.release_id)
    try:
        submitted = json.loads(Path(args.cohort_file).expanduser().resolve().read_bytes())
        if not isinstance(submitted, dict):
            raise ObjectTransactionError("DATA.RELEASE.COHORT_INVALID: cohort must be an object")
        cohort_file = _normalize_cohort(
            submitted, milestone=str(args.milestone), release_root=release_root, release_id=release_id
        )
        cohort = json.loads(cohort_file.read_bytes())
        if not (release_root / release_id / "payload/release.json").is_file():
            build_report = build_pool_release(
                publish_root=publish_root,
                release_root=release_root,
                release_id=release_id,
                cohort_file=cohort_file,
            )
        else:
            build_report = {"status": "replayed", "releaseId": release_id}
        integrity = scan_release_integrity(release_id)
        if not integrity.get("passed"):
            raise ObjectTransactionError(
                "release integrity failed: " + "; ".join(str(issue) for issue in integrity.get("issues") or [])
            )
        document, path, replayed = write_producer_release_handoff(
            release_id=release_id,
            cohort_file=cohort_file,
            milestone=str(args.milestone),
            producer_baseline_revision=str(args.producer_baseline_revision),
            repo_root=Path(REPO_ROOT).resolve(),
            output_root=output_root,
            publish_root=publish_root,
            release_root=release_root,
        )
        reference_copy = write_versioned_release_copy(
            release_dir=release_root / release_id,
            reference_root=Path(args.reference_root or REFERENCE_RELEASES_ROOT),
            release_id=release_id,
        )
    except (FileNotFoundError, OSError, ProducerReleaseHandoffError, ObjectTransactionError, TypeError, ValueError) as exc:
        raise SystemExit(f"[release finalize] GATE_BLOCK {exc}") from exc
    print(json.dumps({
        "schema": "quwoquan_data.release_finalize_result",
        "releaseId": release_id,
        "milestone": str(args.milestone),
        "build": {key: build_report.get(key) for key in ("status", "releaseId", "canonicalMerkle", "counts") if key in build_report},
        "integrity": {"passed": True, "canonicalMerkle": integrity.get("canonicalMerkle")},
        "handoff": {
            "status": "replayed" if replayed else "created",
            "handoffRef": path.relative_to(output_root).as_posix(),
            "handoffDigest": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
            "carrierCounts": document.get("carrierCounts"),
            "producerBaselineRevision": document.get("producerBaselineRevision"),
            "producerContractDigest": document.get("producerContractDigest"),
        },
        "referenceCopy": reference_copy,
        "terminal": "END",
    }, ensure_ascii=False, indent=2))


_VERSIONED_RELEASE_FILES = ("cohort.json", "producer_release_handoff.json")


def write_versioned_release_copy(*, release_dir: Path, reference_root: Path, release_id: str) -> dict[str, str]:
    """把里程碑 release 的 cohort 与 handoff 逐字节复制到受版本控制的 reference/releases/<releaseId>/。

    create-or-same：副本不存在则写入，已存在且逐字节相同视为 replay，不同则 fail closed——
    副本只是可删除输出根的耐久备份，不允许出现第二套字节。
    """

    target_dir = reference_root / release_id
    statuses: dict[str, str] = {}
    for name in _VERSIONED_RELEASE_FILES:
        source = release_dir / name
        if not source.is_file():
            raise ObjectTransactionError(f"DATA.RELEASE.REFERENCE_COPY_SOURCE_MISSING: {source}")
        data = source.read_bytes()
        target = target_dir / name
        if target.exists():
            if target.read_bytes() != data:
                raise ObjectTransactionError(
                    f"DATA.RELEASE.REFERENCE_COPY_CONFLICT: {target} differs from {source}"
                )
            statuses[name] = "replayed"
            continue
        target_dir.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
        temporary.write_bytes(data)
        os.replace(temporary, target)
        statuses[name] = "created"
    return {"root": target_dir.as_posix(), **statuses}


def handle_handoff_verify(args: argparse.Namespace) -> None:
    output_root = Path(OUTPUT_ROOT).resolve()
    release_root = Path(args.release_root or output_root / "data/releases").resolve()
    path = release_root / str(args.release_id) / "producer_release_handoff.json"
    try:
        document = read_producer_release_handoff(
            path,
            repo_root=Path(REPO_ROOT).resolve(),
            output_root=output_root,
            release_root=release_root,
        )
    except (FileNotFoundError, OSError, ProducerReleaseHandoffError, TypeError, ValueError) as exc:
        raise SystemExit(f"[release handoff-verify] GATE_BLOCK {exc}") from exc
    print(json.dumps({
        "schema": "quwoquan_data.handoff_verify_result",
        "releaseId": document["releaseId"],
        "milestone": document["milestone"],
        "carrierCounts": document["carrierCounts"],
        "handoffDigest": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
        "passed": True,
    }, ensure_ascii=False, indent=2))


from content.release.canonical.handler_cli import register_parser  # noqa: F401
