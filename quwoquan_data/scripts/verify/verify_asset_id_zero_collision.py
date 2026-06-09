"""批次资产 ID 零碰撞门。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_ROOT))

from _common.batch_asset_registry import batch_asset_registry_path  # noqa: E402
from _common.batch_manifest import load_batch_manifest  # noqa: E402
from _common.batch_scan import iter_batch_object_dirs  # noqa: E402
from _common.io import read_json  # noqa: E402
from _common.paths import TASKS_ROOT, batch_root  # noqa: E402
from _common.asset_identity import parse_post_asset_id  # noqa: E402


def _coerce_global_batch_seq(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _manifest_assets(manifest: dict, *, rel: str, issues: list[str], seen: dict[str, str], global_seq: int) -> None:
    assets = manifest.get("assets") or []
    if not isinstance(assets, list):
        issues.append(f"{rel}: manifest.assets must be a list")
        return
    for idx, asset in enumerate(assets, start=1):
        if not isinstance(asset, dict):
            issues.append(f"{rel}: manifest.assets[{idx}] must be an object")
            continue
        asset_id = str(asset.get("assetId") or "").strip()
        if not asset_id:
            issues.append(f"{rel}: manifest.assets[{idx}] missing assetId")
            continue
        try:
            parsed = parse_post_asset_id(asset_id)
        except ValueError as exc:
            issues.append(f"{rel}: invalid assetId {asset_id!r} ({exc})")
            continue
        if global_seq > 0 and parsed["globalBatchSeq"] != global_seq:
            issues.append(
                f"{rel}: assetId batch seq mismatch ({asset_id} => {parsed['globalBatchSeq']} != {global_seq})"
            )
        owner = seen.get(asset_id)
        if owner and owner != rel:
            issues.append(f"{rel}: duplicated assetId across batch ({asset_id} also in {owner})")
        else:
            seen[asset_id] = rel
        file_name = str(asset.get("fileName") or "").strip()
        if file_name and Path(file_name).stem != asset_id:
            issues.append(f"{rel}: fileName must be assetId.ext ({file_name} vs {asset_id})")


def scan_batch(task_id: str, batch_id: str) -> list[str]:
    batch = batch_root(task_id, batch_id)
    issues: list[str] = []
    if not batch.is_dir():
        return [f"batch not found: {batch}"]

    manifest = load_batch_manifest(task_id, batch_id)
    global_seq = _coerce_global_batch_seq(manifest.get("globalBatchSeq"))
    if global_seq <= 0:
        return [f"{batch}: missing globalBatchSeq in batch_manifest.json"]

    registry_path = batch_asset_registry_path(task_id, batch_id)
    registry = read_json(registry_path) if registry_path.is_file() else {}
    if registry and _coerce_global_batch_seq(registry.get("globalBatchSeq")) not in (0, global_seq):
        issues.append(
            f"{batch}: registry globalBatchSeq mismatch ({registry.get('globalBatchSeq')} != {global_seq})"
        )

    seen: dict[str, str] = {}
    for obj in iter_batch_object_dirs(batch):
        manifest_path = obj / "manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            obj_manifest = read_json(manifest_path)
        except Exception as exc:  # noqa: BLE001
            issues.append(f"{manifest_path}: unreadable ({exc})")
            continue
        rel = obj.relative_to(batch).as_posix()
        _manifest_assets(obj_manifest if isinstance(obj_manifest, dict) else {}, rel=rel, issues=issues, seen=seen, global_seq=global_seq)

    if seen and not registry:
        issues.append(f"{batch}: missing asset_id_registry.json")
    if registry:
        asset_ids = registry.get("assetIds") or []
        reg_ids = {str(a).strip() for a in asset_ids if str(a or "").strip()}
        if reg_ids != set(seen.keys()):
            missing = sorted(set(seen.keys()) - reg_ids)
            extra = sorted(reg_ids - set(seen.keys()))
            if missing:
                issues.append(f"{batch}: registry missing assetIds: {missing[:10]}")
            if extra:
                issues.append(f"{batch}: registry has extra assetIds: {extra[:10]}")
        entries = registry.get("entries") or {}
        if isinstance(entries, dict):
            for owner_key, asset_id in entries.items():
                aid = str(asset_id or "").strip()
                if aid and aid not in seen:
                    issues.append(f"{batch}: registry entry {owner_key!r} => {aid!r} not found in manifests")
    return issues


def scan_all() -> list[str]:
    issues: list[str] = []
    if not TASKS_ROOT.is_dir():
        return issues
    for batches_dir in TASKS_ROOT.rglob("batches"):
        for batch in sorted(p for p in batches_dir.iterdir() if p.is_dir()):
            task_id, batch_id = _task_batch_from_path(batch)
            manifest = load_batch_manifest(task_id, batch_id)
            if _coerce_global_batch_seq(manifest.get("globalBatchSeq")) <= 0:
                continue
            issues.extend(scan_batch(task_id, batch_id))
    return issues


def _task_batch_from_path(batch: Path) -> tuple[str, str]:
    return str(batch.parent.parent.relative_to(TASKS_ROOT)), batch.name


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="批次资产 ID 零碰撞门")
    parser.add_argument("--task", help="Task ID")
    parser.add_argument("--batch", help="Batch ID")
    args = parser.parse_args(argv)
    if bool(args.task) ^ bool(args.batch):
        print("ERROR: --task 和 --batch 必须同时提供", file=sys.stderr)
        return 2
    issues = scan_batch(args.task, args.batch) if args.task and args.batch else scan_all()
    if issues:
        print("FAIL verify_asset_id_zero_collision:")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("PASS verify_asset_id_zero_collision")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
