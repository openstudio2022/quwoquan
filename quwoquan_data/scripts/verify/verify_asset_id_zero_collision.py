"""Execution asset-id collision gate."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_ROOT))

from content.execution.asset_registry import execution_asset_registry_path
from content.execution.object_scan import iter_execution_object_dirs
from content.execution.runtime_state import load_execution_runtime_state
from core.asset_identity import parse_post_asset_id
from core.io import read_json
from core.paths import execution_root, iter_all_execution_dirs


def _coerce_execution_sequence(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _scan_manifest_assets(
    manifest: dict,
    *,
    relative_object_path: str,
    issues: list[str],
    seen_asset_ids: dict[str, str],
    execution_sequence: int,
) -> None:
    assets = manifest.get("assets") or []
    if not isinstance(assets, list):
        issues.append(f"{relative_object_path}: manifest.assets must be a list")
        return
    for index, asset in enumerate(assets, start=1):
        if not isinstance(asset, dict):
            issues.append(f"{relative_object_path}: manifest.assets[{index}] must be an object")
            continue
        asset_id = str(asset.get("assetId") or "").strip()
        if not asset_id:
            issues.append(f"{relative_object_path}: manifest.assets[{index}] missing assetId")
            continue
        try:
            parsed = parse_post_asset_id(asset_id)
        except ValueError as exc:
            issues.append(f"{relative_object_path}: invalid assetId {asset_id!r} ({exc})")
            continue
        if execution_sequence > 0 and parsed["executionSequence"] != execution_sequence:
            issues.append(
                f"{relative_object_path}: asset executionSequence mismatch "
                f"({asset_id} => {parsed['executionSequence']} != {execution_sequence})"
            )
        previous = seen_asset_ids.get(asset_id)
        if previous and previous != relative_object_path:
            issues.append(
                f"{relative_object_path}: duplicated assetId {asset_id} also appears in {previous}"
            )
        else:
            seen_asset_ids[asset_id] = relative_object_path
        file_name = str(asset.get("fileName") or "").strip()
        if file_name and Path(file_name).stem != asset_id:
            issues.append(
                f"{relative_object_path}: fileName must be assetId.ext ({file_name} vs {asset_id})"
            )


def scan_execution(execution_id: str) -> list[str]:
    root = execution_root(execution_id)
    if not root.is_dir():
        return [f"execution not found: {root}"]

    runtime_state = load_execution_runtime_state(execution_id)
    execution_sequence = _coerce_execution_sequence(runtime_state.get("executionSequence"))
    if execution_sequence <= 0:
        return [f"{root}: missing executionSequence in runtime_state.json"]

    issues: list[str] = []
    registry_path = execution_asset_registry_path(execution_id)
    registry = read_json(registry_path) if registry_path.is_file() else {}
    if registry and _coerce_execution_sequence(registry.get("executionSequence")) not in (0, execution_sequence):
        issues.append(
            f"{root}: asset registry executionSequence mismatch "
            f"({registry.get('executionSequence')} != {execution_sequence})"
        )

    seen_asset_ids: dict[str, str] = {}
    for object_dir in iter_execution_object_dirs(root):
        manifest_path = object_dir / "manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            payload = read_json(manifest_path)
        except Exception as exc:  # noqa: BLE001
            issues.append(f"{manifest_path}: unreadable ({exc})")
            continue
        relative_object_path = object_dir.relative_to(root).as_posix()
        _scan_manifest_assets(
            payload if isinstance(payload, dict) else {},
            relative_object_path=relative_object_path,
            issues=issues,
            seen_asset_ids=seen_asset_ids,
            execution_sequence=execution_sequence,
        )

    if seen_asset_ids and not registry:
        issues.append(f"{root}: missing asset_id_registry.json")
    if isinstance(registry, dict):
        registry_asset_ids = {
            str(item).strip()
            for item in (registry.get("assetIds") or [])
            if str(item or "").strip()
        }
        missing = sorted(set(seen_asset_ids) - registry_asset_ids)
        extra = sorted(registry_asset_ids - set(seen_asset_ids))
        if missing:
            issues.append(f"{root}: registry missing assetIds: {missing[:10]}")
        if extra:
            issues.append(f"{root}: registry has extra assetIds: {extra[:10]}")
        entries = registry.get("entries") or {}
        if isinstance(entries, dict):
            for owner_key, asset_id in entries.items():
                value = str(asset_id or "").strip()
                if value and value not in seen_asset_ids:
                    issues.append(
                        f"{root}: registry entry {owner_key!r} => {value!r} not found in manifests"
                    )
    return issues


def scan_all() -> list[str]:
    issues: list[str] = []
    for execution_dir in iter_all_execution_dirs():
        issues.extend(scan_execution(execution_dir.name))
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Execution asset-id collision gate")
    parser.add_argument("--execution-id", help="Execution ID")
    args = parser.parse_args(argv)
    issues = scan_execution(args.execution_id) if args.execution_id else scan_all()
    if issues:
        print("FAIL verify_asset_id_zero_collision:")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("PASS verify_asset_id_zero_collision")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
