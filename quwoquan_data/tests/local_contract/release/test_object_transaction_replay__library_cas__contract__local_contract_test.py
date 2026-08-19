# spec_ref: specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-002
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import pytest

from content.release.canonical import handler as release_handler
from content.release.canonical.application import rollback_object_transaction
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _tree_digest,
)
from content.release.canonical.object_transaction_replay import (
    replay_object_transaction_package,
)
from core.io import read_json
from support.object_transaction_fixtures import (
    OBJECT_REF,
    TRANSACTION_ID,
    build_canonical,
    build_package,
)


def _library_entry(root: Path, digest: str) -> Path:
    value = digest.removeprefix("sha256:")
    return root / value[:2] / value[2:4] / value


def test_exact_package_replay_cli_binds_explicit_library_and_roots(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    observed: dict[str, object] = {}

    def replay(**kwargs: object) -> dict[str, object]:
        observed.update(kwargs)
        return {
            "schema": "quwoquan_data.object_transaction_package_replay_result",
            "status": "applied",
        }

    monkeypatch.setattr(release_handler, "replay_object_transaction_package", replay)
    parser = argparse.ArgumentParser()
    release_handler.register_parser(
        parser.add_subparsers(dest="command", required=True)
    )
    args = parser.parse_args(
        [
            "release",
            "object-transaction",
            "replay-package",
            "--replay-id",
            "entity-replay",
            "--source-package-root",
            str(tmp_path / "source-package"),
            "--media-library-root",
            str(tmp_path / "library"),
            "--output-root",
            str(tmp_path / "output"),
            "--publish-root",
            str(tmp_path / "publish"),
        ]
    )
    args.handler(args)

    assert observed == {
        "replay_id": "entity-replay",
        "source_package_root": tmp_path / "source-package",
        "media_library_root": tmp_path / "library",
        "output_root": (tmp_path / "output").resolve(),
        "publish_root": (tmp_path / "publish").resolve(),
    }
    assert json.loads(capsys.readouterr().out)["status"] == "applied"


def test_exact_package_replay_restores_missing_cas_from_explicit_library(
    tmp_path: Path,
) -> None:
    publish = build_canonical(tmp_path)
    source_package = build_package(tmp_path, publish)
    package = read_json(source_package / "object_transaction_package.json")
    source_digest = _tree_digest(source_package)
    library = tmp_path / "media-library"
    for row in package["closure"]["casRefs"]:
        source = source_package / row["sourceRef"]
        target = _library_entry(library, row["sha256"])
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        source.unlink()
    source_without_cas = _tree_digest(source_package)
    output = tmp_path / "output"

    result = replay_object_transaction_package(
        replay_id="entity-exact-replay",
        source_package_root=source_package,
        media_library_root=library,
        output_root=output,
        publish_root=publish,
    )

    assert result["status"] == "applied"
    assert result["transactionId"] == TRANSACTION_ID
    assert (publish / "entities" / OBJECT_REF / "manifest.json").is_file()
    assert _tree_digest(source_package) == source_without_cas
    assert source_digest != source_without_cas
    snapshot = Path(result["packageRoot"])
    assert all(
        (snapshot / row["sourceRef"]).is_file()
        for row in package["closure"]["casRefs"]
    )

    repeated = replay_object_transaction_package(
        replay_id="entity-exact-replay",
        source_package_root=source_package,
        media_library_root=library,
        output_root=output,
        publish_root=publish,
    )
    assert repeated["idempotent"] is True
    assert repeated["canonicalObjectSha256"] == result["canonicalObjectSha256"]

    rollback = rollback_object_transaction(
        publish_root=publish,
        output_root=output,
        transaction_id=TRANSACTION_ID,
    )
    assert rollback["status"] == "rolled_back"
    assert not (publish / "entities" / OBJECT_REF).exists()

    replayed = replay_object_transaction_package(
        replay_id="entity-exact-replay",
        source_package_root=source_package,
        media_library_root=library,
        output_root=output,
        publish_root=publish,
    )
    assert replayed["status"] == "replayed"
    assert (publish / "entities" / OBJECT_REF).is_dir()


def test_exact_package_replay_rejects_existing_different_target(
    tmp_path: Path,
) -> None:
    publish = build_canonical(tmp_path)
    source_package = build_package(tmp_path, publish)
    package = read_json(source_package / "object_transaction_package.json")
    library = tmp_path / "media-library"
    for row in package["closure"]["casRefs"]:
        source = source_package / row["sourceRef"]
        target = _library_entry(library, row["sha256"])
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    existing = publish / "entities" / OBJECT_REF
    existing.mkdir(parents=True)
    (existing / "manifest.json").write_text('{"different":true}\n', encoding="utf-8")
    before = _tree_digest(existing)

    with pytest.raises(ObjectTransactionError, match="REPLAY_TARGET_CONFLICT"):
        replay_object_transaction_package(
            replay_id="entity-existing-conflict",
            source_package_root=source_package,
            media_library_root=library,
            output_root=tmp_path / "output",
            publish_root=publish,
        )
    assert _tree_digest(existing) == before


def test_exact_package_replay_rejects_library_digest_drift_before_mutation(
    tmp_path: Path,
) -> None:
    publish = build_canonical(tmp_path)
    source_package = build_package(tmp_path, publish)
    package = read_json(source_package / "object_transaction_package.json")
    library = tmp_path / "media-library"
    row = package["closure"]["casRefs"][0]
    entry = _library_entry(library, row["sha256"])
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_bytes(b"tampered")
    (source_package / row["sourceRef"]).unlink()

    with pytest.raises(ObjectTransactionError, match="LIBRARY_HOLDING_DRIFT"):
        replay_object_transaction_package(
            replay_id="entity-tampered-replay",
            source_package_root=source_package,
            media_library_root=library,
            output_root=tmp_path / "output",
            publish_root=publish,
        )
    assert not (publish / "entities" / OBJECT_REF).exists()
