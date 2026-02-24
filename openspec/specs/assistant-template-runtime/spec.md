# assistant-template-runtime

## Purpose

个人助手模板运行时规范：支持从模板资产动态加载、变量绑定校验、学习上下文注入、灰度与回滚。供 personal-assistant 引擎调用。

---

## ADDED Requirements

### Requirement: 模板运行时注册与动态加载
系统 MUST 提供模板运行时能力，支持从模板资产目录动态加载总控模板与垂类模板，并按 `templateId/templateVersion` 进行注册与寻址。

#### Scenario: 运行时按模板ID加载
- **WHEN** 助手启动一次 run
- **THEN** 系统可按 `templateId` 加载模板正文与变量定义，而非读取硬编码提示词

### Requirement: 模板变量绑定与校验
系统 MUST 在渲染模板前执行变量绑定校验，缺失必填变量时返回结构化错误并触发补齐任务，而非静默降级为错误回答。

#### Scenario: 必填变量缺失
- **WHEN** 模板要求 `gps_lat/gps_lng` 但上下文无该字段
- **THEN** 系统返回 `missing_template_variables` 并生成 `ContextFillTask`

### Requirement: 学习上下文变量注入
系统 MUST 支持将历史学习结果作为模板变量注入，至少包含 `userProfileSnapshot`、`historicalRetrievalFeedback`、`domainLearningSignals`。

#### Scenario: 历史学习变量可用于模板渲染
- **WHEN** 执行 19 垂类任一模板
- **THEN** 模板可读取用户画像标签与历史满意度摘要，驱动 query 生成与答案组织

#### Scenario: 基础信息变量来源受控
- **WHEN** 模板读取 `basicIdentity/ipResidenceProfile`
- **THEN** 变量来源必须是 UserProfile 快照，不允许在模板渲染时临时重算或覆盖基础信息

#### Scenario: 提案变量结构受控
- **WHEN** 模板生成 `profileUpdateProposal`
- **THEN** 输出必须遵循固定字段契约（proposalId/profileVersionRead/generatedAt/sourceRuns/confidence/requiresUserConfirm/updates[]），不允许输出直接写库指令

### Requirement: 模板灰度与回滚
系统 MUST 支持模板版本灰度发布与快速回滚，灰度策略 SHALL 支持按环境、用户分层或流量比例选择模板版本。

#### Scenario: 模板灰度切换
- **WHEN** 新模板版本在小流量验证中出现质量下降
- **THEN** 系统可回滚到上一稳定版本并保留回滚审计记录

#### Scenario: 基于历史满意度的策略模板选择
- **WHEN** 同一垂类存在多个模板策略版本
- **THEN** 系统可结合历史满意度与样本量进行策略优选，并保留可回放选择依据

### Requirement: 模板文件格式与数据指令分离
系统 MUST 采用"模板内容（Markdown）+ 模板元数据（JSON）"双文件格式。  
模板内容用于指令、约束、章节化说明；元数据用于 `templateId/version/stage/requiredVariables/outputContract` 等机器可读信息。  
系统 MUST 严格执行"指令在前、数据在后"边界：数据区必须位于模板尾部，且由统一标记包裹。

#### Scenario: Markdown 模板章节统一
- **WHEN** 新增或更新任意模板
- **THEN** 模板正文必须包含固定章节：任务背景、目标、约束、要求、任务规划（或前置检查）、输出格式、反思自检

#### Scenario: 数据区边界固定
- **WHEN** 渲染模板
- **THEN** 模板数据区必须位于 `CONTEXT_DATA_START` 与 `CONTEXT_DATA_END` 之间；指令区不得注入原始上下文数据

### Requirement: 槽位驱动上下文填充
系统 MUST 采用统一上下文槽位模型渲染模板，每个槽位至少包含 `status/source/value/queryPlan`。  
当槽位 `status=need_query` 时，系统 MUST 生成可执行查询任务，不得直接输出终态答案。

#### Scenario: 槽位缺失触发补齐
- **WHEN** 任一必填槽位为 `need_query` 或 `unavailable`
- **THEN** 系统生成结构化 `ContextFillTask` 或 `GapFillTask`，并阻断终态答案生成

#### Scenario: 槽位补齐可回放
- **WHEN** run 完成
- **THEN** 结构化结果中可回放每个槽位的最终状态、数据来源与补齐动作链

### Requirement: WebSearch 专项槽位子流水线
当垂类依赖联网信息时，系统 MUST 将 `web_search` 作为专项槽位链路执行，至少包含四个模板阶段：  
`web_query_plan -> web_result_judge -> web_key_fact_extract -> web_evidence_pack`。  
系统 MUST 将最终 `web_evidence_pack` 作为该垂类答案模板输入之一。

#### Scenario: 垂类生成 web 查询条件
- **WHEN** 垂类模板判定需要联网检索
- **THEN** `web_query_plan` 输出结构化查询条件（单主题 query、providerHint、timeRange、stopCondition）

#### Scenario: 检索结果相关性判断与抽取
- **WHEN** 获得 web 检索原始结果
- **THEN** `web_result_judge` 必须输出相关性判断，`web_key_fact_extract` 必须输出关键事实与证据来源

#### Scenario: 证据包未达标阻断终答
- **WHEN** `web_evidence_pack` 覆盖率或置信度低于阈值
- **THEN** 系统不得进入终态答案模板，必须继续补查或返回缺失说明

### Requirement: 结构化输出包含反思与诊断
答案模板 MUST 输出结构化结果，并包含"推理依据、反思自检、诊断信息"。  
系统 MUST 在输出契约中固定 `result/evidence/reasoningBasis/selfCheck/diagnostics` 字段族。

字段最低要求：  
- `reasoningBasis`: `whyThisResult[]/rejectedAlternatives[]`  
- `selfCheck`: `constraintSatisfied/coverageSatisfied/safetySatisfied/consistencySatisfied/failedItems[]`  
- `diagnostics`: `missingInputs[]/riskFlags[]/assumptions[]/needMoreInfo/gapFillTasks[]`

#### Scenario: 自检不通过触发阻断
- **WHEN** `selfCheck` 任一关键项不满足（覆盖/约束/安全/一致性）
- **THEN** 输出必须标记 `needMoreInfo=true` 并给出补齐任务，不得伪造最终确定性答案

### Requirement: 禁止占位模板与简化模板
系统 MUST 在模板发布前执行质量审计，禁止"仅示意/仅骨架/象征性"模板进入运行时。  
每个模板 MUST 提供完整规则内容、场景覆盖与自检条目，不得以"后续补全"标记替代。

#### Scenario: 占位模板阻断发布
- **WHEN** 模板正文缺少垂类特有规则或仅包含泛化短指令
- **THEN** 模板状态必须保持非 active，不得参与灰度
