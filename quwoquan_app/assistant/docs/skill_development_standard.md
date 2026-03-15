# 个人助理开发与交付标准（全流程 v3）

> **收口说明**：当前助手增量开发优先阅读：
> - `PERSONAL_ASSISTANT_ARCHITECTURE_AND_FLOW.md`
> - `PERSONAL_ASSISTANT_SKILL_AND_TOOL_EXTENSIBILITY.md`
> - `PERSONAL_ASSISTANT_DESIGN_AND_CONSTRAINTS.md`
>
> 本文档保留为详细规范参考，核心约束已收口到上述三类文档。

本规范不再只约束 Skill，而是覆盖个人助理全链路开发：`Plan -> Create -> Implement -> Verify -> Submit`。  
Skill 只是其中一个子模块，需与运行时协议、提示词平台、工具织物、UI 渲染、观测门禁统一交付。

## 0. 从属关系（强制）
- 本文档是**个人助理子规范**，不是仓库总规范。
- 必须严格服从：
  - `specs/00_MASTER_DEVELOPMENT_FLOW.md`
  - `specs/feature-tree/00_FEATURE_TREE_STANDARD.md`
- 若与仓库主线或特性树标准存在冲突，以仓库主线和特性树标准为准。

## 1. 目标
- **稳定**：关键决策只依赖结构化协议，禁止关键路径字符串判断。
- **可扩展**：Prompt Stack、Skill、Tool、Subagent 可插拔。
- **可审计**：每次运行可回放（trace）、可验收（acceptance）、可门禁（tests）。
- **可产品化**：用户轨 Markdown 精美可读，机器轨 JSON 可执行。

## 2. 范围
- Runtime：`agent_loop`、`react_runtime`、`llm_provider`、`context_orchestrator`
- Skill：`assets/assistant/skills/*`
- Prompt：`assets/assistant/prompts/*`
- Tool：`tools/catalog` + `tool_registry` + 单工具实现
- UI：聊天页时间线、引用、动作卡片
- Docs：特性树四件套 + 个人助理 docs 汇总

## 3. 强制协议基线
- `assistant_turn`：每轮必须输出 canonical JSON 信封与用户轨 Markdown。
- `tool_observation_v1`：工具观测必须包含 `ok/status/errorClass/retryable/slotDelta/data`。
- `subagent_plan_v1/subagent_result_v1`：多代理编排必须结构化。
- `local_context_v1`：包含地理位置，不包含相册数据（`media.included=false`）。

## 4. 设计交付件统一格式（适用于所有节点，不只 Skill）
每个节点 `design.md` 固定包含：
1. 背景与问题定义
2. 目标与非目标
3. 方案对比与选型理由（至少 2 方案）
4. 架构图组（组件/包图、用例图、流程图）
5. 契约设计（输入输出、错误码、状态机）
6. 代码映射（组件 -> 目录/模块）
7. 验收映射（tasks 编号、acceptance 编号、测试用例）
8. 风险与回滚点
9. 未来演进

## 5. 目录规范
- 节点目录仅保留四件套：`spec.md`、`design.md`、`tasks.md`、`acceptance.yaml`
- 可选附图素材目录（不算第五类文档）：
  - `artifacts/architecture/component.mmd`
  - `artifacts/architecture/package.mmd`
  - `artifacts/architecture/usecase.mmd`
  - `artifacts/architecture/flow-main.mmd`
  - `artifacts/architecture/flow-failure.mmd`
- `design.md` 必须可独立阅读，不能只扔链接。

## 6. Skill 子规范（作为全流程一部分）
### 6.1 Frontmatter 必填
- `name`
- `description`
- `domain`
- `allowed_tools`
- `execution_shell`
- `output_contract`
- `tool_observation_contract`
- `reference_docs`
- `script_guides`
- `dialogue_state_docs`

### 6.2 Frontmatter 禁止
- `version`
- `owner`
- `risk_level`

### 6.3 正文必备章节
- `## 目标`
- `## 工具调用策略`
- `## 触发与禁用条件`
- `## 双轨输出契约`
- `## Markdown 卡片结构`
- `## 参考资料`
- `## 脚本指引`
- `## 轮次状态定义`

### 6.4 目录必备
- `SKILL.md`
- `references/`
- `scripts/`
- `dialogue/`（推荐 `state_machine.md` + `state_transition_contract.json`）

## 7. 全流程落地（强化措施）
### 7.1 Plan（G0）
- 必须完成：问题定义、非目标、方案对比、协议边界。
- 若涉及 L1：三图最小骨架必须在设计阶段形成。

### 7.2 Create（G1）
- 节点创建即写入四件套，且 `design.md` 含三图占位与映射表。
- 先 metadata/contract，再 codegen，再业务逻辑。

### 7.3 Implement（G2）
- 每完成一个任务，回填设计映射（实现路径、测试路径、验收编号）。
- 任何新增分支必须补失败流程图或状态迁移说明。

### 7.4 Verify（G3）
- 检查三类一致性：
  - 文档一致性：spec/design/tasks/acceptance
  - 契约一致性：metadata/runtime/ui
  - 测试一致性：任务与验收均有对应测试

### 7.5 Submit（G4）
- 未形成“设计-任务-验收-测试”闭环，不允许提交。

## 8. L1 架构交付最低标准
- `design.md` 必须包含：
  - 组件/包图（Component + Package）
  - 用例图（Use Case）
  - 流程图（主流程 + 失败流程）
- 每张图后必须附：
  - 适用范围与约束
  - 实现映射（目录/模块）
  - 验收映射（tasks/acceptance/tests）

## 9. 质量门禁
- `decision_parse_success >= 99.5%`
- `render_fallback_rate < 1%`
- `heuristic_fallback_ratio < 1%`

## 10. 推荐验证集
- `test/personal_assistant/skill_standard_contract_test.dart`
- `test/personal_assistant/tool_registry_contract_test.dart`
- `test/personal_assistant/react_runtime_tool_observation_contract_test.dart`
- `test/personal_assistant/structured_response_contract_test.dart`
- `test/personal_assistant/quality_metrics_gate_test.dart`

## 11. 执行要求（最终）
- 禁止关键执行路径使用 `contains("中文文案")` 决策。
- 禁止在业务层写死“是否要调用设备能力”的固定文案策略，必须由模型结构化决策驱动。
- 禁止 Skill 与域模板双源冲突；以 Skill + dialogue 契约为唯一领域策略来源。
