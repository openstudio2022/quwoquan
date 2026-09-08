# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-038.t8
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-038.t9
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-038.t10
"""里程碑 release 的 cohort/handoff 版本化副本：逐字节相同、create-or-same、不成为 handoff-verify 的读取位置。"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

DATA_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(DATA_SCRIPTS))

from content.release.canonical import handler  # noqa: E402
from content.release.canonical.object_transaction_contract import ObjectTransactionError  # noqa: E402

RELEASE_ID = "20260907--travel-production-M1000--six-step-cumulative-001"


def _canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _release_dir(tmp_path: Path) -> Path:
    release_dir = tmp_path / "output/data/releases" / RELEASE_ID
    release_dir.mkdir(parents=True)
    (release_dir / "cohort.json").write_bytes(_canonical({
        "schema": "quwoquan_data.release_cohort", "milestone": "M1000", "releaseClass": "production",
        "objectRefs": ["entities/地点/景区/西湖"], "producerBaselineRevision": "a" * 40,
        "expectedCarrierCounts": {"homepage": 1, "article": 0, "image": 0, "video": 0},
    }))
    (release_dir / "producer_release_handoff.json").write_bytes(_canonical({
        "schema": "quwoquan_data.producer_release_handoff", "releaseId": RELEASE_ID, "milestone": "M1000",
    }))
    return release_dir


def test_versioned_copy_is_byte_identical_and_create_or_same(tmp_path: Path) -> None:
    release_dir = _release_dir(tmp_path)
    reference_root = tmp_path / "repo/quwoquan_data/reference/releases"

    first = handler.write_versioned_release_copy(release_dir=release_dir, reference_root=reference_root, release_id=RELEASE_ID)
    assert first["cohort.json"] == "created" and first["producer_release_handoff.json"] == "created"
    for name in ("cohort.json", "producer_release_handoff.json"):
        assert (reference_root / RELEASE_ID / name).read_bytes() == (release_dir / name).read_bytes()

    # 重放：副本已存在且相同 → replayed，不报错。
    second = handler.write_versioned_release_copy(release_dir=release_dir, reference_root=reference_root, release_id=RELEASE_ID)
    assert second["cohort.json"] == "replayed" and second["producer_release_handoff.json"] == "replayed"

    # 输出根字节漂移 → fail closed，副本不被覆盖。
    before = (reference_root / RELEASE_ID / "cohort.json").read_bytes()
    (release_dir / "cohort.json").write_bytes(_canonical({"schema": "quwoquan_data.release_cohort", "objectRefs": ["x"]}))
    with pytest.raises(ObjectTransactionError, match="REFERENCE_COPY_CONFLICT"):
        handler.write_versioned_release_copy(release_dir=release_dir, reference_root=reference_root, release_id=RELEASE_ID)
    assert (reference_root / RELEASE_ID / "cohort.json").read_bytes() == before

    # 输出根缺文件 → fail closed，不从副本反向补。
    (release_dir / "cohort.json").write_bytes(before)
    (release_dir / "producer_release_handoff.json").unlink()
    with pytest.raises(ObjectTransactionError, match="REFERENCE_COPY_SOURCE_MISSING"):
        handler.write_versioned_release_copy(release_dir=release_dir, reference_root=reference_root, release_id=RELEASE_ID)


def test_handoff_verify_reads_only_the_output_root_not_the_versioned_copy(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    release_dir = _release_dir(tmp_path)
    reference_root = tmp_path / "repo/quwoquan_data/reference/releases"
    handler.write_versioned_release_copy(release_dir=release_dir, reference_root=reference_root, release_id=RELEASE_ID)
    assert (reference_root / RELEASE_ID / "producer_release_handoff.json").is_file()

    # 输出根被清理后，即便副本在场，handoff-verify 也只认输出根：GATE_BLOCK 而不是读副本冒充重放。
    (release_dir / "producer_release_handoff.json").unlink()
    args = SimpleNamespace(release_id=RELEASE_ID, release_root=str(release_dir.parent))
    with pytest.raises(SystemExit) as exc:
        handler.handle_handoff_verify(args)
    assert "GATE_BLOCK" in str(exc.value)
    assert capsys.readouterr().out == ""
