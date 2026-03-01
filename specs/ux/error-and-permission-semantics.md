# 错误与权限统一语义规范

> 适用于所有涉及云端交互与系统权限的端侧页面。  
> **特性树**：`runtime/runtime-client-foundation/error-permission-display-semantics`（L3）  
> 参考：`02-dart-coding.mdc`、`06-semantic-consistency-audit.mdc`、`07-error-permission-semantics.mdc`

---

## 1. 云端/网络错误语义

### 1.1 适用范围

| 场景 | 说明 | 示例 |
|------|------|------|
| **页面加载** | 首次进入页面的数据拉取失败 | 发现流、圈子列表、个人主页、聊天列表 |
| **列表加载** | 分页、下拉刷新、上拉加载失败 | feed append、评论分页 |
| **编辑/提交** | 创建、更新、删除等写操作失败 | 发微趣、发评论、修改资料、退出群聊 |
| **单条拉取** | 详情、单条数据 fetch 失败 | 文章详情、视频详情、用户主页 |

### 1.2 错误严重度与展示方式

| 严重度 | 场景 | 展示方式 | 说明 |
|--------|------|----------|------|
| **阻塞性** | 页面/列表首次加载失败、无数据可降级 | 内联占位（Inline Placeholder） | 整块内容区被错误态替换，持久显示 |
| **次要** | 提交失败、单次操作失败、可重试的瞬时错误 | SnackBar（冒泡） | 底部/浮动冒泡，3–5 秒自动消失，可带操作 |
| **可忽略** | 后台静默失败、有降级方案 | 不提示或极轻量 SnackBar | 如缓存命中后忽略网络错误 |

### 1.3 语义 Token（设计系统）

| 用途 | API | 说明 |
|------|-----|------|
| **错误文案颜色** | `Theme.of(context).colorScheme.error` 或 `AppColors.error` | 主错误文本 |
| **辅助文案颜色** | `Theme.of(context).colorScheme.onSurfaceVariant` 或 `AppColorsFunctional.getColor(..., foregroundSecondary)` | 副标题、说明 |
| **错误文案字号** | `textTheme.bodyMedium` / `AppTypography.body` | 主错误信息 |
| **辅助文案字号** | `textTheme.bodySmall` / `AppTypography.secondary` | 副说明 |
| **间距** | `AppSpacing.interGroupLg`、`AppSpacing.interGroupMd` | 组间、卡片内边距 |
| **圆角** | `AppSpacing.borderRadius` 或 `AppSpacing.smallBorderRadius` | 错误卡片 |

### 1.4 展示形态

#### 1.4.1 内联占位（阻塞性错误）

```
┌─────────────────────────────────────┐
│         [可选] Icons.cloud_off       │
│                                     │
│  暂时无法加载，请检查网络后重试       │  ← bodyMedium, colorScheme.error
│  （可选）副说明                      │  ← bodySmall, onSurfaceVariant
│                                     │
│  [重试]                             │  ← FilledButton / TextButton
└─────────────────────────────────────┘
```

- 替换原内容区，居中或靠上，使用卡片式容器（`Card` 或 `Container` + 圆角 + 背景）
- 主操作：**重试**（调用原加载逻辑）
- 禁止使用 SnackBar 作为阻塞性错误的唯一展示方式

#### 1.4.2 SnackBar（次要错误）

- `behavior: SnackBarBehavior.floating`
- `margin: EdgeInsets.all(AppSpacing.interGroupMd)`（或 `context.safeGetContainerSpacing`）
- 可带 `action: SnackBarAction(label: '重试', ...)`
- 禁止用于**阻塞性**错误（页面首次加载失败、权限未开启等）

### 1.5 文案与错误码映射

| 来源 | 端侧映射 |
|------|----------|
| 云端 `*.*.user_message` | 优先使用 `contracts/metadata/*/errors.yaml` 中定义的 `user_message.zh/en`，经 codegen 或 l10n 暴露 |
| 网络超时 / SocketException | 统一：「暂时无法加载，请检查网络后重试」 |
| 4xx/5xx 无结构化 code | 通用：「加载失败」或「操作失败，请稍后重试」 |
| CloudException.code | 根据 `CloudErrorMapper` 或 domain 专属 mapper 映射到 l10n key |

### 1.6 统一 l10n key 约定

```
# 通用云端/网络
loadFailed              # 加载失败
submitFailed            # 提交失败（或操作失败）
networkUnavailable      # 暂时无法加载，请检查网络后重试

# domain 专属（如 content、integration）
# 见 contracts/metadata/*/errors.yaml → dart_const → l10n
```

---

## 2. 权限类语义

### 2.1 适用范围

| 权限类型 | 场景 | 示例 |
|----------|------|------|
| **定位** | 附近位置、地图选点、签到 | 创作选位置、发现附近 |
| **相册** | 选择图片/视频、保存到相册 | 发美图、发微趣、媒体选择器 |
| **相机** | 拍照、录像 | 创作拍照、扫一扫 |
| **麦克风** | 录像配音、语音消息 | 录视频、语音输入 |
| **通知** | 推送、提醒 | 消息推送 |

### 2.2 权限状态与展示方式

| 状态 | 说明 | 展示方式 |
|------|------|----------|
| **未请求** | 首次进入功能，尚未弹出系统对话框 | 功能入口处引导 → 触发 request |
| **已拒绝（可再请求）** | 用户点了「不允许」，可再次请求 | 权限卡片内联占位 + 说明 |
| **永久拒绝** | 用户点了「不允许」且勾选「不再询问」/ iOS 设置中关闭 | 权限卡片 + **去设置** 主操作 |
| **已授予** | 正常使用 | 无提示 |

### 2.3 权限卡片统一形态

```
┌─────────────────────────────────────┐
│  [权限图标]  Icons.location_off      │  图标：与权限类型对应
│                                     │
│  请在设置中为本应用开启定位权限       │  主文案：bodyMedium, error 或 foregroundPrimary
│  （可选）开启后可展示附近地点         │  副文案：bodySmall, foregroundSecondary
│                                     │
│  [去设置]  [取消/跳过]               │  主操作：openAppSettings / openLocationSettings
└─────────────────────────────────────┘
```

### 2.4 权限语义 Token

| 用途 | API |
|------|-----|
| 权限图标 | `Icons.location_off` / `Icons.photo_library_outlined` / `Icons.camera_alt_outlined` / `Icons.mic_off` |
| 主文案颜色 | 阻塞时 `colorScheme.error`，引导时 `foregroundPrimary` |
| 副文案颜色 | `foregroundSecondary` |
| 卡片背景 | `Theme.of(context).colorScheme.surfaceContainerHighest` 或 `backgroundSecondary` |
| 卡片圆角 | `AppSpacing.borderRadius` |
| 内边距 | `AppSpacing.interGroupLg` |

### 2.5 权限类型与 l10n key 约定

| 权限 | 主文案 key | 去设置 key |
|------|------------|------------|
| 定位 | `locationAppPermissionRequired` | `locationOpenSettings` |
| 相册 | `mediaPickerPermissionDenied` | `openSettings`（通用） |
| 相机 | `cameraPermissionRequired` | `openSettings` |
| 麦克风 | `microphonePermissionRequired` | `openSettings` |

通用 key（可复用）：
```
permissionRequired       # 需要 XXX 权限
openSettings             # 去设置
```

### 2.6 特定权限卡片（地图/位置）

地图场景除遵循 2.3 通用形态外，额外约定：

- **加载态**：`locationFetchingResult`（正在获取结果）+ `CircularProgressIndicator`
- **错误态**：区分
  - 未开启定位权限 / 未批准应用 → 权限卡片 + 去设置
  - 云端超时 / 服务异常 → 内联错误卡片 + 重试（使用 `integration/location/errors.yaml` 对应文案）
- **主操作**：永久拒绝时仅展示「去设置」，非永久拒绝时可展示「重试」引导再次请求

### 2.7 交互流程

1. **进入功能** → 检查权限
2. **未授予** → 请求 `requestPermission()`
3. **拒绝** → 若可再请求，展示权限卡片 + 副说明；若永久拒绝，展示权限卡片 + 「去设置」
4. **去设置** → 调用 `Geolocator.openAppSettings()` 或 `openLocationSettings()`，返回后重新检查权限并刷新 UI

---

## 3. 实现约束（强制）

- 所有错误/权限文案必须来自 l10n（`context.l10n.*`）或 `UITextConstants`，禁止硬编码中文字符串
- 颜色、字号、间距必须使用 `AppTypography`、`AppSpacing`、`AppColors` / `colorScheme`
- 云端错误码映射：优先解析 `CloudException.code`，映射到 domain 对应 l10n；无 code 时使用通用 `loadFailed` / `submitFailed`
- 权限相关：使用 `geolocator` / `permission_handler` 等统一包，禁止各页面自行实现分散逻辑

---

## 4. 测试目录结构（按领域服务划分）

### 4.1 原则

- **禁止** `test/features/`、`test/cloud/integration/` 作为顶层
- **统一按领域服务划分**：cloud、ui 下仅按 content、discovery、chat、user 等域组织
- **集成归属到使用它的领域下**：若 content 领域使用 location，则 location 相关测试放在 `content/location/`；若 discovery 使用，则放在 `discovery/location/`
- **领域与实体使用名词**：禁止用动词（如 create、publish）作为目录名；使用 entry（创作入口/草稿）、post、location、circle 等名词

### 4.2 目录结构

```
test/
├── cloud/
│   ├── content/
│   │   ├── post/contract/              # post 业务对象
│   │   └── location/contract/          # content 领域使用的 location 集成
│   │       # CreateLocationService、LocationRepository 契约、错误码
│   ├── discovery/
│   │   └── post/...
│   │   # 若 discovery 有 location（附近流）→ discovery/location/contract/
│   └── chat/...
│
└── ui/
    ├── content/
    │   ├── post/...
    │   └── entry/                      # 创作入口（entry = 草稿/创作项，名词）
    │       ├── contract/               # CreateLocationService、CreateCircleService
    │       └── widgets/                # 位置选择页、权限/错误态 UI
    ├── discovery/post/...
    └── chat/...
```

### 4.3 与 gate 的衔接

- L1a/L1b/L1c 纳入 `make gate`：`flutter test test/cloud/ test/components/ test/ui/`
- Patrol 为 pre-release advisory，不阻塞 PR

---

## 5. 端侧验证策略（交互过程异常为核心）

### 5.1 验证原则

- **核心是交互过程的异常**：权限拒绝、云端超时、加载失败时，UI 是否展示正确文案和操作（去设置、重试）
- **弱化纯 l10n 契约**：仅断言 l10n key 存在性的测试价值低，不单独保留；验证纳入 L1b/L1c 交互测试
- **L1b/L1c 为主**：错误态、权限态、加载态在真实交互场景下验证

### 5.2 测试层级与分工

| 层级 | 类型 | 验证内容 | 放置路径 |
|------|------|----------|----------|
| **L1a** | Contract | CloudException.code → l10n key 映射（可选，非 key 存在性） | `test/cloud/content/location/contract/` |
| **L1b** | Widget | 权限拒绝、云端错误、加载态 UI 渲染、按钮可见 | `test/ui/content/entry/widgets/` |
| **L1c** | Journey | 创作流程「选位置 → 失败」的端到端表现 | `test/ui/content/entry/journeys/` |
| **L4** | Patrol | 真机权限弹窗、去设置跳转（advisory） | `test/patrol/content/` |

### 5.3 L1a 契约测试（极简）

- **不推荐**：纯断言 l10n key 存在、非空的测试
- **可选**：CloudException.code → l10n key 映射表契约（从 `integration/location/errors.yaml` 派生），用于守护错误码与文案 key 的对应关系
- 路径：`test/cloud/content/location/contract/`（content 领域下的 location 集成）

### 5.4 L1b Widget 测试（核心）

**目标**：在交互中验证权限态、错误态、加载态的 UI 表现。

**前提**：生产代码支持依赖注入
- 抽取 `LocationPermissionChecker` 接口，默认实现调用 `Geolocator`，测试注入 `FakeLocationPermissionChecker` 返回 `permanentlyDenied` / `granted`
- 注入 `CreateLocationService`，测试中令 `nearby()` 抛出 `CloudException`

**场景与断言**：

| 场景 | 注入 | 断言 |
|------|------|------|
| 权限永久拒绝 | FakeChecker 返回 `permanentlyDenied` | 展示 `locationAppPermissionRequired` + 「去设置」按钮 |
| 云端超时 | CreateLocationService.nearby() 抛 `CloudException(upstream_timeout)` | 内联错误文案 + 重试按钮 |
| 加载态 | 正常加载中 | `locationFetchingResult` + `CircularProgressIndicator` |

路径：`test/ui/content/entry/widgets/location_selector_page_widget_test.dart`

### 5.5 L1c Journey 测试

**目标**：创作流程中「进入位置选择 → 失败」的端到端表现。

- 注入 Mock `CreateLocationService`：`nearby()` 抛 `CloudException`
- 断言：位置选择页展示错误文案，且为内联（非 SnackBar）
- 若有「去设置」：断言按钮存在且可点击（不实际跳转）

路径：`test/ui/content/entry/journeys/entry_location_error_journey_test.dart`

### 5.6 L4 Patrol（可选）

- 真机/模拟器：进入位置选择 → 拒绝权限 → 断言「去设置」按钮可见
- 点击「去设置」→ 断言能打开系统设置（不断言返回后状态）

路径：`test/patrol/content/` 或 `test/patrol/integration/location/`

---

## 6. 与现有规则的关系

| 规则 | 关系 |
|------|------|
| `02-dart-coding` | 本规范在错误/权限场景下细化设计系统使用方式 |
| `06-semantic-consistency-audit` | 本规范定义的 token 与形态纳入语义一致性检查范围 |
| `contracts/metadata/*/errors.yaml` | 云端错误码与 user_message 为端侧文案的权威来源 |
| `03-testing` | 本规范第 4、5 节细化测试目录与验证策略，与 03-testing 一致 |
