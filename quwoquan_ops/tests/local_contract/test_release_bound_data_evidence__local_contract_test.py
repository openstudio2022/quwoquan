# spec_ref: specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-001
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.ci import release_bound_data_evidence as evidence


DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
RELEASE_ID = "release-golden-001"


def _content_identity() -> dict[str, object]:
    return {
        "readinessReceiptRef": (
            f"env/alpha/runs/data-release/{RELEASE_ID}/verify-001/"
            "release-readiness.json"
        ),
        "releaseId": RELEASE_ID,
        "sourceOwner": "qwq_data",
        "manifestDigest": DIGEST_A,
        "mediaManifestDigest": DIGEST_B,
        "importRunId": "import-001",
        "verifyRunId": "verify-001",
    }


def _binding() -> dict[str, object]:
    return {
        "workId": "post-video",
        "postId": "post-video",
        "postRef": "video/travel/west-lake/1",
        "assetId": "asset-video",
        "assetVersion": 1,
        "publicSliceKey": "media/video/s/asset/asset-video/v1/source.mp4",
        "expectedMimeType": "video/mp4",
        "expectedBytes": 4,
        "expectedHash": DIGEST_A,
    }


def _video_report() -> dict[str, object]:
    content = _content_identity()
    binding = _binding()
    delivery = {
        "tlsSystemTrust": True,
        "requestPath": "/media/video/s/asset/asset-video/v1/source.mp4",
        "requestQuery": "",
        "fullStatus": 200,
        "rangeStatus": 206,
        "mimeType": "video/mp4",
        "rangeMimeType": "video/mp4",
        "contentLength": 4,
        "observedBytes": 4,
        "contentRange": "bytes 0-3/4",
        "rangeBytes": 4,
        "etag": '"asset-video-v1"',
        "rangeEtag": '"asset-video-v1"',
        "observedHash": DIGEST_A,
        "rangeSha256": DIGEST_B,
        "cacheControl": "public, max-age=31536000, immutable",
        "rangeCacheControl": "public, max-age=31536000, immutable",
        "corsAllowOrigin": "*",
        "rangeCorsAllowOrigin": "*",
        "cacheKey": "/media/video/s/asset/asset-video/v1/source.mp4",
        "rangeCacheKey": "/media/video/s/asset/asset-video/v1/source.mp4",
        "signedQueryStatus": 200,
        "signedQueryCacheControl": "no-store",
        "signedQueryCacheKey": "",
    }
    public_url = (
        "https://cdn.alpha.quwoquan.com/media/video/s/asset/"
        "asset-video/v1/source.mp4"
    )
    return {
        "schema": "quwoquan_ops.release_video_delivery_evidence",
        "status": "passed",
        "capturedAt": "2026-07-28T13:00:00Z",
        "environment": "alpha",
        "target": "alpha-local",
        "rolloutStage": "local",
        "release": content,
        "video": {
            **binding,
            "publicUrl": public_url,
        },
        "delivery": delivery,
        "playback": {"durationMs": 1200, "firstFrameDecoded": True},
        "publicSliceKey": binding["publicSliceKey"],
        "videoAuthority": "https://cdn.alpha.quwoquan.com/media/video",
        "rangeStatus": 206,
        "contentType": "video/mp4",
    }


class ReleaseBoundDataEvidenceContractTest(unittest.TestCase):
    def test_video_report_reuses_canonical_binding_and_delivery_validator(self) -> None:
        report = _video_report()
        with mock.patch.object(
            evidence,
            "load_release_video_binding",
            return_value=_binding(),
        ) as binding_loader:
            result = evidence._validate_video_evidence(
                report,
                readiness_path=Path("/evidence/release-readiness.json"),
                content_identity=_content_identity(),
                environment="alpha",
                target="alpha-local",
            )
        self.assertEqual(result["rangeStatus"], 206)
        self.assertTrue(result["firstFrameDecoded"])
        self.assertEqual(result["sha256"], DIGEST_A)
        binding_loader.assert_called_once_with(
            Path("/evidence/release-readiness.json"),
            expected_environment="alpha",
            requested_work_id="post-video",
            requested_asset_id="asset-video",
        )

    def test_schema_hash_and_public_authority_drift_block(self) -> None:
        for mutation in ("schema", "hash", "authority", "public-path"):
            with self.subTest(mutation=mutation):
                report = _video_report()
                if mutation == "schema":
                    report["secondTruth"] = True
                elif mutation == "hash":
                    report["delivery"]["observedHash"] = DIGEST_B
                else:
                    report["video"]["publicUrl"] = (
                        "https://other.example.net/media/video/source.mp4"
                        if mutation == "authority"
                        else "https://cdn.alpha.quwoquan.com/media/video/wrong.mp4"
                    )
                with (
                    mock.patch.object(
                        evidence,
                        "load_release_video_binding",
                        return_value=_binding(),
                    ),
                    self.assertRaises(evidence.DataEvidenceError),
                ):
                    evidence._validate_video_evidence(
                        report,
                        readiness_path=Path("/evidence/release-readiness.json"),
                        content_identity=_content_identity(),
                        environment="alpha",
                        target="alpha-local",
                    )

    def test_data_evidence_recomputes_canonical_readiness_and_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            readiness = (
                root
                / "env/alpha/runs/data-release"
                / RELEASE_ID
                / "verify-001/release-readiness.json"
            )
            rollback = root / "env/alpha/rollback.json"
            video = root / "env/alpha/video.json"
            payloads = {
                readiness: {},
                rollback: {"schema": "lifecycle-from-file"},
                video: {"schema": "video-from-file"},
            }
            for path, payload in payloads.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            expected_release = {
                "releaseId": RELEASE_ID,
                "manifestDigest": DIGEST_A,
                "mediaManifestDigest": DIGEST_B,
                "importRunId": "import-001",
                "verifyRunId": "verify-001",
            }
            with (
                mock.patch.dict(os.environ, {"QWQ_OUTPUT_ROOT": str(root)}),
                mock.patch.object(
                    evidence,
                    "load_release_content_identity",
                    return_value=_content_identity(),
                ) as readiness_loader,
                mock.patch.object(
                    evidence,
                    "environment_lifecycle_issues",
                    return_value=[],
                ) as readiness_verifier,
                mock.patch.object(
                    evidence,
                    "lifecycle_exit_issues",
                    return_value=[],
                ) as lifecycle,
                mock.patch.object(
                    evidence,
                    "_validate_video_evidence",
                    return_value={"rangeStatus": 206},
                ) as video_validator,
            ):
                result = evidence.validate_data_evidence(
                    data_output_root=root,
                    readiness_path=readiness,
                    rollback_path=rollback,
                    video_path=video,
                    environment="alpha",
                    target="alpha-local",
                    expected_release=expected_release,
                )
            self.assertEqual(result, {"rangeStatus": 206})
            readiness_loader.assert_called_once_with(
                readiness.resolve(),
                expected_environment="alpha",
            )
            readiness_verifier.assert_called_once_with(
                RELEASE_ID,
                environment="alpha",
                import_run_id="import-001",
                verify_run_id="verify-001",
                prod_mode="activated",
                release_root=root.resolve() / "data/releases",
                output_root=root.resolve(),
            )
            self.assertEqual(
                lifecycle.call_args.args[0],
                {"schema": "lifecycle-from-file"},
            )
            self.assertEqual(
                video_validator.call_args.args[0],
                {"schema": "video-from-file"},
            )

    def test_lifecycle_recomputation_failure_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = [
                root
                / "env/alpha/runs/data-release"
                / RELEASE_ID
                / "verify-001/release-readiness.json",
                root / "rollback.json",
                root / "video.json",
            ]
            for path in paths:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}\n", encoding="utf-8")
            with (
                mock.patch.dict(os.environ, {"QWQ_OUTPUT_ROOT": str(root)}),
                mock.patch.object(
                    evidence,
                    "load_release_content_identity",
                    return_value=_content_identity(),
                ),
                mock.patch.object(
                    evidence,
                    "environment_lifecycle_issues",
                    return_value=[],
                ),
                mock.patch.object(
                    evidence,
                    "lifecycle_exit_issues",
                    return_value=["rollback result file is missing"],
                ),
                self.assertRaisesRegex(
                    evidence.DataEvidenceError,
                    "canonical Data lifecycle failed",
                ),
            ):
                evidence.validate_data_evidence(
                    data_output_root=root,
                    readiness_path=paths[0],
                    rollback_path=paths[1],
                    video_path=paths[2],
                    environment="alpha",
                    target="alpha-local",
                    expected_release={
                        "releaseId": RELEASE_ID,
                        "manifestDigest": DIGEST_A,
                        "mediaManifestDigest": DIGEST_B,
                        "importRunId": "import-001",
                        "verifyRunId": "verify-001",
                    },
                )

    def test_formal_readiness_verifier_failure_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            readiness = (
                root
                / "env/alpha/runs/data-release"
                / RELEASE_ID
                / "verify-001/release-readiness.json"
            )
            rollback = root / "rollback.json"
            video = root / "video.json"
            for path in (readiness, rollback, video):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}\n", encoding="utf-8")
            with (
                mock.patch.dict(os.environ, {"QWQ_OUTPUT_ROOT": str(root)}),
                mock.patch.object(
                    evidence,
                    "load_release_content_identity",
                    return_value=_content_identity(),
                ),
                mock.patch.object(
                    evidence,
                    "environment_lifecycle_issues",
                    return_value=["release-readiness.json: guestLogin is required"],
                ),
                self.assertRaisesRegex(
                    evidence.DataEvidenceError,
                    "canonical Data readiness failed",
                ),
            ):
                evidence.validate_data_evidence(
                    data_output_root=root,
                    readiness_path=readiness,
                    rollback_path=rollback,
                    video_path=video,
                    environment="alpha",
                    target="alpha-local",
                    expected_release={
                        "releaseId": RELEASE_ID,
                        "manifestDigest": DIGEST_A,
                        "mediaManifestDigest": DIGEST_B,
                        "importRunId": "import-001",
                        "verifyRunId": "verify-001",
                    },
                )

    def test_evidence_payload_is_loaded_from_bound_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            readiness = (
                root
                / "env/alpha/runs/data-release"
                / RELEASE_ID
                / "verify-001/release-readiness.json"
            )
            rollback = root / "rollback.json"
            video = root / "video.json"
            for path in (readiness, video):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}\n", encoding="utf-8")
            rollback.write_text("not-json\n", encoding="utf-8")
            with (
                mock.patch.dict(os.environ, {"QWQ_OUTPUT_ROOT": str(root)}),
                self.assertRaisesRegex(
                    evidence.DataEvidenceError,
                    "rollback-receipt is not valid JSON",
                ),
            ):
                evidence.validate_data_evidence(
                    data_output_root=root,
                    readiness_path=readiness,
                    rollback_path=rollback,
                    video_path=video,
                    environment="alpha",
                    target="alpha-local",
                    expected_release={
                        "releaseId": RELEASE_ID,
                        "manifestDigest": DIGEST_A,
                        "mediaManifestDigest": DIGEST_B,
                        "importRunId": "import-001",
                        "verifyRunId": "verify-001",
                    },
                )


if __name__ == "__main__":
    unittest.main()
