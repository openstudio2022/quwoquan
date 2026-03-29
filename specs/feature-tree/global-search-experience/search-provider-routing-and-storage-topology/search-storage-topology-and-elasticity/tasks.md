# Tasks: search-storage-topology-and-elasticity

## 当前交付任务

- [x] T1: 冻结读模型、读写分离、多 reader slice 与统一读库替换边界 → A1
- [x] T2: 为 `content / circle / homepage / location` 现有读路径补齐 metadata path / query / header contract tests → A1
- [x] T3: 补齐统一 `SearchRepository` 与 assistant `search` tool 的读侧 fail-closed / 审计边界验证证据 → A1

## 未来演进任务

- [ ] F1: 评估统一高性能搜索读库的替换窗口与迁移策略
- [ ] F2: 落地真正的云侧 search read model / projection / cache / throttle 工程实现
- [ ] F3: 补齐大规模容量演练与 reader slice 独立限流压测
