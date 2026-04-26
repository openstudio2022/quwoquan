# L3：fullstack-error-behavior-contract

## 功能说明

为 Post 实体创建结构化错误码层（errors.yaml）和用户行为采集+特征层（behaviors.yaml），
并扩展 codegen 工具链在端云双侧生成对应代码，消除人工协调。

## 范围

**errors.yaml**：
- content 域全量错误码（MODULE.KIND.REASON 三段格式）
- 每个 code 含 http_status / recovery action / i18n user_message / dart_const / go_const
- codegen → Dart ContentErrorCode enum + ContentErrorMessages（含 zh/en i18n）
- codegen → Go errors.go 错误码常量
- CloudErrorMapper 升级：解析 response body "code" 字段 → ContentErrorCode

**behaviors.yaml**：
- 用户行为事件（impression/dwell/click/dislike/share，batch vs dedicated route）
- 推荐特征声明（content_type/tag_count/aspect_ratio/engagement_rate_7d）
- 训练样本 schema（label/signals/features）
- codegen → Dart ContentBehaviorTracker（batch缓冲 + 自动flush）
- codegen → Python Pydantic ContentFeatures + ContentTrainingSample

## 验收标准

- A1：errors.yaml 覆盖全部已知错误场景，make verify-metadata PASS
- A2：ContentErrorCode enum 与 errors.yaml 一一对应（不多不少）
- A3：CloudErrorMapper 解析 CONTENT.USER.post_not_found → 正确 code + zh message
- A4：ContentBehaviorTracker.trackImpression/Dwell/Click 可调用
- A5：Python Pydantic schema 字段与 behaviors.yaml features 一一对应
- A6：make gate G4（错误码覆盖）+ G5（行为路由）+ G9（行为类型）通过
