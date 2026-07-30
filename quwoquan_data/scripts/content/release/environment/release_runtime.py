"""Pure release loading, media sync, and environment action policy."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.release.environment.topology import (
    EnvironmentReleaseMode,
    EnvironmentReleaseTarget,
)
from content.release.model import FULL_SYNC_RELEASE_KINDS, ReleaseKind
from core.io import read_json, write_json
from core.media_asset_url import is_public_media_slice_key
from core.media_library_sync import sync_media_library
from core.release_layout import payload_file, payload_root
from core.schema import assert_valid


def load_release(release_root: Path, release_id: str) -> tuple[Path, dict[str, Any]]:
    release = release_root / release_id
    desired = payload_file(release, "desired_state.json")
    if not desired.is_file():
        raise SystemExit(f"[ship] immutable release desired_state 不存在：{desired}")
    contract = read_json(desired)
    header = read_json(payload_file(release, "release.json"))
    try:
        assert_valid(
            contract,
            "release",
            "release_desired_state",
            label=f"desired_state:{release_id}",
        )
        assert_valid(
            header,
            "release",
            "release_header",
            label=f"release_header:{release_id}",
        )
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(f"[ship] immutable release contract invalid: {exc}") from exc
    if contract.get("releaseId") != release_id or header.get("releaseId") != release_id:
        raise SystemExit("[ship] immutable release identity differs from requested release")
    return release, contract


def release_requires_full_sync(release: Path) -> bool:
    header = read_json(payload_file(release, "release.json"))
    try:
        return ReleaseKind(str(header.get("releaseKind") or "")) in FULL_SYNC_RELEASE_KINDS
    except ValueError as exc:
        raise SystemExit("[ship] releaseKind is invalid") from exc


def release_has_posts(contract: Mapping[str, Any]) -> bool:
    desired_refs = contract.get("desiredRefs")
    if not isinstance(desired_refs, Mapping):
        raise SystemExit("[ship] release desiredRefs is invalid")
    posts = desired_refs.get("posts")
    if not isinstance(posts, list):
        raise SystemExit("[ship] release desiredRefs.posts is invalid")
    return bool(posts)


def release_media_public_slices(release: Path) -> dict[str, str]:
    manifest = read_json(payload_file(release, "media_manifest.json"))
    if manifest.get("schema") != "quwoquan_data.release_media_manifest":
        raise SystemExit("[ship] release media manifest schema 无效")
    assets = manifest.get("assets")
    if not isinstance(assets, list):
        raise SystemExit("[ship] release media manifest assets 必须为数组")
    slices: dict[str, str] = {}
    for index, row in enumerate(assets):
        if not isinstance(row, Mapping):
            raise SystemExit(f"[ship] release media manifest assets[{index}] 必须为对象")
        key = str(row.get("publicSliceKey") or "")
        if not is_public_media_slice_key(key):
            raise SystemExit(f"[ship] release media manifest 含非法 public slice: {key}")
        sha256 = str(row.get("sha256") or "")
        prior = slices.get(key)
        if prior is not None and prior != sha256:
            raise SystemExit(f"[ship] release media manifest public slice 摘要冲突: {key}")
        slices[key] = sha256
    return dict(sorted(slices.items()))


def sync_media(*, release: Path, destination: str, run: Path) -> None:
    report = sync_media_library(
        payload_root(release),
        Path(destination),
        object_digests=release_media_public_slices(release),
        prune_unselected=True,
    )
    write_json(run / "media-sync.json", report)
    if report["failed"] or report["issues"]:
        raise SystemExit(f"[ship] media sync failed: {report['issues'][:5]}")


def assert_target_action_allowed(
    *,
    target: EnvironmentReleaseTarget,
    import_to_db: bool,
    dry_run: bool,
    action: str,
) -> None:
    if not import_to_db:
        return
    if target.mode is EnvironmentReleaseMode.PROJECTION_ONLY:
        raise SystemExit(
            f"[ship] {target.environment.value} is projection-only; database {action} is not a valid environment action"
        )
    if target.missing_requirements and not dry_run:
        raise SystemExit(
            f"[ship] environment release target is not ready for {action}; "
            "missing secret inputs: " + ", ".join(target.missing_requirements)
        )
