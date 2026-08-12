"""Strong typing, request DAG, Provider closure and receipt contracts.

spec_ref: specs/feature-tree/runtime/runtime-testinfra/spec.md#sit-002.t1
spec_ref: specs/feature-tree/runtime/runtime-testinfra/spec.md#sit-002.t2
spec_ref: specs/feature-tree/runtime/runtime-testinfra/spec.md#sit-002.t3
spec_ref: specs/feature-tree/runtime/runtime-testinfra/spec.md#sit-002.t4
spec_ref: specs/feature-tree/runtime/runtime-testinfra/test-data-provisioning-and-isolation/spec.md#gwt-001
spec_ref: specs/feature-tree/runtime/runtime-testinfra/test-data-provisioning-and-isolation/spec.md#gwt-002
"""

from __future__ import annotations

import json
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from enum import StrEnum
from pathlib import Path
from threading import Barrier, Event, Lock
from typing import Any

from quwoquan_ops.cli.lib.test_data.api import (
    AssertionStatus,
    BusinessCaseRunner,
    BusinessObjectRef,
    CaseAssertion,
    CaseExecution,
    CaseRef,
    OutputRef,
    TestDataSession,
)
from quwoquan_ops.cli.lib.test_data.capabilities.chat_service import (
    DIRECT_CONVERSATION_WITH_MESSAGES,
    DirectConversationResult,
    DirectConversationWithMessagesParams,
    MessageHandle,
    MessageStatus,
)
from quwoquan_ops.cli.lib.test_data.capabilities.common import (
    AcceptanceActorSet,
    ActorHandle,
    ActorRole,
)
from quwoquan_ops.cli.lib.test_data.capabilities.user_service import (
    AUTHENTICATED_ACTORS,
    AuthenticatedActorsParams,
)
from quwoquan_ops.cli.lib.test_data.model import (
    CandidateBinding,
    CapabilityDefinition,
    CleanupResult,
    PartialProvisioningError,
    ProviderPlan,
    ProvisionedCapability,
    ReadbackResult,
    TestDataContext as DataContext,
)
from quwoquan_ops.cli.lib.test_data.lease import ActorLeaseManager
from quwoquan_ops.cli.lib.test_data.operations import TestDataRuntime as DataRuntime
from quwoquan_ops.cli.lib.test_data.receipts import ReceiptJournal
from quwoquan_ops.cli.lib.test_data.serialization import (
    case_request_document,
    load_case_requests,
    load_request_graph,
    request_graph_document,
)


_IDENTITY_PROVIDER_CAPABILITY = (
    AUTHENTICATED_ACTORS.required_provider_capabilities[0].value
)


class CaseId(StrEnum):
    CHAT_RECALL = "chat-recall"


class ChatRecallBusinessCase(BusinessCaseRunner[DirectConversationResult]):
    result_type = DirectConversationResult

    @classmethod
    def execute(cls, value, context):
        recalled = value.messages[1].status is MessageStatus.RECALLED
        return CaseExecution(
            (
                CaseAssertion(
                    "chat.message.recall.visible",
                    AssertionStatus.PASSED if recalled else AssertionStatus.FAILED,
                ),
            )
        )


class _ActorProvider:
    definition = CapabilityDefinition(
        capability=AUTHENTICATED_ACTORS,
        operations=(
            "user.authentication_challenge.SendOtp",
            "user.account_session.LoginWithPhone",
        ),
    )

    def describe(self):
        return (self.definition,)

    def plan(self, context, request, resolved_params):
        return _plan_for(self.definition, request, resolved_params)

    def provision(self, context, plan):
        params = plan.resolved_params
        actors = tuple(
            ActorHandle(
                role=role,
                account=BusinessObjectRef("UserAccount", f"account-{role.value}"),
                persona=BusinessObjectRef("Persona", f"persona-{role.value}"),
                session_handle=f"session-{role.value}",
            )
            for role in params.roles
        )
        return ProvisionedCapability(
            value=AcceptanceActorSet(actors),
            operation_count=2 * len(actors),
        )

    def readback(self, context, provisioned):
        return ReadbackResult(passed=True)

    def cleanup(self, context, provisioned):
        return CleanupResult(state="released", operation_count=len(provisioned.value.actors))


class _ChatProvider:
    definition = CapabilityDefinition(
        capability=DIRECT_CONVERSATION_WITH_MESSAGES,
        operations=(
            "chat.conversation.CreateConversation",
            "chat.message.SendMessage",
            "chat.message.RecallMessage",
            "chat.message.ListMessages",
        ),
    )

    def describe(self):
        return (self.definition,)

    def plan(self, context, request, resolved_params):
        return _plan_for(self.definition, request, resolved_params)

    def provision(self, context, plan):
        params = plan.resolved_params
        if not isinstance(params.actors, AcceptanceActorSet):
            raise TypeError("actors were not resolved before Chat provision")
        messages = tuple(
            MessageHandle(
                message=BusinessObjectRef("Message", f"message-{index}"),
                status=(
                    MessageStatus.RECALLED
                    if index == params.recalled_message_index
                    else MessageStatus.SENT
                ),
            )
            for index in range(params.message_count)
        )
        return ProvisionedCapability(
            value=DirectConversationResult(
                conversation=BusinessObjectRef("Conversation", "conversation-1"),
                messages=messages,
                delivery_source=messages[-1].message,
            ),
            operation_count=params.message_count + 2,
        )

    def readback(self, context, provisioned):
        return ReadbackResult(passed=True, operation_count=1)

    def cleanup(self, context, provisioned):
        return CleanupResult(state="released", operation_count=1)


class _ConcurrencyProbe:
    def __init__(self) -> None:
        self._lock = Lock()
        self._overlap = Event()
        self.active = 0
        self.peak = 0

    def enter(self) -> None:
        with self._lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
            if self.active >= 2:
                self._overlap.set()
        if not self._overlap.wait(timeout=1):
            raise RuntimeError("global test-data concurrency did not overlap")

    def exit(self) -> None:
        with self._lock:
            self.active -= 1


class _SlowActorProvider(_ActorProvider):
    definition = replace(_ActorProvider.definition, concurrency_limit=4)

    def __init__(self, probe: _ConcurrencyProbe) -> None:
        self._probe = probe

    def provision(self, context, plan):
        self._probe.enter()
        try:
            role = plan.resolved_params.roles[0]
            return ProvisionedCapability(
                value=AcceptanceActorSet(
                    (
                        ActorHandle(
                            role=role,
                            account=BusinessObjectRef(
                                "UserAccount", f"account-{plan.request_id}"
                            ),
                            persona=BusinessObjectRef(
                                "Persona", f"persona-{plan.request_id}"
                            ),
                            session_handle=f"session-{plan.request_id}",
                        ),
                    )
                )
            )
        finally:
            self._probe.exit()


class _ReadbackFailActorProvider(_ActorProvider):
    def __init__(self) -> None:
        self.cleanup_calls = 0

    def readback(self, context, provisioned):
        return ReadbackResult(passed=False)

    def cleanup(self, context, provisioned):
        self.cleanup_calls += 1
        return CleanupResult(state="released")


class _PartialFailActorProvider(_ActorProvider):
    def __init__(self) -> None:
        self.cleanup_calls = 0

    def provision(self, context, plan):
        role = plan.resolved_params.roles[0]
        partial = ProvisionedCapability(
            value=AcceptanceActorSet(
                (
                    ActorHandle(
                        role=role,
                        account=BusinessObjectRef("UserAccount", "partial-account"),
                        persona=BusinessObjectRef("Persona", "partial-persona"),
                        session_handle="partial-session",
                    ),
                )
            ),
            operation_count=1,
        )
        raise PartialProvisioningError(
            "second actor failed",
            provisioned=partial,
        )

    def cleanup(self, context, provisioned):
        self.cleanup_calls += 1
        self.cleaned_account = provisioned.value.actors[0].account.object_id
        return CleanupResult(state="released", operation_count=1)


def _candidate() -> CandidateBinding:
    return CandidateBinding(
        environment="gamma",
        target="gamma-local",
        baseline_id="sha256:" + "1" * 64,
        package_digest="sha256:" + "2" * 64,
        runtime_config_digest="sha256:" + "3" * 64,
        release_id="release-1",
        release_digest="sha256:" + "4" * 64,
        import_run_id="import-1",
        release_post_ids=("post-1", "post-2", "post-3"),
    )


def _plan_for(definition, request, resolved_params):
    return ProviderPlan(
        request_id=request.request_id.value,
        capability_definition_digest=definition.digest,
        operations=definition.operations,
        resolved_params=resolved_params,
    )


class TestDataControlPlaneContractTest(unittest.TestCase):
    def _requests(self):
        actors = AUTHENTICATED_ACTORS.bind(
            AuthenticatedActorsParams((ActorRole.SENDER, ActorRole.RECEIVER))
        )
        conversation = DIRECT_CONVERSATION_WITH_MESSAGES.bind(
            DirectConversationWithMessagesParams(
                actors=actors.output.whole(),
                sender_role=ActorRole.SENDER,
                receiver_role=ActorRole.RECEIVER,
                message_count=3,
                recalled_message_index=1,
            )
        )
        return actors, conversation

    def test_bind_rejects_weak_dict_before_control_plane(self) -> None:
        weak_params = dict(roles=["sender"])
        with self.assertRaisesRegex(TypeError, "exactly AuthenticatedActorsParams"):
            AUTHENTICATED_ACTORS.bind(weak_params)  # type: ignore[arg-type]

    def test_capability_rejects_weak_provider_dependency_before_mutation(
        self,
    ) -> None:
        with self.assertRaisesRegex(TypeError, "ProviderCapabilityKey"):
            replace(
                AUTHENTICATED_ACTORS,
                required_provider_capabilities=("not-typed",),  # type: ignore[arg-type]
            )

    def test_dependency_type_mismatch_fails_at_request_construction(self) -> None:
        actors, _ = self._requests()
        with self.assertRaisesRegex(TypeError, "OutputRef"):
            DIRECT_CONVERSATION_WITH_MESSAGES.bind(
                DirectConversationWithMessagesParams(
                    actors=OutputRef(
                        request_id=actors.request_id,
                        value_type=ActorHandle,
                        request=actors,
                    ),
                    sender_role=ActorRole.SENDER,
                    receiver_role=ActorRole.RECEIVER,
                    message_count=1,
                )
            )

    def test_serialization_round_trip_keeps_typed_dependency_and_digest(self) -> None:
        _, conversation = self._requests()
        document = request_graph_document((conversation,))
        restored = load_request_graph(document)
        self.assertEqual(len(document["requests"]), 2)
        self.assertEqual(restored[0].capability, DIRECT_CONVERSATION_WITH_MESSAGES)
        self.assertIsInstance(restored[0].params, DirectConversationWithMessagesParams)
        self.assertEqual(restored[0].params.message_count, 3)
        tampered = {**document, "roots": ["unknown"]}
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            load_request_graph(tampered)

        case_document = case_request_document(
            (
                CaseRef(
                    case_id=CaseId.CHAT_RECALL,
                    request=conversation,
                    runner_type=ChatRecallBusinessCase,
                ),
            )
        )
        restored_cases = load_case_requests(case_document)
        self.assertEqual(restored_cases[0].case_id, CaseId.CHAT_RECALL)
        self.assertIs(restored_cases[0].runner_type, ChatRecallBusinessCase)
        self.assertEqual(
            restored_cases[0].request.capability,
            DIRECT_CONVERSATION_WITH_MESSAGES,
        )

    def test_one_hundred_request_discovery_document_stays_within_budget(self) -> None:
        roots = tuple(
            AUTHENTICATED_ACTORS.bind(
                AuthenticatedActorsParams((ActorRole.SENDER, ActorRole.RECEIVER))
            )
            for _ in range(100)
        )
        started = time.monotonic()
        document = request_graph_document(roots)
        restored = load_request_graph(document)
        elapsed_ms = round((time.monotonic() - started) * 1000)
        self.assertEqual(len(restored), 100)
        self.assertLessEqual(elapsed_ms, 500)

    def test_receipt_journal_is_append_only_under_parallel_writers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            journal = ReceiptJournal(
                root=Path(temporary),
                case_id="parallel-receipts",
                test_data_instance_id="instance-1",
                candidate_binding_digest=_candidate().digest,
            )
            with ThreadPoolExecutor(max_workers=4) as pool:
                receipts = tuple(
                    pool.map(
                        lambda index: journal.append("operation", {"index": index}),
                        range(20),
                    )
                )
            self.assertEqual(len({receipt.path for receipt in receipts}), 20)
            self.assertEqual(
                [path.name[:6] for path in sorted(Path(temporary).glob("*.json"))],
                [f"{index:06d}" for index in range(1, 21)],
            )
            journal.close()

    def test_receipt_journal_rejects_secret_key_spelling_variants(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            journal = ReceiptJournal(
                root=Path(temporary),
                case_id="secret-redaction",
                test_data_instance_id="instance-1",
                candidate_binding_digest=_candidate().digest,
            )
            for forbidden in (
                "accessToken",
                "access_token",
                "Refresh-Token",
                "otp_code",
                "phone_number",
            ):
                with self.subTest(forbidden=forbidden):
                    with self.assertRaisesRegex(ValueError, "forbidden secret field"):
                        journal.append("operation", {forbidden: "must-not-persist"})
            self.assertEqual(tuple(Path(temporary).glob("*.json")), ())
            journal.close()

    def test_candidate_cache_uses_single_flight_across_parallel_cases(self) -> None:
        runtime = DataRuntime()
        marker = ProvisionedCapability(
            value=BusinessObjectRef("Post", "post-immutable")
        )
        barrier = Barrier(8)
        owner_count = 0
        owner_lock = Lock()

        def lookup(_index: int) -> ProvisionedCapability:
            nonlocal owner_count
            barrier.wait(timeout=1)
            cached, _hit, owner = runtime.candidate_cache_get(
                candidate_binding_digest=_candidate().digest,
                capability_key="immutable-cache-entry",
                params_identity="sha256:" + "5" * 64,
            )
            if owner:
                with owner_lock:
                    owner_count += 1
                runtime.candidate_cache_put(
                    candidate_binding_digest=_candidate().digest,
                    capability_key="immutable-cache-entry",
                    params_identity="sha256:" + "5" * 64,
                    value=marker,
                )
                return marker
            assert cached is not None
            return cached

        with ThreadPoolExecutor(max_workers=8) as pool:
            values = tuple(pool.map(lookup, range(8)))

        self.assertEqual(owner_count, 1)
        self.assertTrue(all(value is marker for value in values))
        self.assertEqual(runtime.cache_misses, 1)
        self.assertEqual(runtime.cache_hits, 7)

    def test_same_instance_is_exclusive_and_retry_advances_fencing_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = ReceiptJournal(
                root=root,
                case_id="exclusive-instance",
                test_data_instance_id="instance-1",
                candidate_binding_digest=_candidate().digest,
            )
            with self.assertRaisesRegex(RuntimeError, "already has an active"):
                ReceiptJournal(
                    root=root,
                    case_id="exclusive-instance",
                    test_data_instance_id="instance-1",
                    candidate_binding_digest=_candidate().digest,
                )
            first_manager = ActorLeaseManager(first)
            first_lease = first_manager.acquire(
                lease_id="lease-1",
                case_run_id="instance-1",
            )
            self.assertEqual(first_lease.generation, 1)
            first_manager.release(generation=first_lease.generation)
            first.close()

            retry = ReceiptJournal(
                root=root,
                case_id="exclusive-instance",
                test_data_instance_id="instance-1",
                candidate_binding_digest=_candidate().digest,
            )
            retry_manager = ActorLeaseManager(retry)
            retry_lease = retry_manager.acquire(
                lease_id="lease-1",
                case_run_id="instance-1",
            )
            self.assertEqual(retry_lease.generation, 2)
            retry_manager.release(generation=retry_lease.generation)
            retry.close()

    def test_actor_lease_uses_governed_ttl_and_complete_state_sequence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            journal = ReceiptJournal(
                root=Path(temporary),
                case_id="lease-lifecycle",
                test_data_instance_id="instance-1",
                candidate_binding_digest=_candidate().digest,
            )
            manager = ActorLeaseManager(journal)
            lease = manager.acquire(
                lease_id="lease-1",
                case_run_id="instance-1",
            )
            self.assertEqual(
                lease.expires_at - lease.acquired_at,
                timedelta(minutes=30),
            )
            self.assertEqual(lease.renewal_interval, timedelta(minutes=10))
            manager.release(generation=lease.generation)
            states = [
                json.loads(path.read_text(encoding="utf-8"))["payload"]["state"]
                for path in sorted(Path(temporary).glob("*-actor-lease.json"))
            ]
            self.assertEqual(
                states,
                ["requested", "acquiring", "active", "releasing", "released"],
            )
            with self.assertRaisesRegex(ValueError, "at most two hours"):
                manager.acquire(
                    lease_id="lease-too-long",
                    case_run_id="instance-2",
                    ttl=timedelta(hours=2, seconds=1),
                )
            journal.close()

    def test_chat_only_request_loads_only_user_and_chat_and_writes_timings(self) -> None:
        _, conversation = self._requests()
        with tempfile.TemporaryDirectory() as temporary:
            runtime = DataRuntime()
            runtime.provider_overrides = {
                "user_service": _ActorProvider(),
                "chat_service": _ChatProvider(),
            }
            context = DataContext(
                candidate=_candidate(),
                base_url="https://gamma.local.quwoquan.invalid",
                output_root=Path(temporary),
                provider_evidence={
                    _IDENTITY_PROVIDER_CAPABILITY: {
                        "status": "passed",
                        "candidateBindingDigest": _candidate().digest,
                    }
                },
                runtime=runtime,
            )
            case = CaseRef(
                case_id=CaseId.CHAT_RECALL,
                request=conversation,
                runner_type=ChatRecallBusinessCase,
            )
            session = TestDataSession.for_case(CaseId.CHAT_RECALL, context=context)
            executed = session.execute(case)
            self.assertEqual(executed.status, AssertionStatus.PASSED)
            self.assertTrue(executed.test_body_receipt.path.is_file())
            summaries = list(Path(temporary).rglob("*-run-summary.json"))
            self.assertEqual(len(summaries), 1)
            summary = json.loads(summaries[0].read_text(encoding="utf-8"))["payload"]
            self.assertEqual(summary["loadedProviders"], ["chat_service", "user_service"])
            self.assertEqual(summary["requiredProviders"], ["chat_service", "user_service"])
            self.assertEqual(summary["operationCount"], 13)
            self.assertEqual(summary["cleanupOperationCount"], 3)
            self.assertEqual(summary["executed"], 1)
            self.assertEqual(summary["assertionCount"], 1)
            self.assertEqual(summary["status"], "passed")
            self.assertTrue(summary["baselineEligible"])
            for field in (
                "requestCollectionMs",
                "providerDiscoveryMs",
                "planningMs",
                "actorProvisionMs",
                "criticalPathMs",
                "dataPreparationMs",
                "testBodyMs",
                "totalMs",
                "receiptWriteMs",
            ):
                self.assertIn(field, summary)

    def test_global_concurrency_budget_is_shared_across_case_scopes(self) -> None:
        probe = _ConcurrencyProbe()
        runtime = DataRuntime()
        runtime.provider_overrides = {
            "user_service": _SlowActorProvider(probe),
        }
        with tempfile.TemporaryDirectory() as temporary:
            context = DataContext(
                candidate=_candidate(),
                base_url="https://gamma.local.quwoquan.invalid",
                output_root=Path(temporary),
                provider_evidence={
                    _IDENTITY_PROVIDER_CAPABILITY: {
                        "status": "passed",
                        "candidateBindingDigest": _candidate().digest,
                    }
                },
                max_concurrency=2,
                runtime=runtime,
            )
            requests = tuple(
                AUTHENTICATED_ACTORS.bind(
                    AuthenticatedActorsParams((ActorRole.PRIMARY,))
                )
                for _ in range(6)
            )

            def run_case(request):
                session = TestDataSession.for_case(CaseId.CHAT_RECALL, context=context)
                with session.provision(request):
                    pass

            with ThreadPoolExecutor(max_workers=6) as pool:
                tuple(pool.map(run_case, requests))

            summaries = tuple(Path(temporary).rglob("*-run-summary.json"))
            self.assertEqual(len(summaries), 6)
            for path in summaries:
                summary = json.loads(path.read_text(encoding="utf-8"))["payload"]
                self.assertEqual(summary["status"], "prepared")
                self.assertEqual(summary["executed"], 0)
                self.assertFalse(summary["baselineEligible"])

        self.assertEqual(probe.peak, 2)
        self.assertEqual(runtime.max_observed_concurrency, 2)

    def test_readback_failure_still_cleans_provisioned_data(self) -> None:
        provider = _ReadbackFailActorProvider()
        runtime = DataRuntime()
        runtime.provider_overrides = {"user_service": provider}
        request = AUTHENTICATED_ACTORS.bind(
            AuthenticatedActorsParams((ActorRole.PRIMARY,))
        )
        with tempfile.TemporaryDirectory() as temporary:
            context = DataContext(
                candidate=_candidate(),
                base_url="https://gamma.local.quwoquan.invalid",
                output_root=Path(temporary),
                provider_evidence={
                    _IDENTITY_PROVIDER_CAPABILITY: {
                        "status": "passed",
                        "candidateBindingDigest": _candidate().digest,
                    }
                },
                runtime=runtime,
            )
            session = TestDataSession.for_case(CaseId.CHAT_RECALL, context=context)
            with self.assertRaisesRegex(RuntimeError, "capability provision failed"):
                with session.provision(request):
                    pass

        self.assertEqual(provider.cleanup_calls, 1)

    def test_partial_provider_failure_still_cleans_created_facts(self) -> None:
        provider = _PartialFailActorProvider()
        runtime = DataRuntime()
        runtime.provider_overrides = {"user_service": provider}
        request = AUTHENTICATED_ACTORS.bind(
            AuthenticatedActorsParams((ActorRole.PRIMARY,))
        )
        with tempfile.TemporaryDirectory() as temporary:
            context = DataContext(
                candidate=_candidate(),
                base_url="https://gamma.local.quwoquan.invalid",
                output_root=Path(temporary),
                provider_evidence={
                    _IDENTITY_PROVIDER_CAPABILITY: {
                        "status": "passed",
                        "candidateBindingDigest": _candidate().digest,
                    }
                },
                runtime=runtime,
            )
            session = TestDataSession.for_case(CaseId.CHAT_RECALL, context=context)
            with self.assertRaisesRegex(RuntimeError, "capability provision failed"):
                with session.provision(request):
                    pass

            summaries = list(Path(temporary).rglob("*-run-summary.json"))
            self.assertEqual(len(summaries), 1)
            summary = json.loads(summaries[0].read_text(encoding="utf-8"))[
                "payload"
            ]
            self.assertEqual(summary["status"], "GATE_BLOCK")
            self.assertEqual(summary["cleanupOperationCount"], 1)

        self.assertEqual(provider.cleanup_calls, 1)
        self.assertEqual(provider.cleaned_account, "partial-account")

    def test_prod_candidate_is_rejected_before_any_session(self) -> None:
        with self.assertRaisesRegex(ValueError, "outside Alpha/Beta/Gamma"):
            replace(_candidate(), environment="prod", target="prod-hosted")


if __name__ == "__main__":
    unittest.main()
