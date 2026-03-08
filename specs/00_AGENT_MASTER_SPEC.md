# AI Agent 主导开发入口

> 本文件为校验与目录清单所需入口。**开发主线与阶段卡点**见 [00_MASTER_DEVELOPMENT_FLOW.md](00_MASTER_DEVELOPMENT_FLOW.md)；**Runtime 商用准出开发计划与阶段门禁**见 [RUNTIME_DEVELOPMENT_PLAN.md](RUNTIME_DEVELOPMENT_PLAN.md)。

## 权威索引

- **端云开发流水线**：[00_MASTER_DEVELOPMENT_FLOW.md](00_MASTER_DEVELOPMENT_FLOW.md)
- **Runtime 阶段与自动化验收**：[RUNTIME_DEVELOPMENT_PLAN.md](RUNTIME_DEVELOPMENT_PLAN.md)
- **特性树**：`specs/feature-tree/`、`specs/feature-tree/tree_index.yaml`
- **命令**：`/explore`、`/prd`、`/design`、`/dev`、`/commit`、`/deploy`（根目录统一）；`/archive` 仅作兼容补归档入口
- **推荐模型服务就绪**：Create 阶段完成后见 [rec-model-service/readiness.md](feature-tree/recommendation-platform/rec-model-service/readiness.md)；Python 模型与接口由 `make codegen-rec-model-python` 生成，与 App/Go 同源。训练工程见 recommendation-platform 下 **rec-model-training**。

## 原则

- 契约优先、元数据驱动；每阶段结束须通过自动化验证方可验收。
- Runtime 开发严格按 RUNTIME_DEVELOPMENT_PLAN 的 P0-fix → P0 → P1 → P2 → P3 执行，每阶段 Gate 通过后再进入下一阶段。
