# L3 任务：app-theme-infrastructure

## 当前交付任务

- [ ] T1: 定义 `AppearanceSnapshot`、token layering、统一断点与 provider 收敛方案
  - 交付：`theme_provider` / `accessibility_provider` / `responsiveProvider` 收敛设计
  - 验收：A1 / A4 / A5
- [ ] T2: 改造根入口 `main.dart` 与 `AppTheme`
  - 交付：`system / light / dark`、`TextScaler`、系统栏、安全区策略统一接入
  - 验收：A2 / A3 / A5
- [ ] T3: 建立 Cupertino-first 共享组件 recipes
  - 交付：shell / navigation / tab / list / sheet / dialog / button / input / chat input
  - 验收：A1 / A4 / A7
- [ ] T4: 清理 `ScreenUtil`、百分比 `MediaQuery` 与页面级手写深浅色分支
  - 交付：统一断点与布局语义，消除主路径上的记录适配方式
  - 验收：A4 / A6
- [ ] T5: 分域推进全量页面视觉迁移
  - 交付：discovery / content / chat / user / circle / assistant / settings / welcome / rtc
  - 验收：A4 / A6 / A7
- [ ] T6: 建立回归与门禁
  - 交付：`flutter analyze`、`verify_dart_semantic`、golden、UI regression、真机矩阵
  - 验收：A3 / A8

## 搁置任务（带规划）

| 任务 | 搁置原因 | 计划重启条件 |
|---|---|---|
| 全量 `ScreenUtil` 彻底移除 | 记录页面多、回归面大 | 主路径完成断点迁移后分域清理 |
| 每个业务域单独定义品牌 accent | 容易破坏全局苹果风格一致性 | 全局基线稳定后，再评估极少量域级差异 |
| 全量 CupertinoApp 宿主切换 | 当前路由与插件兼容收益不高 | 若后续壳层重构收益显著，再单独立项 |

## 未来演进任务

- 设计 token 元数据化，与 `design-token-metadata-registry` 对齐
- iPad / desktop 进阶多栏布局策略
- 更完整的无障碍项：`reduceTransparency`、系统粗体、增强对比同步
- 主题设计系统文档与组件目录自动生成快照
