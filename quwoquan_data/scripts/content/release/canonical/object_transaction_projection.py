"""Creator and media projection for entity transactions."""

from __future__ import annotations

from content.release.canonical.object_transaction import (
    Any,
    Mapping,
    ObjectTransactionError,
    Path,
    _safe_id,
    _tree_digest,
    project_creator_object,
)


def _project_entity_creator_closure(
    *,
    entity: Mapping[str, Any],
    staging: Path,
) -> tuple[list[str], list[dict[str, object]]]:
    creator_ref = str(entity.get("creatorProfileId") or "").strip()
    if not creator_ref:
        return [], []
    creator_ref = _safe_id(creator_ref, label="creatorProfileId")
    creator_root = project_creator_object(
        creator_ref,
        staging / "creator_objects" / creator_ref,
    )
    return [creator_ref], [
        {
            "creatorRef": creator_ref,
            "packageRef": creator_root.relative_to(staging).as_posix(),
            "treeDigest": _tree_digest(creator_root),
        }
    ]


def _image_dimensions(path: Path) -> tuple[int, int, str]:
    from core.image_decode import probe_image_path

    probe = probe_image_path(path)
    if not probe.succeeded:
        raise ObjectTransactionError(f"发布图片不可解析：{path}: {probe.failure.value}")
    if (
        probe.width <= 0
        or probe.height <= 0
        or not probe.mime_type.startswith("image/")
    ):
        raise ObjectTransactionError(f"发布图片缺有效尺寸或 MIME：{path}")
    return probe.width, probe.height, probe.mime_type
