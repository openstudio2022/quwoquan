# propagation-completeness-check 任务列表

## 当前交付任务

- [ ] T1: 消费 `runtime-codegen/operation-surface-route-single-source` 生成的 operation / surface 标识
- [ ] T2: 校验 header / decoder context 在 gateway 链路中的传播完整性
- [ ] T3: 补齐弱网重试、页面重入、回退场景的上下文稳定性验证

## 未来演进任务

- [ ] 在全域迁移完成后移除旧 `pageId` 兼容读取
