# L3 任务：error-permission-display-semantics

## 当前交付任务

由 L4 子节点承载，**依赖顺序**：先 permission-card（LocationPermissionChecker），再 cloud-network（L1b 依赖 FakeChecker）。

- `permission-card-display-contract/tasks.md` — 权限卡片 + LocationPermissionChecker 抽取
- `cloud-network-error-display-contract/tasks.md` — 云端错误展示 + L1a/L1b/L1c 测试

## 搁置任务（带规划）

| 任务 | 搁置原因 | 计划重启条件 |
|------|----------|--------------|
| 抽取 CloudErrorInlinePlaceholder 共享组件 | 现有页面实现差异大 | 3+ 页面完成迁移后统一抽取 |
| INTEGRATION 域错误码 codegen | 当前仅 content 域 | integration-service 契约稳定后扩展 |

## 未来演进任务

- 共享 Widget 入库 `lib/core/widgets/` 或 `lib/components/`
- 门禁增加错误/权限展示合规检查（可选）
