"""local-gamma 公开媒体根目录的物化与 canonical video 校验。"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
CANONICAL_MEDIA_ROOT = (
    ROOT
    / "quwoquan_service"
    / "contracts"
    / "metadata"
    / "_shared"
    / "test_fixtures"
    / "media"
)
MEDIA_DELIVERY_MANIFEST = (
    ROOT / "quwoquan_ops" / "environments" / "media_delivery_manifest.json"
)
CANONICAL_VIDEO_LOGICAL_ASSET_ID = "content-video-primary"


class LocalGammaMediaError(RuntimeError):
    """表示 local-gamma 公开媒体根无法作为播放平面使用。"""


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def canonical_video_asset() -> dict[str, str]:
    if not MEDIA_DELIVERY_MANIFEST.is_file():
        raise LocalGammaMediaError(
            f"media delivery manifest missing: {MEDIA_DELIVERY_MANIFEST}",
        )
    manifest = json.loads(MEDIA_DELIVERY_MANIFEST.read_text(encoding="utf-8"))
    assets = manifest.get("assets")
    if not isinstance(assets, list):
        raise LocalGammaMediaError("media delivery manifest has no assets list")
    for candidate in assets:
        if (
            isinstance(candidate, dict)
            and str(candidate.get("logicalAssetId") or "").strip()
            == CANONICAL_VIDEO_LOGICAL_ASSET_ID
        ):
            key = str(candidate.get("publicSliceKey") or "").strip().lstrip("/")
            source_hash = str(candidate.get("sha256") or "").strip().lower()
            if key and source_hash.startswith("sha256:"):
                return {"publicSliceKey": key, "sha256": source_hash}
    raise LocalGammaMediaError(
        f"canonical video asset {CANONICAL_VIDEO_LOGICAL_ASSET_ID!r} is missing",
    )


def verify_canonical_video_materialization(target_root: Path) -> dict[str, str]:
    target = target_root.expanduser().resolve()
    asset = canonical_video_asset()
    video_path = target / asset["publicSliceKey"]
    if not video_path.is_file():
        raise LocalGammaMediaError(
            f"canonical video materialization missing: {video_path}",
        )
    actual_hash = _file_sha256(video_path)
    if actual_hash != asset["sha256"]:
        raise LocalGammaMediaError(
            "canonical video hash mismatch: "
            f"expected={asset['sha256']} actual={actual_hash}",
        )
    return {
        "targetRoot": str(target),
        "publicSliceKey": asset["publicSliceKey"],
        "sha256": actual_hash,
    }


def materialize_local_gamma_media(target_root: Path) -> dict[str, Any]:
    """将完整 canonical fixture 媒体树复制到 local-gamma 的受控 cache。"""

    source = CANONICAL_MEDIA_ROOT
    target = target_root.expanduser().resolve()
    if not source.is_dir():
        raise LocalGammaMediaError(f"canonical media root missing: {source}")

    copied_files = 0
    for source_path in source.rglob("*"):
        relative_path = source_path.relative_to(source)
        destination = target / relative_path
        if source_path.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination)
        copied_files += 1

    verified = verify_canonical_video_materialization(target)
    return {
        **verified,
        "sourceRoot": str(source),
        "copiedFiles": copied_files,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("materialize", "verify"):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("--target-root", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    target_root = Path(args.target_root)
    try:
        payload = (
            materialize_local_gamma_media(target_root)
            if args.command == "materialize"
            else verify_canonical_video_materialization(target_root)
        )
    except LocalGammaMediaError as exc:
        print(f"GATE_BLOCK: {exc}")
        return 2
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
