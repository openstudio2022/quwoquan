# 模板领域服务规格

## 定位

`templates` 是特性树作者模板集合，不是面向终端用户的业务能力。它为应用根、领域服务、业务能力和 Story 提供标准化的 `spec`、`design` 与 `acceptance` 起草骨架。

## 范围

- 应用根 `spec/design/acceptance` 模板。
- 领域服务 `spec/design/acceptance` 模板。
- 业务能力 `spec/design/acceptance` 模板。
- Story `spec/acceptance` 模板。

## Out of Scope

- 线上业务能力。
- 运行时代码、metadata、codegen 产物。
- 树内 `树内计划文档` 或 `树内任务文档` 模板。
- Story 层 `design.md` 模板。

## 约束

- 模板只提供结构骨架，不替代具体业务事实。
- 模板字段必须与 gate 校验规则保持一致。
- 新增节点必须优先使用本目录模板，不得复制旧 Journey / Scenario 模板口径。

## 验收重点

- 作者能从本目录找到新模型的所有模板。
- 模板清晰表达 `spec / design / acceptance` 的职责分工。
- 模板不再维护 `树内计划文档`、`树内任务文档` 或 Story 设计文档。
