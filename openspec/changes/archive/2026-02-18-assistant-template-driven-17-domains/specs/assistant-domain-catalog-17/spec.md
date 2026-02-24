## ADDED Requirements

### Requirement: 19 垂类统一目录
系统 MUST 提供 19 个标准化垂类目录（18 主垂类 + 1 大搜兜底垂类）。18 个主垂类包含：`weather`、`travel_transport`、`travel_planning`、`local_life`、`calendar_task`、`knowledge_general`、`finance_consumer`、`health_wellness`、`education_learning`、`work_productivity`、`shopping_decision`、`policy_public_service`、`emotion_companion`、`social_companion_chat`、`relationship_matchmaking`、`divination_fortune`、`astrology_constellation`、`family_parenting`。  
其中 `emotion_companion` MUST 支持持续情感陪伴与疏导式对话（continuous chat），`social_companion_chat` MUST 作为“闲聊/话题陪聊”主垂类并支持持续会话。

#### Scenario: 垂类可被规划层路由
- **WHEN** 总规划识别到跨域问题
- **THEN** 任务可映射到上述 19 垂类之一，并输出可执行 task 列表

### Requirement: 大搜兜底域（计入 19）
系统 MUST 提供 `fallback_general_search` 作为第 19 个垂类。该垂类在未命中 18 主垂类或主垂类执行不足时可触发，并承担“可联网大搜/离线能力边界”分支职责。

#### Scenario: 主垂类不足触发兜底
- **WHEN** 主垂类未命中、命中置信度低或后置条件未满足
- **THEN** 系统触发 `fallback_general_search` 并执行在线/离线分支策略

### Requirement: 每垂类输入输出契约
每个垂类 MUST 采用统一输入输出结构：输入含 `subQuestion/contextEnvelope/priorDomainResults/requiredSlots/userProfileSnapshot/historicalRetrievalFeedback`，输出含 `answerDraft/evidence/confidence/uncertainty/missingSlots/gapFillSuggestion/learningSignals/feedbackUpdate`。

#### Scenario: 垂类输出可机器校验
- **WHEN** 任一垂类任务执行完成
- **THEN** 返回结构满足统一契约，且可被汇总门禁直接消费

#### Scenario: 历史满意度参与垂类决策
- **WHEN** 某垂类执行新一轮检索与答案生成
- **THEN** 必须参考该垂类历史雷同问题的满意度结果，显式输出策略沿用或策略切换原因

### Requirement: 垂类模板与安全边界
每个垂类 MUST 拥有独立模板 `domain.<domainId>.task` 与补查模板 `domain.<domainId>.requery_or_expand_scope`，并声明风险边界与免责声明策略。

#### Scenario: 高风险垂类安全输出
- **WHEN** 执行 `divination_fortune`、`astrology_constellation`、`relationship_matchmaking` 或 `emotion_companion`
- **THEN** 输出包含不确定性与安全提示，避免绝对化结论

#### Scenario: 情感陪伴持续聊边界
- **WHEN** 执行 `emotion_companion` 持续对话
- **THEN** 输出需包含情绪状态跟踪、微行动建议与风险监测字段，不得退化为泛闲聊

#### Scenario: 闲聊持续会话边界
- **WHEN** 执行 `social_companion_chat` 持续对话
- **THEN** 输出需包含话题推进、用户兴趣锚点与下一轮轻引导字段，不得退化为情绪疏导处置流

### Requirement: 垂类持续扩展机制
系统 MUST 支持后续扩展新垂类：可从 `fallback_general_search` 高频主题中抽象新垂类，或在既有 18 主垂类下细化子垂类，并保持模板ID与输入输出契约向后兼容。

#### Scenario: 从兜底沉淀新垂类
- **WHEN** 某主题在兜底垂类中达到频次与质量阈值
- **THEN** 进入“新垂类候选”流程，输出候选ID、模板草案与门禁阈值建议

### Requirement: 19 垂类学习信号统一
系统 MUST 为 19 垂类统一产出学习信号，至少包含 `profileTagDelta`、`retrievalStrategyOutcome`、`answerFormatOutcome`、`satisfactionProxy`，用于后续 run 的策略自适应。

#### Scenario: 垂类学习信号可复用
- **WHEN** 用户再次进入同类问题
- **THEN** 规划层可直接消费上次学习信号，优先采用历史高满意策略

### Requirement: 画像 1.0 与垂类映射
系统 MUST 将 `userProfileSnapshot` 1.0 的五维偏好映射到 19 垂类策略入口，保证每个垂类至少消费一个兴趣子类目和两个行为偏好子类目。

#### Scenario: 垂类策略读取画像子类目
- **WHEN** 任一垂类执行 `domain.<domainId>.task`
- **THEN** 至少读取 `interestTopics` + (`decisionPreferences` 或 `riskPreferences` 或 `tonePreferences` 或 `spatiotemporalPreferences`) 形成策略输入

#### Scenario: 语气标签多选参与垂类输出
- **WHEN** 垂类任务生成最终文案
- **THEN** `tonePreferences.communication_style_tags` 支持多标签组合（如商务正式+尊敬、幽默诙谐+可爱），并由安全边界决定是否降级为稳健语气

#### Scenario: 垂类策略可读取基础身份与IP常驻地
- **WHEN** 垂类涉及地域、出行、时段、生活服务或学习工作场景
- **THEN** 允许读取 `basicIdentity` 与 `ipResidenceProfile` 作为补充上下文（年龄段、生日历法、家/办公/学习常驻地）

#### Scenario: 垂类对基础信息只读消费
- **WHEN** 任一垂类执行策略推理
- **THEN** 对 `basicIdentity/ipResidenceProfile` 仅做只读消费，不得在垂类执行阶段直接更新该类字段

### Requirement: 每垂类双模板分层（Plan/Answer）
19 个垂类 MUST 每域至少提供两类模板：  
`domain.<domainId>.plan`（规划推理/任务计划）与 `domain.<domainId>.answer`（答案生成）。  
系统 SHOULD 支持 `domain.<domainId>.requery` 作为补查模板。

#### Scenario: 垂类规划与答案分离
- **WHEN** 任一垂类执行
- **THEN** 先运行 `plan` 模板产出任务规划与检索策略，再运行 `answer` 模板生成终态答案

### Requirement: WebSearch 垂类子链路契约
对需要联网证据的垂类，系统 MUST 启用 `web_query_plan/web_result_judge/web_key_fact_extract/web_evidence_pack` 子模板链路。

`web_query_plan` 输出字段至少包含：`queryTasks[]`（`topicId/query/providerHint/timeRange/stopCondition`）。  
`web_result_judge` 输出字段至少包含：`relevantItems[]/irrelevantItems[]/relevanceScore`。  
`web_key_fact_extract` 输出字段至少包含：`keyFacts[]`（`fact/sourceRef/publishedAt/confidence`）。  
`web_evidence_pack` 输出字段至少包含：`coverage/confidence/conflictFlags/freshness/facts[]`。

#### Scenario: Web 证据包作为答案输入
- **WHEN** 垂类完成 web 子链路
- **THEN** 必须产出 `web_evidence_pack` 并作为 `domain.<domainId>.answer` 的输入变量

#### Scenario: Web 证据不足继续补查
- **WHEN** `web_evidence_pack.coverage` 或 `web_evidence_pack.confidence` 未达阈值
- **THEN** 必须触发 `domain.<domainId>.requery` 或 `GapFillTask`，不得直接终答

#### Scenario: Web 证据阈值冻结
- **WHEN** 团队进入开发实现阶段
- **THEN** 冻结首期阈值：`coverage >= 0.70`、`confidence >= 0.65`、`freshness <= 72h`（时效场景可按域收紧）

### Requirement: 垂类输出结构化诊断
每个垂类答案输出 MUST 包含结构化诊断字段，至少含：
`reasoningBasis/selfCheck/diagnostics/contextSlots/fillActions`。

#### Scenario: 垂类自检失败
- **WHEN** `selfCheck` 未通过
- **THEN** 垂类输出需显式标记失败项与补齐建议，供总控汇总门禁消费

### Requirement: 垂类模板完整性与业界对标清单
系统 MUST 为每个垂类定义并维护“模板完整性与业界对标清单”，至少覆盖：  
`核心场景`、`边界场景`、`异常场景`、`高风险场景`、`检索策略`、`证据抽取与判断`、`答案质量与自检`。  
系统 MUST 禁止以简化占位模板替代完整垂类模板。

#### Scenario: 垂类模板完整性检查
- **WHEN** 垂类模板进入评审
- **THEN** 若任一检查维度缺失（如异常场景或失败回退），该模板不得标记为 ready

#### Scenario: 业界对标达标
- **WHEN** 垂类进入开发准入门禁
- **THEN** 需提交该垂类对标结果（正确性、覆盖率、稳健性、可解释性）并达标，否则该垂类不得上线
