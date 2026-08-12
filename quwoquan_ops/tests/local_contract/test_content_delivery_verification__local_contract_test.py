from __future__ import annotations

import argparse
import json
from pathlib import Path

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib.content_delivery_verification import (
    verify_content_delivery,
)


_DIGEST = "sha256:" + "a" * 64


def _write(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _fixture(root: Path) -> Path:
    release_id = "research-m100-first"
    environment = "alpha"
    evidence = root / "env/alpha/runs/data-release" / release_id / "verify-001"
    import_path = _write(
        evidence / "import.json",
        {
            "status": "active",
            "environment": environment,
            "releaseId": release_id,
            "manifestDigest": _DIGEST,
            "counts": {
                "postsLoaded": 3,
                "postsUpserted": 3,
                "outboxEventsReady": 3,
                "outboxEventsAppended": 3,
            },
        },
    )
    creator_path = _write(
        evidence / "creator-import.json",
        {
            "status": "active",
            "environment": environment,
            "releaseId": release_id,
            "verifiedCreatorIds": ["creator-a", "creator-b"],
        },
    )
    homepage_path = _write(
        evidence / "homepage-api-verification.json",
        {
            "passed": True,
            "environment": environment,
            "releaseId": release_id,
            "entities": [{"entityRef": "entity-a"}],
        },
    )
    post_path = _write(
        evidence / "post-api-verification.json",
        {
            "passed": True,
            "environment": environment,
            "releaseId": release_id,
            "posts": [
                {"postId": "post-article"},
                {"postId": "post-image"},
                {"postId": "post-video"},
            ],
            "creators": [
                {"personaId": "persona-a", "profileStatus": 200},
                {"personaId": "persona-b", "profileStatus": 200},
            ],
            "searchQueries": [
                {"targetType": "post", "targetId": "post-article"},
                {"targetType": "post", "targetId": "post-image"},
                {"targetType": "post", "targetId": "post-video"},
                {"targetType": "author", "targetId": "persona-a"},
                {"targetType": "author", "targetId": "persona-b"},
            ],
            "feedQueries": [
                {"name": "typed_article", "matchedPostIds": ["post-article"]},
                {"name": "typed_image", "matchedPostIds": ["post-image"]},
                {"name": "typed_video", "matchedPostIds": ["post-video"]},
                {
                    "name": "homepage_recommend",
                    "matchedPostIds": ["post-article", "post-video"],
                },
            ],
        },
    )
    return _write(
        evidence / "release-readiness.json",
        {
            "schema": "quwoquan_data.environment_release_readiness",
            "passed": True,
            "environment": environment,
            "releaseId": release_id,
            "manifestDigest": _DIGEST,
            "postIds": ["post-article", "post-image", "post-video"],
            "entityRefs": ["entity-a"],
            "creatorIds": ["creator-a", "creator-b"],
            "contentImportReportRef": import_path.relative_to(root).as_posix(),
            "creatorAttributionRef": creator_path.relative_to(root).as_posix(),
            "homepageApiVerificationRef": homepage_path.relative_to(root).as_posix(),
            "postApiVerificationRef": post_path.relative_to(root).as_posix(),
        },
    )


def test_content_delivery_verifies_only_the_runtime_content_closure(
    tmp_path: Path,
) -> None:
    readiness = _fixture(tmp_path)
    report = verify_content_delivery(
        output_root=tmp_path,
        readiness_path=readiness,
        environment="alpha",
        release_id="research-m100-first",
        manifest_digest=_DIGEST,
    )
    assert report["result"] == "ready"
    assert report["checks"] == {"delivery": "passed"}
    assert report["counts"] == {
        "manifestPosts": 3,
        "importedPosts": 3,
        "outboxPosts": 3,
        "searchablePosts": 3,
        "recommendablePosts": 3,
        "homepages": 1,
        "personas": 2,
    }


def test_content_delivery_blocks_count_drift_without_unrelated_gates(
    tmp_path: Path,
) -> None:
    readiness = _fixture(tmp_path)
    import_path = readiness.with_name("import.json")
    imported = json.loads(import_path.read_text(encoding="utf-8"))
    imported["counts"]["postsUpserted"] = 2
    _write(import_path, imported)

    report = verify_content_delivery(
        output_root=tmp_path,
        readiness_path=readiness,
        environment="alpha",
        release_id="research-m100-first",
        manifest_digest=_DIGEST,
    )
    assert report["result"] == "blocked"
    assert report["checks"] == {"delivery": "failed"}
    assert report["issues"] == ["Manifest/import Post counts differ"]


def test_stackctl_content_delivery_is_an_integration_only_readback(
    monkeypatch,
    tmp_path: Path,
) -> None:
    readiness = _fixture(tmp_path)
    monkeypatch.setattr(stackctl, "output_root", lambda: tmp_path)
    monkeypatch.setattr(
        stackctl,
        "_data_release_readiness_path",
        lambda **_kwargs: readiness,
    )
    result = stackctl.command_verify(
        argparse.Namespace(
            kind="content-delivery",
            profile="integration",
            env="alpha",
            target="",
            report_dir=str(tmp_path / "report"),
            data_release_id="research-m100-first",
            data_verify_run_id="verify-001",
            data_manifest_digest=_DIGEST,
        )
    )
    assert result["exitCode"] == 0
    assert result["summary"] == "content delivery verification passed"
    assert json.loads((tmp_path / "report/report.json").read_text())["result"] == "ready"


def test_stackctl_parser_exposes_content_delivery_kind() -> None:
    args = stackctl.build_parser().parse_args(
        [
            "verify",
            "--env",
            "alpha",
            "--kind",
            "content-delivery",
            "--profile",
            "integration",
            "--data-release-id",
            "release-a",
            "--data-verify-run-id",
            "verify-a",
            "--data-manifest-digest",
            _DIGEST,
        ]
    )
    assert args.kind == "content-delivery"
