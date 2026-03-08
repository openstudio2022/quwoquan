# operation-surface-route-single-source 任务列表

## 当前交付任务

- [ ] T1: [metadata] 为 `service.yaml` 定义 `operation_id / decoder_context_id / default_surface_id`
- [ ] T2: [metadata] 为 `ui_config.yaml` 或 `ui_surfaces.yaml` 定义 `surface_id / route_id / path_template / binds_operations`
- [ ] T3: [codegen] 扩展 `codegen_app_metadata`，生成 operation/surface/route 常量与 builder，移除代码 override 表
- [ ] T4: [业务逻辑] 迁移 `CloudRequestHeaders`、`CloudResponseDecoder.context` 与 Repository 请求入口
- [ ] T5: [业务逻辑] 迁移 `app_router.dart`、主跳转入口与相关测试
- [ ] T6: [测试/门禁] 新增 router / telemetry semantic checker 并接入 `make gate`
- [ ] T7: [验证] 跑通 `verify-metadata`、`codegen`、`codegen-app`、针对性 analyze / tests / gate

## 搁置任务

- [ ] 低频页面的 surface metadata 扫尾迁移（重启条件：高频域迁移完成）
- [ ] 移除旧 `X-Client-Page-Id` 兼容链路（重启条件：全域迁移完成）

## 未来演进任务

- [ ] 将 route/surface metadata 与埋点事件模板统一建模
- [ ] 将 semantic gate 升级为 AST 级检查
