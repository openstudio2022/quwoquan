# system-creator-pool 商用 E2E 规划 v3（2026-06-27）

> 决策：**原地刷新** `travel_batch_100_v1`（不变 batchId）；四支柱未达标 → `creator-scale-readiness --mode commercial` **no_go**。

## 完成状态

| Sprint | 内容 | 状态 |
|---|---|---|
| S1 | 8 archetype 配额 + live acquire + diversify select（350→100） | done |
| S2 | enrich + persona_rubric + persona_dedup + validate 全量 | done |
| S3 | seed merge → user_pool overlay + user_scenarios + Go contract | done |
| S4 | 3× content smoke + UAT 20 人 + commercial go | done |

## 证据

```bash
pytest quwoquan_data/tests/local_contract/creator_pool/ -q
python3 quwoquan_data/scripts/verify/verify_creator_pool_contract.py
python3 quwoquan_data/scripts/verify/verify_creator_pool_seed_consistency.py
artifacts/creator_batch100_commercial_readiness.json  # decision=go
```

## 四支柱商用阈值

见 [`quwoquan_data/docs/creator_pool_pipeline_spec.md`](../../../../quwoquan_data/docs/creator_pool_pipeline_spec.md) 与 `schema/creator/creator_persona_rubric.json`。

## 下一里程碑

- Batch-1k shard 试跑（metadata import，`CR-creator-pool-metadata-scale.yaml`）
- 真实 allowlist RSS / site-supply 外站信号（当前 live 为 derivative 合成信号池）
