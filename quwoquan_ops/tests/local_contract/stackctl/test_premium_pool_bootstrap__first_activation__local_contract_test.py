"""精选池首次激活：空池环境凭导入证据完成第一条 entry。

`immutable-candidate` 要求一份已通过的 consumer 档收据，而 consumer 档校验又把
「`premium_stream` 暴露至少一个 release 绑定的 postId」当作通过条件。因此一个
此前没有池条目的环境无法完成首次激活。本套件锁定第三条绑定路径：它只接受
`apply` 已产出的导入报告，只在池确实为空时可用，且不放宽 release 绑定。

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-004
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib import premium_pool_release  # noqa: E402


RELEASE_ID = "release-1"
MANIFEST_DIGEST = "sha256:" + "a" * 64
BASELINE_ID = "sha256:" + "b" * 64
PACKAGE_DIGEST = "sha256:" + "c" * 64
VIDEO_ID = "data_post_" + "d" * 64
ARTICLE_ID = "data_post_" + "e" * 64


def _import_report(
    root: Path,
    *,
    environment: str = "alpha",
    release_id: str = RELEASE_ID,
    manifest_digest: str = MANIFEST_DIGEST,
    import_run_id: str = "apply-20260824T154110Z",
) -> Path:
    """写一份与 `ship apply` 同形的导入报告。"""
    report = (
        root
        / "data-release"
        / release_id
        / import_run_id
        / "import.json"
    )
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        json.dumps(
            {
                "schema": "quwoquan.content_import_report",
                "environment": environment,
                "status": "imported",
                "releaseId": release_id,
                "manifestDigest": manifest_digest,
                "postBindings": [
                    {
                        "postRef": "video/攻略/峨眉山/1",
                        "postId": VIDEO_ID,
                        "contentType": "video",
                        "usageScope": "research",
                    },
                    {
                        "postRef": "article/攻略/峨眉山/1",
                        "postId": ARTICLE_ID,
                        "contentType": "article",
                        "usageScope": "research",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return report


class PremiumPoolBootstrapBindingLocalContractTest(unittest.TestCase):
    def _load(
        self,
        report: Path,
        root: Path,
        *,
        content_id: str = VIDEO_ID,
        pool_is_empty: bool = True,
        candidate_release_id: str = RELEASE_ID,
        environment: str = "alpha",
        target: str = "alpha-local",
    ):
        with (
            mock.patch.object(
                premium_pool_release,
                "active_deployment_candidate",
                return_value={"baselineId": BASELINE_ID},
            ),
            mock.patch.object(
                premium_pool_release,
                "load_candidate_manifest",
                return_value={
                    "baselineId": BASELINE_ID,
                    "packageDigest": PACKAGE_DIGEST,
                    "sourceRevision": "revision-1",
                    "release": {
                        "candidate": {
                            "releaseId": candidate_release_id,
                            "releaseDigest": MANIFEST_DIGEST,
                        }
                    },
                },
            ),
            mock.patch.object(
                premium_pool_release, "env_runs_root", return_value=root
            ),
            mock.patch.object(
                premium_pool_release,
                "_load_release_sample_plan_documents_from_attestation",
                return_value=(
                    {},
                    {
                        "schema": "quwoquan_data.release_uat_sample_plan",
                        "releaseId": candidate_release_id,
                        "samples": [
                            {
                                "sampleId": "canary-video-001",
                                "carrier": "video",
                                "objectId": VIDEO_ID,
                                "objectRef": "objects/posts/video/攻略/峨眉山/1",
                                "objectDigest": "sha256:" + "7" * 64,
                            }
                        ],
                    },
                    "sha256:" + "f" * 64,
                ),
            ),
        ):
            return premium_pool_release.load_premium_pool_bootstrap_binding(
                environment=environment,
                target=target,
                import_report=report,
                content_id=content_id,
                pool_is_empty=pool_is_empty,
            )

    def test_empty_pool_binds_the_release_video_from_import_evidence(self) -> None:
        """首次激活只需 apply 已产出的导入证据。

        spec_ref: environment-topology-and-packaging GWT-004（Alpha 激活绑定 ReleaseUatSamplePlan）
        """
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            binding = self._load(_import_report(root), root)
            self.assertEqual(binding.release_id, RELEASE_ID)
            self.assertEqual(binding.manifest_digest, MANIFEST_DIGEST)
            self.assertEqual(binding.content_id, VIDEO_ID)
            self.assertEqual(binding.import_run_id, "apply-20260824T154110Z")
            self.assertEqual(binding.baseline_id, BASELINE_ID)
            # 引用必须相对环境 runs 根，收据里不出现绝对路径。
            self.assertFalse(Path(binding.import_report_ref).is_absolute())

    def test_a_populated_pool_is_not_a_bootstrap(self) -> None:
        """池非空时这条路径必须关闭，否则它就成了绕过 consumer 校验的后门。

        spec_ref: environment-topology-and-packaging GWT-004
        """
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(
                premium_pool_release.PremiumPoolReleaseError,
                "already has premium pool entries",
            ):
                self._load(_import_report(root), root, pool_is_empty=False)

    def test_content_outside_the_import_report_is_refused(self) -> None:
        """内容必须来自这次导入，不能凭空指定。

        spec_ref: environment-topology-and-packaging GWT-004
        """
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(
                premium_pool_release.PremiumPoolReleaseError,
                "ReleaseUatSamplePlan video sample",
            ):
                self._load(
                    _import_report(root), root, content_id="data_post_" + "f" * 64
                )

    def test_a_non_video_binding_is_refused(self) -> None:
        """精选池只收 ReleaseUatSamplePlan 明确选中的 video 样本。

        spec_ref: environment-topology-and-packaging GWT-004
        """
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(
                premium_pool_release.PremiumPoolReleaseError,
                "ReleaseUatSamplePlan video sample",
            ):
                self._load(_import_report(root), root, content_id=ARTICLE_ID)

    def test_an_import_report_from_another_environment_is_refused(self) -> None:
        """跨环境搬运收据仍然被拒。

        spec_ref: environment-topology-and-packaging GWT-004
        """
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = _import_report(root, environment="beta")
            with self.assertRaisesRegex(
                premium_pool_release.PremiumPoolReleaseError,
                "canonical content import report",
            ):
                self._load(report, root)

    def test_an_import_report_off_the_active_candidate_is_refused(self) -> None:
        """导入证据必须指向当前 active candidate 的 release。

        spec_ref: environment-topology-and-packaging GWT-004
        """
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(
                premium_pool_release.PremiumPoolReleaseError,
                "does not match the active candidate release",
            ):
                self._load(
                    _import_report(root), root, candidate_release_id="release-other"
                )

    def test_a_failed_import_is_not_activation_evidence(self) -> None:
        """未成功的导入不构成激活证据。

        spec_ref: environment-topology-and-packaging GWT-004
        """
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = _import_report(root)
            payload = json.loads(report.read_text(encoding="utf-8"))
            payload["status"] = "failed"
            report.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(
                premium_pool_release.PremiumPoolReleaseError,
                "canonical content import report",
            ):
                self._load(report, root)

    def test_the_receipt_records_import_evidence_not_a_readiness_receipt(self) -> None:
        """收据必须如实记录这是导入证据绑定，且不谎称存在 verify 运行。

        spec_ref: environment-topology-and-packaging GWT-004
        """
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            binding = self._load(_import_report(root), root)
            recorded = premium_pool_release._premium_receipt_binding(binding)
            self.assertIn("releaseImportBinding", recorded)
            evidence = recorded["releaseImportBinding"]
            self.assertEqual(evidence["launchPolicy"], "release_import")
            self.assertEqual(evidence["releaseId"], RELEASE_ID)
            self.assertEqual(evidence["videoWorkId"], VIDEO_ID)
            self.assertNotIn("verifyRunId", evidence)
            self.assertNotIn("readinessReceiptRef", evidence)


class PremiumPoolEmptinessProbeLocalContractTest(unittest.TestCase):
    def test_an_empty_premium_feed_is_read_as_an_empty_pool(self) -> None:
        """空池判定只读内容面，不需要运维凭据。

        spec_ref: environment-topology-and-packaging GWT-004
        """
        with mock.patch.object(
            premium_pool_release, "_request_json", return_value={"items": []}
        ) as requested:
            self.assertTrue(
                premium_pool_release.premium_pool_is_empty(
                    api_base_url="https://api.alpha.quwoquan.com:17000",
                    ssl_cafile="/dev/null",
                )
            )
        url, = requested.call_args.args
        self.assertTrue(url.endswith(premium_pool_release.PREMIUM_FEED_PATH))
        self.assertEqual(requested.call_args.kwargs["token"], "")

    def test_any_existing_entry_makes_the_pool_non_empty(self) -> None:
        """已有条目即视为非空，宁可拒绝也不重复首填。

        spec_ref: environment-topology-and-packaging GWT-004
        """
        with mock.patch.object(
            premium_pool_release,
            "_request_json",
            return_value={"items": [{"id": VIDEO_ID}]},
        ):
            self.assertFalse(
                premium_pool_release.premium_pool_is_empty(
                    api_base_url="https://api.alpha.quwoquan.com:17000",
                    ssl_cafile="/dev/null",
                )
            )


class PremiumPoolBootstrapSurfaceLocalContractTest(unittest.TestCase):
    def test_the_parser_exposes_the_release_import_policy(self) -> None:
        """CLI 必须显式暴露这条路径，不能靠隐式回退。

        spec_ref: environment-topology-and-packaging GWT-004
        """
        import argparse

        from quwoquan_ops.cli.commands import premium_pool as premium_pool_command

        parser = argparse.ArgumentParser()
        premium_pool_command.register_parser(parser.add_subparsers(dest="command"))
        parsed = parser.parse_args(
            [
                "premium-pool",
                "--target",
                "alpha-local",
                "--launch-policy",
                "release-import",
                "--readiness-receipt",
                "import.json",
                "--content-id",
                VIDEO_ID,
            ]
        )
        self.assertEqual(parsed.launch_policy, "release-import")


if __name__ == "__main__":
    unittest.main()
