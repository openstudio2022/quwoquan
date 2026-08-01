"""API-only provisioner behavior.

spec_ref: specs/feature-tree/spec.md#uat-009
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli.lib.local_environment_auth import (
    LocalAcceptanceActor,
    LocalAcceptanceSession,
)
from quwoquan_ops.cli.lib.nonprod_data_provisioner import (
    NonprodCandidateIdentity,
    NonprodDataProvisioner,
)
from quwoquan_ops.cli.lib.nonprod_business_data import (
    NONPROD_REFERENCE_CONTENT_INTERACTION,
    NONPROD_REFERENCE_IDENTITY,
)


def _candidate() -> NonprodCandidateIdentity:
    return NonprodCandidateIdentity(
        environment="alpha",
        target="alpha-local",
        baseline_id="sha256:" + "1" * 64,
        source_revision="a" * 40,
        package_digest="sha256:" + "2" * 64,
        runtime_config_digest="sha256:" + "3" * 64,
        release_id="west-lake-canonical-20260729",
        release_digest="sha256:" + "4" * 64,
        import_run_id="import-alpha-1",
        release_post_ids=("post-a", "post-b", "post-c"),
    )


class NonprodDataProvisionerContractTest(unittest.TestCase):
    def test_prod_candidate_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "mismatch"):
            NonprodCandidateIdentity(
                environment="prod",
                target="prod-sim",
                baseline_id="sha256:" + "1" * 64,
                source_revision="a" * 40,
                package_digest="sha256:" + "2" * 64,
                runtime_config_digest="sha256:" + "3" * 64,
                release_id="release",
                release_digest="sha256:" + "4" * 64,
                import_run_id="import",
                release_post_ids=("post-a", "post-b", "post-c"),
            )

    def test_reference_identity_uses_six_real_auth_actors_and_public_commands(self) -> None:
        actors = [
            LocalAcceptanceActor(
                role="primary" if index == 0 else f"member-{index}",
                session=LocalAcceptanceSession(
                    owner_id=f"owner-{index}",
                    persona_id=f"persona-{index}",
                    access_token=f"secret-{index}",
                ),
                challenge_id=f"challenge-{index}",
                account_state="active",
                identity_origin="phone",
            )
            for index in range(6)
        ]
        counter = {"greeting": 0}

        def response(*_args, **kwargs):
            path = kwargs["path"]
            if path == "/user/personas":
                return {"personaId": "persona-secondary"}
            if path == "/user/greeting-request":
                counter["greeting"] += 1
                return {"id": f"greeting-{counter['greeting']}"}
            if path.endswith("/reply"):
                return {
                    "status": "replied",
                    "promotedConversationId": "conversation-promoted",
                }
            return {"status": "ok"}

        with tempfile.TemporaryDirectory() as directory:
            with (
                mock.patch(
                    "quwoquan_ops.cli.lib.nonprod_data_provisioner.env_runs_root",
                    return_value=Path(directory),
                ),
                mock.patch.object(
                    NonprodDataProvisioner,
                    "_open_identity_actors_with_recovery",
                    return_value=actors,
                ),
                mock.patch(
                    "quwoquan_ops.cli.lib.nonprod_data_provisioner.request_local_environment_json",
                    side_effect=response,
                ) as request_json,
            ):
                receipt = NonprodDataProvisioner(
                    base_url="https://api.alpha.quwoquan.local:17000",
                    candidate=_candidate(),
                ).provision_reference_identity()

        self.assertEqual(receipt["status"], "passed")
        self.assertEqual(receipt["readbackResults"]["authenticatedAccounts"], 6)
        self.assertEqual(receipt["readbackResults"]["finalFollowDirections"], 8)
        self.assertEqual(receipt["readbackResults"]["greetingStates"], ["pending", "replied", "ignored"])
        self.assertEqual(request_json.call_count, 17)
        joined = "\n".join(str(call.kwargs) for call in request_json.call_args_list)
        self.assertNotIn("X-Client-User-Id", joined)
        self.assertNotIn("secret-", joined)

    def test_run_bound_failure_persists_recoverable_cleanup_receipt(self) -> None:
        for method_name, dataset_id in (
            ("run_paging_boundary", "nonprod_paging_boundary"),
            ("run_reliability_recovery", "nonprod_reliability_recovery"),
        ):
            with self.subTest(method=method_name), tempfile.TemporaryDirectory() as directory:
                output = Path(directory)
                provisioner = NonprodDataProvisioner(
                    base_url="https://api.alpha.quwoquan.local:17000",
                    candidate=_candidate(),
                    reliability_evidence={
                        name: {
                            "status": "passed",
                            "attemptId": f"attempt-{name}",
                            "baselineId": _candidate().baseline_id,
                            "packageDigest": _candidate().package_digest,
                            "caseResultRef": f"case-{name}.json",
                        }
                        for name in (
                            "expiredSession",
                            "projectionDelay",
                            "cleanupRecovery",
                        )
                    },
                )
                with (
                    mock.patch(
                        "quwoquan_ops.cli.lib.nonprod_data_provisioner.env_runs_root",
                        return_value=output,
                    ),
                    mock.patch.object(
                        NonprodDataProvisioner,
                        "_open_actors",
                        side_effect=RuntimeError("provider unavailable"),
                    ),
                ):
                    with self.assertRaisesRegex(RuntimeError, "provider unavailable"):
                        getattr(provisioner, method_name)()

                receipts = list(output.rglob(f"{dataset_id}.json"))
                self.assertEqual(len(receipts), 1)
                receipt = json.loads(receipts[0].read_text(encoding="utf-8"))
                self.assertEqual(receipt["status"], "GATE_BLOCK")
                self.assertEqual(receipt["retentionClass"], "run_bound")
                self.assertEqual(receipt["cleanupState"], "cleaned")
                self.assertEqual(receipt["failureClass"], "RuntimeError")

    def test_candidate_mutation_persists_object_identity_before_final_receipt(self) -> None:
        actor = LocalAcceptanceActor(
            role="primary",
            session=LocalAcceptanceSession(
                owner_id="owner-primary",
                persona_id="persona-primary",
                access_token="secret-primary",
            ),
            challenge_id="challenge-primary",
            account_state="active",
            identity_origin="phone",
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            provisioner = NonprodDataProvisioner(
                base_url="https://api.alpha.quwoquan.local:17000",
                candidate=_candidate(),
            )
            recipe = NONPROD_REFERENCE_CONTENT_INTERACTION
            epoch = provisioner._epoch(recipe)
            with (
                mock.patch(
                    "quwoquan_ops.cli.lib.nonprod_data_provisioner.env_runs_root",
                    return_value=output,
                ),
                mock.patch(
                    "quwoquan_ops.cli.lib.nonprod_data_provisioner.request_local_environment_json",
                    return_value={"commentId": "comment-created-before-crash"},
                ),
            ):
                executor = provisioner._candidate_executor(
                    recipe,
                    epoch,
                    actor_receipt_refs=[{"datasetId": "identity", "datasetEpoch": "e"}],
                )
                executor.call(
                    "content.comment.CreateComment",
                    actor=actor,
                    step="post-a-comment-00",
                    bindings={"postId": "post-a"},
                    body={"content": "中断前已创建"},
                    object_id_fields=("commentId",),
                )
                receipt = json.loads(
                    provisioner._receipt_path(recipe, epoch).read_text(encoding="utf-8")
                )

        self.assertEqual(receipt["status"], "GATE_BLOCK")
        self.assertEqual(receipt["cleanupState"], "pending")
        self.assertEqual(
            receipt["createdObjectIdsOrHashes"]["operationObjectIds"],
            ["comment-created-before-crash"],
        )
        self.assertEqual(len(receipt["operationReceipts"]), 1)

    def test_account_close_failure_keeps_dependent_receipt_resumable(self) -> None:
        actor = LocalAcceptanceActor(
            role="primary",
            session=LocalAcceptanceSession(
                owner_id="owner-primary",
                persona_id="persona-primary",
                access_token="secret-primary",
            ),
            challenge_id="challenge-primary",
            account_state="active",
            identity_origin="phone",
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            provisioner = NonprodDataProvisioner(
                base_url="https://api.alpha.quwoquan.local:17000",
                candidate=_candidate(),
            )
            identity_epoch = provisioner._epoch(NONPROD_REFERENCE_IDENTITY)
            content_epoch = provisioner._epoch(
                NONPROD_REFERENCE_CONTENT_INTERACTION
            )
            identity = provisioner._base_receipt(
                NONPROD_REFERENCE_IDENTITY, identity_epoch
            )
            identity.update(
                {
                    "status": "GATE_BLOCK",
                    "actorReceiptRefs": [
                        {
                            "role": "primary",
                            "ownerId": "owner-primary",
                            "personaIds": ["persona-primary"],
                            "accountState": "active",
                            "identityOrigin": "phone",
                        }
                    ],
                    "operationReceipts": [],
                    "createdObjectIdsOrHashes": {},
                    "cleanupState": "pending",
                }
            )
            content = provisioner._base_receipt(
                NONPROD_REFERENCE_CONTENT_INTERACTION, content_epoch
            )
            content.update(
                {
                    "status": "GATE_BLOCK",
                    "actorReceiptRefs": [],
                    "operationReceipts": [],
                    "createdObjectIdsOrHashes": {},
                    "cleanupState": "pending",
                }
            )

            def response(*_args, **kwargs):
                if kwargs["path"] == "/owner/account/close":
                    raise RuntimeError("account close unavailable")
                return {"status": "ok"}

            with (
                mock.patch(
                    "quwoquan_ops.cli.lib.nonprod_data_provisioner.env_runs_root",
                    return_value=output,
                ),
                mock.patch(
                    "quwoquan_ops.cli.lib.nonprod_data_provisioner.open_local_phone_acceptance_session",
                    return_value=actor,
                ),
                mock.patch(
                    "quwoquan_ops.cli.lib.nonprod_data_provisioner.request_local_environment_json",
                    side_effect=response,
                ),
            ):
                provisioner._write_receipt(
                    NONPROD_REFERENCE_IDENTITY, identity_epoch, identity
                )
                provisioner._write_receipt(
                    NONPROD_REFERENCE_CONTENT_INTERACTION,
                    content_epoch,
                    content,
                )
                with self.assertRaisesRegex(RuntimeError, "account cleanup failed"):
                    provisioner.cleanup_candidate_bound_data()
                persisted = json.loads(
                    provisioner._receipt_path(
                        NONPROD_REFERENCE_CONTENT_INTERACTION,
                        content_epoch,
                    ).read_text(encoding="utf-8")
                )

        self.assertEqual(persisted["cleanupState"], "pending")
        self.assertTrue(
            persisted["cleanupProgress"]["domainCleanupComplete"]
        )
        self.assertFalse(
            persisted["cleanupProgress"]["accountClosureComplete"]
        )


if __name__ == "__main__":
    unittest.main()
