# circle-community 任务列表

## 当前交付任务

> 状态同步（2026-03-26）
> - P1/P2 已完成，P3 进行中。
> - repo 级 `make gate` 仍被 `shared-homepage-network` 目录下的规格治理缺口阻塞，当前不能标记为整仓门禁完成。

- [x] T1: [metadata] 创建 `contracts/metadata/circle/` 领域元数据（aggregate/fields/storage/events/service）
- [x] T2: [codegen] make verify-metadata && make codegen
- [x] T3: [设计] 完成 L2 子特性的 design.md（activity-member-governance / in-circle-recommendation-loop / circle-management-and-stats）
- [x] T4: [端侧] 迁移 `lib/features/circles/` → `lib/ui/circle/`
- [ ] T5: [门禁] make gate 通过

## 搁置任务

- [ ] 圈子协作工具（共享存储/协作白板）— 重启条件：产品确认 V2 优先级
