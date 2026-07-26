# docs 目录边界

`docs/` 只保存无法由代码、metadata、AGENTS 或 feature-tree 表达的长期工程说明。

产品规格、架构裁定、验收和开放事项统一进入 `specs/feature-tree/**/spec.md` 与 `design.md`；历史由 Git 表达。功能级规格、backlog、状态台账和命令协议不得在 `docs/` 下另建入口。

当前允许的长期文档类型：

- 跨环境能力消费者关系等长期工程说明。
- 不能归入 metadata、policy、AGENTS 或 feature-tree 的稳定参考。
