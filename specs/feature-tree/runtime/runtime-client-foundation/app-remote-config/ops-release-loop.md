# 运营发布闭环

## 角色

| 角色 | 权限 |
|---|---|
| Product Ops | 编辑低/中风险字段、发起灰度 |
| Domain Owner | 审批本域中/高风险字段 |
| Runtime Owner | 审批系统参数、SLO、回滚策略 |
| QA | 验收 alpha/beta/gamma release |
| Oncall | 紧急 kill switch 与回滚 |

## 流程

1. 编辑配置草稿：字段必须存在于 `app_remote_config_catalog.yaml`。
2. 静态校验：owner、risk、expiry、fallback、禁止字段。
3. 预览影响：展示 diff、受影响 appVersion/platform、预计覆盖人数。
4. 审批：按 risk_level 触发单人/多人审批。
5. 发布灰度：1% -> 5% -> 20% -> 50% -> 100%。
6. 生效率观测：客户端上报 configHash/source/result，服务端看 hash 分布。
7. 回滚：切回上一 release pointer，保留审计链。

## 风险规则

| risk_level | 审批 | 灰度 | 回滚 |
|---|---|---|---|
| low | Product Ops | 可直接 100% | 手动 |
| medium | Domain Owner | 必须分阶段 | 一键 |
| high | Domain Owner + Runtime Owner | 强制 SLO gate | 一键 + oncall |
| critical | 不允许 AppRemoteConfig | 不适用 | 不适用 |

## 看板

- 当前 active release、previous release、rollback target。
- release 生效率：按 appVersion/platform/configHash 展示。
- SLO：QPS、p95/p99、5xx、304 命中率、LKG/stale 比例。
- 字段风险：即将 expiry 的 flag、长期未清理灰度字段。
- 漂移：不同实例返回 hash 不一致。

## 审计

每次变更记录：
- actor、reviewer、reason、ticket。
- diff、risk_level、target audience、rollout stages。
- release id、configHash、startedAt、completedAt、rollbackAt。
- 验收证据与 SLO gate 结果。
