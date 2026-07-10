# L3 Story: zhejiang-sichuan-province-coverage（浙江/四川旅行地点省级覆盖放量）

## 节点定位

- `L1_domain_service`: `discovery-content`
- `L2_business_capability`: `object-homepage-coverage-scaling`
- `L3_story`: `zhejiang-sichuan-province-coverage`

## 背景与动机

WP5 试点只圈舟山（14）/乐山（24）两市州；两省主清单 1093 项中已发布 18、ready 492
（含 20-30% 虚高）、pending 599。本 Story 把两省推进到「省级全覆盖」冻结口径
（定义见 L2 spec），并以两省为样板产出下一省复制策略。

## 目标用户

- 内容消费者：在 App 标签页/搜索中发现两省任一旅行地点时，能进入有真实正文、封面与
  类型标签的实体主页。
- 平台运营：以省为单位掌握覆盖率、来源饱和度与排产折扣率。

## 功能范围

1. 两省主清单扩容至来源发现饱和（目标合计 3000+ 候选，证据约束不凑数；不足则出
   来源饱和报告与缺口清单）。
2. 两省 ready 存量前置 sourceScreen 全量核验，产出折扣率与扩源缺口报告。
3. WP5 尾部 3 分区（乐山沙湾区/市中区、舟山岱山县）补跑收口，验证已落码产线修复
   （全放弃分区收口链、homepage-only promote、双树互杀边界）。
4. M1（两省各 100 校准批）→ M2（各 500）→ M3（全部真 ready）三档批次执行、gamma
   导入与 coverage 账本回写。
5. App 标签页/搜索入口 → 实体主页消费路径 user_acceptance 验收。

## Out of Scope

- 两省以外省份实跑。
- pending 存量的逐项扩源执行（扩源缺口清单是本 Story 输出，扩源执行按批次滚动）。
- 云端 worker 池横向扩展。

## 约束

- 严格准入门：并发/平稳性改造未完成不启动省级大批；M1 未达标不进 M2；放量硬前置
  未完成前省级大批只导 gamma。
- 跨省地点单主归属 + 多 geoTagRefs（泸沽湖模式）。
- 只跑核验后 ready；放弃必须 reasoned 归因落账。
- promote 质量对比门 SKIP 属正常裁决。

## 验收重点

1. 「省级全覆盖」六项冻结口径（市州齐全/区县无缺口/10 类覆盖/跨省单主/来源饱和/
   数值目标）逐项有证据。
2. M1/M2/M3 准入门逐档达标或诚实 GATE_BLOCK。
3. 覆盖账本、publish 主线、gamma 导入三方一致。
4. App 消费路径 UAT 通过（正文、封面、categoryTags、错误/空态、曝光/停留埋点）。
