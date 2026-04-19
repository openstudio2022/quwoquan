# 小趣私人助理：Skill 增强多 agent 正式规格书

> **状态**：Milestone 1 Frozen / M6 Defined  
> **用途**：冻结 skill 增强的三阶段主线、并行 subagent 机制、澄清策略、局部回答策略、跨问题历史策略与最终集成验收  
> **前置阅读**：`PERSONAL_ASSISTANT_DESIGN_AND_CONSTRAINTS.md`、`PERSONAL_ASSISTANT_SKILL_AND_TOOL_EXTENSIBILITY.md`、`skill-directory-and-progressive-disclosure-design.md`

---

## 1. 目标

本规格定义小趣私人助理的 skill 增强主线：将用户问题路由到 1 到 n 个 skill 候选，由多个 subagent 并行完成独立检索与局部总结，最终由汇总阶段基于各 skill 的总结与采纳证据统一成答。

### 1.1 设计目标

- 统一接入 skill 增强，不再区分“技能路径”和“非技能路径”
- 支持单问题内的多 skill 并行执行
- 支持每个 skill 的独立检索设计、独立结果处理、独立局部总结
- 支持必要时的多点澄清，且澄清应一次性给出
- 支持局部回答：即使某个 skill 失败，也不阻塞已完成部分
- 支持跨问题历史保存与接续
- 保持输入、输出、状态、历史均尽量轻量

### 1.2 非目标

- 不做规则召回
- 不做关键词硬过滤
- 不做重型共享计划对象
- 不做全量技能目录直塞模型
- 不做多套冲突 prompt 文本

---

## 2. 总体流程

本系统统一为三阶段：

1. `skill_route`
2. `skill_subagent_turn`
3. `skill_synthesis`

### 2.1 阶段一：`skill_route`

职责：
- 理解用户意图
- 判断是否需要澄清
- 选出 1 到 n 个 skill 候选
- 生成面向用户的并行处理叙事
- 如果没有选中具体 skill，则落到 `search_fallback`

输出要求：
- 只保留最小路由结果
- 支持 primary / supporting 关系
- 支持多 skill 一次返回
- 支持一次性澄清点列表

### 2.1.1 里程碑 2 输出即里程碑 3 输入

阶段一的输出必须足够支撑阶段二的并行 subagent 执行，至少包括：

- `selectedTargets`
- `routeNarrative`
- `needClarify`
- `pendingClarifications`
- 每个目标 skill 的 `role`
- 每个目标 skill 的 `taskBrief`
- 每个目标 skill 的局部上下文种子

如果这些字段不足，则不能进入并行 subagent 执行，必须先补足澄清或补路由。

### 2.2 阶段二：`skill_subagent_turn`

职责：
- 每个 skill 候选独立执行
- 每个 subagent 独立设计检索
- 每个 subagent 独立处理工具调用
- 每个 subagent 独立产出局部总结
- 每个 subagent 独立记录采纳证据与失败原因

要求：
- 候选之间互不污染
- 允许并行执行
- 允许部分完成
- 允许局部挂起

### 2.2.1 里程碑 3 输入检查

阶段二在执行前必须确认以下输入已齐备：

- 当前 skill 候选清单已明确
- 每个候选都有独立 `taskBrief`
- 路由叙事已说明为何要并行处理
- 每个候选的预算已分配
- 每个候选的局部上下文已准备
- 待澄清点已拆分到对应候选

如果某个候选缺少必要输入，该候选可挂起，但不应阻塞其他已就绪候选。

### 2.3 阶段三：`skill_synthesis`

职责：
- 汇总所有 subagent 的局部总结
- 汇总各自采纳的关键证据
- 消解冲突
- 生成最终答案与下一步建议

要求：
- 最终答案必须基于各 skill 的汇总与证据
- 若存在未完成 skill，可先输出局部可交付结果并标记待补全
- 若用户补充信息后，只继续挂起的局部 skill，再重新汇总

---

## 3. 澄清策略

### 3.1 澄清触发原则

只在必要时澄清。以下情况才澄清：

- 关键槽位缺失，不补无法可靠继续
- 多个候选 skill 都无法确定主次
- 信息缺失会直接影响正确性或安全性

### 3.2 多点澄清一次给出

当需要澄清时，应一次性给出勾选式澄清点，而不是逐点追问。

澄清项可包括：
- 时间范围
- 地点
- 预算
- 偏好
- 目标优先级
- 约束条件

### 3.3 允许部分完成

用户若只补全部分信息：

- 已满足的 skill 继续执行
- 未满足的 skill 挂起
- 能局部回答的先局部回答
- 再提示用户补全剩余信息以提升结果

### 3.4 不必要就不打断

如果：
- 用户表达不满
- 输入与澄清不相关
- 系统已可局部回答

则应先输出局部答案，再在末尾提示可补充的少量信息，不得强行打断主线。

---

## 4. 并行 subagent 规则

### 4.1 子代理定义

每个 subagent 对应一个 skill 候选，独立负责：

- 自己的检索设计
- 自己的工具调用
- 自己的证据采纳
- 自己的局部总结
- 自己的失败 / 挂起状态

### 4.2 子代理输出

每个 subagent 只输出以下最小信息：

- `skillId`
- `role`
- `localSummary`
- `acceptedEvidence`
- `rejectedEvidence`
- `nextAction`
- `missingSlots`
- `failureReason`

### 4.3 汇总要求

最终汇总阶段只消费：

- 各 subagent 的 `localSummary`
- 各 subagent 的 `acceptedEvidence`
- 各 subagent 的 `rejectedEvidence`
- 各 subagent 的 `missingSlots`
- 各 subagent 的 `failureReason`

不回放完整思考链，不保留重状态。

---

## 5. 历史保存

### 5.1 当前会话状态

每个会话只保留：
- `selectedTargets`
- `routeNarrative`
- `subagentStates`
- `pendingClarifications`
- `sessionSummary`
- `budget`

### 5.2 跨轮历史状态

只保留：
- `completedSkillSummaries`
- `pendingSkillStates`
- `userPreferences`
- `lastAcceptedEvidenceSummary`

### 5.3 保存原则

- 已完成 skill 的结果必须保留
- 未完成 skill 可挂起
- 用户补全后继续同一问题的局部子会话
- 跨问题可复用用户偏好，但不得污染当前问题

---

## 6. 轻量输入输出原则

### 6.1 输入

路由阶段只给：
- 用户原始问题
- 最近会话摘要
- 目录树摘要
- 最小策略标记

子代理阶段只给：
- 当前 skill 候选
- 当前局部上下文
- 当前预算
- 必要的 skill pack

### 6.2 输出

每阶段输出都尽量短：
- 路由阶段输出路由与并行叙事
- 子代理阶段输出局部总结与证据
- 汇总阶段输出最终答案与下一步建议

---

## 7. 验收标准

### 7.1 路由验收

- 一个问题可选出 1 到 n 个 skill
- 支持一次性给出多点澄清
- 没有必要时不得强制澄清
- 要能表达 primary / supporting 关系

### 7.2 并行执行验收

- 每个 skill 独立处理
- 一个 skill 的失败不影响其他 skill
- 支持局部完成、局部挂起、局部恢复

### 7.3 汇总验收

- 最终答案必须基于各 skill 汇总与采纳证据
- 能先局部回答，再在用户补全后继续统一成答
- 有下一步建议

### 7.4 历史验收

- 同一问题链可以多轮完成
- 跨问题可复用偏好
- 历史不污染当前问题

---

## 8. Milestone 1 Freeze

### 8.1 冻结内容

Milestone 1 仅冻结以下内容：
- 三阶段总流程：`skill_route` / `skill_subagent_turn` / `skill_synthesis`
- 并行 subagent 原则
- 多点澄清策略
- 局部回答策略
- 历史保存原则
- 轻量输入输出原则

### 8.2 冻结结论

冻结后，后续里程碑 2 到 6 仅可在该规格下展开实施，不再变更主流程与核心状态原则。

---

## 9. Milestone 6：最终集成验收

### 9.1 定义

Milestone 6 不是新增能力点，而是对里程碑 2 到 5 的统一收口与端到端验收层。

它验证的是一条完整问题链是否能稳定完成：

`skill_route` -> `skill_subagent_turn` -> `skill_synthesis` -> `Finalize`

### 9.2 验收边界

Milestone 6 只验收最终集成效果，不再单独引入新的状态实体或新的路由分支。

它必须同时满足：
- 路由阶段可输出 1 到 n 个 skill 候选
- 并行 subagent 阶段彼此隔离，单个失败不污染其他候选
- 汇总阶段只消费各 skill 的局部总结与采纳证据
- 局部完成、澄清补全、重新汇总、跨轮接续都能稳定闭环
- 最终输出、过程叙事、历史保存三者一致

### 9.3 最小验收矩阵

- **路由集成验收**：一次问题可以完成多 skill 路由、primary / supporting 标注、一次性澄清列表输出
- **并行执行验收**：每个 skill 独立设计检索、独立调用工具、独立产出总结，且失败不扩散
- **汇总验收**：最终答案必须基于各 skill 汇总与采纳证据，支持先局部回答后统一成答
- **历史验收**：同一问题链可多轮完成，跨问题只保留轻量摘要且不污染当前问题
- **终局验收**：`Finalize` 写回的 display / process / history 视图必须与最终答案和 trace 对齐

### 9.4 出口条件

Milestone 6 只有在以下条件同时满足时才算通过：
- M2 到 M5 的对应验收全部通过
- 没有新的 Map 语义回流到主链路
- 连续叙事、局部完成、补全再成答、历史接续均可回放
- 关键失败场景能够稳定降级，不会把异常直接暴露成无补救的终止态

