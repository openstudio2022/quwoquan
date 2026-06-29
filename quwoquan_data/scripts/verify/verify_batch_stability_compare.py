"""双批次稳定性比对门。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_ROOT))

from _common.asset_identity import parse_post_asset_id  # noqa: E402
from _common.batch_manifest import load_batch_manifest  # noqa: E402
from _common.batch_scan import iter_batch_object_dirs  # noqa: E402
from _common.content_object import load_index as load_content_index  # noqa: E402
from _common.io import read_json, write_json  # noqa: E402
from _common.paths import batch_root  # noqa: E402
from _common.source_unit import iter_source_units  # noqa: E402
from verify.verify_asset_id_zero_collision import scan_batch as scan_zero_collision  # noqa: E402
from verify.verify_directory_evidence_chain import scan_batch as scan_directory  # noqa: E402


def _normalize_path(rel: str) -> str:
    path = Path(rel)
    if len(path.parts) >= 2 and path.parts[-2] == "assets":
        stem = path.stem
        try:
            parse_post_asset_id(stem)
        except ValueError:
            return rel
        return str(path.with_name(f"{{assetId}}{path.suffix}")).replace("\\", "/")
    return rel.replace("\\", "/")


def _dir_tree(batch: Path) -> list[str]:
    files: list[str] = []
    for path in sorted(p for p in batch.rglob("*") if p.is_file()):
        rel = path.relative_to(batch).as_posix()
        files.append(_normalize_path(rel))
    return files


def _page_chars(path: Path) -> int:
    if not path.is_file():
        return 0
    return len("".join(path.read_text(encoding="utf-8").split()))


def _count_source_units(obj: Path) -> int:
    return len(iter_source_units(obj))


def _count_source_images(obj: Path) -> int:
    total = 0
    for unit in iter_source_units(obj):
        idx = unit / "assets" / "index.json"
        if idx.is_file():
            data = read_json(idx)
            assets = data.get("assets") if isinstance(data, dict) else []
            if isinstance(assets, list):
                total += len(assets)
    return total


def _manifest_assets_count(path: Path) -> int:
    if not path.is_file():
        return 0
    data = read_json(path)
    assets = data.get("assets") if isinstance(data, dict) else []
    return len(assets) if isinstance(assets, list) else 0


def _manifest_asset_ids(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    data = read_json(path)
    assets = data.get("assets") if isinstance(data, dict) else []
    out: set[str] = set()
    if isinstance(assets, list):
        for asset in assets:
            if isinstance(asset, dict):
                aid = str(asset.get("assetId") or "").strip()
                if aid:
                    out.add(aid)
    return out


def snapshot_batch(task_id: str, batch_id: str) -> dict[str, Any]:
    batch = batch_root(task_id, batch_id)
    manifest = load_batch_manifest(task_id, batch_id)
    global_batch_seq = int(manifest.get("globalBatchSeq") or 0)
    if global_batch_seq <= 0:
        raise RuntimeError(f"missing globalBatchSeq for task={task_id} batch={batch_id}")
    content_refs = sorted(load_content_index(task_id, batch_id).keys())
    directory_tree = _dir_tree(batch) if batch.is_dir() else []
    object_dirs = iter_batch_object_dirs(batch) if batch.is_dir() else []
    entity_metrics: dict[str, dict[str, Any]] = {}
    post_metrics: dict[str, dict[str, Any]] = {}
    asset_ids: set[str] = set()
    for obj in object_dirs:
        rel = obj.relative_to(batch).as_posix()
        man = obj / "manifest.json"
        obj_assets = _manifest_asset_ids(man)
        asset_ids.update(obj_assets)
        if rel.startswith("entities/"):
            key = obj.name
            entity_metrics[key] = {
                "objectRef": rel,
                "sourceUnitCount": _count_source_units(obj),
                "downloadImageCount": _count_source_images(obj),
                "pageChars": _page_chars(obj / "page.md"),
                "homepageAssetCount": _manifest_assets_count(man),
                "assetIds": sorted(obj_assets),
            }
        elif rel.startswith("posts/"):
            key = rel
            post_metrics[key] = {
                "objectRef": rel,
                "postArticleChars": _page_chars(obj / "article.md"),
                "postAssetCount": _manifest_assets_count(man),
                "reviewDecision": (read_json(man).get("reviewDecision") if man.is_file() else ""),
                "assetIds": sorted(obj_assets),
            }
    return {
        "schemaVersion": "quwoquan_data.e2e_baseline_snapshot/1",
        "taskId": task_id,
        "batchId": batch_id,
        "globalBatchSeq": global_batch_seq,
        "coverageEntities": [str(t.get("name") or "") for t in (manifest.get("coverageTargets") or []) if isinstance(t, dict) and t.get("name")],
        "contentRefs": content_refs,
        "directoryTree": directory_tree,
        "perEntity": entity_metrics,
        "perPost": post_metrics,
        "assetIds": sorted(asset_ids),
        "gateResults": {
            "verify_directory_evidence_chain": "PASS" if not scan_directory(task_id, batch_id) else "FAIL",
            "verify_asset_id_zero_collision": "PASS" if not scan_zero_collision(task_id, batch_id) else "FAIL",
        },
    }


def write_snapshot(path: Path, snapshot: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, snapshot)
    return path


def render_report_md(report: dict[str, Any]) -> str:
    baseline = report.get("baseline") or {}
    candidate = report.get("candidate") or {}
    issues = report.get("issues") or []
    dir_pass = not any("directory tree mismatch" in str(i) for i in issues)
    quality_pass = not any("regressed" in str(i) for i in issues) and not any(
        "reviewDecision not approved" in str(i) for i in issues
    )
    asset_pass = not any("cross-batch assetIds intersect" in str(i) for i in issues)
    lines = [
        "# 双批稳定性比对报告",
        "",
        f"- taskId: `{report.get('taskId')}`",
        f"- passed: `{bool(report.get('passed'))}`",
        f"- baseline batch: `{baseline.get('batchId')}`",
        f"- candidate batch: `{candidate.get('batchId')}`",
        f"- baseline globalBatchSeq: `{baseline.get('globalBatchSeq')}`",
        f"- candidate globalBatchSeq: `{candidate.get('globalBatchSeq')}`",
        "",
        "## 结论",
        "",
        f"- 目录同构: `{ 'PASS' if dir_pass else 'FAIL' }`",
        f"- 质量非回退: `{ 'PASS' if quality_pass else 'FAIL' }`",
        f"- 跨批 assetId 零交集: `{ 'PASS' if asset_pass else 'FAIL' }`",
        "",
        "## 发现的问题",
        "",
    ]
    if issues:
        lines.extend(f"- {issue}" for issue in issues)
    else:
        lines.append("- 无")
    return "\n".join(lines) + "\n"


def write_report(path: Path, report: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".md":
        path.write_text(render_report_md(report), encoding="utf-8")
    else:
        write_json(path, report)
    return path


def _normalize_snapshot_tree(snapshot: dict[str, Any]) -> list[str]:
    return [str(item) for item in snapshot.get("directoryTree") or []]


def compare_snapshots(baseline: dict[str, Any], candidate: dict[str, Any]) -> list[str]:
    issues: list[str] = []

    def _gate_value(snapshot: dict[str, Any], key: str) -> str:
        gate = snapshot.get("gateResults")
        if not isinstance(gate, dict):
            return ""
        return str(gate.get(key) or "")

    if int(candidate.get("globalBatchSeq") or 0) != int(baseline.get("globalBatchSeq") or 0) + 1:
        issues.append(
            f"globalBatchSeq mismatch: baseline={baseline.get('globalBatchSeq')} candidate={candidate.get('globalBatchSeq')}"
        )
    if _gate_value(baseline, "verify_directory_evidence_chain") != "PASS":
        issues.append("baseline directory evidence gate did not pass")
    if _gate_value(baseline, "verify_asset_id_zero_collision") != "PASS":
        issues.append("baseline asset id collision gate did not pass")
    if _gate_value(candidate, "verify_directory_evidence_chain") != "PASS":
        issues.append("candidate directory evidence gate did not pass")
    if _gate_value(candidate, "verify_asset_id_zero_collision") != "PASS":
        issues.append("candidate asset id collision gate did not pass")
    if _normalize_snapshot_tree(baseline) != _normalize_snapshot_tree(candidate):
        issues.append("directory tree mismatch after normalization")
    if set(baseline.get("coverageEntities") or []) != set(candidate.get("coverageEntities") or []):
        issues.append("coverageEntities mismatch")
    if set(baseline.get("contentRefs") or []) != set(candidate.get("contentRefs") or []):
        issues.append("contentRefs mismatch")
    base_entities = baseline.get("perEntity") or {}
    cand_entities = candidate.get("perEntity") or {}
    if set(base_entities) != set(cand_entities):
        issues.append("entity object set mismatch")
    for name, base in base_entities.items():
        cand = cand_entities.get(name)
        if not cand:
            issues.append(f"candidate missing entity metrics: {name}")
            continue
        if int(cand.get("sourceUnitCount") or 0) < int(base.get("sourceUnitCount") or 0):
            issues.append(f"{name}: sourceUnitCount regressed")
        if int(cand.get("downloadImageCount") or 0) < int(base.get("downloadImageCount") or 0):
            issues.append(f"{name}: downloadImageCount regressed")
        if int(cand.get("homepageAssetCount") or 0) < int(base.get("homepageAssetCount") or 0):
            issues.append(f"{name}: homepageAssetCount regressed")
        if int(cand.get("pageChars") or 0) < int(int(base.get("pageChars") or 0) * 0.9):
            issues.append(f"{name}: pageChars regressed")
    base_posts = baseline.get("perPost") or {}
    cand_posts = candidate.get("perPost") or {}
    if set(base_posts) != set(cand_posts):
        issues.append("post object set mismatch")
    for ref, base in base_posts.items():
        cand = cand_posts.get(ref)
        if not cand:
            issues.append(f"candidate missing post metrics: {ref}")
            continue
        if str(cand.get("reviewDecision") or "") != "approved":
            issues.append(f"{ref}: reviewDecision not approved")
        if int(cand.get("postAssetCount") or 0) < int(base.get("postAssetCount") or 0):
            issues.append(f"{ref}: postAssetCount regressed")
        if int(cand.get("postArticleChars") or 0) < int(int(base.get("postArticleChars") or 0) * 0.9):
            issues.append(f"{ref}: postArticleChars regressed")
    if set(baseline.get("assetIds") or []) & set(candidate.get("assetIds") or []):
        issues.append("cross-batch assetIds intersect")
    return issues


def compare_batches(task_id: str, baseline_batch_id: str, candidate_batch_id: str) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    baseline = snapshot_batch(task_id, baseline_batch_id)
    candidate = snapshot_batch(task_id, candidate_batch_id)
    issues = compare_snapshots(baseline, candidate)
    return baseline, candidate, issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="双批次目录同构与质量非回归比对")
    parser.add_argument("--task", required=True, help="Task ID")
    parser.add_argument("--baseline", required=True, help="Baseline batch ID")
    parser.add_argument("--candidate", required=True, help="Candidate batch ID")
    parser.add_argument("--baseline-snapshot-out", help="Optional baseline snapshot path")
    parser.add_argument("--report-out", help="Optional compare report path")
    args = parser.parse_args(argv)

    task_id = args.task
    baseline, candidate, issues = compare_batches(task_id, args.baseline, args.candidate)
    if args.baseline_snapshot_out:
        write_snapshot(Path(args.baseline_snapshot_out), baseline)

    report = {
        "schemaVersion": "quwoquan_data.batch_stability_compare/1",
        "taskId": task_id,
        "baseline": baseline,
        "candidate": candidate,
        "issues": issues,
        "passed": not issues,
    }
    if args.report_out:
        write_report(Path(args.report_out), report)

    if issues:
        print("FAIL verify_batch_stability_compare:")
        for issue in issues:
            print(f"  - {issue}")
        return 1

    print("PASS verify_batch_stability_compare")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
