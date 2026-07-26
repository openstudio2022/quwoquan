# Specs 入口

产品规格从 [`feature-tree/README.md`](feature-tree/README.md) 进入。特性结构只由目录表达；AppRoot/L1/L2/L3 的当前行为、有效设计、验收和 OPEN 全部位于目标父链的 `spec.md/design.md`。

其他受版本控制文件仅承担专门契约：

- `quwoquan_service/contracts/metadata/**`：wire、字段、operation、surface、route、error、event 与 metric。
- `quwoquan_ops/policies/**`：可执行 gate 消费的正式策略例外与只减不增棘轮；不得登记特性状态或人工索引。

iOS/跨平台体验、测试模型和对象扩展规则分别归入目标 feature-tree 父链、根/子目录 `AGENTS.md`、命令与可执行 gate；本目录不保留第二份总规范。

常用命令：

```bash
make feature-context TARGET=<spec-or-code-path>
make feature-tree-overview
make feature-tree-change-report
make verify-feature-tree
```
