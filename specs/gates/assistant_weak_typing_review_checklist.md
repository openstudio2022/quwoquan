# 助手弱类型 PR 评审清单（诚信）

与 [`assistant_search_weak_typing_governance.md`](assistant_search_weak_typing_governance.md) §1.1 一致。合并前建议核对：

## 应视为「主要交付」的条件（至少满足其一）

- [ ] **contracts/metadata** 有新增或修改，且 **`make codegen-app`** 后 **`lib/assistant/generated/**` 有对应更新**，手写代码改为消费 **生成 DTO / 契约类型**。
- [ ] 或：引入 **具名 sealed class / 领域类型**，跨层传递**不再**以匿名 `Map<String, dynamic>` 为唯一状态载体（须有设计说明）。

## 不应单独作为「弱类型收口」理由

- [ ] PR 主体仅为 **`dynamic` → `Object?`**、**`.cast<String, dynamic>` → `.cast<String, Object?>`**、或 **`Map<String, dynamic>` → `Map<String, Object?>`** 的机械替换，而无契约或生成体跟进。
- [ ] 仅展示棘轮 **`dynamic_keyword` 下降**，无 metadata / 生成体 / 领域类型变更说明。

## 仍可接受但须标注

- 纯重构、重命名、与 JSON **入口**收窄相关的 `Object?`（_decode 边界），在 PR 描述中注明 **「非域模型类型化」**。
