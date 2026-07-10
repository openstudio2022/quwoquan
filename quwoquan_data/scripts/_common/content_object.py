"""内容对象路由：ref → `posts/{contentType}/{angle}/{title}/{seq}/`（规格 §2.4/§2.5/§15）。

对象优先布局把 produce 过程产物（`3.compose`/`4.draft`/`5.review`）与成品都挂在**同一个
内容对象目录**下。内容对象坐标在
brief 阶段即可确定（全部来自 brief，不依赖 agent 创作）：

- `contentType` = produce `--type`（默认 `article`）。
- `angle` = `_publish_angle(brief)`（底稿派生内容类目：image→画报，否则按 writingIntent 派生标签）。
- `title` = `brief.titleHint`（文章与公开图片标题同源；image/gallery 若公开标题缺失，内部对象坐标允许回退到 `ref`，但该回退不得复制到 `publishTitle`）。
- `seq` = 默认 `1`；同 `(type,angle,title)` 组多 ref 按 ref 稳定排序递增（与 promote/materialize 对齐）。

`ref → coords` 路由持久化在 `batches/{batch}/_shared/content_object_index.json`，作为批次内
ref→对象的**唯一路由真相**，供 draft_io / stage 写入 / materialize / 读取端一致解析，避免再
出现「同一 ref 在不同阶段目录间漂移」。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from datetime import datetime, timezone

from _common.io import read_json, write_json
from _common.paths import (
    OBJECT_STAGES,
    STAGE_COMPOSE,
    batch_post_object_dir,
    batch_post_stage_dir,
    batch_root,
    batch_shared_dir,
    object_index_path,
)

CONTENT_OBJECT_INDEX = "content_object_index.json"
INDEX_SCHEMA = "quwoquan_data.content_object_index"
OBJECT_INDEX_SCHEMA = "quwoquan.object.index"
BRIEF_FILE = "brief.json"


def index_path(task_id: str, batch_id: str) -> Path:
    return batch_shared_dir(task_id, batch_id) / CONTENT_OBJECT_INDEX


def load_index(task_id: str, batch_id: str) -> dict[str, dict[str, Any]]:
    path = index_path(task_id, batch_id)
    if not path.is_file():
        return {}
    data = read_json(path)
    refs = data.get("refs") if isinstance(data, dict) else None
    return refs if isinstance(refs, dict) else {}


def content_type_from_brief(brief: Mapping[str, Any]) -> str:
    """Image/gallery carriers live under posts/image; prose lives under article."""
    return "image" if str(brief.get("carrier") or "") in ("image", "gallery") else "article"


def require_title_hint(brief: Mapping[str, Any], *, ref: str = "") -> str:
    """发布标题真相源：compose 阶段必须给出非空 titleHint，禁止回退到 ref/空串。"""
    title = str(brief.get("titleHint") or "").strip()
    if title:
        return title
    if str(brief.get("carrier") or "") in ("image", "gallery") and ref:
        # Image titles are optional publicly; the ref is only a stable routing
        # coordinate and must not be copied into publishTitle.
        return ref
    suffix = f" for ref={ref!r}" if ref else ""
    raise ValueError(f"titleHint missing or empty{suffix}; publish title must be decided before content object routing")


def compute_content_coords(
    brief: Mapping[str, Any],
    content_type: str = "article",
    *,
    ref: str = "",
) -> dict[str, Any]:
    """从 brief 确定性算出内容对象坐标（angle/title），不含 seq。"""
    from produce.route_workflow import _publish_angle  # 延迟导入避免循环依赖

    angle = _publish_angle(brief)
    title = require_title_hint(brief, ref=ref)
    return {"contentType": content_type, "angle": angle, "title": title}


def _enforce_single_batch_content_type(
    task_id: str, batch_id: str, content_type: str, *, ref: str = ""
) -> None:
    """目录规范硬门：一个批次只允许一个 contentType，禁止混批。

    批次声明真相源是 batch_manifest.json.contentType（homepage/article/image/video）；
    内容对象 content_type（article/image/...）必须与之一致。manifest 未声明
    contentType（legacy 批次）时不拦截，由 legacy 只读策略兜底。
    """
    from _common.batch_manifest import load_batch_manifest  # 延迟导入避免循环依赖

    declared = str(load_batch_manifest(task_id, batch_id).get("contentType") or "").strip()
    if not declared:
        return
    if str(content_type or "").strip() != declared:
        raise ValueError(
            f"batch contentType mixed: batch={batch_id} declared={declared!r} "
            f"but object ref={ref!r} contentType={content_type!r}; "
            "一批次只允许一个 contentType，请为其它内容类型另起批次"
        )


def register_content_object(
    task_id: str,
    batch_id: str,
    ref: str,
    *,
    content_type: str,
    angle: str,
    title: str,
    seq: int | None = None,
) -> dict[str, Any]:
    """登记/刷新 ref→coords 路由（幂等）。

    seq 一旦分配就不能因后续同标题 ref 注册而漂移；对象阶段文件已经写入
    posts/{type}/{angle}/{title}/{seq}/，重排旧 seq 会让已落盘 brief/draft 与索引脱节。
    """
    title = str(title or "").strip()
    if not title:
        raise ValueError(f"content object title missing or empty for ref={ref!r}")
    _enforce_single_batch_content_type(task_id, batch_id, content_type, ref=ref)
    index = load_index(task_id, batch_id)
    existing = index.get(ref) or {}
    if seq is not None:
        next_seq = int(seq)
    elif existing.get("seq"):
        next_seq = int(existing.get("seq") or 1)
    else:
        group_seqs = [
            int(c.get("seq") or 0)
            for c in index.values()
            if c.get("contentType") == content_type
            and c.get("angle") == angle
            and c.get("title") == title
        ]
        next_seq = max(group_seqs or [0]) + 1
    index[ref] = {"contentType": content_type, "angle": angle, "title": title, "seq": next_seq}
    write_json(index_path(task_id, batch_id), {"schemaVersion": INDEX_SCHEMA, "refs": index})
    return index[ref]


def register_from_brief(
    task_id: str, batch_id: str, ref: str, brief: Mapping[str, Any], content_type: str = "article"
) -> dict[str, Any]:
    coords = compute_content_coords(brief, content_type, ref=ref)
    return register_content_object(
        task_id, batch_id, ref,
        content_type=coords["contentType"], angle=coords["angle"], title=coords["title"],
    )


def content_coords(task_id: str, batch_id: str, ref: str) -> dict[str, Any] | None:
    return load_index(task_id, batch_id).get(ref)


def _coords_or_raise(task_id: str, batch_id: str, ref: str) -> dict[str, Any]:
    coords = content_coords(task_id, batch_id, ref)
    if not coords:
        raise KeyError(
            f"content object not registered for ref={ref!r} (task={task_id} batch={batch_id}); "
            f"call register_from_brief at compose-brief time"
        )
    return coords


def content_object_dir(task_id: str, batch_id: str, ref: str) -> Path:
    c = _coords_or_raise(task_id, batch_id, ref)
    return batch_post_object_dir(
        task_id, batch_id, c["contentType"], c["angle"], c["title"], int(c.get("seq") or 1)
    )


def content_object_stage_dir(task_id: str, batch_id: str, ref: str, stage: str) -> Path:
    c = _coords_or_raise(task_id, batch_id, ref)
    return batch_post_stage_dir(
        task_id, batch_id, c["contentType"], c["angle"], c["title"], int(c.get("seq") or 1), stage
    )


def iter_content_refs(task_id: str, batch_id: str) -> list[str]:
    return sorted(load_index(task_id, batch_id).keys())


def content_object_rel(task_id: str, batch_id: str, ref: str) -> str:
    """内容对象根相对 batch 根的 POSIX 路径（= publish 根同名相对路径）。"""
    obj = content_object_dir(task_id, batch_id, ref)
    return obj.relative_to(batch_root(task_id, batch_id)).as_posix()


def write_content_object_index(task_id: str, batch_id: str, ref: str) -> Path:
    """写内容对象 `_object.json`（§14.3）：publish 目标相对路径 + 成品相对路径 + 各阶段状态。"""
    obj_dir = content_object_dir(task_id, batch_id, ref)
    rel = obj_dir.relative_to(batch_root(task_id, batch_id)).as_posix()
    stages = {
        stage: ("done" if (obj_dir / stage).is_dir() else "pending")
        for stage in OBJECT_STAGES
    }
    path = object_index_path(obj_dir)
    write_json(
        path,
        {
            "schemaVersion": OBJECT_INDEX_SCHEMA,
            "objectKind": "content",
            "objectRef": ref,
            "publishTargetRef": rel,
            "finalRef": rel,
            "stages": stages,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        },
    )
    return path


# ---------------------------------------------------------------------------
# brief 输入（compose brief）：对象 3.compose/brief.json
# ---------------------------------------------------------------------------


def write_brief_object(
    task_id: str, batch_id: str, ref: str, brief: Mapping[str, Any], content_type: str = "article"
) -> Path:
    """登记路由并把 compose brief 落对象 `3.compose/brief.json`。"""
    payload = dict(brief)
    from _common.paths import batch_manifest_path

    manifest_path = batch_manifest_path(task_id, batch_id)
    if manifest_path.is_file() and not payload.get("globalBatchSeq"):
        manifest = read_json(manifest_path)
        if isinstance(manifest, dict) and manifest.get("globalBatchSeq") is not None:
            try:
                payload["globalBatchSeq"] = int(manifest["globalBatchSeq"])
            except (TypeError, ValueError):
                pass
    register_from_brief(task_id, batch_id, ref, payload, content_type)
    from _common.paths import STAGE_COMPOSE, ensure_object_stages

    obj_dir = content_object_dir(task_id, batch_id, ref)
    ensure_object_stages(obj_dir, through_stage=STAGE_COMPOSE)
    path = content_object_stage_dir(task_id, batch_id, ref, STAGE_COMPOSE) / BRIEF_FILE
    write_json(path, payload)
    return path


def read_brief_object(task_id: str, batch_id: str, ref: str) -> dict[str, Any] | None:
    """读 compose brief：仅读取对象 `3.compose/brief.json`。"""
    if content_coords(task_id, batch_id, ref):
        path = content_object_stage_dir(task_id, batch_id, ref, STAGE_COMPOSE) / BRIEF_FILE
        if path.is_file():
            return read_json(path)
    return None


def iter_briefs(task_id: str, batch_id: str) -> list[tuple[str, dict[str, Any]]]:
    """(ref, brief) 列表：仅枚举已登记的对象 brief。"""
    out: list[tuple[str, dict[str, Any]]] = []
    for ref in iter_content_refs(task_id, batch_id):
        brief = read_brief_object(task_id, batch_id, ref)
        if brief is not None:
            out.append((ref, brief))
    return out


def has_briefs(task_id: str, batch_id: str) -> bool:
    for ref in iter_content_refs(task_id, batch_id):
        if read_brief_object(task_id, batch_id, ref) is not None:
            return True
    return False
