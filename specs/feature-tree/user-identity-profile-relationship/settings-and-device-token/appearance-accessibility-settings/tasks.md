# L3 任务：appearance-accessibility-settings

## 当前交付任务

- [ ] T1: 扩展 `user_profile` metadata 基线
  - 交付：`fields.yaml`、`storage.yaml`、`service.yaml`、`events.yaml`、`errors.yaml`、`tests/contract.yaml`、`user/openapi.yaml`、`_shared/request_context.yaml`
  - 验收：A1 / A2 / A7
- [ ] T2: 生成并接入 app/cloud metadata 常量
  - 交付：`make -C quwoquan_service verify-metadata`、`make codegen`、`make codegen-app` 通过；新增 `AppearanceSettingsRepository`
  - 验收：A1 / A8
- [ ] T3: 实现本地 optimistic apply、pending 队列与 `last-write-wins` reconcile
  - 交付：本地先应用、失败待同步、恢复联网自动补同步
  - 验收：A5 / A6 / A7
- [ ] T4: 实现设置页与子账号 scope 交互
  - 交付：继承状态展示、`同步所有账号` 默认勾选、`恢复继承` 行为、source explainability
  - 验收：A2 / A3 / A4 / A5
- [ ] T5: 与 `app-theme-infrastructure` 打通
  - 交付：主题/字号设置驱动全 app 运行时，满足 `<=100ms / <=300ms`
  - 验收：A5 / A8
- [ ] T6: 实现跨端失效通知、前台补拉取与 settings-audit 链路
  - 交付：在线设备失效通知、前台恢复刷新、正式审计记录
  - 验收：A6 / A7 / A8

## 搁置任务（带规划）

| 任务 | 搁置原因 | 计划重启条件 |
|---|---|---|
| 主题与字号分字段独立同步策略 | 首发优先保证“统一生效”而非复杂差异化合并 | 主流程稳定后，再评估按字段继承/覆盖 |
| portal / ops 后台展示或回滚用户外观设置 | 当前首发目标是移动端用户体验，不是运营控制面 | settings-audit 稳定后再扩展只读视图 |
| 更细粒度 accessibility 偏好同步（高对比、粗体、减弱动效） | 当前运行时与设计 token 尚在第一阶段收敛 | `app-theme-infrastructure` 稳定后按批次追加 |

## 未来演进任务

- 演进为通用 scoped settings 平台，复用到通知、隐私、助手偏好等更多设置域
- 引入设置变更历史与用户可见的“恢复默认 / 回退上一次”能力
- 为跨端同步增加更强的变更来源标识与诊断能力
- 把弱网/离线 pending 状态纳入统一可观测埋点
