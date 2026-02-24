# AI Agent 主导开发入口

> 本文件为校验与目录清单所需入口。**开发主线与阶段卡点**见 [00_MASTER_DEVELOPMENT_FLOW.md](00_MASTER_DEVELOPMENT_FLOW.md)；**Runtime 商用准出开发计划与阶段门禁**见 [RUNTIME_DEVELOPMENT_PLAN.md](RUNTIME_DEVELOPMENT_PLAN.md)。

## 权威索引

- **端云开发流水线**：[00_MASTER_DEVELOPMENT_FLOW.md](00_MASTER_DEVELOPMENT_FLOW.md)
- **Runtime 阶段与自动化验收**：[RUNTIME_DEVELOPMENT_PLAN.md](RUNTIME_DEVELOPMENT_PLAN.md)
- **特性树**：`specs/feature-tree/`、`specs/feature-tree/tree_index.yaml`
- **命令**：`/opsx-ff`、`/opsx-apply`、`/opsx-archive`（根目录统一）

## 原则

- 契约优先、元数据驱动；每阶段结束须通过自动化验证方可验收。
- Runtime 开发严格按 RUNTIME_DEVELOPMENT_PLAN 的 P0-fix → P0 → P1 → P2 → P3 执行，每阶段 Gate 通过后再进入下一阶段。
