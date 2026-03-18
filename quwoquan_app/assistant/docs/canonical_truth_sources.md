# 小趣助理 真相源冻结声明

> **版本**：v1.0 · **日期**：2026-03-13  
> **目的**：明确助理子系统各维度的唯一真相源（SSOT），禁止在 runtime 中维护第二套。  
> **从属**：[architecture_overview.md](architecture_overview.md) · [react-agent-tool-lifecycle-spec-v4.md](react-agent-tool-lifecycle-spec-v4.md)
>
> **收口说明**：当前必读入口为 `PERSONAL_ASSISTANT_DESIGN_AND_CONSTRAINTS.md`。本文档保留为真相源冻结细则参考。

---

## 一、架构与生命周期（唯一真相源）

| 维度 | 唯一真相源 | 禁止 |
|------|------------|------|
| 目标架构 | `docs/react-agent-tool-lifecycle-spec-v4.md` | 在 `assistant_agent_loop` / `local_phase_execution_owner` / react / skill / tool 中偏离 v4 行为 |
| Prompt 模板 | `docs/prompt-template-architecture-v2.md` | 在 runtime 手写 prompt 模板或注入规则 |
| 总体设计 | `docs/architecture_overview.md` | 在 engine 中引入文档未声明的分层或职责 |

**原则**：LLM-first，零规则硬编码。意图识别、Skill 选择、搜索策略由 LLM 自主判断。

---

## 二、输出合同（唯一真相源）

| 维度 | 唯一真相源 | 禁止 |
|------|------------|------|
| 助理协议 metadata | `quwoquan_service/contracts/metadata/assistant/` | 在 app runtime 手写第二套 contract schema / enum / 字段名 |
| Phase 输出契约 | `assets/assistant/prompts/global/phase.output_contract.plan.md` | 在 runtime 推断或硬编码 phase 字段含义 |
| 结构化合同定义 | `assets/assistant/prompts/_standards/output_contracts.json` | 在 serializer/parser 中维护与 contract 不一致的 schema |
| 端侧协议 codegen 产物 | `lib/assistant/generated/` | 在 `lib/personal_assistant/contracts/` 中继续手写 DTO / enum / serde，或绕过 `lib/assistant/{contracts,generated}/` 另起一套协议入口 |

---

## 三、工具交互文案（唯一真相源）

| 维度 | 唯一真相源 | 禁止 |
|------|------------|------|
| 工具 phase 文案 | `assets/assistant/tools/catalog/tool_catalog.meta.json` | 在 journey projector、phase owner、tool impl 中硬编码 phaseTitle/completedTemplate 等 |
| 工具描述与参数 | 同上 `tool_catalog.meta.json` | 在 websearch_tool、tool_registry 等中维护第二套文案或 label |

`userInteraction.phaseTitle`、`executing.completedTemplate`、`reasoning.promptHint` 等均以该文件为准。

---

## 四、Skill / 垂类策略（唯一真相源）

| 维度 | 唯一真相源 | 禁止 |
|------|------------|------|
| 垂类特判与干预 | `assets/assistant/skills/<domain>/` 下 SKILL.md、config、scripts | 在 `assistant_agent_loop`、`local_phase_execution_owner`、`react_runtime`、`context_orchestrator`、tool impl 中按 domainId 或关键词做 if/switch |
| retrieval policy | 对应 skill 的 `config/retrieval_policy.json`、`retrieval_policy.json` | 在 runtime 中硬编码 providerPolicy、freshnessHoursMax、authorityDomains |
| tool 权限 / domainToolMatrix | `tool_catalog.meta.json` 的 `domainToolMatrix` | 在 tool_registry 中按 domain 硬编码权限或 preferred tools |
| tool 执行权限（requireConfirmation、allowedActions） | `assets/assistant/tools/catalog/tool_permissions.json` | 在 ToolExecutionGuard、ReactRuntime 中硬编码 requireConfirmation |

---

## 五、Legacy 与兼容层（仅作兼容，不再新增依赖）

| 资产 | 状态 | 说明 |
|------|------|------|
| `assistant_turn_v2/v3` | 已淘汰 | 当前运行时不再读取兼容；仅允许在历史文档/回放说明中出现，待后续专门兼容方案再评估 |
| `trigger_keywords` | 兼容层 | runtime 已停止消费，该字段仅留给历史资产读取 |
| 旧 prompt stack（非 v4 规划链） | 兼容层 | 不用于新功能 |
| 基于 RegExp/contains 的语义分类 | 待移除 | 只保留单点兼容兜底，其余移除 |
| `lib/personal_assistant/app/*` | 兼容层 | 仅保留桥接到 `lib/assistant/{application,runtime}/` 的 shim，不再作为新 UI / provider / gateway 入口 |
| `lib/assistant/orchestration/local_phase_execution_owner.dart` | 本地 phase 执行 owner | 禁止再分叉第二份 owner 实现；执行/合成/收尾逻辑统一在 `orchestration/phases/` 与 owner 下收口 |

---

## 六、执行约束与代码门禁

1. **冻结后**：runtime 只消费 typed contract、enum、metadata；不再用自然语言字符串做语义分类或路由。
2. **代码门禁**：以 `test/assistant/runtime_string_governance_test.dart` 与当前 `lib/assistant/*` 主入口约束为准，禁止在 engine/react/skill/tool 中新增用户可见文案与语义词表。
3. **新增能力**：必须先更新对应真相源（metadata、prompt、tool catalog、skill config），再改 runtime；禁止反向在 runtime 中先硬编码再补资产。
4. **generated-only**：`lib/assistant/generated/` 仅允许 codegen 写入，禁止手写、禁止人工修补。
5. **当前阶段**：只生成端侧 Dart 协议产物并只做端侧校验，但 metadata 设计必须保持与端云一体化一致，后续可生成 Go 产物。
6. **门禁**：禁止在 `engine/react/skill/tool` 中新增用户可见中文文案和语义词表；允许的协议字符串只能来自 enum/schema 映射层。
7. **结构主轴**：端侧 edge assistant 的实现入口收敛到 `lib/assistant/`，不再以 `personal_assistant/runtime` 作为未来目录主轴。
