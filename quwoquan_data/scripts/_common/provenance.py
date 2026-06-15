"""结构化出处记录 provenance.json ——「便于回查、区分中间过程与最终结果」单一入口。

用户诉求：中间过程文件太多、要精简；把每次「给 agent 的输入」与「最终结果」结构化记录，
原始数据源与参考补全的证据源一一登记，并区分中间过程与最终结果。

每个 post 在 `5.review/provenance.json` 落一份追责快照（取代分散的 produce_trace.json），只保留发布追责必需字段：
- final           ：最终交付结果摘要（generator/model/style/opening/article|asset digest/entities）。
- agentInput      ：本次给会话 agent 的写作契约与 prompt 路径。
- originalSources ：原始数据源（source 路径 + url）。
- gateResults     ：review decision 与各质量门通过状态。

provenance_issues：强制门——每个交付 post 必须有完整且一致的 provenance.json
（存在 + schema 正确 + generator=agent + 原始源非空 + 门结果 approved + article/asset digest 与引用源闭环）。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from _common.article_package import compute_asset_manifest_sha256, compute_document_sha256
from _common.io import read_json

PROVENANCE_SCHEMA = "quwoquan_data.provenance"
PROVENANCE_FILE = "5.review/provenance.json"


def _original_sources(compose_payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    paths = [str(p) for p in (compose_payload.get("sourcePaths") or []) if p]
    urls = [str(u) for u in (compose_payload.get("sourceUrls") or []) if u]
    out: list[dict[str, Any]] = []
    for index, path in enumerate(paths):
        out.append({"path": path, "url": urls[index] if index < len(urls) else None})
    for url in urls[len(paths):]:
        out.append({"path": None, "url": url})
    image_source = {
        key: compose_payload.get(key)
        for key in (
            "sourceCollectionId",
            "creator",
            "collectionPageUrl",
            "license",
            "termsUrl",
            "authorizationProof",
        )
        if compose_payload.get(key) not in (None, "", {})
    }
    if image_source:
        if out:
            out = [{**source, **image_source} for source in out]
        else:
            out.append(
                {
                    "path": None,
                    "url": image_source.get("collectionPageUrl")
                    if isinstance(image_source.get("collectionPageUrl"), str)
                    else None,
                    **image_source,
                }
            )
    return out


def build_provenance(
    ref: str,
    *,
    writing_pack: Mapping[str, Any] | None,
    draft_meta: Mapping[str, Any] | None,
    review_payload: Mapping[str, Any] | None,
    compose_payload: Mapping[str, Any] | None,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    wp = writing_pack or {}
    meta = draft_meta or {}
    review = review_payload or {}
    cp = compose_payload or {}
    checks = review.get("checks") or {}
    content_type = str(manifest.get("contentType") or "")
    is_image = content_type == "image" or str(manifest.get("carrier") or "") in (
        "image",
        "gallery",
    )
    final = {
        "contentType": "image" if is_image else (content_type or "article"),
        "publishTitle": manifest.get("publishTitle"),
        "publishSeq": manifest.get("publishSeq"),
        "generator": meta.get("generator") or cp.get("generator"),
        "model": meta.get("model") or cp.get("generatorModel"),
        "agentRunId": meta.get("agentRunId"),
        "agentId": meta.get("agentId"),
        "sessionTrace": meta.get("sessionTrace"),
        "styleFamily": meta.get("styleFamily") or wp.get("styleFamily"),
        "openingStrategy": meta.get("openingStrategy"),
        "entityRefs": list(manifest.get("entityRefs") or []),
    }
    if is_image:
        final.update(
            {
                "assetDigest": cp.get("assetManifestDigest")
                or compute_asset_manifest_sha256(list(manifest.get("assets") or [])),
                **{
                    key: manifest.get(key)
                    for key in (
                        "sourceCollectionId",
                        "creator",
                        "collectionPageUrl",
                        "license",
                        "termsUrl",
                        "authorizationProof",
                    )
                },
            }
        )
    else:
        final["articleDigest"] = cp.get("articleMarkdownDigest") or manifest.get(
            "articleMarkdownDigest"
        )
    return {
        "schemaVersion": PROVENANCE_SCHEMA,
        "ref": ref,
        "final": final,
        "agentInput": {
            "writingPack": f"3.compose/writing_pack.json",
            "prompt": f"4.draft/prompt.md",
            "title": wp.get("title"),
            "styleFamily": wp.get("styleFamily"),
            "promptSha256": meta.get("promptSha256"),
            "writingPackSha256": meta.get("writingPackSha256"),
            "sourceBundleSha256": meta.get("sourceBundleSha256"),
            "draftSha256": meta.get("draftSha256"),
        },
        "originalSources": _original_sources(cp),
        "gateResults": {
            "decision": review.get("decision"),
            "checks": {name: bool(result.get("passed")) for name, result in checks.items()},
        },
        "citedSourcePaths": list(meta.get("citedSourcePaths") or cp.get("citedSourceRefs") or []),
    }


def provenance_issues(post_dir: Path, manifest: Mapping[str, Any]) -> list[str]:
    """强制门：交付 post 必须有完整且一致的 provenance.json（存在 + 完整 + 闭环）。"""
    path = post_dir / PROVENANCE_FILE
    if not path.exists():
        return [f"{post_dir}: missing provenance.json (中间过程与最终结果必须结构化记录)"]
    try:
        data = read_json(path)
    except Exception as exc:  # noqa: BLE001
        return [f"{post_dir}: provenance.json unreadable: {exc}"]
    issues: list[str] = []
    if data.get("schemaVersion") != PROVENANCE_SCHEMA:
        issues.append(f"{post_dir}: provenance.schemaVersion invalid")
    final = data.get("final") or {}
    is_image = str(manifest.get("contentType") or "") == "image" or str(
        manifest.get("carrier") or ""
    ) in ("image", "gallery")
    if is_image:
        expected_digest = compute_asset_manifest_sha256(list(manifest.get("assets") or []))
        if final.get("assetDigest") != expected_digest:
            issues.append(f"{post_dir}: provenance.final.assetDigest != manifest assets digest")
        for key in (
            "sourceCollectionId",
            "creator",
            "collectionPageUrl",
            "license",
            "termsUrl",
            "authorizationProof",
        ):
            if final.get(key) != manifest.get(key):
                issues.append(f"{post_dir}: provenance.final.{key} != manifest.{key}")
    else:
        expected_digest = manifest.get("articleMarkdownDigest")
        if not expected_digest:
            article_path = post_dir / "article.md"
            if article_path.is_file():
                expected_digest = compute_document_sha256(article_path.read_text(encoding="utf-8"))
        if final.get("articleDigest") != expected_digest:
            issues.append(f"{post_dir}: provenance.final.articleDigest != article.md digest")
    if final.get("generator") != "agent":
        issues.append(f"{post_dir}: provenance.final.generator must be 'agent'")
    if not is_image and not str(final.get("agentRunId") or "").strip():
        issues.append(f"{post_dir}: provenance.final.agentRunId missing")
    if not data.get("agentInput"):
        issues.append(f"{post_dir}: provenance.agentInput missing (agent 输入摘要必须记录)")
    agent_input = data.get("agentInput") or {}
    if not is_image:
        for key in ("promptSha256", "writingPackSha256", "sourceBundleSha256", "draftSha256"):
            value = str(agent_input.get(key) or "").strip()
            if not value:
                issues.append(f"{post_dir}: provenance.agentInput.{key} missing")
            elif not value.startswith("sha256:"):
                issues.append(f"{post_dir}: provenance.agentInput.{key} invalid")
    if not data.get("originalSources"):
        issues.append(f"{post_dir}: provenance.originalSources empty (原始数据源必须一一记录)")
    if (data.get("gateResults") or {}).get("decision") != "approved":
        issues.append(f"{post_dir}: provenance.gateResults.decision must be 'approved'")
    original_paths = {str(s.get("path")) for s in (data.get("originalSources") or []) if s.get("path")}
    for cited in data.get("citedSourcePaths") or []:
        if str(cited) not in original_paths:
            issues.append(f"{post_dir}: cited source not in originalSources: {cited}")
    return issues


__all__ = [
    "PROVENANCE_SCHEMA",
    "PROVENANCE_FILE",
    "build_provenance",
    "provenance_issues",
]
