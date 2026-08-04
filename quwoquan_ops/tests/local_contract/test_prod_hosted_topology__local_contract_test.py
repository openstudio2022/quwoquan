from __future__ import annotations

import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.prod.prod_hosted_topology import (
    ProdHostedTopologyError,
    load_access_manifest,
    plan_payload,
    resolve_plan,
)


ROOT = Path(__file__).resolve().parents[3]


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
                    stage="full",
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

    def test_host_coverage_requires_every_placement_passed(self) -> None:
        from quwoquan_ops.cli.prod.prod_hosted_topology import (
            expected_placement_check_names,
            placement_check_name,
            validate_host_coverage,
        )

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


if __name__ == "__main__":
    unittest.main()
