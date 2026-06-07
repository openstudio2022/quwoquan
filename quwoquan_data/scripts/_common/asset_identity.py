"""资产 ID 真相源：生成、解析、token 规范化。"""
from __future__ import annotations

import hashlib
import re
from typing import Any

_ROLE_FILE_TOKENS = {"cover": "cover", "closing": "closing", "node": "detail", "detail": "detail"}
_ASSET_ID_RE = re.compile(r"^(.+?)_(cover|closing|detail)_([0-9]+)_([0-9a-f]{8})$")


def asset_token(value: str) -> str:
    """文件名 token：保留中文/英文/数字，折叠其它字符，避免路径泄漏。"""
    token = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "_", str(value or "")).strip("_")
    return token or "asset"


def role_file_token(role: str) -> str:
    """把内部 role 归一成文件名 token。"""
    return _ROLE_FILE_TOKENS.get(str(role or ""), asset_token(role))


def compute_post_asset_id(
    *,
    entity_name: str,
    role: str,
    global_batch_seq: int | str,
    ref: str = "",
    nonce: int = 0,
) -> str:
    """成品图统一命名：实体_角色_全局批次号_hash。"""
    entity = asset_token(entity_name)
    role_token = role_file_token(role)
    batch_seq = str(int(global_batch_seq))
    seed = "|".join([batch_seq, str(ref or ""), entity, role_token, str(max(int(nonce or 0), 0))])
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8]
    return f"{entity}_{role_token}_{batch_seq}_{digest}"


def parse_post_asset_id(asset_id: str) -> dict[str, Any]:
    """从右锚定解析 assetId。

    返回 entity_name / role / globalBatchSeq / digest / raw / assetToken。
    允许 entity 名含下划线。
    """
    aid = str(asset_id or "").strip()
    if not aid:
        raise ValueError("asset_id is empty")
    match = _ASSET_ID_RE.match(aid)
    if not match:
        raise ValueError(f"invalid post asset id: {asset_id!r}")
    entity, role, global_batch_seq, digest = match.groups()
    return {
        "raw": aid,
        "entityName": entity,
        "assetToken": entity,
        "role": role,
        "globalBatchSeq": int(global_batch_seq),
        "digest": digest,
    }
