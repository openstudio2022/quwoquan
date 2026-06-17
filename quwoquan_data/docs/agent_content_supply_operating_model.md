# Agent 内容供给组织模型与 AI 自主创作治理设计

本文是内容生产线的公司治理式组织模型与 AI 自主创作边界设计。目标是让平台在冷启动与持续运营阶段，稳定产出高质量内容，同时让 Agent 有足够创作空间，而不是退化成填表器。

本设计适用于旅游、校园、汽车、科技、摄影等所有垂类，不允许写成某个景区、某个批次或某个临时任务的特例。

## 1. 设计原则

1. **上游锁边界，中游放创作，下游独立审计**：上游锁定任务、事实、权利、载体、作者边界和验收标准；中游允许 AI 自主决定标题、结构、叙事、信息取舍和表达风格；下游由独立 gate 审核事实、权利、质量、重复和消费价值。
2. **组织职责分离**：规划、检索、权利、创作、审校、修订、发布、反馈分别由不同角色承担，禁止同一个 Agent 自选来源、自写正文、自审通过、自发布。
3. **文件与 gate 是真相源**：Agent 口头声明不具备准出效力；准出只认结构化 packet、文件 hash、`GateVerdict` 和 `TokenLedger`。
4. **对象级隔离与快速失败**：单个实体、文章、图片或视频失败，不得拖住同批其它对象。不可恢复对象进入 `abandoned` 或 `manual_required`，批次结束后统一复盘。
5. **一稿一用，一图一属**：底稿、sourceUnit、sourceCollection、图片资产和授权凭证必须可追溯、可去重、可审计。未经明确声明和 gate 批准，不得跨作品复用。
6. **AI 自主性只在证据边界内发生**：AI 可以发挥表达、结构和读者价值判断；不能使用未准入来源、编造事实、越权换图、改变载体或伪造亲历。
7. **规模能力先由调度与门禁证明**：日产万级和十万级首先验证队列、token、缓存、去重、导入、反馈和故障隔离，再逐步扩大真实生成比例。

## 2. 组织角色

| 角色 | 类似公司职能 | 核心职责 | 禁止事项 | 主要产物 |
| --- | --- | --- | --- | --- |
| Supply Portfolio Controller | 经营计划 / PMO | 定义垂类、场景、目标量、载体比例、作者池、预算和放量节奏 | 不直接写正文、不绕过 gate | `SupplyPlanPacket`、批次计划、放量报告 |
| Vertical SOP Owner | 垂类负责人 | 维护垂类 SOP、来源注册、质量 rubric、禁用声明、样例库 | 不为单批放宽通用门槛 | `verticalSopRef`、`scenarioSopRef` |
| Source Research Agent | 资料研究员 | homepage/article/image/video 分 lane 检索与抽取，生成 evidence packet | 不写最终内容、不把不可抓或无授权来源标成可用 | `ObjectEvidencePacket`、source sufficiency report |
| Rights & Safety Agent | 法务 / 风控 | 判断 `sourceUseMode`、许可、署名、安全、人脸、商用风险 | 不用“看起来可用”替代授权证明 | rights verdict、safety verdict |
| Creative Planner Agent | 策划编辑 | 在 evidence packet 内提出 2-3 个创作方案、读者承诺、结构和标题候选 | 不新增事实、不换来源、不改载体 | `CreativeBrief`、creative plan gate 输入 |
| Creator Agent | 作者 / 编辑 | 按 creative brief 创作正文、标题、配文、主页介绍或视频脚本 | 不编造亲历、资质、官方背书或商业合作 | draft、`draft_meta` |
| Self Critic Agent | 作者自检 | 低成本自评标题兑现、信息密度、图文节奏、越界风险 | 不拥有最终通过权 | `author_self_check.json` |
| Independent Review Agent | 独立审校 | 审核事实、版权、图文一致、作者边界、非模板感和消费价值 | 不继承 creator 的自评结论 | `GateVerdict`、问题指纹 |
| Optimizer Agent | 修订编辑 | 只针对 review 指定失败点修复 | 不重新选源、不扩大事实边界 | repair draft、repair note |
| Batch Reducer | 批次总编 | 跑跨稿重复、题材分布、底稿复用、资产复用和作者疲劳门 | 不改写单篇正文 | batch reducer verdict |
| Release & Import Agent | 发布运营 | 打包 isolated release、导入 staging/gamma、刷新 search/recommendation 投影 | 不发布未过门对象 | release manifest、import report |
| Feedback & Revision Agent | 增长 / 客诉闭环 | 消费反馈、举报、下线、修订和下一轮选题回流 | 不直接修改线上正式对象 | feedback packet、revision task |
| Human Reviewer | 抽检 / 高风险复核 | 审批高风险内容、抽检 AI 审核质量、更新政策 | 不成为普通对象流水线瓶颈 | review record、policy update |

## 3. 端到端流程

| 阶段 | 输入 | 负责人 | 输出 | 准出 gate | 快速失败 |
| --- | --- | --- | --- | --- | --- |
| `clarify` | 用户目标、垂类、场景、产量、预算 | Supply Portfolio Controller | 任务边界、Out of Scope、载体比例 | spec completeness gate | 目标不可执行、预算缺失 |
| `prep` | 任务边界、当前实体/标签/作者/SOP | Vertical SOP Owner | SOP、作者池、来源 registry、生产记忆 | prep readiness gate | 缺 SOP、缺作者披露、缺来源 registry |
| `partition plan` | 目标对象、分区键、并发预算 | Controller | 分区计划、对象计划、job plan | quota and partition gate | 配额无法满足、分区不稳定 |
| `source-ready admission` | 对象计划、source registry | Source Research Agent | 三路独立 source plan | source candidate gate | 无可抓来源、弱匹配、授权不足 |
| `evidence packet` | source plan、下载抽取结果 | Source Research + Rights | `ObjectEvidencePacket` | evidence sufficiency gate | 底稿不足、图片不足、sourceUseMode 不匹配 |
| `creative planning` | evidence packet、SOP、作者画像 | Creative Planner Agent | `CreativeBrief` | creative plan gate | 读者承诺空泛、与同实体其它内容重复 |
| `authoring` | creative brief、evidence packet | Creator Agent | draft、assets refs、`draft_meta` | draft structure gate | 新增事实越界、载体不匹配 |
| `self critique` | draft | Self Critic Agent | self-check、修订建议 | self-check completeness gate | 自检缺失或未覆盖关键风险 |
| `independent review` | draft、evidence、rights、self-check | Independent Review Agent | `GateVerdict` | review hard gates | 事实、权利、图文、人格边界任一硬失败 |
| `optimizer repair` | failed verdict、draft、evidence | Optimizer Agent | repair draft、repair note | same failed gate only | 同一失败指纹超过 2 次 |
| `batch reduce` | 全部对象 verdict | Batch Reducer | batch verdict | duplicate/diversity/reuse gate | 跨稿重复、底稿或资产复用 |
| `release/import` | approved objects | Release & Import Agent | isolated release、staging/gamma import | release/import gate | 引用不闭合、manifest 不完整 |
| `feedback loop` | 曝光、点击、停留、举报、互动 | Feedback & Revision Agent | revision task、下一轮策略 | feedback policy gate | 举报高危、事实过期、质量退化 |

## 4. 交接契约

所有交接只使用当前唯一契约名，不允许用历史版本后缀制造双轨。

| 契约 | 用途 | 必填要点 |
| --- | --- | --- |
| `SupplyPlanPacket` | 任务澄清与分区计划 | 垂类、场景、目标量、载体比例、作者策略、预算、release policy |
| `ObjectJob` | 队列执行单元 | jobId、objectKey、stage、partition、creator、预算、retry policy、deadline |
| `ObjectEvidencePacket` | 事实和权利边界 | sourceUnit、primaryEvidenceRef、supportingEvidenceRefs、sourceUseMode、asset refs、rights verdict |
| `CreativeBrief` | AI 创作空间 | `readerPromise`、`contentAngle`、`voiceStyle`、`allowedMoves`、`mustNotDo`、`qualityTargets` |
| `AgentResultEnvelope` | Agent 结果采纳 | 输出文件、sha256、使用的输入 hash、gate 引用、token ledger 引用 |
| `GateVerdict` | 单一门禁裁决 | gateName、inputHash、outputHash、passed、issues、failureFingerprint、retryable |
| `TokenLedger` | 成本闭环 | budget、actual、cacheHit、model、cost、unitPassedCost |
| `FeedbackSignalPacket` | 消费反馈回流 | exposure、click、dwell、follow、share、report、revision action |

交接规则：

- 上游 packet 必须可回放；只写“见上一步”无效。
- 下游只能读取声明过的输入，不得扫同批其它对象正文。
- Agent 输出必须通过 `AgentResultEnvelope` 被 controller 采纳；无 envelope、hash 不符、gate 缺裁决均失败。
- `entityRefs`、`tagRefs` 只能由已发布 mention 派生；待确认候选只保留为不可点击文本。

## 5. AI 自主创作边界

AI 可以自主决定：

- 标题候选、开头方式、段落结构、叙事节奏和收束方式。
- 在 evidence packet 内哪些事实更适合前置，哪些作为辅助信息。
- 读者视角，例如规划咨询、体验决策、避坑、摄影审美、知识科普。
- 表达风格，例如专业编辑、攻略型、摄影型、亲子型、自驾型、知识型。
- 修订策略，但只能针对 review 指定失败点。

AI 不可以自主决定：

- 使用未准入来源或无授权素材。
- 替换、扩展或混用图片 source collection。
- 改变内容载体，例如把图片作品写成文章，或把文章降成图库。
- 编造具体数字、路线、价格、开放状态、历史事件或亲历体验。
- 伪造真实自然人身份、资质、官方背书或商业合作。
- 把 `pending_review` mention 写入 active `entityRefs/tagRefs`。
- 绕过 gate，或用口头成功替代文件和裁决。

## 6. Creative Workspace

`CreativeBrief` 是 AI 发挥创造力的空间，必须在 `ObjectEvidencePacket` 之后生成。

```json
{
  "readerPromise": "这篇内容承诺帮用户解决什么问题",
  "contentAngle": "规划|体验|摄影|科普|清单|路线|避坑",
  "voiceStyle": {
    "creatorProfileId": "creator_xxx",
    "tone": "专业编辑/轻攻略/摄影观察",
    "claimBoundary": "资料整理，不声明亲历"
  },
  "allowedMoves": [
    "问答式结构",
    "场景式开头",
    "对比式信息组织"
  ],
  "mustNotDo": [
    "禁止虚假亲历",
    "禁止百科腔",
    "禁止营销腔",
    "禁止来源痕迹复写"
  ],
  "qualityTargets": {
    "informationDensity": "high",
    "titlePromise": "must_fulfill",
    "practicality": "explicit",
    "templateRisk": "low"
  }
}
```

Creative Planner 必须先提出 2-3 个方案，再选择一个最符合 `readerPromise` 的方案进入创作；未选方案和未使用事实写入 `draft_meta`，用于审计 AI 的取舍。

## 7. 质量门

| Gate | 检查重点 | 失败动作 |
| --- | --- | --- |
| Spec Gate | 垂类、场景、载体、作者、预算、验收是否完整 | 阻断创建批次 |
| Source Candidate Gate | 实体强匹配、可抓取性、类别、权利、反探针页 | 快速失败或补检索 |
| Evidence Boundary Gate | 新增事实是否回溯到 evidence packet | 修订或失败 |
| Rights Gate | sourceUseMode、许可、署名、安全、人脸、商用风险 | 阻断发布 |
| Creative Plan Gate | 读者承诺、结构差异、非重复、可消费价值 | 退回 creative planning |
| Persona Boundary Gate | 虚拟作者披露、无虚假亲历、无虚假资质 | 修订或冻结作者 |
| Carrier Gate | homepage/article/image/video 的底稿与产物匹配 | 退回 plan 或 source |
| Image/Asset Gate | 一图一属、sourceCollectionId、授权凭证、图文一致 | 阻断对象 |
| Editorial Value Gate | 标题兑现、信息密度、可操作性、非模板感 | 进入 optimizer |
| Diversity Gate | 同实体多篇角度不同、同作者不连续模板化 | reducer 回退受影响对象 |
| Token Gate | prompt 预算、缓存命中、单位通过成本 | 降级摘要或拒绝生成 |
| Release Gate | manifest、assets、provenance、refs、import 投影闭合 | 阻断 release/import |
| Feedback Gate | 举报、事实过期、低消费价值触发修订或下线 | 创建 revision task |

## 8. 失败与重试

- **内容质量失败**：同一对象同一失败指纹最多修复 2 次，仍失败则 `manual_required`。
- **基础设施失败**：网络、SDK、队列 lease、进程崩溃最多重试 3 次，不占内容质量预算。
- **不可恢复失败**：来源不可抓、授权缺失、实体弱匹配、图片不足、载体不匹配时快速标记 `abandoned` 或进入人工授权队列。
- **批次不被单点拖死**：release policy 可声明 `strict_all_pass` 或 `partial_with_abandoned_report`；后者必须输出失败对象、原因、影响和下一步。
- **修复只回退失败对象与失败阶段**：不得因一个对象失败全批重跑。

## 9. 高并发与低 token 策略

1. **分区**：按垂类、地域、省份、品牌、知识域或作者池分区。旅游全国任务可采用“每省一个 partition agent，省内 subagent 并发”的模式。
2. **队列**：本地文件队列只用于小批；生产使用可靠队列后端，保持 lease、heartbeat、deadline、dead、spillover 语义一致。
3. **摘要缓存**：SOP 摘要、作者画像、source 抽取、evidence packet、review 诊断按 hash 缓存。
4. **prompt 限额**：SOP 摘要不超过 500 tokens，作者画像摘要不超过 300 tokens，evidence 摘要按载体限额注入。
5. **模型分级**：规划与最终法务门使用强模型；抽取、格式、去重、批量 QA 使用规则或低成本模型。
6. **生产记忆前置去重**：sourceUnit、baseDraft、sourceCollection、asset hash、title embedding、body simhash 在生成前阻断。
7. **始终保持活跃槽位**：完成一个补一个，慢 job 由 deadline/reaper 管理，不让并发池空转或被卡死对象占满。

## 10. 商用放量验收

| 档位 | 目标 | 必须证明 |
| --- | --- | --- |
| 小样本 | 10-30 内容对象 | 全流程 gate 有效、AI 输出不模板化、人工抽检可消费 |
| 百级 | 100-600 内容对象 | 分区、重试、失败隔离、TokenLedger、release/import 幂等 |
| 千级 | 1k-3k 内容对象 | 队列吞吐、缓存命中、去重、抽检质量、成本可外推 |
| 万级 dry-run | 10k 内容计划 | 调度、预算、source sufficiency、导入模拟、反馈模拟 |
| 十万级 dry-run | 100k 内容计划 | 分区无热点、作者激活分布、队列无阻塞、单位通过成本可控 |

进入商用放量前必须同时满足：

- 硬门通过率 100%。
- 事实回溯率不低于当前垂类阈值，旅游/知识类默认不低于 95%。
- 图片/视频授权完整率 100%。
- active `entityRefs/tagRefs` 无待确认污染。
- stuck job 为 0；dead job 可隔离、可复盘，不阻塞其它对象。
- TokenLedger 能输出单对象成本、单位通过成本和缓存命中率。
- 消费者价值抽检合格率达到垂类 SOP 阈值。

## 11. 与现有文档关系

- 端到端生产主线见 [`content_pipeline_spec.md`](content_pipeline_spec.md)。
- 单对象隔离、队列、lease、并发与 spillover 见 [`subagent_scheduler_spec.md`](subagent_scheduler_spec.md)。
- 商用 SLO、成本、产能和人审闭环见 [`content_ops_slo.md`](content_ops_slo.md)。
- 环境发布与回滚见 [`environment_data_release_runbook.md`](environment_data_release_runbook.md)。
