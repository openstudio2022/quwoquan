#!/usr/bin/env python3
"""语义层内容质量门禁（防模版化回填）。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import argparse
import re
import sys
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_ROOT))

from core.io import read_json  # noqa: E402
from core.fact_coverage import fact_covered  # noqa: E402


STUB_URL_MARKERS = ("cold-start.local", "cold_start.local")
FORBIDDEN_BLOCKS = (r"(?m)^实体引用[:：]",)


def _section_bodies(article: str) -> list[str]:
    parts = re.split(r"\n## ", article)
    bodies = []
    skip_titles = {"延伸阅读", "行前核对", "注意事项"}
    for part in parts[1:]:
        lines = part.split("\n", 1)
        title = lines[0].strip()
        if title in skip_titles:
            continue
        body = lines[1] if len(lines) > 1 else ""
        body = re.sub(r":::figure[\s\S]*?:::", "", body)
        body = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", body)
        bodies.append(re.sub(r"\s+", " ", body).strip())
    return [b for b in bodies if len(b) > 40]


def _jaccard(a: str, b: str) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _load_brief_facts(execution_id: str, ref: str) -> list[str]:
    from content.post.object_index import read_brief_object

    brief = read_brief_object(execution_id, ref)
    return [str(f) for f in (brief or {}).get("mustIncludeFacts", []) if f]


def _post_rel(posts_root: Path, post_dir: Path) -> str:
    try:
        return post_dir.relative_to(posts_root.parent).as_posix()
    except ValueError:
        return post_dir.as_posix()


def _post_allowed(posts_root: Path, post_dir: Path, post_rels: set[str] | None) -> bool:
    if post_rels is None:
        return True
    return _post_rel(posts_root, post_dir) in post_rels


def verify_semantics(
    posts_root: Path,
    execution_id: str | None = None,
    *,
    post_rels: set[str] | None = None,
) -> list[str]:
    issues: list[str] = []
    if not posts_root.exists():
        return [f"posts root missing: {posts_root}"]

    for article_path in sorted(posts_root.rglob("article.md")):
        post_dir = article_path.parent
        if not _post_allowed(posts_root, post_dir, post_rels):
            continue
        manifest_path = post_dir / "manifest.json"
        article = article_path.read_text(encoding="utf-8")
        manifest = read_json(manifest_path) if manifest_path.exists() else {}
        ref = str(manifest.get("topicId") or post_dir.name)

        for pattern in FORBIDDEN_BLOCKS:
            if re.search(pattern, article):
                issues.append(f"{ref}: standalone entity-ref debug block")

        if "围绕「" in article and article.count("围绕「") >= 3:
            issues.append(f"{ref}: template filler phrase '围绕「' repeated")

        bodies = _section_bodies(article)
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                if _jaccard(bodies[i], bodies[j]) > 0.72:
                    issues.append(f"{ref}: sections {i+1} and {j+1} too similar (jaccard>{0.72})")

        source_urls = manifest.get("sourceUrls") or []
        if not source_urls:
            issues.append(f"{ref}: missing sourceUrls")
        elif any(any(m in str(u) for m in STUB_URL_MARKERS) for u in source_urls):
            issues.append(f"{ref}: sourceUrls still use cold-start stub")

        if execution_id:
            facts = _load_brief_facts(execution_id, ref)
            for fact in facts:
                if re.search(rf"请把[^。\n]*{re.escape(fact)}", article):
                    issues.append(f"{ref}: mustIncludeFact '{fact}' appears as schema label only")
                if not fact_covered(fact, article):
                    issues.append(f"{ref}: mustIncludeFact '{fact}' not reflected in body")
            story_spine = manifest.get("storySpine") or {}
            if isinstance(story_spine, dict) and story_spine.get("routeEntities"):
                route_entities = [str(item) for item in story_spine.get("routeEntities") or [] if item]
                if route_entities:
                    mentioned = [name for name in route_entities if name in article]
                    min_covered = min(len(route_entities), 2)
                    if len(mentioned) < min_covered:
                        issues.append(f"{ref}: routeCoverage insufficient ({len(mentioned)}/{len(route_entities)})")
                    if len(route_entities) >= 2:
                        positions = [article.find(name) for name in route_entities if name in article]
                        if positions and positions != sorted(positions):
                            issues.append(f"{ref}: routeCoverage progression order broken")
                        if sum(article.count(term) for term in ("先", "再", "随后", "最后", "一路", "转场", "返程")) < 2:
                            issues.append(f"{ref}: narrativeContinuity lacks progression transitions")
                    headings = re.findall(r"(?m)^##\s+(.+)$", article)
                    if headings:
                        from content.post.object_index import read_brief_object

                        brief = read_brief_object(execution_id, ref)
                        if brief:
                            required = [str(x) for x in (brief.get("structure") or {}).get("required") or []]
                            mirrored = sum(1 for heading in headings if heading in required)
                            if required and mirrored >= max(3, len(required) - 1):
                                issues.append(f"{ref}: narrativeContinuity still mirrors structure.required")
                if "evidenceBundle" in manifest:
                    coverage = (manifest.get("evidenceBundle") or {}).get("coverage") or {}
                    if coverage.get("rejectOnlyEntities"):
                        issues.append(f"{ref}: evidenceQuality reject-only entities {coverage['rejectOnlyEntities']}")

        # assetId 可读化后含中文（如 ..._峨眉山_cover_jpg_xxx）；token 须含中文，
        # 否则正则会在首个中文处截断，把不同图片塌缩成同一 ASCII 前缀，误报"重复使用"。
        asset_ids = re.findall(r"asset://([A-Za-z0-9_./\u4e00-\u9fff-]+)", article)
        if asset_ids:
            from collections import Counter

            counts = Counter(asset_ids)
            if max(counts.values()) > 2:
                issues.append(f"{ref}: same asset reused {max(counts.values())} times in body")

    for manifest_path in sorted(posts_root.rglob("manifest.json")):
        if not _post_allowed(posts_root, manifest_path.parent, post_rels):
            continue
        if (manifest_path.parent / "article.md").exists():
            continue
        ref = manifest_path.parent.name
        data = read_json(manifest_path)
        urls = data.get("sourceUrls") or []
        if urls and any(any(m in str(u) for m in STUB_URL_MARKERS) for u in urls):
            issues.append(f"{ref}: image manifest sourceUrls use stub")

    return issues


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify content semantics")
    parser.add_argument("--execution-id")
    parser.add_argument("--posts-root")
    args = parser.parse_args()

    if args.posts_root:
        root = Path(args.posts_root)
        execution_id = None
    elif args.execution_id:
        from core.paths import execution_posts_root
        root = execution_posts_root(args.execution_id)
        execution_id = args.execution_id
    else:
        print("[semantics] specify --execution-id or --posts-root", file=sys.stderr)
        sys.exit(1)

    issues = verify_semantics(root, execution_id)
    if issues:
        print(f"[semantics] FAILED ({len(issues)} issue(s))", file=sys.stderr)
        for issue in issues:
            print(f"  - {issue}", file=sys.stderr)
        sys.exit(1)
    print(f"[semantics] PASSED: {root}")


if __name__ == "__main__":
    main()
