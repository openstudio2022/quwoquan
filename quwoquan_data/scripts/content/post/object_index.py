"""内容对象路由：ref → `posts/{contentType}/{angle}/{title}/{seq}/`（规格 §2.4/§2.5/§15）。

对象优先布局把 post 过程产物（`3.compose`/`4.draft`/`5.review`）与成品都挂在**同一个
内容对象目录**下。内容对象坐标在
brief 阶段即可确定（全部来自 brief，不依赖 agent 创作）：

- `contentType` = post `--type`（默认 `article`）。
- `angle` = `_publish_angle(brief)`（底稿派生内容类目：image→画报，否则按 writingIntent 派生标签）。
- `title` = `brief.titleHint`（文章与公开图片标题同源；image/gallery 若公开标题缺失，内部对象坐标允许回退到 `ref`，但该回退不得复制到 `publishTitle`）。
- `seq` = 默认 `1`；同 `(type,angle,title)` 组多 ref 按 ref 稳定排序递增（与 promote/materialize 对齐）。

`ref → coords` 路由持久化在 `tasks/{executionId}/_shared/content_object_index.json`，作为批次内
ref→对象的**唯一路由真相**，供 draft_io / stage 写入 / materialize / 读取端一致解析，避免再
出现「同一 ref 在不同阶段目录间漂移」。
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from core import paths as core_paths
from core.control_types import ContentType
from core.io import read_json, write_json
from core.paths import (
    OBJECT_STAGES,
    STAGE_COMPOSE,
    execution_post_object_dir,
    execution_post_stage_dir,
    execution_root,
    execution_shared_dir,
    object_index_path,
)

CONTENT_OBJECT_INDEX = "content_object_index.json"
INDEX_SCHEMA = "quwoquan_data.content_object_index"
OBJECT_INDEX_SCHEMA = "quwoquan.object.index"
BRIEF_FILE = "brief.json"


def _canonical_group_sequences(
    *,
    content_type: str,
    angle: str,
    title: str,
) -> tuple[int, ...]:
    """Return already materialized canonical versions for one post identity.

    A campaign can publish some lanes before another lane fails.  A later
    execution must then freeze the next immutable post version before authoring
    instead of rebuilding ``.../<title>/1`` and colliding only at transaction
    time.  Directory names are not inferred as evidence unless the version has
    a canonical manifest.
    """
    group = core_paths.PUBLISH_ROOT / "posts" / content_type / angle / title
    if not group.is_dir():
        return ()
    versions: list[int] = []
    for child in group.iterdir():
        if not child.is_dir() or not child.name.isdigit():
            continue
        if not (child / "manifest.json").is_file():
            continue
        versions.append(int(child.name))
    return tuple(sorted(set(versions)))


def index_path(execution_id: str) -> Path:
    return execution_shared_dir(execution_id) / CONTENT_OBJECT_INDEX


def load_index(execution_id: str) -> dict[str, dict[str, Any]]:
    path = index_path(execution_id)
    if not path.is_file():
        return {}
    data = read_json(path)
    refs = data.get("refs") if isinstance(data, dict) else None
    return refs if isinstance(refs, dict) else {}


def content_type_from_brief(brief: Mapping[str, Any]) -> str:
    """Resolve the sole post content type from the carrier contract."""
    carrier = str(brief.get("carrier") or ContentType.ARTICLE.value)
    try:
        content_type = ContentType(carrier)
    except ValueError as exc:
        raise ValueError(f"unsupported post carrier: {carrier!r}") from exc
    if content_type is ContentType.HOMEPAGE:
        raise ValueError("homepage is not a post carrier")
    return content_type.value


def require_title_hint(brief: Mapping[str, Any], *, ref: str = "") -> str:
    """发布标题真相源：compose 阶段必须给出非空 titleHint，禁止回退到 ref/空串。"""
    title = str(brief.get("titleHint") or "").strip()
    if title:
        return title
    if str(brief.get("carrier") or "") == "image" and ref:
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
    from content.post.article.route_core import _publish_angle  # 延迟导入避免循环依赖

    angle = _publish_angle(brief)
    title = require_title_hint(brief, ref=ref)
    return {"contentType": content_type, "angle": angle, "title": title}


def _validate_execution_and_object_content_types(
    execution_id: str, content_type: str, *, ref: str = ""
) -> None:
    """Require one canonical content type for the complete execution package."""
    from content.execution.identity import ContentType, parse_execution_id

    execution_content_type = parse_execution_id(execution_id).content_type
    try:
        object_content_type = ContentType(str(content_type or "").strip())
    except ValueError as exc:
        raise ValueError(
            f"content object type invalid: execution={execution_id} "
            f"ref={ref!r} contentType={content_type!r}"
        ) from exc
    if object_content_type is not execution_content_type:
        raise ValueError(
            "content object type conflicts with immutable execution identity: "
            f"execution={execution_id} executionContentType={execution_content_type.value!r} "
            f"ref={ref!r} objectContentType={object_content_type.value!r}; "
            "create a separate execution for the other carrier"
        )


def register_content_object(
    execution_id: str,
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
    # A content object is runtime output, so it may only be created inside an
    # execution package whose immutable plan has already been frozen.
    from content.execution.workspace import load_execution_manifest

    load_execution_manifest(execution_id)
    _validate_execution_and_object_content_types(execution_id, content_type, ref=ref)
    index = load_index(execution_id)
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
        canonical_seqs = _canonical_group_sequences(
            content_type=content_type,
            angle=angle,
            title=title,
        )
        next_seq = max([*group_seqs, *canonical_seqs, 0]) + 1
    index[ref] = {"contentType": content_type, "angle": angle, "title": title, "seq": next_seq}
    write_json(index_path(execution_id), {"schema": INDEX_SCHEMA, "refs": index})
    return index[ref]


def register_from_brief(
    execution_id: str, ref: str, brief: Mapping[str, Any], content_type: str = "article"
) -> dict[str, Any]:
    coords = compute_content_coords(brief, content_type, ref=ref)
    return register_content_object(
        execution_id, ref,
        content_type=coords["contentType"], angle=coords["angle"], title=coords["title"],
    )


def content_coords(execution_id: str, ref: str) -> dict[str, Any] | None:
    return load_index(execution_id).get(ref)


def _coords_or_raise(execution_id: str, ref: str) -> dict[str, Any]:
    coords = content_coords(execution_id, ref)
    if not coords:
        raise KeyError(
            f"content object not registered for ref={ref!r} (execution={execution_id}); "
            f"call register_from_brief at compose-brief time"
        )
    return coords


def content_object_dir(execution_id: str, ref: str) -> Path:
    c = _coords_or_raise(execution_id, ref)
    return execution_post_object_dir(
        execution_id, c["contentType"], c["angle"], c["title"], int(c.get("seq") or 1)
    )


def content_object_stage_dir(execution_id: str, ref: str, stage: str) -> Path:
    c = _coords_or_raise(execution_id, ref)
    return execution_post_stage_dir(
        execution_id, c["contentType"], c["angle"], c["title"], int(c.get("seq") or 1), stage
    )


def iter_content_refs(execution_id: str) -> list[str]:
    return sorted(load_index(execution_id).keys())


def content_object_rel(execution_id: str, ref: str) -> str:
    """内容对象根相对 execution 根的 POSIX 路径（= publish 根同名相对路径）。"""
    obj = content_object_dir(execution_id, ref)
    return obj.relative_to(execution_root(execution_id)).as_posix()


def write_content_object_index(execution_id: str, ref: str) -> Path:
    """写内容对象 `_object.json`（§14.3）：publish 目标相对路径 + 成品相对路径 + 各阶段状态。"""
    obj_dir = content_object_dir(execution_id, ref)
    rel = obj_dir.relative_to(execution_root(execution_id)).as_posix()
    stages = {
        stage: ("done" if (obj_dir / stage).is_dir() else "pending")
        for stage in OBJECT_STAGES
    }
    path = object_index_path(obj_dir)
    write_json(
        path,
        {
            "schema": OBJECT_INDEX_SCHEMA,
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
    execution_id: str, ref: str, brief: Mapping[str, Any], content_type: str = "article"
) -> Path:
    """登记路由并把 compose brief 落对象 `3.compose/brief.json`。"""
    payload = dict(brief)
    from content.execution.runtime_state import load_execution_runtime_state

    runtime_state = load_execution_runtime_state(execution_id)
    if runtime_state is not None and not payload.get("executionSequence"):
        payload["executionSequence"] = runtime_state.execution_sequence
    register_from_brief(execution_id, ref, payload, content_type)
    from core.paths import STAGE_COMPOSE, ensure_object_stages

    obj_dir = content_object_dir(execution_id, ref)
    ensure_object_stages(obj_dir)
    path = content_object_stage_dir(execution_id, ref, STAGE_COMPOSE) / BRIEF_FILE
    write_json(path, payload)
    return path


def read_brief_object(execution_id: str, ref: str) -> dict[str, Any] | None:
    """读 compose brief：仅读取对象 `3.compose/brief.json`。"""
    if content_coords(execution_id, ref):
        path = content_object_stage_dir(execution_id, ref, STAGE_COMPOSE) / BRIEF_FILE
        if path.is_file():
            return read_json(path)
    return None


def iter_briefs(execution_id: str) -> list[tuple[str, dict[str, Any]]]:
    """(ref, brief) 列表：仅枚举已登记的对象 brief。"""
    out: list[tuple[str, dict[str, Any]]] = []
    for ref in iter_content_refs(execution_id):
        brief = read_brief_object(execution_id, ref)
        if brief is not None:
            out.append((ref, brief))
    return out


def has_briefs(execution_id: str) -> bool:
    for ref in iter_content_refs(execution_id):
        if read_brief_object(execution_id, ref) is not None:
            return True
    return False
