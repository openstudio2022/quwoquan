# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#req-006
"""Pre-contract immutable releases rebuild forward without legacy UAT reads."""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "quwoquan_data/scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from content.release.canonical.release_contract_migration import (  # noqa: E402
    ReleaseContractMigrationError,
    migrate_release_contract,
    release_contract_migration_precheck,
)
from content.release.canonical.release_header import validate_release_header  # noqa: E402
from content.release.canonical.release_uat_sample_plan import (  # noqa: E402
    release_object_digest,
    validate_release_uat_sample_plan,
)
from core.release_layout import objects_merkle, payload_digest, payload_file  # noqa: E402
from verify.verify_release_lifecycle import release_lifecycle_issues  # noqa: E402

SOURCE_ID = "release-20260829-alpha-fourcarrier-slice-002"
TARGET_ID = "release-current-contract-b"


def _write_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
    )


def _source_release(tmp_path: Path) -> tuple[Path, bytes]:
    fixture = (
        Path.cwd()
        / ".qwq_output/data/releases"
        / "release-20260829-alpha-fourcarrier-slice-002"
    )
    if not fixture.is_dir():
        pytest.skip("workspace historical release fixture is unavailable")
    release_root = tmp_path / "releases"
    source = release_root / SOURCE_ID
    shutil.copytree(fixture, source)
    return release_root, b"".join(
        path.relative_to(source).as_posix().encode() + b"\0" + path.read_bytes()
        for path in sorted(source.rglob("*"))
        if path.is_file()
    )


def test_precheck_and_apply_create_fresh_exact_release_without_touching_source(
    tmp_path: Path,
) -> None:
    release_root, source_before = _source_release(tmp_path)

    precheck = release_contract_migration_precheck(
        release_root=release_root,
        source_release_id=SOURCE_ID,
        new_release_id=TARGET_ID,
    )
    assert precheck["status"] == "ready"
    assert precheck["sourceSampleContractState"] == "retired_sample_fields"
    assert not (release_root / TARGET_ID).exists()

    result = migrate_release_contract(
        release_root=release_root,
        source_release_id=SOURCE_ID,
        new_release_id=TARGET_ID,
    )
    target = release_root / TARGET_ID
    assert result["status"] == "migrated"
    assert objects_merkle(target) == objects_merkle(release_root / SOURCE_ID)
    assert release_lifecycle_issues(TARGET_ID, release_root=release_root) == []
    assert source_before == b"".join(
        path.relative_to(release_root / SOURCE_ID).as_posix().encode()
        + b"\0"
        + path.read_bytes()
        for path in sorted((release_root / SOURCE_ID).rglob("*"))
        if path.is_file()
    )

    plan = json.loads(
        payload_file(target, "uat/sample_plan.json").read_text(encoding="utf-8")
    )
    assert all(
        set(sample)
        == {"sampleId", "carrier", "objectId", "objectRef", "objectDigest"}
        for sample in plan["samples"]
    )
    validate_release_uat_sample_plan(plan)
    for sample in plan["samples"]:
        assert sample["objectDigest"] == release_object_digest(
            payload_file(target, str(sample["objectRef"]))
        )
    header = validate_release_header(
        json.loads(payload_file(target, "release.json").read_text(encoding="utf-8"))
    )
    assert header["contractMigration"] == {
        "sourceReleaseId": SOURCE_ID,
        "sourcePayloadSha256": precheck["sourcePayloadSha256"],
        "sourceCanonicalMerkle": precheck["sourceCanonicalMerkle"],
        "sourceSamplePlanRef": "uat/sample_plan.json",
        "sourceSamplePlanDigest": precheck["sourceSamplePlanDigest"],
        "reasonCode": "RELEASE_UAT_SAMPLE_PLAN_CONTRACT_CUTOVER",
    }


def test_migration_requires_fresh_identity_and_exact_retired_shape(
    tmp_path: Path,
) -> None:
    release_root, _ = _source_release(tmp_path)
    with pytest.raises(ReleaseContractMigrationError, match="REQUIRES_FRESH_RELEASE_ID"):
        release_contract_migration_precheck(
            release_root=release_root,
            source_release_id=SOURCE_ID,
            new_release_id=SOURCE_ID,
        )

    sample_path = payload_file(release_root / SOURCE_ID, "uat/sample_plan.json")
    sample = json.loads(sample_path.read_text(encoding="utf-8"))
    sample["samples"][0]["guessedRef"] = "objects/entities/guessed"
    _write_json(sample_path, sample)
    header_path = payload_file(release_root / SOURCE_ID, "release.json")
    header = json.loads(header_path.read_text(encoding="utf-8"))
    header["samplePlanDigest"] = "sha256:" + hashlib.sha256(
        sample_path.read_bytes()
    ).hexdigest()
    _write_json(header_path, header)
    attestation_path = release_root / SOURCE_ID / "attestations/release.json"
    attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
    attestation["payloadSha256"] = payload_digest(release_root / SOURCE_ID)
    _write_json(attestation_path, attestation)

    with pytest.raises(ReleaseContractMigrationError, match="SOURCE_UNSUPPORTED"):
        release_contract_migration_precheck(
            release_root=release_root,
            source_release_id=SOURCE_ID,
            new_release_id=TARGET_ID,
        )
