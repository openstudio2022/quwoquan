# 小趣私人助理：设计与开发约束

> **定位**：小趣私人助理增量开发三类核心文档之一，也是助手相关需求的主入口必读文档  
> **前置阅读**：`PERSONAL_ASSISTANT_ARCHITECTURE_AND_FLOW.md`  
> **配套阅读**：`PERSONAL_ASSISTANT_SKILL_AND_TOOL_EXTENSIBILITY.md`

---

## 1. 适用范围

凡是涉及以下任一目录或模块，进入探索、设计、开发、测试与验收前都必须先读本文：

- `quwoquan_app/lib/assistant/`
- `quwoquan_app/lib/personal_assistant/`（仅当触达兼容实现或 legacy bridge 时）
- `quwoquan_app/assets/assistant/`
- `quwoquan_app/test/personal_assistant/`
- `quwoquan_app/lib/ui/chat/` 中与助理链路直接耦合的页面或渲染逻辑

---

## 2. 总体约束

### 2.1 架构约束

- `assistant_agent_loop + local_phase_execution_owner + react_runtime + tool_registry` 不得承载垂类知识或垂类特判
- 运行时只做编排、守卫、解析、序列化和回放
- 垂类扩展只能通过 `skills/<domain>/`、prompt asset、tool metadata、policy config 下沉

### 2.2 字符串治理约束

- 禁止用用户可见字符串、中文文案、label 文本做行为路由
- 禁止在 engine、react、tool 中新增 `contains()` / `RegExp` 语义分类
- 协议与值域应优先使用 typed contract、enum、schema
- `assistant_turn_v2`、`assistant_turn_v3` 视为已淘汰协议，当前运行时禁止继续保留读取兼容

### 2.3 提示词与文案约束

- 提示词正文必须在 `assets/assistant/prompts/` 中管理
- 工具 phase 文案、完成文案、提示语以工具 metadata 为准
- 追问文案、兜底文案、过程文案不得再散落在 runtime

### 2.4 回答质量约束

- 默认通用兜底必须可用，不依赖垂类 if/switch
- 无证据时输出边界与下一步，不伪造确定性答案
- 用户轨与机器轨必须遵循统一输出契约

### 2.5 元数据与 codegen 约束

- 助理协议真相源统一放在 `quwoquan_service/contracts/metadata/assistant/`
- 目录划分必须按业务对象组织，并在业务对象之上保留业务大类聚类：`assistant/{cluster}/{business_object}/`，仅允许少量 `_shared/` 共享类型
- 端侧助理内核目录主轴不再使用 `runtime`，目标结构为 `quwoquan_app/lib/assistant/{application,domain,orchestration,capabilities,infrastructure,generated}/`
- 端侧协议生成产物统一放在 `quwoquan_app/lib/assistant/generated/`
- `generated/` 下所有文件必须带 `DO NOT EDIT`，禁止手写、禁止混放桥接层
- `quwoquan_app/lib/personal_assistant/contracts/` 逐步退出 DTO / enum / serde 定义职责，不再作为当前 contract 主轴
- `quwoquan_app/lib/personal_assistant/app/` 仅允许保留 compatibility shim，不再承接新的 provider / gateway 实现，也不再作为当前 app 入口主轴
- 当前实施阶段只生成端侧 Dart 协议产物，并只做端侧校验；但 metadata 设计必须保持与端云一体化一致，后续可生成 Go 产物
- 当前完整 `agentloop + react + skill + tool` 服务先在端侧实现，但目录与对象设计必须兼容未来云侧 `assistant-service` 完整承接

---

## 3. 真相源（SSOT）

| 维度 | 唯一真相源 |
|---|---|
| 总体架构与主流程 | `PERSONAL_ASSISTANT_ARCHITECTURE_AND_FLOW.md` |
| Skill / Tool 扩展边界 | `PERSONAL_ASSISTANT_SKILL_AND_TOOL_EXTENSIBILITY.md` |
| 设计与开发约束 | 本文 |
| Prompt 模板 | `quwoquan_app/assets/assistant/prompts/` |
| Tool 元数据 | `quwoquan_app/assets/assistant/tools/catalog/tool_catalog.meta.json` |
| Tool 权限 | `quwoquan_app/assets/assistant/tools/catalog/tool_permissions.json` |
| Skill 域策略 | `quwoquan_app/assets/assistant/skills/<domain>/` |
| 助理协议 metadata | `quwoquan_service/contracts/metadata/assistant/` |
| 端侧助理协议 codegen 产物 | `quwoquan_app/lib/assistant/generated/` |
| 端侧 edge assistant 实现 | `quwoquan_app/lib/assistant/` |
| 编排主入口（禁止旧 monolith 增量） | `orchestration/assistant_agent_loop.dart` 为真实 owner，执行细节收敛到 `orchestration/local_phase_execution_owner.dart` 与 `orchestration/phases/` |
| 主编排入口 | `quwoquan_app/lib/assistant/orchestration/assistant_agent_loop.dart` |
| 端侧 cloud client | `quwoquan_app/lib/cloud/services/assistant/` |
| 端侧 UI 入口 | `quwoquan_app/lib/ui/assistant/` |

仅允许保留必要的运行时桥接层，但不得作为新功能的首选依赖。

---

## 4. 各阶段必读要求

### 4.1 Explore

若需求涉及助手：

- 先读本文与 `PERSONAL_ASSISTANT_ARCHITECTURE_AND_FLOW.md`
- 确认本次变更属于 runtime、skill、tool、prompt、UI 哪一层
- 明确是否需要新增场景级设计与约束文档

### 4.2 PRD

若需求涉及助手：

- `spec.md` 必须明确是否影响 skill、tool、prompt、memory、streaming
- `spec.md` 必须明确影响的业务大类：conversation / memory / learning / skill / tool / agent / model / channel
- 明确哪些内容属于 asset 扩展，哪些属于 runtime 约束
- 写清楚不可通过 runtime 硬编码实现的边界

### 4.3 Design

若需求涉及助手：

- `design.md` 必须引用本文
- 说明本方案如何满足“无垂类特判、无字符串硬编码、模板资产化”
- 说明本方案如何映射到 `metadata -> service -> cloud client -> ui domain` 主轴与 `domain/{cluster}/{business_object}` 结构
- 若引入新场景，必须附对应场景级文档

### 4.4 Dev

若需求涉及助手：

- 开发前确认读过本文第 2 节与第 3 节
- 优先改 asset / metadata / config，其次才是 runtime
- 若涉及协议对象、enum、contractVersion、字段名，必须先改 `quwoquan_service/contracts/metadata/assistant/`，不得先手写 Dart contract
- 若涉及目录迁移，优先迁到 `quwoquan_app/lib/assistant/` 新结构，不再新增 `lib/personal_assistant/contracts/*`、`lib/personal_assistant/app/*` 或 `personal_assistant/runtime/*` 风格目录
- 若不得不新增兼容逻辑，必须说明退出条件与清理路径

### 4.5 Verify

若需求涉及助手：

- 审计是否新增 runtime 垂类特判
- 审计是否新增字符串驱动行为判断
- 审计是否新增第二真相源
- 审计测试是否围绕合同，而不是围绕某个垂类样例文案

---

## 5. 设计交付要求

### 5.1 文档

助手相关 `design.md` 至少补充：

- 影响层：runtime / skill / tool / prompt / UI
- 影响的业务大类聚类：conversation / memory / learning / skill / tool / agent / model / channel
- 真相源映射
- 场景级文档引用
- 回滚与兼容清理策略

### 5.2 代码

助手相关实现优先顺序：

1. metadata / prompt / skill / tool catalog
2. codegen 产物（当前先 Dart，后续可扩到 Go）
3. typed contract / parser / serializer 适配层
4. application / orchestration
5. UI 渲染与解释事件

### 5.3 测试

优先补：

- contract test
- manifest / registry test
- parser / response test
- streaming / regression test
- generated-only / metadata drift test

避免把具体垂类样例文案当作长期稳定断言。

---

## 6. 场景级设计与约束文档

当变更命中以下场景时，除本文外还必须补读对应文档：

| 场景 | 文档 |
|---|---|
| 新增 Skill | `scenarios/NEW_SKILL_DESIGN_AND_CONSTRAINTS.md` |
| 新增 Tool | `scenarios/NEW_TOOL_DESIGN_AND_CONSTRAINTS.md` |
| 新增 Phase / Prompt 模板 | `scenarios/NEW_PHASE_OR_TEMPLATE_DESIGN_AND_CONSTRAINTS.md` |
| 某个垂类专项改造 | `scenarios/DOMAIN_SPECIFIC_DESIGN_AND_CONSTRAINTS.md` |

通用模板见 `scenarios/_TEMPLATE_DESIGN_AND_CONSTRAINTS.md`。

---

## 7. 验收审计清单

- 是否仍坚持三类核心文档为主入口
- 是否把运行时职责限制在 orchestration / guard / parsing
- 是否把垂类知识收敛到 skill 资产
- 是否把工具文案收敛到 metadata
- 是否避免新增字符串语义路由
- 是否在 explore / prd / design / dev / verify 中体现必读门禁

---

## 8. 参考旧文档

以下文档保留为细节参考，不再作为第一入口：

- `skill_development_standard.md`
- `canonical_truth_sources.md`
- `runtime_audit_baseline.md`
- `prompt-template-architecture-v2.md`
- `react-agent-tool-lifecycle-spec-v4.md`
