"""Compatibility entrypoint for compact creator publish packages."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from _common.creator_pool.batch_policy import default_target_for_batch
from _common.io import read_json
from _common.paths import PUBLISH_ROOT, SERVICE_CONTRACTS_METADATA_ROOT
from governance.user_pool.media_presets import PRESET_ROOT
from governance.user_pool.rebuild_prefab_users import (
    TRAVEL_PHOTO_BATCH,
    _write_compact_publish,
    rebuild_contract_issues,
)


def run_publish_creators(
    *,
    vertical: str,
    batch_id: str,
    target: int = default_target_for_batch(TRAVEL_PHOTO_BATCH),
    out: Path | None = None,
    mode: str = "commercial",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Project a rebuilt creator seed into compact ``publish/creators``.

    The old publish package wrote a nested 12-file bundle. The current user-pool
    contract deliberately publishes only ``manifest.json`` and ``creators.jsonl``.
    """
    if vertical != "travel":
        raise ValueError("compact creator publish currently supports vertical=travel")
    if batch_id != TRAVEL_PHOTO_BATCH:
        raise ValueError(f"compact creator publish currently supports batch={TRAVEL_PHOTO_BATCH}")
    if mode != "commercial":
        raise ValueError("compact creator publish is a commercial package")
    if out is not None and out != PUBLISH_ROOT / "creators" and str(out) != "quwoquan_data/publish/creators":
        raise ValueError("compact creator publish must write to quwoquan_data/publish/creators")
    preset_manifest = read_json(PRESET_ROOT / "manifest.json")
    seed_path = (
        SERVICE_CONTRACTS_METADATA_ROOT
        / "_shared"
        / "test_fixtures"
        / "creator_pool"
        / f"creator_{batch_id}.seed.json"
    )
    seed = read_json(seed_path)
    users = [row for row in seed.get("users") or [] if isinstance(row, dict)]
    if len(users) != target:
        raise ValueError(f"creator seed users {len(users)} != {target}")
    if not dry_run:
        _write_compact_publish(users, batch_id=batch_id, preset_manifest=preset_manifest)
        issues = rebuild_contract_issues(batch_id=batch_id, target_creators=target)
        if issues:
            raise ValueError("publish-creators gate failed: " + "; ".join(issues[:20]))
    return {
        "batchId": batch_id,
        "target": target,
        "creatorCount": len(users),
        "publishDir": str(PUBLISH_ROOT / "creators"),
        "dryRun": dry_run,
        "files": ["creators.jsonl", "manifest.json"],
    }
