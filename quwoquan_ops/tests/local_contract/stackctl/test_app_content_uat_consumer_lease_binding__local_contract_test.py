"""聚合 UAT 回执与 Patrol 报告的 consumer lease 字段位置必须一致。

`read_only_user_availability` 的 `device_bound` 层判据是「verify 观察到的活跃
lease 都出现在聚合回执的 `consumerLeaseIds` 里」。Patrol 报告把 lease 写成
`runs[].evidence.consumerLease` 结构化对象，而聚合器从 `runs[].consumerLeaseId`
顶层标量收集——两处不对齐时该数组恒为空，判定不是「lease 无效」而是根本没读到，
且失败信息看起来像设备侧问题，排查方向会被带偏。

direct-flutter-run 分支一直填的是顶层标量键，因此对齐方向是让 Patrol 分支填同一
个键，而不是让聚合器改成双读两种位置。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SOURCE = ROOT / "quwoquan_ops" / "cli" / "commands" / "app_preflight_uat.py"
CONSUMER = ROOT / "quwoquan_ops" / "cli" / "lib" / "read_only_user_availability.py"


def test_patrol_run_payload_carries_top_level_consumer_lease_id() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    assert 'run_payload["consumerLeaseId"] = patrol_lease_id' in source
    assert 'patrol_evidence.get("consumerLease")' in source


def test_aggregate_receipt_collects_lease_ids_from_a_single_key() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    collector = source[source.index('"consumerLeaseIds": sorted(') :][:400]
    assert 'item.get("consumerLeaseId")' in collector
    # 聚合器只认一个位置：出现第二种读法就意味着字段有了两处真相源。
    assert "consumerLease" not in collector.replace("consumerLeaseId", "")


def test_device_bound_layer_reads_the_same_receipt_key() -> None:
    consumer = CONSUMER.read_text(encoding="utf-8")
    assert 'payload.get("consumerLeaseIds")' in consumer
