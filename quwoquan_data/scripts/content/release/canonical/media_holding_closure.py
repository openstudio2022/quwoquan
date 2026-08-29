"""判定一个 canonical release 的媒体闭包能否被 content library 兑现。

canonical publish 只携带引用而不携带字节，字节由库唯一持有，而库落在版本控制与
可重建输出边界之外。因此「这个 release 的媒体交付得出去」不是一个可以从树本身读
出来的事实，必须去库上兑现一次。

本模块把两件事分开，因为它们的真相源不同：`media_references_in_tree` 从树里读
release **声明**了哪些字节由库持有，`judge_media_closure` 只向库要兑现结论。判定
不接受任何 release 目录内的路径作为兑现来源——树里恰好另存了一份副本，不改变库
是否持有这些字节，把它算进兑现会让闭包在库已经丢字节之后仍然报成立。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from core.content_library import (
    MEDIA_KIND,
    ContentLibraryUnreachable,
    MediaHoldingAbsent,
    MediaHoldingDrift,
    library_cas_path,
    library_reachable,
    normalize_library_digest,
)
from core.control_types import (
    MediaClosureVerdict,
    MediaDurabilityState,
    MediaHoldingRecoveryAction,
    MediaHoldingState,
)

# 交付字节的显式声明位。一条媒体记录用这个形态的 objectKey 声明「我的字节由库按
# 内容寻址持有」；没有它的记录（权利快照、已回收的原始采集素材）显式地不作这个
# 声明，因此不进闭包。改成「凡带 sha256 与 bytes 的记录都算」会把 rights 快照与
# 一份 267MB 的已回收视频原体拉进来，让闭包在字节齐全时也报不成立。
_MEDIA_OBJECT_KEY = re.compile(
    r"^media/objects/sha256/(?P<shard>[0-9a-f]{2})/(?P<subshard>[0-9a-f]{2})/"
    r"(?P<digest>[0-9a-f]{64})(?P<suffix>\.[A-Za-z0-9]+)$"
)


class MediaReferenceRecordError(ValueError):
    """一条媒体引用记录本身不合法，与它能否被兑现无关。

    记录形态判否发生在兑现之前：一条自相矛盾的记录（`sha256` 与 `objectKey` 内嵌
    的摘要不同）没有一个「该去库里取哪份字节」的答案，把它按任一侧去兑现都是替
    记录选了一个它没写的取值。
    """


@dataclass(frozen=True)
class MediaReference:
    """release 声明的一条由库持有的交付字节。

    `declared_bytes` 缺席是合法形态而非零：image 与 video 载体的 manifest 记录用
    width/height/codec 描述资产但不声明字节数，此时大小维度不可判。塌陷成 0 会让
    每一条这类引用都判成漂移。
    """

    digest: str
    declared_bytes: int | None
    document_ref: str
    record_path: str

    @property
    def reference_ref(self) -> str:
        """把这条引用定位回它被声明的那个位置。"""

        return f"{self.document_ref}#{self.record_path}"


@dataclass(frozen=True)
class DurabilityAttestation:
    """独立持有方上的一次恢复验证。

    三项都必需：持有方是谁、恢复目标是哪个、验证发生在何时。缺任一项就不构造，
    而不是构造一个「部分成立」的承诺——耐久性没有部分成立这个状态，一个只填了
    持有方名字的承诺与没有承诺对读者是同一件事，却会让报告呈现为已耐久。
    """

    independent_holder_ref: str
    restore_target_ref: str
    restore_verified_at: str

    def __post_init__(self) -> None:
        missing = [
            name
            for name in ("independent_holder_ref", "restore_target_ref", "restore_verified_at")
            if not str(getattr(self, name) or "").strip()
        ]
        if missing:
            raise ValueError(
                "durability attestation requires every field to be declared; missing: "
                + ", ".join(sorted(missing))
            )


@dataclass(frozen=True)
class MediaHoldingOutcome:
    """一条引用的兑现结论。"""

    reference: MediaReference
    state: MediaHoldingState
    recovery: MediaHoldingRecoveryAction
    detail: str

    @property
    def honoured(self) -> bool:
        return self.state is MediaHoldingState.HONOURED


@dataclass(frozen=True)
class MediaClosureReport:
    """一个 release 的媒体闭包判定结果。"""

    verdict: MediaClosureVerdict
    durability: MediaDurabilityState
    library_root: str
    library_recovery: MediaHoldingRecoveryAction
    outcomes: tuple[MediaHoldingOutcome, ...]
    reference_count: int
    detail: str

    @property
    def honoured(self) -> bool:
        return self.verdict is MediaClosureVerdict.HONOURED

    @property
    def unhonoured(self) -> tuple[MediaHoldingOutcome, ...]:
        return tuple(outcome for outcome in self.outcomes if not outcome.honoured)

    def to_document(self) -> dict:
        document = {
            "verdict": str(self.verdict),
            "durability": str(self.durability),
            "libraryRoot": self.library_root,
            "libraryRecovery": str(self.library_recovery),
            "referenceCount": self.reference_count,
            "detail": self.detail,
        }
        # 库不可达时 outcomes 为空，键也不出现：给出一个空数组会读成「零条引用不可
        # 兑现」，而真实结论是这些引用一条都没被判过。
        if self.verdict is not MediaClosureVerdict.LIBRARY_UNREACHABLE:
            document["holdings"] = [
                {
                    "referenceRef": outcome.reference.reference_ref,
                    "sha256": f"sha256:{outcome.reference.digest}",
                    "state": str(outcome.state),
                    "recovery": str(outcome.recovery),
                    "detail": outcome.detail,
                    **(
                        {"declaredBytes": outcome.reference.declared_bytes}
                        if outcome.reference.declared_bytes is not None
                        else {}
                    ),
                }
                for outcome in self.outcomes
            ]
        return document


def _reference_from_record(record: dict, *, document_ref: str, record_path: str) -> MediaReference:
    object_key = str(record.get("objectKey") or "")
    match = _MEDIA_OBJECT_KEY.fullmatch(object_key)
    if match is None:
        raise MediaReferenceRecordError(f"not a library-held media record: {record_path}")
    key_digest = match.group("digest")
    declared = record.get("sha256")
    if not isinstance(declared, str) or not declared.strip():
        raise MediaReferenceRecordError(
            f"media record declares an objectKey but no sha256: {document_ref}#{record_path}"
        )
    digest = normalize_library_digest(declared)
    if digest != key_digest:
        raise MediaReferenceRecordError(
            "media record disagrees with its own objectKey: "
            f"{document_ref}#{record_path} sha256={digest} objectKey={key_digest}"
        )
    declared_bytes = record.get("bytes")
    if declared_bytes is not None and not isinstance(declared_bytes, int):
        raise MediaReferenceRecordError(
            f"media record declares a non-integer size: {document_ref}#{record_path}"
        )
    return MediaReference(
        digest=digest,
        declared_bytes=declared_bytes,
        document_ref=document_ref,
        record_path=record_path,
    )


def _walk_records(node: object, *, path: str, document_ref: str, found: list[MediaReference]) -> None:
    if isinstance(node, dict):
        if isinstance(node.get("objectKey"), str) and _MEDIA_OBJECT_KEY.fullmatch(
            str(node.get("objectKey"))
        ):
            found.append(
                _reference_from_record(node, document_ref=document_ref, record_path=path)
            )
        for key, value in node.items():
            _walk_records(value, path=f"{path}.{key}", document_ref=document_ref, found=found)
        return
    if isinstance(node, list):
        for index, value in enumerate(node):
            _walk_records(value, path=f"{path}[{index}]", document_ref=document_ref, found=found)


def media_references_in_tree(root: Path) -> tuple[MediaReference, ...]:
    """一棵 canonical 树声明由库持有的全部交付字节，按声明位置逐条列出。

    同一摘要在多处被声明时逐条保留而不去重：判定要能回答「哪个对象的哪个字段引用
    不可兑现」，去重后剩下的摘要指不回任何一个对象。
    """

    references: list[MediaReference] = []
    for path in sorted(Path(root).rglob("*.json")):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            document = json.loads(text)
        except json.JSONDecodeError:
            continue
        _walk_records(
            document,
            path="$",
            document_ref=path.relative_to(root).as_posix(),
            found=references,
        )
    return tuple(references)


def media_references_in_release_manifest(
    manifest: object,
    *,
    document_ref: str = "payload/media_manifest.json",
) -> tuple[MediaReference, ...]:
    """一个 release 的 media manifest 声明的全部媒体引用。

    清单是交付面的权威声明，所以这里不套 canonical 树那条「objectKey 是否声明由库
    持有」的判据：清单里不出现权利快照与已回收的原始素材，每一条都是要交付的字节。
    引用身份取 `sha256`——它同时是内容身份与库地址，因此不同 key 形态
    （`privateObjectKey` 的内容寻址路径与 `publicSliceKey` 的公开切片路径）解析到
    同一个持有方，不需要各判一次。
    """

    if not isinstance(manifest, dict):
        raise MediaReferenceRecordError(f"release media manifest must be an object: {document_ref}")
    assets = manifest.get("assets")
    if not isinstance(assets, list):
        raise MediaReferenceRecordError(
            f"release media manifest declares no assets array: {document_ref}"
        )
    references: list[MediaReference] = []
    for index, asset in enumerate(assets):
        record_path = f"$.assets[{index}]"
        if not isinstance(asset, dict):
            raise MediaReferenceRecordError(
                f"release media manifest asset must be an object: {document_ref}#{record_path}"
            )
        declared = asset.get("sha256")
        if not isinstance(declared, str) or not declared.strip():
            raise MediaReferenceRecordError(
                f"release media manifest asset declares no sha256: {document_ref}#{record_path}"
            )
        declared_bytes = asset.get("bytes")
        if declared_bytes is not None and not isinstance(declared_bytes, int):
            raise MediaReferenceRecordError(
                "release media manifest asset declares a non-integer size: "
                f"{document_ref}#{record_path}"
            )
        references.append(
            MediaReference(
                digest=normalize_library_digest(declared),
                declared_bytes=declared_bytes,
                document_ref=document_ref,
                record_path=record_path,
            )
        )
    return tuple(references)


def _judge_one(reference: MediaReference, *, library_root: Path | None) -> MediaHoldingOutcome:
    entry = library_cas_path(MEDIA_KIND, reference.digest, library_root=library_root)
    suffixed = sorted(entry.parent.glob(f"{reference.digest}*")) if entry.parent.is_dir() else []
    held = next((candidate for candidate in suffixed if candidate.is_file()), None)
    if held is None:
        return MediaHoldingOutcome(
            reference=reference,
            state=MediaHoldingState.ABSENT,
            recovery=MediaHoldingRecoveryAction.ADMIT_CARRIED_BYTES,
            detail="library holds no entry for this digest",
        )
    if reference.declared_bytes is not None:
        observed = held.stat().st_size
        if observed != reference.declared_bytes:
            return MediaHoldingOutcome(
                reference=reference,
                state=MediaHoldingState.DRIFTED,
                recovery=MediaHoldingRecoveryAction.RESTORE_FROM_INDEPENDENT_HOLDER,
                detail=(
                    f"library entry is {observed} bytes, the record declares "
                    f"{reference.declared_bytes}"
                ),
            )
    return MediaHoldingOutcome(
        reference=reference,
        state=MediaHoldingState.HONOURED,
        recovery=MediaHoldingRecoveryAction.NONE,
        detail=(
            "honoured"
            if reference.declared_bytes is not None
            else "honoured; the record declares no size, so drift is not judged here"
        ),
    )


def judge_media_closure(
    references: tuple[MediaReference, ...],
    *,
    library_root: Path | None = None,
    durability_attestation: DurabilityAttestation | None = None,
) -> MediaClosureReport:
    """判定这批引用能否由库兑现，并如实呈现耐久性。

    耐久性默认为未确立，且只有一次带独立持有方与隔离恢复目标的验证能把它置位。库
    当前可读不参与这个判定：字节现在读得到，说的是这一刻库还在，不是它有第二个
    持有方。
    """

    root = Path(library_root).expanduser() if library_root is not None else None
    durability = (
        MediaDurabilityState.VERIFIED
        if durability_attestation is not None
        else MediaDurabilityState.NOT_ESTABLISHED
    )
    resolved_root = str(
        root if root is not None else library_cas_path(MEDIA_KIND, "0" * 64).parents[3]
    )
    if not library_reachable(library_root=root):
        return MediaClosureReport(
            verdict=MediaClosureVerdict.LIBRARY_UNREACHABLE,
            durability=durability,
            library_root=resolved_root,
            library_recovery=MediaHoldingRecoveryAction.REATTACH_LIBRARY,
            outcomes=(),
            reference_count=len(references),
            detail=(
                f"content library is not reachable, so none of the {len(references)} "
                "references were judged"
            ),
        )
    outcomes = tuple(_judge_one(reference, library_root=root) for reference in references)
    unhonoured = tuple(outcome for outcome in outcomes if not outcome.honoured)
    if unhonoured:
        return MediaClosureReport(
            verdict=MediaClosureVerdict.REFERENCES_UNHONOURED,
            durability=durability,
            library_root=resolved_root,
            library_recovery=MediaHoldingRecoveryAction.NONE,
            outcomes=outcomes,
            reference_count=len(references),
            detail=f"{len(unhonoured)} of {len(references)} references cannot be honoured",
        )
    return MediaClosureReport(
        verdict=MediaClosureVerdict.HONOURED,
        durability=durability,
        library_root=resolved_root,
        library_recovery=MediaHoldingRecoveryAction.NONE,
        outcomes=outcomes,
        reference_count=len(references),
        detail=f"all {len(references)} references are honoured by the library",
    )


def resolve_reference_bytes(
    reference: MediaReference,
    *,
    library_root: Path | None = None,
) -> Path:
    """兑现一条引用并返回持有它的库条目，失败按三类分别抛出。

    给需要字节本身的读取方用：判定面回答「能不能」，这里回答「在哪」，两者共用
    同一批判据，因此不会出现报告说可兑现而读取方拿不到字节的组合。
    """

    outcome = _judge_one(reference, library_root=library_root)
    if outcome.state is MediaHoldingState.HONOURED:
        entry = library_cas_path(MEDIA_KIND, reference.digest, library_root=library_root)
        return next(
            candidate
            for candidate in sorted(entry.parent.glob(f"{reference.digest}*"))
            if candidate.is_file()
        )
    if not library_reachable(library_root=library_root):
        raise ContentLibraryUnreachable(
            f"content library is not reachable: {library_root}"
        )
    if outcome.state is MediaHoldingState.ABSENT:
        raise MediaHoldingAbsent(
            f"{outcome.detail}: {reference.reference_ref} sha256={reference.digest}"
        )
    raise MediaHoldingDrift(
        f"{outcome.detail}: {reference.reference_ref} sha256={reference.digest}"
    )


__all__ = [
    "DurabilityAttestation",
    "MediaClosureReport",
    "MediaHoldingOutcome",
    "MediaReference",
    "MediaReferenceRecordError",
    "judge_media_closure",
    "media_references_in_release_manifest",
    "media_references_in_tree",
    "resolve_reference_bytes",
]
