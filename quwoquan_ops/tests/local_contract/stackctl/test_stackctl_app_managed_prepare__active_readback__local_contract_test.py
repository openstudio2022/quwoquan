"""managed preparation 从公开 feed 精确绑定无类别 readiness。

spec_ref: specs/feature-tree/runtime/runtime-config/environment-ops-cli-and-skill/spec.md#gwt-001
spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-002
"""
from __future__ import annotations

import unittest
from typing import Any
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib.environment_topology import EnvironmentTargetBase
from quwoquan_ops.cli.lib.managed_preparation_support import MANAGED_CONTENT_BINDING_UNAVAILABLE

_DIGEST = "sha256:" + "a" * 64
_PUBLIC_HTTP = (
    "quwoquan_ops.cli.lib.local_environment_auth.http_transport."
    "request_local_environment_public_json"
)


def _readback() -> dict[str, str]:
    return {"releaseId": "alpha-slice-003", "manifestDigest": _DIGEST}


def _readiness() -> dict[str, Any]:
    return {
        **_readback(),
        "verifyRunId": "verify-1",
        "passed": True,
        "authorizationRequiredAssetIds": ["media-1"],
        "containsUnverifiedAssets": True,
    }


class ManagedActiveReadbackContractTest(unittest.TestCase):
    def _call_readback(self, payload: object) -> tuple[dict[str, str], mock.Mock]:
        request = mock.Mock(return_value=payload)
        with (
            mock.patch.object(stackctl, "load_environment_topology", return_value={}),
            mock.patch(
                "quwoquan_ops.cli.lib.environment_topology.resolve_environment_target_base",
                return_value=EnvironmentTargetBase(
                    environment="alpha", target="alpha-local",
                    api_base="https://api.alpha.quwoquan.local",
                ),
            ),
            mock.patch(_PUBLIC_HTTP, request),
        ):
            result = stackctl._managed_active_release_readback(
                environment="alpha", startup_attempt_id="attempt-1"
            )
        return result, request

    def test_public_feed_projects_tuple_without_privileged_identity(self) -> None:
        projection, request = self._call_readback({
            **_readback(), "items": [], "outcome": "empty",
        })
        self.assertEqual(projection, _readback())
        request.assert_called_once_with(
            "https://api.alpha.quwoquan.local",
            path="/content/feed?identity=work&limit=1",
            method="GET",
            headers={
                "X-Client-Page-Id": "content.feed.list",
                "X-Client-Session-Id": "attempt-1",
            },
        )
        # 单页只承担 active tuple；空页不构造完整内容集合或跳过严格预检。
        self.assertNotIn("postIds", projection)

    def test_invalid_or_absent_active_tuple_is_rejected(self) -> None:
        for payload in (
            None, [], {},
            {**_readback(), "releaseId": ""},
            {**_readback(), "releaseId": " alpha-slice-003 "},
            {**_readback(), "releaseId": "alpha/release"},
            {**_readback(), "releaseId": 42},
            {**_readback(), "manifestDigest": "sha256:INVALID"},
            {**_readback(), "manifestDigest": 42},
        ):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self._call_readback(payload)

    def _bind(self, readiness: dict[str, Any], created: dict[str, Any]) -> tuple[dict, mock.Mock]:
        create = mock.Mock(return_value=created)
        with (
            mock.patch.object(stackctl, "_managed_active_release_readback", return_value=_readback()),
            mock.patch.object(
                stackctl, "_managed_readiness_candidates",
                return_value=[{"verifyRunId": "verify-1", "readiness": readiness}],
            ),
            mock.patch.object(stackctl, "create_test_live_content_binding", create),
        ):
            binding = stackctl._managed_content_binding(
                environment="alpha", target="alpha-local", startup_attempt_id="attempt-1",
            )
        return binding, create

    def test_unique_readiness_binds_without_removing_rights_records(self) -> None:
        readiness = _readiness()
        created = {**_readback(), "verifyRunId": "verify-1"}
        binding, create = self._bind(readiness, created)
        self.assertEqual(binding, created)
        self.assertEqual(readiness["authorizationRequiredAssetIds"], ["media-1"])
        self.assertIs(readiness["containsUnverifiedAssets"], True)
        create.assert_called_once_with(
            environment="alpha", target="alpha-local", startup_attempt_id="attempt-1",
            release_id="alpha-slice-003", verify_run_id="verify-1", manifest_digest=_DIGEST,
        )

    def test_each_readiness_identity_drift_blocks_before_binding(self) -> None:
        for field, value in (
            ("releaseId", "other-release"),
            ("manifestDigest", "sha256:" + "b" * 64),
            ("verifyRunId", "other-verify"),
            ("passed", False),
        ):
            with self.subTest(field=field, value=value):
                with self.assertRaises(stackctl.ManagedPreparationBlocked) as raised:
                    self._bind({**_readiness(), field: value}, {})
                self.assertEqual(raised.exception.blocker, MANAGED_CONTENT_BINDING_UNAVAILABLE)
                self.assertTrue(any(field in item for item in raised.exception.details))

    def test_readiness_and_binding_reject_category_fields_even_when_empty(self) -> None:
        for field in ("readinessPhase", "releaseClass", "productLifecycleState"):
            for value in ("research", "production", "commercial", "consumer", "import", "default", "", None):
                with self.subTest(field=field, value=value):
                    with self.assertRaises(stackctl.ManagedPreparationBlocked):
                        self._bind({**_readiness(), field: value}, {})
                    with self.assertRaises(stackctl.ManagedPreparationBlocked):
                        self._bind(_readiness(), {field: value})


if __name__ == "__main__":
    unittest.main()
