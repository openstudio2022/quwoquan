"""只读核对显式 execution 的 review、已发布字节与历史池快照。

不调用当前 pool reader，不重评内容，不改 sealed review/receipt，也不授予发布资格。
"""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path

from core.content_library import file_sha256


def evidence(path: Path) -> dict:
    return {"path": str(path), "sha256": f"sha256:{file_sha256(path)}", "bytes": path.stat().st_size}


def read_document(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"DATA.AUDIT.DOCUMENT_INVALID: {path}")
    return value


def contained(root: Path, ref: str) -> Path:
    path = (root / ref).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"DATA.AUDIT.REF_ESCAPE: {ref}")
    return path


def write_evidence(path: Path, document: dict) -> None:
    """只新建 evidence；不覆盖旧审计或把输出用作控制面。"""
    with path.open("x", encoding="utf-8") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def pool_members(document: dict) -> set[str]:
    eligible = document["eligible"]
    return set(eligible["homepages"]) | {row["objectRef"] for row in eligible["posts"]}


def aggregate(rows: list[dict]) -> dict:
    values: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        for dimension, score in row["qualityScores"].items():
            values[row["carrier"]][dimension].append(score)
    return {
        carrier: {
            dimension: {"n": len(scores), "mean": statistics.mean(scores),
                        "populationSd": statistics.pstdev(scores),
                        "min": min(scores), "max": max(scores)}
            for dimension, scores in sorted(dimensions.items())
        }
        for carrier, dimensions in sorted(values.items())
    }


def _publication(publish_root: Path, review: dict, review_digest: str) -> dict:
    root = contained(publish_root, review["objectRef"])
    published_review = root / "content_review.json"
    records = []
    for path in sorted((root / "_pool/versions").glob("*.json")):
        record = read_document(path)
        if (record.get("sourceIdentity", {}).get("executionId") == review["executionId"]
                and record.get("evidenceDigest") == review_digest):
            records.append(evidence(path))
    matched = published_review.is_file() and f"sha256:{file_sha256(published_review)}" == review_digest
    return {"matched": bool(matched and records), "reviewBytesMatched": matched,
            "records": records, "canonicalReview": evidence(published_review) if published_review.is_file() else None}


def _execution_rows(root: Path, publish_root: Path, eligible: set[str]) -> tuple[list, dict]:
    root = root.resolve()
    receipt_path = root / "_shared/receipts/003-5.review.json"
    receipt = read_document(receipt_path)
    if receipt.get("executionId") != root.name or receipt.get("stage") != "5.review":
        raise ValueError(f"DATA.AUDIT.RECEIPT_IDENTITY: {receipt_path}")
    rows = []
    for reference in receipt["resultRefs"]:
        path = contained(root, reference["ref"])
        exact = evidence(path)
        if exact["sha256"] != reference["digest"]:
            raise ValueError(f"DATA.AUDIT.REVIEW_DIGEST_DRIFT: {path}")
        review = read_document(path)
        expected_ref = path.parent.parent.relative_to(root).as_posix()
        if review.get("objectRef") != expected_ref or review.get("executionId") != root.name:
            raise ValueError(f"DATA.AUDIT.REVIEW_IDENTITY: {path}")
        carrier = "homepage" if expected_ref.startswith("entities/") else expected_ref.split("/")[1]
        publication = _publication(publish_root, review, exact["sha256"])
        rows.append({"executionId": root.name, "objectRef": expected_ref, "carrier": carrier,
                     "review": exact, "decision": review.get("decision"),
                     "qualityScores": review.get("qualityScores", {}), "publication": publication,
                     "eligibleAtSnapshot": expected_ref in eligible and publication["matched"]})
    keys = [(row["executionId"], row["objectRef"]) for row in rows]
    if len(keys) != len(set(keys)):
        raise ValueError(f"DATA.AUDIT.DUPLICATE_REVIEW_REF: {root}")
    receipts = [evidence(path) for path in sorted((root / "_shared/receipts").glob("*.json"))]
    return rows, {"executionId": root.name, "reviewReceipt": evidence(receipt_path),
                  "receiptVerdict": receipt.get("verdict"), "sealedReceipts": receipts}


def _set_views(sets: dict, executions: list[dict]) -> dict:
    return {
        "sets": {name: [{"executionId": row["executionId"], "objectRef": row["objectRef"],
                         "reviewSha256": row["review"]["sha256"]} for row in members]
                 for name, members in sets.items()},
        "counts": {name: {carrier: sum(row["carrier"] == carrier for row in members)
                          for carrier in ("homepage", "article", "image", "video")}
                   for name, members in sets.items()},
        "perExecutionCounts": {entry["executionId"]: {
            name: sum(row["executionId"] == entry["executionId"] for row in members)
            for name, members in sets.items()} for entry in executions},
        "statistics": {name: aggregate(members) for name, members in sets.items()},
    }


def quality_audit(*, executions: list[Path], publish_root: Path, pool_snapshot: Path,
                  observations: list[Path], preserve_files: list[Path]) -> dict:
    snapshot = read_document(pool_snapshot)
    eligible = pool_members(snapshot)
    rows, execution_evidence = [], []
    for root in sorted(set(executions)):
        members, entry = _execution_rows(root, publish_root, eligible)
        rows.extend(members)
        execution_evidence.append(entry)
    sets = {"reviewed": rows, "published": [row for row in rows if row["publication"]["matched"]],
            "eligible": [row for row in rows if row["eligibleAtSnapshot"]]}
    observed = [{**evidence(path), "schema": (document := read_document(path)).get("schema"),
                 "counts": document.get("counts"), "semantics": "current_reader_observation_not_historical_baseline"}
                for path in observations]
    observations_notes = [{"code": "DATA.AUDIT.READER_OBSERVATION_DIFFERS", "path": item["path"],
                          "detail": "新 reader 观察与历史快照不同；不影响原快照三集合核对，不声明新契约准入"}
                         for item in observed if item["counts"] != snapshot["counts"]]
    return {
        "schema": "quwoquan_data.production_quality_audit.v2", "purpose": "offline_evidence_only",
        "status": "passed", "firstTypedBlocker": None, "issues": [],
        "observationNotes": observations_notes,
        "poolSnapshot": {**evidence(pool_snapshot), "counts": snapshot["counts"],
                         "excluded": snapshot.get("excluded", []), "eligible": snapshot["eligible"],
                         "semantics": "历史保存快照；不声明当前新契约 eligible"},
        "currentReaderObservations": observed,
        "preservedOriginals": [{**evidence(path), "utf8Content": path.read_text(encoding="utf-8")}
                               for path in preserve_files],
        "executions": execution_evidence, "objects": rows,
        **_set_views(sets, execution_evidence),
        "method": {"sd": "population", "missingScores": "not imputed",
                   "published": "exact canonical review bytes + matching execution/evidence digest pool record",
                   "eligible": "published intersection with explicit historical snapshot",
                   "scorePolicy": "保留原六维；不重评、不合并维度、不强拉分布；视频 n=5 不作普遍结论"},
    }


def handle_quality(args) -> None:
    document = quality_audit(executions=[Path(p) for p in args.execution],
                             publish_root=Path(args.publish_root), pool_snapshot=Path(args.pool_snapshot),
                             observations=[Path(p) for p in args.observation],
                             preserve_files=[Path(p) for p in args.preserve_file])
    write_evidence(Path(args.output), document)
    print(json.dumps({"output": args.output, "counts": document["counts"],
                      "perExecutionCounts": document["perExecutionCounts"],
                      "firstTypedBlocker": document["firstTypedBlocker"]}, ensure_ascii=False, indent=2))
    if document["firstTypedBlocker"]:
        raise SystemExit(1)


def register_audit_parser(subparsers) -> None:
    quality = subparsers.add_parser("production-audit", help="只读核对显式 executions 的三集合与六维评分")
    quality.add_argument("--execution", action="append", required=True)
    quality.add_argument("--pool-snapshot", required=True)
    quality.add_argument("--publish-root", default="quwoquan_data/publish")
    quality.add_argument("--observation", action="append", default=[])
    quality.add_argument("--preserve-file", action="append", default=[])
    quality.add_argument("--output", required=True)
    quality.set_defaults(handler=handle_quality)
    media = subparsers.add_parser("media-protection-audit", help="有界逐摘要核验媒体 holders 和明确保护输入")
    media.add_argument("--publish-root", default="quwoquan_data/publish")
    media.add_argument("--releases-root", required=True)
    media.add_argument("--reference-releases-root", required=True)
    media.add_argument("--backup-root", required=True)
    media.add_argument("--binding", action="append", default=[])
    media.add_argument("--max-digests", type=int, required=True)
    media.add_argument("--max-hash-bytes", type=int, required=True)
    media.add_argument("--max-files", type=int, required=True, help="显式保护根内总文件/目录条数上限")
    media.add_argument("--max-metadata-bytes", type=int, required=True, help="JSON/Markdown 等元文件累计读取预算")
    for component in ("original", "transcode-staging", "pool-staging", "golden-growth", "backup-growth"):
        media.add_argument(f"--{component}-bytes", type=int, help="本次峰值声明上限；缺席为 unknown，不补零")
    media.add_argument("--reserve-bytes", type=int, default=0, help="每个相关设备保留量；默认无额外保留")
    media.add_argument("--budget-root", required=True, help="原件、转码、新池 staging 的显式本地落盘根")
    media.add_argument("--output", required=True)
    media.set_defaults(handler=_handle_media)


def _handle_media(args) -> None:
    from governance.media_protection_audit import handle_protection

    handle_protection(args)
