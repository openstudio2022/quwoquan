"""Execution 审计摘要：脚本验收结果 + 人工抽检清单。

目标：
- 为 `qwq-data verify --execution-id ...` 生成可直接复核的审计包。
- 把脚本硬门结果、都江堰锚点对象、以及人工抽检项收敛到 execution `_shared/` 下。
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Mapping

from content.post.object_index import iter_content_refs, content_object_dir
from core.io import read_json, write_json
from core.paths import (
    execution_audit_markdown_path,
    execution_audit_summary_path,
    execution_entity_object_dir,
    execution_root,
    now_iso,
)
from content.execution import store

AUDIT_SUMMARY_SCHEMA = "quwoquan_data.execution_audit_summary"
_FOCUS_ENTITY_NAME = "都江堰"


def _read_json_if_file(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    data = read_json(path)
    return data if isinstance(data, dict) else None


def _payload_or_self(path: Path) -> dict[str, Any] | None:
    data = _read_json_if_file(path)
    if not isinstance(data, dict):
        return None
    payload = data.get("payload")
    return payload if isinstance(payload, dict) else data


def _execution_rel(execution_dir: Path, path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return path.relative_to(execution_dir).as_posix()
    except ValueError:
        return str(path)


def _normalize_entity_ref(raw: str) -> str:
    text = str(raw or "").strip().strip("/")
    if not text:
        return ""
    if not text.startswith("entity/"):
        text = f"entity/{text}"
    return f"/{text}"


def _coverage_targets(execution_id: str) -> list[dict[str, str]]:
    try:
        spec = store.load_spec(execution_id)
    except Exception:
        return []
    targets = ((spec.get("scope") or {}).get("coverageTargets")) or []
    out: list[dict[str, str]] = []
    for row in targets:
        if not isinstance(row, Mapping):
            continue
        entity_type = str(row.get("entityType") or "").strip()
        name = str(row.get("name") or "").strip()
        if not entity_type or not name or "/" not in entity_type:
            continue
        domain, etype = entity_type.split("/", 1)
        out.append({"domain": domain, "type": etype, "name": name})
    return out


def _iter_entity_dirs(execution_dir: Path) -> list[Path]:
    root = execution_dir / "entities"
    if not root.is_dir():
        return []
    found: dict[str, Path] = {}
    for marker in ("_entity.json", "page.md"):
        for path in root.rglob(marker):
            found[str(path.parent)] = path.parent
    return sorted(found.values())


def _pick_focus_entity(execution_id: str, execution_dir: Path) -> dict[str, str] | None:
    targets = _coverage_targets(execution_id)
    for row in targets:
        if row["name"] == _FOCUS_ENTITY_NAME:
            return row
    for entity_dir in _iter_entity_dirs(execution_dir):
        rel = entity_dir.relative_to(execution_dir)
        parts = rel.parts
        if len(parts) == 4 and parts[0] == "entities" and parts[3] == _FOCUS_ENTITY_NAME:
            return {"domain": parts[1], "type": parts[2], "name": parts[3]}
    if targets:
        return targets[0]
    entities = _iter_entity_dirs(execution_dir)
    if not entities:
        return None
    rel = entities[0].relative_to(execution_dir)
    parts = rel.parts
    if len(parts) != 4:
        return None
    return {"domain": parts[1], "type": parts[2], "name": parts[3]}


def _iter_post_dirs(execution_id: str) -> list[Path]:
    found: dict[str, Path] = {}
    for ref in iter_content_refs(execution_id):
        try:
            obj = content_object_dir(execution_id, ref)
        except Exception:
            continue
        found[str(obj)] = obj
    return sorted(found.values())


def _pick_focus_article(execution_id: str, focus: Mapping[str, str] | None) -> Path | None:
    focus_ref = ""
    if focus:
        focus_ref = _normalize_entity_ref(f"{focus['domain']}/{focus['type']}/{focus['name']}")
    fallback: Path | None = None
    for post_dir in _iter_post_dirs(execution_id):
        if not (post_dir / "article.md").is_file():
            continue
        manifest = _read_json_if_file(post_dir / "manifest.json") or {}
        if fallback is None:
            fallback = post_dir
        entity_refs = {
            _normalize_entity_ref(str(ref))
            for ref in (manifest.get("entityRefs") or [])
            if str(ref or "").strip()
        }
        if focus_ref and focus_ref in entity_refs:
            return post_dir
    return fallback


def _bool_map(required: list[str], existing: set[str]) -> dict[str, bool]:
    return {name: name in existing for name in required}


def _entity_sample(execution_dir: Path, execution_id: str, focus: Mapping[str, str] | None) -> dict[str, Any]:
    if not focus:
        return {"exists": False}
    entity_dir = execution_entity_object_dir(execution_id, focus["domain"], focus["type"], focus["name"])
    if not entity_dir.is_dir():
        return {
            "exists": False,
            "name": focus["name"],
            "domain": focus["domain"],
            "type": focus["type"],
            "path": _execution_rel(execution_dir, entity_dir),
        }
    required = [
        "_entity.json",
        "manifest.json",
        "page.md",
        "2.quality/quality_analysis.json",
        "3.compose/entity_page_input.json",
        "4.draft/page.md",
        "5.review/review.json",
        "5.review/provenance.json",
        "5.review/finalization_report.json",
    ]
    existing = {
        rel.as_posix()
        for rel in [
            Path("_entity.json"),
            Path("manifest.json"),
            Path("page.md"),
            Path("2.quality/quality_analysis.json"),
            Path("3.compose/entity_page_input.json"),
            Path("4.draft/page.md"),
            Path("5.review/review.json"),
            Path("5.review/provenance.json"),
            Path("5.review/finalization_report.json"),
        ]
        if (entity_dir / rel).exists()
    }
    quality = _read_json_if_file(entity_dir / "2.quality" / "quality_analysis.json") or {}
    review = _read_json_if_file(entity_dir / "5.review" / "review.json") or {}
    provenance = _read_json_if_file(entity_dir / "5.review" / "provenance.json") or {}
    finalization = _read_json_if_file(entity_dir / "5.review" / "finalization_report.json") or {}
    payload = _read_json_if_file(entity_dir / "_entity.json") or {}
    source_units = list((entity_dir / "1.download" / "sources").glob("*/source.md"))
    return {
        "exists": True,
        "name": focus["name"],
        "domain": focus["domain"],
        "type": focus["type"],
        "path": _execution_rel(execution_dir, entity_dir),
        "requiredArtifacts": _bool_map(required, existing),
        "sourceUnitCount": len(source_units),
        "qualityRecommendation": quality.get("recommendation"),
        "qualityIssues": list(quality.get("issues") or []),
        "baseDraftSourceRef": ((quality.get("baseDraft") or {}) if isinstance(quality.get("baseDraft"), Mapping) else {}).get("sourceRef"),
        "sourcePathsCount": len(quality.get("sourcePaths") or []),
        "reviewDecision": review.get("decision"),
        "sourceQualificationPassed": bool((((review.get("checks") or {}).get("sourceQualification") or {}).get("passed"))),
        "provenanceOriginalSources": len(provenance.get("originalSources") or []),
        "finalizationDraftRef": finalization.get("draftArticleRef"),
        "finalizationFinalRef": finalization.get("finalArticleRef"),
    }


def _post_sample(execution_dir: Path, execution_id: str, focus: Mapping[str, str] | None) -> dict[str, Any]:
    post_dir = _pick_focus_article(execution_id, focus)
    if post_dir is None:
        return {"exists": False}
    required = [
        "article.md",
        "manifest.json",
        "1.download/source_refs.json",
        "4.draft/draft.article.md",
        "5.review/review.json",
        "5.review/review_gate.json",
        "5.review/review_ledger.json",
        "5.review/review_entities.json",
        "5.review/provenance.json",
        "5.review/finalization_report.json",
    ]
    existing = {
        rel.as_posix()
        for rel in [
            Path("article.md"),
            Path("manifest.json"),
            Path("1.download/source_refs.json"),
            Path("4.draft/draft.article.md"),
            Path("5.review/review.json"),
            Path("5.review/review_gate.json"),
            Path("5.review/review_ledger.json"),
            Path("5.review/review_entities.json"),
            Path("5.review/provenance.json"),
            Path("5.review/finalization_report.json"),
        ]
        if (post_dir / rel).exists()
    }
    manifest = _read_json_if_file(post_dir / "manifest.json") or {}
    review = _payload_or_self(post_dir / "5.review" / "review.json") or {}
    review_gate = _payload_or_self(post_dir / "5.review" / "review_gate.json") or {}
    source_refs = _read_json_if_file(post_dir / "1.download" / "source_refs.json") or {}
    provenance = _read_json_if_file(post_dir / "5.review" / "provenance.json") or {}
    finalization = _read_json_if_file(post_dir / "5.review" / "finalization_report.json") or {}
    entity_refs = [_normalize_entity_ref(str(ref)) for ref in (manifest.get("entityRefs") or [])]
    return {
        "exists": True,
        "path": _execution_rel(execution_dir, post_dir),
        "requiredArtifacts": _bool_map(required, existing),
        "contentType": manifest.get("contentType"),
        "publishTitle": manifest.get("publishTitle"),
        "topicId": manifest.get("topicId"),
        "entityRefs": entity_refs,
        "tagRefsCount": len(manifest.get("tagRefs") or []),
        "sourceUrlsCount": len(manifest.get("sourceUrls") or []),
        "intersectionHintsCount": len(manifest.get("intersectionHints") or []),
        "reviewDecision": review.get("decision"),
        "reviewChecks": {
            "generatorProvenance": bool((((review.get("checks") or {}).get("generatorProvenance") or {}).get("passed"))),
            "factTraceability": bool((((review.get("checks") or {}).get("factTraceability") or {}).get("passed"))),
            "baseDraftFidelity": bool((((review.get("checks") or {}).get("baseDraftFidelity") or {}).get("passed"))),
            "writingIntentConsistency": bool((((review.get("checks") or {}).get("writingIntentConsistency") or {}).get("passed"))),
        },
        "reviewGatePassed": bool(review_gate.get("passed")),
        "reviewGateIssues": list(review_gate.get("issues") or []),
        "baseSourceRef": source_refs.get("baseSourceRef"),
        "citedSourceRefsCount": len(source_refs.get("citedSourceRefs") or []),
        "sourceMirrorCount": len(source_refs.get("sources") or []),
        "provenanceOriginalSources": len(provenance.get("originalSources") or []),
        "finalizationDraftRef": finalization.get("draftArticleRef"),
        "finalizationFinalRef": finalization.get("finalArticleRef"),
        "frontmatterOnlyChange": finalization.get("frontmatterOnlyChange"),
        "bodyChanged": finalization.get("bodyChanged"),
        "composeSnapshotMatchesDraft": finalization.get("composeSnapshotMatchesDraft"),
    }


def _manual_checklist(
    execution_dir: Path,
    focus: Mapping[str, str] | None,
    article: Mapping[str, Any],
    entity: Mapping[str, Any],
    *,
    post_count: int,
) -> dict[str, Any]:
    focus_name = str((focus or {}).get("name") or _FOCUS_ENTITY_NAME)
    min_samples = max(1, math.ceil(max(post_count, 1) * 0.1))
    items: list[dict[str, Any]] = []
    article_path = str(article.get("path") or "")
    entity_path = str(entity.get("path") or "")
    if article.get("exists"):
        items.extend(
            [
                {
                    "id": "article-source-chain",
                    "target": f"{focus_name}文章对象",
                    "paths": [
                        f"{article_path}/1.download/source_refs.json",
                        str(article.get("baseSourceRef") or ""),
                    ],
                    "whatToCheck": "核对文章对象是否自持底稿/引证来源镜像，并且都能回查到实体来源单元。",
                    "passCondition": "baseSourceRef、citedSourceRefs、sources[*].sourceRef 全部非空、为 execution 相对路径、且指向 sources/{sourceUnitId}/source.md。",
                },
                {
                    "id": "article-light-edit",
                    "target": f"{focus_name}文章对象",
                    "paths": [
                        f"{article_path}/4.draft/draft.article.md",
                        f"{article_path}/article.md",
                        f"{article_path}/5.review/finalization_report.json",
                        f"{article_path}/5.review/review.json",
                    ],
                    "whatToCheck": "对照草稿、成品和 finalization report，确认正文是以底稿轻加工而不是脱稿重写或模板照抄。",
                    "passCondition": "review.decision=approved，review.checks.baseDraftFidelity/generatorProvenance/factTraceability 均为 passed；finalization_report 指向 4.draft/draft.article.md -> article.md，且 bodyChanged 不应与 fidelity 失败并存。",
                },
                {
                    "id": "article-audit-surface",
                    "target": f"{focus_name}文章对象",
                    "paths": [
                        f"{article_path}/5.review/review_gate.json",
                        f"{article_path}/5.review/review_ledger.json",
                        f"{article_path}/5.review/review_entities.json",
                        f"{article_path}/5.review/provenance.json",
                    ],
                    "whatToCheck": "确认 review gate、账本、实体边车、provenance 四类审计面都已落盘，可直接追责。",
                    "passCondition": "review_gate.passed=true；review_ledger / review_entities / provenance 文件齐全；provenance.originalSources 非空，且交集/实体/来源三条链都能闭环复核。",
                },
            ]
        )
    if entity.get("exists"):
        items.extend(
            [
                {
                    "id": "entity-source-readiness",
                    "target": f"{focus_name}实体对象",
                    "paths": [
                        f"{entity_path}/2.quality/quality_analysis.json",
                        f"{entity_path}/1.download/source_refs.json",
                    ],
                    "whatToCheck": "确认实体主页的底稿选择与来源准备阶段完整，且不是空源硬产主页。",
                    "passCondition": "quality_analysis.recommendation=proceed；baseDraft.sourceRef 可读；sourcePaths 非空；source_refs.json 至少指向 1 个真实来源单元。",
                },
                {
                    "id": "entity-review-chain",
                    "target": f"{focus_name}实体对象",
                    "paths": [
                        f"{entity_path}/4.draft/page.md",
                        f"{entity_path}/page.md",
                        f"{entity_path}/5.review/review.json",
                        f"{entity_path}/5.review/provenance.json",
                        f"{entity_path}/5.review/finalization_report.json",
                    ],
                    "whatToCheck": "确认实体主页从 draft 到 final 的 review/provenance/finalization 三件套完整，且 review 已正式采纳。",
                    "passCondition": "review.decision=approved；review.checks.sourceQualification.passed=true；provenance.originalSources 非空；finalization_report 指向 4.draft/page.md -> page.md。",
                },
                {
                    "id": "entity-light-edit-semantics",
                    "target": f"{focus_name}实体对象",
                    "paths": [
                        f"{entity_path}/_entity.json",
                        f"{entity_path}/page.md",
                    ],
                    "whatToCheck": "人工对照主页正文与底稿来源，确认主页是百科/官方底稿轻改，而不是 padding 凑字数。",
                    "passCondition": "正文与底稿事实一致，不出现重复句式灌水、机械收尾标题或与来源无关扩写。",
                },
            ]
        )
    return {
        "minimumHumanSampleCount": min_samples,
        "items": items,
    }


def _summary_markdown(summary: Mapping[str, Any]) -> str:
    script_gate = summary.get("scriptGate") or {}
    execution_stats = summary.get("executionStats") or {}
    focus = summary.get("focusEntity") or {}
    article = (summary.get("samples") or {}).get("article") or {}
    entity = (summary.get("samples") or {}).get("entity") or {}
    manual = summary.get("manualChecklist") or {}
    lines = [
        "# Execution 审计摘要",
        "",
        f"- executionId: `{summary.get('executionId')}`",
        f"- 生成时间: `{summary.get('generatedAt')}`",
        f"- 脚本门结果: `{script_gate.get('status')}`（issues={script_gate.get('issueCount', 0)}）",
        f"- 内容对象: `{execution_stats.get('postObjectCount', 0)}`（article={execution_stats.get('articleCount', 0)}, gallery={execution_stats.get('galleryCount', 0)}）",
        f"- 实体对象: `{execution_stats.get('entityObjectCount', 0)}`",
        f"- 10% 人工抽检基线: 至少 `{manual.get('minimumHumanSampleCount', 1)}` 篇内容；本清单固定锚定 `{focus.get('name') or _FOCUS_ENTITY_NAME}` 文章对象与实体对象。",
        "",
        "## 复核入口",
        "",
        f"- `python3 quwoquan_data/scripts/cli.py verify execution-readiness --execution-id {summary.get('executionId')}`",
        "",
        "## 脚本门摘要",
        "",
    ]
    issues_preview = list(script_gate.get("issuesPreview") or [])
    if issues_preview:
        for issue in issues_preview:
            lines.append(f"- `{issue}`")
    else:
        lines.append("- 脚本硬门全绿。")
    lines.extend(["", f"## {focus.get('name') or _FOCUS_ENTITY_NAME} 文章对象", ""])
    if article.get("exists"):
        lines.append(f"- 对象路径: `{article.get('path')}`")
        lines.append(f"- reviewDecision: `{article.get('reviewDecision')}`")
        lines.append(f"- baseSourceRef: `{article.get('baseSourceRef')}`")
        lines.append(
            f"- finalization: `draft={article.get('finalizationDraftRef')}` -> `final={article.get('finalizationFinalRef')}` "
            f"(frontmatterOnlyChange={article.get('frontmatterOnlyChange')}, bodyChanged={article.get('bodyChanged')})"
        )
    else:
        lines.append("- 未找到可审计的文章对象。")
    lines.extend(["", f"## {focus.get('name') or _FOCUS_ENTITY_NAME} 实体对象", ""])
    if entity.get("exists"):
        lines.append(f"- 对象路径: `{entity.get('path')}`")
        lines.append(f"- qualityRecommendation: `{entity.get('qualityRecommendation')}`")
        lines.append(f"- reviewDecision: `{entity.get('reviewDecision')}`")
        lines.append(f"- baseDraftSourceRef: `{entity.get('baseDraftSourceRef')}`")
    else:
        lines.append("- 未找到可审计的实体对象。")
    lines.extend(["", "## 人工抽检项", ""])
    for idx, item in enumerate(manual.get("items") or [], start=1):
        lines.append(f"{idx}. `{item.get('target')}` 看 `{', '.join(item.get('paths') or [])}`")
        lines.append(f"   - 检查内容：{item.get('whatToCheck')}")
        lines.append(f"   - 判定标准：{item.get('passCondition')}")
    lines.append("")
    return "\n".join(lines)


def write_execution_audit_summary(execution_id: str, *, roots: list[Path], issues: list[str]) -> tuple[Path, Path] | None:
    execution_dir = execution_root(execution_id)
    if not execution_dir.is_dir():
        return None
    focus = _pick_focus_entity(execution_id, execution_dir)
    entity_dirs = _iter_entity_dirs(execution_dir)
    post_dirs = _iter_post_dirs(execution_id)
    article_count = sum(1 for post_dir in post_dirs if (post_dir / "article.md").is_file())
    gallery_count = sum(1 for post_dir in post_dirs if (post_dir / "gallery.md").is_file())
    article = _post_sample(execution_dir, execution_id, focus)
    entity = _entity_sample(execution_dir, execution_id, focus)
    manual = _manual_checklist(
        execution_dir,
        focus,
        article,
        entity,
        post_count=len(post_dirs),
    )
    summary = {
        "schema": AUDIT_SUMMARY_SCHEMA,
        "executionId": execution_id,
        "generatedAt": now_iso(),
        "scriptGate": {
            "status": "passed" if not issues else "failed",
            "issueCount": len(issues),
            "issuesPreview": list(issues[:20]),
            "postRoots": [_execution_rel(execution_dir, root) for root in roots],
        },
        "executionStats": {
            "entityObjectCount": len(entity_dirs),
            "postObjectCount": len(post_dirs),
            "articleCount": article_count,
            "galleryCount": gallery_count,
        },
        "focusEntity": focus or {},
        "samples": {
            "article": article,
            "entity": entity,
        },
        "manualChecklist": manual,
    }
    json_path = execution_audit_summary_path(execution_id)
    md_path = execution_audit_markdown_path(execution_id)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(json_path, summary)
    md_path.write_text(_summary_markdown(summary), encoding="utf-8")
    return json_path, md_path


__all__ = [
    "AUDIT_SUMMARY_SCHEMA",
    "write_execution_audit_summary",
]
