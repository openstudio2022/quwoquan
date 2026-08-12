from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in os.sys.path:
    os.sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib import release_video_delivery as delivery_contract
from quwoquan_ops.cli.smoke import verify_video_playback_canary as canary


EXPECTED_HASH = "sha256:" + "a" * 64
MANIFEST_DIGEST = "sha256:" + "b" * 64
MEDIA_MANIFEST_DIGEST = "sha256:" + "c" * 64


class VideoPlaybackCanaryContractTest(unittest.TestCase):
    def _topology_target(self, *, env: str = "prod") -> dict[str, object]:
        return {
            "env": env,
            "publicBases": {
                "mediaVideo": (
                    "https://cdn.quwoquan.com/media/video"
                    if env == "prod"
                    else f"https://cdn.{env}.quwoquan.com:19000/media/video"
                ),
            },
            "playbackCanary": {
                "source": "published-release",
                "workIdEnv": "VIDEO_PLAYBACK_CANARY_WORK_ID",
                "publicSliceKeyEnv": "VIDEO_PLAYBACK_CANARY_PUBLIC_SLICE_KEY",
            },
        }

    def _binding(self) -> dict[str, object]:
        return {
            "readinessReceiptRef": (
                "env/prod/runs/data-release/release-a/verify-a/release-readiness.json"
            ),
            "releaseId": "release-a",
            "sourceOwner": "qwq_data",
            "manifestDigest": MANIFEST_DIGEST,
            "mediaManifestDigest": MEDIA_MANIFEST_DIGEST,
            "importRunId": "import-a",
            "verifyRunId": "verify-a",
            "workId": "post-video-a",
            "postId": "post-video-a",
            "postRef": "video/travel/canary/1",
            "assetId": "asset-video-a",
            "assetVersion": 1,
            "publicSliceKey": "media/video/s/asset/asset-video-a/v1/source.mp4",
            "expectedMimeType": "video/mp4",
            "expectedBytes": 4,
            "expectedHash": EXPECTED_HASH,
        }

    def _delivery(self) -> dict[str, object]:
        cache_key = "/media/video/s/asset/asset-video-a/v1/source.mp4"
        return {
            "tlsSystemTrust": True,
            "requestPath": cache_key,
            "requestQuery": "",
            "fullStatus": 200,
            "rangeStatus": 206,
            "mimeType": "video/mp4",
            "rangeMimeType": "video/mp4",
            "contentLength": 4,
            "observedBytes": 4,
            "contentRange": "bytes 0-3/4",
            "rangeBytes": 4,
            "etag": '"release-a"',
            "rangeEtag": '"release-a"',
            "observedHash": EXPECTED_HASH,
            "rangeSha256": "sha256:" + "d" * 64,
            "cacheControl": "public, max-age=31536000, immutable",
            "rangeCacheControl": "public, max-age=31536000, immutable",
            "corsAllowOrigin": "*",
            "rangeCorsAllowOrigin": "*",
            "cacheKey": cache_key,
            "rangeCacheKey": cache_key,
            "signedQueryStatus": 200,
            "signedQueryCacheControl": "no-store",
            "signedQueryCacheKey": "",
        }

    def _run_success(self, argv: list[str], *, env: str = "prod") -> tuple[int, str]:
        output = io.StringIO()
        with (
            mock.patch.object(canary, "load_environment_topology", return_value={}),
            mock.patch.object(
                canary,
                "get_target",
                return_value=self._topology_target(env=env),
            ),
            mock.patch.object(
                canary,
                "resolve_readiness_path",
                return_value=Path("/tmp/release-readiness.json"),
            ),
            mock.patch.object(
                canary,
                "load_release_video_binding",
                return_value=self._binding(),
            ),
            mock.patch.object(
                canary,
                "probe_https_video",
                return_value=self._delivery(),
            ),
            mock.patch.object(canary, "probe_duration_ms", return_value=12_042),
            mock.patch.object(canary, "probe_first_frame", return_value=True),
            redirect_stdout(output),
        ):
            status = canary.main(argv)
        return status, output.getvalue()

    def test_canary_binds_release_and_full_delivery_evidence(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "PROD_TEST_AUTH_TOKEN": "secret-token",
                "PROD_ROLLOUT_STAGE": "canary",
            },
            clear=True,
        ):
            status, output = self._run_success(
                ["--release-readiness", "env/prod/runs/data-release/release-a/verify-a/release-readiness.json"],
            )

        self.assertEqual(status, 0)
        report = json.loads(output)
        self.assertEqual(report["schema"], "quwoquan_ops.release_video_delivery_evidence")
        self.assertEqual(report["release"]["releaseId"], "release-a")
        self.assertEqual(report["delivery"]["fullStatus"], 200)
        self.assertEqual(report["delivery"]["rangeStatus"], 206)
        self.assertEqual(report["delivery"]["observedHash"], EXPECTED_HASH)
        self.assertEqual(report["playback"]["durationMs"], 12_042)
        self.assertTrue(report["playback"]["firstFrameDecoded"])
        self.assertEqual(
            report["video"]["publicUrl"],
            "https://cdn.quwoquan.com/media/video/s/asset/asset-video-a/v1/source.mp4",
        )
        self.assertNotIn("/media/video/media/video/", report["video"]["publicUrl"])
        self.assertNotIn("secret-token", output)
        schema = json.loads(
            (
                ROOT
                / "quwoquan_ops/environments/release_video_delivery_evidence.schema.json"
            ).read_text(encoding="utf-8"),
        )
        Draft202012Validator(schema).validate(report)

    def test_missing_authentication_blocks_hosted_patrol_preflight(self) -> None:
        output = io.StringIO()
        with (
            mock.patch.dict(
                os.environ,
                {"PROD_ROLLOUT_STAGE": "canary"},
                clear=True,
            ),
            redirect_stdout(output),
        ):
            status = canary.main(["--release-readiness", "env/prod/missing.json"])

        self.assertEqual(status, 2)
        self.assertIn("required authentication prerequisite", output.getvalue())

    def test_local_target_uses_same_release_receipt_without_prod_credentials(self) -> None:
        binding = self._binding()
        binding["readinessReceiptRef"] = (
            "env/gamma/runs/data-release/release-a/verify-a/release-readiness.json"
        )
        output = io.StringIO()
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch.object(canary, "load_environment_topology", return_value={}),
            mock.patch.object(
                canary,
                "get_target",
                return_value=self._topology_target(env="gamma"),
            ),
            mock.patch.object(
                canary,
                "resolve_readiness_path",
                return_value=Path("/tmp/release-readiness.json"),
            ),
            mock.patch.object(
                canary,
                "load_release_video_binding",
                return_value=binding,
            ),
            mock.patch.object(
                canary,
                "probe_https_video",
                return_value=self._delivery(),
            ),
            mock.patch.object(canary, "probe_duration_ms", return_value=12_042),
            mock.patch.object(canary, "probe_first_frame", return_value=True),
            redirect_stdout(output),
        ):
            status = canary.main(
                [
                    "--target",
                    "gamma-local",
                    "--release-readiness",
                    "env/gamma/runs/data-release/release-a/verify-a/release-readiness.json",
                ],
            )

        self.assertEqual(status, 0)
        report = json.loads(output.getvalue())
        self.assertEqual(report["environment"], "gamma")
        self.assertEqual(report["rolloutStage"], "local")

    def test_delivery_hash_drift_is_gate_block(self) -> None:
        invalid_delivery = self._delivery()
        invalid_delivery["observedHash"] = "sha256:" + "e" * 64
        output = io.StringIO()
        with (
            mock.patch.dict(
                os.environ,
                {
                    "PROD_TEST_AUTH_TOKEN": "secret-token",
                    "PROD_ROLLOUT_STAGE": "canary",
                },
                clear=True,
            ),
            mock.patch.object(canary, "load_environment_topology", return_value={}),
            mock.patch.object(
                canary,
                "get_target",
                return_value=self._topology_target(),
            ),
            mock.patch.object(
                canary,
                "resolve_readiness_path",
                return_value=Path("/tmp/release-readiness.json"),
            ),
            mock.patch.object(
                canary,
                "load_release_video_binding",
                return_value=self._binding(),
            ),
            mock.patch.object(
                canary,
                "probe_https_video",
                return_value=invalid_delivery,
            ),
            redirect_stdout(output),
        ):
            status = canary.main(["--release-readiness", "env/prod/release-readiness.json"])

        self.assertEqual(status, 2)
        self.assertIn("sha256 drifts", output.getvalue())

    def test_fixture_key_cannot_be_a_release_canary(self) -> None:
        binding = self._binding()
        binding["publicSliceKey"] = "media/video/s/fixture_video_001/source.mp4"
        output = io.StringIO()
        with (
            mock.patch.dict(
                os.environ,
                {
                    "PROD_TEST_AUTH_TOKEN": "secret-token",
                    "PROD_ROLLOUT_STAGE": "canary",
                },
                clear=True,
            ),
            mock.patch.object(canary, "load_environment_topology", return_value={}),
            mock.patch.object(
                canary,
                "get_target",
                return_value=self._topology_target(),
            ),
            mock.patch.object(
                canary,
                "resolve_readiness_path",
                return_value=Path("/tmp/release-readiness.json"),
            ),
            mock.patch.object(
                canary,
                "load_release_video_binding",
                return_value=binding,
            ),
            redirect_stdout(output),
        ):
            status = canary.main(["--release-readiness", "env/prod/release-readiness.json"])

        self.assertEqual(status, 2)
        self.assertIn("must not reference fixture/mock/seed", output.getvalue())

    def test_data_receipt_binds_premium_post_to_canonical_video_asset(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            release_id = "release-a"
            verify_run_id = "verify-a"
            receipt_path = (
                root
                / "env/gamma/runs/data-release"
                / release_id
                / verify_run_id
                / "release-readiness.json"
            )
            import_path = (
                root
                / "env/gamma/runs/data-release"
                / release_id
                / "import-a"
                / "import.json"
            )
            media_path = root / f"data/releases/{release_id}/payload/media_manifest.json"
            attestation_path = (
                root / f"data/releases/{release_id}/attestations/release.json"
            )
            post_tag_path = (
                root
                / f"data/releases/{release_id}/payload/objects/posts/"
                "video/travel/canary/1/tag.refs.json"
            )
            import_path.parent.mkdir(parents=True)
            media_path.parent.mkdir(parents=True)
            attestation_path.parent.mkdir(parents=True)
            post_tag_path.parent.mkdir(parents=True)
            import_report = {
                "schema": "quwoquan.content_import_report",
                "status": "imported",
                "environment": "gamma",
                "releaseId": release_id,
                "sourceOwner": "qwq_data",
                "manifestDigest": MANIFEST_DIGEST,
                "postBindings": [
                    {
                        "postRef": "video/travel/canary/1",
                        "postId": "post-video-a",
                        "contentType": "video",
                        "authorId": "creator-a",
                    },
                ],
            }
            import_path.write_text(json.dumps(import_report), encoding="utf-8")
            attestation_path.write_text(
                json.dumps(
                    {
                        "schema": "quwoquan_data.release_attestation",
                        "releaseId": release_id,
                        "releaseKind": "content",
                        "sourceOwner": "qwq_data",
                        "payloadSha256": MANIFEST_DIGEST,
                    },
                ),
                encoding="utf-8",
            )
            post_tag_path.write_text(
                json.dumps({"tagRefs": ["tag/travel"]}),
                encoding="utf-8",
            )
            media_manifest = {
                "schema": "quwoquan_data.release_media_manifest",
                "releaseId": release_id,
                "sourceOwner": "qwq_data",
                "assets": [
                    {
                        "assetId": "asset-video-a",
                        "kind": "video",
                        "version": 1,
                        "contentType": "video/mp4",
                        "publicSliceKey": (
                            "media/video/s/asset/asset-video-a/v1/source.mp4"
                        ),
                        "sha256": EXPECTED_HASH,
                        "bytes": 4,
                        "ownerRefs": ["posts/video/travel/canary/1"],
                    },
                ],
            }
            media_path.write_text(json.dumps(media_manifest), encoding="utf-8")
            media_digest = "sha256:" + hashlib.sha256(media_path.read_bytes()).hexdigest()
            receipt = {
                "schema": "quwoquan_data.environment_release_readiness",
                "environment": "gamma",
                "releaseId": release_id,
                "releaseKind": "content",
                "sourceOwner": "qwq_data",
                "manifestDigest": MANIFEST_DIGEST,
                "mediaManifestDigest": media_digest,
                "importRunId": "import-a",
                "verifyRunId": verify_run_id,
                "postIds": ["post-video-a"],
                "creatorIds": ["creator-a"],
                "tagRefs": ["tag/travel"],
                "mediaAssetIds": ["asset-video-a"],
                "feedQueries": [
                    {
                        "name": "typed_video",
                        "path": "/content/feed",
                        "query": "identity=work&type=video&limit=10",
                        "status": 200,
                        "releaseBound": True,
                        "matchedPostIds": ["post-video-a"],
                    },
                    {
                        "name": "premium_stream",
                        "path": "/content/feed",
                        "query": "sort=recommend&channelId=premium_stream&limit=10",
                        "status": 200,
                        "releaseBound": True,
                        "matchedPostIds": ["post-video-a"],
                    },
                ],
                "contentImportReportRef": import_path.relative_to(root).as_posix(),
                "mediaManifestRef": media_path.relative_to(root).as_posix(),
                "passed": True,
            }
            receipt["verificationChecksum"] = delivery_contract._canonical_checksum(receipt)
            receipt_path.parent.mkdir(parents=True)
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

            with mock.patch.dict(os.environ, {"QWQ_OUTPUT_ROOT": str(root)}, clear=False):
                binding = delivery_contract.load_release_video_binding(
                    receipt_path,
                    expected_environment="gamma",
                )

            import_report["status"] = "active"
            import_path.write_text(json.dumps(import_report), encoding="utf-8")
            with (
                mock.patch.dict(
                    os.environ,
                    {"QWQ_OUTPUT_ROOT": str(root)},
                    clear=False,
                ),
                self.assertRaisesRegex(
                    delivery_contract.ReleaseVideoDeliveryError,
                    "content import report identity drift",
                ),
            ):
                delivery_contract.load_release_video_binding(
                    receipt_path,
                    expected_environment="gamma",
                )

        self.assertEqual(binding["workId"], "post-video-a")
        self.assertEqual(binding["assetId"], "asset-video-a")
        self.assertEqual(binding["expectedHash"], EXPECTED_HASH)
        self.assertEqual(
            delivery_contract.build_release_video_url(
                {"mediaVideo": "https://cdn.gamma.quwoquan.com/media/video"},
                binding,
            ),
            "https://cdn.gamma.quwoquan.com/media/video/s/asset/asset-video-a/v1/source.mp4",
        )

    def test_http_probe_hashes_full_and_range_bytes(self) -> None:
        class Response:
            def __init__(
                self,
                *,
                status: int,
                headers: dict[str, str],
                body: bytes,
            ) -> None:
                self.status = status
                self.headers = headers
                self._stream = io.BytesIO(body)

            def __enter__(self) -> "Response":
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def read(self, size: int = -1) -> bytes:
                return self._stream.read(size)

        body = b"abcd"
        expected_hash = "sha256:" + hashlib.sha256(body).hexdigest()
        with mock.patch.object(
            delivery_contract.urllib.request,
            "urlopen",
            side_effect=[
                Response(
                    status=200,
                    headers={
                        "Content-Type": "video/mp4",
                        "Content-Length": "4",
                        "ETag": '"asset-a"',
                        "Cache-Control": "public, max-age=31536000, immutable",
                        "Access-Control-Allow-Origin": "*",
                        "X-QWQ-Media-Cache-Key": "/media/video/s/asset/a/v1/source.mp4",
                    },
                    body=body,
                ),
                Response(
                    status=206,
                    headers={
                        "Content-Type": "video/mp4",
                        "Content-Range": "bytes 0-1/4",
                        "ETag": '"asset-a"',
                        "Cache-Control": "public, max-age=31536000, immutable",
                        "Access-Control-Allow-Origin": "*",
                        "X-QWQ-Media-Cache-Key": "/media/video/s/asset/a/v1/source.mp4",
                    },
                    body=b"ab",
                ),
                Response(
                    status=200,
                    headers={"Cache-Control": "no-store"},
                    body=b"",
                ),
            ],
        ) as urlopen:
            observed = delivery_contract.probe_https_video(
                "https://cdn.gamma.quwoquan.com/media/video/s/asset/a/v1/source.mp4",
                expected_bytes=4,
            )

        delivery_contract.validate_delivery(
            observed,
            expected_mime_type="video/mp4",
            expected_bytes=4,
            expected_hash=expected_hash,
            expected_public_slice_key="media/video/s/asset/a/v1/source.mp4",
        )
        self.assertEqual(observed["observedHash"], expected_hash)
        self.assertEqual(observed["rangeBytes"], 2)
        self.assertEqual(urlopen.call_count, 3)


if __name__ == "__main__":
    unittest.main()
