# 四川游玩点全集 — 批次运行记录

## 命名约定

```text
{mode}_{region}_{category}_{quota}_{date}
```

## 当前批次（prod 放量）

| 字段 | 值 |
|------|-----|
| mode | `prod` |
| region | `sichuan` |
| category | `poi` |
| quota | `100e400c` |
| date | `20260608` |

- **batchId**：`prod_sichuan_poi_100e400c_20260608`
- **releaseId**：`旅行__地域__四川省__景区__景区精选__prod_sichuan_poi_100e400c_20260608`
- **fanout planId**：`sichuan_100e_400c_20260608`
- **目标**：100 实体 + 300～500 篇（多角度：攻略/一日游/环线/自驾等，禁止一律环线攻略）
- **工作流**：fanout 21 市州分区 + object_queue + fanout_runner(6 workers) + Ralph + reducer

## 已归档批次（superseded，勿重建）

| batchId | 说明 |
|---------|------|
| `e2e_sichuan_scenic_10e20c_20260608` | 10e20c 试点，runtime 已清零 |
| `e2e_sichuan_10e20c_20260608` | 更早试点 |

## 内容配额

| 类型 | 配额 |
|------|------|
| 单实体文 (entity) | 100 |
| 线路/攻略文 (route) | 300（上限 400） |

## 角度多样性 SLO

- `环线攻略` publishAngle 占比 ≤ 40%
- `攻略`（含一日游/周边）+ 周末短途类 ≥ 30%

## writingIntent 分布目标

planning_consultation ~40% | decision_experience ~35% | post_trip_journal ~25%

## SLO 记录（待真实重产）

> 此前 `fanout_workflow_driver.py` 脚本拼接的伪造产物（100 主页 + 271 文章 + 伪造来源/配图）已全部废弃清理（runtime batches/entities 与 publish posts/entities 已清空，`publish/tags` 5197 个 `_definition.json` 保留未变）。
>
> 重产须经「CLI 准备上下文 → cursor-sdk 云端 orchestrator/leaf subagent 真实检索+真创作 → CLI 校验」三段式，下列 SLO 待真实产物实测后回填。

| 指标 | 阈值 | 实测 |
|------|------|------|
| 首过 approved 率 | ≥ 70% | 待实测 |
| 图文完备率 | 100% | 待实测 |
| simhash P95 | ≤ 0.80 | 待实测 |
| 实体 page.md | 100 | 待实测 |
| 文章 article.md | 300～500 | 待实测 |
| publish/tags `_definition.json` | 与清理前一致 | 5197（未变） |
| 角度多样性 | 环线≤40% / 攻略类≥30% | 待实测 |
| goldenset 校准 | PASS | 待实测 |

**结构**：保持 by-partition（21 task / 1 共享 `batchId` = `fanout_sichuan_100e_400c_20260608`），最终经 `task rollup` + `ship --copy-entities` 聚合为单一 `release/{releaseId}`。
