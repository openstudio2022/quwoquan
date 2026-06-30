#!/usr/bin/env python3
"""Content quality gate for materialized article packages."""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import argparse
import json
import re
import sys
from pathlib import Path

from _common import quality_gates as qg
from _common.article_package import sha256_file
from _common.entity_annotation import annotation_publish_issues
from _common.intersection_signal import intersection_hint_issues
from _common.provenance import provenance_issues
from produce.materialize import _normalized_runtime_entity_refs
# asset:// 引用 token：允许中文实体名（assetId 可读化后含中文）。
_ASSET_REF_RE = re.compile(r"asset://([A-Za-z0-9_./\u4e00-\u9fff-]+)")


FORBIDDEN = ["冷启动", "批次", "角色：", "contract_fixture", "isSystemBuiltin", "routingReason"]
FORBIDDEN_PATTERNS = [
    ("占位稿", "占位稿"),
    ("占位正文", "占位正文"),
    ("占位内容", "占位内容"),
    ("占位图片", "占位图片"),
    ("占位实体", "占位实体"),
    ("占位符", "占位符"),
    ("占位数据", "占位数据"),
]


def forbidden_phrase_hits(article: str) -> list[str]:
    hits = [word for word in FORBIDDEN if word in article]
    for pattern, label in FORBIDDEN_PATTERNS:
        if pattern in article:
            hits.append(label)
    return hits


def _normalized_entity_ref_issues(manifest_path: Path, manifest: dict) -> list[str]:
    issues: list[str] = []
    entity_refs = manifest.get("entityRefs", [])
    normalized_refs = manifest.get("normalizedEntityRefs", [])
    if not isinstance(entity_refs, list):
        return issues
    if normalized_refs is None:
        normalized_refs = []
    if not isinstance(normalized_refs, list):
        issues.append(f"{manifest_path}: normalizedEntityRefs must be an array")
        return issues
    expected = _normalized_runtime_entity_refs([str(ref) for ref in entity_refs if str(ref).strip()])
    actual = [str(ref).strip() for ref in normalized_refs if str(ref).strip()]
    if expected != actual:
        issues.append(
            f"{manifest_path}: normalizedEntityRefs must equal canonicalized entityRefs "
            f"(expected={expected}, actual={actual})"
        )
    for ref in actual:
        if not ref.startswith("entity:") or "/" in ref:
            issues.append(f"{manifest_path}: normalizedEntityRefs must use canonical entity:* format: {ref}")
    return issues


def _default_posts_root(task: str | None, batch: str | None) -> Path | None:
    if task and batch:
        from _common.paths import batch_posts_root
        return batch_posts_root(task, batch)
    return None


def _post_rel(posts_root: Path, post_dir: Path) -> str:
    try:
        return post_dir.relative_to(posts_root.parent).as_posix()
    except ValueError:
        return post_dir.as_posix()


def _post_allowed(posts_root: Path, post_dir: Path, post_rels: set[str] | None) -> bool:
    if post_rels is None:
        return True
    return _post_rel(posts_root, post_dir) in post_rels


def verify_posts(
    posts_root: Path,
    *,
    post_rels: set[str] | None = None,
    advisories: list[str] | None = None,
) -> list[str]:
    issues: list[str] = []
    if not posts_root.exists():
        return issues
    collected: list[tuple[Path, str]] = []  # selected (article_path, article)
    peer_articles: list[tuple[Path, str]] = []  # all articles, used as scoped-review peers
    for article_path in sorted(posts_root.rglob("article.md")):
        post_dir = article_path.parent
        manifest_path = post_dir / "manifest.json"
        article = article_path.read_text(encoding="utf-8")
        peer_articles.append((article_path, article))
        if not _post_allowed(posts_root, post_dir, post_rels):
            continue
        manifest = {}
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        else:
            issues.append(f"{post_dir}: missing manifest.json")
        collected.append((article_path, article))

        for word in forbidden_phrase_hits(article):
            issues.append(f"{article_path}: forbidden phrase found: {word}")
        # 字数门形态自适应（唯一真相源 base_draft_readiness）：图片作品(image/gallery)
        # 不受正文长度门约束；article 长文需≥600，图文混排正文≥200且有足量内联图/图注。
        carrier = str(manifest.get("carrier") or "")
        if carrier not in ("image", "gallery"):
            from _common.base_draft import base_draft_readiness

            readiness = base_draft_readiness(
                article,
                publish_media_mode=str(manifest.get("publishMediaMode") or ""),
            )
            if not readiness["ready"]:
                issues.append(
                    f"{article_path}: article body fails adaptive word gate "
                    f"(form={readiness['sourceForm']} prose={readiness['proseChars']} "
                    f"figures={readiness['inlineFigureCount']} effective={readiness['effectiveChars']}; "
                    f"need long-form>={readiness['minTextChars']} or mixed prose>="
                    f"{readiness['richMixedMinTextChars']}+figures>={readiness['richMixedMinFigures']})"
                )
        if re.search(r"(?m)^标签[:：]", article):
            issues.append(f"{article_path}: standalone tag section is not allowed")

        tag_refs = manifest.get("tagRefs", [])
        entity_refs = manifest.get("entityRefs", [])
        if not isinstance(tag_refs, list) or len(tag_refs) < 2:
            issues.append(f"{manifest_path}: tagRefs must contain at least 2 refs")
        if not isinstance(entity_refs, list):
            issues.append(f"{manifest_path}: entityRefs must be an array")
        issues.extend(_normalized_entity_ref_issues(manifest_path, manifest))
        if not manifest.get("sourceTaskId"):
            issues.append(f"{manifest_path}: missing sourceTaskId provenance (task trace/hydrate 必需)")

        issues.extend(asset_closure_issues(post_dir, manifest))
        # 出处强制门：交付 post 必须有完整且一致的 provenance.json。
        issues.extend(provenance_issues(post_dir, manifest))
        # 实体标注强制门：manifest.entityRefs 每个实体必须在正文 inline 标注并登记闭环。
        issues.extend(annotation_publish_issues(article, entity_refs if isinstance(entity_refs, list) else []))
        # 「明」交集信号强制门：每个 post 必须有完备的 intersectionHints（对齐 IntersectionReason 闭集）。
        issues.extend(intersection_hint_issues(manifest.get("intersectionHints"), manifest))
        # 发布面复跑单一门库语义门：不只信 review.json=approved。软门进 advisories（不 hard-block）。
        issues.extend(_semantic_gate_issues(article_path, article, manifest, advisories=advisories))

    # 跨篇模板骨架门 + SimHash 语义去重双指标：换实体名同骨架在发布面也要拦。
    all_articles = [art for _, art in peer_articles]
    all_article_hashes = {path: qg.simhash64(art) for path, art in peer_articles}
    for path, art in collected:
        peers = [other for peer_path, other in peer_articles if peer_path != path]
        peer_hashes = [
            all_article_hashes[peer_path]
            for peer_path, _other in peer_articles
            if peer_path != path
        ]
        for msg in qg.skeleton_similarity_issues(art, peers):
            issues.append(f"{path}: {msg}")
        for msg in qg.semantic_duplicate_issues(
            art,
            peers,
            article_hash=all_article_hashes[path],
            peer_hashes=peer_hashes,
        ):
            issues.append(f"{path}: {msg}")
    return issues


def _semantic_gate_issues(
    article_path: Path,
    article: str,
    manifest: dict,
    *,
    advisories: list[str] | None = None,
) -> list[str]:
    """复用单一 gate library，在发布面复跑图文闭环/主线一致性/语域门。

    软门（``quality_gates.SOFT_QUALITY_GATES``：writingIntentConsistency / mechanicalHeading）
    命中只进 ``advisories``（软扣分+建议），绝不 hard-block；与 produce review 的 SOFT_CHECKS
    同口径（消除第二真相源）。硬门（图文闭环/语域/联系方式/段内重复）仍 hard-block。
    """
    out: list[str] = []
    advisory_sink = advisories if advisories is not None else []
    carrier = str(manifest.get("carrier") or "article")
    assets = manifest.get("assets") if isinstance(manifest.get("assets"), list) else []
    route_nodes = manifest.get("routeNodes") or manifest.get("routeNodeRefs") or []
    route_node_count = len(route_nodes) if isinstance(route_nodes, list) else 0
    for msg in qg.image_reference_closure_issues(article, assets, carrier=carrier, route_node_count=route_node_count):
        out.append(f"{article_path}: {msg}")
    writing_intent = manifest.get("writingIntent")
    if writing_intent:
        # 软门：写作主线一致性（启发式），降软扣分不 hard-block。
        for msg in qg.writing_intent_consistency_issues(article, writing_intent):
            advisory_sink.append(f"{article_path}: [soft:writingIntentConsistency] {msg}")
    banned = manifest.get("bannedRegisterTerms")
    if isinstance(banned, list) and banned:
        for msg in qg.register_lexicon_issues(article, [str(b) for b in banned]):
            out.append(f"{article_path}: {msg}")
    from _common import public_contacts as pc

    allowed_contacts = manifest.get("allowedContactNumbers") if isinstance(manifest.get("allowedContactNumbers"), list) else []
    for msg in qg.contact_info_issues(article, allowed_numbers=pc.allowed_numbers([str(n) for n in allowed_contacts])):
        out.append(f"{article_path}: {msg}")
    heading_extra = manifest.get("mechanicalHeadingTerms") if isinstance(manifest.get("mechanicalHeadingTerms"), list) else []
    # 软门：机械化清单式小标题（启发式），降软扣分不 hard-block。
    for msg in qg.mechanical_heading_issues(article, extra_terms=[str(t) for t in heading_extra]):
        advisory_sink.append(f"{article_path}: [soft:mechanicalHeading] {msg}")
    for msg in qg.intra_doc_repetition_issues(article):
        out.append(f"{article_path}: {msg}")
    return out


def _asset_index(manifest: dict) -> tuple[dict[str, str], dict[str, str]]:
    """返回 (assetId→fileName, assetId→sha256)。fileName/sha256 取顶层 assets。"""

    id_to_file: dict[str, str] = {}
    for asset in manifest.get("assets") or []:
        if isinstance(asset, dict) and asset.get("assetId"):
            id_to_file[str(asset["assetId"])] = str(asset.get("fileName") or "")
    id_to_sha: dict[str, str] = {}
    for asset in manifest.get("assets") or []:
        if isinstance(asset, dict) and asset.get("assetId"):
            id_to_sha[str(asset["assetId"])] = str(asset.get("sha256") or "")
    return id_to_file, id_to_sha


def _referenced_asset_ids(post_dir: Path) -> set[str]:
    """收集 article.md + gallery.md 内的全部 asset:// 引用 id（含 frontmatter coverImage）。"""
    refs: set[str] = set()
    for md_name in ("article.md", "gallery.md"):
        md_path = post_dir / md_name
        if not md_path.is_file():
            continue
        for ref in _ASSET_REF_RE.findall(md_path.read_text(encoding="utf-8")):
            refs.add(ref.split("/")[-1])
    return refs


def asset_closure_issues(post_dir: Path, manifest: dict) -> list[str]:
    """asset:// 引用闭环：引用 → manifest.assets → fileName → 物理文件 → sha256 全链可追。

    评审痛点「图片找不到对应资源文件」的硬门：
    1. 正向——article/gallery 的每个 asset:// 引用都能在 manifest 命中（assetId 或 fileName）；
    2. 物理——每个声明 asset 的 assets/<fileName> 真实存在于盘上；
    3. 一致——若 manifest.assets 记录了 sha256，则物理文件摘要必须与之一致。
    """
    issues: list[str] = []
    id_to_file, id_to_sha = _asset_index(manifest)
    known_ids = set(id_to_file) | set(id_to_sha)
    file_names = {name for name in id_to_file.values() if name}
    assets_dir = post_dir / "assets"

    for ref in sorted(_referenced_asset_ids(post_dir)):
        if ref not in known_ids and ref not in file_names:
            issues.append(f"{post_dir}: asset ref not in manifest: {ref}")

    for asset_id, file_name in id_to_file.items():
        if not file_name:
            issues.append(f"{post_dir}: asset {asset_id} missing fileName in manifest")
            continue
        physical = assets_dir / file_name
        if not physical.is_file():
            issues.append(f"{post_dir}: asset file missing on disk: assets/{file_name} (assetId={asset_id})")
            continue
        expected = id_to_sha.get(asset_id)
        if expected:
            actual = sha256_file(physical)
            if actual != expected:
                issues.append(
                    f"{post_dir}: asset sha256 mismatch for {file_name}: manifest={expected} disk={actual}"
                )
    return issues


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify materialized content quality")
    parser.add_argument("--task")
    parser.add_argument("--batch")
    parser.add_argument("--posts-root")
    args = parser.parse_args()

    posts_root = Path(args.posts_root) if args.posts_root else _default_posts_root(args.task, args.batch)
    if posts_root is None:
        print("[content-quality] No posts root specified; template-only gate skipped")
        return
    advisories: list[str] = []
    issues = verify_posts(posts_root, advisories=advisories)
    if advisories:
        # 软门（情感密度/写作主线/机械小标题/机械结尾）只软提示，不计入 FAIL。
        print(f"[content-quality] {len(advisories)} soft advisory(ies) (non-blocking):")
        for advisory in advisories:
            print(f"  ~ {advisory}")
    if issues:
        print(f"[content-quality] FAILED ({len(issues)} issue(s))", file=sys.stderr)
        for issue in issues:
            print(f"  - {issue}", file=sys.stderr)
        sys.exit(1)
    print(f"[content-quality] PASSED: {posts_root}")


if __name__ == "__main__":
    main()
