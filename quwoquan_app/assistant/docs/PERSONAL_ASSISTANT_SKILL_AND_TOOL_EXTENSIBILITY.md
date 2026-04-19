# 小趣私人助理：Skill 与 Tool 可扩展机制

> **定位**：小趣私人助理增量开发三类核心文档之一  
> **前置阅读**：`PERSONAL_ASSISTANT_ARCHITECTURE_AND_FLOW.md`
> **正式规格**：`PERSONAL_ASSISTANT_SKILL_MULTI_AGENT_SPEC.md`

---

## 1. 目标

本文件定义小趣私人助理的扩展边界：新增能力优先通过 skill 资产、tool metadata、prompt asset 和 config 落地，而不是在 runtime 中叠加垂类逻辑。

---

## 2. Skill 扩展机制

### 2.1 Skill 是什么

Skill 是某一业务路径下的模型主导会话资产，负责表达：

- 领域、（可选）子领域与具体 skill 的层级结构
- 该 skill 的目标、边界与完成标准
- 该 skill 的对话状态机与轮次推进
- 该 skill 的工具调用约束与参数指引
- 该 skill 的 few-shot 与最终输出要求

### 2.2 Skill 目录结构

```text
assets/assistant/skills/{domain}/
├── {skill}/
└── {subdomain}/
    └── {skill}/
```

### 2.3 各目录职责

- `SKILL.md`：技能主控文档，包含 skill 说明、边界与完成条件
- `references/`：模型可读的领域知识、工具指引、输出示例
- `dialogue/`：状态机、状态提示、事件判定与测试样例
- `scripts/`：始终加载的策略叠加层，例如 persona 和全局段落
- `config/`：结构化策略，如 `retrieval_policy.json`

### 2.4 运行时如何消费 Skill

1. `PersonalAssistantSkillLoader` 读取 asset
2. `AssistantSkillMarketService` / `AssistantCapabilityCatalog` 暴露目录树与常用技能
3. 第 1 次模型调用基于目录树选择领域、子领域、skill 或多 skill
4. `AssistantEdgeService` 装配当前运行时，并按选中 skill 加载指令与 dialogue 片段
5. ReAct 在阶段推进时按需注入 phase-aware 材料

### 2.5 Phase-aware 加载

| Phase | 典型来源 | 作用 |
|---|---|---|
| `bootstrap` | `SKILL.md` + `scripts/skill.policy.md` | 建立领域目标与语气基线 |
| `tool_call` | `references/tool-call-guidance.md` | 限制工具使用方式 |
| `ask_user` | `references/domain-knowledge.md` | 槽位追问、补齐信息 |
| `answer` | `references/output-examples.md` | few-shot 与回答结构 |

### 2.6 路由与会话约束

- 路由阶段只做模型选择，不做规则召回、不做关键词过滤
- 模型输入使用目录树摘要，每个子领域只展示 1 到 5 个常用 skill
- 模型可一次返回多个 skill，分别标记 primary / supporting
- 若未选中具体 skill，系统级默认 skill 必须根据当前领域/子领域继续承接
- 一旦选中 skill，后续会话由 skill 主导，直到成答、转交、用户终止或 replan
- 技能内多轮只能由状态机推进，不得回到全局路由重置全部上下文
- 全程必须保持连续叙事，不得在问题理解、问题处理、问题答案之间插入固定占位话术

### 2.7 新增 Skill 的正确路径

1. 新建 `assets/assistant/skills/{domain}/{subdomain}/{skill}/`
2. 编写 `SKILL.md` 与必需目录
3. 通过目录树摘要把该 skill 暴露给首轮模型
4. 补充 dialogue 契约和测试样例
5. 若需要工具或输出细节，放入 `references/` 与 `dialogue/`
6. 在测试中验证 skill 结构、合同与可加载性

### 2.8 Skill 扩展禁止事项

- 禁止把垂类知识写进 `assistant_agent_loop`、`local_phase_execution_owner`、`react_runtime`、`context_orchestrator`
- 禁止把 skill 路由写成规则召回、关键词命中或硬阈值过滤
- 禁止让 skill 与域模板维护两套冲突策略
- 禁止把输出要求散落在 runtime 中

---

## 3. Tool 扩展机制

### 3.1 Tool 是什么

Tool 是运行时可调用的能力单元，例如 `web_search`、`web_fetch`、`scheduler`、`app_action`。

### 3.2 Tool 的组成

- 工具合同入口：`lib/assistant/tools/tool_schema.dart`
- 能力目录入口：`lib/assistant/capabilities/capabilities.dart`
- 运行时装配入口：`lib/assistant/application/assistant_edge_service.dart`
- 元数据：`assets/assistant/tools/catalog/tool_catalog.meta.json`
- 权限矩阵：`assets/assistant/tools/catalog/tool_permissions.json`

如需暂时落到 `lib/personal_assistant/` 兼容实现，必须显式说明桥接原因与退出路径，且不得把旧路径写成当前推荐入口。

### 3.3 Tool 运行时链路

1. 模型返回 `toolCalls`
2. `ToolRegistry` 校验名称、参数、预算和输出
3. `ToolExecutionGuard` 做安全与确认检查
4. 工具执行后产出标准化 observation
5. observation 回流到 ReAct 继续推理

### 3.4 Tool 的真相源

- 工具描述、phase 文案、参数说明以 `tool_catalog.meta.json` 为准
- 权限和域矩阵以 `tool_permissions.json` / metadata 为准
- Runtime 不得再维护第二套工具标题、完成文案或 domain tool 分支

### 3.5 新增 Tool 的正确路径

1. 先在 `lib/assistant/tools/`、`lib/assistant/capabilities/` 定义或扩展当前合同入口
2. 在当前运行时装配入口注册，并在需要时补充兼容桥接
3. 在 `tool_catalog.meta.json` 中声明描述、参数、用户交互文案
4. 在权限配置中声明可用域和确认策略
5. 补充 contract test、registry test 与回归测试

### 3.6 Tool 扩展禁止事项

- 禁止在工具实现里硬编码与 domain 绑定的特殊分支
- 禁止在 trace / user event translator 中重复维护工具文案
- 禁止把 query label 这类展示字段当成运行时行为键

---

## 4. Prompt、Memory 与扩展的关系

### 4.1 Prompt

- 新阶段或新模板优先在 `assets/assistant/prompts/` 扩展
- 运行时代码不直接嵌入提示词正文

### 4.2 Memory

- 记忆是通用能力，不是某个 domain 的私有规则仓库
- 需要个性化时，优先通过画像标签和记忆召回，而不是在 runtime 写经验判断

---

## 5. 扩展设计检查表

新增 Skill 或 Tool 前必须确认：

- 是否已有现成 skill / tool / prompt 可复用
- 本次新增逻辑是否能全部落在 asset、metadata、config 层
- 是否引入了运行时第二真相源
- 是否需要补充场景级设计与约束文档

---

## 6. 关联文档

- `PERSONAL_ASSISTANT_ARCHITECTURE_AND_FLOW.md`
- `PERSONAL_ASSISTANT_DESIGN_AND_CONSTRAINTS.md`
- `scenarios/NEW_SKILL_DESIGN_AND_CONSTRAINTS.md`
- `scenarios/NEW_TOOL_DESIGN_AND_CONSTRAINTS.md`
- `scenarios/NEW_PHASE_OR_TEMPLATE_DESIGN_AND_CONSTRAINTS.md`

---

## 7. 参考旧文档

- `skill-directory-and-progressive-disclosure-design.md`
- `skill_development_standard.md`
