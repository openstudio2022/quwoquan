# L3：privacy-ui-config-contract

## 功能说明

为 Post 实体创建隐私安全层（privacy.yaml）和端侧可配置化层（ui_config.yaml），
消除端侧硬编码 contentType/tab 顺序/布局参数，并自动化 PII 字段的 app 日志过滤。

## 范围

**privacy.yaml**：
- 端侧 app log 字段 mask 策略（location → city_level / body → truncate / embedding → drop）
- GDPR 数据生命周期（retention_days + 删除级联顺序 + user_deletion_hook）
- API 字段 alias（_id → postId，embedding → never_expose）
- codegen → Dart ContentPrivacyPolicy.sanitizeForLog()
- CloudHttpClient 集成：请求/响应 log 自动过滤

**ui_config.yaml**：
- discovery_tabs（photo/video/moment/article，含 label_key/layout/columns）
- card_config（各类型展示参数）
- interaction_config（like/favorite 的乐观更新/动画/错误提示配置）
- feature_flags（enable_helper_read/show_view_count/enable_share_to_circle）
- empty_states（feed_empty/feed_error 的 illustration/文案 key）
- codegen → Dart ContentUIConfig（完全类型化，DO NOT EDIT）
- Discovery 页消费：TabBar/CardRenderer 由 ContentUIConfig 驱动

## 验收标准

- A1：privacy.yaml PII/SENSITIVE 字段全覆盖，make gate G8 通过
- A2：ContentPrivacyPolicy.sanitizeForLog 对 location 返回城市级别
- A3：CloudHttpClient log 路径自动调用 sanitizeForLog，flutter test 验证
- A4：ui_config.yaml tab 配置与 types.yaml ContentType 枚举一致，make gate G6 通过
- A5：ContentUIConfig.discoveryTabs 长度 == ui_config.yaml discovery_tabs 数量
- A6：discovery_page.dart 不含硬编码 contentType 字符串
- A7：make gate G10（feature flags 对齐）通过
