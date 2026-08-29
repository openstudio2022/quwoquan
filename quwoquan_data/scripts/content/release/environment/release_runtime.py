"""Pure release loading, media sync, and environment action policy."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.release.canonical.release_header import validate_release_header
from content.release.canonical.environment_release_selection import DATA_POST_CAPS
from content.release.environment.topology import (
    EnvironmentReleaseMode,
    EnvironmentReleaseTarget,
)
from content.release.model import FULL_SYNC_RELEASE_KINDS, ReleaseKind
from core.io import read_json, write_json
from core.media_asset_url import (
    is_public_media_slice_key,
    release_media_delivery_key,
)
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
        validate_release_header(header, label=f"release_header:{release_id}")
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


def assert_environment_release_policy(
    *,
    release: Path,
    contract: Mapping[str, Any],
    environment: str,
) -> None:
    """Fail closed on environment mode and Data Post capacity drift."""

    env = str(environment).strip()
    if env not in DATA_POST_CAPS:
        raise SystemExit(
            f"[ship] DATA.RELEASE.ENVIRONMENT_POLICY_INVALID: unsupported environment {env!r}"
        )
    desired_refs = contract.get("desiredRefs")
    posts = desired_refs.get("posts") if isinstance(desired_refs, Mapping) else None
    if not isinstance(posts, list):
        raise SystemExit(
            "[ship] DATA.RELEASE.ENVIRONMENT_POLICY_INVALID: desiredRefs.posts must be an array"
        )
    post_refs = [str(item).strip() for item in posts]
    if any(not item for item in post_refs) or len(post_refs) != len(set(post_refs)):
        raise SystemExit(
            "[ship] DATA.RELEASE.ENVIRONMENT_POLICY_INVALID: Data Post refs must be unique and non-empty"
        )
    cap = DATA_POST_CAPS[env]
    if cap is not None and len(post_refs) > cap:
        raise SystemExit(
            "[ship] DATA.RELEASE.POST_CAP_EXCEEDED: "
            f"environment={env} count={len(post_refs)} cap={cap}"
        )
    header = read_json(payload_file(release, "release.json"))
    target_environment = str(header.get("targetEnvironment") or "").strip()
    if target_environment and target_environment != env:
        raise SystemExit(
            "[ship] DATA.RELEASE.TARGET_ENVIRONMENT_MISMATCH: "
            f"manifest={target_environment} requested={env}"
        )
    release_class = str(header.get("releaseClass") or "").strip()
    lifecycle = str(header.get("productLifecycleState") or "").strip()
    if release_class not in {"research", "commercial"} or lifecycle != release_class:
        raise SystemExit(
            "[ship] DATA.RELEASE.USAGE_SCOPE_MISMATCH: "
            "environment names cannot derive authorization; immutable "
            f"releaseClass/lifecycle={release_class or '<missing>'}/"
            f"{lifecycle or '<missing>'}"
        )


def release_media_public_slices(release: Path) -> dict[str, str]:
    """Map每个交付 key 到其摘要，形态必须与 header releaseClass 一致（DEC-031）。"""
    header_path = payload_file(release, "release.json")
    if not header_path.is_file():
        raise SystemExit(f"[ship] immutable release header 不存在：{header_path}")
    release_class = str(read_json(header_path).get("releaseClass") or "").strip()
    if release_class not in {"research", "commercial"}:
        raise SystemExit(
            "[ship] release header 必须声明 research/commercial releaseClass"
        )
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
        try:
            key = release_media_delivery_key(row)
        except ValueError as exc:
            raise SystemExit(f"[ship] release media manifest 交付 key 非法: {exc}") from exc
        is_public = is_public_media_slice_key(key)
        if release_class == "research" and is_public:
            raise SystemExit(
                f"[ship] research release 不得携带公开交付 slice: {key}"
            )
        if release_class == "commercial" and not is_public:
            raise SystemExit(
                f"[ship] commercial release 不得携带私有交付 key: {key}"
            )
        sha256 = str(row.get("sha256") or "")
        prior = slices.get(key)
        if prior is not None and prior != sha256:
            raise SystemExit(f"[ship] release media manifest 交付 key 摘要冲突: {key}")
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
