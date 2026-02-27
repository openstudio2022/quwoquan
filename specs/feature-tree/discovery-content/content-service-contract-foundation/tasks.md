# Tasks: content-service-contract-foundation

> 顺序：metadata → codegen → 业务逻辑 → 测试

---

## L3-1: metadata-domain-restructure（目录重组）

### T1.1 创建域目录层 contracts/metadata/content/
- [ ] 创建 `contracts/metadata/content/` 目录
- [ ] 将 `contracts/metadata/post/` 整体移动到 `contracts/metadata/content/post/`
- [ ] 将 `contracts/openapi/content-service.v1.yaml` 迁入 `contracts/metadata/content/openapi.yaml`
- [ ] 创建 `contracts/metadata/_shared/errors/common_codes.yaml`（通用错误码枚举）
- [ ] 创建 `contracts/metadata/_shared/errors/http_mapping.yaml`（错误码 → HTTP status）

### T1.2 投影迁入实体目录
- [ ] 创建 `contracts/metadata/content/post/projections/` 目录
- [ ] 将 `_projections/photo_post.yaml` 迁入 `projections/photo_post.yaml`
- [ ] 将 `_projections/video_post.yaml` 迁入 `projections/video_post.yaml`
- [ ] 将 `_projections/article_post.yaml` 迁入 `projections/article_post.yaml`
- [ ] 将 `_projections/moment_post.yaml` 迁入 `projections/moment_post.yaml`
- [ ] 删除 `_projections/` 中已迁移的文件（保留跨域投影如 chat_inbox.yaml）

### T1.3 更新 codegen 工具路径
- [ ] 更新 `tools/codegen_app_metadata/main.go`：`metadataDir` 默认路径改为 `contracts/metadata/content`
- [ ] 更新工具投影扫描：读 `{entity}/projections/*.yaml` 而非 `_projections/*.yaml`
- [ ] 更新 `tools/codegen_content_service/main.go`：读取新路径
- [ ] 更新 `Makefile` 中 codegen-app / codegen-content-service 的路径参数
- [ ] 运行 `make verify-metadata` 确认通过
- [ ] 运行 `make codegen` + `make codegen-app` 确认产物不变

---

## L3-2: fullstack-error-behavior-contract（错误码 + 行为采集）

### T2.1 errors.yaml 声明
- [ ] 创建 `contracts/metadata/content/post/errors.yaml`
- [ ] 声明 content 域全量错误码（参见 design.md §三 errors.yaml 示例）
  - CONTENT.USER.post_not_found
  - CONTENT.USER.forbidden_edit / forbidden_create
  - CONTENT.USER.rate_limited（含 retry_after_seconds）
  - CONTENT.USER.invalid_argument（参数校验失败）
  - CONTENT.USER.unauthorized
  - CONTENT.SYSTEM.storage_write_failed
  - CONTENT.SYSTEM.internal_error
  - CONTENT.MIDDLEWARE.upstream_timeout
- [ ] 运行 `make verify-metadata`

### T2.2 errors.yaml → Dart codegen
- [ ] 扩展 `codegen_app_metadata`：解析 errors.yaml
- [ ] 生成 `lib/cloud/content/generated/content_errors.g.dart`
  - `enum ContentErrorCode { postNotFound, rateLimited, ... }`
  - `class ContentErrorMessages { static const Map<ContentErrorCode,String> zh = {...}; }`
  - `static ContentErrorCode fromCode(String code)`
  - `static bool isRetryable(ContentErrorCode code)`
- [ ] 运行 `make codegen-app`，确认文件生成

### T2.3 errors.yaml → Go codegen
- [ ] 扩展 `codegen_content_service`：解析 errors.yaml
- [ ] 生成 `services/content-service/internal/generated/errors.go`
  - `var ErrPostNotFound = errors.New("CONTENT.USER.post_not_found")`
  - 全部错误码常量，与 runtime/errors.AppError 绑定
- [ ] 运行 `make codegen`

### T2.4 CloudErrorMapper 升级
- [ ] 修改 `lib/cloud/runtime/errors/cloud_error_mapper.dart`
  - 升级 `_readCode()` 实现：真正解析 JSON body 中的 `"code"` 字段
  - 新增 `fromErrorResponse()` 方法：接受完整 response → ContentErrorCode
- [ ] 修改 `lib/cloud/runtime/errors/cloud_exception.dart`：增加 `errorCode` 字段（强类型）
- [ ] UI 层错误展示统一用 `ContentErrorMessages.zh[exception.errorCode]`

### T2.5 behaviors.yaml 声明
- [ ] 创建 `contracts/metadata/content/post/behaviors.yaml`
- [ ] 声明行为事件（参见 spec.md 和 design.md §三）：
  - impression（viewport_enter，batch=true）
  - dwell（viewport_exit，batch=true，payload: dwellMs）
  - click（tap_post_card，batch=false）
  - dislike（user_action，batch=true）
  - share（dedicated route or batch，batch=true）
  - report（专用路由）
  - like/favorite（声明为 dedicated_route，不走 BehaviorTracker）
- [ ] 声明推荐特征（content_type / tag_count / aspect_ratio / engagement_rate_7d）
- [ ] 声明训练样本 schema（label/positive_signals/negative_signals/features）
- [ ] 运行 `make verify-metadata`

### T2.6 behaviors.yaml → Dart codegen
- [ ] 扩展 `codegen_app_metadata`：解析 behaviors.yaml
- [ ] 生成 `lib/cloud/content/generated/content_behaviors.g.dart`（DO NOT EDIT）
  - `class ContentBehaviorTracker { static trackImpression/trackDwell/trackClick/trackDislike }`
  - 批量路由从 service.yaml 读取，不硬编码
  - batch 缓冲队列 + 自动 flush 逻辑骨架

### T2.7 behaviors.yaml → Python codegen
- [ ] 扩展 `codegen_rec_model_python`：解析 behaviors.yaml
- [ ] 生成 `services/rec-model-service/generated/content_features.py`（Pydantic）
- [ ] 生成 `services/rec-model-service/generated/training_sample.py`（Pydantic）
- [ ] 运行 `make codegen-rec-model-python`

---

## L3-3: privacy-ui-config-contract（隐私 + 端侧配置）

### T3.1 privacy.yaml 声明
- [ ] 创建 `contracts/metadata/content/post/privacy.yaml`
- [ ] 声明端侧 app log 字段过滤策略（location → city_level_only；body → truncate 200chars；embedding → drop）
- [ ] 声明数据生命周期：retention_days: 1825，删除级联顺序（comments → reactions → media_assets → post）
- [ ] 声明 user_deletion_hook: true
- [ ] 声明字段 API alias（_id → postId，embedding → never_expose）
- [ ] 运行 `make verify-metadata`

### T3.2 privacy.yaml → Dart codegen
- [ ] 扩展 `codegen_app_metadata`：解析 privacy.yaml
- [ ] 生成 `lib/cloud/content/generated/content_privacy_policy.g.dart`（DO NOT EDIT）
  - `class ContentPrivacyPolicy { static String? sanitizeForLog(String field, dynamic value) }`
- [ ] 修改 `CloudHttpClient`：请求/响应 log 调用 `ContentPrivacyPolicy.sanitizeForLog()` 过滤字段
- [ ] 运行 `make codegen-app`

### T3.3 ui_config.yaml 声明
- [ ] 创建 `contracts/metadata/content/post/ui_config.yaml`
- [ ] 声明 discovery_tabs（photo/video/moment/article，含 label_key/icon/contentType/layout/columns）
- [ ] 声明 card_config（各类型的 showAuthorAvatar/showLikeCount/actionBarPosition 等）
- [ ] 声明 interaction_config（like/favorite 的 optimistic_update/animation/error_message_key）
- [ ] 声明 feature_flags（enable_helper_read:false / enable_share_to_circle:true / show_view_count:false）
- [ ] 声明 empty_states（feed_empty / feed_error 的 illustration/title_key/subtitle_key/cta）
- [ ] 运行 `make verify-metadata`

### T3.4 ui_config.yaml → Dart codegen
- [ ] 扩展 `codegen_app_metadata`：解析 ui_config.yaml
- [ ] 生成 `lib/cloud/content/generated/content_ui_config.g.dart`（DO NOT EDIT）
  - `class ContentUIConfig { static const List<DiscoveryTabConfig> discoveryTabs }`
  - `static const Map<String, CardConfig> cardConfigs`
  - `static const Map<String, bool> featureFlags`
  - `static const Map<String, EmptyStateConfig> emptyStates`
- [ ] 运行 `make codegen-app`

### T3.5 Discovery 页适配（UI 代码消费 codegen 配置）
- [ ] 修改 `lib/ui/discovery/pages/discovery_page.dart`：
  - TabBar 从 `ContentUIConfig.discoveryTabs` 生成
  - 移除所有硬编码 contentType 字符串
- [ ] 修改 Feed Provider：使用 `ContentUIConfig.featureFlags['enable_helper_read']`
- [ ] `flutter analyze` 无新增错误

---

## L3-4: three-layer-test-contract（三层测试契约）

### T4.1 tests/contract.yaml 创建
- [ ] 创建 `contracts/metadata/content/post/tests/contract.yaml`
- [ ] 将 `service.yaml` 中 `contract_test.service_side` 场景迁移到此文件
- [ ] 补充错误码场景（GetPost(nonExistent) → CONTENT.USER.post_not_found）
- [ ] 补充幂等场景（LikePost x2 → counter=1）
- [ ] 更新 `service.yaml`：删除 `contract_test` 块（测试场景已迁出）

### T4.2 tests/mock.yaml 创建
- [ ] 创建 `contracts/metadata/content/post/tests/mock.yaml`
- [ ] 将 `service.yaml` 中 `contract_test.app_side` 场景迁移到此文件
- [ ] 补充 DTO 解析场景（四类类型分发 + alias 解析）
- [ ] 补充错误码解析场景（每个 errors.yaml code 至少一个）
- [ ] 补充行为上报格式场景（behaviors.yaml 中 batch events）

### T4.3 tests/e2e.yaml 创建
- [ ] 创建 `contracts/metadata/content/post/tests/e2e.yaml`
- [ ] 声明核心集成场景（discovery_feed_load_and_render / like_post_realtime / behavior_batch_report）
- [ ] 声明执行环境：staging，advisory（不阻塞 PR）

### T4.4 Gate 扩展（G4-G10）
- [ ] 扩展 `scripts/gate.sh` 或 `tools/verify_metadata/main.go`：
  - G4: errors.yaml code 在 tests/ 中全覆盖
  - G5: behaviors.yaml routes ⊆ service.yaml api_routes
  - G6: ui_config.yaml contentTypes ⊆ _shared/types.yaml ContentType
  - G7: tests/contract.yaml scenarios ⊆ Go 测试函数名
  - G8: PII/SENSITIVE fields ⊆ privacy.yaml 字段声明
  - G9: behaviors.yaml behavior_events.type ⊆ _shared/types.yaml BehaviorEventType
  - G10: ui_config.yaml feature_flags keys ⊆ 服务治理配置
- [ ] 运行 `make gate`，全部通过

### T4.5 端侧 mock 测试更新
- [ ] 更新 `test/cloud/content/` 下测试（目录调整）
- [ ] 新增 `test/cloud/content/error_code_contract_test.dart`：验证 CloudErrorMapper 解析
- [ ] 新增 `test/cloud/content/behavior_tracker_contract_test.dart`：验证 BehaviorTracker 调用格式
- [ ] 新增 `test/cloud/content/ui_config_contract_test.dart`：验证 ContentUIConfig 完整性

---

## 规划任务（后续演进，不阻塞本期）

- 将 user/chat/circle 域复用相同横切文件模式（每域独立 errors/behaviors/privacy/ui_config）
- ui_config.yaml 增加 `runtime_overridable: true` 标记，支持未来 Remote Config 覆盖
- behaviors.yaml 中 ml_signal 权重改为在推荐服务 Python 代码控制（去除 YAML 中的权重枚举）
- e2e.yaml 场景接入 CI staging 自动触发
