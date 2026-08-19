# spec_ref: specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-002
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from content.release.canonical.content_pool_record import (
    is_pool_record_admitted,
    latest_pool_record,
)
from content.release.canonical.creator_generation_bootstrap import (
    bootstrap_creator_generation,
)
from content.release.canonical.object_transaction_contract import ObjectTransactionError


def _creator_pool(root: Path, *, creators: tuple[str, ...]) -> tuple[Path, Path]:
    pool = root / "creator-pool"
    library = root / "library"
    evidence = {
        "schema": "fixture.creator.evidence",
        "processResult": "completed",
        "qualityResult": "passed",
    }
    evidence_path = pool / "evidence/system_builtin_author_admission.json"
    evidence_path.parent.mkdir(parents=True)
    evidence_path.write_text(
        json.dumps(evidence, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    evidence_digest = "sha256:" + hashlib.sha256(evidence_path.read_bytes()).hexdigest()
    for index, creator_ref in enumerate(creators):
        body = f"avatar-{creator_ref}".encode()
        digest = hashlib.sha256(body).hexdigest()
        entry = library / digest[:2] / digest[2:4] / digest
        entry.parent.mkdir(parents=True, exist_ok=True)
        entry.write_bytes(body)
        avatar_evidence = {
            "manifestAsset": {
                "assetId": f"avatar-{index}",
                "sha256": f"sha256:{digest}",
            }
        }
        avatar_evidence_path = pool / f"evidence/avatar/{creator_ref}.json"
        avatar_evidence_path.parent.mkdir(parents=True, exist_ok=True)
        avatar_evidence_path.write_text(
            json.dumps(avatar_evidence, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        profile = {
            "creatorProfileId": creator_ref,
            "personaId": f"persona-{index}",
            "authorId": f"author-{index}",
            "version": 1,
            "admission": {
                "processResult": "completed",
                "qualityResult": "passed",
                "evidenceRef": "evidence/system_builtin_author_admission.json",
                "evidenceDigest": evidence_digest,
            },
            "status": "active",
            "displayName": f"Creator {index}",
            "userHandle": f"creator_{index}",
            "headline": "fixture",
            "bio": "fixture",
            "creatorArchetype": "geo_editor",
            "publicProfileTagRefs": ["Topic/旅行"],
            "disclosure": {
                "type": "platform_virtual_creator",
                "displayText": "fixture",
                "visible": True,
            },
            "avatarAsset": {
                "assetId": f"avatar-{index}",
                "kind": "avatar",
                "sha256": f"sha256:{digest}",
                "objectKey": (
                    f"media/objects/sha256/{digest[:2]}/{digest[2:4]}/{digest}.webp"
                ),
                "bytes": len(body),
                "mimeType": "image/webp",
                "evidenceRef": f"evidence/avatar/{creator_ref}.json",
            },
        }
        profile_path = pool / f"profiles/system_builtin/{creator_ref}.creator.yaml"
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        profile_path.write_text(
            yaml.safe_dump(profile, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
    return pool, library


def test_creator_generation_bootstrap_is_atomic_and_uses_explicit_holdings(
    tmp_path: Path,
) -> None:
    creators = ("creator-a", "creator-b")
    creator_pool, library = _creator_pool(tmp_path, creators=creators)
    publish = tmp_path / "generation/publish"

    result = bootstrap_creator_generation(
        generation_id="research-generation",
        creator_refs=creators,
        creator_pool_root=creator_pool,
        media_library_root=library,
        publish_root=publish,
        output_root=tmp_path / "output",
    )

    assert result["creatorRefs"] == list(creators)
    assert result["status"] == "created"
    for creator_ref in creators:
        root = publish / "creators" / creator_ref
        record = latest_pool_record(root, "author")
        assert is_pool_record_admitted(record)
        asset = json.loads((root / "assets.refs.json").read_text())["assets"][0]
        assert (publish / asset["objectKey"]).is_file()


def test_creator_generation_bootstrap_fails_before_publish_on_holding_drift(
    tmp_path: Path,
) -> None:
    creators = ("creator-a", "creator-b")
    creator_pool, library = _creator_pool(tmp_path, creators=creators)
    first = yaml.safe_load(
        (creator_pool / "profiles/system_builtin/creator-a.creator.yaml").read_text()
    )
    digest = first["avatarAsset"]["sha256"].removeprefix("sha256:")
    (library / digest[:2] / digest[2:4] / digest).write_bytes(b"tampered")
    publish = tmp_path / "generation/publish"

    with pytest.raises(ObjectTransactionError, match="LIBRARY_HOLDING_DRIFT"):
        bootstrap_creator_generation(
            generation_id="research-generation",
            creator_refs=creators,
            creator_pool_root=creator_pool,
            media_library_root=library,
            publish_root=publish,
            output_root=tmp_path / "output",
        )
    assert not publish.exists()
