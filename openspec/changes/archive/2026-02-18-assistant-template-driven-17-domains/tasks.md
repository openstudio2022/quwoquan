## 1. 模板运行时基础设施

- [x] 1.1 新建模板目录结构：`assets/personal_assistant/prompts/planner|synthesizer|domains`
- [x] 1.2 实现模板注册表与加载器（按 `templateId/templateVersion` 寻址）
- [x] 1.3 实现模板变量绑定与必填变量校验
- [x] 1.4 实现模板灰度选择策略（环境/流量/用户分层）与回滚开关
- [x] 1.5 接入学习变量源（`userProfileSnapshot/historicalRetrievalFeedback/domainLearningSignals`）到模板渲染上下文

## 2. 总分总双门禁模板接入

- [x] 2.1 接入总1模板 `planner.global_plan` 到上下文组装与任务规划阶段
- [x] 2.2 接入 DomainPreconditionCheck，缺失时产出结构化 `ContextFillTask`
- [x] 2.3 接入总2模板 `synthesizer.final_answer` 与 `planner.postcondition_check`
- [x] 2.4 汇总门禁不满足时生成 `GapFillTask` 并触发重跑 domain

## 3. 19 垂类目录与模板

- [x] 3.1 定义 19 垂类目录与统一契约（18 主垂类 + 1 兜底垂类，输入、输出、前后置条件）
- [x] 3.2 为 19 垂类创建主任务模板 `domain.<id>.task`
- [x] 3.3 为 19 垂类创建补查模板 `domain.<id>.requery_or_expand_scope`
- [x] 3.4 为高风险垂类（卜卦/星座/婚配/情感）补充安全边界与免责声明模板
- [x] 3.5 增加 `fallback_general_search`（第 19 垂类）在线/离线分支模板与守卫模板
- [x] 3.6 增加垂类演进机制：从兜底高频主题细化新垂类，或细化既有 18 主垂类子域
- [x] 3.7 为 19 垂类定义学习信号输出契约（`profileTagDelta/retrievalStrategyOutcome/answerFormatOutcome/satisfactionProxy`）
- [x] 3.8 定义画像 1.0 子类目字典（兴趣/决策/风险/语气/时空）并完成 19 垂类映射
- [x] 3.9 扩展画像 1.0 基础身份字段（年龄/性别/阳历生日/农历生日）与 IP 常驻地字段（家/办公/学习）
- [x] 3.10 将语气偏好升级为多标签字段 `communication_style_tags`（含商务正式/幽默诙谐/可爱/尊敬）并接入19垂类

## 4. run 结构化响应与协议升级

- [x] 4.1 扩展 `AssistantRunRequest` 支持设备/GPS上下文字段并完成兼容反序列化
- [x] 4.2 扩展 `AssistantRunResponse` 新增结构化阶段结果（context/domain/synthesis/fill tasks）
- [x] 4.3 在 `AgentLoop` 输出结构化响应，前端可直接渲染补齐任务卡片
- [x] 4.4 保持 `finalText/traces` 向后兼容，确保旧客户端可继续使用
- [x] 4.5 在 run 结构化响应中增加学习闭环字段（`userProfileSnapshot/retrievalFeedback/learningSignals/strategySelectionReason`）
- [x] 4.6 在 run 结构化响应中增加画像快照元字段（`profileVersion/snapshotAt/confidenceByFacet/sourceRuns`）
- [x] 4.7 在 run 结构化响应中增加 `basicIdentity/ipResidenceProfile` 字段并保持兼容
- [x] 4.8 在 run 结构化响应中增加 `profileUpdateProposal` 字段（仅建议回流，不直接改写基础信息）
- [x] 4.9 定义 `profileUpdateProposal` 字段契约并完成序列化/反序列化校验

## 5. 可观测与日志升级

- [x] 5.1 记录模板运行时元数据（templateId/templateVersion/variableBindings）
- [x] 5.2 记录双门禁阶段摘要（contextAssembly/domainPrecheck/domainExecution/synthesisReadiness）
- [x] 5.3 记录回流补齐链路（触发原因、补齐策略、回流轮次）
- [x] 5.4 更新日志导出内容，确保结构化响应与模板元数据可回放
- [x] 5.5 记录学习闭环轨迹（画像标签变化、满意度信号、策略切换与效果）
- [x] 5.6 增加 UserProfile 消费/回流日志（读取的 `profileVersion`、回流提案ID、是否被用户确认）
- [x] 5.7 增加路由可观测日志（`candidateDomains/domainScores/selectedDomains/fallbackReason`）
- [x] 5.8 增加检索回合日志（`retrievalRound/queryId/topicId/singleTopic/providerHint/usedHistoricalStrategy`）
- [x] 5.9 增加提案生命周期日志（`proposalStatus/statusChangedAt/changedBy/idempotencyKey`）
- [x] 5.10 增加敏感字段脱敏与保留策略日志（生日/IP常驻地脱敏、删除标记）

## 6. 规格统一与记录目录清理

- [x] 6.1 将主能力升级统一写入 `openspec/specs/personal-assistant/spec.md`
- [x] 6.2 将 `personal-assistant-commercial-v1` 改为“已合并”迁移说明
- [x] 6.3 将 `personal-assistant-domain-orchestration-v1` 改为“已合并”迁移说明
- [x] 6.4 清理记录规格中与统一规格重复且会产生歧义的条款

## 7. 测试与灰度发布

- [x] 7.1 新增模板运行时单测（加载、变量校验、灰度选择、回滚）
- [x] 7.2 新增双门禁集成测试（前置阻断、后置回流、补齐重跑）
- [x] 7.3 新增 19 垂类契约测试（输入输出结构与风险边界）
- [x] 7.4 执行灰度验收（准确率、覆盖率、冲突率、P95、成本）并固化回滚阈值
- [x] 7.5 新增学习闭环测试（标签提取准确性、满意度回灌正确性、策略切换有效性）
- [x] 7.6 新增画像 1.0 子类目测试（子类目覆盖率、映射正确性、回放一致性）
- [x] 7.7 新增“阳历转农历”与“IP常驻地推断”测试（准确性、稳定性、回放一致性）
- [x] 7.8 新增语气多标签测试（多标签并存、优先级冲突、高风险场景降级）
- [x] 7.9 新增 UserProfile 边界测试（基础信息只读消费、学习结果提案回流、用户修改后生效）
- [x] 7.10 新增 `profileUpdateProposal` 契约测试（字段完整性、操作合法性、基础信息强确认）
- [x] 7.11 新增日志完备性测试（路由评分、检索回合、提案生命周期、敏感字段脱敏）

## 8. 模板2.0规范升级（补充）

- [x] 8.1 将总控与垂类模板从 `*.json` 提示词正文迁移为 `*.md + *.meta.json` 双文件格式（文件名去掉 v1）
- [x] 8.2 实现模板章节规范校验（任务背景/目标/约束/要求/规划或前置检查/输出格式/反思自检）
- [x] 8.3 实现“指令在前、数据在后”边界校验（`CONTEXT_DATA_START/END`）
- [x] 8.4 清理运行时代码中的提示词正文硬编码，仅保留模板ID与变量绑定逻辑
- [x] 8.5 冻结模板元数据契约（templateId/version/stage/requiredVariables/outputContract/selfCheckRules）

## 9. 槽位填充与 WebSearch 子流水线（补充）

- [x] 9.1 定义统一上下文槽位契约（`status/source/value/queryPlan`）并接入 run 结构化输出
- [x] 9.2 实现槽位 `need_query` 到 `ContextFillTask/GapFillTask` 的自动生成逻辑
- [x] 9.3 为需联网垂类接入 `web_query_plan` 子模板（结构化查询条件生成）
- [x] 9.4 实现 `web_result_judge` 子模板（相关性判断与过滤）
- [x] 9.5 实现 `web_key_fact_extract` 子模板（关键信息与证据抽取）
- [x] 9.6 实现 `web_evidence_pack` 子模板并注入 `domain.<id>.answer` 输入
- [x] 9.7 增加证据包阈值门禁：`coverage/confidence` 未达标时阻断终答并触发补查

## 10. 结构化答案反思与诊断（补充）

- [x] 10.1 扩展答案输出契约：`result/evidence/reasoningBasis/selfCheck/diagnostics`
- [x] 10.2 增加自检失败阻断策略（`needMoreInfo=true` + 补齐任务）
- [x] 10.3 在 run 结构化响应中增加 `contextSlots/fillActions/missingCriticalSlots/answerEligibility`
- [x] 10.4 新增模板与输出契约映射表，确保 plan/answer/requery 输出格式可机器校验

## 11. 补充测试与验收（补充）

- [x] 11.1 新增模板2.0格式测试（md+meta配对、章节完整性、边界标记）
- [x] 11.2 新增“零硬编码提示词”静态扫描测试（personal_assistant runtime scope）
- [x] 11.3 新增槽位状态机测试（ready/need_query/unavailable）
- [x] 11.4 新增 WebSearch 子流水线集成测试（query->judge->extract->pack）
- [x] 11.5 新增结构化答案契约测试（reasoningBasis/selfCheck/diagnostics）
- [x] 11.6 新增日志完备性补充测试（模板边界、槽位填充、web子链路、自检诊断）

## 12. 垂类对标与质量门禁（补充）

- [x] 12.1 为 19 垂类建立“业界对标完整性清单”（核心场景/边界场景/异常场景/风险场景/失败回退）
- [x] 12.2 为每个垂类补齐对标级模板内容（禁止象征性或占位式模板）
- [x] 12.3 建立模板质量审计器：拦截“过短模板、缺章节模板、缺垂类规则模板”
- [x] 12.4 为每个垂类输出对标验收报告（正确性/覆盖率/稳健性/可解释性）
- [x] 12.5 将“任一垂类不达标即 No-Go”接入开发门禁脚本
- [x] 12.6 新增对标质量测试集（每垂类至少核心+边界+异常+高风险样例）
