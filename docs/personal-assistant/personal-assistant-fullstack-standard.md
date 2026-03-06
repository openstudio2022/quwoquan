# 小趣个人助理全栈原理、方案与流程（新规范基线）

## 0. 从属关系（强制）

- 本文档用于“个人助理域”落地解释，不是仓库总规范。
- 必须遵从：
  - `specs/00_MASTER_DEVELOPMENT_FLOW.md`
  - `specs/feature-tree/00_FEATURE_TREE_STANDARD.md`
- 若出现不一致，以仓库主线和特性树标准为唯一准绳。

## 1. 系统原理总览

小趣个人助理采用“系统策略 + 领域 Skill + 工具契约 + ReAct 执行”四层架构：

1. 系统策略层（Prompt Stack）
   - 全局边界、运行策略、恢复策略、输出契约。
2. 领域策略层（Skill）
   - 垂类目标、工具策略、对话状态、卡片结构。
3. 能力执行层（Tool Fabric）
   - 工具 schema 校验、统一执行、统一错误封装。
4. 运行编排层（AgentLoop + ReactRuntime）
   - 单循环调度、工具观察、重规划、最终合成。

## 2. 目标方案（世界水准）

### 2.1 运行目标
- 能回答：高质量 Markdown 结果。
- 能做事：结构化工具调用与结果回注。
- 能恢复：失败后自动重试/降级/补槽追问。
- 能扩展：多 Skill、多工具、多子代理统一编排。

### 2.2 协议目标
- 机器轨：`assistant_turn_v2`
- 观测轨：`tool_observation_v1`
- 子代理轨：`subagent_plan_v1` / `subagent_result_v1`
- 本地上下文轨：`local_context_v1`

### 2.3 隐私目标
- 默认最小权限，不做恐慌式能力宣告。
- 设备能力调用由模型结构化决策触发，不由写死文案触发。
- `local_context` 不包含相册内容，`media.included=false`。

## 3. 全流程标准流程

### Plan
- 明确问题、目标、非目标、风险边界。
- 输出方案对比与选型，不直接进入实现。

### Create
- 在特性树节点生成四件套：`spec/design/tasks/acceptance`。
- 先定义契约与状态机，再进入代码接线。

### Implement
- 按“metadata -> codegen -> logic -> tests”顺序实施。
- 每个任务完成即回填设计映射与验收映射。

### Verify
- 校验文档、代码、契约、测试四链路一致性。
- 关键指标门禁达标后进入提交。

### Submit
- 无闭环不提交：设计-任务-验收-测试必须全映射。

## 4. 架构交付件规范（L1 强化）

每个 L1 `design.md` 至少包含：
1. 组件/包图（Component + Package）
2. 用例图（Use Case）
3. 流程图（主流程 + 失败流程）

每张图必须附：
- 适用范围与约束
- 代码实现映射
- tasks/acceptance/tests 映射

## 5. 关键实现约束

- 禁止关键路径 `contains("中文文案")` 决策。
- 禁止领域策略散落在 `llm_provider` 中写死分支。
- 领域策略统一下沉到 Skill 与状态契约。
- 工具输入与输出都要做 schema 校验。
- 任何结构解析失败都必须可降级，不能中断会话。

## 6. 增量开发策略（逆向生成 + 补齐）

当历史目录不完整时，按以下顺序逆向补齐：
1. 从代码逆向当前流程图与组件边界。
2. 从 trace 与测试逆向协议输入输出。
3. 生成/补齐特性树四件套。
4. 再做代码增量改造，避免“边改边漂移”。

## 7. 验收标准（核心）

- 协议解析成功率：`decision_parse_success >= 99.5%`
- 渲染降级率：`render_fallback_rate < 1%`
- 启发式回退占比：`heuristic_fallback_ratio < 1%`
- 天气类补槽完成率：城市缺失场景 >= 95%

## 8. 当前落实策略

- 文档已统一到“全流程标准”，不再是 Skill 局部规范。
- 个人助理原理、方案、流程按统一模板归档在 `docs/personal-assistant/`。
- 后续任何新增垂类必须先过文档标准与契约测试，再接 runtime。
