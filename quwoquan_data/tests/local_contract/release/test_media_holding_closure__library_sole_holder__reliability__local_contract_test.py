# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/spec.md#sit-002.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/spec.md#sit-002.t2
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/spec.md#sit-002.t3
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/spec.md#sit-002.t5
"""content library 是媒体字节唯一持有方时，四种情形必须给出互不塌陷的终态。

四种情形在隔离库根上构造，因此判据只证明控制逻辑：字节此刻在本机库里读得到，不是
耐久性结论，所以耐久性在每一种情形下都必须呈现为未确立。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from content.release.canonical.media_holding_closure import (
    DurabilityAttestation,
    MediaReference,
    MediaReferenceRecordError,
    judge_media_closure,
    media_references_in_tree,
    resolve_reference_bytes,
)
from core.content_library import (
    MEDIA_KIND,
    ContentLibraryUnreachable,
    MediaHoldingAbsent,
    MediaHoldingDrift,
    MediaHoldingError,
    admit_library_bytes,
    library_cas_path,
)
from core.control_types import (
    MediaClosureVerdict,
    MediaDurabilityState,
    MediaHoldingRecoveryAction,
    MediaHoldingState,
)

_BODY = b"a frozen media body"
_OTHER = b"a different media body entirely"


def _digest(body: bytes) -> str:
    import hashlib

    return hashlib.sha256(body).hexdigest()


def _object_key(digest: str, suffix: str = ".jpg") -> str:
    return f"media/objects/sha256/{digest[:2]}/{digest[2:4]}/{digest}{suffix}"


def _tree(root: Path, records: list[dict]) -> Path:
    """一棵只携带引用、不携带字节的 canonical 树。"""

    root.mkdir(parents=True, exist_ok=True)
    (root / "entities" / "地点" / "景区" / "样例").mkdir(parents=True, exist_ok=True)
    (root / "entities" / "地点" / "景区" / "样例" / "asset.refs.json").write_text(
        json.dumps({"assets": records}, ensure_ascii=False),
        encoding="utf-8",
    )
    return root


def _held_library(root: Path, bodies: list[bytes]) -> Path:
    library = root / "content_library"
    library.mkdir(parents=True, exist_ok=True)
    for body in bodies:
        admit_library_bytes(body, kind=MEDIA_KIND, library_root=library)
    return library


def test_a_release_whose_every_reference_is_held_has_a_standing_media_closure(
    tmp_path: Path,
) -> None:
    digest = _digest(_BODY)
    tree = _tree(
        tmp_path / "publish",
        [{"assetId": "a1", "sha256": f"sha256:{digest}", "objectKey": _object_key(digest), "bytes": len(_BODY)}],
    )
    library = _held_library(tmp_path / "lib", [_BODY])

    report = judge_media_closure(media_references_in_tree(tree), library_root=library)

    assert report.verdict is MediaClosureVerdict.HONOURED
    assert report.honoured
    assert report.unhonoured == ()
    assert [outcome.state for outcome in report.outcomes] == [MediaHoldingState.HONOURED]


def test_the_closure_verdict_does_not_read_a_copy_kept_inside_the_release_tree(
    tmp_path: Path,
) -> None:
    """t1：结论只由库给出。树里另存一份字节不能把不可兑现变成可兑现。"""

    digest = _digest(_BODY)
    tree = _tree(
        tmp_path / "publish",
        [{"assetId": "a1", "sha256": f"sha256:{digest}", "objectKey": _object_key(digest), "bytes": len(_BODY)}],
    )
    # 与库条目同名同内容的一份副本就摆在树里，位置与 objectKey 声明的一致。
    inside = tree / _object_key(digest)
    inside.parent.mkdir(parents=True, exist_ok=True)
    inside.write_bytes(_BODY)
    empty_library = tmp_path / "lib"
    empty_library.mkdir(parents=True, exist_ok=True)

    report = judge_media_closure(media_references_in_tree(tree), library_root=empty_library)

    assert report.verdict is MediaClosureVerdict.REFERENCES_UNHONOURED
    assert [outcome.state for outcome in report.unhonoured] == [MediaHoldingState.ABSENT]


def test_an_absent_holding_fails_closed_and_points_back_at_the_one_reference(
    tmp_path: Path,
) -> None:
    """t2：不返回空路径也不跳过该对象，且结果能定位到那一条引用。"""

    held, missing = _digest(_BODY), _digest(_OTHER)
    tree = _tree(
        tmp_path / "publish",
        [
            {"assetId": "held", "sha256": f"sha256:{held}", "objectKey": _object_key(held), "bytes": len(_BODY)},
            {"assetId": "gone", "sha256": f"sha256:{missing}", "objectKey": _object_key(missing), "bytes": len(_OTHER)},
        ],
    )
    library = _held_library(tmp_path / "lib", [_BODY])
    references = media_references_in_tree(tree)

    report = judge_media_closure(references, library_root=library)

    assert report.verdict is MediaClosureVerdict.REFERENCES_UNHONOURED
    assert len(report.outcomes) == 2, "可兑现的那一条同样要留下结论，不能只报失败项"
    absent = report.unhonoured
    assert [outcome.state for outcome in absent] == [MediaHoldingState.ABSENT]
    assert absent[0].reference.digest == missing
    assert "asset.refs.json#$.assets[1]" in absent[0].reference.reference_ref
    assert absent[0].recovery is MediaHoldingRecoveryAction.ADMIT_CARRIED_BYTES

    gone = next(reference for reference in references if reference.digest == missing)
    with pytest.raises(MediaHoldingAbsent):
        resolve_reference_bytes(gone, library_root=library)


def test_a_size_that_disagrees_with_the_record_is_drift_and_not_absence(
    tmp_path: Path,
) -> None:
    """t2：缺席与漂移不合并——库里有字节但不是记录里那一份。"""

    digest = _digest(_BODY)
    tree = _tree(
        tmp_path / "publish",
        [{"assetId": "a1", "sha256": f"sha256:{digest}", "objectKey": _object_key(digest), "bytes": len(_BODY) + 41}],
    )
    library = _held_library(tmp_path / "lib", [_BODY])
    references = media_references_in_tree(tree)

    report = judge_media_closure(references, library_root=library)

    assert report.verdict is MediaClosureVerdict.REFERENCES_UNHONOURED
    outcome = report.unhonoured[0]
    assert outcome.state is MediaHoldingState.DRIFTED
    assert outcome.state is not MediaHoldingState.ABSENT
    assert outcome.recovery is MediaHoldingRecoveryAction.RESTORE_FROM_INDEPENDENT_HOLDER
    assert str(len(_BODY)) in outcome.detail and str(len(_BODY) + 41) in outcome.detail

    with pytest.raises(MediaHoldingDrift):
        resolve_reference_bytes(references[0], library_root=library)


def test_an_unreachable_library_is_one_verdict_and_never_expands_per_reference(
    tmp_path: Path,
) -> None:
    """t3：库整体不可达不被展开成逐对象引用缺席。"""

    bodies = [_BODY, _OTHER]
    records = []
    for index, body in enumerate(bodies):
        digest = _digest(body)
        records.append(
            {
                "assetId": f"a{index}",
                "sha256": f"sha256:{digest}",
                "objectKey": _object_key(digest),
                "bytes": len(body),
            }
        )
    tree = _tree(tmp_path / "publish", records)
    detached = tmp_path / "volume-went-away"
    references = media_references_in_tree(tree)

    report = judge_media_closure(references, library_root=detached)

    assert report.verdict is MediaClosureVerdict.LIBRARY_UNREACHABLE
    assert report.outcomes == (), "库不可达时一条引用都没被判过，不能报成逐条缺席"
    assert report.reference_count == len(bodies), "未被判的引用条数仍要如实呈现"
    assert report.library_recovery is MediaHoldingRecoveryAction.REATTACH_LIBRARY
    assert "holdings" not in report.to_document(), (
        "空数组会读成「零条不可兑现」，而真实结论是这些引用一条都没判"
    )

    with pytest.raises(ContentLibraryUnreachable):
        resolve_reference_bytes(references[0], library_root=detached)


def test_a_reachable_but_empty_library_is_absence_rather_than_unreachable(
    tmp_path: Path,
) -> None:
    """库在场却是空的，与库不在场是两件事：前者每条引用都判得了。"""

    digest = _digest(_BODY)
    tree = _tree(
        tmp_path / "publish",
        [{"assetId": "a1", "sha256": f"sha256:{digest}", "objectKey": _object_key(digest), "bytes": len(_BODY)}],
    )
    empty = tmp_path / "lib"
    empty.mkdir(parents=True)

    report = judge_media_closure(media_references_in_tree(tree), library_root=empty)

    assert report.verdict is MediaClosureVerdict.REFERENCES_UNHONOURED
    assert report.verdict is not MediaClosureVerdict.LIBRARY_UNREACHABLE
    assert [outcome.state for outcome in report.outcomes] == [MediaHoldingState.ABSENT]


def test_the_three_unhonoured_reasons_are_distinguishable_types(tmp_path: Path) -> None:
    """三类失败共一个基类但互不相等，只判「不可兑现」的读取方仍然正确。"""

    assert issubclass(ContentLibraryUnreachable, MediaHoldingError)
    assert issubclass(MediaHoldingAbsent, MediaHoldingError)
    assert issubclass(MediaHoldingDrift, MediaHoldingError)
    distinct = {ContentLibraryUnreachable, MediaHoldingAbsent, MediaHoldingDrift}
    assert len(distinct) == 3
    for error in distinct:
        assert not issubclass(error, tuple(distinct - {error})), (
            f"{error.__name__} 不能是另一类失败的子类，否则 except 顺序会决定语义"
        )


def test_durability_is_not_established_by_bytes_being_readable_right_now(
    tmp_path: Path,
) -> None:
    """t4 的默认态：库当前可读不构成耐久性，闭包成立也不置位。"""

    digest = _digest(_BODY)
    tree = _tree(
        tmp_path / "publish",
        [{"assetId": "a1", "sha256": f"sha256:{digest}", "objectKey": _object_key(digest), "bytes": len(_BODY)}],
    )
    library = _held_library(tmp_path / "lib", [_BODY])

    report = judge_media_closure(media_references_in_tree(tree), library_root=library)

    assert report.honoured
    assert report.durability is MediaDurabilityState.NOT_ESTABLISHED
    assert report.to_document()["durability"] == "not_established"


def test_durability_only_moves_on_a_complete_restore_attestation(tmp_path: Path) -> None:
    digest = _digest(_BODY)
    tree = _tree(
        tmp_path / "publish",
        [{"assetId": "a1", "sha256": f"sha256:{digest}", "objectKey": _object_key(digest), "bytes": len(_BODY)}],
    )
    library = _held_library(tmp_path / "lib", [_BODY])
    references = media_references_in_tree(tree)

    verified = judge_media_closure(
        references,
        library_root=library,
        durability_attestation=DurabilityAttestation(
            independent_holder_ref="holder://independent",
            restore_target_ref="/isolated/restore/target",
            restore_verified_at="2026-08-27T00:00:00Z",
        ),
    )
    assert verified.durability is MediaDurabilityState.VERIFIED

    for omitted in ("independent_holder_ref", "restore_target_ref", "restore_verified_at"):
        fields = {
            "independent_holder_ref": "holder://independent",
            "restore_target_ref": "/isolated/restore/target",
            "restore_verified_at": "2026-08-27T00:00:00Z",
        }
        fields[omitted] = ""
        with pytest.raises(ValueError, match=omitted):
            DurabilityAttestation(**fields)


def test_refetching_the_original_capture_is_not_offered_as_a_recovery_route(
    tmp_path: Path,
) -> None:
    """t5：可重新采集原始素材不计入任何恢复路径。"""

    routes = {str(action) for action in MediaHoldingRecoveryAction}
    assert routes == {
        "restore_from_independent_holder",
        "admit_carried_bytes",
        "reattach_library",
        "none",
    }
    for route in routes:
        assert "refetch" not in route and "recollect" not in route and "reacquire" not in route


def test_reclaimed_source_originals_are_not_part_of_the_media_closure(
    tmp_path: Path,
) -> None:
    """t5：原始采集素材已被回收，它不进闭包，因此回收不改变闭包结论。

    权利快照与 `sourceAssets` 记录带着自己的摘要与大小，但不声明 `objectKey`——它们
    没有声明由库持有，把它们算进闭包会让一个交付字节齐全的 release 判成不成立。
    """

    digest = _digest(_BODY)
    reclaimed = _digest(b"a 267MB source original that was reclaimed")
    tree = tmp_path / "publish"
    (tree / "entities" / "样例").mkdir(parents=True)
    (tree / "entities" / "样例" / "asset.refs.json").write_text(
        json.dumps(
            {
                "assets": [
                    {
                        "assetId": "delivered",
                        "sha256": f"sha256:{digest}",
                        "objectKey": _object_key(digest),
                        "bytes": len(_BODY),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (tree / "entities" / "样例" / "rights.json").write_text(
        json.dumps(
            {
                "sourceAssets": [{"sha256": f"sha256:{reclaimed}", "bytes": 267327343}],
                "commercialRights": {"snapshot": {"sha256": f"sha256:{reclaimed}", "bytes": 3121}},
            }
        ),
        encoding="utf-8",
    )
    library = _held_library(tmp_path / "lib", [_BODY])

    references = media_references_in_tree(tree)

    assert [reference.digest for reference in references] == [digest]
    assert judge_media_closure(references, library_root=library).honoured


def test_a_reference_without_a_declared_size_is_judged_on_presence_only(
    tmp_path: Path,
) -> None:
    """`bytes` 缺席是合法记录形态，不塌陷成 0——否则每条这类引用都判成漂移。"""

    digest = _digest(_BODY)
    tree = _tree(
        tmp_path / "publish",
        [{"assetId": "a1", "sha256": f"sha256:{digest}", "objectKey": _object_key(digest), "width": 3840}],
    )
    library = _held_library(tmp_path / "lib", [_BODY])
    references = media_references_in_tree(tree)

    assert references[0].declared_bytes is None
    report = judge_media_closure(references, library_root=library)

    assert report.honoured
    assert "declares no size" in report.outcomes[0].detail
    assert "declaredBytes" not in report.to_document()["holdings"][0]


def test_a_record_that_disagrees_with_its_own_object_key_is_refused_before_judging(
    tmp_path: Path,
) -> None:
    """记录自相矛盾时没有「该取哪份字节」的答案，按任一侧兑现都是替它选一个取值。"""

    declared, keyed = _digest(_BODY), _digest(_OTHER)
    tree = _tree(
        tmp_path / "publish",
        [{"assetId": "a1", "sha256": f"sha256:{declared}", "objectKey": _object_key(keyed), "bytes": len(_BODY)}],
    )

    with pytest.raises(MediaReferenceRecordError, match="disagrees with its own objectKey"):
        media_references_in_tree(tree)


def test_a_record_declaring_an_object_key_without_a_digest_is_refused(
    tmp_path: Path,
) -> None:
    digest = _digest(_BODY)
    tree = _tree(tmp_path / "publish", [{"assetId": "a1", "objectKey": _object_key(digest)}])

    with pytest.raises(MediaReferenceRecordError, match="no sha256"):
        media_references_in_tree(tree)


def test_the_same_digest_declared_twice_keeps_both_locations(tmp_path: Path) -> None:
    """去重会让摘要指不回任何一个对象，而 t2 要求结果能定位到那一条引用。"""

    digest = _digest(_BODY)
    record = {
        "assetId": "a1",
        "sha256": f"sha256:{digest}",
        "objectKey": _object_key(digest),
        "bytes": len(_BODY),
    }
    tree = _tree(tmp_path / "publish", [record, dict(record, assetId="a2")])
    empty = tmp_path / "lib"
    empty.mkdir(parents=True)

    report = judge_media_closure(media_references_in_tree(tree), library_root=empty)

    assert len(report.unhonoured) == 2
    assert {outcome.reference.record_path for outcome in report.unhonoured} == {
        "$.assets[0]",
        "$.assets[1]",
    }


def test_the_canonical_tree_declares_only_library_held_delivery_bytes(tmp_path: Path) -> None:
    """在真实 canonical 树上跑一次采集，证明判据不依赖构造出来的形态。

    只断言采集结果的性质而不断言条数：条数随发布内容变化，写死会让每次新发布都
    在这里红一次，而它要钉的是「采集到的每一条都是库应持有的交付字节」。
    """

    # 走仓内实际路径而不是 `core.paths.PUBLISH_ROOT`：测试进程把后者隔离到空临时
    # 根，照那里采集会一条都采不到，于是「零条引用」被这条判据读成通过。
    publish = ROOT / "quwoquan_data" / "publish"
    assert publish.is_dir(), publish

    references = media_references_in_tree(publish)

    assert references, "canonical 树必须声明至少一条由库持有的交付字节"
    for reference in references:
        assert len(reference.digest) == 64
        assert reference.document_ref.endswith(".json")
        assert reference.record_path.startswith("$")
        assert reference.declared_bytes is None or reference.declared_bytes > 0
    assert len({reference.digest for reference in references}) <= len(references)


def _minimal_release(release_root: Path, *, release_id: str, assets: list[dict]) -> Path:
    """一个只声明媒体引用、不物化任何字节副本的 release。"""

    payload = release_root / release_id / "payload"
    payload.mkdir(parents=True, exist_ok=True)
    (payload / "desired_state.json").write_text(
        json.dumps(
            {
                "schema": "quwoquan_data.release_desired_state",
                "releaseId": release_id,
                "desiredRefs": {"posts": [], "entities": [], "creators": [], "tags": []},
            }
        ),
        encoding="utf-8",
    )
    (payload / "media_manifest.json").write_text(
        json.dumps(
            {
                "schema": "quwoquan_data.release_media_manifest",
                "releaseId": release_id,
                "sourceOwner": "qwq_data",
                "assets": assets,
                "issues": [],
                "counts": {"assets": len(assets), "issues": 0},
            }
        ),
        encoding="utf-8",
    )
    return payload


def _holding_issues(release_id: str) -> list[str]:
    from content.release.canonical.integrity import scan_release_integrity

    report = scan_release_integrity(release_id)
    return [
        issue
        for issue in report["issues"]
        if "HOLDING_UNREACHABLE" in issue or "MEDIA_LIBRARY_UNREACHABLE" in issue
    ]


def test_release_integrity_judges_the_manifest_declaration_not_the_payload_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """t1：release 目录里一份媒体副本都没有，闭包仍由库给出成立结论。

    先前这条路上判据从 `payload/media/` 枚举物化文件，那个目录整个不在场时枚举出零
    条持有，于是「一条都没判过」与「每一条都完好」得出同一个结论。

    与下一条测试成对：两者的 release 结构相同、副本同样不在场，只有库里有没有那份
    字节不同。因此「这里没有 issue」证明的是结论由库给出，而不是判定被跳过了。
    """

    from core import paths as core_paths

    monkeypatch.setattr(core_paths, "RELEASE_ROOT", tmp_path / "releases")
    digest = _digest(_BODY)
    admit_library_bytes(_BODY, kind=MEDIA_KIND)
    release_id = "20260827--media-closure--manifest-declared--pilot-001"
    payload = _minimal_release(
        tmp_path / "releases",
        release_id=release_id,
        assets=[
            {
                "assetId": "a1",
                "kind": "image",
                "version": 1,
                "contentType": "image/jpeg",
                "sha256": f"sha256:{digest}",
                "bytes": len(_BODY),
                "privateObjectKey": _object_key(digest),
                "ownerRefs": ["posts/x"],
                "rightsSnapshotRefs": ["rights/x.json"],
            }
        ],
    )
    assert not (payload / "media").exists(), "这个 release 不物化任何字节副本"

    from content.release.canonical.integrity import scan_release_integrity

    report = scan_release_integrity(release_id)
    assert report["stats"]["assetCount"] == 1, "清单必须被读到，否则下面那条断言是空判"
    assert [
        issue
        for issue in report["issues"]
        if "HOLDING_UNREACHABLE" in issue or "MEDIA_LIBRARY_UNREACHABLE" in issue
    ] == []


def test_release_integrity_fails_closed_when_the_library_drops_a_declared_holding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """t2：清单声明的引用库里没有时判否，且指回那一条引用。"""

    from core import paths as core_paths

    monkeypatch.setattr(core_paths, "RELEASE_ROOT", tmp_path / "releases")
    body = b"a body this release declares but the library will not hold" + tmp_path.name.encode()
    digest = _digest(body)
    entry = library_cas_path(MEDIA_KIND, digest)
    if entry.exists():
        entry.chmod(0o644)
        entry.unlink()
    release_id = "20260827--media-closure--library-dropped--pilot-001"
    _minimal_release(
        tmp_path / "releases",
        release_id=release_id,
        assets=[
            {
                "assetId": "a1",
                "kind": "image",
                "version": 1,
                "contentType": "image/jpeg",
                "sha256": f"sha256:{digest}",
                "bytes": len(body),
                "privateObjectKey": _object_key(digest),
                "ownerRefs": ["posts/x"],
                "rightsSnapshotRefs": ["rights/x.json"],
            }
        ],
    )

    issues = _holding_issues(release_id)

    assert len(issues) == 1, issues
    assert "HOLDING_UNREACHABLE" in issues[0]
    assert digest in issues[0]
    assert "media_manifest.json#$.assets[0]" in issues[0]
    assert str(MediaHoldingState.ABSENT) in issues[0]
    assert str(MediaHoldingRecoveryAction.ADMIT_CARRIED_BYTES) in issues[0]


def test_release_integrity_reports_a_declared_size_that_the_library_disagrees_with(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core import paths as core_paths

    monkeypatch.setattr(core_paths, "RELEASE_ROOT", tmp_path / "releases")
    digest = _digest(_BODY)
    admit_library_bytes(_BODY, kind=MEDIA_KIND)
    release_id = "20260827--media-closure--size-drift--pilot-001"
    _minimal_release(
        tmp_path / "releases",
        release_id=release_id,
        assets=[
            {
                "assetId": "a1",
                "kind": "image",
                "version": 1,
                "contentType": "image/jpeg",
                "sha256": f"sha256:{digest}",
                "bytes": len(_BODY) + 7,
                "privateObjectKey": _object_key(digest),
                "ownerRefs": ["posts/x"],
                "rightsSnapshotRefs": ["rights/x.json"],
            }
        ],
    )

    issues = _holding_issues(release_id)

    assert len(issues) == 1, issues
    assert str(MediaHoldingState.DRIFTED) in issues[0]
    assert str(MediaHoldingState.ABSENT) not in issues[0]


def test_a_manifest_asset_without_a_digest_is_refused_rather_than_skipped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """清单里一条不可用的声明不能被跳过——跳过后它就不在任何判定的覆盖里。"""

    from core import paths as core_paths

    monkeypatch.setattr(core_paths, "RELEASE_ROOT", tmp_path / "releases")
    release_id = "20260827--media-closure--unusable-record--pilot-001"
    _minimal_release(
        tmp_path / "releases",
        release_id=release_id,
        assets=[{"assetId": "a1", "kind": "image", "version": 1, "bytes": 7}],
    )

    from content.release.canonical.integrity import scan_release_integrity

    issues = [
        issue
        for issue in scan_release_integrity(release_id)["issues"]
        if "unusable media reference" in issue
    ]
    assert len(issues) == 1, issues
    assert "declares no sha256" in issues[0]


def test_manifest_references_take_their_identity_from_the_digest_not_the_key_shape(
    tmp_path: Path,
) -> None:
    """公开切片 key 与内容寻址 key 解析到同一个持有方，不各判一次。"""

    digest = _digest(_BODY)
    private = {
        "assetId": "a1",
        "sha256": f"sha256:{digest}",
        "bytes": len(_BODY),
        "privateObjectKey": _object_key(digest),
    }
    public = {
        "assetId": "a1",
        "sha256": f"sha256:{digest}",
        "bytes": len(_BODY),
        "publicSliceKey": "media/image/s/asset/a1/v1/source.jpg",
    }
    from content.release.canonical.media_holding_closure import (
        media_references_in_release_manifest,
    )

    by_private = media_references_in_release_manifest({"assets": [private]})
    by_public = media_references_in_release_manifest({"assets": [public]})

    assert by_private[0].digest == by_public[0].digest == digest
    assert by_private[0].declared_bytes == by_public[0].declared_bytes


def test_a_holding_absent_from_a_reachable_library_names_the_carried_bytes_route(
    tmp_path: Path,
) -> None:
    """缺席的恢复出路是「灌入受版本控制的随体字节」，那是一条真实存在的路径。"""

    digest = _digest(_BODY)
    reference = MediaReference(
        digest=digest,
        declared_bytes=len(_BODY),
        document_ref="entities/样例/asset.refs.json",
        record_path="$.assets[0]",
    )
    empty = tmp_path / "lib"
    empty.mkdir(parents=True)

    report = judge_media_closure((reference,), library_root=empty)

    assert report.outcomes[0].recovery is MediaHoldingRecoveryAction.ADMIT_CARRIED_BYTES
    assert not library_cas_path(MEDIA_KIND, digest, library_root=empty).exists()
