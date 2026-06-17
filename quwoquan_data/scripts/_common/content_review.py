"""Content review helpers for cold-start data production."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable

from _common.io import read_json
from _common.paths import batch_command_root
from _common.fact_coverage import FACT_COVERAGE_ALIASES, fact_covered
from _common import quality_gates as qg
from _common.template_fingerprints import template_fingerprint_issues


PLATFORM_TERMS = ("马蜂窝", "携程", "小红书", "知乎", "大众点评", "来源平台", "游记里还提到")
NOISE_TERMS = ("这篇主要围绕", "补充：", "contract_fixture", "cold-start.local", "实体引用：", "批次")
PUBLISHER_BANNED_FIELDS = ("authorId", "creatorProfileId", "isSystemBuiltin", "routingReason", "coldStartBoost")


@dataclass(frozen=True)
class ReviewIssue:
    role: str
    ref: str
    severity: str
    message: str


def _article_paths(posts_root: Path) -> list[Path]:
    return sorted(posts_root.rglob("article.md"))


def _load_manifest(article_path: Path) -> dict:
    manifest_path = article_path.parent / "manifest.json"
    if manifest_path.exists():
        return read_json(manifest_path)
    return {}


def _source_names_from_manifest(manifest: dict, fallback_ref: str) -> list[str]:
    names: list[str] = []
    for entity_ref in manifest.get("entityRefs") or []:
        if isinstance(entity_ref, str):
            names.append(entity_ref.split("/")[-1])
    spine = manifest.get("storySpine") or {}
    if isinstance(spine, dict):
        primary = spine.get("primaryEntity")
        if isinstance(primary, str):
            names.insert(0, primary)
    if not names:
        names.append(fallback_ref.split("_")[0])
    return list(dict.fromkeys([name for name in names if name]))


def _load_source_texts(task: str | None, batch: str | None, manifest: dict, fallback_ref: str) -> list[str]:
    if not task or not batch:
        return []
    texts: list[str] = []
    for name in _source_names_from_manifest(manifest, fallback_ref):
        source_root = batch_command_root(task, batch, "download") / "sources" / name
        if not source_root.exists():
            continue
        for source_file in sorted(source_root.rglob("source*.md")):
            try:
                texts.append(source_file.read_text(encoding="utf-8"))
            except Exception:
                continue
    return texts


def _long_phrase_hits(article: str, source_texts: Iterable[str], min_len: int = 28) -> list[str]:
    hits: list[str] = []
    compact_article = re.sub(r"\s+", "", article)
    for text in source_texts:
        cleaned = re.sub(r"\s+", "", text)
        sentences = re.split(r"[。！？\n]", cleaned)
        for sent in sentences:
            sent = sent.strip()
            if len(sent) < min_len:
                continue
            if sent.count("：") >= 1 or sent.count(":") >= 1:
                continue
            if any(label in sent for label in ("交通", "门票", "开放", "最佳季节", "体验时间", "图片来源", "授权状态", "行程", "路线")):
                continue
            if len(re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", sent)) < min_len:
                continue
            if sent in compact_article:
                hits.append(sent[:40])
                if len(hits) >= 5:
                    return hits
    return hits


def check_narrative_quality(article: str, manifest: dict) -> list[str]:
    issues: list[str] = []
    for term in PLATFORM_TERMS:
        if term in article:
            issues.append(f"contains forbidden provenance term: {term}")
    for term in NOISE_TERMS:
        if term in article:
            issues.append(f"contains noisy template term: {term}")
    if article.count("##") >= 7 and "叙事" in str(manifest.get("template", "")):
        issues.append("narrative article uses too many hard section breaks")
    if re.search(r"^> .*displayName", article, flags=re.M):
        issues.append("blockquote leaks displayName")
    if re.search(r"^\s*> .*阿宁在路上", article, flags=re.M):
        issues.append("blockquote leaks system builtin persona")
    if str(manifest.get("carrier") or "") != "gallery" and len(re.sub(r"\s+", "", article)) < 600:
        issues.append("article too short")
    issues.extend(qg.intra_doc_repetition_issues(article))
    return issues


def check_provenance(article_path: Path, task: str | None = None, batch: str | None = None) -> list[str]:
    article = article_path.read_text(encoding="utf-8")
    manifest = _load_manifest(article_path)
    ref = article_path.parent.name
    issues: list[str] = []
    for term in PLATFORM_TERMS:
        if term in article:
            issues.append(f"{ref}: leaked provenance term {term}")
    source_texts = _load_source_texts(task, batch, manifest, ref)
    for hit in _long_phrase_hits(article, source_texts):
        issues.append(f"{ref}: too similar to source phrase '{hit}'")
    if "来源平台：" in article:
        issues.append(f"{ref}: leaked source platform label")
    if "游记里还提到：" in article:
        issues.append(f"{ref}: leaked source hint label")
    if re.search(r"(?m)^实体引用[:：]", article):
        issues.append(f"{ref}: standalone entity-ref block")
    if any(field in article for field in PUBLISHER_BANNED_FIELDS):
        issues.append(f"{ref}: leaked publisher boundary field")
    if manifest and not manifest.get("sourceUrls"):
        issues.append(f"{ref}: missing manifest sourceUrls")
    return issues


def check_story_spine_integrity(article_path: Path, task: str | None = None, batch: str | None = None) -> list[str]:
    article = article_path.read_text(encoding="utf-8")
    spine = _load_manifest(article_path).get("storySpine") or {}
    ref = article_path.parent.name
    issues: list[str] = []
    primary = spine.get("primaryEntity")
    if isinstance(primary, str) and primary and primary not in article:
        issues.append(f"{ref}: primaryEntity missing from article")
    return issues


def check_source_expansion_quality(article_path: Path, task: str | None = None, batch: str | None = None) -> list[str]:
    ref = article_path.parent.name
    issues: list[str] = []
    if not task or not batch:
        return issues
    manifest = _load_manifest(article_path)
    for name in _source_names_from_manifest(manifest, ref):
        source_root = batch_command_root(task, batch, "download") / "sources" / name
        related_path = source_root / "related_search.json"
        if related_path.exists():
            related = read_json(related_path)
            search_terms = related.get("searchTerms") or []
            if not isinstance(search_terms, list) or len(search_terms) < 2:
                issues.append(f"{ref}: related search terms too few for {name}")
        spine_path = source_root / "story_spine.json"
        if spine_path.exists():
            spine = read_json(spine_path)
            if not spine.get("relatedTopics"):
                issues.append(f"{ref}: no relatedTopics in story spine for {name}")
    return issues


def check_image_asset_quality(article_path: Path) -> list[str]:
    manifest = _load_manifest(article_path)
    ref = article_path.parent.name
    issues: list[str] = []
    assets = manifest.get("assets") or []
    if not isinstance(assets, list) or not assets:
        issues.append(f"{ref}: missing assets")
        return issues
    seen: set[str] = set()
    source_assets: list[dict] = []
    for asset in assets:
        if not isinstance(asset, dict):
            issues.append(f"{ref}: asset entry invalid")
            continue
        asset_id = str(asset.get("assetId") or "")
        if not asset_id:
            issues.append(f"{ref}: asset missing assetId")
        if asset_id in seen:
            issues.append(f"{ref}: duplicated assetId {asset_id}")
        seen.add(asset_id)
        source_path = asset.get("sourcePath")
        if isinstance(source_path, str) and not Path(source_path).exists():
            issues.append(f"{ref}: missing sourcePath file {source_path}")
        elif isinstance(source_path, str):
            source_assets.append(asset)
        caption = str(asset.get("caption") or "")
        if not caption.strip():
            issues.append(f"{ref}: asset caption empty")
        if any(term in caption for term in PLATFORM_TERMS):
            issues.append(f"{ref}: asset caption leaks provenance term")
    issues.extend(_image_content_issues(ref, source_assets))
    if "contract_fixture" in article_path.read_text(encoding="utf-8"):
        issues.append(f"{ref}: body leaks contract_fixture")
    return issues


def _image_content_issues(ref: str, source_assets: list[dict]) -> list[str]:
    """真实 CV 图片内容门：水印/平台文字 -> unsafe；人脸/后端缺失 -> needs_review；近重复 -> 阻断。"""
    if not source_assets:
        return []
    from _common.image_safety import assess_asset_sources

    report = assess_asset_sources(source_assets)
    issues: list[str] = []
    for asset_id in report["unsafe"]:
        issues.append(f"{ref}: image unsafe (watermark/platform/copyright) {asset_id}")
    for asset_id in report["needsReview"]:
        issues.append(f"{ref}: image needs human review (face/backend) {asset_id}")
    if report["duplicateGroups"]:
        issues.append(f"{ref}: {len(report['duplicateGroups'])} duplicate image group(s)")
    return issues


def check_editorial_quality(article_path: Path) -> list[str]:
    article = article_path.read_text(encoding="utf-8")
    ref = article_path.parent.name
    issues: list[str] = []
    paragraphs = [p.strip() for p in article.split("\n\n") if p.strip()]
    if len(paragraphs) < 6:
        issues.append(f"{ref}: too few paragraphs")
    avg_len = sum(len(p) for p in paragraphs) / max(len(paragraphs), 1)
    if avg_len < 25:
        issues.append(f"{ref}: paragraphs too terse")
    if article.count("##") > 12:
        issues.append(f"{ref}: too many section breaks")
    return issues


def check_reader_experience(article_path: Path) -> list[str]:
    article = article_path.read_text(encoding="utf-8")
    ref = article_path.parent.name
    issues: list[str] = []
    paragraphs = [p.strip() for p in article.split("\n\n") if p.strip()]
    if "这篇主要围绕" in article:
        issues.append(f"{ref}: has meta intro")
    if "行前核对" in article and "叙事" in ref:
        issues.append(f"{ref}: narrative contains checklist tone")
    if len(paragraphs) >= 3 and all(len(p) < 20 for p in paragraphs[:3]):
        issues.append(f"{ref}: opening lacks narrative density")
    return issues


def check_factual_grounding(article_path: Path, task: str | None = None, batch: str | None = None) -> list[str]:
    article = article_path.read_text(encoding="utf-8")
    manifest = _load_manifest(article_path)
    ref = article_path.parent.name
    issues: list[str] = []
    if task and batch:
        from _common.content_object import read_brief_object

        brief = read_brief_object(task, batch, ref)
        if brief:
            for fact in [str(x) for x in (brief.get("mustIncludeFacts") or []) if x]:
                if not fact_covered(fact, article):
                    issues.append(f"{ref}: mustIncludeFact not reflected: {fact}")
    if manifest and not manifest.get("conditionContext") and any(term in article for term in ("高原", "雪山", "海岛")):
        issues.append(f"{ref}: region-locked term without conditionContext")
    return issues


def check_source_license(article_path: Path, task: str | None = None, batch: str | None = None) -> list[str]:
    ref = article_path.parent.name
    issues: list[str] = []
    if not task or not batch:
        return issues
    manifest = _load_manifest(article_path)
    names = _source_names_from_manifest(manifest, ref)
    for name in names:
        source_root = batch_command_root(task, batch, "download") / "sources" / name
        if not source_root.exists():
            issues.append(f"{ref}: missing download sources for {name}")
            continue
        for source_md in source_root.rglob("source.md"):
            text = source_md.read_text(encoding="utf-8")
            if "license:" not in text and "allowedUse:" not in text:
                issues.append(f"{ref}: source missing license metadata {source_md.parent.name}")
    return issues


def check_publisher_boundary(article_path: Path) -> list[str]:
    article = article_path.read_text(encoding="utf-8")
    ref = article_path.parent.name
    issues: list[str] = []
    for field in PUBLISHER_BANNED_FIELDS:
        if field in article:
            issues.append(f"{ref}: leaked publisher field {field}")
    if re.search(r"^> .*displayName", article, flags=re.M):
        issues.append(f"{ref}: byline still exposes displayName")
    return issues


_NUMERIC_FACT_RE = re.compile(
    r"\d+(?:[.,]\d+)?\s*(?:元|公里|千米|km|KM|米|m|小时|分钟|h|min|度|°C|℃|天|晚|分)"
)
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")


def _normalize_numeric_token(value: str) -> str:
    return value.replace(",", "").replace("，", "").strip()


def numeric_traceability_issues(article: str, source_texts: Iterable[str]) -> list[str]:
    """关键数值可回溯门：正文中带旅行单位的数字必须能在 source 证据里找到，杜绝杜撰票价/海拔/时长。"""
    sources_compact = "".join(re.sub(r"\s+", "", t) for t in source_texts)
    if not sources_compact:
        return []
    normalized_sources_compact = _normalize_numeric_token(sources_compact)
    issues: list[str] = []
    seen: set[str] = set()
    for match in _NUMERIC_FACT_RE.finditer(article):
        token = re.sub(r"\s+", "", match.group(0))
        numbers = _NUMBER_RE.findall(token)
        if not numbers:
            continue
        for num in numbers:
            normalized_num = _normalize_numeric_token(num)
            if normalized_num in seen:
                continue
            seen.add(normalized_num)
            # 至少 2 位的数字才校验（个位数太易巧合）；命中任一 source 即视为可回溯。
            if len(normalized_num.replace(".", "")) < 2:
                continue
            if normalized_num not in normalized_sources_compact:
                issues.append(f"numeric fact not traceable to source: '{token}'")
                break
    return issues


def fact_traceability_issues(article: str, brief: dict, source_texts: Iterable[str]) -> list[str]:
    """mustIncludeFacts 覆盖 + 关键数值可回溯。供 review draft 阶段直接调用（无 manifest）。"""
    issues: list[str] = []
    for fact in [str(x) for x in (brief.get("mustIncludeFacts") or []) if x]:
        if not fact_covered(fact, article):
            issues.append(f"mustIncludeFact not traceable: {fact}")
    issues.extend(numeric_traceability_issues(article, source_texts))
    return issues


def generator_provenance_issues(draft_meta: dict | None) -> list[str]:
    """出处门：正文必须由 generator=agent 创作，并附运行证据与可回查哈希。"""
    if not draft_meta:
        return ["missing draft_meta (no generator provenance)"]
    generator = str(draft_meta.get("generator") or "")
    if generator != "agent":
        return [f"generator is '{generator or 'unknown'}', only 'agent' may be materialized"]
    issues: list[str] = []
    model = str(draft_meta.get("model") or "").strip()
    if not model:
        issues.append("draft_meta missing model")
    elif model == "scaled-e2e/agent":
        issues.append("draft_meta uses blocked pseudo model 'scaled-e2e/agent'")
    if not (draft_meta.get("citedSourcePaths") or []):
        issues.append("draft_meta missing citedSourcePaths")
    if not str(draft_meta.get("agentRunId") or "").strip():
        issues.append("draft_meta missing agentRunId")
    for key in ("promptSha256", "writingPackSha256", "sourceBundleSha256", "draftSha256"):
        value = str(draft_meta.get(key) or "").strip()
        if not value:
            issues.append(f"draft_meta missing {key}")
        elif not value.startswith("sha256:"):
            issues.append(f"draft_meta {key} must use sha256: digest")
    return issues


def check_template_fingerprint(article_path: Path) -> list[str]:
    article = article_path.read_text(encoding="utf-8")
    ref = article_path.parent.name
    return [f"{ref}: {issue}" for issue in template_fingerprint_issues(article)]


def check_generator_provenance(article_path: Path) -> list[str]:
    """交付面出处门：materialized manifest 的 generator 必须为 agent。"""
    manifest = _load_manifest(article_path)
    ref = article_path.parent.name
    if not manifest:
        return []
    generator = str(manifest.get("generator") or "")
    if generator != "agent":
        return [f"{ref}: manifest.generator is '{generator or 'unset'}', only 'agent' content may ship"]
    issues: list[str] = []
    if not str(manifest.get("generatorModel") or "").strip():
        issues.append(f"{ref}: manifest missing generatorModel")
    if not (manifest.get("citedSourceRefs") or []):
        issues.append(f"{ref}: manifest missing citedSourceRefs")
    return issues


def check_fact_traceability(article_path: Path, task: str | None = None, batch: str | None = None) -> list[str]:
    article = article_path.read_text(encoding="utf-8")
    manifest = _load_manifest(article_path)
    ref = article_path.parent.name
    source_texts = _load_source_texts(task, batch, manifest, ref)
    return [f"{ref}: {issue}" for issue in numeric_traceability_issues(article, source_texts)]


def five_role_review(article_path: Path, task: str | None = None, batch: str | None = None) -> dict:
    roles = {
        "editor": check_editorial_quality(article_path),
        "qa": check_reader_experience(article_path) + check_image_asset_quality(article_path) + check_template_fingerprint(article_path),
        "reader": check_reader_experience(article_path),
        "legal": check_provenance(article_path, task, batch) + check_source_license(article_path, task, batch) + check_publisher_boundary(article_path) + check_generator_provenance(article_path),
        "truth": check_factual_grounding(article_path, task, batch) + check_story_spine_integrity(article_path, task, batch) + check_source_expansion_quality(article_path, task, batch) + check_fact_traceability(article_path, task, batch),
    }
    blocking = []
    for role, issues in roles.items():
        blocking.extend(f"{role}: {issue}" for issue in issues)
    return {"roles": roles, "blocking": blocking}
