## MODIFIED Requirements

### Requirement: 垂类任务编排与迭代补查
系统 SHALL 支持多垂类识别、任务拆解、依赖排序与迭代补查（改写查询、换源、扩范围、交叉验证），并在统一目录下覆盖 19 个垂类（18 主垂类 + 1 大搜兜底垂类）。

#### Scenario: 跨域问题多步执行
- **WHEN** 用户提问跨域问题（如天气 + 出行 + 推荐）
- **THEN** 生成结构化任务图并按依赖顺序执行，且任务路由落入 19 垂类之一

#### Scenario: 证据不足触发补查
- **WHEN** 首轮证据不足
- **THEN** 进入下一轮补查并记录补查策略

### Requirement: 大搜兜底默认策略
系统 MUST 提供默认大搜兜底域（`fallback_general_search`），当问题未命中垂类或垂类执行后仍无法满足汇总充分性时进入兜底流程。  
兜底流程 MUST 先判断是否可联网检索，再决定在线检索或离线能力边界回答。

#### Scenario: 未命中垂类触发兜底
- **WHEN** 18 个主垂类均未命中或命中置信度低于阈值
- **THEN** 系统进入 `fallback_general_search` 并执行兜底判断

#### Scenario: 可联网时执行默认大搜
- **WHEN** 兜底判断确认网络与搜索 provider 可用
- **THEN** 系统执行网络检索并返回“结论 + 依据 + 不确定性”结构化答案

#### Scenario: 不可联网时返回能力边界
- **WHEN** 兜底判断确认无法联网检索或搜索 provider 不可用
- **THEN** 系统不得伪造检索结果，必须明确告知当前可支持的回答范围，并返回可执行下一步建议

### Requirement: 模板资产化治理（不写死代码）
模型提示词 MUST 通过模板资产管理，不得写入业务代码字符串。  
系统 MUST 提供 2 个总控模板（`planner.global_plan`、`synthesizer.final_answer`）与 19 垂类模板（18 主垂类 + 1 兜底垂类，对应 `domain.<domainId>.task` + `domain.<domainId>.requery_or_expand_scope`）以及离线兜底守卫模板（`guardrail.fallback_offline_response`）的动态替换与灰度能力。

#### Scenario: 模板全链路可追踪
- **WHEN** run 执行模型调用
- **THEN** 日志可回溯 `templateId/templateVersion/variableBindings`

#### Scenario: 模板灰度切换
- **WHEN** 发布新模板
- **THEN** 支持按环境/流量灰度与快速回滚

#### Scenario: 兜底模板动态替换
- **WHEN** 调整兜底策略模板（在线大搜或离线能力边界模板）
- **THEN** 系统可通过模板版本动态替换与灰度，不修改业务代码

### Requirement: 双门禁总分总执行闭环
系统 MUST 采用双门禁总分总执行：`ContextAssembly -> DomainPreconditionCheck -> DomainExecution -> SynthesisReadinessCheck -> GlobalSynthesis`，并在 run 响应中输出结构化阶段结果。

#### Scenario: 入口门禁阻断
- **WHEN** Domain 前置条件不满足（如缺少 GPS 或长期记忆）
- **THEN** 触发 `ContextFillTask`，未补齐前不得进入对应 domain

#### Scenario: 汇总门禁回流
- **WHEN** 汇总充分性不足（覆盖/证据/冲突闭合未达标）
- **THEN** 触发 `GapFillTask`，并将历史检索条件与历史响应结果作为回流输入，明确说明“不满足原因”，据此生成单主题新检索条件后回流重跑 domain

### Requirement: 情感陪伴与社交陪聊边界
系统 MUST 同时支持 `emotion_companion`（情感陪伴/疏导）与 `social_companion_chat`（闲聊/话题陪聊）两种持续对话模式，并定义可回放的模式切换规则。

#### Scenario: 情感模式持续聊
- **WHEN** 用户持续表达负向情绪或疏导诉求
- **THEN** 系统进入 `emotion_companion` 持续聊，输出共情回应、微行动建议与风险检查

#### Scenario: 社交模式持续聊
- **WHEN** 用户表达“想聊聊/找话题/陪伴聊天”且无明显风险信号
- **THEN** 系统进入 `social_companion_chat` 持续聊，输出话题建议与下一轮引导

#### Scenario: 双模式动态切换
- **WHEN** 社交陪聊中出现情绪风险信号，或情感疏导后回到轻话题
- **THEN** 系统按规则在 `social_companion_chat` 与 `emotion_companion` 间切换，并记录切换原因

### Requirement: 统一提示词模板流水线
系统 MUST 采用统一模板流水线驱动：`推理(Reason) -> 规划(Plan) -> 执行(Execute) -> 总结(Summarize)`，并对每阶段定义输入上下文、检索驱动条件与输出结构。

#### Scenario: 规划前置上下文齐备
- **WHEN** 进入规划阶段
- **THEN** 输入至少包含用户问题、近期会话、长期记忆摘要、设备与位置信息、预算约束、用户画像快照与历史满意度摘要

#### Scenario: 执行阶段检索驱动
- **WHEN** 规划结果标记“需要外部证据”或“证据不足”
- **THEN** 执行阶段必须生成检索条件（query/time-window/provider/scope-expansion-policy）并记录到 run 结构化结果

#### Scenario: 总结阶段规则化输出
- **WHEN** 进入总结阶段
- **THEN** 输出必须包含结论、依据、不确定性、下一步建议与“继续怎么聊”的引导语

### Requirement: 模板输入契约与检索条件生成
每个模板 MUST 定义必填输入上下文与缺失处理策略。需要继续检索时，MUST 生成可执行检索条件而非仅文本描述。

#### Scenario: 模板必填输入缺失
- **WHEN** 模板必填变量缺失（如 `gps_lat`、`longterm_memory_summary`）
- **THEN** 系统触发 `ContextFillTask` 并阻断进入下一阶段

#### Scenario: 检索条件可执行
- **WHEN** 模板判断需补查
- **THEN** 输出结构化检索条件至少包含 `query`、`providerHint`、`timeRange`、`scopeExpansionPolicy`

#### Scenario: 历史检索回流输入
- **WHEN** 系统生成补查或重查任务
- **THEN** 必须输入历史检索条件与历史响应摘要（含证据命中情况、失败码、时效性），并输出“为何不满足”的结构化原因字段

#### Scenario: 单主题检索约束
- **WHEN** 系统生成新检索条件
- **THEN** 每条检索 query 必须聚焦单一主题（single-topic），多主题问题需拆分为多条子检索任务，禁止将多个主题揉为一条 query

#### Scenario: 历史满意度驱动策略选择
- **WHEN** 系统生成同类问题的新检索与答案策略
- **THEN** 必须输入历史雷同问题的满意度与失败原因，优先选择高满意策略并回避低满意策略

### Requirement: 串并行调度与依赖执行
系统 MUST 在总分总执行中支持串并行调度：可并行任务并行执行；存在依赖关系的任务必须按拓扑顺序串行执行。

#### Scenario: 可并行任务并行执行
- **WHEN** 多个 domain 任务无依赖且共享上下文已满足
- **THEN** 系统可并行执行并在汇总前统一做后置条件校验

#### Scenario: 依赖任务强制先后
- **WHEN** 某 domain 任务依赖上游结果（如 `travel_planning` 依赖 `weather/travel_transport`）
- **THEN** 系统必须等待上游任务完成后再执行下游任务，不得跳过依赖顺序

#### Scenario: 串并行混合回流
- **WHEN** 并行批次中仅部分任务证据不足
- **THEN** 仅对不足任务生成回流补查，不阻断已满足任务，并在下一轮按依赖关系重组执行图

### Requirement: 下一步引导与会话延续
系统 MUST 在最终回答中输出下一步引导建议（可选操作或继续对话提示），支持任务型对话与陪伴型对话的不同延续策略。

#### Scenario: 任务型下一步建议
- **WHEN** 回答属于任务解决场景（如旅行规划、选购、政策办理）
- **THEN** 至少给出 1-3 条可执行下一步建议

#### Scenario: 陪伴型继续对话引导
- **WHEN** 回答属于陪伴场景（emotion/social）
- **THEN** 给出低负担延续提示，帮助用户继续对话而不造成压迫感

### Requirement: 模板动态替换与 A/B 灰度
系统 MUST 支持模板版本动态替换、A/B 实验分流与指标回收；A/B 结果 MUST 绑定 `templateId/templateVersion/experimentBucket`。

#### Scenario: A/B 分桶执行
- **WHEN** 开启模板实验
- **THEN** 同类请求可按分桶命中不同模板版本，并记录分桶与结果指标

#### Scenario: 实验失败快速回滚
- **WHEN** 某模板实验版本导致关键指标下降
- **THEN** 系统可在不发版代码的前提下回滚到稳定模板版本

### Requirement: 越用越聪明学习闭环（19 垂类）
系统 MUST 在 19 垂类中统一实现“历史对话提取画像 + 历史满意度回灌 + 策略更新”机制，并将学习结果写入可复用上下文。

#### Scenario: 画像标签持续更新
- **WHEN** run 完成并具备有效对话与行为反馈
- **THEN** 系统提取并更新用户标签（兴趣、偏好、语气、风险偏好、时间地理偏好）并生成版本化画像快照

#### Scenario: 检索与答案策略自适应
- **WHEN** 同类问题存在可用历史满意度样本
- **THEN** 系统按垂类更新检索策略与答案组织策略权重，用于后续同类任务优先决策

#### Scenario: 低满意纠偏回路
- **WHEN** 同垂类连续低满意或高追问
- **THEN** 系统触发纠偏（改写 query、切换 provider、调整答案结构）并记录纠偏成效

### Requirement: 用户画像 1.0 子类目字典
系统 MUST 定义统一 `userProfileSnapshot` 1.0 字典，供 19 垂类共享，且支持版本化回放（`profileVersion/snapshotAt/sourceRuns`）。

#### Scenario: 五维偏好子类目完整
- **WHEN** 画像快照写入或更新
- **THEN** 必须覆盖以下五维及子类目：
  - 兴趣主题：`news_current_affairs/weather_environment/travel_exploration/local_life_services/shopping_consumption/finance_planning/health_wellness/education_growth/work_productivity/emotion_relationship/entertainment_hobby`
  - 决策偏好：`evidence_style/option_count_preference/explanation_depth/time_horizon/budget_sensitivity/brand_preference`
  - 风险偏好：`financial_risk_tolerance/safety_margin_preference/privacy_sensitivity/uncertainty_acceptance/health_safety_caution/social_emotional_risk`
  - 语气偏好：`communication_style_tags/directness/emoji_tolerance/motivation_style/interaction_pace`（其中 `communication_style_tags` 支持多标签，如商务正式/幽默诙谐/可爱/尊敬）
  - 时空偏好：`active_time_bands/schedule_density/trip_radius_preference/mobility_mode_preference/location_granularity_permission/weather_comfort_profile`

#### Scenario: 快照字段完整
- **WHEN** run 消费画像快照
- **THEN** 快照至少包含 `profileVersion`、`snapshotAt`、`confidenceByFacet`、`lastUpdatedByDomain`、`sourceRuns`、`recentSatisfactionSummary`

#### Scenario: 语气多标签可并存
- **WHEN** 用户偏好存在多种语气标签
- **THEN** `communication_style_tags` 允许多选并按场景动态加权，不强制单值覆盖

#### Scenario: 基础身份信息入档
- **WHEN** 系统写入或更新 `userProfileSnapshot`
- **THEN** 必须支持 `basicIdentity` 字段：`age`、`gender`、`birthDateSolar`、`birthDateLunar`（由 UserProfile 管理模块在资料维护时完成换算）

#### Scenario: IP 常驻地画像入档
- **WHEN** 系统具备可用 IP 地理信息与历史行为样本
- **THEN** 必须支持 `ipResidenceProfile` 字段：`homeAreaByIp`、`officeAreaByIp`、`studyAreaByIp`、`ipGeoConfidence`、`ipGeoUpdatedAt`

### Requirement: UserProfile 主模型边界
系统 MUST 将基础信息与画像统一托管在 `UserProfile` 管理模块；助手链路仅消费快照，不在运行时动态计算或覆盖基础信息字段。

#### Scenario: 助手消费不改写
- **WHEN** run 执行 19 垂类任务
- **THEN** 仅消费 `userProfileSnapshot`，不得对 `basicIdentity/ipResidenceProfile` 直接写库或重算覆盖

#### Scenario: 学习信号回流到 UserProfile
- **WHEN** 越用越聪明链路产出画像优化结果
- **THEN** 输出 `profileUpdateProposal` 给 UserProfile 管理模块，允许用户修改后再落库生效

### Requirement: `profileUpdateProposal` 字段契约（1.0）
系统 MUST 为 `profileUpdateProposal` 定义固定结构，仅用于建议回流，不得在 assistant 侧直接触发基础信息写库。

#### Scenario: 提案字段完整
- **WHEN** run 输出 `profileUpdateProposal`
- **THEN** 顶层至少包含 `proposalId/profileVersionRead/generatedAt/sourceRuns/confidence/requiresUserConfirm/updates[]`

#### Scenario: 更新项字段完整
- **WHEN** 输出 `updates[]`
- **THEN** 每项至少包含 `facet/path/operation/newValue/oldValueSnapshot/reason/evidenceRefs/itemConfidence/riskLevel`

#### Scenario: 基础信息强确认
- **WHEN** `updates[]` 命中 `basicIdentity` 或 `ipResidenceProfile`
- **THEN** `requiresUserConfirm=true` 且仅作为建议回流，不得由 assistant 直接落库

### Requirement: 垂类扩展与演进机制
系统 MUST 支持后续继续扩展新垂类，包括从 `fallback_general_search` 细化新垂类，或在既有 18 主垂类中细化子垂类，且不破坏既有模板契约。

#### Scenario: 从兜底演进新垂类
- **WHEN** 某主题在兜底域中持续高频且达到质量阈值
- **THEN** 系统生成新垂类候选并进入模板与门禁接入流程

### Requirement: 推荐阈值基线
系统 SHOULD 采用以下首期阈值基线并支持按实验桶动态调整：

- 主垂类命中阈值：`domainMatchScore >= 0.62`
- 低置信度阈值：`domainMatchScore < 0.45`
- 子意图覆盖率阈值：`intentCoverage >= 0.80`
- 证据充分度阈值：`evidenceSufficiency >= 0.70`
- 有帮助率回滚阈值：相对基线下降 `>= 5%`（连续 2 个窗口）
- 错误率回滚阈值：上升 `>= 3%`（连续 2 个窗口）
- 画像入库阈值：`tagConfidence >= 0.65`
- 策略切换阈值：`similarCaseCount >= 20` 且满意度差值 `>= 8%`

### Requirement: 残余风险收敛门禁
系统 MUST 对当前残余风险建立收敛门禁：字段类型漂移、回流协议未冻结、日志覆盖不足、敏感信息合规四类风险必须有对应实现与测试项。

#### Scenario: 发布前风险校验
- **WHEN** 团队准备灰度扩量
- **THEN** 若任一风险缺少“实现项 + 测试项 + 可观测项”，判定 No-Go

## ADDED Requirements

### Requirement: run 结构化响应
系统 MUST 在保留 `finalText/traces` 的同时，新增结构化响应对象，至少包含：`contextAssembly`、`domainPrecheck`、`domainResults`、`synthesisReadiness`、`fillTasks`、`nextActions`、`experimentBucket`、`userProfileSnapshot`、`retrievalFeedback`、`learningSignals`、`profileUpdateProposal`。

#### Scenario: 前端可直接渲染补齐任务
- **WHEN** run 因前置条件不足被阻断或因汇总不足回流
- **THEN** 前端可直接基于结构化字段渲染补齐任务，不依赖 trace 反解析

### Requirement: 开发准入门禁
进入开发阶段前，系统设计 MUST 完成模板ID与变量字典、前置输入契约、检索驱动输出契约、双陪伴模式边界与 run 结构化字段冻结。

#### Scenario: Go/No-Go 校验
- **WHEN** 团队准备进入实现阶段
- **THEN** 若上述任一契约未冻结，则判定 No-Go，不进入开发

### Requirement: 模板 2.0 章节规范与边界
系统 MUST 采用 `Markdown + Meta` 模板 2.0 规范，并统一章节结构。  
系统 MUST 执行“指令在前、数据在后”边界，数据区使用 `CONTEXT_DATA_START/END` 包裹。

#### Scenario: 模板章节完整
- **WHEN** 新增或更新任意模板
- **THEN** 模板正文必须包含任务背景、目标、约束、要求、任务规划（或前置检查）、输出格式、反思自检

#### Scenario: 指令数据边界校验
- **WHEN** 渲染模板
- **THEN** 指令区不得出现原始上下文数据，数据区不得新增指令约束

### Requirement: 槽位驱动与 WebSearch 子流水线
系统 MUST 使用统一槽位模型驱动上下文填充；对需联网垂类 MUST 执行 `web_query_plan -> web_result_judge -> web_key_fact_extract -> web_evidence_pack`。

#### Scenario: 槽位缺失触发补齐
- **WHEN** 任一必填槽位 `status!=ready`
- **THEN** 触发结构化补齐任务并阻断终态答案

#### Scenario: Web 证据包驱动答案
- **WHEN** 垂类进入答案生成阶段
- **THEN** 若该垂类需要联网证据，必须消费 `web_evidence_pack` 作为输入；证据不足时不得终答

### Requirement: 结构化答案反思诊断
系统 MUST 输出结构化答案并包含 `reasoningBasis/selfCheck/diagnostics`，用于说明“为何如此输出、是否满足自检约束”。

#### Scenario: 自检失败阻断
- **WHEN** `selfCheck` 关键项失败
- **THEN** 标记 `needMoreInfo=true` 并返回补齐任务，不得输出伪确定性结果

### Requirement: 垂类模板对标业界一流水准（无折扣）
19 个垂类模板 MUST 对标业界同类垂类实现完整度，禁止象征性模板或简化占位模板。

#### Scenario: 象征性模板判定不通过
- **WHEN** 模板缺少垂类专有规则、缺少异常与失败回退处理、缺少自检约束
- **THEN** 判定不通过，不得进入开发主线或灰度
