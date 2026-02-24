# 特性目录树总揽（L1-L5）

本目录用于替代“平铺 specs 文件”模式，采用**目录即特性**的组织方式：

- 每个特性一个目录（目录名使用特性名/slug）
- 每个特性目录固定一个 `spec.md`
- 层级关系通过目录嵌套表达（L1 -> L2 -> L3 -> L4 -> L5）

这样做的目的：
- AI agent 可以从目录结构直接构建全局特性上下文
- 语义清晰，避免 `id/parent_id` 可读性问题
- 规范、任务、验收可在同一路径聚合

---

## 命名规则（统一）

- 目录命名：`<feature-slug>`（kebab-case）
- spec 命名：固定为 `spec.md`
- 推荐路径：
  - `specs/feature-tree/<l1-feature>/<l2-feature>/<l3-feature>/<l4-feature>/<l5-feature>/spec.md`

说明：
- 目录名承担“特性名”语义，`spec.md` 保持工具链与模板一致性。
- 不建议同层再用自定义文件名（如 `xxx_spec_v2.md`），避免漂移。

---

## L1 落地范围（端云一体化 9 大能力域）

功能 L1（5）：

- `discovery-content`（内容发现与发布）
- `circle-community`（圈子社区）
- `chat-conversation`（聊天与会话）
- `user-identity-profile-relationship`（用户身份画像与关系）
- `assistant-run-learning`（助手运行与学习闭环）

非功能 L1（4）：

- `runtime`（统一运行时能力域）
- `platform-ops-governance`（运维横切）
- `product-ops-growth`（运营横切）
- `gateway-orchestrator-foundation`（网关与编排基础能力）

每个 L1 子目录包含：`spec.md`、`tasks.md`、`acceptance.yaml`；非功能 L1 含 `tree.yaml` 定义 L2~L5 目录树。

---

## 与现有体系关系

- `changes/feature_tree.yaml`：作为全局能力树台账
- `specs/feature-tree/*`：作为“可执行目录化规范”
- 权威 L1-L5 目录化规范，无兼容层

## 开发就绪与首批建议

- **首批 L2**：`runtime-errors`、`platform-ops-governance/observability-and-alerting`、`product-ops-growth/event-ingestion-and-analytics`
- **门禁**：`make verify`、`make gate`、`make gate-full`

