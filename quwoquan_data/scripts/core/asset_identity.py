"""资产 ID 真相源：生成、解析、token 规范化。

唯一命名格式：

    {entity}_{role}_{caption}_{executionSequence}_{digest8}

caption 为图注 token 段（清洗 + 截断 ≤16 字符），退化时按
sectionSlug → 图{ordinal} → 实体名 降级，保证恒非空且非纯数字。
caption 不进 hash seed；同一 execution 的幂等由 asset registry owner key 复用保证。
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re

_ROLE_FILE_TOKENS = {"cover": "cover", "closing": "closing", "node": "detail", "detail": "detail"}
# role 与 sequence 之间有图注段（可含下划线，右锚定 sequence + digest）。
_ASSET_ID_RE = re.compile(r"^(.+?)_(cover|closing|detail)_(.+)_([0-9]+)_([0-9a-f]{8})$")

CAPTION_TOKEN_MAX_CHARS = 16

# 通用占位词：无信息量的图注不得进入文件名。
_DEGENERATE_CAPTION_TOKENS = frozenset(
    {"图", "图片", "配图", "封面", "插图", "题图", "image", "img", "photo", "picture", "cover", "asset"}
)


@dataclass(frozen=True, slots=True)
class PostAssetIdentity:
    raw: str
    entity_name: str
    role: str
    caption_token: str
    execution_sequence: int
    digest: str


def asset_token(value: str) -> str:
    """文件名 token：保留中文/英文/数字，折叠其它字符，避免路径泄漏。"""
    token = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "_", str(value or "")).strip("_")
    return token or "asset"


def role_file_token(role: str) -> str:
    """把内部 role 归一成文件名 token。"""
    return _ROLE_FILE_TOKENS.get(str(role or ""), asset_token(role))


def _caption_is_degraded(token: str, entity_token: str) -> bool:
    """图注 token 退化判定：空/过短/纯数字/占位词/与实体同名 → 无信息量。"""
    t = str(token or "").strip("_")
    if len(t) < 2:
        return True
    if t.isdigit():
        return True
    if t.casefold() in _DEGENERATE_CAPTION_TOKENS:
        return True
    if entity_token and t == entity_token:
        return True
    return False


def caption_file_token(
    caption: str,
    *,
    section_slug: str = "",
    ordinal: int = 0,
    entity_name: str = "",
) -> str:
    """图注文件名 token：清洗 + 截断 ≤16；退化时降级 sectionSlug→图{ordinal}→实体名。

    返回值恒非空且非纯数字，确保生成的资产 ID 可读且可解析。
    """
    entity_token = asset_token(entity_name) if str(entity_name or "").strip() else ""
    for candidate in (caption, section_slug):
        raw = str(candidate or "").strip()
        if not raw:
            continue
        token = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "_", raw).strip("_")
        token = token[:CAPTION_TOKEN_MAX_CHARS].strip("_")
        if not _caption_is_degraded(token, entity_token):
            return token
    try:
        n = int(ordinal or 0)
    except (TypeError, ValueError):
        n = 0
    if n > 0:
        return f"图{n}"
    return (entity_token or "asset")[:CAPTION_TOKEN_MAX_CHARS].strip("_") or "asset"


def compute_post_asset_id(
    *,
    entity_name: str,
    role: str,
    execution_sequence: int | str,
    ref: str = "",
    nonce: int = 0,
    caption: str = "",
    section_slug: str = "",
    ordinal: int = 0,
) -> str:
    """成品图统一命名：实体_角色_图注_全局执行序号_hash。

    caption 不进 seed：图注微调不改 digest；批内幂等由 registry owner key 保证。
    """
    entity = asset_token(entity_name)
    role_token = role_file_token(role)
    caption_token = caption_file_token(
        caption,
        section_slug=section_slug,
        ordinal=ordinal,
        entity_name=entity_name,
    )
    batch_seq = str(int(execution_sequence))
    seed = "|".join([batch_seq, str(ref or ""), entity, role_token, str(max(int(nonce or 0), 0))])
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8]
    return f"{entity}_{role_token}_{caption_token}_{batch_seq}_{digest}"


def parse_post_asset_id(asset_id: str) -> PostAssetIdentity:
    """按唯一格式解析 assetId；实体名与图注段允许包含下划线。"""
    aid = str(asset_id or "").strip()
    if not aid:
        raise ValueError("asset_id is empty")
    match = _ASSET_ID_RE.match(aid)
    if match:
        entity, role, caption, execution_sequence, digest = match.groups()
        return PostAssetIdentity(
            raw=aid,
            entity_name=entity,
            role=role,
            caption_token=caption,
            execution_sequence=int(execution_sequence),
            digest=digest,
        )
    raise ValueError(f"invalid post asset id: {asset_id!r}")
