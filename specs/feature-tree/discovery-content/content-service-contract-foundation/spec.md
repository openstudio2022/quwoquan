# L2 特性：content-service-contract-foundation

## 功能说明

内容服务端云一体化契约基础层。将业务对象（Post 及其子类型）的所有横切关注点——接口契约、存储、领域模型、错误码、行为采集与推荐特征、隐私安全、端侧可配置化、三层测试契约——统一纳入以业务对象为中心的元数据目录，并通过 codegen 工具链确保端云双侧代码从同一 YAML 真相源派生，消除人工协调。

**核心目标**：让端侧聚焦交互与呈现（零硬编码），云侧聚焦业务逻辑与性能，所有横切面从 metadata 驱动。

## 范围

**目录结构重组**：
- `contracts/metadata/` 增加域层 `content/`，形成 `contracts/metadata/content/post/` 路径
- `_projections/` 中归属 post 实体的投影 YAML 迁入 `content/post/projections/`
- `contracts/openapi/content-service.v1.yaml` 迁入 `contracts/metadata/content/openapi.yaml`

**新增横切 YAML 文件**（per-entity，均对 codegen 工具可见）：
- `errors.yaml`：域级错误码声明（MODULE.KIND.REASON + i18n + HTTP映射）
- `behaviors.yaml`：用户行为事件 + 推荐特征 schema + 训练样本 schema
- `privacy.yaml`：端侧日志字段过滤策略 + GDPR 数据生命周期 + 字段暴露范围
- `ui_config.yaml`：发现页 tab 配置 + 卡片布局 + feature flags + 空状态

**三层测试契约**（per-entity tests/ 目录）：
- `tests/mock.yaml`：端侧独立测试场景（不依赖云侧）
- `tests/contract.yaml`：云侧契约测试场景（从 service.yaml 迁出，真实 DB）
- `tests/e2e.yaml`：端云集成场景（staging 环境）

**Codegen 工具链扩展**：
- `codegen_app_metadata`：读取新横切文件 → Dart ContentErrorCode / ContentBehaviorTracker / ContentUIConfig / ContentPrivacyPolicy（全部 DO NOT EDIT）
- `codegen_content_service`：读取 errors.yaml → Go 错误码常量
- `codegen_rec_model_python`：读取 behaviors.yaml → Python Pydantic 特征/训练样本 schema
- `CloudErrorMapper` 升级：解析 `MODULE.KIND.REASON` 结构化码 → `ContentErrorCode` enum

**Gate 扩展**（10 项）：
- G4 错误码覆盖：errors.yaml 中每个 code 在 tests/ 中至少有一个场景
- G5 行为事件路由一致性：behaviors.yaml 路由 ⊆ service.yaml api_routes
- G6 UI 配置完整性：ui_config.yaml contentType ⊆ types.yaml ContentType 枚举
- G7 测试场景覆盖：tests/contract.yaml scenarios ⊆ Go 测试函数
- G8 隐私字段完整性：PII/SENSITIVE 字段在 privacy.yaml 中全部声明
- G9 行为类型合法：behaviors.yaml 中所有 type ⊆ _shared/types.yaml BehaviorEventType
- G10 feature flags 端云对齐

## 适用范围与约束

- **适用**：content-service 的 Post 聚合及全部子类型（image/video/micro/article）；后续其他域（user/chat/circle）可复用相同横切文件模式
- **不适用**：本次不扩展 user/chat/circle 域的横切层（模式相同，独立交付）
- **约束**：
  - 所有横切 YAML 文件须通过 `make verify-metadata` 校验
  - codegen 产物标记 `DO NOT EDIT`，由 make gate 通过 hash 比对守护
  - 端侧 UI 禁止直接 import 横切常量之外的任何 metadata 文件
  - 0 到 1，不考虑历史兼容性；旧 _projections/ 路径在工具更新后废弃

## 子节点（L3）

| 子节点 | 职责 | 依赖 |
|--------|------|------|
| `metadata-domain-restructure` | 目录重组：域层+投影迁入+openapi并置 | 无 |
| `fullstack-error-behavior-contract` | errors.yaml + behaviors.yaml + codegen双侧 | metadata-domain-restructure |
| `privacy-ui-config-contract` | privacy.yaml + ui_config.yaml + codegen端侧 | metadata-domain-restructure |
| `three-layer-test-contract` | tests/{mock,contract,e2e}.yaml + gate绑定 | 以上所有 |

## 验收标准概要

- A1：`contracts/metadata/content/post/` 包含全部横切 YAML，`make verify-metadata` 通过
- A2：`make codegen-app` 生成 content_errors.g.dart / content_behaviors.g.dart / content_ui_config.g.dart / content_privacy_policy.g.dart
- A3：`make codegen` 生成 Go errors.go + Python Pydantic schema
- A4：`CloudErrorMapper` 能解析 `CONTENT.USER.post_not_found` → `ContentErrorCode.postNotFound` + i18n message
- A5：端侧 UI 发现页 tab bar 完全由 `ContentUIConfig.discoveryTabs` 驱动，无硬编码 contentType 字符串
- A6：`ContentBehaviorTracker.trackImpression/trackDwell/trackClick` 可调用，路由与 service.yaml 一致
- A7：tests/contract.yaml scenarios 与 Go 契约测试函数一一绑定（`make gate` G7 通过）
- A8：`make gate` 全部 G1-G10 通过
