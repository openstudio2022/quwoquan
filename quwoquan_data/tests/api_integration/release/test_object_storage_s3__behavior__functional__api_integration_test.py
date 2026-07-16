"""S3-compatible（local-gamma MinIO）统一对象存储集成测试。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from core.object_storage import S3ObjectStorage, store_artifact  # noqa: E402
from support.gamma_object_storage import resolve_gamma_object_storage  # noqa: E402


@pytest.mark.api_integration
def test_s3_compatible_storage_roundtrip_and_idempotency(tmp_path):
    connection = resolve_gamma_object_storage()
    storage = S3ObjectStorage(
        bucket=connection.bucket,
        endpoint=connection.endpoint,
        region=connection.region,
        access_key=connection.access_key,
        secret_key=connection.secret_key,
        ca_bundle=str(connection.ca_bundle),
    )
    try:
        storage.client.create_bucket(Bucket=connection.bucket)
    except Exception as exc:
        status = int(
            ((getattr(exc, "response", {}) or {}).get("ResponseMetadata") or {}).get("HTTPStatusCode")
            or 0
        )
        if status not in {200, 409}:
            pytest.fail(
                "GATE_BLOCK: local Gamma object storage is not ready at the Ops topology endpoint: "
                f"{type(exc).__name__}"
            )
    source = tmp_path / "release.json"
    source.write_text('{"release":"local-gamma"}', encoding="utf-8")
    first = store_artifact(
        source,
        kind="release",
        logical_ref="release/local-gamma/release.json",
        storage=storage,
        prefix="integration",
    )
    second = store_artifact(
        source,
        kind="release",
        logical_ref="release/local-gamma/release.json",
        storage=storage,
        prefix="integration",
    )
    assert first["objectKey"] == second["objectKey"]
    assert storage.get_bytes(first["objectKey"]) == source.read_bytes()
    storage.client.delete_object(Bucket=connection.bucket, Key=first["objectKey"])
