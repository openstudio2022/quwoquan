# 站点维度内容供给提示词（携程 / Pinterest · 百 / 千 / 万级）

本文件是**站点维度**端到端内容供给的可执行提示词，面向顶层治理 / 编排 Agent（L0/L1），由其分解为执行子 Agent（L2）任务。配套蓝图见 [`content_supply_commercialization_plan.md`](content_supply_commercialization_plan.md)。

> 命令前缀 `qwq-data` = `python3 quwoquan_data/scripts/cli.py`。所有命令在仓库根目录执行。

---

## 0. 平台铁律（每档都必须遵守，禁止放宽）

1. **只产作品，不产随记**：产出仅限实体主页 / 图片作品 / 文章作品。任何被 `WorksClassifier` 判为 `moment` / `abandoned` 的候选不进 `content_plan`。视频作品当前后置。
2. **作品门前置**：站点维度在 `site-supply score`（`build_site_score_packet`）做全站分类入库。真实抓取候选必须先过作品门，moment/abandoned 加 blocker、不 `productionEligible`；不在 score 阶段消耗 L2 创作 token。
3. **版权诚实（站点维度最关键）**：携程、Pinterest 的内容**绝大多数不可直接发布**。逐资产必须具备 `license / credit / sourceUrl / termsUrl / usageScope`；缺一即 `rights_blocked`，只能 discovery/reference，不进发布候选。平台发现图≠发布图。
4. **受控试跑 vs 真实授权**：`controlledTrial.allowed=true` 的站点只可做受控 DAG/并发/门禁验证，此时 `validationOnly=true`、`rawFetchAllowed=false`、`publishableAssetsAllowed=false`，候选仅用于 `content_plan` handoff 结构验证，**不代表真实抓取或发布授权**。
5. **准出认文件不认口头**：每档必须产出站点漏斗 `rollup` + `TokenLedger` + release/import + 搜索可见 + 推荐反馈证据；CLI 返回 done ≠ 准出，必须读 gate 报告。
6. **失败隔离不拖批**：单候选失败进 `repair-fetch` 或 dead-letter，不阻塞同批其它候选。
7. **数量口径**：目标数量 = 实体主页 + 作品总数**相加**。

---

## 1. 站点事实速查

| 站点 | site-id | 内容体裁 | 版权口径 | 现实产能定位 |
| --- | --- | --- | --- | --- |
| 携程攻略 | `ctrip` | 游记 / 攻略（文章 lane 为主，图片需逐图授权） | `travelogue`；多为 `factual_reference_only`，发布需独立表达 + 逐资产授权 | 文章作品事实互证源；可受控试跑验证管线；真实发布受授权约束 |
| Pinterest | `pinterest` | 视觉灵感（图片 lane） | `editorial_reference_only`；发布必须逐图明确授权或开放许可 | 图片 discovery / 审美参考；真实可发布资产极少，主要做受控试跑 + 自有/授权图库补充 |

> 结论：站点维度的**真实可发布产能**受版权强约束。百/千/万级提示词分两种执行模式：
> - **受控试跑模式**（验证管线规模能力）：`--admission-mode controlled_trial`，全量数量可达标，但产物为结构验证，不发布站点素材。
> - **真实授权模式**（真实产能）：只对逐资产授权充分的候选放行，数量以实际授权为上限，不足部分由自有/CC/公版图库与事实改写文章补齐。

---

## 2. 百级（~100：实体主页 + 作品相加）

**目标**：跑通站点维度全链路正确性、作品门准确率、证据闭环。

**分配建议**（携程为例）：实体主页 30 + 文章作品 60 + 图片作品 10 = 100。

**编排骨架**：

```bash
SITE=ctrip; BATCH=site-ctrip-h100; TASK=site_ctrip_h100; TBATCH=b1
# 1) 站点准入与 frontier（受控试跑或真实，按授权选择 admission-mode）
qwq-data site-supply plan --site-id $SITE --batch $BATCH --vertical travel \
  --daily-target 100 --admission-mode controlled_trial --write
# 2) 候选注入（真实抓取或受控合成），逐候选声明 lane/title/text/assets(含license)
qwq-data site-supply candidate --site-id $SITE --batch $BATCH \
  --url <url> --lane article --title "<title>" --text "<正文>" \
  --assets "<assetUrl>|<license>|<credit>|<termsUrl>|<usageScope>|<modelReleaseStatus>" --write
# 3) 作品门评分（全站分类入库，moment/abandoned 自动阻断）
qwq-data site-supply score --site-id $SITE --batch $BATCH --candidate-ref <ref> --write
# 4) 合格候选映射 content_plan handoff
qwq-data site-supply map --site-id $SITE --batch $BATCH --candidate-ref <ref> --write
# 5) 物化为标准 content_plan batch
qwq-data site-supply content-plan --site-id $SITE --batch $BATCH \
  --task $TASK --target-batch $TBATCH --limit 100 --write
# 6) 进入统一生产主线（compose-brief 再过一次作品门 → Agent 创作 → review → materialize）
qwq-data produce --task $TASK --batch $TBATCH ...
# 7) 站点漏斗与准出证据
qwq-data site-supply rollup --site-id $SITE --batch $BATCH --objects-per-hour <n> --write
qwq-data site-supply quality-report --site-id $SITE --batch $BATCH --write
```

**准出判据（全绿才算通过）**：
- 作品门零硬门漏判：人工抽检 ≥10 个 verdict，决策与正文一致。
- moment/abandoned 候选确实未进 `content_plan`。
- 每个产出对象有完整证据 packet（evidence / brief / review / provenance / token ledger）。
- `rollup` 漏斗各级数量自洽；单候选失败被隔离。

**放量阻断**：任一硬门漏判、证据缺失或漏斗不自洽 → 停在百级，修复后重跑，不进千级。

---

## 3. 千级（~1000）

**目标**：并发调度、per-lane 限流背压、去重、成本线性。

**分配建议**：实体主页 250 + 文章作品 600 + 图片作品 150 = 1000（按授权实际可调）。

**与百级差异**：
- `site-supply plan` 用 `--queue-backend reliabletask`，按 lane 设并发与限流。
- 批量候选注入 + 批量 `score`/`map`；用 `--refs` 批量物化。
- 重点观测：HTTP 429/403、probe page、空抽取、重复、dead-letter 计数（`rollup` 参数）。

```bash
qwq-data site-supply plan --site-id $SITE --batch $BATCH --vertical travel \
  --daily-target 1000 --queue-backend reliabletask --admission-mode controlled_trial --write
# ... 批量 candidate/score/map ...
qwq-data site-supply content-plan --site-id $SITE --batch $BATCH \
  --task $TASK --target-batch $TBATCH --limit 1000 --write
qwq-data site-supply rollup --site-id $SITE --batch $BATCH \
  --objects-per-hour <n> --first-pass-rate <r> --token-ledger-count <c> \
  --http-429-count <..> --http-403-count <..> --duplicate-count <..> --dead-letter-count <..> --write
```

**准出判据**：
- 首过率（first-pass-rate）稳定，无队列雪崩。
- `unitPassedCost`（TokenLedger 派生）可预测、随量线性。
- 限流生效：429/403 在阈值内，背压未导致丢单。
- 去重命中合理，dead-letter 可复盘。

**放量阻断**：成本非线性、队列雪崩、限流失效或去重异常 → 停在千级，补 Phase 0.5 工程地基，不进万级。

---

## 4. 万级（~10000）

**目标**：崩溃恢复、故障域隔离、放量节奏、监控分位数、下游闭环。

**分配建议**：实体主页 2500 + 文章作品 6000 + 图片作品 1500 = 10000（真实授权模式下以实际授权为上限）。

**与千级差异**：
- 分多个 site batch 滚动放量，按 SLO 分位数（非算术均值）监控通过率 / 延迟。
- 崩溃中断后用 stage result + objectKey 幂等断点续跑。
- 下游证据汇总：

```bash
qwq-data site-supply downstream-evidence --site-id $SITE --batch $BATCH \
  --task $TASK --target-batch $TBATCH --env gamma --write
qwq-data site-supply rerollup --site-id $SITE --batch $BATCH --objects-per-hour <n> --write
```

**准出判据**：
- 断点续跑成功，无重复产出（幂等）。
- 单 lane / 单站故障被隔离，不拖垮全批。
- 下游链路闭合：content_plan → ship/import → search 可见 → 推荐反馈 ready。
- SLO 达标（见 `content_ops_slo.md`）。

**放量阻断**：恢复失败、故障扩散、下游断点或 SLO 不达标 → 回退到千级规模，修复后再放大。

---

## 5. 真实授权模式补充

当以真实发布为目标（非受控试跑）时，额外强制：
- 每个候选逐资产授权字段齐全，`rights_blocked=false` 才进 score 放行。
- 携程文章作品必须独立表达（事实回溯 + 跨稿重复门），不得整段搬运游记原文。
- Pinterest 图片只接受明确授权 / CC / 公版；无授权图只作 discovery，真实图片作品缺口由自有 / 授权图库补齐。
- 真实数量以授权充分的候选为上限；不足不得用降低版权门来凑数。
