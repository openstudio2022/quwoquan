# 隐私与安全数据保护统一规范（PII / Sensitive / Secrets）

目标：在不增加各服务额外负担的前提下，实现商用化所需的隐私合规与安全防护：
- 字段分级可识别（哪些是个人隐私/安全敏感）
- 日志可配置匿名化/脱敏（默认关闭，便于调试；可按环境开启）
- 存储可配置加密（默认关闭；可按环境/字段分级开启）
- 隐私数据保留期限可控（默认不缩短；可按环境/分级配置）

本规范以“contracts 标注 + pkg 自动处理 + sys 配置开关”为落地方式。

---

## 1. 数据分级（强制口径）

对所有 API schema / event schema / DB model 字段进行分级标注（至少在 contracts 层可追溯）。

建议分级枚举（最小集合）：
- `PUBLIC`：公开信息（可入日志/指标，但仍需避免高基数）
- `PII`：个人可识别信息（如手机号、邮箱、精确地址、设备标识符等）
- `SENSITIVE`：敏感业务信息（如私信内容、用户画像明细、内部策略参数）
- `SECRET`：安全秘密（token、密钥、密码、验证码、签名材料）

---

## 2. 如何在 contracts 中标注（统一方式）

### 2.1 OpenAPI（推荐方式）

对 schema 属性增加扩展字段：
- `x-data-classification`: `PUBLIC|PII|SENSITIVE|SECRET`
- `x-loggable`: `true|false`（默认 true，但 `SECRET` 必须为 false）

示例（片段）：
```yaml
phone:
  type: string
  x-data-classification: PII
  x-loggable: false
```

### 2.2 JSON Schema（消息/事件）

对字段增加 `x-data-classification`（或 `x-...` 扩展），与 OpenAPI 同枚举。

---

## 3. 日志匿名化/脱敏（运行时自动完成）

### 3.1 默认策略（满足你的诉求）

- **默认不匿名化**：`sys.privacy.log.anonymize.enabled = false`
- 按环境启用：prod/staging 可开启，local/dev 默认关闭

### 3.2 脱敏规则（建议）

- `PII`：mask 或 hash（带稳定盐，便于聚合但不可逆）
- `SENSITIVE`：默认不入日志（或只记录摘要）
- `SECRET`：绝对禁止入日志

### 3.3 落地方式（不增加服务负担）

- 由 `runtime/observability` 提供统一 logger + sanitizer
- 服务只传结构化字段，是否脱敏由 `runtime/config` 读取 `sys.*` 开关决定

---

## 4. 存储加密（运行时可配置）

### 4.1 默认策略（满足你的诉求）

- **默认不加密**：`sys.privacy.storage.encrypt_pii.enabled = false`
- 可按环境开启：prod 开启或对部分字段开启

### 4.2 约束

- 一旦开启加密，需要明确：查询索引策略（不可对密文做范围查询）与迁移策略（历史数据是否回填）
- `SECRET` 不应持久化（如必须持久化，应使用专用密钥管理与最小权限）

> 本规范只定义“开关与边界”，具体加密实现由后端技术栈选择（Mongo/PG 字段级加密或应用层加密）。

---

## 5. 隐私数据保留期限（Retention）

默认遵从 `contracts/data_retention_and_sampling.md`。
另提供可配置项用于“隐私最小化”（按分级）：
- `sys.privacy.retention.pii_days`（默认不启用或等同普通保留）
- `sys.privacy.retention.sensitive_days`

> 要求：保留期限策略必须可审计、可回滚，并在环境维度配置。

---

## 6. 与验收标准/服务治理的关系（强制）

- 验收必须覆盖：字段分级标注是否齐全、日志是否泄露、脱敏开关是否生效（见 `contracts/acceptance_criteria.md`）
- 服务治理必须覆盖：debugMessage 脱敏、禁止泄露 token（见 `contracts/error_codes.md` 与 `contracts/service_governance.md`）

