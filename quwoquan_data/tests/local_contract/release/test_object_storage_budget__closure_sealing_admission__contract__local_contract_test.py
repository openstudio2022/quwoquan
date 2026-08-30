"""The single-object storage budget is admission at closure sealing, not a later report.

Sealing a closure into its ``objectClosureDigest`` is the one step both the post
and the entity transaction builder must cross, so binding the budget check there
is what makes "a new carrier forgot to ask" impossible rather than a convention. A
per-asset check cannot see the closure total and so cannot answer "may this object
be published"; a scan that runs after the canonical object is written can only
report what already happened.

Over budget is one whole-object refusal with two separable causes, because they
hand the operator two different next steps: reference fewer assets in this object,
versus replace the one asset that exceeds the object budget by itself. Blocking one
object never blocks the qualified objects beside it in the same batch.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

DATA_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "quwoquan_data"
)
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from content.execution.closure.publish_outcome import (  # noqa: E402
    OBJECT_ASSET_OVER_BUDGET,
    OBJECT_CLOSURE_OVER_BUDGET,
    TypedPublishExclusion,
    is_hard_publish_failure,
    publish_issue_code,
)
from content.release.canonical.object_transaction_contract import (  # noqa: E402
    ObjectStorageBudgetExceeded,
    ObjectTransactionError,
    _admit_object_storage_budget,
)
from verify import verify_object_size_budget as budget_gate  # noqa: E402

MEBIBYTE = 1024 * 1024
# REQ-008 states the illustrated (text+image) object budget as a number; the gate
# owns the per-carrier table, so the number is read there rather than copied.
ILLUSTRATED_OBJECT_BUDGET_BYTES = 10 * MEBIBYTE


def _cas_key(body: bytes) -> tuple[str, str]:
    digest = hashlib.sha256(body).hexdigest()
    return (
        f"media/objects/sha256/{digest[:2]}/{digest[2:4]}/{digest}.jpg",
        f"sha256:{digest}",
    )


def _post_object(
    publish_root: Path,
    *,
    ref: str,
    bodies: list[bytes],
    document_bytes: int = 512,
) -> Path:
    """Write one canonical post object that references ``bodies`` in order.

    Repeating a body repeats only the reference; the library holds one copy, which
    is exactly the case the budget must not charge twice.
    """

    object_root = publish_root / "posts" / ref
    object_root.mkdir(parents=True)
    (object_root / "manifest.json").write_text(
        json.dumps({"ref": ref}) + " " * document_bytes,
        encoding="utf-8",
    )
    rows = []
    for body in bodies:
        object_key, sha256 = _cas_key(body)
        rows.append({"objectKey": object_key, "sha256": sha256})
    (object_root / "asset.refs.json").write_text(
        json.dumps({"assets": rows}), encoding="utf-8"
    )
    return object_root


@pytest.fixture
def library(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Hold the media bodies where the library holds them, addressed by digest.

    Publish carries the reference and the library carries the body, so the budget
    is measured wherever the bytes actually are. Only that resolution is stood in
    for here; the measurement under test stays the real one.
    """

    root = tmp_path / "library"
    root.mkdir()

    def _hold(body: bytes) -> None:
        (root / hashlib.sha256(body).hexdigest()).write_bytes(body)

    def _resolve(sha256: str) -> Path:
        digest = str(sha256).removeprefix("sha256:")
        entry = root / digest
        if not entry.is_file():
            raise budget_gate.MediaHoldingError(f"library holds no body {sha256}")
        return entry

    monkeypatch.setattr(budget_gate, "resolve_media_holding", _resolve)
    return _hold


# spec_ref: specs/feature-tree/discovery-content/media-processing-helper-read/image-delivery-variants/spec.md#req-008
def test_the_illustrated_object_budget_is_ten_mebibytes() -> None:
    assert (
        budget_gate._object_budget_bytes("article")
        == ILLUSTRATED_OBJECT_BUDGET_BYTES
    )
    assert (
        budget_gate._object_budget_bytes("image")
        == ILLUSTRATED_OBJECT_BUDGET_BYTES
    )


# spec_ref: specs/feature-tree/discovery-content/media-processing-helper-read/image-delivery-variants/spec.md#gwt-007.t6
def test_one_media_body_referenced_twice_costs_the_object_once(
    tmp_path: Path,
    library,
) -> None:
    publish_root = tmp_path / "publish"
    body = b"one shared media body" * 64
    library(body)
    _post_object(publish_root, ref="article/work/000/1", bodies=[body])
    _post_object(publish_root, ref="article/work/001/1", bodies=[body, body, body])

    closures, issues = budget_gate.object_closures(publish_root=publish_root)

    assert issues == []
    measured = {row.ref: row.media_bytes for row in closures}
    assert measured["posts/article/work/001/1"] == measured[
        "posts/article/work/000/1"
    ] == len(body), (
        "physical repetition inside one object must not buy it extra budget"
    )


# spec_ref: specs/feature-tree/discovery-content/media-processing-helper-read/image-delivery-variants/spec.md#gwt-007.t3
def test_the_two_over_budget_causes_stay_two_unmerged_codes() -> None:
    assert OBJECT_CLOSURE_OVER_BUDGET != OBJECT_ASSET_OVER_BUDGET
    for code in (OBJECT_CLOSURE_OVER_BUDGET, OBJECT_ASSET_OVER_BUDGET):
        assert code.startswith("DATA.PUBLISH.")


# spec_ref: specs/feature-tree/discovery-content/media-processing-helper-read/image-delivery-variants/spec.md#gwt-007.t4
def test_the_over_budget_terminal_state_carries_its_own_code() -> None:
    """Reading the reason must not depend on the wording of an error message.

    Deriving a code by matching an exception string keeps a translation table
    outside the closed set, so rewording one message would silently change what an
    operator reads as the reason.
    """

    for code in (OBJECT_CLOSURE_OVER_BUDGET, OBJECT_ASSET_OVER_BUDGET):
        failure = ObjectStorageBudgetExceeded(code, "object exceeds its budget")

        assert isinstance(failure, TypedPublishExclusion)
        assert isinstance(failure, ObjectTransactionError)
        assert publish_issue_code(failure) == code

    # The message-matching fallback owns neither code, so neither can be produced
    # by wording alone.
    assert publish_issue_code(
        ObjectTransactionError("object closure over budget")
    ) not in {OBJECT_CLOSURE_OVER_BUDGET, OBJECT_ASSET_OVER_BUDGET}


# spec_ref: specs/feature-tree/discovery-content/media-processing-helper-read/image-delivery-variants/spec.md#gwt-007.t6
def test_an_over_budget_object_does_not_terminate_its_batch() -> None:
    failure = ObjectStorageBudgetExceeded(
        OBJECT_CLOSURE_OVER_BUDGET, "object exceeds its budget"
    )

    assert not is_hard_publish_failure(failure), (
        "an object-level refusal must stay inside object isolation so the "
        "qualified objects in the same batch still reach the release"
    )


# spec_ref: specs/feature-tree/discovery-content/media-processing-helper-read/image-delivery-variants/spec.md#req-008
def test_a_closure_within_budget_seals(tmp_path: Path, library) -> None:
    publish_root = tmp_path / "publish"
    body = b"x" * MEBIBYTE
    library(body)
    object_root = _post_object(publish_root, ref="article/work/000/1", bodies=[body])

    _admit_object_storage_budget(
        object_root, object_kind="posts", object_ref="article/work/000/1"
    )


# spec_ref: specs/feature-tree/discovery-content/media-processing-helper-read/image-delivery-variants/spec.md#gwt-007.t2
def test_a_closure_that_accumulates_past_budget_cannot_be_sealed(
    tmp_path: Path,
    library,
) -> None:
    """Each asset fits; the object does not. Only the closure total can see that."""

    publish_root = tmp_path / "publish"
    bodies = [bytes([index]) * (3 * MEBIBYTE) for index in range(4)]
    for body in bodies:
        library(body)
    object_root = _post_object(
        publish_root, ref="article/work/000/1", bodies=bodies
    )

    with pytest.raises(ObjectStorageBudgetExceeded) as failure:
        _admit_object_storage_budget(
            object_root, object_kind="posts", object_ref="article/work/000/1"
        )

    assert failure.value.issue_code == OBJECT_CLOSURE_OVER_BUDGET


# spec_ref: specs/feature-tree/discovery-content/media-processing-helper-read/image-delivery-variants/spec.md#gwt-007.t3
def test_a_single_asset_past_the_whole_budget_is_its_own_cause(
    tmp_path: Path,
    library,
) -> None:
    publish_root = tmp_path / "publish"
    body = b"y" * (ILLUSTRATED_OBJECT_BUDGET_BYTES + MEBIBYTE)
    library(body)
    object_root = _post_object(
        publish_root, ref="article/work/000/1", bodies=[body]
    )

    with pytest.raises(ObjectStorageBudgetExceeded) as failure:
        _admit_object_storage_budget(
            object_root, object_kind="posts", object_ref="article/work/000/1"
        )

    assert failure.value.issue_code == OBJECT_ASSET_OVER_BUDGET, (
        "replacing one asset and reducing the reference count are different "
        "operator actions, so the two causes cannot merge"
    )


# spec_ref: specs/feature-tree/discovery-content/media-processing-helper-read/image-delivery-variants/spec.md#req-008
def test_an_unresolvable_closure_is_a_failure_rather_than_zero_bytes(
    tmp_path: Path,
    library,
) -> None:
    publish_root = tmp_path / "publish"
    object_root = _post_object(
        publish_root, ref="article/work/000/1", bodies=[b"never held"]
    )

    with pytest.raises(ObjectTransactionError, match="closure could not be measured"):
        _admit_object_storage_budget(
            object_root, object_kind="posts", object_ref="article/work/000/1"
        )
