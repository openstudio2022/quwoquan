# L3 Story: zhejiang-sichuan-province-coverage（浙江/四川旅行地点省级覆盖放量）

## 节点定位

- `L1_domain_service`: `discovery-content`
- `L2_business_capability`: `object-homepage-coverage-scaling`
- `L3_story`: `zhejiang-sichuan-province-coverage`
- 当前实施与验收真相源：本目录的 `spec.md` 与 `acceptance.yaml`。不维护并行滚动计划。

## 背景与动机

WP5 试点只圈舟山/乐山两市州。两省 coverage 主清单包含大量待核验候选，
当前唯一主清单已扩展为浙江 922、四川 1977，共 2899 个区县级叶子；
任何旧 ready 标记都不能绕过 `encyclopedia-primary`。本 Story 把两省推进到「省级全覆盖」
冻结口径（定义见 L2 spec），并以两省为样板产出下一省复制策略。

## 目标用户

- 内容消费者：在 App 标签页/搜索中发现两省任一旅行地点时，能进入有真实正文、封面与
  类型标签的实体主页。
- 平台运营：以省为单位掌握覆盖率、来源饱和度与排产折扣率。

## 功能范围

1. 以省→市州→区县→10 类→五路 discovery source 的 coverage 矩阵证明来源发现
   饱和；资源 limit 只作护栏，不得作为饱和证据。
2. OSM/Wikidata/百科搜索只做候选发现；OSM-only、泛名、商户/物业/普通设施不得直接
   写 master list。身份按 QID/pageid/OSM ID→名称+坐标+区县解析。
3. 两省候选在每个 execution 内以对象本地 source catalog、来源证据和图片权利结论动态
   核验；只有三百科闭集 qualification confirmed 对象可以发布。
4. WP5 尾部 3 分区（乐山沙湾区/市中区、舟山岱山县）补跑收口，验证已落码产线修复
   （全放弃分区收口链、homepage-only promote、双树互杀边界）。
5. M1（两省各 100 校准批）→ M2（各 500）→ M3（全部主清单目标）三档批次执行、四环境
   promotion 与 coverage 账本回写。
6. App 标签页/搜索入口 → 实体主页消费路径 user_acceptance 验收。
7. 所有主页执行使用单一 `executionId` 工作包：规划、来源、对象五阶段、证据与 release
   引用都在 `.qwq_output/data/tasks/<executionId>/`；可复用 recipe/prompt/template/schema
   不携带省份、日期、实体或运行路径，最终 approved 对象才进入 `publish/**`。
8. 页面图片必须由单一 `MediaWikiPageBundle` 枚举：页面图位不得受数量 cap；下载漏失、
   策略排除和语义重复必须逐项归因。封面只进入 frontmatter，正文仅接受有结构锚点的
   inline 图，groupMember 与无可靠锚点图片只进入唯一「相关图片」章节。
9. 作者与独立审阅者的模型 ID、模型族必须在 recipe 显式声明；执行 G0 在任何来源抓取前
   对两者分别做真实 Cursor SDK 启动探针。`reviewer_response` 只承载 Agent 结论，控制器
   才能绑定 provider/model/modelFamily/runId 并写入 canonical `reviewer_result`；同族、同
   run、不可启动或无 findings 一律 `GATE_BLOCK`。
10. 金丝雀、M1、M2、M3 每档都必须先聚合 immutable release，再完成 Gamma 导入、API
    核验、动态 App UAT、回滚与重放，并写入 `rollout_milestone_closure`。下一档只能复验前
    一档的不可变 release 闭包，不得读取 campaign 进度文件、状态目录或人工标记。
11. `execution_manifest.json` 是唯一执行身份源，必须包含 `selectionPolicy=frozen`、
    `targetSetRef` 与 `targetSetSha256`。Data execution 不携带部署环境；`runtime_state.json`
    只保存命令序列与运行时间，不重复 `contentType/phase/supplyMode/sourceKey/params`。
12. 冻结目标集在初始化时即为每个目标创建 `1.download` 至 `5.review` 五阶段目录；不得使用
    reserve、replacement、abandoned-as-success 或重试时改变目标。重试仅用新 sequence 并写
    `retryOf`，且不得复用旧阶段文件。
13. M3 闭包后使用仓内 `verticals/travel/cold_start_supply_policy.yaml` 选择浙江、四川各 10 个
    代表实体，每实体生成 article、image、video 各 1 篇，共 60 个 approved posts；三类内容
    复用同一 execution/review/publish/release 主干，不建立冷启动旁路。
14. video 是正式发布 lane，必须生成 9:16 H.264 MP4、poster、字幕、checksum 与权利 provenance；
    自生成或明确可商用素材之外的输入一律阻断，不允许 `smoke_only` 成品进入 launch release。
15. 最终 launch release 是 2899 entities、60 posts 及其实际引用 creator/media/tag 的唯一不可变
    发布单元。Alpha 只验证同 digest 的 mock/contract 投影，Beta 验证 full-sync/API/幂等/回滚，
    Gamma 验证全对象 API、29 个主页 UAT 分片和 feed/search/三载体消费；Prod 仅在显式确认和审批
    证据齐全时按 canary→M1→M2→M3→launch 灰度，任何阶段失败回滚上一 immutable release。

## 放量数量合同

| 里程碑 | 浙江新增 / 累计 | 四川新增 / 累计 | 总累计 |
|---|---:|---:|---:|
| canary | 2 / 2 | 1 / 1 | 3 |
| M1 | 100 / 102 | 100 / 101 | 203 |
| M2 | 500 / 602 | 500 / 601 | 1203 |
| M3 | 320 / 922 | 1376 / 1977 | 2899 |

四档目标集必须两两不交叠，合并后与 coverage master digest 精确相等。每一档 release 都是
从 canary 到当前里程碑的累计 immutable `full-sync` release；回滚目标依次为空基线、
canary、M1、M2，回滚后必须 replay 当前 release。

M3 之后的 launch release 不改变两省主页集合，只增加冷启动供给合同冻结的 60 个 posts 及其
引用闭包。feed 至少可消费 20 条，非空率不低于 0.999，重复曝光率低于 0.01；阈值只从
`cold_start_supply_policy.yaml` 读取，不得在代码或测试复制第二默认值。

## Out of Scope

- 两省以外省份实跑。
- 云端 worker 池横向扩展。
- 未经显式确认和审批证据的 Prod 写入。

## 约束

- 严格准入门：并发/平稳性改造未完成不启动省级大批；M1 未达标不进 M2；放量硬前置
  未完成前省级大批只导 gamma。
- 跨省地点单主归属 + 多 geoTagRefs（泸沽湖模式）。
- 主清单所有目标都可以进入 execution；只有动态来源资格 confirmed 的对象可以发布，blocked
  对象必须以 typed `GATE_BLOCK` 归因落账，并阻断当前累计 release，不得替换目标。
- M1 真实 approved homepage 吞吐与对象 P95 必须满足 rollout capacity 合同；进入内容放量前必须先完成
  同一合同定义的 Cursor SDK soak，并明确区分基础设施探针与主页生产证据。
- review 未批准的对象不得写入 canonical；批准对象只经 object transaction 原子写入，
  不维护第二套 promote 路径或新旧稿兼容裁决。

## 验收重点

1. 「省级全覆盖」六项冻结口径（市州齐全/区县无缺口/10 类×六来源 cell 终态/
   跨省单主/来源饱和/数值目标）逐项有 checkpoint 与饱和证据。
2. M1/M2/M3 准入门逐档达标或诚实 GATE_BLOCK。
3. 每个 execution 的来源、失败对象、review 与 readiness 都留在自身工作包；
   approved 对象原子写 canonical，环境导入只消费对应 immutable release。
4. App 消费路径 UAT 通过（正文、封面、categoryTags、错误/空态、曝光/停留埋点）。
5. G0 目录/凭证/输入门、G1 覆盖饱和、G2 v2 来源与逐图权利、G3 双省金丝雀、G4 M1、
   G5 M2、G6 M3 release/import、G7 launch 冷启动供给与四环境 UAT 必须按顺序准出；任一失败只输出带
   `executionId` 的 `GATE_BLOCK`。
6. 浙江金丝雀固定验证普陀山与东钱湖，四川金丝雀固定验证海螺沟；普陀山页面图位
   完整性为 17，东钱湖为 infobox lead 1 + Gallery 4。实时页面变化时以执行 revision/hash
   为准，但任何未枚举、未下载、未归因或 cover/section 重复都阻断放量。
7. 独立审阅证据必须同时证明 author/reviewer 的异模型族、不同 runId、最少一项独立
   findings 与执行前模型启动成功；模型列举成功但实际 SDK 运行失败不构成准入证据。
8. 浙江金丝雀只能是普陀山、东钱湖，四川金丝雀只能是海螺沟；M1/M2 必须分别达到每省
   100/500 个 approved 实体，M3 必须与覆盖主清单等量。任意数量、范围或 Gamma 证据漂移
   必须阻断下一档 execution 创建。
9. launch release 必须精确包含 60 个 approved posts，article/image/video 各 20；Alpha、Beta、
   Gamma、Prod 的 promotion evidence 必须指向相同 release digest。Prod 未经显式确认不得写入，
   未执行不得登记为通过。
