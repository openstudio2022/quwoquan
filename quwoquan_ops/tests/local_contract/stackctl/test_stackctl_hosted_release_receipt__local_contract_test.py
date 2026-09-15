# spec_ref: specs/feature-tree/platform-ops-governance/config-and-reliability-governance/reliability-policy-control/spec.md#gwt-002
from __future__ import annotations

import copy
import tempfile
import unittest
import json
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.prod import hosted_release_ledger


def _execution_install(root: Path, hosts: int = 1):
    """隔离安装fixture；不初始化真实host，不签hosted资格。"""
    import hashlib
    from quwoquan_ops.cli.prod.hosted_release_ledger_lib.execution import ExecutionSlot
    root.mkdir(parents=True)
    (root / ".ledger.lock").touch()
    execution = root / "execution"; execution.mkdir()
    (execution / "history").mkdir()
    (execution / "slot.json").write_text(json.dumps({"status": "closed", "generation": 0, "revision": 0}))
    placements = []
    data = b'{"environment":"prod","fixture":"not-hosted"}'
    for host in range(hosts):
        for plane in ("edge", "service"):
            for instance in ("gray", "prod"):
                identity = f"host-{host}-{plane}-{instance}"
                runtime = root / "placements" / identity
                (runtime / "runtime").mkdir(parents=True)
                (runtime / "runtime/artifact-identity.json").write_bytes(data)
                guard = runtime / "process/execution-guard"; guard.mkdir(parents=True)
                (guard / "guard.lock").touch()
                (guard / "guard.json").write_text(json.dumps({"status": "closed"}))
                placements.append({"id": identity, "hostId": f"host-{host}", "plane": plane,
                    "instance": instance, "replicaId": f"r{host}", "runtimeRoot": str(runtime), "guardRoot": str(guard)})
    inventory = {"target": "prod-hosted", "environment": "prod", "authorityHostId": "host-0",
                 "sourceDigest": "sha256:" + "a" * 64, "placements": placements}
    (execution / "inventory.json").write_text(json.dumps(inventory))
    return ExecutionSlot(root), "sha256:" + hashlib.sha256(data).hexdigest()


class HostedReleaseReceiptContractTest(unittest.TestCase):
    _DIGEST = "sha256:" + "a" * 64
    _FROM_CANDIDATE = "sha256:" + "b" * 64
    _TO_CANDIDATE = "sha256:" + "c" * 64
    _NEXT_CANDIDATE = "sha256:" + "d" * 64
    _SERVICE = "mainline"

    def _candidate(self) -> dict[str, str]:
        return {
            "imageDigest": self._DIGEST,
            "configDigest": self._DIGEST,
            "contractGraphDigest": self._DIGEST,
            "adapterDigest": self._DIGEST,
        }

    def _admission(self) -> dict:
        return {
            "deliveryTargets": ["service"],
            "prior": {"state": "present", "target": "prod-hosted", "environment": "prod",
                      "previousReleased": {"ref": self._NEXT_CANDIDATE, "digest": self._NEXT_CANDIDATE},
                      "rollbackReadiness": {"ref": "immutable/rollback.json", "digest": self._DIGEST},
                      "expectedGeneration": 1, "ociDigests": [self._FROM_CANDIDATE]},
            "prodActivationAdmissionRef": self._DIGEST,
            "prodActivationAdmissionOciDigest": self._DIGEST,
            "prodActivationAdmissionPayloadDigest": self._DIGEST,
            "prodActivationAdmissionId": self._DIGEST,
            "candidateMaterialManifestRef": self._FROM_CANDIDATE,
            "candidateMaterialManifestOciDigest": self._FROM_CANDIDATE,
            "candidateMaterialManifestPayloadDigest": self._FROM_CANDIDATE,
            "previousReleasedRef": self._NEXT_CANDIDATE,
            "previousReleasedOciDigest": self._NEXT_CANDIDATE,
            "previousReleasedPayloadDigest": self._NEXT_CANDIDATE,
            "previousReleasedId": self._FROM_CANDIDATE,
        }

    def _commit(
        self,
        *,
        state_dir: Path,
        stage: str,
        decision: str,
        generation: int,
        from_candidate: str = _FROM_CANDIDATE,
        to_candidate: str = _TO_CANDIDATE,
        trigger_stage: str | None = None,
        last_good: str | None = None,
        artifact_digest: str = _DIGEST,
    ) -> tuple[dict[str, str], dict[str, object]]:
        resolved_last_good = last_good or (
            to_candidate
            if stage == "100" and decision in {"continue", "rolled_back"}
            else from_candidate
        )
        result = hosted_release_ledger.commit(
            state_dir,
            {
                "schema": hosted_release_ledger.REQUEST_SCHEMA,
                "prodActivationAdmissionRef": "ghcr.io/owner/prod-admission@sha256:" + ("6" * 64),
                "prodActivationAdmissionOciDigest": "sha256:" + ("6" * 64),
                "prodActivationAdmissionPayloadDigest": "sha256:" + ("6" * 64),
                "prodActivationAdmissionId": "sha256:" + ("6" * 64),
                "candidateMaterialManifestRef": "ghcr.io/owner/release-tag@sha256:" + ("7" * 64),
                "candidateMaterialManifestOciDigest": "sha256:" + ("7" * 64),
                "candidateMaterialManifestPayloadDigest": "sha256:" + ("7" * 64),
                                "previousReleasedRef": "ghcr.io/owner/released@sha256:" + ("e" * 64),
                                "previousReleasedOciDigest": "sha256:" + ("e" * 64),
                "previousReleasedPayloadDigest": "sha256:" + ("e" * 64),
                "previousReleasedId": "sha256:" + ("f" * 64),
                "service": self._SERVICE,
                "fromCandidateDigest": from_candidate,
                "toCandidateDigest": to_candidate,
                "step": {"canary": "0", "50": "50", "100": "100"}[stage],
                "stage": stage,
                "triggerStage": trigger_stage or stage,
                "fromServiceFactoryOciDigest": (
                    from_candidate
                ),
                "toServiceFactoryOciDigest": (
                    to_candidate
                ),
                "fromAppFactoryOciDigest": f"sha256:" + ("1" * 64),
                "toAppFactoryOciDigest": f"sha256:" + ("1" * 64),
                "decision": decision,
                "rollbackOutcome": (
                    decision
                    if decision in {"rolled_back", "rollback_failed"}
                    else "not_triggered"
                ),
                "rollbackEvidence": (
                    {
                        "triggered": True,
                        "startedAt": "2026-07-25T23:59:58Z",
                        "endedAt": "2026-07-25T23:59:59Z",
                        "durationMs": 1000,
                        "postChecks": [
                            {
                                "name": "rollback-health",
                                "status": (
                                    "passed"
                                    if decision == "rolled_back"
                                    else "failed"
                                ),
                                "receiptDigest": self._DIGEST,
                            }
                        ],
                    }
                    if decision in {"rolled_back", "rollback_failed"}
                    else {"triggered": False}
                ),
                "candidateMaterialId": artifact_digest,
                **self._candidate(),
                "expectedGeneration": generation,
                "sloReadback": {"values": {"errorRate": 0.001}},
                "postChecks": [
                    {
                        "name": "hosted-health",
                        "status": "passed",
                        "receiptDigest": self._DIGEST,
                    }
                ],
                "lastGoodCandidateDigest": resolved_last_good,
                "verifiedAt": "2026-07-26T00:00:00Z",
            },
        )
        return dict(result["state"]), dict(result["receipt"])

    # spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-005
    def test_prior_observation_missing_root_is_unknown_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "missing"
            result = hosted_release_ledger.observe_prior(root, self._SERVICE)
            self.assertEqual(result["priorState"], "unknown")
            self.assertFalse(result["admissionEligible"])
            self.assertFalse(root.exists())

    def test_prior_observation_empty_directory_and_missing_lock_are_not_absent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            result = hosted_release_ledger.observe_prior(root, self._SERVICE)
            self.assertEqual(result["priorState"], "unknown")
            self.assertEqual(list(root.iterdir()), [])
            (root / ".ledger.lock").touch()
            (root / "receipts").mkdir()
            before = sorted(path.relative_to(root).as_posix() for path in root.rglob("*"))
            result = hosted_release_ledger.observe_prior(root, self._SERVICE)
            self.assertEqual(result["reason"], "PRIOR.TARGET_ABSENCE_UNPROVEN")
            self.assertFalse(result["admissionEligible"])
            self.assertEqual(before, sorted(path.relative_to(root).as_posix() for path in root.rglob("*")))

    def test_prior_observation_current_release_history_and_lost_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._commit(state_dir=root, stage="100", decision="continue", generation=0)
            result = hosted_release_ledger.observe_prior(root, self._SERVICE)
            self.assertEqual(result["priorState"], "present", result)
            self.assertEqual(result["generation"], 1)
            self.assertFalse(result["admissionEligible"])
            before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
            self.assertEqual(result, hosted_release_ledger.observe_prior(root, self._SERVICE))
            self.assertTrue(all(path.read_bytes() == value for path, value in before.items()))
            (root / f"{self._SERVICE}.state").unlink()
            result = hosted_release_ledger.observe_prior(root, self._SERVICE)
            self.assertEqual(result["priorState"], "unknown")
            self.assertEqual(result["reason"], "PRIOR.ORPHAN_HISTORY")
            self.assertTrue(result["historyReceiptIds"])

    def test_prior_observation_inflight_or_corrupt_history_is_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._commit(state_dir=root, stage="canary", decision="continue", generation=0)
            result = hosted_release_ledger.observe_prior(root, self._SERVICE)
            self.assertEqual(result["priorState"], "unknown")
            self.assertEqual(result["reason"], "PRIOR.HISTORY_REQUIRES_RECONCILIATION")
            (root / "receipts" / "unexpected.json").write_text("{}")
            result = hosted_release_ledger.observe_prior(root, self._SERVICE)
            self.assertEqual(result["priorState"], "unknown")
            self.assertFalse(result["admissionEligible"])

    def test_prior_observation_read_failure_and_symlink_are_not_empty(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / ".ledger.lock").touch()
            (root / "receipts").mkdir()
            from quwoquan_ops.cli.prod.hosted_release_ledger_lib import ledger_store
            with mock.patch.object(ledger_store, "_validated_readback", side_effect=PermissionError("denied")):
                result = hosted_release_ledger.observe_prior(root, self._SERVICE)
                self.assertEqual(result["priorState"], "unknown")
            link = root / "linked"
            link.symlink_to(root, target_is_directory=True)
            self.assertEqual(hosted_release_ledger.observe_prior(link, self._SERVICE)["priorState"], "unknown")

    def test_prior_observation_locked_ledger_is_unknown(self) -> None:
        import fcntl
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "receipts").mkdir()
            with (root / ".ledger.lock").open("w") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                result = hosted_release_ledger.observe_prior(root, self._SERVICE)
                self.assertEqual(result["priorState"], "unknown")
                self.assertFalse(result["admissionEligible"])

    def test_stackctl_prior_query_does_not_promote_empty_readback(self) -> None:
        from types import SimpleNamespace
        from quwoquan_ops.cli.commands.inspect_surface import command_inspect
        args = SimpleNamespace(scope="prior", target="prod-hosted", ssh_host="", host_id="")
        with tempfile.TemporaryDirectory() as directory:
            observation = hosted_release_ledger.observe_prior(Path(directory).resolve() / "missing", stackctl.PROD_RELEASE_UNIT)
        with mock.patch.object(stackctl, "_run_hosted_release_ledger", return_value=observation) as query:
            result = command_inspect(args)
        self.assertEqual(result["exitCode"], 2)
        self.assertFalse(result["priorObservation"]["admissionEligible"])
        self.assertFalse(result["targetAbsence"]["admissionEligible"])
        self.assertIn("fence_handoff_to_activation_expected_generation_cas", result["targetAbsence"]["missingAdapters"])
        query.assert_called_once_with(service=stackctl.PROD_RELEASE_UNIT, action="prior-observe")
        args.host_id = "subset"
        with mock.patch.object(stackctl, "_run_hosted_release_ledger") as query:
            self.assertEqual(command_inspect(args)["exitCode"], 2)
        query.assert_not_called()

    def test_explicit_prior_ledger_position_and_absent_are_fail_closed(self) -> None:
        from quwoquan_ops.cli.commands.deploy_release_state import validate_prior_ledger_position
        identity = self._admission()
        identity["previousCandidateDigest"] = self._FROM_CANDIDATE
        state = {"generation": "1", "to_candidate_digest": self._FROM_CANDIDATE,
                 "stage": "100", "decision": "continue"}
        validate_prior_ledger_position(identity, state)
        for change in ({"generation": "2"}, {"stage": "canary"}, {"to_candidate_digest": self._TO_CANDIDATE}):
            with self.assertRaisesRegex(RuntimeError, "PROD.PRIOR.INVALID"):
                validate_prior_ledger_position(identity, {**state, **change})
        resumed = {**state, "generation": "2", "stage": "canary",
                   "prod_activation_admission_id": identity["prodActivationAdmissionId"],
                   "previous_released_id": identity["previousReleasedId"]}
        validate_prior_ledger_position(identity, resumed)
        identity.pop("prior")
        with self.assertRaisesRegex(RuntimeError, "PROD.PRIOR.INVALID"):
            validate_prior_ledger_position(identity, state)

    # spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-005
    def test_execution_kernel_missing_installed_inventory_fails_closed(self) -> None:
        from quwoquan_ops.cli.prod.hosted_release_ledger_lib.execution import ExecutionSlot
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises((ValueError, RuntimeError, OSError)):
                ExecutionSlot(Path(directory).resolve()).acquire(
                    attempt_id=self._DIGEST, expected_execution_generation=0,
                    expected_release_generation=0,
                )

    def test_execution_kernel_slots_guards_and_exact_steps(self) -> None:
        from quwoquan_ops.cli.prod.hosted_release_ledger_lib.execution import ExecutionSlot, PlaneGuard
        for hosts in (1, 2):
            with self.subTest(hosts=hosts), tempfile.TemporaryDirectory() as directory:
                slot, material = _execution_install(Path(directory).resolve() / "authority", hosts)
                state = slot.acquire(attempt_id=self._DIGEST, expected_execution_generation=0, expected_release_generation=0)
                with self.assertRaises(RuntimeError):
                    ExecutionSlot(slot.root).acquire(attempt_id=self._TO_CANDIDATE, expected_execution_generation=0, expected_release_generation=0)
                other, _ = _execution_install(Path(directory).resolve() / "other-target-authority")
                other.acquire(attempt_id=self._TO_CANDIDATE, expected_execution_generation=0, expected_release_generation=0)
                guards = [PlaneGuard(slot, item["id"]) for item in slot.inventory["placements"]]
                request = {"schema": "quwoquan.prod.execution-request.v1", "controllerIdentity": "quwoquan-prod-deployment-controller",
                    "controllerKeyId": "prod-execution-controller-ed25519-k1", "attemptId": self._DIGEST, "executionGeneration": 1, "releaseGeneration": 0,
                    "inventoryDigest": slot.inventory_digest, "placementId": guards[0].placement["id"],
                    "guardIncarnation": 1, "sequence": 1, "action": "observe-runtime-identity", "parameters": {"relativePath": "runtime/artifact-identity.json"}, "materialDigest": material}
                with self.assertRaisesRegex(RuntimeError, "PARTICIPANTS_INCOMPLETE"):
                    slot.register(request)
                try:
                    for guard in guards: guard.prepare(attempt_id=self._DIGEST, generation=state["generation"])
                    step = slot.register(request)
                    self.assertEqual(step, slot.register(request))
                    with self.assertRaisesRegex(RuntimeError, "STEP_CONFLICT"):
                        slot.register({**request, "materialDigest": self._TO_CANDIDATE})
                    with self.assertRaises(ValueError): slot.register({**request, "action": "shell"})
                    result = guards[0].execute(request)
                    self.assertEqual(result["outputDigest"], material)
                    self.assertFalse(result["admissionEligible"])
                    slot.acknowledge({"schema": "quwoquan.prod.execution-result.v1", "requestDigest": step,
                        "placementId": request["placementId"], "guardIncarnation": request["guardIncarnation"],
                        "sequence": request["sequence"], "status": "completed", "effectDigest": result["outputDigest"],
                        "processGroup": result["processGroup"], "returnCode": result["returncode"], "terminal": True, "reconciled": False})
                    with mock.patch("quwoquan_ops.cli.prod.hosted_release_ledger_lib.execution.subprocess.Popen", side_effect=AssertionError("ACK replay must not spawn")):
                        self.assertEqual(result, guards[0].execute(request))
                    with self.assertRaises((RuntimeError, BlockingIOError)):
                        slot.close(attempt_id=self._DIGEST, generation=1)
                    for guard in reversed(guards): guard.close()
                    slot.close(attempt_id=self._DIGEST, generation=1)
                    self.assertEqual(slot.acquire(attempt_id=self._TO_CANDIDATE, expected_execution_generation=1, expected_release_generation=0)["generation"], 2)
                finally:
                    import os
                    for guard in guards:
                        if guard.fd is not None: os.close(guard.fd); guard.fd = None

    def test_execution_kernel_lost_ack_and_guard_crash_never_release_slot(self) -> None:
        import os
        from quwoquan_ops.cli.prod.hosted_release_ledger_lib.execution import PlaneGuard
        with tempfile.TemporaryDirectory() as directory:
            slot, _ = _execution_install(Path(directory).resolve() / "authority")
            slot.acquire(attempt_id=self._DIGEST, expected_execution_generation=0, expected_release_generation=0)
            guard = PlaneGuard(slot, slot.inventory["placements"][0]["id"])
            guard.prepare(attempt_id=self._DIGEST, generation=1)
            os.close(guard.fd); guard.fd = None  # 模拟guard崩溃，flock释放但durable记录未收口。
            with self.assertRaisesRegex(RuntimeError, "CLOSURE_UNKNOWN"):
                slot.close(attempt_id=self._DIGEST, generation=1)
            with self.assertRaises(RuntimeError):
                slot.acquire(attempt_id=self._TO_CANDIDATE, expected_execution_generation=1, expected_release_generation=0)
            retry = PlaneGuard(slot, guard.placement["id"])
            with self.assertRaises(RuntimeError): retry.prepare(attempt_id=self._DIGEST, generation=1)
            self.assertEqual(slot._state()["status"], "held")

    def test_execution_kernel_cross_process_single_winner_and_orphan_guard(self) -> None:
        import os
        import subprocess
        import sys
        with tempfile.TemporaryDirectory() as directory:
            slot, _ = _execution_install(Path(directory).resolve() / "authority")
            script = """import json,sys
from pathlib import Path
from quwoquan_ops.cli.prod.hosted_release_ledger_lib.execution import ExecutionSlot,PlaneGuard
slot=ExecutionSlot(Path(sys.argv[1]))
print('ready',flush=True)
sys.stdin.readline()
try:
 slot.acquire(attempt_id=sys.argv[2],expected_execution_generation=0,expected_release_generation=0)
 print('winner',flush=True)
except (RuntimeError,BlockingIOError):
 print('blocked',flush=True)
"""
            children = [subprocess.Popen([sys.executable, "-B", "-c", script, str(slot.root), attempt], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
                        for attempt in (self._DIGEST, self._TO_CANDIDATE)]
            try:
                for child in children: self.assertEqual(child.stdout.readline().strip(), "ready")
                for child in children: child.stdin.write("go\n"); child.stdin.flush()
                results = [child.communicate(timeout=10)[0].strip() for child in children]
                self.assertEqual(sorted(results), ["blocked", "winner"])
            finally:
                for child in children:
                    if child.poll() is None: child.kill(); child.wait()
            state = slot._state()
            orphan = """import os,sys
from pathlib import Path
from quwoquan_ops.cli.prod.hosted_release_ledger_lib.execution import ExecutionSlot,PlaneGuard
slot=ExecutionSlot(Path(sys.argv[1])); g=PlaneGuard(slot,slot.inventory['placements'][0]['id'])
g.prepare(attempt_id=sys.argv[2],generation=1)
os._exit(0)
"""
            subprocess.run([sys.executable, "-B", "-c", orphan, str(slot.root), state["attemptId"]], check=True, timeout=10)
            with self.assertRaisesRegex(RuntimeError, "CLOSURE_UNKNOWN"):
                slot.close(attempt_id=state["attemptId"], generation=1)
            with self.assertRaises(RuntimeError):
                slot.acquire(attempt_id=self._NEXT_CANDIDATE, expected_execution_generation=1, expected_release_generation=0)

    def test_execution_kernel_step_timeout_keeps_durable_unknown(self) -> None:
        import os
        from quwoquan_ops.cli.prod.hosted_release_ledger_lib.execution import PlaneGuard
        with tempfile.TemporaryDirectory() as directory:
            slot, material = _execution_install(Path(directory).resolve() / "authority")
            slot.acquire(attempt_id=self._DIGEST, expected_execution_generation=0, expected_release_generation=0)
            guards = [PlaneGuard(slot, item["id"]) for item in slot.inventory["placements"]]
            try:
                for guard in guards: guard.prepare(attempt_id=self._DIGEST, generation=1)
                request = {"schema": "quwoquan.prod.execution-request.v1", "controllerIdentity": "quwoquan-prod-deployment-controller",
                    "controllerKeyId": "prod-execution-controller-ed25519-k1", "attemptId": self._DIGEST, "executionGeneration": 1, "releaseGeneration": 0, "inventoryDigest": slot.inventory_digest,
                    "placementId": guards[0].placement["id"], "guardIncarnation": 1, "sequence": 1, "action": "observe-runtime-identity", "parameters": {"relativePath": "runtime/artifact-identity.json"}, "materialDigest": material}
                slot.register(request)
                import subprocess
                with self.assertRaises(subprocess.TimeoutExpired): guards[0].execute(request, timeout_seconds=0)
                with self.assertRaisesRegex(RuntimeError, "RECONCILE_REQUIRED"): guards[0].close()
                with self.assertRaises(RuntimeError): guards[0].execute(request)
                self.assertEqual(slot._state()["status"], "held")
            finally:
                for guard in guards:
                    if guard.fd is not None: os.close(guard.fd); guard.fd = None

    def test_execution_kernel_partial_prepare_reverse_close_and_lock_loss(self) -> None:
        import os
        from quwoquan_ops.cli.prod.hosted_release_ledger_lib.execution import PlaneGuard
        with tempfile.TemporaryDirectory() as directory:
            slot, material = _execution_install(Path(directory).resolve() / "authority")
            slot.acquire(attempt_id=self._DIGEST, expected_execution_generation=0, expected_release_generation=0)
            first = PlaneGuard(slot, slot.inventory["placements"][0]["id"])
            first.prepare(attempt_id=self._DIGEST, generation=1)
            first.close()
            slot.close(attempt_id=self._DIGEST, generation=1)
            slot.acquire(attempt_id=self._TO_CANDIDATE, expected_execution_generation=1, expected_release_generation=0)
            guards = [PlaneGuard(slot, item["id"]) for item in slot.inventory["placements"]]
            try:
                for guard in guards: guard.prepare(attempt_id=self._TO_CANDIDATE, generation=2)
                request = {"schema": "quwoquan.prod.execution-request.v1", "controllerIdentity": "quwoquan-prod-deployment-controller",
                           "controllerKeyId": "prod-execution-controller-ed25519-k1", "attemptId": self._TO_CANDIDATE, "executionGeneration": 2, "releaseGeneration": 0, "inventoryDigest": slot.inventory_digest,
                           "placementId": guards[0].placement["id"], "guardIncarnation": 1, "sequence": 1, "action": "observe-runtime-identity", "parameters": {"relativePath": "runtime/artifact-identity.json"}, "materialDigest": material}
                slot.register(request)
                guards[0].lock_path.unlink(); guards[0].lock_path.touch()
                with self.assertRaisesRegex(RuntimeError, "LOCK_LOST"):
                    guards[0].execute(request)
                with self.assertRaises((RuntimeError, BlockingIOError)): slot.close(attempt_id=self._TO_CANDIDATE, generation=2)
            finally:
                for guard in guards:
                    if guard.fd is not None: os.close(guard.fd); guard.fd = None

    def test_execution_kernel_live_descendant_prevents_success_after_leader_exit(self) -> None:
        import os
        import select
        import signal
        import subprocess
        import sys
        from quwoquan_ops.cli.prod.hosted_release_ledger_lib import execution
        # 注入仅在测试中替换Popen；生产动作/argv闭集不变。
        with tempfile.TemporaryDirectory() as directory:
            slot, material = _execution_install(Path(directory).resolve() / "authority")
            slot.acquire(attempt_id=self._DIGEST, expected_execution_generation=0, expected_release_generation=0)
            guards = [execution.PlaneGuard(slot, item["id"]) for item in slot.inventory["placements"]]
            ready_r, ready_w = os.pipe()
            stop_r, stop_w = os.pipe()
            groups = []
            real_popen = subprocess.Popen
            script = """import os,sys
ready,stop=int(sys.argv[1]),int(sys.argv[2])
pid=os.fork()
if pid==0:
 os.close(1);os.close(2)
 os.write(ready,(str(os.getpid())+'\\n').encode());os.close(ready)
 os.read(stop,1);os._exit(0)
os.close(ready);os.close(stop)
sys.stdout.buffer.write(open(sys.argv[3],'rb').read());sys.stdout.flush()
"""
            def spawn(argv, **kwargs):
                child = real_popen([sys.executable, "-B", "-c", script, str(ready_w), str(stop_r), argv[-1]],
                    pass_fds=(ready_w, stop_r), **kwargs)
                groups.append(child.pid)
                return child
            try:
                for guard in guards: guard.prepare(attempt_id=self._DIGEST, generation=1)
                request = {"schema": "quwoquan.prod.execution-request.v1", "controllerIdentity": "quwoquan-prod-deployment-controller",
                    "controllerKeyId": "prod-execution-controller-ed25519-k1", "attemptId": self._DIGEST, "executionGeneration": 1, "releaseGeneration": 0,
                    "inventoryDigest": slot.inventory_digest, "placementId": guards[0].placement["id"],
                    "guardIncarnation": 1, "sequence": 1, "action": "observe-runtime-identity", "parameters": {"relativePath": "runtime/artifact-identity.json"}, "materialDigest": material}
                slot.register(request)
                with mock.patch.object(execution.subprocess, "Popen", side_effect=spawn):
                    with self.assertRaisesRegex(RuntimeError, "PROCESS_GROUP_NOT_CLOSED"):
                        guards[0].execute(request)
                self.assertTrue(select.select([ready_r], [], [], 5)[0])
                descendant = int(os.read(ready_r, 100).strip())
                os.kill(descendant, 0)
                self.assertEqual(os.getpgid(descendant), groups[0])
                with self.assertRaisesRegex(RuntimeError, "RECONCILE_REQUIRED"): guards[0].close()
                with self.assertRaises(RuntimeError):
                    slot.acquire(attempt_id=self._NEXT_CANDIDATE, expected_execution_generation=1, expected_release_generation=0)
            finally:
                for pgid in groups:
                    try: os.killpg(pgid, signal.SIGKILL)
                    except ProcessLookupError: pass
                for fd in (ready_r, ready_w, stop_r, stop_w): os.close(fd)
                for guard in guards:
                    if guard.fd is not None: os.close(guard.fd); guard.fd = None

    def test_execution_kernel_guard_parent_exit_with_live_orphan_remains_blocked(self) -> None:
        import fcntl
        import os
        import select
        import signal
        import subprocess
        import sys
        from quwoquan_ops.cli.prod.hosted_release_ledger_lib.execution import ExecutionSlot, PlaneGuard
        with tempfile.TemporaryDirectory() as directory:
            slot, material = _execution_install(Path(directory).resolve() / "authority")
            ready_r, ready_w = os.pipe()
            stop_r, stop_w = os.pipe()
            child_script = """import os,sys
pid=os.fork()
if pid==0:
 os.close(1);os.close(2)
 os.write(int(sys.argv[1]),(str(os.getpid())+'\\n').encode());os.close(int(sys.argv[1]))
 os.read(int(sys.argv[2]),1);os._exit(0)
os.close(int(sys.argv[1]));os.close(int(sys.argv[2]))
sys.stdout.buffer.write(open(sys.argv[3],'rb').read());sys.stdout.flush()
"""
            parent_script = """import json,os,sys,subprocess
from pathlib import Path
from quwoquan_ops.cli.prod.hosted_release_ledger_lib import execution as e
slot=e.ExecutionSlot(Path(sys.argv[1]));attempt=sys.argv[2]
slot.acquire(attempt_id=attempt,expected_execution_generation=0,expected_release_generation=0)
guards=[e.PlaneGuard(slot,p['id']) for p in slot.inventory['placements']]
for g in guards:g.prepare(attempt_id=attempt,generation=1)
request={'schema':'quwoquan.prod.execution-request.v1','controllerIdentity':'quwoquan-prod-deployment-controller','controllerKeyId':'prod-execution-controller-ed25519-k1','attemptId':attempt,'executionGeneration':1,'releaseGeneration':0,'inventoryDigest':slot.inventory_digest,'placementId':guards[0].placement['id'],'guardIncarnation':1,'sequence':1,'action':'observe-runtime-identity','parameters':{'relativePath':'runtime/artifact-identity.json'},'materialDigest':sys.argv[3]}
slot.register(request)
real=subprocess.Popen
class Child:
 def __init__(self,argv,**kw):
  self.child=real([sys.executable,'-B','-c',sys.argv[6],sys.argv[4],sys.argv[5],argv[-1]],pass_fds=(int(sys.argv[4]),int(sys.argv[5])),**kw)
  self.pid=self.child.pid
 def communicate(self,timeout):
  self.child.communicate(timeout=timeout)
  print(json.dumps({'pgid':self.pid,'guardPath':str(guards[0].path)}),flush=True)
  sys.stdin.readline()
  os._exit(0)
e.subprocess.Popen=Child
guards[0].execute(request)
"""
            parent = subprocess.Popen([sys.executable, "-B", "-c", parent_script, str(slot.root), self._DIGEST,
                material, str(ready_w), str(stop_r), child_script], pass_fds=(ready_w, stop_r),
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            pgid = None
            try:
                self.assertTrue(select.select([ready_r], [], [], 10)[0], "descendant startup barrier")
                descendant = int(os.read(ready_r, 100).strip())
                pgid = os.getpgid(descendant)  # 精确记录仅由本测试创建的组。
                self.assertTrue(select.select([parent.stdout], [], [], 10)[0], "durable running barrier")
                evidence = json.loads(parent.stdout.readline())
                self.assertEqual(evidence["pgid"], pgid)
                guard_path = Path(evidence["guardPath"])
                before = guard_path.read_bytes()
                self.assertEqual(next(iter(json.loads(before)["steps"].values()))["status"], "running")
                parent.stdin.write("exit\n"); parent.stdin.flush()
                parent.wait(timeout=10)
                os.kill(descendant, 0)
                with self.assertRaises(ProcessLookupError): os.kill(pgid, 0)  # leader已被guard wait回收。
                with (guard_path.parent / "guard.lock").open("r+") as lock:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)  # OS锁确实已释放。
                fresh = ExecutionSlot(slot.root)
                with self.assertRaisesRegex(RuntimeError, "BUSY_OR_STALE"):
                    fresh.acquire(attempt_id=self._NEXT_CANDIDATE, expected_execution_generation=1, expected_release_generation=0)
                with self.assertRaisesRegex(RuntimeError, "RESULTS_INCOMPLETE|CLOSURE_UNKNOWN"):
                    fresh.close(attempt_id=self._DIGEST, generation=1)
                with self.assertRaises(RuntimeError):
                    PlaneGuard(fresh, fresh.inventory["placements"][0]["id"]).prepare(attempt_id=self._DIGEST, generation=1)
                self.assertEqual(guard_path.read_bytes(), before)
                # 即便测试精确终止后代，也不替内核伪造reconcile成功或清空记录。
                os.killpg(pgid, signal.SIGKILL); pgid = None
                with self.assertRaises(RuntimeError): fresh.close(attempt_id=self._DIGEST, generation=1)
                self.assertEqual(guard_path.read_bytes(), before)
            finally:
                if pgid is not None:
                    try: os.killpg(pgid, signal.SIGKILL)
                    except ProcessLookupError: pass
                if parent.poll() is None: parent.kill(); parent.wait(timeout=10)
                for stream in (parent.stdin, parent.stdout, parent.stderr): stream.close()
                for fd in (ready_r, ready_w, stop_r, stop_w): os.close(fd)

    def test_execution_kernel_failed_completion_write_cannot_close_from_memory(self) -> None:
        import os
        from quwoquan_ops.cli.prod.hosted_release_ledger_lib import execution
        with tempfile.TemporaryDirectory() as directory:
            slot, material = _execution_install(Path(directory).resolve() / "authority")
            slot.acquire(attempt_id=self._DIGEST, expected_execution_generation=0, expected_release_generation=0)
            guards = [execution.PlaneGuard(slot, p["id"]) for p in slot.inventory["placements"]]
            try:
                for guard in guards: guard.prepare(attempt_id=self._DIGEST, generation=1)
                request = {"schema": "quwoquan.prod.execution-request.v1", "controllerIdentity": "quwoquan-prod-deployment-controller",
                    "controllerKeyId": "prod-execution-controller-ed25519-k1", "attemptId": self._DIGEST, "executionGeneration": 1, "releaseGeneration": 0,
                    "inventoryDigest": slot.inventory_digest, "placementId": guards[0].placement["id"],
                    "guardIncarnation": 1, "sequence": 1, "action": "observe-runtime-identity", "parameters": {"relativePath": "runtime/artifact-identity.json"}, "materialDigest": material}
                slot.register(request)
                write = execution._atomic_write
                def fail_completion(path, raw):
                    if path == guards[0].path and any(step["status"] == "completed" for step in json.loads(raw)["steps"].values()):
                        raise OSError("fixture completion persistence failed")
                    return write(path, raw)
                with mock.patch.object(execution, "_atomic_write", side_effect=fail_completion):
                    with self.assertRaisesRegex(OSError, "persistence failed"): guards[0].execute(request)
                before = guards[0].path.read_bytes()
                with self.assertRaisesRegex(RuntimeError, "DURABLE_STATE_DRIFT"):
                    guards[0].close()
                with mock.patch.object(execution.subprocess, "Popen", side_effect=AssertionError("unknown must not respawn")):
                    with self.assertRaisesRegex(RuntimeError, "DURABLE_STATE_DRIFT"): guards[0].execute(request)
                self.assertEqual(guards[0].path.read_bytes(), before)
            finally:
                for guard in guards:
                    if guard.fd is not None: os.close(guard.fd); guard.fd = None

    def test_execution_kernel_rejects_argv_path_and_identity_symlink_without_spawn(self) -> None:
        import os
        from quwoquan_ops.cli.prod.hosted_release_ledger_lib import execution
        with tempfile.TemporaryDirectory() as directory:
            slot, material = _execution_install(Path(directory).resolve() / "authority")
            slot.acquire(attempt_id=self._DIGEST, expected_execution_generation=0, expected_release_generation=0)
            guards = [execution.PlaneGuard(slot, p["id"]) for p in slot.inventory["placements"]]
            try:
                for guard in guards: guard.prepare(attempt_id=self._DIGEST, generation=1)
                request = {"schema": "quwoquan.prod.execution-request.v1", "controllerIdentity": "quwoquan-prod-deployment-controller",
                    "controllerKeyId": "prod-execution-controller-ed25519-k1", "attemptId": self._DIGEST, "executionGeneration": 1, "releaseGeneration": 0,
                    "inventoryDigest": slot.inventory_digest, "placementId": guards[0].placement["id"],
                    "guardIncarnation": 1, "sequence": 1, "action": "observe-runtime-identity", "parameters": {"relativePath": "runtime/artifact-identity.json"}, "materialDigest": material}
                for bad in ({**request, "argv": ["sh", "-c", "true"]}, {**request, "path": "../../escape"}, {**request, "action": "shell"}):
                    with self.assertRaises(ValueError): slot.register(bad)
                slot.register(request)
                identity = Path(guards[0].placement["runtimeRoot"]) / "runtime/artifact-identity.json"
                outside = Path(directory).resolve() / "outside.json"
                outside.write_bytes(identity.read_bytes()); identity.unlink(); identity.symlink_to(outside)
                with mock.patch.object(execution.subprocess, "Popen", side_effect=AssertionError("unsafe path spawned")):
                    with self.assertRaisesRegex(ValueError, "SYMLINK"): guards[0].execute(request)
                with self.assertRaisesRegex(ValueError, "PATH_INVALID"):
                    execution._safe(slot.root / ".." / "outside.json", directory=False)
            finally:
                for guard in guards:
                    if guard.fd is not None: os.close(guard.fd); guard.fd = None

    def test_execution_guard_signed_delivery_lost_ack_and_reconcile_only(self) -> None:
        import hashlib
        import os
        import subprocess
        from quwoquan_ops.cli.prod.hosted_release_ledger_lib.execution_delivery import sign_request
        from quwoquan_ops.cli.prod.hosted_release_ledger_lib.execution_guard import DurablePlaneGuard, verify_envelope
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); guard_root = root / "guard"; runtime = root / "runtime"
            guard_root.mkdir(); runtime.mkdir(); (guard_root / "guard.lock").touch()
            identity = runtime / "runtime/artifact-identity.json"; identity.parent.mkdir(); identity.write_bytes(b"exact-runtime")
            private = root / "controller.pem"; public = root / "controller.pub.pem"
            subprocess.run(["openssl", "genpkey", "-algorithm", "Ed25519", "-out", str(private)], check=True, capture_output=True)
            private.chmod(0o600)
            subprocess.run(["openssl", "pkey", "-in", str(private), "-pubout", "-out", str(public)], check=True, capture_output=True)
            request = {"schema": "quwoquan.prod.execution-request.v1", "controllerIdentity": "quwoquan-prod-deployment-controller",
                "controllerKeyId": "prod-execution-controller-ed25519-k1", "attemptId": self._DIGEST, "executionGeneration": 1,
                "releaseGeneration": 0, "inventoryDigest": self._DIGEST, "placementId": "prod-host-01-service-prod-r0",
                "guardIncarnation": 1, "sequence": 1, "action": "observe-runtime-identity",
                "parameters": {"relativePath": "runtime/artifact-identity.json"}, "materialDigest": self._DIGEST}
            envelope = sign_request(request, private_key=private)
            verified = verify_envelope(envelope, public_key=public, expected_identity=request["controllerIdentity"], expected_key_id=request["controllerKeyId"]); self.assertEqual(verified, request)
            guard = DurablePlaneGuard(guard_root, runtime)
            prepare = {**request, "sequence": 1, "action": "guard-prepare", "parameters": {}, "materialDigest": self._DIGEST}
            guard.submit(prepare)
            request["sequence"] = 2
            envelope = sign_request(request, private_key=private)
            verified = verify_envelope(envelope, public_key=public, expected_identity=request["controllerIdentity"], expected_key_id=request["controllerKeyId"])
            result = guard.submit(verified)
            self.assertTrue(result["terminal"]); self.assertEqual(result, guard.submit(verified))  # lost ACK replay
            journal = json.loads((guard_root / "journal.json").read_bytes()); key = result["requestDigest"]
            journal["steps"][key] = {"status": "running", "request": request, "processGroup": 99999999}; journal["mode"] = "reconcile-only"
            (guard_root / "journal.json").write_text(json.dumps(journal))
            next_request = {**request, "sequence": 3}
            with self.assertRaisesRegex(RuntimeError, "RECONCILE_ONLY"): guard.submit(next_request)
            effect = "sha256:" + hashlib.sha256(b"readback").hexdigest()
            reconciled = guard.reconcile(key, effect_digest=effect); self.assertTrue(reconciled["reconciled"])
            self.assertEqual(json.loads((guard_root / "journal.json").read_bytes())["mode"], "ready")

    def test_execution_kernel_rejects_symlink_and_partial_inventory(self) -> None:
        from quwoquan_ops.cli.prod.hosted_release_ledger_lib.execution import ExecutionSlot
        with tempfile.TemporaryDirectory() as directory:
            slot, _ = _execution_install(Path(directory).resolve() / "authority")
            path = slot.inventory_path
            inventory = json.loads(path.read_bytes()); inventory["placements"].pop()
            path.write_text(json.dumps(inventory))
            with self.assertRaisesRegex(ValueError, "INCOMPLETE"):
                ExecutionSlot(slot.root)
            link = Path(directory).resolve() / "alias"; link.symlink_to(slot.root, target_is_directory=True)
            with self.assertRaises(ValueError): ExecutionSlot(link)

    def test_gray_carry_on_and_full_receipts_bind_immutable_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_dir = Path(temporary)
            first, gray_receipt = self._commit(
                state_dir=state_dir,
                stage="canary",
                decision="continue",
                generation=0,
            )
            second, carry_receipt = self._commit(
                state_dir=state_dir,
                stage="50",
                decision="continue",
                generation=1,
            )
            third, full_receipt = self._commit(
                state_dir=state_dir,
                stage="100",
                decision="continue",
                generation=2,
            )
            readback = hosted_release_ledger.fetch(state_dir, self._SERVICE)

        self.assertEqual(
            [first["stage"], second["stage"], third["stage"]],
            ["canary", "50", "100"],
        )
        for receipt, expected_generation, expected_last_good in (
            (gray_receipt, 1, self._FROM_CANDIDATE),
            (carry_receipt, 2, self._FROM_CANDIDATE),
            (full_receipt, 3, self._TO_CANDIDATE),
        ):
            self.assertEqual(
                {
                    "imageDigest": receipt["imageDigest"],
                    "configDigest": receipt["configDigest"],
                    "contractGraphDigest": receipt["contractGraphDigest"],
                    "adapterDigest": receipt["adapterDigest"],
                },
                self._candidate(),
            )
            self.assertEqual(receipt["committedGeneration"], expected_generation)
            self.assertEqual(
                receipt["lastGoodCandidateDigest"],
                expected_last_good,
            )
            self.assertEqual(
                receipt["postChecks"],
                [
                    {
                        "name": "hosted-health",
                        "status": "passed",
                        "receiptDigest": self._DIGEST,
                    }
                ],
            )
            self.assertEqual(receipt["decision"], "continue")
            self.assertEqual(receipt["rollbackEvidence"], {"triggered": False})
        self.assertEqual(readback["authority"], "prod-hosted-service-plane")
        self.assertEqual(readback["receipt"], full_receipt)
        self.assertEqual(
            readback["receiptRef"],
            f"receipt:hosted:{full_receipt['receiptId']}",
        )
        self.assertEqual(first["canary_receipt_id"], gray_receipt["receiptId"])
        self.assertEqual(first["percent_50_receipt_id"], "")
        self.assertEqual(first["percent_100_receipt_id"], "")
        self.assertEqual(second["canary_receipt_id"], gray_receipt["receiptId"])
        self.assertEqual(second["percent_50_receipt_id"], carry_receipt["receiptId"])
        self.assertEqual(second["percent_100_receipt_id"], "")
        self.assertEqual(third["canary_receipt_id"], gray_receipt["receiptId"])
        self.assertEqual(third["percent_50_receipt_id"], carry_receipt["receiptId"])
        self.assertEqual(third["percent_100_receipt_id"], full_receipt["receiptId"])

    def test_successful_and_failed_rollback_are_distinct_receipt_facts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_dir = Path(temporary)
            _, success = self._commit(
                state_dir=state_dir,
                stage="100",
                decision="rolled_back",
                generation=0,
                from_candidate=self._TO_CANDIDATE,
                to_candidate=self._FROM_CANDIDATE,
            )
            _, failure = self._commit(
                state_dir=state_dir,
                stage="100",
                decision="rollback_failed",
                generation=1,
            )

        self.assertEqual(success["decision"], "rolled_back")
        self.assertEqual(success["rollbackOutcome"], "rolled_back")
        self.assertEqual(success["rollbackEvidence"]["durationMs"], 1000)
        self.assertEqual(
            success["rollbackEvidence"]["postChecks"][0]["status"], "passed"
        )
        self.assertEqual(failure["decision"], "rollback_failed")
        self.assertEqual(failure["rollbackOutcome"], "rollback_failed")
        self.assertEqual(
            failure["rollbackEvidence"]["postChecks"][0]["status"], "failed"
        )

    def test_rollback_evidence_rejects_non_exact_or_invented_facts(self) -> None:
        with self.assertRaisesRegex(ValueError, "only triggered=false"):
            hosted_release_ledger.validate_rollback_evidence(
                {"triggered": False, "durationMs": 0},
                decision="continue",
                rollback_outcome="not_triggered",
                verified_at="2026-07-26T00:00:00Z",
            )
        with self.assertRaisesRegex(ValueError, "non-empty passed"):
            hosted_release_ledger.validate_rollback_evidence(
                {
                    "triggered": True,
                    "startedAt": "2026-07-25T23:59:58Z",
                    "endedAt": "2026-07-25T23:59:59Z",
                    "durationMs": 1000,
                    "postChecks": [],
                },
                decision="rolled_back",
                rollback_outcome="rolled_back",
                verified_at="2026-07-26T00:00:00Z",
            )
        with self.assertRaisesRegex(ValueError, "not canonically bound"):
            hosted_release_ledger.validate_rollback_evidence(
                {"triggered": False},
                decision="rollback_failed",
                rollback_outcome="not_triggered",
                verified_at="2026-07-26T00:00:00Z",
            )

    def test_check_summary_never_treats_missing_exit_code_as_passed(self) -> None:
        checks = stackctl._release_check_receipts(
            [
                {"exitCode": 0, "summary": "healthy"},
                {"exitCode": None, "summary": "missing"},
                {"summary": "absent"},
            ]
        )
        self.assertEqual(
            [item["status"] for item in checks],
            ["passed", "failed", "failed"],
        )

    def test_new_target_resets_stage_receipt_history(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_dir = Path(temporary)
            self._commit(
                state_dir=state_dir,
                stage="canary",
                decision="continue",
                generation=0,
            )
            self._commit(
                state_dir=state_dir,
                stage="50",
                decision="continue",
                generation=1,
            )
            _, old_full = self._commit(
                state_dir=state_dir,
                stage="100",
                decision="continue",
                generation=2,
            )
            new_state, new_gray = self._commit(
                state_dir=state_dir,
                stage="canary",
                decision="continue",
                generation=3,
                from_candidate=self._TO_CANDIDATE,
                to_candidate=self._NEXT_CANDIDATE,
            )

        self.assertNotEqual(new_gray["receiptId"], old_full["receiptId"])
        self.assertEqual(
            {
                field: new_state[field]
                for field in hosted_release_ledger.STAGE_RECEIPT_ID_FIELDS.values()
            },
            {
                "canary_receipt_id": new_gray["receiptId"],
                "percent_5_receipt_id": "",
                "percent_20_receipt_id": "",
                "percent_50_receipt_id": "",
                "percent_100_receipt_id": "",
            },
        )

    def test_same_candidate_rejects_evidence_drift_before_state_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_dir = Path(temporary)
            first_state, _ = self._commit(
                state_dir=state_dir,
                stage="canary",
                decision="continue",
                generation=0,
            )
            with self.assertRaisesRegex(RuntimeError, "evidence drifted"):
                self._commit(
                    state_dir=state_dir,
                    stage="50",
                    decision="continue",
                    generation=1,
                    artifact_digest=self._NEXT_CANDIDATE,
                )
            readback = hosted_release_ledger.fetch(state_dir, self._SERVICE)

        self.assertEqual(readback["state"], first_state)

    def test_rollback_preserves_history_and_updates_its_trigger_stage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_dir = Path(temporary)
            _, gray = self._commit(
                state_dir=state_dir,
                stage="canary",
                decision="continue",
                generation=0,
            )
            _, carry = self._commit(
                state_dir=state_dir,
                stage="50",
                decision="continue",
                generation=1,
            )
            rollback_state, rollback = self._commit(
                state_dir=state_dir,
                stage="100",
                trigger_stage="50",
                decision="rolled_back",
                generation=2,
                from_candidate=self._TO_CANDIDATE,
                to_candidate=self._FROM_CANDIDATE,
                last_good=self._FROM_CANDIDATE,
            )
            readback = hosted_release_ledger.fetch(state_dir, self._SERVICE)

        self.assertNotEqual(carry["receiptId"], rollback["receiptId"])
        self.assertEqual(
            rollback_state["canary_receipt_id"],
            gray["receiptId"],
        )
        self.assertEqual(
            rollback_state["percent_50_receipt_id"],
            rollback["receiptId"],
        )
        self.assertEqual(rollback_state["percent_100_receipt_id"], "")
        self.assertEqual(readback["state"], rollback_state)

    @staticmethod
    def _write_state(path: Path, state: dict[str, str]) -> None:
        path.write_text(
            "\n".join(f"{key}={value}" for key, value in state.items()) + "\n",
            encoding="utf-8",
        )

    def test_transition_rejects_retired_release_evidence_shape_before_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_dir = Path(temporary)
            _, receipt = self._commit(
                state_dir=state_dir,
                stage="canary",
                decision="continue",
                generation=0,
            )
            request = {
                key: receipt[key]
                for key in hosted_release_ledger.REQUEST_FIELDS
                if key != "schema"
            }
            request["schema"] = hosted_release_ledger.REQUEST_SCHEMA
            request["fromReleaseEvidenceRef"] = "ghcr.io/owner/release@" + self._FROM_CANDIDATE
            state_before = (state_dir / f"{self._SERVICE}.state").read_bytes()
            with self.assertRaisesRegex(ValueError, "invalid shape"):
                hosted_release_ledger.commit(state_dir, request)
            self.assertEqual(
                (state_dir / f"{self._SERVICE}.state").read_bytes(),
                state_before,
            )

    def test_fetch_rejects_old_state_without_fixed_history_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_dir = Path(temporary)
            state, _ = self._commit(
                state_dir=state_dir,
                stage="canary",
                decision="continue",
                generation=0,
            )
            state.pop("percent_100_receipt_id")
            self._write_state(state_dir / f"{self._SERVICE}.state", state)
            with self.assertRaisesRegex(RuntimeError, "shape is not canonical"):
                hosted_release_ledger.fetch(state_dir, self._SERVICE)
            with self.assertRaisesRegex(RuntimeError, "shape is not canonical"):
                self._commit(
                    state_dir=state_dir,
                    stage="50",
                    decision="continue",
                    generation=1,
                )

    def test_fetch_rejects_missing_or_unbound_history_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_dir = Path(temporary)
            state, _ = self._commit(
                state_dir=state_dir,
                stage="canary",
                decision="continue",
                generation=0,
            )
            state["percent_50_receipt_id"] = "f" * 64
            self._write_state(state_dir / f"{self._SERVICE}.state", state)
            with self.assertRaisesRegex(RuntimeError, "receipt is missing"):
                hosted_release_ledger.fetch(state_dir, self._SERVICE)

        with tempfile.TemporaryDirectory() as temporary:
            state_dir = Path(temporary)
            state, current = self._commit(
                state_dir=state_dir,
                stage="canary",
                decision="continue",
                generation=0,
            )
            unrelated = dict(current)
            unrelated.update(
                {
                    "fromCandidateDigest": self._NEXT_CANDIDATE,
                    "toCandidateDigest": self._DIGEST,
                    "triggerStage": "50",
                    "fromServiceFactoryOciDigest": self._NEXT_CANDIDATE,
                    "toServiceFactoryOciDigest": (
                        self._DIGEST
                    ),
                }
            )
            unrelated.pop("receiptId")
            unrelated_id = hosted_release_ledger._receipt_id(unrelated)
            unrelated["receiptId"] = unrelated_id
            receipt_path = state_dir / "receipts" / f"{unrelated_id}.json"
            receipt_path.write_text(
                json.dumps(unrelated, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            state["percent_50_receipt_id"] = unrelated_id
            self._write_state(state_dir / f"{self._SERVICE}.state", state)
            with self.assertRaisesRegex(RuntimeError, "candidate-transaction bound"):
                hosted_release_ledger.fetch(state_dir, self._SERVICE)

    def test_history_receipt_hash_authority_and_service_are_verified(self) -> None:
        for mutation in ("hash", "authority", "service"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                state_dir = Path(temporary)
                state, current = self._commit(
                    state_dir=state_dir,
                    stage="canary",
                    decision="continue",
                    generation=0,
                )
                history = dict(current)
                history["triggerStage"] = "50"
                history.pop("receiptId")
                if mutation == "authority":
                    history["authority"] = "untrusted-plane"
                elif mutation == "service":
                    history["service"] = "other-service"
                history_id = hosted_release_ledger._receipt_id(history)
                history["receiptId"] = history_id
                if mutation == "hash":
                    history["verifiedAt"] = "2026-07-26T00:01:00Z"
                receipt_path = state_dir / "receipts" / f"{history_id}.json"
                receipt_path.write_text(
                    json.dumps(history, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                state["percent_50_receipt_id"] = history_id
                self._write_state(state_dir / f"{self._SERVICE}.state", state)
                with self.assertRaisesRegex(
                    RuntimeError,
                    "digest or ledger binding is invalid",
                ):
                    hosted_release_ledger.fetch(state_dir, self._SERVICE)

    def test_stackctl_readback_requires_fixed_stage_history_binding(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            readback = hosted_release_ledger.commit(
                Path(temporary),
                {
                    "schema": hosted_release_ledger.REQUEST_SCHEMA,
                "prodActivationAdmissionRef": "ghcr.io/owner/prod-admission@sha256:" + ("6" * 64),
                "prodActivationAdmissionOciDigest": "sha256:" + ("6" * 64),
                "prodActivationAdmissionPayloadDigest": "sha256:" + ("6" * 64),
                "prodActivationAdmissionId": "sha256:" + ("6" * 64),
                "candidateMaterialManifestRef": "ghcr.io/owner/release-tag@sha256:" + ("7" * 64),
                "candidateMaterialManifestOciDigest": "sha256:" + ("7" * 64),
                "candidateMaterialManifestPayloadDigest": "sha256:" + ("7" * 64),
                                "previousReleasedRef": "ghcr.io/owner/released@sha256:" + ("e" * 64),
                                "previousReleasedOciDigest": "sha256:" + ("e" * 64),
                "previousReleasedPayloadDigest": "sha256:" + ("e" * 64),
                "previousReleasedId": "sha256:" + ("f" * 64),
                    "service": self._SERVICE,
                    "fromCandidateDigest": self._FROM_CANDIDATE,
                    "toCandidateDigest": self._TO_CANDIDATE,
                    "step": "0",
                    "stage": "canary",
                    "triggerStage": "canary",
                    "fromServiceFactoryOciDigest": self._FROM_CANDIDATE,
                    "toServiceFactoryOciDigest": self._TO_CANDIDATE,
                    "fromAppFactoryOciDigest": "sha256:" + ("1" * 64),
                    "toAppFactoryOciDigest": "sha256:" + ("1" * 64),
                    "decision": "continue",
                    "rollbackOutcome": "not_triggered",
                    "rollbackEvidence": {"triggered": False},
                    "candidateMaterialId": self._DIGEST,
                    **self._candidate(),
                    "expectedGeneration": 0,
                    "sloReadback": {"sampleCount": 100},
                    "postChecks": [],
                    "lastGoodCandidateDigest": self._FROM_CANDIDATE,
                    "verifiedAt": "2026-07-26T00:00:00Z",
                },
            )

        self.assertEqual(
            stackctl._validate_hosted_release_readback(
                readback,
                service=self._SERVICE,
            ),
            readback,
        )
        for field in hosted_release_ledger.STAGE_RECEIPT_ID_FIELDS.values():
            invalid = copy.deepcopy(readback)
            invalid["state"].pop(field)
            with self.subTest(missing=field), self.assertRaisesRegex(
                RuntimeError,
                "shape is not canonical",
            ):
                stackctl._validate_hosted_release_readback(
                    invalid,
                    service=self._SERVICE,
                )

        malformed = copy.deepcopy(readback)
        malformed["state"]["percent_50_receipt_id"] = "not-a-receipt"
        with self.assertRaisesRegex(RuntimeError, "history is invalid"):
            stackctl._validate_hosted_release_readback(
                malformed,
                service=self._SERVICE,
            )

        wrong_slot = copy.deepcopy(readback)
        wrong_slot["state"]["canary_receipt_id"] = ""
        wrong_slot["state"]["percent_50_receipt_id"] = wrong_slot["state"][
            "receipt_id"
        ]
        with self.assertRaisesRegex(RuntimeError, "not trigger-stage bound"):
            stackctl._validate_hosted_release_readback(
                wrong_slot,
                service=self._SERVICE,
            )

    def test_stackctl_cache_revalidates_history_before_local_write(self) -> None:
        with tempfile.TemporaryDirectory() as hosted_temporary:
            readback = hosted_release_ledger.commit(
                Path(hosted_temporary),
                {
                    "schema": hosted_release_ledger.REQUEST_SCHEMA,
                "prodActivationAdmissionRef": "ghcr.io/owner/prod-admission@sha256:" + ("6" * 64),
                "prodActivationAdmissionOciDigest": "sha256:" + ("6" * 64),
                "prodActivationAdmissionPayloadDigest": "sha256:" + ("6" * 64),
                "prodActivationAdmissionId": "sha256:" + ("6" * 64),
                "candidateMaterialManifestRef": "ghcr.io/owner/release-tag@sha256:" + ("7" * 64),
                "candidateMaterialManifestOciDigest": "sha256:" + ("7" * 64),
                "candidateMaterialManifestPayloadDigest": "sha256:" + ("7" * 64),
                                "previousReleasedRef": "ghcr.io/owner/released@sha256:" + ("e" * 64),
                                "previousReleasedOciDigest": "sha256:" + ("e" * 64),
                "previousReleasedPayloadDigest": "sha256:" + ("e" * 64),
                "previousReleasedId": "sha256:" + ("f" * 64),
                    "service": self._SERVICE,
                    "fromCandidateDigest": self._FROM_CANDIDATE,
                    "toCandidateDigest": self._TO_CANDIDATE,
                    "step": "0",
                    "stage": "canary",
                    "triggerStage": "canary",
                    "fromServiceFactoryOciDigest": self._FROM_CANDIDATE,
                    "toServiceFactoryOciDigest": self._TO_CANDIDATE,
                    "fromAppFactoryOciDigest": "sha256:" + ("1" * 64),
                    "toAppFactoryOciDigest": "sha256:" + ("1" * 64),
                    "decision": "continue",
                    "rollbackOutcome": "not_triggered",
                    "rollbackEvidence": {"triggered": False},
                    "candidateMaterialId": self._DIGEST,
                    **self._candidate(),
                    "expectedGeneration": 0,
                    "sloReadback": {},
                    "postChecks": [],
                    "lastGoodCandidateDigest": self._FROM_CANDIDATE,
                    "verifiedAt": "2026-07-26T00:00:00Z",
                },
            )
        invalid_state = dict(readback["state"])
        invalid_state.pop("percent_100_receipt_id")
        with tempfile.TemporaryDirectory() as cache_temporary:
            cache_dir = Path(cache_temporary)
            with (
                mock.patch.object(
                    stackctl,
                    "_release_state_dir",
                    return_value=cache_dir,
                ),
                self.assertRaisesRegex(RuntimeError, "shape is not canonical"),
            ):
                stackctl._cache_hosted_release_readback(
                    self._SERVICE,
                    invalid_state,
                    readback["receipt"],
                )
            self.assertFalse((cache_dir / f"{self._SERVICE}.state").exists())

    def test_stackctl_commit_uses_returned_hosted_readback_without_refetch(self) -> None:
        committed = {
            "state": {"receipt_id": "a" * 64},
            "receipt": {"receiptId": "a" * 64},
            "receiptRef": "receipt:hosted:" + "a" * 64,
        }
        cached_path = Path("/tmp/hosted-release-receipt.json")
        with (
            mock.patch(
                "quwoquan_ops.cli.commands.deploy_release_state.guarded_release_transition",
                return_value={"terminal": True},
            ) as guarded_transition,
            mock.patch.object(
                stackctl,
                "_run_hosted_release_ledger",
                return_value=committed,
            ) as run_hosted,
            mock.patch.object(
                stackctl,
                "_cache_hosted_release_readback",
                return_value=(committed["state"], cached_path),
            ) as cache_readback,
            mock.patch.object(
                stackctl,
                "utc_now",
                return_value="2026-07-26T00:00:00Z",
            ),
        ):
            result = stackctl._commit_hosted_release_transition(
                service=self._SERVICE,
                from_candidate_digest=self._FROM_CANDIDATE,
                to_candidate_digest=self._TO_CANDIDATE,
                step="5",
                stage="canary",
                decision="continue",
                candidate_material_id=self._DIGEST,
                expected_generation=1,
                receipt_id="unused",
                slo_readback={"sampleCount": 100},
                candidate_digests=self._candidate(),
                last_good_candidate_digest=self._FROM_CANDIDATE,
                post_deploy_checks=[],
                rollback_outcome="not_triggered",
                rollback_evidence={"triggered": False},
                from_service_factory_oci_digest=self._FROM_CANDIDATE,
                to_service_factory_oci_digest=self._TO_CANDIDATE,
                from_app_factory_oci_digest=self._FROM_CANDIDATE,
                to_app_factory_oci_digest=self._TO_CANDIDATE,
                prod_activation_admission=self._admission(),
            )

        self.assertEqual(result, (committed["state"], cached_path))
        self.assertEqual(run_hosted.call_count, 1)
        self.assertEqual(run_hosted.call_args.kwargs["action"], "fetch")
        guarded_transition.assert_called_once()
        self.assertEqual(guarded_transition.call_args.kwargs["request"]["rollbackEvidence"], {"triggered": False})
        cache_readback.assert_called_once_with(
            self._SERVICE,
            committed["state"],
            committed["receipt"],
        )


if __name__ == "__main__":
    unittest.main()
