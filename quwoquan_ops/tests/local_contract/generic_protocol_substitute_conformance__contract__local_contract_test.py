# spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-001
"""Contract tests for the package-bound generic Provider harness."""

from __future__ import annotations

import io
import json
import os
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci.provider_conformance import (
    generic_protocol_substitute_conformance as subject,
)
from quwoquan_ops.cli.lib.provider_conformance import PUBLIC_ASSERTION_IDS

CAPABILITY_ASSERTION = "provider.push_delivery"
ASSERTIONS = tuple(sorted(PUBLIC_ASSERTION_IDS)) + (CAPABILITY_ASSERTION,)


class _FakeClient:
    def __init__(self, context: subject.RuntimeContext):
        self.context = context
        self.active: tuple[str, str] | None = None
        self.transient_calls = 0
        self.acquired: list[tuple[str, str]] = []
        self._cleanup_receipts: list[str] = []
        self.call_ordinal = 0
        self.effect_counts: dict[str, int] = {}
        self.idempotency: dict[str, tuple[int, bytes]] = {}
        self.callback_channel: dict[str, object] | None = None

    @property
    def cleanup_receipts(self) -> tuple[str, ...]:
        return tuple(self._cleanup_receipts)

    def health(self):
        return {"status": "ready"}

    def acquire(self, *, operation, scenario, parameters, max_matches):
        del parameters, max_matches
        lease_id = f"fault-{len(self.acquired) + 1:032x}"
        self.active = (lease_id, scenario)
        self.transient_calls = 0
        self.acquired.append((operation, scenario))
        return {"leaseId": lease_id}

    def invoke_raw(
        self,
        operation,
        *,
        canary,
        idempotency_key="",
        callback_channel="",
        extra_query="",
    ):
        del canary
        self.call_ordinal += 1
        lease_id = self.active[0] if self.active else ""
        scenario = self.active[1] if self.active else "success"
        status, outcome = {
            "success": (202, "success"),
            "validation": (400, "validation_rejected"),
            "auth": (401, "auth_rejected"),
            "delay_timeout": (504, "timeout"),
            "throttle": (429, "throttled"),
        }.get(scenario, (503, "transient_unavailable"))
        if scenario == "transient_then_success":
            self.transient_calls += 1
            if self.transient_calls == 2:
                status, outcome = 202, "success"
        idempotency_state = "none"
        effect_ordinal = self.call_ordinal
        body = (
            json.dumps({"providerRequestId": "nonprod-request"}).encode()
            if status == 202
            else b"fault"
        )
        if idempotency_key:
            previous = self.idempotency.get(idempotency_key)
            if extra_query:
                status, outcome, idempotency_state = 409, "idempotency_conflict", "conflict"
                effect_ordinal = previous[0]
                body = b"conflict"
            elif previous is not None:
                effect_ordinal, body = previous
                status, outcome, idempotency_state = 202, "idempotent_replay", "replay"
            else:
                idempotency_state = "new"
                self.idempotency[idempotency_key] = (effect_ordinal, body)
                self.effect_counts[operation] = self.effect_counts.get(operation, 0) + 1
        else:
            self.effect_counts[operation] = self.effect_counts.get(operation, 0) + 1
        evidence = subject.InvocationEvidence(
            operation=operation,
            outcome=outcome,
            status=status,
            request_digest=subject._sha256_text(f"request:{operation}:{scenario}:{self.transient_calls}"),
            trace_digest=subject._sha256_text(f"trace:{operation}:{scenario}:{self.transient_calls}"),
            lease_id=lease_id,
            receipt_ref=f"receipt:provider-protocol-invocation:{len(self.acquired):024x}",
            call_ordinal=self.call_ordinal,
            effect_ordinal=effect_ordinal,
            idempotency_key_digest=(
                subject._sha256_text("idempotency\n" + idempotency_key)
                if idempotency_key
                else ""
            ),
            idempotency_state=idempotency_state,
            network_host_digest=subject._sha256_text("dns\nlocalhost"),
            tls_server_name_digest=subject._sha256_text("dns\nlocalhost"),
            tls_version="TLSv1.3",
        )
        if callback_channel:
            assert self.callback_channel is not None
            events = self.callback_channel["events"]
            events.append(
                {
                    "sequence": len(events) + 1,
                    "callOrdinal": self.call_ordinal,
                    "effectOrdinal": effect_ordinal,
                    "requestDigest": evidence.request_digest,
                    "traceDigest": evidence.trace_digest,
                }
            )
        response = subject.HTTPResult(
            status=status,
            headers={},
            body=body,
        )
        return evidence, response

    def acquire_callback_channel(self, *, operation, max_callbacks):
        del max_callbacks
        self.callback_channel = {
            "channelId": "callback-" + "1" * 32,
            "operation": operation,
            "events": [],
        }
        return self.callback_channel

    def read_callback_channel(self, channel_id):
        assert self.callback_channel is not None
        assert self.callback_channel["channelId"] == channel_id
        receipt = "receipt:provider-callback-cleanup:" + "2" * 24
        if receipt not in self._cleanup_receipts:
            self._cleanup_receipts.append(receipt)
        return {
            **self.callback_channel,
            "state": "exhausted",
            "cleanupReceipt": {"status": "restored", "receiptRef": receipt},
        }

    def read_lease(self, lease_id):
        self.active = None
        receipt = f"receipt:provider-fault-cleanup:{lease_id[-24:]}"
        self._cleanup_receipts.append(receipt)
        return {
            "leaseId": lease_id,
            "state": "exhausted",
            "cleanupReceipt": {"status": "restored", "receiptRef": receipt},
        }

    def readback(self):
        scope = f"{self.context.capability_id}/{self.context.operations[0]}"
        return {
            "faultLeases": [],
            "invocations": [],
            "effects": {scope: self.effect_counts.get(self.context.operations[0], 0)},
        }

    def release_all(self):
        self.active = None


class _MissingCleanupClient(_FakeClient):
    @property
    def cleanup_receipts(self) -> tuple[str, ...]:
        return ()


def _context(*, capability: str = "integration.push.delivery", operations=("deliver",)):
    return subject.RuntimeContext(
        environment="alpha",
        target="alpha-local",
        baseline_id="sha256:" + "1" * 64,
        attempt_id="attempt-real-001",
        runtime_config_digest="sha256:" + "2" * 64,
        runtime_composition_digest="sha256:" + "3" * 64,
        capability_id=capability,
        adapter_id="ext.push.protocol_substitute",
        typed_port="PushDeliveryPort",
        operations=tuple(operations),
        endpoint_values={"endpoint": "https://provider-protocol-substitute:18089/push/send"},
        host_origin="https://localhost:17360",
        ca_path=Path("/protected/ca.crt"),
        operator_token="protected-operator-token-that-is-never-rendered",
    )


class GenericProtocolSubstituteConformanceContractTest(unittest.TestCase):
    def test_owner_contract_remains_the_operation_and_endpoint_role_source(self):
        dependency = subject._owner_dependency(
            contract_ref=(
                "quwoquan_service/services/integration-service/contracts/"
                "external_integration/location/operations.yaml"
            ),
            capability_id="integration.location.lookup",
            adapter_id="ext.map.protocol_fixture",
            typed_port="LocationLookupPort",
        )
        self.assertEqual(dependency["operations"], ["nearby"])
        self.assertEqual(
            dependency["endpointEnvs"],
            {"base": "INTEGRATION_LOCATION_FIXTURE_BASE_URL"},
        )

    def test_supported_scenes_execute_all_public_assertions_and_emit_markers(self):
        with mock.patch.dict(
            os.environ,
            {"QWQ_PROVIDER_CONFORMANCE_ASSERTION_IDS": json.dumps(ASSERTIONS)},
            clear=False,
        ):
            run = subject.execute_supported_scenes(
                _context(),
                client_factory=_FakeClient,
            )
        self.assertEqual(run.blocked_assertion_ids, ())
        self.assertEqual(
            set(run.supported_assertion_ids),
            set(ASSERTIONS) - set(run.blocked_assertion_ids),
        )
        output = io.StringIO()
        with redirect_stdout(output):
            subject.emit_markers(run, expected_assertions=ASSERTIONS)
        self.assertEqual(
            output.getvalue().count("QWQ_PROVIDER_CONFORMANCE_ASSERTION:"),
            len(ASSERTIONS),
        )
        self.assertEqual(
            output.getvalue().count("QWQ_PROVIDER_CONFORMANCE_CLEANUP:"),
            1,
        )

    def test_supported_scenes_reject_incomplete_native_cleanup_receipts(self):
        with mock.patch.dict(
            os.environ,
            {"QWQ_PROVIDER_CONFORMANCE_ASSERTION_IDS": json.dumps(ASSERTIONS)},
            clear=False,
        ), self.assertRaisesRegex(
            subject.ConformanceBlocked,
            "cleanup receipts do not cover every fault lease",
        ):
            subject.execute_supported_scenes(
                _context(),
                client_factory=_MissingCleanupClient,
            )

    def test_social_authorize_and_resolve_identity_have_distinct_protocol_requests(self):
        context = _context(
            capability="identity.social.login",
            operations=("authorize", "resolveIdentity"),
        )
        authorize = subject._probe_request(context, "authorize", canary="safe-canary")
        resolve = subject._probe_request(context, "resolveIdentity", canary="safe-canary")
        self.assertEqual(authorize[0], "POST")
        self.assertEqual(authorize[2], {"action": "authorize", "provider": "alipay"})
        self.assertEqual(resolve[0], "POST")
        self.assertEqual(resolve[2]["action"], "resolveIdentity")
        self.assertEqual(resolve[2]["code"], "safe-canary")

    def test_offline_relays_exact_go_native_markers_without_secret_argv(self):
        observed = {}

        marker_lines = [
            subject._ASSERTION_MARKER
            + json.dumps({"assertionId": assertion_id})
            for assertion_id in ASSERTIONS
        ]
        marker_lines.append(
            subject._CLEANUP_MARKER
            + json.dumps({"status": "restored", "receiptRef": "receipt:native:1"})
        )

        def run(command, **kwargs):
            observed["command"] = command
            observed["kwargs"] = kwargs
            return SimpleNamespace(
                returncode=0,
                stdout=("\n".join(marker_lines) + "\n").encode(),
                stderr=b"",
            )

        environment = {
            "QWQ_PROVIDER_CONFORMANCE_ENVIRONMENT": "alpha",
            "QWQ_PROVIDER_CONFORMANCE_CAPABILITY_ID": "integration.push.delivery",
            "QWQ_PROVIDER_CONFORMANCE_ADAPTER_ID": "ext.push.protocol_substitute",
            "QWQ_PROVIDER_CONFORMANCE_TYPED_PORT": "PushDeliveryPort",
            "QWQ_PROVIDER_CONFORMANCE_CONTRACT_REF": (
                "quwoquan_service/services/integration-service/contracts/"
                "external_integration/external_interaction/operations.yaml"
            ),
            "QWQ_PROVIDER_CONFORMANCE_ASSERTION_IDS": json.dumps(ASSERTIONS),
        }
        output = io.StringIO()
        with mock.patch.dict(
            os.environ,
            environment,
            clear=False,
        ), redirect_stdout(output):
            subject.execute_offline_local_contract(process_runner=run)
        self.assertEqual(
            observed["command"],
            (
                "go",
                "-C",
                "quwoquan_ops/external/provider-protocol-substitute",
                "run",
                "./cmd/provider-protocol-conformance",
            ),
        )
        self.assertEqual(output.getvalue(), "\n".join(marker_lines) + "\n")
        command_text = " ".join(observed["command"])
        self.assertNotIn("token", command_text.lower())
        self.assertNotIn("endpoint", command_text.lower())
        self.assertNotIn(
            "PROVIDER_SUBSTITUTE_OPERATOR_TOKEN",
            observed["kwargs"]["env"],
        )

    def test_offline_exit_zero_without_native_markers_remains_blocked(self):
        with self.assertRaisesRegex(
            subject.ConformanceBlocked,
            "do not exactly cover",
        ):
            subject._validated_native_marker_lines(
                b"go suite exited successfully without receipts\n",
                expected_assertions=ASSERTIONS,
            )

    def test_blocked_diagnostic_contains_only_identity_digests_and_receipts(self):
        run = subject.SupportedRun(
            assertions={},
            cleanup_receipt="receipt:provider-protocol-cleanup:1234567890abcdef12345678",
            supported_assertion_ids=("provider.success",),
            blocked_assertion_ids=("provider.network_dns",),
            readback_digest="sha256:" + "4" * 64,
        )
        encoded = json.dumps(subject.diagnostic_payload(_context(), run), sort_keys=True)
        self.assertIn('"status": "GATE_BLOCK"', encoded)
        self.assertNotIn("protected-operator-token", encoded)
        self.assertNotIn("provider-protocol-substitute:18089", encoded)
        self.assertNotIn("ca.crt", encoded)

    def test_exact_generic_wrappers_use_one_fixed_runner_without_secret_argv(self):
        runner = (
            "quwoquan_ops/ci/provider_conformance/"
            "run_generic_protocol_substitute_conformance.py"
        )
        files = [
            path
            for root in (
                ROOT / "quwoquan_ops/tests/local_contract/service_ops",
                ROOT / "quwoquan_ops/tests/acceptance/api_integration/service_ops",
            )
            for path in root.rglob("*_provider_conformance.py")
            if "protocol_fixture" in path.name or "protocol_substitute" in path.name
        ]
        generic = [path for path in files if runner in path.read_text(encoding="utf-8")]
        self.assertEqual(len(generic), 18)
        for path in generic:
            raw = path.read_text(encoding="utf-8")
            self.assertEqual(raw.count(runner), 1, path)
            self.assertNotIn("PROVIDER_SUBSTITUTE_OPERATOR_TOKEN", raw, path)
            self.assertNotIn("--endpoint", raw, path)
            self.assertNotIn("--token", raw, path)


if __name__ == "__main__":
    unittest.main()
