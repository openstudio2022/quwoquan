from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from content.source.research.homepage_article_source_ready_batch import (
    HomepageArticleSourceReadyBatchError,
    freeze_homepage_article_source_ready_batch,
)
from quwoquan_data.tests.local_contract.source.test_scale_source_pool_homepage_article__catalog_projection__contract__local_contract_test import (
    IDENTITY,
    _article_candidate,
    _homepage_candidate,
    _image_bytes,
)


def _digest(value: dict[str, object]) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _file_sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_content(root: Path, ref: str, seed: str | bytes) -> dict[str, str]:
    path = root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    body = seed.encode("utf-8") if isinstance(seed, str) else seed
    path.write_bytes(body)
    digest = "sha256:" + hashlib.sha256(body).hexdigest()
    return {"ref": ref, "contentSha256": digest, "fileSha256": digest}


def _provenance(root: Path, *, prefix: str, coverage_ref: str, coverage_digest: str) -> dict[str, object]:
    bindings: list[dict[str, str]] = []
    for name in ("discovery", "acquisition", "rights", "quality"):
        ref = f"provenance/{prefix}-{name}.json"
        _write_json(root / ref, {"schema": f"test.{name}", "candidate": prefix})
        bindings.append({"ref": ref, "fileSha256": _file_sha(root / ref)})
    return {
        "coverageProjectionRef": coverage_ref,
        "coverageProjectionDigest": coverage_digest,
        "coverageProjectionFileSha256": _file_sha(root / coverage_ref),
        "discoveryEvidenceRef": bindings[0]["ref"],
        "discoveryEvidenceFileSha256": bindings[0]["fileSha256"],
        "acquisitionEvidenceRefs": [bindings[1]],
        "rightsEvidenceRefs": [bindings[2]],
        "qualityEvidenceRefs": [bindings[3]],
    }


def _capsule(
    root: Path,
    *,
    carrier: str,
    candidate: dict[str, object],
    coverage_ref: str,
    coverage_digest: str,
) -> tuple[dict[str, object], str]:
    candidate_id = str(candidate["candidateId"])
    if carrier == "homepage":
        primary = candidate["primarySource"]
        hero = candidate["hero"]
        assert isinstance(primary, dict) and isinstance(hero, dict)
        body = _write_content(
            root, str(primary["bodyEvidenceRef"]), "body:homepage-west-lake-0"
        )
        media = [{
            "assetId": hero["assetId"],
            "role": "hero",
            **_write_content(
                root,
                str(hero["assetRef"]),
                _image_bytes("homepage-west-lake-0:hero-0"),
            ),
        }]
    else:
        body = _write_content(
            root, str(candidate["bodyEvidenceRef"]), "body:article-hangzhou-0"
        )
        media = []
        for asset in candidate["assets"]:
            assert isinstance(asset, dict)
            role = str(asset["role"])
            media.append({
                "assetId": asset["assetId"],
                "role": role,
                **_write_content(
                    root,
                    str(asset["assetRef"]),
                    _image_bytes(f"article-hangzhou-0:article-0-{role}"),
                ),
            })
    stable: dict[str, object] = {
        "schema": "quwoquan_data.homepage_article_source_ready_candidate",
        "carrier": carrier,
        **IDENTITY,
        "candidate": candidate,
        "materialization": {"body": body, "media": media},
        "provenance": _provenance(
            root,
            prefix=candidate_id,
            coverage_ref=coverage_ref,
            coverage_digest=coverage_digest,
        ),
    }
    capsule = {**stable, "capsuleDigest": _digest(stable)}
    ref = f"capsules/{carrier}.json"
    _write_json(root / ref, capsule)
    return capsule, ref


def _batch(root: Path) -> tuple[dict[str, object], Path]:
    coverage_digest = "sha256:" + "f" * 64
    coverage_ref = "coverage/projection.json"
    _write_json(
        root / coverage_ref,
        {"schema": "test.coverage_projection", "projectionDigest": coverage_digest},
    )
    homepage = _homepage_candidate()
    article = _article_candidate()
    homepage_capsule, homepage_ref = _capsule(
        root,
        carrier="homepage",
        candidate=homepage,
        coverage_ref=coverage_ref,
        coverage_digest=coverage_digest,
    )
    article_capsule, article_ref = _capsule(
        root,
        carrier="article",
        candidate=article,
        coverage_ref=coverage_ref,
        coverage_digest=coverage_digest,
    )
    stable: dict[str, object] = {
        "schema": "quwoquan_data.homepage_article_source_ready_batch",
        "sourceSetId": "m100-homepage-article-source-set",
        "targetScale": "M100",
        **IDENTITY,
        "createdAt": "2026-08-08T00:00:00Z",
        "coverageProjection": {
            "ref": coverage_ref,
            "digest": coverage_digest,
            "fileSha256": _file_sha(root / coverage_ref),
        },
        "candidateCapsules": [
            {
                "carrier": "homepage",
                "candidateId": homepage["candidateId"],
                "ref": homepage_ref,
                "digest": homepage_capsule["capsuleDigest"],
                "fileSha256": _file_sha(root / homepage_ref),
            },
            {
                "carrier": "article",
                "candidateId": article["candidateId"],
                "ref": article_ref,
                "digest": article_capsule["capsuleDigest"],
                "fileSha256": _file_sha(root / article_ref),
            },
        ],
        "counts": {"homepage": 1, "article": 1},
    }
    batch = {**stable, "sourceSetDigest": _digest(stable)}
    path = root / "batch.json"
    _write_json(path, batch)
    return batch, path


def test_batch_projects_physical_capsules_into_create_once_catalogs(tmp_path: Path) -> None:
    evidence_root = tmp_path / "evidence"
    batch, batch_path = _batch(evidence_root)
    output_root = tmp_path / "output"

    result = freeze_homepage_article_source_ready_batch(
        batch_path,
        evidence_root=evidence_root,
        output_root=output_root,
        minimum_homepage_candidate_count=1,
        minimum_article_candidate_count=1,
    )
    replay = freeze_homepage_article_source_ready_batch(
        batch_path,
        evidence_root=evidence_root,
        output_root=output_root,
        minimum_homepage_candidate_count=1,
        minimum_article_candidate_count=1,
    )

    assert replay == result
    assert result["sourceSetDigest"] == batch["sourceSetDigest"]
    assert result["homepage"]["candidateCount"] == 1
    assert result["article"]["candidateCount"] == 1
    assert (output_root / result["homepage"]["catalogRef"]).is_file()
    assert (output_root / result["article"]["catalogRef"]).is_file()


@pytest.mark.parametrize("tamper", ["body", "capsule", "identity", "symlink"])
def test_batch_rejects_physical_or_identity_drift(tmp_path: Path, tamper: str) -> None:
    evidence_root = tmp_path / "evidence"
    batch, batch_path = _batch(evidence_root)
    if tamper == "body":
        (evidence_root / "sources/homepage-unit-0/source.md").write_text(
            "tampered", encoding="utf-8"
        )
    elif tamper == "capsule":
        capsule_path = evidence_root / "capsules/homepage.json"
        capsule = json.loads(capsule_path.read_text(encoding="utf-8"))
        capsule["candidate"]["candidateId"] = "drift"
        _write_json(capsule_path, capsule)
        batch["candidateCapsules"][0]["fileSha256"] = _file_sha(capsule_path)
        stable = {key: value for key, value in batch.items() if key != "sourceSetDigest"}
        batch["sourceSetDigest"] = _digest(stable)
        _write_json(batch_path, batch)
    elif tamper == "identity":
        capsule_path = evidence_root / "capsules/article.json"
        capsule = json.loads(capsule_path.read_text(encoding="utf-8"))
        capsule["sourceDigest"] = "sha256:" + "9" * 64
        stable_capsule = {
            key: value for key, value in capsule.items() if key != "capsuleDigest"
        }
        capsule["capsuleDigest"] = _digest(stable_capsule)
        _write_json(capsule_path, capsule)
        batch["candidateCapsules"][1]["digest"] = capsule["capsuleDigest"]
        batch["candidateCapsules"][1]["fileSha256"] = _file_sha(capsule_path)
        stable = {key: value for key, value in batch.items() if key != "sourceSetDigest"}
        batch["sourceSetDigest"] = _digest(stable)
        _write_json(batch_path, batch)
    else:
        target = evidence_root / "capsules/homepage.json"
        saved = target.read_bytes()
        target.unlink()
        outside = tmp_path / "outside.json"
        outside.write_bytes(saved)
        target.symlink_to(outside)

    with pytest.raises(HomepageArticleSourceReadyBatchError) as captured:
        freeze_homepage_article_source_ready_batch(
            batch_path,
            evidence_root=evidence_root,
            output_root=tmp_path / "output",
            minimum_homepage_candidate_count=1,
            minimum_article_candidate_count=1,
        )

    assert captured.value.code == "DATA.SOURCE.INVALID_EVIDENCE"


def test_batch_shortfall_is_typed_and_does_not_write_catalogs(tmp_path: Path) -> None:
    evidence_root = tmp_path / "evidence"
    _, batch_path = _batch(evidence_root)
    output_root = tmp_path / "output"

    with pytest.raises(HomepageArticleSourceReadyBatchError) as captured:
        freeze_homepage_article_source_ready_batch(
            batch_path,
            evidence_root=evidence_root,
            output_root=output_root,
            minimum_homepage_candidate_count=180,
            minimum_article_candidate_count=180,
        )

    assert captured.value.code == "DATA.SOURCE.POOL_SHORTFALL"
    assert not output_root.exists()
