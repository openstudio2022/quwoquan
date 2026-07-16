"""Intake tag candidates and merge only candidates approved by a human review."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from core.paths import (  # noqa: E402
    CONTROL_PLANE_TAXONOMY_ROOT,
    DATA_LOCAL_ROOT,
)
from core.semantic_mentions import DEFAULT_MAX_CANDIDATES  # noqa: E402
from governance.creators.candidates.store import CandidateRepository, candidate_id_for  # noqa: E402
from governance.creators.candidates.state import STATUS_PENDING_REVIEW, STATUS_PUBLISHED  # noqa: E402

TAGS_ROOT = CONTROL_PLANE_TAXONOMY_ROOT
RUNTIME_TAG_DIR = DATA_LOCAL_ROOT / "workspace" / "taxonomy"
CANDIDATES_FILE = RUNTIME_TAG_DIR / "candidates.ndjson"
MERGE_LOG = RUNTIME_TAG_DIR / "merge_log.ndjson"
GOVERNANCE_ROOT = DATA_LOCAL_ROOT / "workspace" / "governance"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalized_tag_ref(value: str) -> str:
    raw = str(value).strip().strip("/")
    parts = raw.split("/")
    if not raw or any(part in {"", ".", ".."} or "\x00" in part for part in parts):
        raise ValueError(f"invalid tag ref: {value!r}")
    return "/".join(parts)


def all_existing_tags(tags_root: Path = TAGS_ROOT) -> set[str]:
    return {str(path.parent.relative_to(tags_root)) for path in tags_root.rglob("_definition.json")}


def all_existing_labels(tags_root: Path = TAGS_ROOT) -> set[str]:
    labels: set[str] = set()
    for path in tags_root.rglob("_definition.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        label = str(data.get("label") or "").strip()
        if label:
            labels.add(label)
    return labels


def merge_tag(
    tag_ref: str,
    label: str,
    label_en: str,
    description: str,
    *,
    candidate_id: str,
    tags_root: Path = TAGS_ROOT,
    now: str | None = None,
) -> bool:
    tag_ref = _normalized_tag_ref(tag_ref)
    path = tags_root / tag_ref / "_definition.json"
    if path.exists():
        return False
    timestamp = now or _now_iso()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "label": label,
        "labelEn": label_en,
        "description": description,
        "sourceRefs": [f"governance:{candidate_id}"],
        "createdAt": timestamp,
        "updatedAt": timestamp,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def _read_ndjson(path: Path) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: expected object")
            output.append(value)
    return output


def _load_reviews(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    if not path.is_file():
        raise FileNotFoundError(f"review file not found: {path}")
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload if isinstance(payload, list) else payload.get("reviews")
        if not isinstance(rows, list):
            raise ValueError(f"{path}: expected a JSON list or {{\"reviews\": [...]}}")
        return [dict(row) for row in rows]
    return _read_ndjson(path)


def _candidate_descriptor(
    raw: Mapping[str, Any],
    *,
    min_freq: int,
) -> dict[str, Any] | None:
    reason = str(raw.get("reason") or "")
    if reason in {"dead_ref", "dead_geo_ref"}:
        tag_ref = _normalized_tag_ref(str(raw.get("tagRef") or ""))
        if not tag_ref:
            return None
        label = tag_ref.rsplit("/", 1)[-1]
        description = f"由死引用发现，待人工确认: {raw.get('source', '')}"
    elif reason == "content_keyword":
        if int(raw.get("frequency") or 0) < min_freq:
            return None
        label = str(raw.get("label") or "").strip()
        if not label:
            return None
        group = str(raw.get("suggestedGroup") or "Topic").strip().strip("/")
        tag_ref = _normalized_tag_ref(f"{group}/主题/{label}")
        description = f"由正文高频词发现，待人工确认（频率 {int(raw.get('frequency') or 0)}）"
    else:
        return None
    return {
        "kind": "tag",
        "naturalKey": tag_ref,
        "payload": {
            "tagRef": tag_ref,
            "label": label,
            "labelEn": str(raw.get("labelEn") or label),
            "description": description,
            "discoveryReason": reason,
            "rawCandidate": dict(raw),
        },
        "sourceRefs": [str(raw.get("source") or "")],
    }


def _apply_reviews(
    repository: CandidateRepository,
    reviews: Sequence[Mapping[str, Any]],
) -> int:
    applied = 0
    for row in reviews:
        actor_type = str(row.get("actorType") or "human").strip()
        if actor_type != "human":
            raise ValueError("tag candidate reviews must have actorType=human")
        candidate_id = str(row.get("candidateId") or "").strip()
        if not candidate_id:
            kind = str(row.get("kind") or "tag").strip()
            natural_key = str(row.get("naturalKey") or "").strip()
            candidate_id = candidate_id_for(kind, natural_key)
        repository.review(
            candidate_id,
            decision=str(row.get("decision") or "").strip(),
            reviewer=str(row.get("reviewer") or "").strip(),
            decision_id=str(row.get("decisionId") or "").strip(),
            reason=str(row.get("reason") or ""),
            reviewed_at=str(row.get("reviewedAt") or "").strip() or None,
        )
        applied += 1
    return applied


def run_merge(
    *,
    candidates_file: Path = CANDIDATES_FILE,
    reviews_file: Path | None = None,
    tags_root: Path = TAGS_ROOT,
    governance_root: Path = GOVERNANCE_ROOT,
    merge_log: Path = MERGE_LOG,
    min_freq: int = 3,
    dry_run: bool = False,
) -> dict[str, int]:
    if not candidates_file.is_file():
        return {"eligible": 0, "merged": 0, "skipped": 0, "pending": 0, "reviewsApplied": 0}

    raw_candidates = _read_ndjson(candidates_file)
    existing_tags = all_existing_tags(tags_root)
    existing_labels = all_existing_labels(tags_root)
    descriptors: list[dict[str, Any]] = []
    descriptor_keys: set[str] = set()
    skipped = 0
    for raw in raw_candidates:
        descriptor = _candidate_descriptor(raw, min_freq=min_freq)
        if descriptor is None:
            skipped += 1
            continue
        payload = descriptor["payload"]
        if payload["tagRef"] in existing_tags or payload["label"] in existing_labels:
            skipped += 1
            continue
        if descriptor["naturalKey"] in descriptor_keys:
            skipped += 1
            continue
        if len(descriptors) >= DEFAULT_MAX_CANDIDATES:
            skipped += 1
            continue
        descriptor_keys.add(descriptor["naturalKey"])
        descriptors.append(descriptor)

    repository = CandidateRepository(governance_root)
    if dry_run:
        pending = sum(
            1
            for descriptor in descriptors
            if (
                repository.find(descriptor["kind"], descriptor["naturalKey"]) or {}
            ).get("status", STATUS_PENDING_REVIEW)
            == STATUS_PENDING_REVIEW
        )
        return {
            "eligible": len(descriptors),
            "merged": 0,
            "skipped": skipped,
            "pending": pending,
            "reviewsApplied": 0,
        }

    governed: list[dict[str, Any]] = []
    for descriptor in descriptors:
        governed.append(
            repository.intake(
                kind=descriptor["kind"],
                natural_key=descriptor["naturalKey"],
                payload=descriptor["payload"],
                source_refs=descriptor["sourceRefs"],
                actor="governance.taxonomy.candidate_merge",
            )
        )

    reviews_applied = _apply_reviews(repository, _load_reviews(reviews_file))
    merged = 0
    pending = 0
    log_entries: list[dict[str, Any]] = []
    for original in governed:
        candidate = repository.get(str(original["candidateId"])) or original
        status = str(candidate.get("status") or STATUS_PENDING_REVIEW)
        if status == STATUS_PENDING_REVIEW:
            pending += 1
            continue
        if status != STATUS_PUBLISHED:
            skipped += 1
            continue
        payload = candidate.get("payload") or {}
        timestamp = _now_iso()
        if merge_tag(
            str(payload.get("tagRef") or ""),
            str(payload.get("label") or ""),
            str(payload.get("labelEn") or payload.get("label") or ""),
            str(payload.get("description") or ""),
            candidate_id=str(candidate["candidateId"]),
            tags_root=tags_root,
            now=timestamp,
        ):
            merged += 1
            log_entries.append(
                {
                    "action": "merge",
                    "candidateId": candidate["candidateId"],
                    "tagRef": payload.get("tagRef"),
                    "mergedAt": timestamp,
                }
            )
        else:
            skipped += 1

    if log_entries:
        merge_log.parent.mkdir(parents=True, exist_ok=True)
        with open(merge_log, "a", encoding="utf-8") as handle:
            for entry in log_entries:
                handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    return {
        "eligible": len(descriptors),
        "merged": merged,
        "skipped": skipped,
        "pending": pending,
        "reviewsApplied": reviews_applied,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="候选标签治理与人工审核后归并")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--min-freq", type=int, default=3)
    parser.add_argument(
        "--reviews",
        type=Path,
        help="人工审核 JSON/NDJSON；每项必须含 decisionId/reviewer/decision",
    )
    args = parser.parse_args(argv)
    summary = run_merge(
        reviews_file=args.reviews,
        min_freq=args.min_freq,
        dry_run=args.dry_run,
    )
    print(
        "候选治理完成: "
        f"{summary['merged']} 合入, {summary['pending']} 待人审, "
        f"{summary['skipped']} 跳过, {summary['reviewsApplied']} 条审核记录"
    )
    if args.dry_run:
        print("[dry-run 模式]")
    if summary["pending"]:
        print("[CHECKPOINT human_review] 未审核候选禁止写入正式标签树", file=sys.stderr)
        return 2
    return 0
