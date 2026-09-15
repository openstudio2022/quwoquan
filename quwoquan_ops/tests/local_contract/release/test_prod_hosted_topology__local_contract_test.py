from __future__ import annotations

import copy
import hashlib
import inspect
from dataclasses import replace
from types import SimpleNamespace
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.prod.prod_hosted_topology import (
    ProdHostedTopologyError,
    expected_placement_check_names,
    load_access_manifest,
    placement_check_name,
    plan_payload,
    require_release_inventory,
    resolve_plan,
    validate_host_coverage,
)


ROOT = Path(__file__).resolve().parents[4]
SPEC_REF = "specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-002"


def _runtime_evidence(root: Path, plan: list, candidate: str) -> list[dict]:
    """创建最小已渲染物料与只读runtime结果，不触发部署。"""
    runtimes = []
    for placement in plan:
        directory = root / placement.render_name
        directory.mkdir()
        services = list(placement.governed_services)
        digests = {service: "sha256:" + "b" * 64 for service in services}
        provenance = {"candidateDigest": candidate, "configServices": services,
                      "configSources": {key: {"effectiveConfigDigest": value}
                                        for key, value in digests.items()}}
        raw = json.dumps(provenance).encode()
        (directory / "provenance.json").write_bytes(raw)
        runtimes.append({
            "plane": placement.plane, "hostId": placement.host_id,
            "replicaId": placement.replica_id, "instance": placement.instance,
            "host": placement.ssh_host, "account": placement.account,
            "composeRoot": placement.remote_root, "project": placement.project,
            "candidateDigest": candidate, "configDigest": candidate,
            "configFileDigests": digests,
            "provenanceDigest": hashlib.sha256(raw).hexdigest(),
            "configAck": {"status": "ready"}, "exitCode": 0,
            "composeFileExists": True, "envFileExists": True,
            "unit": {"enabled": True, "active": True, "name": placement.systemd_unit},
            "containers": [{"composeService": service, "running": True, "health": "healthy"}
                           for service in placement.governed_services + placement.support_services],
        })
    return runtimes


def _two_host_access() -> dict:
    access = copy.deepcopy(load_access_manifest())
    access["management"]["hosts"].append(
        {
            "id": "prod-host-02",
            "sshHost": "203.0.113.22",
            "planes": ["service", "edge"],
        }
    )
    for instance in ("prevalidate", "gray", "prod"):
        for plane in ("service", "edge"):
            access["deploymentInstances"][instance]["replicas"][plane].append(
                {"id": "r1", "hostId": "prod-host-02"}
            )
    return access


class ProdHostedTopologyContractTest(unittest.TestCase):
    def test_two_hosts_two_replicas_have_isolated_runtime_identities(self) -> None:
        plan = resolve_plan(_two_host_access(), instance="gray")
        require_release_inventory(plan, _two_host_access())
        self.assertEqual(len(plan), 4)
        self.assertEqual({item.host_id for item in plan}, {"prod-host-01", "prod-host-02"})
        for plane in ("service", "edge"):
            replicas = [item for item in plan if item.plane == plane]
            self.assertEqual({item.replica_id for item in replicas}, {"r0", "r1"})
            self.assertEqual({item.replica_count for item in replicas}, {2})
            self.assertEqual(len({item.remote_root for item in replicas}), 2)
            self.assertEqual(len({item.project for item in replicas}), 2)
            self.assertEqual(len({item.systemd_unit for item in replicas}), 2)
        payload = plan_payload(plan)
        self.assertEqual(payload["schema"], "prod-hosted-deployment-plan")
        self.assertFalse(payload["secretMaterialEmbedded"])
        self.assertNotIn("privateKey", json.dumps(payload))

    # spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-002
    def test_repository_inventory_is_complete_for_formal_rollout(self) -> None:
        plan = resolve_plan(load_access_manifest(), instance="prod")
        require_release_inventory(plan, load_access_manifest())

    def test_duplicate_check_cannot_overwrite_failed_receipt(self) -> None:
        plan = resolve_plan(load_access_manifest(), instance="prod")
        checks = [{"name": name, "status": "passed"}
                  for name in expected_placement_check_names(plan)]
        checks.insert(0, {"name": checks[0]["name"], "status": "failed"})
        issues = validate_host_coverage(checks, plan)
        self.assertTrue(any("duplicate" in issue for issue in issues), issues)

    def test_formal_redundancy_rejects_filtered_plane_plan(self) -> None:
        service_only = resolve_plan(
            _two_host_access(),
            instance="prod",
            planes=("service",),
        )
        with self.assertRaisesRegex(
            ProdHostedTopologyError,
            "complete canonical service\\+edge inventory",
        ):
            require_release_inventory(service_only, _two_host_access())

    def test_placement_receipts_use_the_single_current_schema_identity(self) -> None:
        plan = resolve_plan(load_access_manifest(), instance="prod")
        runtimes = [
            {
                "plane": placement.plane,
                "hostId": placement.host_id,
                "replicaId": placement.replica_id,
                "exitCode": 0,
                "composeFileExists": True,
                "envFileExists": True,
                "unit": {"enabled": True, "active": True},
                "containers": [
                    {
                        "name": f"{placement.plane}-{placement.replica_id}",
                        "running": True,
                        "health": "healthy",
                    }
                ],
            }
            for placement in plan
        ]
        with tempfile.TemporaryDirectory() as temporary_directory:
            with patch.object(
                stackctl,
                "_prod_instance_runtime_reports",
                return_value=runtimes,
            ):
                checks = stackctl._prod_hosted_placement_coverage_checks(
                    Path(temporary_directory),
                    stage="100", candidate_digest="sha256:" + "a" * 64,
                    expected_plan=plan,
                )

        receipts = [
            check["placementReceipt"]
            for check in checks
            if "placementReceipt" in check
        ]
        self.assertEqual(len(receipts), len(plan))
        self.assertEqual(
            {receipt["schema"] for receipt in receipts},
            {"prod-hosted-placement-receipt"},
        )

    def test_inventory_rejects_filtered_duplicate_and_drifted_plans(self) -> None:
        access = _two_host_access()
        plan = resolve_plan(access, instance="prod")
        cases = [plan[:2], plan + [plan[0]],
                 [replace(plan[0], ssh_host="203.0.113.99"), *plan[1:]],
                 resolve_plan(access, instance="prod", host_ids=["prod-host-01"])]
        for selected in cases:
            with self.subTest(selected=selected), self.assertRaises(ProdHostedTopologyError):
                require_release_inventory(selected, access)
        single = load_access_manifest()
        changed_endpoint = resolve_plan(single, instance="prod", ssh_host_override="203.0.113.99")
        with self.assertRaises(ProdHostedTopologyError):
            require_release_inventory(changed_endpoint, single)

    def test_manifest_rejects_missing_duplicate_unknown_and_misplaced_inventory(self) -> None:
        for mutation in ("host-id", "endpoint", "replica", "unknown", "empty", "plane", "colocation", "management"):
            access = _two_host_access()
            hosts = access["management"]["hosts"]
            replicas = access["deploymentInstances"]["prod"]["replicas"]
            if mutation == "host-id": hosts[1]["id"] = hosts[0]["id"]
            if mutation == "endpoint": hosts[1]["sshHost"] = hosts[0]["sshHost"]
            if mutation == "replica": replicas["service"][1]["id"] = "r0"
            if mutation == "unknown": replicas["service"][1]["hostId"] = "unknown"
            if mutation == "empty": replicas["service"] = []
            if mutation == "plane": del replicas["edge"]
            if mutation == "colocation": replicas["edge"][1]["id"] = "r2"
            if mutation == "management": access["management"]["sshHost"] = "wrong.invalid"
            with self.subTest(mutation=mutation), self.assertRaises(ProdHostedTopologyError):
                resolve_plan(access, instance="prod")

    def test_strict_runtime_receipts_and_inventory_recheck(self) -> None:
        from quwoquan_ops.cli.commands import prod_plane_reports as reports
        from quwoquan_ops.cli.commands.deploy_prod_finalize import _validate_inventory_before_commit
        candidate = "sha256:" + "a" * 64
        access = load_access_manifest()
        plan = resolve_plan(access, instance="prod")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = _runtime_evidence(root, plan, candidate)
            mutations = ("valid", "missing", "duplicate", "host", "endpoint", "candidate", "config",
                         "bytes", "ack", "failed", "legacy", "inventory")
            for mutation in mutations:
                runtimes = copy.deepcopy(original)
                if mutation == "missing": runtimes.pop()
                if mutation == "duplicate": runtimes.append(copy.deepcopy(runtimes[0]))
                if mutation == "host": runtimes[0]["hostId"] = "wrong"
                if mutation == "endpoint": runtimes[0]["host"] = "wrong.invalid"
                if mutation == "candidate": runtimes[0]["candidateDigest"] = "sha256:" + "c" * 64
                if mutation == "config": runtimes[0]["configDigest"] = "sha256:" + "c" * 64
                if mutation == "bytes": runtimes[0]["configFileDigests"] = {}
                if mutation == "ack": runtimes[0]["configAck"] = {"status": "not_ready"}
                if mutation == "failed": runtimes[0]["unit"]["active"] = False
                if mutation == "legacy": del runtimes[0]["replicaId"]
                current = _two_host_access() if mutation == "inventory" else access
                with self.subTest(mutation=mutation), patch.object(
                    stackctl, "load_prod_hosted_access_manifest", return_value=current,
                ), patch.object(stackctl, "_prod_instance_runtime_reports", return_value=runtimes), patch.object(
                    reports, "deployment_render_dir", side_effect=lambda *a, **kw: root / kw["name"],
                ):
                    checks = stackctl._prod_hosted_placement_coverage_checks(
                        root / mutation, stage="100", candidate_digest=candidate, expected_plan=plan,
                    )
                    self.assertEqual(all(item["exitCode"] == 0 for item in checks), mutation == "valid", checks)
                    scope = {"release_inventory": access, "release_plan": plan,
                             "post_deploy_checks": checks, "rollout_stage": "100",
                             "args": SimpleNamespace(to_candidate_digest=candidate)}
                    if mutation == "valid":
                        _validate_inventory_before_commit(scope)
                        scope["post_deploy_checks"] = checks + [checks[0]]
                        with self.assertRaises(ValueError): _validate_inventory_before_commit(scope)
                    else:
                        with self.assertRaises((ValueError, ProdHostedTopologyError)):
                            _validate_inventory_before_commit(scope)

    def test_multiple_hosts_use_the_same_strict_receipt_algorithm(self) -> None:
        from quwoquan_ops.cli.commands import prod_plane_reports as reports
        access = _two_host_access()
        plan = resolve_plan(access, instance="gray")
        candidate = "sha256:" + "a" * 64
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtimes = _runtime_evidence(root, plan, candidate)
            with patch.object(stackctl, "load_prod_hosted_access_manifest", return_value=access), patch.object(
                stackctl, "_prod_instance_runtime_reports", return_value=runtimes,
            ), patch.object(reports, "deployment_render_dir", side_effect=lambda *a, **kw: root / kw["name"]):
                checks = stackctl._prod_hosted_placement_coverage_checks(
                    root / "checks", stage="canary", candidate_digest=candidate, expected_plan=plan,
                )
                self.assertEqual(len(checks), 4)
                self.assertTrue(all(item["exitCode"] == 0 for item in checks), checks)

    def test_all_effect_entrypoints_enforce_inventory_without_old_alias(self) -> None:
        source = (ROOT / "quwoquan_ops/cli/prod/deploy_to_prod.sh").read_text()
        self.assertIn("plan_args+=(--require-release-inventory)", source)
        self.assertIn("assert_inventory_unchanged\n  deploy_plane", source)
        self.assertIn("assert_inventory_unchanged\nplacement_count=", source)
        self.assertNotIn("require-release-redundancy", source)
        self.assertFalse(hasattr(stackctl, "require_prod_hosted_release_redundancy"))
        finalize = inspect.getsource(stackctl._deploy_prod_hosted_finalize)
        self.assertIn("_validate_inventory_before_commit(scope)", finalize)
        from quwoquan_ops.cli.prod.inspect_prod_plane_runtime import _remote_python
        remote = _remote_python()
        compile(remote, "<prod-readback>", "exec")
        self.assertIn('config_path.read_bytes()', remote)
        self.assertIn('"/readyz/config-convergence"', remote.replace('http://127.0.0.1:18088', ''))

    def test_exit_code_zero_and_conflicting_status_are_not_truthiness_based(self) -> None:
        plan = resolve_plan(load_access_manifest(), instance="prod")
        checks = [{"name": name, "exitCode": 0} for name in expected_placement_check_names(plan)]
        self.assertEqual(validate_host_coverage(checks, plan), [])
        checks[0].update(status="passed", exitCode=1)
        self.assertTrue(validate_host_coverage(checks, plan))

    def test_published_port_replicas_cannot_share_one_host(self) -> None:
        access = _two_host_access()
        for instance in ("prevalidate", "gray", "prod"):
            for plane in ("service", "edge"):
                access["deploymentInstances"][instance]["replicas"][plane][1][
                    "hostId"
                ] = "prod-host-01"
        with self.assertRaisesRegex(
            ProdHostedTopologyError,
            "multiple published-port replicas",
        ):
            resolve_plan(access, instance="prod")

    def test_gray_and_prod_placements_must_match_for_local_router_handoff(self) -> None:
        access = _two_host_access()
        access["deploymentInstances"]["gray"]["replicas"]["service"][1]["id"] = "r2"
        with self.assertRaisesRegex(
            ProdHostedTopologyError,
            "service/edge replicas|gray/prod service replicas",
        ):
            resolve_plan(access, instance="gray")

    def test_stackctl_exposes_read_only_canonical_plan(self) -> None:
        result = subprocess.run(
            [
                "python3",
                "quwoquan_ops/cli/stackctl.py",
                "--output",
                "json",
                "prod-hosted-plan",
                "--deployment-instance",
                "prod",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        plan = payload["deploymentPlan"]
        self.assertEqual(plan["target"], "prod-hosted")
        self.assertEqual(plan["instance"], "prod")
        self.assertFalse(plan["secretMaterialEmbedded"])
        self.assertTrue(
            all(
                placement["remoteRoot"].endswith(
                    f"/instances/prod/{placement['replicaId']}"
                )
                for placement in plan["placements"]
            )
        )

    def test_stackctl_accepts_complete_single_host_inventory(self) -> None:
        result = subprocess.run(
            [
                "python3",
                "quwoquan_ops/cli/stackctl.py",
                "--output",
                "json",
                "prod-hosted-plan",
                "--deployment-instance",
                "prod",
                "--require-release-inventory",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["exitCode"], 0)

    def test_host_coverage_requires_every_placement_passed(self) -> None:
        plan = resolve_plan(_two_host_access(), instance="prod", planes=("service",))
        expected = expected_placement_check_names(plan)
        self.assertEqual(len(expected), 2)
        self.assertEqual(
            placement_check_name(plan[0]),
            "host:prod-host-01:plane:service:replica:r0",
        )
        issues = validate_host_coverage(
            [
                {
                    "name": expected[0],
                    "status": "passed",
                    "receiptDigest": "sha256:" + ("a" * 64),
                }
            ],
            plan,
        )
        self.assertTrue(any("missing host coverage" in item for item in issues))
        complete = [
            {
                "name": name,
                "status": "passed",
                "receiptDigest": "sha256:" + ("b" * 64),
            }
            for name in expected
        ]
        self.assertEqual(validate_host_coverage(complete, plan), [])

    def test_rolling_replica_failure_blocks_coverage_and_rollback_uses_policy(self) -> None:
        plan = resolve_plan(_two_host_access(), instance="prod")
        names = expected_placement_check_names(plan)
        failed_name = placement_check_name(
            next(
                item
                for item in plan
                if item.host_id == "prod-host-02" and item.plane == "edge"
            )
        )
        checks = [
            {
                "name": name,
                "status": "failed" if name == failed_name else "passed",
                "receiptDigest": "sha256:" + ("c" * 64),
            }
            for name in names
        ]
        issues = validate_host_coverage(checks, plan)
        self.assertEqual(
            issues,
            [f"host coverage check not passed: {failed_name} status=failed"],
        )

        # 通过 stackctl 命名空间取真实实现源码：rollout / finalize 已迁往
        # quwoquan_ops/cli/commands/**，只靠 stackctl.py 文本扫描会随再导出失效。
        rollout_source = inspect.getsource(stackctl._command_deploy_with_lock)
        finalize_source = inspect.getsource(stackctl._deploy_prod_hosted_finalize)
        deploy_source = (
            ROOT / "quwoquan_ops/cli/prod/deploy_to_prod.sh"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "production apply failed; stackctl will rollback every plane",
            rollout_source,
        )
        # apply 与 rollback 两条 plane 编排都必须把 PROD_SSH_HOST 留空，
        # 由 access-isolation 策略重新解析完整 host/replica 放置。
        self.assertIn('"PROD_SSH_HOST": ""', rollout_source)
        self.assertIn('"PROD_SSH_HOST": ""', finalize_source)
        self.assertIn(
            "while IFS=$'\\t' read -r plane account compose_root",
            deploy_source,
        )
        self.assertIn('done <<< "$PLANE_PLAN"', deploy_source)
        self.assertIn("set -euo pipefail", deploy_source)


if __name__ == "__main__":
    unittest.main()
