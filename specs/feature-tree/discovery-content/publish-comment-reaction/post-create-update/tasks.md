# 开发任务：post-create-update

## 当前交付任务

### metadata
- [ ] M1. 校验 `content/post` 元数据与“创作入口位置/公开/圈子选择”需求一致。
- [ ] M2. 若无缺口，记录“本节点无需新增 metadata”；若有缺口，补最小 YAML 变更。

### codegen
- [ ] C1. 执行 `make verify-metadata`。
- [ ] C2. 仅在 metadata 变更时执行 `make codegen && make codegen-app`。

### 业务逻辑
- [ ] B1. 四类内容发布校验在服务侧持续有效（moment/photo/video/article）。
- [ ] B2. 发布后内容不可变策略持续有效（仅允许删除与分发关系变更）。
- [ ] B3. 可见性语义保持 `public/private`，并保证“发布到圈子前提为公开”。
- [ ] B4. 作者分发/用户转发关系分离与查询语义保持一致。
- [ ] B5. 删除级联（分发+转发）与 tombstone 返回语义保持一致。
- [ ] B6. 媒体元数据、设备信息、发布地点信息入库与回读保持可用。
- [ ] B7. 承接子节点 `create-entry-location-visibility-circle`（创作入口位置/公开/圈子）实现并完成联调。

### 测试
- [ ] T1. 合同与单测覆盖发布校验、可见性与圈子约束、删除级联语义。
- [ ] T2. 端到端回归覆盖“创作页选择位置/圈子后发布并可被发现页消费”。
- [ ] T3. 子节点 `create-entry-location-visibility-circle` 的 A1~A8 全部通过。

### gate
- [ ] G1. `make gate-full` 通过。

## 搁置任务（带规划）
- [ ] P1. 微趣“更多功能按钮反馈”全链路闭环（不感兴趣/屏蔽/投诉）。
  - 搁置原因：本轮优先保证创作入口到发布主链路可生产发布。
  - 重启条件：本节点与子节点全部验收后，在 `content-action-intent-contract` 节点承接。

## 未来演进任务
- [ ] F1. 发布前圈子推荐与位置智能推荐。
- [ ] F2. 媒体上传完成后自动质量策略与重试策略增强。
