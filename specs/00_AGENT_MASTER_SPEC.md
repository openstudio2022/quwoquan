# AI Agent 主导开发入口

> 本文件为校验与目录清单所需入口。开发主线与阶段卡点见
> [00_MASTER_DEVELOPMENT_FLOW.md](00_MASTER_DEVELOPMENT_FLOW.md)；D0/F1/G1
> 架构与阶段准出见
> [system-architecture-and-engineering-guide](feature-tree/runtime/system-architecture-and-engineering-guide/design.md)
> 及同目录 `acceptance.yaml`。

## 权威索引

- **端云开发流水线**：[00_MASTER_DEVELOPMENT_FLOW.md](00_MASTER_DEVELOPMENT_FLOW.md)
- **Runtime D0/F1/G1 设计**：[system-architecture-and-engineering-guide/design.md](feature-tree/runtime/system-architecture-and-engineering-guide/design.md)
- **Runtime 自动化验收**：[system-architecture-and-engineering-guide/acceptance.yaml](feature-tree/runtime/system-architecture-and-engineering-guide/acceptance.yaml)
- **Metadata/ContractGraph 设计**：[metadata/DESIGN.md](../quwoquan_service/contracts/metadata/DESIGN.md)
- **扩展执行目录**：[runtime_extension_catalog.md](runtime_extension_catalog.md)
- **特性树**：`specs/feature-tree/`、`specs/feature-tree/tree_index.yaml`
- **命令**：`/explore`、`/prd`、`/design`、`/dev`、`/commit`、`/deploy`（根目录统一）；`/archive` 仅作兼容补归档入口
- **推荐模型服务就绪**：以
  [`recommendation-platform/spec.md`](feature-tree/recommendation-platform/spec.md)、
  各 L3 `acceptance.yaml` 与 metadata/codegen 验证结果为准；Python 模型与接口由
  `make codegen-rec-model-python` 生成，与 App/Go 同源。

## 原则

- 契约优先、元数据驱动；每阶段结束须通过自动化验证方可验收。
- Runtime 开发严格遵循 D0 设计冻结 → F1 ContractGraph/公共底座 →
  G1 硬门禁 → 首个真实业务样板的准入顺序；不得恢复第二套计划或运行时动态对象/存储路由。
