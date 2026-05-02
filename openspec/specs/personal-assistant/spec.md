# personal-assistant

## Purpose

个人私人助理统一能力规范：在趣我圈内提供单一助手能力定义，不再区分“商用版本”或“垂类编排版本”。  
规范覆盖统一网关、ReAct++ 主循环、双门禁总分总、垂类任务编排、模板资产治理、可观测回放、SLO 与灰度门禁。

---

## ADDED Requirements

### Requirement: 统一能力边界与命名

系统 MUST 以单一 `personal-assistant` 规格作为对外与内部协作基线，不再并行维护“商业版”与“垂类编排版”能力定义。

#### Scenario: 单一规格来源

- **WHEN** 团队新增或调整助手能力
- **THEN** 仅更新本规格，不在记录分叉规格上新增新能力条款

---

### Requirement: 统一网关与运行接口

系统 SHALL 提供统一网关能力，包含 providers、skills、runs、stream、sessions、costs、alerts、adapters、channels ingress。

#### Scenario: 核心接口可用

- **WHEN** 调用统一助手网关
- **THEN** `GET /v1/assistent/providers|skills|sessions|costs|alerts|adapters` 与 `POST /v1/assistent/runs|runs/stream|skills/invoke|channels/{adapterId}` 可用

---

### Requirement: 双门禁总分总执行闭环

系统 MUST 采用双门禁总分总执行：`ContextAssembly -> DomainPreconditionCheck -> DomainExecution -> SynthesisReadinessCheck -> GlobalSynthesis`。

#### Scenario: 入口门禁阻断

- **WHEN** Domain 前置条件不满足（如缺少 GPS 或长期记忆）
- **THEN** 触发 `ContextFillTask`，未补齐前不得进入对应 domain

#### Scenario: 汇总门禁回流

- **WHEN** 汇总充分性不足（覆盖/证据/冲突闭合未达标）
- **THEN** 触发 `GapFillTask`，生成新检索条件并回流重跑 domain

---

### Requirement: 上下文逐步披露与补齐任务

系统 MUST 采用最小必要上下文启动，并按缺口逐步披露补齐；缺失项以任务形式可追踪。

#### Scenario: 精准补齐而非全量扩查

- **WHEN** 仅缺少某类上下文（如位置信息）
- **THEN** 只触发对应 `FillTask`，不进行无差别全量检索

#### Scenario: 长期记忆按需补齐

- **WHEN** 用户问题涉及“很久前发生了什么”
- **THEN** 触发长期记忆补齐任务并回写 `ContextEnvelope`

---

### Requirement: 垂类任务编排与迭代补查

系统 SHALL 支持多垂类识别、任务拆解、依赖排序与迭代补查（改写查询、换源、扩范围、交叉验证）。

#### Scenario: 跨域问题多步执行

- **WHEN** 用户提问跨域问题（如天气 + 出行 + 推荐）
- **THEN** 生成结构化任务图并按依赖顺序执行

#### Scenario: 证据不足触发补查

- **WHEN** 首轮证据不足
- **THEN** 进入下一轮补查并记录补查策略

---

### Requirement: 情感陪伴与闲聊陪聊边界

系统 MUST 同时支持 `emotion_companion`（情感陪伴/疏导）与 `social_companion_chat`（闲聊/话题陪聊）两种持续对话模式，并定义可回放的模式切换规则。

#### Scenario: 情感模式持续聊

- **WHEN** 用户持续表达负向情绪或疏导诉求
- **THEN** 系统进入 `emotion_companion` 持续聊，输出共情回应、微行动建议与风险检查

#### Scenario: 闲聊模式持续聊

- **WHEN** 用户表达“想聊聊/找话题/陪伴聊天”且无明显风险信号
- **THEN** 系统进入 `social_companion_chat` 持续聊，输出话题建议与下一轮引导

#### Scenario: 双模式动态切换

- **WHEN** 社交陪聊中出现情绪风险信号，或情感疏导后回到轻话题
- **THEN** 系统按规则在 `social_companion_chat` 与 `emotion_companion` 间切换，并记录切换原因

---

### Requirement: 大搜兜底默认策略

系统 MUST 提供默认大搜兜底域（`fallback_general_search`），当问题未命中垂类或垂类执行后仍无法满足汇总充分性时，进入兜底流程。  
兜底流程 MUST 先判断是否可联网检索，再决定在线检索或离线能力边界回答。

#### Scenario: 未命中垂类触发兜底

- **WHEN** 18 个主垂类均未命中或命中置信度低于阈值
- **THEN** 系统进入 `fallback_general_search` 并执行兜底判断

#### Scenario: 可联网时执行默认大搜

- **WHEN** 兜底判断确认网络与搜索 provider 可用
- **THEN** 系统执行网络检索并返回“结论 + 依据 + 不确定性”结构化答案

#### Scenario: 不可联网时返回能力边界

- **WHEN** 兜底判断确认无法联网检索或搜索 provider 不可用
- **THEN** 系统不得伪造检索结果，必须明确告知当前可支持的回答范围，并返回可执行下一步建议（如授权网络、补充信息后重试）

---

### Requirement: 统一契约与前后置条件规格

系统 MUST 采用统一契约：`GlobalPlan`、`ContextEnvelope`、`DomainTaskContext`、`DomainResult`、`SynthesisReport`、`PreconditionSpec`、`PostconditionSpec`、`FillTask`。

#### Scenario: 契约可机器校验

- **WHEN** 任一 run 执行
- **THEN** 可从轨迹中校验前后置条件、缺失槽位与补齐任务执行状态

---

### Requirement: 模板资产化治理（不写死代码）

模型提示词 MUST 通过模板资产管理，不得写入业务代码字符串。

#### Scenario: 模板全链路可追踪

- **WHEN** run 执行模型调用
- **THEN** 日志可回溯 `templateId/templateVersion/variableBindings`

#### Scenario: 模板灰度切换

- **WHEN** 发布新模板
- **THEN** 支持按环境/流量灰度与快速回滚

#### Scenario: 兜底模板动态替换

- **WHEN** 调整兜底策略模板（在线大搜或离线能力边界模板）
- **THEN** 系统可通过模板版本动态替换与灰度，不修改业务代码

---

### Requirement: 统一提示词模板流水线

系统 MUST 采用统一模板流水线驱动：`推理(Reason) -> 规划(Plan) -> 执行(Execute) -> 总结(Summarize)`，并对每阶段定义输入上下文、检索驱动条件与输出结构。

#### Scenario: 规划前置上下文齐备

- **WHEN** 进入规划阶段
- **THEN** 输入至少包含用户问题、近期会话、长期记忆摘要、设备与位置信息、预算约束、用户画像快照与记录满意度摘要

#### Scenario: 执行阶段检索驱动

- **WHEN** 规划结果标记“需要外部证据”或“证据不足”
- **THEN** 执行阶段必须生成检索条件（query/time-window/provider/scope-expansion-policy）并记录到 run 结构化结果

#### Scenario: 总结阶段规则化输出

- **WHEN** 进入总结阶段
- **THEN** 输出必须包含结论、依据、不确定性、下一步建议与“继续怎么聊”的引导语

---

### Requirement: 模板输入契约与检索条件生成

每个模板 MUST 定义必填输入上下文与缺失处理策略。需要继续检索时，MUST 生成可执行检索条件而非仅文本描述。

#### Scenario: 模板必填输入缺失

- **WHEN** 模板必填变量缺失（如 `gps_lat`、`longterm_memory_summary`）
- **THEN** 系统触发 `ContextFillTask` 并阻断进入下一阶段

#### Scenario: 检索条件可执行

- **WHEN** 模板判断需补查
- **THEN** 输出结构化检索条件至少包含 `query`、`providerHint`、`timeRange`、`scopeExpansionPolicy`

#### Scenario: 记录检索满意度驱动新检索

- **WHEN** 系统生成新一轮检索条件
- **THEN** 必须输入“记录雷同问题检索响应满意度”与失败原因，优先复用高满意策略并规避低满意策略（如 provider、query风格、时间范围、结构化答案样式）

---

### Requirement: 越用越聪明学习闭环（19 垂类通用）

系统 MUST 为 19 个垂类统一建设“记录对话 -> 画像标签 -> 检索/答案策略更新”的学习闭环，且学习结果可被后续 run 直接消费。

#### Scenario: 从记录对话提取画像标签

- **WHEN** run 结束并产生有效对话
- **THEN** 系统抽取并更新用户标签/画像（兴趣主题、决策偏好、风险偏好、语气偏好、时间地理偏好）并写入可回放快照

#### Scenario: 从记录满意度更新策略

- **WHEN** 记录雷同问题存在显式或隐式满意度信号（如点赞、追问减少、任务完成）
- **THEN** 系统更新该垂类策略权重（检索provider偏好、query改写策略、答案结构偏好），并在下次同类任务优先采用高满意策略

#### Scenario: 低满意度触发纠偏

- **WHEN** 同类问题连续低满意或高追问
- **THEN** 系统降低当前策略权重，触发“改写query/换provider/换答案组织”纠偏路径，并记录纠偏结果用于后续学习

#### Scenario: 记录会话聚类作为共享能力输入

- **WHEN** 系统进入同类问题策略选择或模板优化评估
- **THEN** 必须先读取“记录会话聚类”结果（跨 19 垂类共享能力），用于同类参考、策略权重更新与提示词优化输入

#### Scenario: 记录会话聚类存量任务入总目标

- **WHEN** 当前版本尚未完成“记录会话聚类在线能力”
- **THEN** 必须在总体目标中记录为存量任务（全垂类共享），并在发布评审中持续跟踪，不得因仅完成算卦域而关闭该任务

### Requirement: 用户画像 1.0 子类目字典（可回放快照）

系统 MUST 提供统一的 `userProfileSnapshot` 1.0 字典，供 19 垂类共用，并支持版本化回放（`profileVersion/snapshotAt/sourceRuns`）。

#### Scenario: 兴趣主题（interestTopics）子类目

- **WHEN** 系统更新画像快照
- **THEN** `interestTopics` 至少包含以下子类目及权重：
  - `news_current_affairs`（资讯时事）
  - `weather_environment`（天气与环境）
  - `travel_exploration`（出行与旅行）
  - `local_life_services`（本地生活服务）
  - `shopping_consumption`（购物消费）
  - `finance_planning`（财务规划）
  - `health_wellness`（健康养生）
  - `education_growth`（学习成长）
  - `work_productivity`（工作效率）
  - `emotion_relationship`（情感关系）
  - `entertainment_hobby`（娱乐兴趣）

#### Scenario: 决策偏好（decisionPreferences）子类目

- **WHEN** 系统更新画像快照
- **THEN** `decisionPreferences` 至少包含：
  - `evidence_style`: `data_first|experience_first|balanced`
  - `option_count_preference`: `few|medium|many`
  - `explanation_depth`: `concise|standard|detailed`
  - `time_horizon`: `immediate|short_term|long_term`
  - `budget_sensitivity`: `low|medium|high`
  - `brand_preference`: `none|stable_brands|cost_effective`

#### Scenario: 风险偏好（riskPreferences）子类目

- **WHEN** 系统更新画像快照
- **THEN** `riskPreferences` 至少包含：
  - `financial_risk_tolerance`: `conservative|balanced|aggressive`
  - `safety_margin_preference`: `strict|normal|flexible`
  - `privacy_sensitivity`: `high|medium|low`
  - `uncertainty_acceptance`: `low|medium|high`
  - `health_safety_caution`: `high|medium|low`
  - `social_emotional_risk`: `avoidant|neutral|open`

#### Scenario: 语气偏好（tonePreferences）子类目

- **WHEN** 系统更新画像快照
- **THEN** `tonePreferences` 至少包含：
  - `communication_style_tags`: `string[]`（可多标签并存），候选值至少包括 `business_formal`（商务正式）、`humorous`（幽默诙谐）、`cute`（可爱）、`respectful`（尊敬）、`friendly`（亲和）、`empathetic`（共情）
  - `directness`: `direct|balanced|gentle`
  - `emoji_tolerance`: `none|light|normal`
  - `motivation_style`: `action_oriented|supportive|reflective`
  - `interaction_pace`: `fast|normal|slow`

#### Scenario: 多语气标签组合生效

- **WHEN** 用户语气偏好同时命中多个标签（如 `business_formal` + `respectful`，或 `humorous` + `cute`）
- **THEN** 系统允许组合输出语气，并在高风险场景（医疗、财务、情感危机）自动抑制过度娱乐化标签

#### Scenario: 时空偏好（spatiotemporalPreferences）子类目

- **WHEN** 系统更新画像快照
- **THEN** `spatiotemporalPreferences` 至少包含：
  - `active_time_bands`: `morning|afternoon|evening|late_night`
  - `schedule_density`: `compact|balanced|relaxed`
  - `trip_radius_preference`: `nearby|city_wide|cross_city`
  - `mobility_mode_preference`: `walk|public_transit|drive|mixed`
  - `location_granularity_permission`: `precise|coarse|city_only`
  - `weather_comfort_profile`: `heat_sensitive|cold_sensitive|rain_avoidant|all_weather`

#### Scenario: 快照字段统一

- **WHEN** 任一 run 读取画像快照
- **THEN** 字段至少包含 `profileVersion`、`snapshotAt`、`confidenceByFacet`、`lastUpdatedByDomain`、`sourceRuns`、`recentSatisfactionSummary`

#### Scenario: 基础身份信息子类目（basicIdentity）

- **WHEN** UserProfile 管理模块写入或更新用户基础资料
- **THEN** `basicIdentity` 至少包含：
  - `age`（年龄，可为区间或精确值）
  - `gender`（性别：`female|male|non_binary|unknown`）
  - `birthDateSolar`（阳历生日，`YYYY-MM-DD`）
  - `birthDateLunar`（农历生日，由 UserProfile 管理模块在资料维护时完成换算并存储）

#### Scenario: 基于 IP 的常驻地子类目（ipResidenceProfile）

- **WHEN** UserProfile 管理模块具备可用 IP 地理信息与记录访问样本
- **THEN** `ipResidenceProfile` 至少包含：
  - `homeAreaByIp`（家常驻地，省市区粒度）
  - `officeAreaByIp`（办公常驻地，省市区粒度）
  - `studyAreaByIp`（学习常驻地，省市区粒度）
  - `ipGeoConfidence`（IP 地理推断置信度）
  - `ipGeoUpdatedAt`（最近更新时间）

### Requirement: UserProfile 管理边界与消费关系

系统 MUST 将用户“基础信息 + 画像”统一托管于 `UserProfile` 模型与管理模块。助手运行时仅消费快照，不得在推理链路中动态改写基础信息字段。

#### Scenario: 助手仅消费基础信息

- **WHEN** 19 垂类执行任务
- **THEN** 助手仅从 `userProfileSnapshot` 读取 `basicIdentity/ipResidenceProfile`，不得在运行时对年龄、性别、生日、常驻地做动态重算与覆盖写入

#### Scenario: 越用越聪明回流路径

- **WHEN** 助手产生学习信号（画像标签变化、满意度反馈、策略偏好变化）
- **THEN** 仅输出 `profileUpdateProposal`（更新建议）回流给 UserProfile 管理模块；由管理模块落库并支持用户修改/确认后生效

#### Scenario: 出生信息一致性校验提示

- **WHEN** 卜卦对话中用户提供的出生信息与 `UserProfile.basicIdentity` 已存信息不一致
- **THEN** 系统必须提示用户存在差异并请求确认是否更新基础信息，未确认前不得覆盖原值

### Requirement: `profileUpdateProposal` 字段契约（1.0）

系统 MUST 为 `profileUpdateProposal` 定义固定结构，用于“建议更新”回流，不得承载直接写库指令。

#### Scenario: 提案主结构固定

- **WHEN** run 输出 `profileUpdateProposal`
- **THEN** 顶层至少包含：
  - `proposalId`（唯一ID）
  - `profileVersionRead`（本次读取的 profile 版本）
  - `generatedAt`（提案生成时间）
  - `sourceRuns`（来源 runId 列表）
  - `confidence`（0~1）
  - `requiresUserConfirm`（是否必须用户确认）
  - `updates[]`（更新项数组）

#### Scenario: 更新项结构固定

- **WHEN** 输出 `updates[]`
- **THEN** 每项至少包含：
  - `facet`（如 `interestTopics/tonePreferences/basicIdentity/ipResidenceProfile`）
  - `path`（目标字段路径，如 `tonePreferences.communication_style_tags`）
  - `operation`（`set|add|remove|merge`）
  - `newValue`
  - `oldValueSnapshot`
  - `reason`
  - `evidenceRefs`（证据引用，如 trace/search 片段ID）
  - `itemConfidence`（0~1）
  - `riskLevel`（`low|medium|high`）

#### Scenario: 基础信息保护策略

- **WHEN** 更新项 `facet` 属于 `basicIdentity` 或 `ipResidenceProfile`
- **THEN** `requiresUserConfirm=true` 且 `operation` 不得为强制覆盖；仅允许“建议修改”，最终落库由 UserProfile 管理模块执行

---

### Requirement: 下一步引导与会话延续

系统 MUST 在最终回答中输出下一步引导建议（可选操作或继续对话提示），支持任务型对话与陪伴型对话的不同延续策略。

#### Scenario: 任务型下一步建议

- **WHEN** 回答属于任务解决场景（如旅行规划、选购、政策办理）
- **THEN** 至少给出 1-3 条可执行下一步建议

#### Scenario: 陪伴型继续对话引导

- **WHEN** 回答属于陪伴场景（emotion/social）
- **THEN** 给出低负担延续提示，帮助用户继续对话而不造成压迫感

---

### Requirement: 模板动态替换与 A/B 灰度

系统 MUST 支持模板版本动态替换、A/B 实验分流与指标回收；A/B 结果 MUST 绑定 `templateId/templateVersion/experimentBucket`。

#### Scenario: A/B 分桶执行

- **WHEN** 开启模板实验
- **THEN** 同类请求可按分桶命中不同模板版本，并记录分桶与结果指标

#### Scenario: 实验失败快速回滚

- **WHEN** 某模板实验版本导致关键指标下降
- **THEN** 系统可在不发版代码的前提下回滚到稳定模板版本

---

### Requirement: 模板 2.0 统一格式与边界

系统 MUST 采用“Markdown 模板正文 + JSON 元数据”的模板 2.0 格式。  
模板正文用于分章节表达任务背景、目标、约束、要求、规划、反思自检；  
元数据用于声明 `templateId/version/stage/requiredVariables/outputContract`。  
系统 MUST 禁止在业务代码中硬编码任何提示词正文。

#### Scenario: 模板章节结构统一

- **WHEN** 新增或更新任意模板
- **THEN** 必须包含固定章节：`任务背景/目标/约束/要求/任务规划(或前置检查)/输出格式/反思自检`

#### Scenario: 指令与数据分离

- **WHEN** 渲染模板
- **THEN** 指令与约束位于模板前段，数据位于模板末尾 `CONTEXT_DATA_START/CONTEXT_DATA_END` 区域，不得混放

#### Scenario: 提示词零硬编码

- **WHEN** 审查运行时代码
- **THEN** 不得存在模板正文字符串常量；代码仅可引用模板ID与变量绑定逻辑

---

### Requirement: 槽位驱动上下文填充与查询生成

系统 MUST 使用统一槽位模型驱动上下文填充。槽位至少包含 `status/source/value/queryPlan`。  
当槽位 `status=need_query` 时，系统 MUST 生成可执行查询任务，不得直接进入终态答案。

#### Scenario: 槽位缺失阻断终答

- **WHEN** 任一必填槽位未就绪
- **THEN** 输出 `ContextFillTask` 或 `GapFillTask`，并标记 `answerEligibility=blocked`

#### Scenario: 槽位填充链路可回放

- **WHEN** run 完成
- **THEN** 结构化响应可回放 `contextSlots/fillActions/missingCriticalSlots`

---

### Requirement: WebSearch 专项子流水线

当垂类需要联网证据时，系统 MUST 执行 `web_query_plan -> web_result_judge -> web_key_fact_extract -> web_evidence_pack` 子流水线。  
最终 `web_evidence_pack` MUST 作为该垂类答案模板输入。

#### Scenario: 垂类生成 web 查询条件

- **WHEN** 垂类判断需要联网补证
- **THEN** `web_query_plan` 输出结构化查询条件（单主题 query、providerHint、timeRange、stopCondition）

#### Scenario: 相关性判断与关键事实抽取

- **WHEN** 获取 web 检索结果
- **THEN** 先执行相关性判断，再执行关键事实抽取，形成可消费证据包

#### Scenario: 证据包不足继续补查

- **WHEN** `web_evidence_pack` 覆盖率或置信度不足
- **THEN** 不得终答，必须触发补查或返回缺口说明

---

### Requirement: 结构化答案含反思与诊断

最终答案 MUST 为结构化输出，至少包含：  
`result/evidence/reasoningBasis/selfCheck/diagnostics`。  
`selfCheck` 未通过时 MUST 返回补齐需求，不得伪造确定性答案。

#### Scenario: 自检失败触发补齐

- **WHEN** `selfCheck` 任一关键项失败（覆盖/约束/安全/一致性）
- **THEN** 输出 `needMoreInfo=true` 并生成补齐任务

---

### Requirement: 垂类模板对标业界一流水准（无折扣）

19 个垂类模板 MUST 对标业界同类助手与垂类最佳实践，覆盖完整任务链路，不得使用“简单占位”“象征性模板”替代。  
系统 MUST 为每个垂类维护“能力完整性清单”（场景覆盖、约束覆盖、异常覆盖、风险覆盖、输出质量）并在发布前通过审计。

#### Scenario: 禁止象征性模板

- **WHEN** 模板仅包含简短泛化指令、缺少关键章节或缺少垂类特有规则
- **THEN** 判定该垂类模板不合格，禁止进入开发主分支与灰度

#### Scenario: 垂类能力完整性审计

- **WHEN** 垂类模板提交评审
- **THEN** 必须通过完整性检查：场景覆盖、检索策略、证据判断、答案规则、自检规则、失败回退与安全边界

#### Scenario: 对标基线达标

- **WHEN** 进行开发准入评估
- **THEN** 每个垂类必须提供可量化对标结果（正确性、覆盖率、稳健性、可解释性），任一垂类未达标则整体 No-Go

---

### Requirement: 可观测、评测与发布门禁

系统 MUST 提供 `plan/task/round/synthesis` 四层回放轨迹，并接入质量门禁（准确率、覆盖率、冲突率、P95、成本）。

#### Scenario: 轨迹完整可回放

- **WHEN** 查询单次 run
- **THEN** 可见 `ContextAssembly -> DomainPreconditionCheck -> FillTask -> Domain -> SynthesisReadinessCheck -> GlobalSynthesis`

#### Scenario: 质量不达标阻断放量

- **WHEN** 核心指标低于阈值
- **THEN** 阻断灰度扩量并触发回滚建议

---

## 统一模板清单（2总 + 19垂类）

- 总控模板：
  - `planner.global_plan`
  - `synthesizer.final_answer`
- 流水线模板：
  - `reasoning.precheck`
  - `planner.precondition_check`
  - `executor.domain_task`
  - `executor.requery_or_expand_scope`
  - `synthesizer.postcondition_check`
- 垂类模板：
  - `domain.<domainId>.task`
  - `domain.<domainId>.requery_or_expand_scope`
- 兜底模板：
  - `domain.fallback_general_search.task`
  - `guardrail.fallback_offline_response`
- 风险与质检模板：
  - `guardrail.safety_boundary`
  - `quality.self_check`

---

## 运行配置基线（统一）

- 网关与鉴权：`PERSONAL_ASSISTENT_ENABLE_API`、`PERSONAL_ASSISTANT_GATEWAY_TOKEN`
- 路由与门禁：domain 路由开关、前后置阈值、预算阈值
- 模板治理：模板版本、灰度比例、A/B 分桶策略
- 定位策略：精确/城市级/未知降级策略
- SLO 告警：告警分发、抑制窗口、自动降级与人工恢复

---

## 验收清单（统一）

- [ ] 单一规格可覆盖网关、推理、垂类、门禁、回放与发布门禁
- [ ] 缺失上下文时能生成并执行补齐任务，不会直接跳过门禁
- [ ] 汇总前不足会触发回流重跑，不会直接输出最终答案
- [ ] 模型提示词全部资产化，不在业务代码中硬编码
- [ ] 模板流水线具备前置输入契约、检索驱动条件与总结输出规则
- [ ] 最终答案包含“下一步怎么聊/怎么做”的引导建议
- [ ] 模板支持动态替换与 A/B 分桶，并可按指标回滚
- [ ] 四层轨迹与质量门禁在灰度中可实际观测
- [ ] 19 垂类均接入画像标签与满意度回灌闭环，能驱动检索与答案策略自适应
- [ ] 日志可回放路由评分、检索回合、提案生命周期，且敏感字段已脱敏

## 开发准入门禁（Go / No-Go）

进入开发阶段前，以下条件 MUST 全部满足：

- [ ] 2 个总控模板、19 个垂类模板（18主垂类+1兜底）已完成模板ID与变量字典定义
- [ ] 全部模板采用 Markdown+Meta 2.0 规范，模板正文零硬编码
- [ ] 每个模板必填输入、缺失补齐策略、检索条件输出结构已定义
- [ ] 模板满足“指令在前、数据在后”边界，且包含固定章节与反思自检项
- [ ] 19 个垂类模板均通过“业界一流水准完整性清单”审计，禁止象征性模板
- [ ] `emotion_companion` 与 `social_companion_chat` 的边界与切换规则已定义
- [ ] WebSearch 专项子流水线（query_plan/judge/extract/evidence_pack）已定义并接入垂类输入
- [ ] run 结构化响应字段已冻结（context/domain/synthesis/fillTasks/nextActions/experimentBucket/userProfileSnapshot/retrievalFeedback/learningSignals/profileUpdateProposal）
- [ ] run 结构化响应新增 `contextSlots/fillActions/reasoningBasis/selfCheck/diagnostics` 并完成契约冻结
- [ ] A/B 灰度与回滚阈值已定义并可观测
- [ ] `profileUpdateProposal` 契约、UserProfile 回流协议与日志输出清单已冻结
- [ ] 每个垂类完成对标验收报告（正确性/覆盖率/稳健性/可解释性），任一未达标则 No-Go

## 推荐阈值基线（可用于首期开发）

- 路由命中阈值：
  - 主垂类命中阈值 `domainMatchScore >= 0.62`
  - 低置信度阈值 `domainMatchScore < 0.45` 触发兜底评估
- 前置门禁阈值：
  - 必需槽位满足率 `requiredSlotsCoverage = 1.0`（硬要求）
  - 软槽位满足率 `optionalSlotsCoverage >= 0.6`
- 汇总充分性阈值：
  - 子意图覆盖率 `intentCoverage >= 0.80`
  - 证据充分度 `evidenceSufficiency >= 0.70`
  - 冲突闭合 `conflictResolved = true`
- 回流与检索阈值：
  - 单轮新增证据增益 `< 0.15` 且连续 2 轮则停止扩查
  - 单查询主题约束：`singleTopic=true`，多主题必须拆任务
- A/B 灰度与回滚阈值：
  - 主指标（有帮助率）相对基线下降 `>= 5%` 持续 2 个窗口即回滚
  - 错误率上升 `>= 3%` 或 P95 上升 `>= 20%` 持续 2 个窗口即回滚
- 兜底阈值：
  - 18 主垂类均 `< 0.45` 或主垂类后置不满足时进入 `fallback_general_search`
  - 兜底在线检索可用性 `< 0.95` 时触发离线能力边界回答
- 学习闭环阈值：
  - 画像标签入库置信度 `tagConfidence >= 0.65` 才可写入长期画像
  - 策略切换最小样本 `similarCaseCount >= 20` 且满意度差值 `>= 8%`
  - 低满意纠偏触发：同垂类 7 天窗口满意度 `< 0.70` 或连续 3 次低满意
- 评测抽查与发布门槛：
  - 人工辅助抽查比例：`10%`
  - 分项门槛：`allScoreItems >= 80`
  - 关键分项门槛：`transitionAccuracyScore/globalRuleComplianceScore/safetyBoundaryScore >= 90`

## 领域窗口词表扩展策略（行业可扩展）

系统 MUST 支持窗口词表按行业扩展定义，默认使用 `近期/近阶段/后势/逢节点`，并允许行业包在不改代码前提下增补词表映射。

#### Scenario: 行业窗口词表扩展

- **WHEN** 新行业接入需要不同应期表达（如交易日窗口、班次窗口、学期窗口）
- **THEN** 系统通过配置扩展窗口词表并在模板渲染时按行业映射，不影响基础状态机契约字段

## 垂类扩展策略（从兜底持续细化）

系统 MUST 支持从兜底域持续沉淀新垂类：当 `fallback_general_search` 在某主题连续高频触发并达到质量阈值时，应将该主题升级为新主垂类或细化既有主垂类子域。

#### Scenario: 从兜底升级新垂类

- **WHEN** 同主题兜底请求在统计窗口内达到频次阈值且质量稳定
- **THEN** 系统进入“新垂类候选”流程，输出新垂类提案（输入契约、模板、门禁与验收指标）

## 残余风险与收敛计划（补充）

- `P1` 字段类型漂移风险：`profileUpdateProposal.updates[].newValue` 仍可能因 `facet/path` 不同而出现类型不一致。
  - 收敛要求：必须补齐 `facet/path -> valueType` 映射表，并在序列化校验中强约束。
- `P1` 回流协议不确定风险：`profileUpdateProposal` 已定义，但回流到 UserProfile 的传输协议（同步 API/异步事件）未冻结。
  - 收敛要求：冻结 `profile_update_proposal.created|approved|rejected|applied` 事件或等价 API 契约，并记录幂等键。
- `P1` 日志覆盖不足风险：若未输出“路由评分、检索回合、提案生命周期”，将无法复盘策略正确性。
  - 收敛要求：日志必须覆盖 `domainRouting/retrievalRounds/profileProposalLifecycle` 三类结构化字段。
- `P2` 隐私与合规风险：IP 常驻地与生日属于敏感信息，若无脱敏与留存策略会增加合规风险。
  - 收敛要求：日志与埋点仅允许脱敏值，且定义保留周期、删除策略、用户撤回后清理路径。
- `P1` 记录会话聚类能力缺口风险：若仅在算卦域局部实现，会导致跨垂类学习闭环断裂。
  - 收敛要求：将“记录会话聚类服务”作为全垂类共享基础能力排入存量任务清单，定义里程碑与验收口径（覆盖率、可解释性、策略增益）。

#### Scenario: 残余风险收敛达标

- **WHEN** 团队准备进入灰度发布
- **THEN** 上述 `P1/P2` 收敛要求必须在实现清单与测试清单有对应项，否则不得扩量
