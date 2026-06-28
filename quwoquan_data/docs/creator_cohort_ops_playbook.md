# Creator Cohort 运营 Playbook

## 指标

| 指标 | 说明 | 数据源 |
|---|---|---|
| cohort_active_rate | 活跃创作者占比 | creator_rollup_report + user API |
| publish_cadence_adherence | 实际发文 vs publishCadence | content_supply authorPool |
| quality_score_p50 | 创作者质量分中位数 | CreatorBundle.operations.qualityScore |
| fatigue_throttle_count | 被限流创作者数 | operations.status=throttled |

## content_supply 对接

- `authorPool.profiles[]` 读取 `templates/creator_profiles/travel/{batchId}/*.creator.yaml`
- `match_creator` 必须使用同一 `creatorProfileId` / `authorId` 命名空间

## 放量

1. Scale-10 go → Scale-100
2. Scale-100 go → Batch-1k shard（每 shard 100，10 shard 并行）
3. 垂类复制：campus / photography 各先 10→100

## 千级/万级 shard 模板

```bash
for shard in $(seq -w 1 10); do
  qwq-data governance creator-pool workflow run \
    --vertical travel --batch travel_batch_1k_v1_shard_${shard} \
    --target 100 --through seed --env beta
done
```
