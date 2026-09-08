"""六步协议的 seal 内核：校验当前步骤硬事实并 create-once 写 receipt。

只有 acquire(1.download)、author(4.draft)、review(5.review) 三步有 receipt。seal 自己完成
schema/引用/摘要/媒体硬事实检查并冻结产物 exact bytes；不再有 stage-open、宿主 verifierFacts、
跨阶段回扫。review 步骤额外把 content_review.json 的机械字段（schema/stage/executionId/objectRef/
draft/assetRights 权利转录）从 execution 与 source meta 补齐，AI 只写判断字段。
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Any, Iterator

from content.execution.identity import validate_execution_id
from core import paths
from core.control_types import (
    AUTHOR_ARTIFACT_BY_CARRIER,
    QUALITY_DIMENSIONS_BY_CARRIER,
    RECEIPT_STAGE_SEQUENCE,
    carrier_of_target_ref,
)
from core.schema import assert_valid

STAGES: tuple[str, ...] = tuple(stage.value for stage in RECEIPT_STAGE_SEQUENCE)
RECEIPT_DIRECTORY = "_shared/receipts"
_RIGHTS_TRANSCRIPTION_FIELDS = ("sourceUrl", "license", "termsUrl", "authorizationProof")


class SealError(ValueError):
    """当前步骤硬事实不闭合。"""


class SealConflict(SealError):
    """create-once receipt 已存在且字节不同。"""


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def receipt_name(stage: str) -> str:
    return f"{STAGES.index(stage) + 1:03d}-{stage}.json"


def _safe_ref(value: str, *, label: str) -> str:
    parsed = PurePosixPath(value)
    if not value or parsed.is_absolute() or any(part in {"", ".", ".."} for part in parsed.parts) or "\x00" in value:
        raise SealError(f"{label} 不是安全相对引用：{value!r}")
    return value


def _regular(path: Path, *, label: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise SealError(f"{label} 缺失或不是 regular file：{path.name}")
    return path


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(_regular(path, label=label).read_bytes())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SealError(f"{label} 不是合法 JSON") from exc
    if not isinstance(value, dict):
        raise SealError(f"{label} 必须是 JSON 对象")
    return value


def _frozen(root: Path, ref: str) -> dict[str, str]:
    return {"scope": "execution", "ref": ref, "digest": sha256(_regular(root / ref, label=ref).read_bytes())}


def _target_refs(root: Path) -> list[str]:
    target_set = _read_json(root / "0.plan/target_set.json", label="target_set")
    assert_valid(target_set, "execution", "target_set", label="target_set")
    refs = target_set.get("targetRefs")
    if not isinstance(refs, list) or not refs or any(not isinstance(ref, str) for ref in refs):
        raise SealError("target_set.targetRefs 必须是非空字符串数组")
    return list(refs)


def _actor_key(actor: dict[str, Any]) -> tuple[str, str, str]:
    invocation = actor.get("invocation") or {}
    return (
        str(actor.get("host") or "").strip(),
        str(actor.get("sessionId") or "").strip(),
        str(invocation.get("runId") or "").strip(),
    )


# ── 三步硬事实 ────────────────────────────────────────────────────────


def _validate_acquire_target(root: Path, target_ref: str) -> dict[str, str]:
    """单对象 source_refs.json 在场且每个 source unit 的正文/资产字节与记录一致；任一违规抛 SealError。"""

    refs_ref = f"{target_ref}/1.download/source_refs.json"
    refs_doc = _read_json(root / refs_ref, label=refs_ref)
    try:
        assert_valid(refs_doc, "source", "object_source_refs", label=refs_ref)
    except ValueError as exc:
        raise SealError(str(exc)) from exc
    if refs_doc.get("objectRef") != target_ref:
        raise SealError(f"source_refs objectRef 与 target 漂移：{target_ref}")
    rows = refs_doc.get("sources") or []
    if not rows:
        raise SealError(f"acquire 未取得任何来源：{target_ref}")
    for row in rows:
        meta_ref = _safe_ref(str(row.get("metaRef") or ""), label="metaRef")
        source_ref = _safe_ref(str(row.get("sourceRef") or ""), label="sourceRef")
        meta = _read_json(root / meta_ref, label=meta_ref)
        try:
            assert_valid(meta, "source", "atomic_source_unit_meta", label=meta_ref)
        except ValueError as exc:
            raise SealError(str(exc)) from exc
        source_bytes = _regular(root / source_ref, label=source_ref).read_bytes()
        if sha256(source_bytes) != meta.get("sourceMarkdownSha256"):
            raise SealError(f"source.md 摘要漂移：{source_ref}")
        unit_dir = (root / meta_ref).parent
        index = _read_json(unit_dir / "assets/index.json", label=f"{meta_ref}#assets")
        for asset in index.get("assets") or []:
            if not isinstance(asset, dict):
                raise SealError(f"assets/index.json 行必须是对象：{meta_ref}")
            file_name = _safe_ref(str(asset.get("fileName") or ""), label="assets.fileName")
            asset_bytes = _regular(unit_dir / "assets" / file_name, label=file_name).read_bytes()
            if sha256(asset_bytes) != asset.get("sha256") or len(asset_bytes) != int(asset.get("bytes") or -1):
                raise SealError(f"资产字节或摘要漂移：{file_name}")
            if not str(asset.get("sourceUrl") or "").startswith("https://"):
                raise SealError(f"资产缺少 https sourceUrl：{file_name}")
    return _frozen(root, refs_ref)


def _seal_acquire(root: Path, target_refs: list[str]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """逐对象校验 acquire 硬事实：ingest 失败或字节漂移的对象只记 typed issue 并退出本 execution。

    与 `task acquire` 的「逐 target 独立报告」同一语义；零合规对象的判定交给调用方（verdict 必须为 blocked）。
    """

    result_refs: list[dict[str, str]] = []
    typed_issues: list[dict[str, str]] = []
    for target_ref in target_refs:
        try:
            result_refs.append(_validate_acquire_target(root, target_ref))
        except SealError as exc:
            typed_issues.append({"code": "DATA.SEAL.ACQUIRE_INVALID", "message": str(exc), "ref": target_ref})
    return result_refs, typed_issues


def _acquire_receipt_target_refs(acquire_receipt: dict[str, Any]) -> list[str]:
    """从 001-1.download receipt 的 resultRefs 反推已取得来源的对象集合；acquire 退轮的对象不在其中。"""

    refs: list[str] = []
    for row in acquire_receipt.get("resultRefs") or []:
        ref = str((row or {}).get("ref") or "")
        marker = "/1.download/"
        if marker not in ref:
            raise SealError(f"001-1.download resultRef 不是 source_refs：{ref!r}")
        refs.append(ref.split(marker, 1)[0])
    return sorted(set(refs))


def _author_artifact_ref(target_ref: str) -> str:
    return f"{target_ref}/4.draft/{AUTHOR_ARTIFACT_BY_CARRIER[carrier_of_target_ref(target_ref)]}"


_FRONTMATTER_TAGS = re.compile(r"^tagRefs:\s*\[(.*?)\]\s*$", re.M)


def _declared_tag_refs(path: Path, document: dict[str, Any] | None) -> list[str]:
    if document is not None:
        return [str(value) for value in document.get("tagRefs") or []]
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return []
    header = text.split("\n---\n", 1)[0]
    match = _FRONTMATTER_TAGS.search(header)
    if not match:
        return []
    return [item.strip().strip("'\"") for item in match.group(1).split(",") if item.strip()]


def _assert_tag_refs_resolve(tag_refs: list[str], *, label: str) -> None:
    """tagRefs 必须是 taxonomy 现有叶子；这是 publish 会拒绝的硬事实，提前在 author seal 报出。"""

    taxonomy_root = Path(os.environ.get("QWQ_TAGS_ROOT") or paths.CONTROL_PLANE_TAXONOMY_ROOT)
    for ref in tag_refs:
        safe = _safe_ref(ref, label=f"{label} tagRef")
        if not (taxonomy_root / safe / "_definition.json").is_file():
            raise SealError(f"tagRef 不在 taxonomy 中：{ref}（{label}）")


_FRONTMATTER_CREATOR = re.compile(r"^creatorProfileId:\s*(\S+)\s*$", re.M)


def _declared_creator(path: Path, document: dict[str, Any] | None) -> str:
    if document is not None:
        return str(document.get("creatorProfileId") or "").strip()
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return ""
    match = _FRONTMATTER_CREATOR.search(text.split("\n---\n", 1)[0])
    return match.group(1).strip().strip("'\"") if match else ""


def _assert_creator_resolves(creator_profile_id: str, *, label: str) -> None:
    """creatorProfileId 缺省按载体默认，写了就必须解析到 creator 注册表；publish 会拒绝，提前报出。"""

    if not creator_profile_id:
        return
    from governance.creators.assignment import creator_from_payload

    if not creator_from_payload({"creatorProfileId": creator_profile_id}):
        raise SealError(f"creatorProfileId 不在 creator 注册表中：{creator_profile_id}（{label}）")


def _assert_homepage_has_encyclopedia_source(root: Path, target_ref: str) -> None:
    """homepage 的 _entity.json 要求百科主源；缺失在 author seal 即判否，不留到 publish。"""

    if carrier_of_target_ref(target_ref) != "homepage":
        return
    refs_doc = _read_json(root / f"{target_ref}/1.download/source_refs.json", label="source_refs")
    for row in refs_doc.get("sources") or []:
        identity = f"{row.get('sourceId') or ''} {row.get('sourceClass') or ''}".lower()
        if "wikipedia" in identity or "baike" in identity or "encyclopedia" in identity:
            return
    raise SealError(f"homepage 缺少百科 page 来源（zh.wikipedia/baike）：{target_ref}")


def _validate_author_artifact(root: Path, execution_id: str, target_ref: str) -> dict[str, str]:
    """校验单个对象的 carrier 产物硬事实并返回其 frozen ref；任一违规抛 SealError。"""

    artifact_ref = _author_artifact_ref(target_ref)
    path = _regular(root / artifact_ref, label=artifact_ref)
    if path.stat().st_size == 0:
        raise SealError(f"author 产物为空：{artifact_ref}")
    document: dict[str, Any] | None = None
    if path.suffix == ".json":
        schema_name = path.stem
        document = _read_json(path, label=artifact_ref)
        completed = {
            **document,
            "schema": f"quwoquan_data.{schema_name}",
            "executionId": execution_id,
            "objectRef": target_ref,
        }
        try:
            assert_valid(completed, "content", schema_name, label=artifact_ref)
        except ValueError as exc:
            raise SealError(str(exc)) from exc
        if completed != document:
            _write_create_or_same(path, canonical_bytes(completed), allow_rewrite=True)
        document = completed
    _assert_tag_refs_resolve(_declared_tag_refs(path, document), label=artifact_ref)
    _assert_creator_resolves(_declared_creator(path, document), label=artifact_ref)
    _assert_homepage_has_encyclopedia_source(root, target_ref)
    return _frozen(root, artifact_ref)


def _seal_author(root: Path, execution_id: str, target_refs: list[str]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """逐对象校验 carrier 产物：合规对象进入 resultRefs，违规对象只记 typed issue 并退出本 execution。

    一次报出全部违规而不是只报首个；4.draft 目录允许存在草稿以外的文件（笔记、备选稿），
    只有 carrier 产物进入 receipt。零合规对象的判定交给调用方（verdict 必须为 blocked）。
    """

    result_refs: list[dict[str, str]] = []
    typed_issues: list[dict[str, str]] = []
    for target_ref in target_refs:
        try:
            result_refs.append(_validate_author_artifact(root, execution_id, target_ref))
        except SealError as exc:
            typed_issues.append({"code": "DATA.SEAL.DRAFT_INVALID", "message": str(exc), "ref": target_ref})
    return result_refs, typed_issues


def _author_receipt_target_refs(author_receipt: dict[str, Any]) -> list[str]:
    """从 002-4.draft receipt 的 resultRefs 反推合规对象集合；4.draft 退轮的对象不在其中。"""

    refs: list[str] = []
    for row in author_receipt.get("resultRefs") or []:
        ref = str((row or {}).get("ref") or "")
        marker = "/4.draft/"
        if marker not in ref:
            raise SealError(f"002-4.draft resultRef 不是 carrier 产物：{ref!r}")
        refs.append(ref.split(marker, 1)[0])
    return sorted(set(refs))


def _assert_quality_scores_match_carrier(review: dict[str, Any], *, target_ref: str) -> None:
    """qualityScores 只记录不判否，但维度键必须落在该载体的闭集内，否则是申报错误而非评分差异。"""

    scores = review.get("qualityScores")
    if scores is None:
        return
    if not isinstance(scores, dict) or not scores:
        raise SealError(f"qualityScores 必须是非空对象：{target_ref}")
    allowed = set(QUALITY_DIMENSIONS_BY_CARRIER[carrier_of_target_ref(target_ref)])
    unknown = sorted(set(scores) - allowed)
    if unknown:
        raise SealError(f"qualityScores 维度不属于该载体闭集：{target_ref} unknown={unknown}")


def _object_source_assets(root: Path, target_ref: str) -> dict[str, dict[str, Any]]:
    """对象全部 source unit 的资产行，键为 execution 相对路径 sources/<unit>/assets/<fileName>。"""

    refs_doc = _read_json(root / f"{target_ref}/1.download/source_refs.json", label="source_refs")
    rows: dict[str, dict[str, Any]] = {}
    for row in refs_doc.get("sources") or []:
        unit_dir = (root / str(row.get("metaRef"))).parent
        index = _read_json(unit_dir / "assets/index.json", label="assets/index.json")
        for asset in index.get("assets") or []:
            if isinstance(asset, dict) and asset.get("fileName"):
                ref = (unit_dir / "assets" / str(asset["fileName"])).relative_to(root).as_posix()
                rows[ref] = asset
    return rows


def _normalize_asset_ref(raw: str, assets: dict[str, dict[str, Any]]) -> str:
    """接受 AI 写的 fileName / assets/<fileName> / 完整 sources 路径，归一为 execution 相对路径。"""

    value = str(raw or "").strip().strip("/")
    if value in assets:
        return value
    tail = value.removeprefix("assets/")
    matches = [ref for ref in assets if ref.endswith(f"/assets/{tail}")]
    if len(matches) != 1:
        raise SealError(f"assetRef 无法唯一解析到对象资产：{raw!r}")
    return matches[0]


_MARKDOWN_IMAGE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)\)")


def _referenced_asset_refs(root: Path, target_ref: str, assets: dict[str, dict[str, Any]]) -> list[str]:
    """对象产物实际引用的资产（publish 会精确核对这个集合）：image 取 assetRefs，video 取全部
    源资产（视频 + poster），article/homepage 取正文 `![](assets/...)`。"""

    carrier = carrier_of_target_ref(target_ref)
    draft_path = root / _author_artifact_ref(target_ref)
    if carrier == "video":
        return sorted(assets)
    if carrier == "image":
        document = _read_json(draft_path, label=draft_path.name)
        raw_refs = [str(value) for value in document.get("assetRefs") or []]
    else:
        raw_refs = [
            match for match in _MARKDOWN_IMAGE.findall(draft_path.read_text(encoding="utf-8"))
            if "assets/" in match
        ]
    return sorted({_normalize_asset_ref(raw, assets) for raw in raw_refs})


def _complete_review(
    review: dict[str, Any],
    *,
    execution_id: str,
    target_ref: str,
    root: Path,
) -> dict[str, Any]:
    """reviewer 只写 decision/blockingIssues/advisories（可选 safety、assetRights[].issues）；
    assetRights 按对象实际引用的资产机械补齐，dimensions 缺省为单维。"""

    draft_ref = _author_artifact_ref(target_ref)
    draft_digest = sha256(_regular(root / draft_ref, label=draft_ref).read_bytes())
    assets = _object_source_assets(root, target_ref)
    referenced = _referenced_asset_refs(root, target_ref, assets)
    raw_rows = review.get("assetRights") if isinstance(review.get("assetRights"), list) else []
    reviewer_rows: dict[str, dict[str, Any]] = {}
    advisories = [str(item) for item in (review.get("advisories") or []) if str(item).strip()]
    for row in raw_rows:
        if not isinstance(row, dict):
            raise SealError(f"content_review.assetRights 行必须是对象：{target_ref}")
        ref = _normalize_asset_ref(str(row.get("assetRef") or ""), assets)
        if ref not in referenced:
            # 未被产物引用的资产不进入发布集合；reviewer 的意见保留为 advisory 记录。
            for issue in row.get("issues") or []:
                advisories.append(f"{ref}: {issue}")
            continue
        reviewer_rows[ref] = row
    completed_rights: list[dict[str, Any]] = []
    for ref in referenced:
        row = reviewer_rows.get(ref, {})
        source = assets[ref]
        completed_rights.append(
            {
                **{k: v for k, v in row.items() if k not in _RIGHTS_TRANSCRIPTION_FIELDS},
                "assetRef": ref,
                "decision": row.get("decision") or "approved",
                "usageScope": row.get("usageScope") or "research",
                "issues": row.get("issues") if isinstance(row.get("issues"), list) else [],
                "sourceUrl": source.get("sourceUrl") or source.get("url"),
                "license": source.get("license"),
                "termsUrl": source.get("termsUrl"),
                "authorizationProof": source.get("authorizationProof") or None,
            }
        )
    decision = str(review.get("decision") or "")
    blocking = review.get("blockingIssues") if isinstance(review.get("blockingIssues"), list) else []
    dimensions = review.get("dimensions") if isinstance(review.get("dimensions"), list) and review.get("dimensions") else [
        {"name": "overall", "decision": decision, "issues": [] if decision == "approved" else list(blocking)}
    ]
    completed = {
        **review,
        "schema": "quwoquan_data.content_review",
        "stage": "5.review",
        "executionId": execution_id,
        "objectRef": target_ref,
        "draft": {"ref": f"4.draft/{PurePosixPath(draft_ref).name}", "digest": draft_digest},
        "dimensions": dimensions,
        "blockingIssues": blocking,
        "advisories": advisories,
        "assetRights": completed_rights,
    }
    return completed


def _seal_review(
    root: Path,
    execution_id: str,
    target_refs: list[str],
    *,
    reviewer: dict[str, Any],
    reviews: dict[str, Any],
    author_receipt: dict[str, Any],
) -> tuple[list[dict[str, str]], int]:
    """把 execution 级 reviews 扇出为逐对象 content_review.json 并补齐机械字段。

    reviewer 与 author 必须是不同 session/runId。覆盖集合是 002-4.draft receipt 的 resultRefs 对象集合
    （4.draft 退轮的对象没有产物可评，也不得被评）。单阶段扇出：只对显式输入与直接前序 receipt 展开。
    """

    author = author_receipt.get("actor") or {}
    author_host, author_session, author_run = _actor_key(author)
    reviewer_host, reviewer_session, reviewer_run = _actor_key(reviewer)
    if (author_host, author_session) == (reviewer_host, reviewer_session):
        raise SealError("reviewer 与 author 使用同一 host/sessionId")
    if author_run == reviewer_run:
        raise SealError("reviewer 与 author 使用同一 invocation.runId")
    reviewable = _author_receipt_target_refs(author_receipt)
    unknown = sorted(set(reviewable) - set(target_refs))
    if unknown:
        raise SealError(f"002-4.draft resultRefs 含 target_set 之外的对象：{unknown}")
    declared = {str(key).strip().strip("/") for key in reviews}
    expected = set(reviewable)
    if declared != expected:
        raise SealError(
            f"reviews 必须恰好覆盖 002-4.draft 合规对象集合：missing={sorted(expected - declared)} extra={sorted(declared - expected)}"
        )

    result_refs: list[dict[str, str]] = []
    approved = 0
    for target_ref in reviewable:
        review_ref = f"{target_ref}/5.review/content_review.json"
        path = root / review_ref
        judgement = reviews.get(target_ref) or reviews.get(f"/{target_ref}") or {}
        _assert_quality_scores_match_carrier(judgement, target_ref=target_ref)
        completed = _complete_review(dict(judgement), execution_id=execution_id, target_ref=target_ref, root=root)
        try:
            assert_valid(completed, "content", "content_review", label=review_ref)
        except ValueError as exc:
            raise SealError(str(exc)) from exc
        _write_create_or_same(path, canonical_bytes(completed))
        approved += completed.get("decision") == "approved"
        result_refs.append(_frozen(root, review_ref))
    return result_refs, approved


# ── receipt 链与 create-once ──────────────────────────────────────────


def _load_prior_receipts(root: Path, stage: str) -> tuple[list[dict[str, Any]], dict[str, str] | None]:
    receipts_dir = root / RECEIPT_DIRECTORY
    index = STAGES.index(stage)
    expected_prior = [receipt_name(prior) for prior in STAGES[:index]]
    present = sorted(p.name for p in receipts_dir.iterdir() if p.is_file() and not p.name.startswith(".")) if receipts_dir.is_dir() else []
    extra = set(present) - set(expected_prior) - {receipt_name(stage)}
    if extra or set(expected_prior) - set(present):
        raise SealError(f"receipt 链必须是连续前缀；expected={expected_prior} present={present}")
    receipts: list[dict[str, Any]] = []
    predecessor: dict[str, str] | None = None
    for name in expected_prior:
        raw = _regular(receipts_dir / name, label=name).read_bytes()
        doc = _read_json(receipts_dir / name, label=name)
        assert_valid(doc, "execution", "stage_receipt", label=name)
        if raw != canonical_bytes(doc) or doc.get("predecessor") != predecessor or doc.get("verdict") != "pass":
            raise SealError(f"前序 receipt 不可信或未 pass：{name}")
        predecessor = {"scope": "execution", "ref": f"{RECEIPT_DIRECTORY}/{name}", "digest": sha256(raw)}
        receipts.append(doc)
    return receipts, predecessor


@contextmanager
def _lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _write_create_or_same(path: Path, data: bytes, *, allow_rewrite: bool = False) -> str:
    """create-once 写入；已存在且字节相同视为 replay，不同则冲突（allow_rewrite 时覆盖）。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() == data:
            return "replayed"
        if not allow_rewrite:
            raise SealConflict(f"create-once 冲突：{path}")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    return "created"


def seal_stage(*, execution_id: str, stage: str, input_path: Path) -> dict[str, Any]:
    execution_id = validate_execution_id(execution_id)
    if stage not in STAGES:
        raise SealError(f"未知 stage：{stage!r}；只允许 {STAGES}")
    root = paths.execution_root(execution_id)
    _regular(root / "execution_manifest.json", label="execution_manifest")
    target_refs = _target_refs(root)

    seal_input = _read_json(Path(input_path).expanduser(), label="seal input")
    assert_valid(seal_input, "execution", "seal_input", label="seal input")
    actor = seal_input["actor"]
    verdict = seal_input["verdict"]
    typed_issues = list(seal_input.get("typedIssues") or [])
    reviews = seal_input.get("reviews")
    if stage == "5.review" and not isinstance(reviews, dict):
        raise SealError("5.review seal 需要 execution 级 reviews（targetRef → 判断字段）")
    if stage != "5.review" and reviews is not None:
        raise SealError(f"{stage} seal 不接受 reviews")

    with _lock(root / RECEIPT_DIRECTORY / ".seal.lock"):
        prior, predecessor = _load_prior_receipts(root, stage)
        if stage == "1.download":
            result_refs, acquire_issues = _seal_acquire(root, target_refs)
            typed_issues.extend(issue for issue in acquire_issues if issue not in typed_issues)
            if verdict == "pass" and not result_refs:
                raise SealError(
                    "1.download pass 必须至少有一个取得来源的对象；全部对象失败时以 verdict=blocked 提交："
                    + "; ".join(issue["message"] for issue in acquire_issues)
                )
        elif stage == "4.draft":
            acquired = _acquire_receipt_target_refs(prior[0])
            unknown = sorted(set(acquired) - set(target_refs))
            if unknown:
                raise SealError(f"001-1.download resultRefs 含 target_set 之外的对象：{unknown}")
            result_refs, draft_issues = _seal_author(root, execution_id, acquired)
            typed_issues.extend(issue for issue in draft_issues if issue not in typed_issues)
            if verdict == "pass" and not result_refs:
                raise SealError(
                    "4.draft pass 必须至少有一个合规产物；全部对象违规时以 verdict=blocked 提交："
                    + "; ".join(issue["message"] for issue in draft_issues)
                )
        else:
            result_refs, approved = _seal_review(
                root, execution_id, target_refs, reviewer=actor, reviews=reviews, author_receipt=prior[1]
            )
            if verdict == "pass" and approved == 0:
                raise SealError("review pass 必须至少有一个 approved 对象")
        receipt = {
            "schema": "quwoquan_data.stage_receipt",
            "executionId": execution_id,
            "stage": stage,
            "sequence": STAGES.index(stage) + 1,
            "predecessor": predecessor,
            "sealInput": {"digest": sha256(canonical_bytes(seal_input))},
            "actor": actor,
            "verdict": verdict,
            "typedIssues": typed_issues,
            "resultRefs": sorted(result_refs, key=lambda row: row["ref"]),
        }
        assert_valid(receipt, "execution", "stage_receipt", label=receipt_name(stage))
        status = _write_create_or_same(root / RECEIPT_DIRECTORY / receipt_name(stage), canonical_bytes(receipt))
    return {"executionId": execution_id, "stage": stage, "status": status, "receipt": f"{RECEIPT_DIRECTORY}/{receipt_name(stage)}", "verdict": verdict, "resultRefs": len(result_refs)}


__all__ = ["STAGES", "SealConflict", "SealError", "receipt_name", "seal_stage"]
