from __future__ import annotations

from quwoquan_ops.gate import verify_media_delivery_contract as gate


def _issues(value: str) -> list[str]:
    issues: list[str] = []
    gate._validate_media_field_value(
        rel_path="fixture.json",
        field_key="objectKey",
        value=value,
        manifest_keys=set(),
        force_mock_seed_ban=False,
        issues=issues,
        seen=set(),
    )
    return issues


def test_media_delivery_accepts_canonical_slice_and_rejects_unversioned_slice() -> None:
    assert _issues("media/image/s/asset/fixture/v1/cover.png") == []
    assert any(
        "恰有一个 /vN/" in issue
        for issue in _issues("media/image/s/asset/fixture/cover.png")
    )
