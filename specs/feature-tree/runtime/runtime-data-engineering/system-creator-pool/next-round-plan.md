# system-creator-pool 商用 E2E 规划 v4（2026-07-03）

> 决策：active 试跑池唯一收敛为 `travel_photo_1k_v1`。历史 `travel_batch_100_v1` 与 service 侧 `travel_scale10` 已从 active import 口径退役；小样本仅可作为 data 私有测试 fixture。

## 完成状态

| Sprint | 内容 | 状态 |
|---|---|---|
| S1 | 8 archetype 配额 + live acquire + diversify select（420→120） | done |
| S2 | enrich + persona_rubric + persona_dedup + validate 全量 | done |
| S3 | seed merge → canonical 1200 user_pool overlay + user_scenarios + Go contract | done |
| S4 | 3× content smoke + UAT core shard + commercial go | done（待升级到 dual-view 口径证据） |

## 证据

```bash
pytest quwoquan_data/tests/local_contract/creator_pool/ -q
python3 quwoquan_data/scripts/verify/verify_creator_pool_contract.py
python3 quwoquan_data/scripts/verify/verify_creator_pool_seed_consistency.py
.qwq_output/artifacts/pools/creator/creator_travel_photo_1k_v1_readiness.json  # decision=go
```

## 四支柱商用阈值

见 [`quwoquan_data/docs/creator_pool_pipeline_spec.md`](../../../../quwoquan_data/docs/creator_pool_pipeline_spec.md) 与 `schema/creator/creator_persona_rubric.json`。

## 下一里程碑

- canonical 1200 unique / dual 1k active pool 四环境 importer 继续补 beta/gamma API 证据
- 真实 allowlist RSS / site-supply 外站信号持续增强（博主只做公开风格信号，不复制身份）
