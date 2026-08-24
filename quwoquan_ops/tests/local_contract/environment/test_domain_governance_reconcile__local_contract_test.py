from __future__ import annotations

import unittest
from unittest import mock

from quwoquan_ops.cli import domain_governance
from quwoquan_ops.cli.lib import dns_provider


class _RecordingProvider:
    def __init__(self, existing: list[dict[str, object]]) -> None:
        self.existing = existing
        self.created: list[dict[str, object]] = []
        self.updated: list[tuple[str, dict[str, object]]] = []
        self.deleted: list[str] = []

    def list_records(self, *, name: str, record_type: str) -> list[dict[str, object]]:
        return [
            item
            for item in self.existing
            if str(item["name"]) == name and str(item["type"]) == record_type
        ]

    def create_record(self, record: dict[str, object]) -> str:
        self.created.append(record)
        return f"new-{len(self.created)}"

    def update_record(self, provider_record_id: str, record: dict[str, object]) -> None:
        self.updated.append((provider_record_id, record))

    def delete_record(self, provider_record_id: str) -> None:
        self.deleted.append(provider_record_id)


class DnsApplyReconciliationLocalContractTest(unittest.TestCase):
    """收敛只作用于「本次有期望」的分组；期望缺席不得被解释为要求清空。"""

    def _apply_with(
        self,
        provider: _RecordingProvider,
        *,
        prod_edge: str = "",
        allow_production_mutation: bool = False,
    ) -> dict[str, object]:
        # zone 标识由策略的 registrableDomain 派生，不是部署时输入。
        environment = {"QWQ_DNS_PROVISIONING_API_TOKEN": "id:secret"}
        if prod_edge:
            environment["QWQ_PROD_EDGE_IPV4"] = prod_edge
        with (
            mock.patch.dict(
                domain_governance.os.environ, environment, clear=True
            ),
            mock.patch.object(
                domain_governance, "build_provider", return_value=provider
            ),
        ):
            return domain_governance.apply_dns_records(
                allow_production_mutation=allow_production_mutation
            )

    def test_absent_prod_plan_never_deletes_existing_prod_records(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（缺席不得被解释为要求删除）"""
        provider = _RecordingProvider(
            [
                {
                    "type": "A",
                    "name": "quwoquan.com",
                    "content": "1.2.3.4",
                    "ttl": 600,
                    "providerRecordId": "live-apex",
                }
            ]
        )
        receipt = self._apply_with(provider)
        self.assertEqual(provider.deleted, [])
        self.assertNotIn(
            "live-apex", [record_id for record_id, _ in provider.updated]
        )
        self.assertEqual(
            [item["scope"] for item in receipt["pending"]], ["prod"]
        )

    def test_matching_record_with_correct_ttl_is_left_untouched(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（稳态记录不产生 provider 写入）"""
        provider = _RecordingProvider(
            [
                {
                    "type": "A",
                    "name": "alpha.quwoquan.com",
                    "content": "127.0.0.1",
                    "ttl": 600,
                    "providerRecordId": "live-alpha",
                }
            ]
        )
        receipt = self._apply_with(provider)
        self.assertEqual(provider.deleted, [])
        actions = {
            (item["type"], item["name"]): item["action"]
            for item in receipt["changes"]
        }
        self.assertEqual(actions[("A", "alpha.quwoquan.com")], "unchanged")

    def test_stale_value_in_a_planned_group_is_reused_not_duplicated(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（同组内旧值就地纠正不重复下发）"""
        provider = _RecordingProvider(
            [
                {
                    "type": "A",
                    "name": "alpha.quwoquan.com",
                    "content": "203.0.113.7",
                    "ttl": 600,
                    "providerRecordId": "live-stale",
                }
            ]
        )
        self._apply_with(provider)
        self.assertEqual(
            [record_id for record_id, _ in provider.updated].count("live-stale"), 1
        )
        self.assertEqual(provider.deleted, [])

    def test_overwriting_an_existing_production_record_needs_confirmation(
        self,
    ) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（破坏性生产动作缺确认即 fail closed）"""
        provider = _RecordingProvider(
            [
                {
                    "providerRecordId": "manual-apex",
                    "name": "quwoquan.com",
                    "type": "A",
                    "content": "9.9.9.9",
                    "ttl": 600,
                }
            ]
        )
        with self.assertRaisesRegex(
            domain_governance.DomainGovernanceError, "destructive"
        ):
            self._apply_with(provider, prod_edge="1.2.3.4")
        self.assertEqual(provider.created, [])
        self.assertEqual(provider.updated, [])
        self.assertEqual(provider.deleted, [])

    def test_confirmed_apply_converges_the_manual_production_record(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（确认后收敛控制台人工记录）"""
        provider = _RecordingProvider(
            [
                {
                    "providerRecordId": "manual-apex",
                    "name": "quwoquan.com",
                    "type": "A",
                    "content": "9.9.9.9",
                    "ttl": 600,
                }
            ]
        )
        receipt = self._apply_with(
            provider, prod_edge="1.2.3.4", allow_production_mutation=True
        )
        self.assertEqual(
            [record["content"] for _, record in provider.updated], ["1.2.3.4"]
        )
        self.assertTrue(
            any(
                change["name"] == "quwoquan.com" and change["action"] == "updated"
                for change in receipt["changes"]
            ),
            receipt["changes"],
        )

    def test_first_time_production_records_are_not_destructive(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（首次下发不属于破坏性动作）"""
        provider = _RecordingProvider([])
        receipt = self._apply_with(provider, prod_edge="1.2.3.4")
        created = {record["name"] for record in provider.created}
        self.assertIn("quwoquan.com", created)
        self.assertIn("www.quwoquan.com", created)
        self.assertEqual(provider.deleted, [])
        self.assertTrue(
            all(
                change["action"] in {"created", "unchanged"}
                for change in receipt["changes"]
            ),
            receipt["changes"],
        )

    def test_apply_requires_the_dedicated_provisioning_credential(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（provisioning 凭据缺失即 fail closed）"""
        with mock.patch.dict(domain_governance.os.environ, {}, clear=True):
            with self.assertRaisesRegex(
                domain_governance.DomainGovernanceError,
                "QWQ_DNS_PROVISIONING_API_TOKEN",
            ):
                domain_governance.apply_dns_records()

    def test_third_party_verification_txt_is_never_taken_over_or_removed(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（收敛不触碰计划外记录）"""
        foreign = {
            "type": "TXT",
            "name": "quwoquan.com",
            "content": "quwoquan-site-verification=abc123",
            "ttl": 600,
            "providerRecordId": "icp-token",
        }
        provider = _RecordingProvider([foreign])
        receipt = self._apply_with(
            provider, prod_edge="1.2.3.4", allow_production_mutation=True
        )
        self.assertEqual(provider.deleted, [])
        self.assertNotIn(
            "icp-token", [record_id for record_id, _ in provider.updated]
        )
        self.assertIn(
            {
                "type": "TXT",
                "name": "quwoquan.com",
                "value": "quwoquan-site-verification=abc123",
            },
            receipt["observedUnmanaged"],
        )

    def test_our_own_spf_record_is_still_converged_in_a_shared_group(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（自有 TXT 仍单轨收敛）"""
        provider = _RecordingProvider(
            [
                {
                    "type": "TXT",
                    "name": "quwoquan.com",
                    "content": "v=spf1 include:legacy.example -all",
                    "ttl": 3600,
                    "providerRecordId": "old-spf",
                },
                {
                    "type": "TXT",
                    "name": "quwoquan.com",
                    "content": "google-site-verification=zzz",
                    "ttl": 3600,
                    "providerRecordId": "google-token",
                },
            ]
        )
        self._apply_with(
            provider, prod_edge="1.2.3.4", allow_production_mutation=True
        )
        updated = {record_id: record for record_id, record in provider.updated}
        self.assertIn("old-spf", updated)
        self.assertEqual(updated["old-spf"]["content"], "v=spf1 -all")
        self.assertNotIn("google-token", updated)
        self.assertEqual(provider.deleted, [])

    def test_already_correct_caa_records_are_not_rewritten(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（收敛幂等，稳态不写）"""
        policy = domain_governance._policy()
        prod_zone = next(
            zone
            for zone in domain_governance.dns_zones()
            if str(zone.get("scope")) == "prod"
        )
        live = [
            {
                "type": "CAA",
                "name": "quwoquan.com",
                "content": dns_provider.caa_value(entry),
                "ttl": 3600,
                "providerRecordId": f"caa-{index}",
            }
            for index, entry in enumerate(
                domain_governance.caa_profile(prod_zone, policy)
            )
        ]
        provider = _RecordingProvider(live)
        receipt = self._apply_with(
            provider, prod_edge="1.2.3.4", allow_production_mutation=True
        )
        self.assertEqual(
            [record_id for record_id, _ in provider.updated
             if record_id.startswith("caa-")],
            [],
        )
        self.assertEqual(provider.deleted, [])
        caa_actions = {
            change["action"]
            for change in receipt["changes"]
            if change["type"] == "CAA" and change["name"] == "quwoquan.com"
        }
        self.assertEqual(caa_actions, {"unchanged"})

    def test_extra_address_in_an_owned_group_is_removed(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（地址组由计划完全拥有）"""
        provider = _RecordingProvider(
            [
                {
                    "type": "A",
                    "name": "quwoquan.com",
                    "content": "1.2.3.4",
                    "ttl": 600,
                    "providerRecordId": "correct",
                },
                {
                    "type": "A",
                    "name": "quwoquan.com",
                    "content": "9.9.9.9",
                    "ttl": 600,
                    "providerRecordId": "rogue",
                },
            ]
        )
        receipt = self._apply_with(
            provider, prod_edge="1.2.3.4", allow_production_mutation=True
        )
        self.assertEqual(provider.deleted, ["rogue"])
        self.assertIn(
            "removed",
            {
                change["action"]
                for change in receipt["changes"]
                if change["name"] == "quwoquan.com" and change["type"] == "A"
            },
        )

    def test_ttl_only_drift_is_retuned_in_place(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（TTL 漂移就地纠正）"""
        provider = _RecordingProvider(
            [
                {
                    "type": "A",
                    "name": "alpha.quwoquan.com",
                    "content": "127.0.0.1",
                    "ttl": 60,
                    "providerRecordId": "low-ttl",
                }
            ]
        )
        receipt = self._apply_with(provider)
        updated = {record_id: record for record_id, record in provider.updated}
        self.assertIn("low-ttl", updated)
        self.assertGreaterEqual(int(updated["low-ttl"]["ttl"]), 600)
        self.assertEqual(provider.deleted, [])
        self.assertIn(
            "retuned",
            {
                change["action"]
                for change in receipt["changes"]
                if change["name"] == "alpha.quwoquan.com"
            },
        )



if __name__ == "__main__":
    unittest.main()
