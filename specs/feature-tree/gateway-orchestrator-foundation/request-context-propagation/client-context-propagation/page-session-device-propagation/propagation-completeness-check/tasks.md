# propagation-completeness-check 任务列表

## 当前交付任务

- [ ] T1: [metadata] 扩展 `service.yaml` 的 operation client_context 契约，明确 `operation_id / default_surface_id / decoder_context_id`
- [ ] T2: [metadata] 扩展 UI metadata（优先 `ui_config.yaml`，必要时拆 `ui_surfaces.yaml`），声明 `surface_id / route_id / path_template / route_kind / binds_operations`
- [ ] T3: [codegen] 扩展 `codegen_app_metadata`，生成 `*OperationIds`、`*SurfaceIds`、`AppRoutePaths`、route/path builder，移除代码维护 override 表
- [ ] T4: [测试-Red] 为 codegen 产物与 Router/Repository 静态语义检查补失败用例与基线
- [ ] T5: [业务逻辑-Green] 迁移 `CloudRequestHeaders`、`CloudResponseDecoder.context` 与各域 Remote Repository 到生成常量
- [ ] T6: [业务逻辑-Green] 迁移 `app_router.dart` 与跳转入口到生成 route 常量 / builder
- [ ] T7: [规则] 更新 `/prd`、`/design`、`/dev`、`/try`、`/deliver` 与根规则，要求 operation/surface/route 必须 metadata-first
- [ ] T8: [测试] 补齐 T1/T2/T3/T4 证据，并将 semantic checker 接入 `make gate`

## 搁置任务（不在本次交付范围，但已识别，有重启条件）

- [ ] 为所有历史低频页面补齐 surface metadata（重启条件：高频域迁移完成后统一扫尾）
- [ ] 将旧 `pageId` header 完全移除（重启条件：所有客户端与观测链路完成新 header 消费）

## 未来演进任务

- [ ] 将 surface metadata 扩展到页面投影与埋点事件模板联动
- [ ] 将 router semantic checker 从文本扫描升级为 AST 校验
