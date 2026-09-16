# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#req-002
"""Release admission 对来源证据与 manifest 的媒体身份实行 typed fail-closed。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

DATA_ROOT = next(
    parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data"
)
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from content.release.canonical import (  # noqa: E402
    aggregate_release_closure,
    post_transaction_sources,
    release_admission,
)
from content.release.canonical.object_transaction_contract import (  # noqa: E402
    ObjectTransactionError,
)

_OBJECT_REF = "posts/image/风光/测试/1"
_ASSET_ID = "source-image-1"
_SHA256 = "sha256:" + "1" * 64


def _source_asset(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "assetId": _ASSET_ID,
        "sha256": _SHA256,
        "bytes": 10,
        "mimeType": "image/jpeg",
        "contentSha256": _SHA256,
        "sourceUrl": "https://commons.wikimedia.org/wiki/File:test.jpg",
        "license": "CC BY-SA 4.0",
        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0",
        "authorizationProof": "https://creativecommons.org/licenses/by-sa/4.0",
        "creator": "测试作者",
        "platform": "Wikimedia Commons",
        "capturedAt": "2026-09-15T00:00:00Z",
        "rightsStatus": "verified",
        "rightsIssues": [],
    }
    row.update(overrides)
    return row


def _object_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    manifest_assets: list[dict[str, object]],
    source_asset: dict[str, object] | None = None,
) -> list[dict[str, object]]:
    root = tmp_path / "object"
    root.mkdir()
    (root / "manifest.json").write_text(
        json.dumps({"contentType": "image", "assets": manifest_assets}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        aggregate_release_closure,
        "object_root",
        lambda *_args, **_kwargs: root,
    )
    monkeypatch.setattr(
        post_transaction_sources,
        "read_object_sources",
        lambda *_args, **_kwargs: [
            {"assets": [source_asset or _source_asset()]}
        ],
    )
    return release_admission._object_rows(
        tmp_path,
        {"entities": [], "posts": [_OBJECT_REF.removeprefix("posts/")]},
        output_root=tmp_path,
    )


def test_source_asset_missing_from_manifest_is_typed_and_never_leaks_stop_iteration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(ObjectTransactionError) as raised:
        _object_rows(tmp_path, monkeypatch, manifest_assets=[])

    assert str(raised.value) == (
        f"DATA.RELEASE.MEDIA_MISSING: {_OBJECT_REF} assetId={_ASSET_ID}"
    )
    assert not isinstance(raised.value, StopIteration)
    assert not isinstance(raised.value.__cause__, StopIteration)


@pytest.mark.parametrize(
    "drift",
    [
        {"sha256": "sha256:" + "2" * 64},
        {"bytes": 11},
    ],
)
def test_source_manifest_sha_or_bytes_identity_drift_is_typed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    drift: dict[str, object],
) -> None:
    with pytest.raises(
        ObjectTransactionError,
        match=rf"^DATA\.RELEASE\.MEDIA_DRIFT: {_OBJECT_REF} assetId={_ASSET_ID}$",
    ):
        _object_rows(
            tmp_path,
            monkeypatch,
            manifest_assets=[
                {
                    "assetId": _ASSET_ID,
                    "sha256": _SHA256,
                    "bytes": 10,
                    "mimeType": "image/jpeg",
                    **drift,
                }
            ],
        )


def test_matching_source_and_manifest_media_identity_is_projected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows = _object_rows(
        tmp_path,
        monkeypatch,
        manifest_assets=[
            {
                "assetId": _ASSET_ID,
                "sha256": _SHA256,
                "bytes": 10,
                "mimeType": "image/jpeg",
            }
        ],
    )

    assert len(rows) == 1
    assert rows[0]["objectRef"] == _OBJECT_REF
    assert len(rows[0]["assets"]) == 1
    assert rows[0]["assets"][0]["assetId"] == _ASSET_ID
    assert rows[0]["assets"][0]["contentSha256"] == _SHA256
    assert rows[0]["assets"][0]["acquisitionStatus"] == "acquired"
