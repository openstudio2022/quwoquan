"""现役 seal 语义审核输入的测试构造器；仅供已具备真实 source/draft 的 fixture。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def approved_semantic_judgement(root: Path, target_ref: str) -> dict[str, object]:
    """按 execution 的真实 source refs 构造 reviewer 已确认的无损语义闭包。"""
    refs = json.loads((root / target_ref / "1.download/source_refs.json").read_text(encoding="utf-8"))
    sources = []
    for binding in refs.get("sources") or []:
        source_ref = str(binding["sourceRef"])
        source_path = root / source_ref
        text = source_path.read_text(encoding="utf-8")
        counts = {
            "title": sum(1 for line in text.splitlines() if line.startswith("# ")),
            "heading": sum(1 for line in text.splitlines() if line.startswith("##")),
            "paragraph": sum(1 for block in text.split("\n\n") if block.strip() and not block.lstrip().startswith("#")),
            "list": sum(1 for line in text.splitlines() if line.startswith(("- ", "* "))),
            "tableLogicalCell": 0,
            "footnote": 0,
            "media": sum(1 for line in text.splitlines() if "![" in line),
        }
        capabilities = [name for field, name in (("title", "title"), ("heading", "heading"), ("paragraph", "paragraph"), ("list", "list"), ("media", "media_order")) if counts[field] > 0]
        if not capabilities:
            capabilities = ["paragraph"]
        sequence = _digest(source_path)
        sources.append({
            "sourceRef": source_ref, "sourceDigest": sequence, "parseStatus": "complete",
            "dialect": "markdown", "dialectVersion": "1", "capabilities": capabilities,
            "sourceCounts": counts, "draftCounts": dict(counts),
            "sourceSequenceDigest": sequence, "draftSequenceDigest": sequence,
        })
    carrier = "homepage" if target_ref.startswith("entities/") else target_ref.split("/", 2)[1]
    report: dict[str, object] = {"reviewedCarrier": carrier, "carrierCompatible": True, "sources": sources, "issues": []}
    if carrier == "homepage":
        report["homepageFidelity"] = {name: True for name in ("title", "headingTree", "paragraphOrder", "links", "nestedLists", "tableLogicalGrid", "footnotes", "mediaCaptionOrder")}
    elif carrier == "article":
        report["articleIntent"] = {"independent": True, "intent": "fixture acceptance", "rationale": "测试作者已形成独立载体表达"}
    protocol = {"schemaVersion": "1.0.0", "dialectVersion": "1.0.0", "canonicalizationVersion": "1.0.0"}
    revision = {"contentRevision": 1, "sourceRevision": 1, "layoutRevision": 1}
    source_digest = sources[0]["sourceDigest"] if sources else "sha256:" + "0" * 64
    disposition = {
        "issueId": "semantic-exact", "objectRef": target_ref, "sourceDigest": source_digest,
        "targetDigest": source_digest, "detectedType": "SEMANTIC_EXACT", "proposedMapping": None,
        "lossFields": [], "severity": "info",
        "actor": {"actorId": "fixture-reviewer", "actorType": "independent_reviewer"},
        "reason": "fixture reviewer confirmed semantic preservation", "policyVersion": "1.0.0",
        "reviewStatus": "reviewed_confirmed", "outcome": "auto_continue",
        "processingDisposition": "preserved", "protocol": protocol, "objectRevision": revision,
    }
    return {"decision": "approved", "blockingIssues": [], "advisories": [], "semanticReport": report, "protocol": protocol, "objectRevision": revision, "dispositions": [disposition]}
