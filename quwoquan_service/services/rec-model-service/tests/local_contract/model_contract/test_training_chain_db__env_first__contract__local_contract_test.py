"""N0-5 契约：CI 训练链库统一 + replay 冻结集物化。

历史断裂：workflow 只在 join 步骤传 --db（quwoquan_content_training），
train/evaluate/replay 落脚本默认 quwoquan_content —— join 写 A 库、训练读 B 库，
train 永远训不到新样本、promote 必报 No staged model。

契约（防回归）：
 1. 五个训练链脚本的 --db 默认值必须消费 DB 环境变量（env-first）；
 2. replay freeze 必须物化完整样本快照（rec_replay_samples），
    不再只存 sampleIds（sample_joiner --clean 会物理摧毁 id 引用）；
 3. train_multiobjective 必须把子模型 artifact uri 写入 fusion config
    （serving 侧按 model_artifact_uris 拉子模型，否则恒回退 rule）。
"""

from __future__ import annotations

import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from training_sample_policy import filter_point_in_time_rows
from sample_joiner import build_training_samples

TRAINING_CHAIN_SCRIPTS = [
    "sample_joiner.py",
    "train.py",
    "train_multiobjective.py",
    "evaluate.py",
    "replay_dataset.py",
]

ENV_FIRST_DB_PATTERN = re.compile(
    r"add_argument\(\s*\"--db\",\s*default=os\.environ\.get\(\s*\"DB\""
)


def test_training_chain_scripts_resolve_db_env_first():
    for name in TRAINING_CHAIN_SCRIPTS:
        src = (SCRIPTS_DIR / name).read_text(encoding="utf-8")
        assert ENV_FIRST_DB_PATTERN.search(src), (
            f"{name}: --db 默认值必须是 os.environ.get('DB', ...)（env-first），"
            "否则 CI 的 DB env 不生效、训练链再次读写分裂"
        )


def test_replay_freeze_materializes_sample_snapshots():
    src = (SCRIPTS_DIR / "replay_dataset.py").read_text(encoding="utf-8")
    assert "rec_replay_samples" in src, (
        "replay freeze 必须物化快照到 rec_replay_samples"
    )
    assert '"sampleIds"' not in src, (
        "冻结集禁止回退为只存 sampleIds（--clean 会物理摧毁引用）"
    )
    assert "sourceSampleId" in src, "快照文档必须保留源样本 id 以便追溯"


def test_evaluate_replay_reads_materialized_snapshot():
    src = (SCRIPTS_DIR / "evaluate.py").read_text(encoding="utf-8")
    assert "snapshotCollection" in src or "rec_replay_samples" in src, (
        "evaluate --replay-dataset 必须从物化快照读取，"
        "不得再按 sampleIds 回查 rec_training_samples"
    )


def test_multiobjective_uploads_sub_model_artifacts():
    src = (SCRIPTS_DIR / "train_multiobjective.py").read_text(encoding="utf-8")
    assert "model_artifact_uris" in src, (
        "fusion config 必须携带子模型 artifact uri（serving 拉取入口）"
    )
    assert "sub_model_uris" in src, "全部子模型必须逐个上传 artifact"


def test_serving_consumes_sub_model_artifact_uris():
    scorer = (
        SCRIPTS_DIR.parent / "models" / "multiobjective_scorer.py"
    ).read_text(encoding="utf-8")
    assert "model_artifact_uris" in scorer, (
        "serving 侧必须消费 model_artifact_uris 按需下载子模型，"
        "否则远端部署恒回退 rule"
    )


def test_training_consumes_feature_lag_seconds_pit_filter():
    """N3-3 PIT 泄漏防护：训练必须按 featureLagSeconds 过滤时间旅行样本。"""
    for name in ("train.py", "train_multiobjective.py"):
        src = (SCRIPTS_DIR / name).read_text(encoding="utf-8")
        assert "max_feature_lag_seconds" in src, (
            f"{name}: 必须提供 --max-feature-lag-seconds 并过滤超阈值样本"
        )
        assert "featureLagSeconds" in src, (
            f"{name}: 必须消费 featureLagSeconds（PIT 泄漏防护）"
        )
        assert "filter_point_in_time_rows" in src, (
            f"{name}: 必须复用统一 PIT 样本准入策略，禁止训练入口各自复制过滤逻辑"
        )


def test_point_in_time_filter_is_fail_closed_and_boundary_safe():
    rows = [
        {"id": "zero", "featureLagSeconds": 0},
        {"id": "inside", "featureLagSeconds": 9.5},
        {"id": "boundary", "featureLagSeconds": 10},
        {"id": "missing"},
        {"id": "boolean", "featureLagSeconds": True},
        {"id": "text", "featureLagSeconds": "9"},
        {"id": "negative", "featureLagSeconds": -0.1},
        {"id": "over", "featureLagSeconds": 10.1},
        {"id": "nan", "featureLagSeconds": math.nan},
        {"id": "infinite", "featureLagSeconds": math.inf},
    ]

    accepted, dropped = filter_point_in_time_rows(rows, 10)

    assert [row["id"] for row in accepted] == ["zero", "inside", "boundary"]
    assert dropped == 7


@pytest.mark.parametrize("invalid_threshold", [-1, math.nan, math.inf, True, "10"])
def test_point_in_time_filter_rejects_invalid_threshold(invalid_threshold):
    with pytest.raises(ValueError):
        filter_point_in_time_rows([], invalid_threshold)


def test_sample_joiner_uses_request_scoped_immutable_online_snapshots():
    occurred_at = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
    snapshot_at = datetime(2026, 7, 19, 23, 0, tzinfo=timezone.utc)
    events = []
    for request_id, marker in (("frq_1", 1), ("frq_2", 2)):
        events.extend([
            {
                "eventType": "rec_impression",
                "userId": "user-1",
                "targetId": "post-1",
                "occurredAt": occurred_at,
                "labels": {"contentType": "image"},
                "context": {
                    "feedRequestId": request_id,
                    "featureSnapshotAt": snapshot_at,
                    "userFeatureSnapshot": {"totalLikes": marker},
                    "itemFeatureSnapshot": {
                        "contentType": "image",
                        "viewCount": marker,
                    },
                },
            },
            {
                "eventType": "rec_engagement",
                "userId": "user-1",
                "targetId": "post-1",
                "occurredAt": occurred_at,
                "labels": {"action": "click"},
                "context": {
                    "feedRequestId": request_id,
                    "duration": marker,
                },
            },
        ])

    docs, rejected_identity, rejected_snapshot = build_training_samples(
        events,
        "content_feed",
    )

    assert rejected_identity == 0
    assert rejected_snapshot == 0
    assert [doc["requestId"] for doc in docs] == ["frq_1", "frq_2"]
    assert [doc["userFeatures"]["totalLikes"] for doc in docs] == [1, 2]
    assert [doc["itemFeatures"]["viewCount"] for doc in docs] == [1, 2]
    assert all(doc["labels"]["click"] == 1.0 for doc in docs)
    assert all(doc["contextFeatures"]["requestHour"] == 23 for doc in docs)
    assert all(doc["contextFeatures"]["requestDayOfWeek"] == 6 for doc in docs)
    assert all(doc["featureLagSeconds"] == 13 * 60 * 60 for doc in docs)


def test_sample_joiner_preserves_future_snapshot_as_invalid_pit_lag():
    impression_at = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
    future_snapshot_at = datetime(2026, 7, 20, 12, 0, 1, tzinfo=timezone.utc)
    events = [{
        "eventType": "rec_impression",
        "userId": "user-future-snapshot",
        "targetId": "post-future-snapshot",
        "occurredAt": impression_at,
        "context": {
            "feedRequestId": "frq_future_snapshot",
            "featureSnapshotAt": future_snapshot_at,
            "userFeatureSnapshot": {},
            "itemFeatureSnapshot": {"contentType": "image"},
        },
    }]

    docs, rejected_identity, rejected_snapshot = build_training_samples(
        events,
        "content_feed",
    )

    assert rejected_identity == 0
    assert rejected_snapshot == 0
    assert docs[0]["featureLagSeconds"] == -1.0
    accepted, dropped = filter_point_in_time_rows(docs, 24 * 60 * 60)
    assert accepted == []
    assert dropped == 1


def test_sample_joiner_fails_closed_without_identity_or_snapshot():
    occurred_at = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
    events = [
        {
            "eventType": "rec_impression",
            "userId": "user-1",
            "targetId": "post-missing-request",
            "occurredAt": occurred_at,
            "context": {},
        },
        {
            "eventType": "rec_impression",
            "userId": "user-1",
            "targetId": "post-missing-snapshot",
            "occurredAt": occurred_at,
            "context": {"feedRequestId": "frq_missing_snapshot"},
        },
    ]

    docs, rejected_identity, rejected_snapshot = build_training_samples(
        events,
        "content_feed",
    )

    assert docs == []
    assert rejected_identity == 1
    assert rejected_snapshot == 1


def test_skewed_features_stay_retired():
    """N3-3 特征偏斜收口：bodyLength/aspectRatio/hasCover 在线不可得，
    训练/serving 双侧必须保持退役（重新启用前先补召回投影 + registry）。"""
    extractor_files = (
        SCRIPTS_DIR / "train.py",
        SCRIPTS_DIR / "train_multiobjective.py",
        SCRIPTS_DIR / "train_embedding.py",
        SCRIPTS_DIR.parent / "models" / "content_feed.py",
        SCRIPTS_DIR.parent / "features" / "transformer.py",
    )
    for path in extractor_files:
        src = path.read_text(encoding="utf-8")
        for feature in ('"bodyLength",', '"aspectRatio",', 'get("hasCover")'):
            assert feature not in src, (
                f"{path.name}: 退役特征 {feature} 回潮——在线召回投影不携带该字段，"
                "启用前先在 ContentCandidate/召回投影补齐并更新 feature_registry"
            )
        assert '"publishHour"' in src or "publishHour" in src, (
            f"{path.name}: publishHour 已在线补齐（Go 派生下发），不得移除"
        )

    for path in (
        SCRIPTS_DIR / "sample_joiner.py",
        SCRIPTS_DIR / "generate_seed_data.py",
    ):
        src = path.read_text(encoding="utf-8")
        for feature in ("bodyLength", "aspectRatio", "hasCover"):
            assert f'"{feature}":' not in src, (
                f"{path.name}: 不得继续生成已退役特征 {feature}，"
                "否则 dry-run/训练样本与线上候选契约不再同构"
            )
