# spec_ref: specs/feature-tree/platform-ops-governance/config-and-reliability-governance/reliability-policy-control/spec.md#gwt-002
from __future__ import annotations

import copy
import datetime as dt
import json
import os
import tempfile
import unittest
from pathlib import Path

from quwoquan_ops.cli.prod import hosted_release_ledger
from quwoquan_ops.cli.prod import rollout_stage_promotion_evidence as evidence


DIGEST_A = "sha256:" + ("a" * 64)
DIGEST_B = "sha256:" + ("b" * 64)


class RolloutStagePromotionEvidenceTest(unittest.TestCase):
    def _policy(self) -> dict[str, object]:
        return {
            "platforms": {
                "mode": "include",
                "values": ["android", "ios", "web"],
            },
            "appVersions": {"mode": "supported", "values": []},
            "regions": {"mode": "all", "values": []},
            "carriers": {"mode": "all", "values": []},
        }

    def _observation(
        self,
        stage: str,
        *,
        policy: dict[str, object] | None = None,
    ) -> dict[str, object]:
        thresholds = evidence.STAGE_THRESHOLDS[stage]
        duration = thresholds["durationSeconds"]
        minimum_installations = thresholds["perPlatformInstallations"]
        total_installations = thresholds["uniqueInstallations"]
        counts = {
            "android": total_installations - (minimum_installations * 2),
            "ios": minimum_installations,
            "web": minimum_installations,
        }
        selected_policy = policy or self._policy()
        selected_platforms = set(selected_policy["platforms"]["values"])  # type: ignore[index]
        counts = {
            platform: count
            for platform, count in counts.items()
            if platform in selected_platforms
        }
        if stage not in {"canary", "100"} and selected_platforms == {"android"}:
            counts = {"android": total_installations}
        requests = thresholds["candidateRequests"]
        started = dt.datetime(2026, 8, 1, tzinfo=dt.timezone.utc)
        ended = started + dt.timedelta(seconds=duration)
        platforms = {
            platform: {
                "candidateRequestCount": requests if index == 0 else 0,
                "uniqueCandidateInstallations": count,
            }
            for index, (platform, count) in enumerate(sorted(counts.items()))
        }

        def audience(dimension: str) -> dict[str, object]:
            selector = selected_policy[dimension]
            mode = selector["mode"]  # type: ignore[index]
            values = selector["values"]  # type: ignore[index]
            if mode == "include":
                observations = [
                    {
                        "value": value,
                        "top": False,
                        "candidateRequestCount": 100,
                        "uniqueCandidateInstallations": 10,
                    }
                    for value in values
                ]
            else:
                observations = [
                    {
                        "value": "top-segment",
                        "top": True,
                        "candidateRequestCount": requests,
                        "uniqueCandidateInstallations": sum(counts.values()),
                    },
                    {
                        "value": "unknown",
                        "top": False,
                        "candidateRequestCount": 0,
                        "uniqueCandidateInstallations": 0,
                    },
                ]
            return {"mode": mode, "observations": observations}

        return {
            "schema": evidence.SCHEMA,
            "authority": evidence.AUTHORITY,
            "releaseCompositionId": DIGEST_A,
            "artifactDigest": DIGEST_B,
            "campaignId": "release-test-campaign",
            "routingPolicyDigest": DIGEST_B,
            "stage": stage,
            "observedFrom": started.isoformat().replace("+00:00", "Z"),
            "observedUntil": ended.isoformat().replace("+00:00", "Z"),
            "candidateRequestCount": requests,
            "uniqueCandidateInstallations": sum(counts.values()),
            "platforms": platforms,
            "audiences": {
                "regions": audience("regions"),
                "carriers": audience("carriers"),
            },
            "supportedAppCoverage": {
                "mode": "supported",
                "complete": stage == "100",
            },
            "source": {
                "authority": evidence.SOURCE_AUTHORITY,
                "queryDigest": DIGEST_A,
                "receiptDigest": DIGEST_B,
                "generatedAt": ended.isoformat().replace("+00:00", "Z"),
            },
        }

    def _validate(
        self,
        value: dict[str, object],
        *,
        stage: str,
        policy: dict[str, object] | None = None,
    ) -> dict[str, object]:
        return evidence.validate_observation(
            value,
            candidate_id=DIGEST_A,
            artifact_digest=DIGEST_B,
            campaign_id="release-test-campaign",
            routing_policy_digest=DIGEST_B,
            stage=stage,
            stage_policy=policy or self._policy(),
            actual_synthetic_requests=120 if stage == "canary" else 0,
        )

    def test_each_stage_satisfies_canonical_threshold_and_receipt_validation(self) -> None:
        for stage in evidence.STAGES:
            with self.subTest(stage=stage):
                projection = self._validate(self._observation(stage), stage=stage)
                self.assertEqual(projection["stage"], stage)
                evidence.validate_receipt_evidence(
                    projection,
                    candidate_id=DIGEST_A,
                    artifact_digest=DIGEST_B,
                    stage=stage,
                )
                hosted_projection = copy.deepcopy(projection)
                hosted_projection["candidateMaterialId"] = hosted_projection.pop(
                    "artifactDigest"
                )
                unsigned = dict(hosted_projection)
                unsigned.pop("evidenceDigest")
                hosted_projection["evidenceDigest"] = evidence.canonical_digest(
                    unsigned
                )
                hosted_release_ledger.validate_promotion_evidence(
                    hosted_projection,
                    candidate_id=DIGEST_A,
                    candidate_material_id=DIGEST_B,
                    stage=stage,
                )

    def test_below_stage_duration_requests_or_platform_sample_is_blocked(self) -> None:
        observation = self._observation("20")
        observation["candidateRequestCount"] = 4999
        observation["platforms"]["android"]["candidateRequestCount"] = 4999  # type: ignore[index]
        with self.assertRaisesRegex(evidence.PromotionEvidenceError, "requests"):
            self._validate(observation, stage="20")

        observation = self._observation("50")
        observation["platforms"]["ios"]["uniqueCandidateInstallations"] = 99  # type: ignore[index]
        observation["platforms"]["android"]["uniqueCandidateInstallations"] += 1  # type: ignore[index,operator]
        with self.assertRaisesRegex(evidence.PromotionEvidenceError, "platform ios"):
            self._validate(observation, stage="50")

    def test_directed_audience_requires_samples_but_all_only_top_and_unknown(self) -> None:
        policy = self._policy()
        policy["platforms"] = {"mode": "include", "values": ["android"]}
        policy["regions"] = {"mode": "include", "values": ["guangdong"]}
        observation = self._observation("5", policy=policy)
        self._validate(observation, stage="5", policy=policy)
        observation["audiences"]["regions"]["observations"][0][  # type: ignore[index]
            "candidateRequestCount"
        ] = 99
        with self.assertRaisesRegex(evidence.PromotionEvidenceError, "10 installations"):
            self._validate(observation, stage="5", policy=policy)

    def test_digest_or_candidate_binding_tamper_is_blocked(self) -> None:
        projection = self._validate(self._observation("canary"), stage="canary")
        tampered = copy.deepcopy(projection)
        tampered["candidateRequestCount"] = 1
        with self.assertRaisesRegex(ValueError, "digest"):
            evidence.validate_receipt_evidence(
                tampered,
                candidate_id=DIGEST_A,
                artifact_digest=DIGEST_B,
                stage="canary",
            )

    def test_protected_materialization_rejects_symlink_and_writable_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            root.chmod(0o700)
            observation_path = root / "5.json"
            observation_path.write_text(
                json.dumps(self._observation("5")), encoding="utf-8"
            )
            observation_path.chmod(0o600)
            loaded = evidence.load_protected_observation(
                observation_path, trusted_root=root
            )
            self.assertEqual(loaded["stage"], "5")

            link_path = root / "linked.json"
            link_path.symlink_to(observation_path)
            with self.assertRaisesRegex(evidence.PromotionEvidenceError, "unsafe"):
                evidence.load_protected_observation(link_path, trusted_root=root)

            root.chmod(0o770)
            with self.assertRaisesRegex(evidence.PromotionEvidenceError, "writable"):
                evidence.load_protected_observation(
                    observation_path, trusted_root=root
                )
            root.chmod(0o700)


if __name__ == "__main__":
    unittest.main()
