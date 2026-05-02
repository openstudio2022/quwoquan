# L3 设计：appearance-accessibility-settings

## 设计动因

见 `appearance-accessibility-settings/spec.md`。本 L3 的核心目标是把“外观与字号偏好”从单端临时状态升级为 `owner 默认值 -> 子账号继承 -> 子账号 override -> 可同步全部账号` 的统一设置体系，并与 `app-theme-infrastructure` 的运行时能力打通。

## 上游输入评审

### 1. PRD 输入稳定性

- `spec.md` 已冻结：账号侧需要跨账号、跨端、弱网与离线补同步
- `acceptance.yaml` 已冻结：本地生效、跨端同步、`last-write-wins`、审计与真机验证均有明确阈值
- “同步所有账号”语义已明确：写入 owner 默认值，并让全部子账号收敛到新的统一默认值

### 2. 现有 metadata / 代码基线评审

现有用户域已经提供可复用基础：

- `quwoquan_service/contracts/metadata/user/user_profile/service.yaml`
  - 已有 `/v1/owner/sub-accounts` 系列端点
  - 已有 `/v1/user/settings/notifications|privacy|calls` 端点
- `quwoquan_service/contracts/metadata/user/user_profile/storage.yaml`
  - 已有 `user_settings` 表，适合承载 owner 默认值
  - 已有 `personas`（SubAccount）实体，可承载子账号 override
- `quwoquan_app/lib/cloud/services/user/auth_repository.dart`
  - 已消费 `/v1/owner/sub-accounts` 生成常量

因此，本 Story **不需要新开服务**，应继续落在 `user-service / user_profile` 现有 metadata 范围内。

### 3. G1 基线

本次 `/design` 已执行并通过：

- `make -C quwoquan_service verify-metadata`
- `make codegen`
- `make codegen-app`

说明当前 metadata / codegen 链路健康，可在后续 Task 中直接扩展用户域契约。

## 对标输入分析

| 输入 | 吸收点 | 本 Story 处理方式 |
|---|---|---|
| Apple HIG | 设置分组、状态可解释性、继承关系表达克制清晰 | 作为设置页结构与状态表达基线 |
| Instagram | 修改后应立即全局生效 | 作为本地应用时延目标基线 |
| 小红书 | 阅读字号对内容体验影响显著 | 首发把 `fontSizePreset` 作为一级偏好 |
| 微信 | 多账号与高频切换场景需要状态稳定 | 用于切号、恢复、低认知负担要求 |
| 抖音 | 沉浸式页面对主题/字号切换稳定性要求高 | 作为全局 runtime 对接稳定性边界 |

## 方案对比

| 维度 | 方案 A：仅本地设备存储（SharedPreferences/Hive） | 方案 B：复用 `UserSetting` + `Persona`，以单一 appearance API 暴露 owner 默认与 sub override（选定） | 方案 C：新建独立 `AppearancePreference` 聚合/表 |
|---|---|---|---|
| 本地生效速度 | 高 | 高 | 高 |
| 跨端同步 | 无法满足 | 可满足 | 可满足 |
| 与现有用户域对齐 | 低 | 高 | 中 |
| 迁移成本 | 低 | 中 | 高 |
| 契约清晰度 | 低 | 高 | 最高 |
| 审计与冲突处理 | 弱 | 高 | 高 |
| 当前阶段适配度 | 不适合 | 最适合 | 过重 |

## 选型决策

**选定方案 B**：复用 `user_profile` 现有聚合与 owner/sub-account 语义，把 owner 默认值落在 `UserSetting`，把子账号 override 落在 `Persona`，再通过一个统一的 appearance settings API 暴露给 app。

### 选定理由

- 最小破坏性：不需要新开服务或新增独立 settings 聚合
- 语义自然：owner 默认与 sub override 正好对应现有 `UserSetting` / `Persona`
- 端侧简单：app 只消费一个 appearance settings 读写接口，不感知底层存储拆分
- 能满足时延、离线、同步、审计与 `last-write-wins`

## 关键设计决策

### KD-1：存储模型采用“owner 默认 + sub override”双层结构

冻结如下 metadata 目标：

#### `UserSetting`（owner 默认值）

目标新增字段：

- `defaultThemeMode`: `system / light / dark`
- `defaultFontSizePreset`: `xs / sm / md / lg / xl`（命名后续可在 metadata 中细化）
- `appearanceVersion`: 整体设置版本号
- `appearanceUpdatedAt`: owner 默认最后更新时间

#### `Persona`（sub override）

目标新增字段：

- `themeModeOverride`: nullable
- `fontSizePresetOverride`: nullable
- `appearanceOverrideUpdatedAt`

读时优先级：

```text
subAccountOverride ?? ownerDefault ?? systemDefault
```

当 `applyScope = all_accounts` 时：

- 更新 owner 默认值
- 清空该 owner 下所有子账号的 appearance override
- 所有账号收敛到新的统一默认值

### KD-2：端侧只暴露一个 appearance settings API

虽然底层存储拆成 `UserSetting + Persona`，但对 app 暴露统一接口：

- `GET /v1/user/settings/appearance`
- `PATCH /v1/user/settings/appearance`

#### GET 返回

返回 `AppearanceSettingsView`，至少包含：

- `themeMode`
- `fontSizePreset`
- `source`: `owner_default / sub_override / system_default`
- `ownerDefaultThemeMode`
- `ownerDefaultFontSizePreset`
- `hasSubAccountOverride`
- `pendingSync`: 仅端侧本地态，服务端不持久化
- `version`
- `updatedAt`

#### PATCH 请求

请求体采用显式作用域，而不是多个分散接口：

- `themeMode`
- `fontSizePreset`
- `applyScope`: `all_accounts / current_sub_account / inherit_owner_default`

理由：

- UI 语义与用户心智更直观
- 端侧逻辑简单，不需要拼多个 owner/sub-account 写接口
- 服务端可以在单次事务中统一处理 owner 默认、sub override 与 override 清理

### KD-3：metadata 基线冻结到现有 `user_profile` 相关文件

后续 `/dev` 实施时，必须优先更新以下文件：

- `quwoquan_service/contracts/metadata/user/user_profile/fields.yaml`
- `quwoquan_service/contracts/metadata/user/user_profile/storage.yaml`
- `quwoquan_service/contracts/metadata/user/user_profile/service.yaml`
- `quwoquan_service/contracts/metadata/user/user_profile/events.yaml`
- `quwoquan_service/contracts/metadata/user/user_profile/errors.yaml`
- `quwoquan_service/contracts/metadata/user/user_profile/tests/contract.yaml`
- `quwoquan_service/contracts/metadata/user/openapi.yaml`
- `quwoquan_service/contracts/metadata/_shared/request_context.yaml`

本轮 design 不直接提交这些 metadata 变更，但已冻结目标落点和作用域，后续必须遵循 `metadata -> verify-metadata -> codegen -> codegen-app` 顺序实施。

### KD-4：跨端同步采用“事件失效通知 + 拉取最新快照”

为满足 `p95 <= 3s`，不能只依赖登录/前台轮询刷新。

选定机制：

1. 服务端提交 appearance 变更后，发布 `UserAppearanceSettingsChanged`
2. `realtime-gateway` 或现有实时通道向同 owner 的在线设备发送失效通知
3. 设备收到通知后重新拉取 `GET /v1/user/settings/appearance`
4. 设备未在线时，下一次登录/前台恢复时执行补拉取

原因：

- 推送消息只传“失效 + version”，避免在通道内复制完整设置模型
- 客户端总是以服务端快照为最终真相，避免广播内容与服务端真实状态分叉

### KD-5：离线与 pending 采用端侧乐观应用 + 待同步队列

端侧引入本地 `PendingAppearanceMutation`：

- 修改后立即更新 `app-theme-infrastructure` 运行时，满足 `<=100ms`
- 若请求失败或离线，记录待同步标记
- 同 scope 的多次修改在本地队列中折叠为最后一次用户意图
- 联网恢复后自动重放

冲突规则：

- 服务端提交时间定义 `last-write-wins`
- 本地收到更高版本远端快照时，以远端为准
- 若本地仍有未提交意图，按最新意图重新发起一次 PATCH

### KD-6：审计不在 UI 层做“日志”，而是走 settings-audit 正式链路

每次 appearance 修改都应记录：

- `ownerUserId`
- `actorSubAccountId`
- `applyScope`
- `oldValues`
- `newValues`
- `deviceId`
- `mutationId`
- `committedAt`
- `clearedOverrideCount`

设置审计与 UI 提示分离：UI 只负责显示“已同步 / 待同步 / 同步失败”，正式追踪由 `settings-audit` 承担。

### KD-7：端侧仓库与运行时解耦

引入独立 `AppearanceSettingsRepository`，不要继续把外观设置塞进 `authRepository` 或 `themeProvider`：

- `cloud/services/user/appearance_settings_repository.dart`
- `app/providers/appearance_settings_provider.dart`
- `core/design_system/providers/theme_provider.dart` 只消费运行时状态，不直接读远端

这样可以让账号设置 Story 与视觉运行时 Story 保持边界清晰：

- 本 Story：负责“设置值”
- `app-theme-infrastructure`：负责“如何应用这些值”

## TDD / ATDD 策略

### ATDD

以 `acceptance.yaml` A1-A8 为主驱动，优先锁定：

- owner 默认、sub override、同步全部账号
- 本地时延与全 app 稳定切换
- 跨端同步、弱网最终一致、离线待同步、冲突与审计

### TDD

实施顺序：

1. 先写 metadata / contract 测试，冻结 API 与数据模型
2. 再写 repository 与本地 pending 队列单元测试
3. 再写设置 UI、跨账号行为与 runtime bridge 测试
4. 最后做多端、多账号、弱网和真机验证

## Task 与测试层映射

| Task | 核心交付 | 对应验收 | 测试层 |
|---|---|---|---|
| T1 | 扩展 `user_profile` metadata：fields/storage/service/errors/openapi/request_context/contract | A1 A2 A7 | T1 |
| T2 | 生成并接入 app/cloud metadata 常量，新增 `AppearanceSettingsRepository` 与 provider | A1 A8 | T1 T3 |
| T3 | 实现本地 optimistic apply、pending 队列、LWW reconcile | A5 A6 A7 | T1 T3 T4 |
| T4 | 实现设置页与子账号 scope 交互：继承状态、同步全部账号默认勾选、恢复继承 | A2 A3 A4 A5 | T2 T3 |
| T5 | 与 `app-theme-infrastructure` 打通，保证运行时在 `<=100ms / <=300ms` 阈值内稳定应用 | A5 A8 | T2 T3 T4 |
| T6 | 实现跨端失效通知、前台补拉取与 settings-audit 链路 | A6 A7 A8 | T3 T4 |

## 未来演进

- 把 appearance 之外的 accessibility 偏好（高对比、粗体、减弱动效）按同样 owner/sub scope 纳入正式同步
- 从“appearance settings”演进到更通用的“scoped settings platform”
- 为用户提供设置变更记录与一键回退能力
- 为 ops / portal 提供受控只读审计视图，而非直接改写用户设置
