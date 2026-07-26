from __future__ import annotations

import unittest

from content.source.contracts import (
    AcquisitionMode,
    MatchVerdict,
    MediaProvenance,
    RightsAuditStatus,
    SourceCandidate,
)


class SourceContractsTest(unittest.TestCase):
    def test_homepage_candidate__accepted_match__functional(self) -> None:
        candidate = SourceCandidate.from_mapping(
            {
                "source_id": "source-a",
                "researchLane": "homepage",
                "url": "https://example.test/entity-a",
                "sourceTitle": "Test Entity A",
                "matchConfidence": 0.95,
                "candidateGate": {"passed": True, "issues": []},
            }
        )

        self.assertEqual(AcquisitionMode.ENTITY_DIRECTORY_LOOKUP, candidate.acquisition_mode)
        self.assertEqual(MatchVerdict.ACCEPTED, candidate.match_verdict)
        candidate.require_accepted()

    def test_image_candidate__rejected_match__reliability(self) -> None:
        candidate = SourceCandidate.from_mapping(
            {
                "source_id": "source-b",
                "researchLane": "image",
                "url": "https://example.test/entity-b.jpg",
                "matchConfidence": 0.1,
                "candidateGate": {"passed": False, "issues": ["entity mismatch"]},
            }
        )

        self.assertEqual(MatchVerdict.REJECTED, candidate.match_verdict)
        with self.assertRaises(ValueError):
            candidate.require_accepted()

    def test_media_provenance__audit_issue__cannot_remain_verified(self) -> None:
        provenance = MediaProvenance.from_mapping(
            {
                "url": "https://example.test/entity-c.jpg",
                "rightsAuditStatus": "verified",
                "modelReleaseStatus": "not_required",
            },
            vertical="travel",
        )

        self.assertEqual(RightsAuditStatus.UNVERIFIED, provenance.rights_audit_status)
        self.assertTrue(provenance.rights_audit_issues)


if __name__ == "__main__":
    unittest.main()
