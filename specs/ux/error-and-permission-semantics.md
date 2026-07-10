# 错误、权限与登录门禁统一语义规范

> 适用于所有涉及云端交互、系统权限、登录门禁与提交动作的端侧页面。  
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
| **次要** | 提交失败、单次操作失败、可重试的瞬时错误 | 弹窗 `actionDialog` 或轻提示 `AppToast` | 需用户决策（重试/确认）→ 弹窗；无需决策 → `AppToast` 冒泡 3 秒自动消失 |
| **可忽略** | 后台静默失败、有降级方案 | 不提示或极轻量 `AppToast` | 如缓存命中后忽略网络错误 |

> 术语说明：本项目端侧**没有** Material `SnackBar` / `ScaffoldMessenger`（`lib/**` 全量为空）。所有"冒泡/轻提示"统一指基于 `OverlayEntry` 的 `AppToast`（`lib/core/widgets/app_toast.dart`）。历史文档中"SnackBar"一律等价理解为 `AppToast`，新代码禁止引入 Material `SnackBar`。

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

#### 1.4.2 弹窗 / 轻提示（次要错误）

次要错误按"是否需要用户决策"二选一：

- **需要决策（提交/发布/删除失败可重试）** → `AppActionErrorFeedback.show`（居中 `CupertinoAlertDialog`，标题 + 正文 + 主操作`再试一次` + 取消）。无主操作时自动退化为 `AppToast`。
- **无需决策（纯通知、约束提示）** → `AppToast.show`（`OverlayEntry` 冒泡，3 秒自动消失，无按钮）。

约束：
- 禁止用于**阻塞性**错误（页面首次加载失败、权限未开启等）。
- 禁止引入 Material `SnackBar`；轻提示一律走 `AppToast`。

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

### 1.7 统一 UI 错误语义对象

端侧页面不得直接把 `RuntimeFailure` / `CloudException` / 本地校验结果原样泄漏到页面组件，
必须先提升为一层**面向用户的 UI 语义对象**。推荐字段：

| 字段 | 说明 |
|------|------|
| `category` | `pageLoad` / `sectionLoad` / `listAppend` / `submit` / `authRequired` / `permissionRequired` / `validation` / `notFound` / `rateLimited` / `backgroundAction` |
| `scope` | `page` / `section` / `dialog` / `global` / `inlineField` |
| `title` | 用户第一眼识别失败类型的标题 |
| `message` | 主说明文案 |
| `secondaryMessage` | 可选的补充说明，如“登录后将继续当前操作” |
| `primaryAction` | `retry` / `login` / `openSettings` / `back` / `dismiss` / `resubmit` |
| `secondaryAction` | 可选次操作，如“取消”/“稍后” |
| `sourceCode` | 原始 error code（便于诊断与埋点） |
| `failureKind` | 原始 `RuntimeFailureKind` |
| `recoveryAction` | 归一化后的恢复动作，来源于 metadata / runtime recovery / 本地权限状态 |
| `appearanceMode` | `inherit / light / dark`，错误页使用的局部外观模式；默认 `inherit` |
| `sourceRouteId` / `sourceSurfaceId` | 可选来源路由/表面诊断信息，用于证明错误页保持来源上下文，不参与错误码事实 |

统一规则：

- **domain code 优先**：若 `CloudException.code` 可解析为 domain error enum，则优先消费该枚举映射的文案。
- **服务端 `userMessage` 次之**：若 `RuntimeErrorResponse.userMessage` 存在，允许作为首选 message。
- **runtime kind 回退**：domain code 与 `userMessage` 都不可用时，再退到 `RuntimeFailureKind`。
- **场景覆盖**：同一错误在不同 `category + scope` 下可以映射为不同标题、按钮与载体。

#### 1.7.1 来源外观模式（sourceAppearanceMode）

内容消费、沉浸媒体、外链直达等页面可能在成功态强制深色，但失败态仍应回到用户进入该页时的来源外观。错误页语义因此增加 `sourceAppearanceMode` 约束：

- 来源页面进入目标页时，若已经解析为浅色/深色，应通过路由或页面参数传递 `light` / `dark`；不保存 `system`，外部深链缺省时按当前全局主题继承。
- `AppPageErrorState` 按 `UiErrorSemantic.appearanceMode` 包局部 `CupertinoTheme`，并使用同一背景、文字、按钮 token 渲染。
- 成功进入沉浸式 viewer、相机、编辑器等专用场景时，页面可继续使用自身强制外观；但首屏拉取失败、内容不存在、权限失败等错误页必须保持来源外观。
- `appearanceMode` 不改变 `RuntimeFailure`、`CloudException`、后端错误码或恢复动作；它只是 UI 展示约束，避免异常页继承错误的沉浸式深色上下文。

### 1.8 页面首屏 / 局部区块 / 列表追加语义契约

| 场景 | 影响范围 | 推荐载体 | 主操作 | 禁止 |
|------|----------|----------|--------|------|
| **首屏失败且无数据** | 阻塞整页 | `AppPageErrorState` | `重试` / `登录` / `去设置` | 只用 SnackBar / Toast |
| **局部区块失败** | 页面主框架仍可继续 | `AppSectionErrorCard` | `重试` | 用整页错误替换整个页面 |
| **首屏失败但有缓存/旧数据** | 非阻塞 | 顶部 banner / 轻量提示 / 区块提示 | 可选 `重试` | 清空旧数据后回退为空白页 |
| **分页追加失败** | 仅影响继续滚动 | 列表尾部错误行 / sentinel | `重试` | 把已加载内容整体替换成首屏错误页 |
| **下拉刷新失败** | 不影响当前内容 | `AppActionErrorFeedback` / 轻提示 | 可选 `重试` | 直接清空当前列表 |

列表场景必须显式拆分以下 3 类状态：

1. `initialBlockingError`：首屏失败且当前无内容。
2. `staleDataError`：已有旧内容但远端刷新失败。
3. `appendError`：滚动触底加载下一页失败。

### 1.9 表单 / 提交 / 对话框动作失败契约

| 场景 | 推荐载体 | 说明 |
|------|----------|------|
| **字段校验失败** | 字段下方提示或 `inlineField` 语义 | 不应伪装成网络错误 |
| **页面级提交失败** | 页内 `AppSectionErrorCard` 或 `AppActionErrorFeedback` | 保留用户已填写内容，允许继续编辑 |
| **对话框 / sheet 内提交失败** | `dialog` scope 的 `AppActionErrorFeedback` 或对话框内错误区 | 失败提示应留在当前上下文，不应只剩一条瞬时 toast |
| **成功后失败回滚** | 动作级反馈 + 恢复建议 | 如点赞失败、发消息失败、上传失败 |

提交类页面必须满足：

- **不得**在 `catch (_) { ... }` 中吞错后写固定字符串。
- **不得**把字段校验、登录门禁、提交失败三类语义混成同一个分支。
- **必须**保留表单输入态，失败后允许用户继续修改或重试。

### 1.10 登录门禁语义契约

登录门禁属于**可恢复的交互阻塞**，不是单纯的路由跳转逻辑。

| 场景 | 推荐载体 | 主操作 | 补充说明 |
|------|----------|--------|----------|
| **整页内容需登录后可见** | `AppInlineGateState` / `AppPageErrorState` | `登录` | 说明“登录后查看什么” |
| **单次动作需登录** | `AppActionErrorFeedback` 或轻提示 + 跳登录 | `登录` | 若存在 continuation，应提示“登录后将继续当前操作” |
| **登录态过期** | `AppActionErrorFeedback` / 页态 | `重新登录` | 与普通 `401 unauthorized` 区分 |

实现约束：

- `AuthGateReason` 是“为什么需要登录”的真相源。
- `AuthContinuation` 是“登录后将继续什么动作”的真相源。
- 任何登录门禁提示都必须能够从这两者推导出用户可理解的说明，不得仅显示“请先登录”。

### 1.11 操作级失败反馈契约

后台异步或局部动作失败（点赞、收藏、发消息、预取、上传）应使用更轻量的动作反馈语义：

| 类型 | 推荐载体 | 说明 |
|------|----------|------|
| **无可恢复动作** | Toast / 轻提示 | 仅说明失败，不强塞按钮 |
| **可立即重试** | `AppActionErrorFeedback` + `重试` | 如发送失败、追加失败 |
| **需用户修正输入** | `AppActionErrorFeedback` / 字段提示 | 如评论超长、内容为空 |

统一原则：

- 按 `recovery_action + 交互场景` 决定按钮是否出现。
- 有旧内容可继续消费时，优先保留旧内容并给轻提示。
- 无恢复动作的错误，不得为了“统一”硬塞无意义按钮。

### 1.12 低打扰错误 UX 分层（新增强制口径）

统一错误语义的目标是帮助用户恢复，不是制造“系统警报”。默认禁止使用惊叹三角、红色大标题、强边框和巨大刷新图标。只有账号安全、破坏性动作、权限高风险等确实需要警觉的场景，才允许使用错误色强调。

| 场景 | 影响范围 | 载体 | 停留时间 | 操作 |
|------|----------|------|----------|------|
| **下拉刷新失败 / 已有内容刷新失败** | 不影响当前内容 | 顶部轻量胶囊 `transientNotice` | 约 1.8–2.5 秒，回弹后出现，滚动/再次刷新即消失 | 默认无按钮 |
| **分页追加失败 / 瀑布流触底失败** | 仅影响继续浏览 | 列表尾部 `appendFooter` | 常驻在尾部，直到重试成功或离开列表 | 可点“轻点重试”，继续上滑也可触发重试 |
| **首屏无数据且页面打不开** | 阻塞整页 | 柔和整页空态 `emptyPage` | 持久显示 | `再试一次` / `去登录` / `去设置` |
| **局部区块失败** | 不影响页面主框架 | 低强调区块占位 `sectionSoftCard` | 持久显示在区块内 | 可选 `再试一次` |
| **主动作失败** | 当前动作未完成 | 轻量 dialog / sheet 内错误区 `actionDialog` | 用户确认后消失 | `再试一次` / `我知道了` |
| **登录/权限门禁** | 可恢复的交互阻塞 | 引导卡 `gateCard` | 按场景持久或弹层 | `去登录` / `去设置` |

文案分层：

- 首屏网络失败：标题“暂时连不上”，说明“检查网络后再试一次，或稍后回来看看。”
- 下拉刷新失败：“网络不太稳定，刚刚没有刷新成功。”
- 分页失败：“后面的内容暂时没拉到，上拉再试。”
- 服务暂不可用：“服务暂时不可用，稍后自动恢复后再试”
- 内容不存在：“内容不可用了”，说明“可能已被删除或暂时无法查看。”
- 权限门禁：“需要开启定位权限”，说明“开启后才能展示附近位置。”
- 登录门禁：“登录后继续”，说明来自 `AuthGateReason` 与 `AuthContinuation`。

实现要求：

- `UiErrorSemantic` 必须携带展示意图（presentation）与语气（tone），页面不得仅按 `category` 自行猜测组件。
- `AppPageErrorState` 只用于首屏无数据的阻塞错误，不得用于已有内容刷新失败或分页失败。
- `AppSectionErrorCard` 必须是弱强调，不得使用红色大标题或惊叹图标。
- 列表页必须为刷新失败和分页失败提供专用载体，禁止把 `staleDataError` / `appendError` 渲染成整页错误卡。

### 1.13 错误展示载体决策矩阵（权威边界 · 全屏 vs 弹窗）

> 本节是"什么时候全屏、什么时候弹窗、什么时候卡片/footer/横幅/toast"的**唯一权威边界**。
> 代码层真相源是 `UiErrorSemanticResolver._presentationFor`（`quwoquan_app/lib/core/errors/ui_error_semantics.dart`）。
> 本表必须与该函数保持一致；任何调整先改本表，再改 `_presentationFor`，最后补/改测试。

#### 1.13.1 presentation → 渲染组件 → 视觉形态

| `UiErrorPresentation` | 渲染组件（`app_error_states.dart`） | 视觉形态 | 是否阻塞 | 是否丢失上下文 |
|---|---|---|---|---|
| `emptyPage` | `AppPageErrorState` | **全屏**（顶栏下方内容区铺满，柔和插图 + 标题 + 副文案 + 主/次操作） | 阻塞整页 | 进入即失败，本无内容 |
| `sectionSoftCard` | `AppSectionErrorCard` | 区块内软卡片（弱强调，无插图） | 仅区块 | 否，其余内容可用 |
| `appendFooter` | `AppListAppendErrorFooter` | 列表尾部错误行 | 仅"加载更多" | 否 |
| `transientNotice` | `AppTransientErrorNotice` | 顶部轻量胶囊横幅 | 不阻塞 | 否，保留已有内容 |
| `actionDialog` | `AppActionErrorFeedback`（`CupertinoAlertDialog`，无主操作时退化 `AppToast`） | **居中弹窗** | 弹层阻塞、保留底层页面 | **否（关键：保留用户已输入上下文）** |
| `gateCard` | `AppInlineGateState` | 登录/权限引导卡 | 按场景 | 否 |
| `inlineField` | 字段内联提示 | 字段下方文字 | 否 | 否 |
| —（纯通知） | `AppToast` | 底部冒泡 toast | 否 | 否 |

#### 1.13.2 category × scope → presentation（与 `_presentationFor` 一一对应）

判定按优先级自上而下短路：

1. `scope == inlineField` → `inlineField`
2. `category ∈ {authRequired, permissionRequired}` → `gateCard`
3. `category == listAppend` → `appendFooter`
4. `category == backgroundAction` → `transientNotice`
5. `scope ∈ {dialog, global}` 或 `category ∈ {submit, rateLimited}` → `actionDialog`
6. `scope == section` 或 `category == sectionLoad` → `sectionSoftCard`
7. 其余（默认，含 `category == pageLoad` 且 `scope == page`）→ `emptyPage`

#### 1.13.3 全屏 vs 弹窗 决策树（强制）

```
是字段级校验？ ── 是 ──► inlineField
   │否
需要登录/权限恢复？ ── 是 ──► gateCard（引导卡，去登录/去设置）
   │否
是"加载更多"分页失败？ ── 是 ──► appendFooter
   │否
是后台/刷新静默失败、且已有内容？ ── 是 ──► transientNotice（横幅，不替换内容）
   │否
是用户主动一次性动作（提交/发布/删除/重试/限流），
或处于 dialog/global 浮层上下文，
或页面有不可丢失的已输入上下文？ ── 是 ──► actionDialog（弹窗；保留底层页面与输入）
   │否
仅某区块失败、整体可用？ ── 是 ──► sectionSoftCard
   │否
进入页面即失败且当前无任何内容可展示？ ── 是 ──► emptyPage（全屏）
```

#### 1.13.4 关键边界判据（评审与门禁口径）

- **全屏 `emptyPage` 仅用于**：被动加载（非用户主动提交）失败 + 当前无内容 + 整页阻塞。例：附近位置页首加载失败、详情页首加载失败。
- **弹窗 `actionDialog` 仅用于**：用户主动触发的一次性动作失败，且**必须保留底层页面与用户已输入内容**。例：发布设置页"确认发布"失败——用户已填好可见性/位置/圈子，**禁止用全屏覆盖**，必须弹窗让其重试或取消。
- **互斥红线**：
  - 含用户输入的表单/sheet 的提交失败 **禁止** 用 `emptyPage`（会丢输入）。
  - 进入即失败的空页 **禁止** 仅用 `AppToast`（无可恢复主操作、无上下文）。
  - 阻塞性错误 **禁止** 仅用 `AppToast` / `transientNotice`。
- **主操作必达**：`emptyPage` 与 `actionDialog` 必须带主操作（`再试一次` / `去登录` / `去设置`）；`actionDialog` 无主操作时退化为 `AppToast`。

#### 1.13.5 回归防护

- 单测守护：`quwoquan_app/test/local_contract/core/errors/ui_error_semantics__local_contract_test.dart` 的"错误展示载体决策矩阵"测试组必须逐条断言 1.13.2 的 7 条映射（覆盖每个 `category × scope` 组合到目标 `presentation`），任何对 `_presentationFor` 的改动若未同步本表与测试即失败。
- 静态门禁：`quwoquan_app/scripts/runtime/verify_unified_error_semantics_ratchet.py` 继续阻断"页面直接消费 raw 异常字符串 / 失败态裸 `AppToast` 字面量 / 旧式加载失败标题 / 惊叹图标"等回归。

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

| 状态 | 说明 | 展示方式 | `AppPermissionPhase` | L 阶段 |
|------|------|----------|----------------------|--------|
| **未请求** | 首次进入功能，尚未弹出系统对话框 | 功能入口处引导 → 触发 request | `requestable` | L1/L2 |
| **已拒绝（可再请求）** | 用户点了「不允许」，可再次请求（Android 常见） | 轻 Toast 或 inline 说明 | `requestable` | L1 + 轻提示 |
| **永久拒绝** | 用户点了「不允许」且勾选「不再询问」/ iOS 首次拒 | 权限 gate + **去设置** 主操作 | `settingsRequired` | L3 |
| **已授予** | 正常使用 | 无提示 | `granted` | L0 |
| **策略限制** | 家长控制 / 企业策略 | 仅 Toast，无去设置 | `restricted` | — |

统一状态机真相源：`AppPermissionCoordinator`（见 §2.8、§2.9）。

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
4. **去设置** → 经 `AppPermissionCoordinator.openSettings()` 标记 pending，用户主动跳转；**禁止**跳转后立即 `request()` / reload / 再次 `ensure(showUi=true)`
5. **设置返回** → Coordinator 在 `AppLifecycleState.resumed` 静默 recheck，**仅一次** Toast 反馈（见 §2.8）

### 2.8 防死循环与设置返回（强制）

统一入口：`AppPermissionCoordinator`（`quwoquan_app/lib/core/services/app_permission_coordinator.dart`）。
新功能 **禁止** 直接 `Permission.xxx.request()` 或裸 `openAppSettings()`；必须登记 `AppPermissionKind` 并走 Coordinator。

#### 2.8.1 阶段漏斗（L0–L4）

| 阶段 | 行为 | 是否跳转设置 |
|------|------|--------------|
| **L0 已授权** | 直接执行功能 | 否 |
| **L1 系统 request** | 用户主动触发时调用 `request()` / 插件等价 API | 否（系统原生弹窗） |
| **L2 Pre-Permission 说明** | 首次前应用内 1 句说明 +「继续」 | 否 |
| **L3 永久拒绝 / 不可再 request** | 应用内 gateCard/dialog：**一次**说明 + 用户 **主动点击**「去设置」 | 是（唯一入口） |
| **L4 设置返回** | 静默 recheck → **仅一次**反馈 | 否（禁止自动再跳） |

#### 2.8.2 会话状态契约

| 字段 | 含义 |
|------|------|
| `settingsVisitPending` | 仅用户点击「去设置」时置位；resume 时处理 **一次** 后清除 |
| `suppressSettingsPrompt` | 设置返回且仍未授权 → 置 `true`；本会话内后续 `ensure()` **禁止**再弹含「去设置」的 modal |

#### 2.8.3 六条防循环军规

1. **`suppressSettingsPrompt`**：设置返回未授权后，后续 `ensure()` 只展示 `AppToast` 或 inline 轻提示（文案：`permissionStillDeniedMessage`），**不**再弹含「去设置」的 dialog/gateCard。
2. **`settingsVisitPending` + resume**：granted → 成功 Toast（`permissionGrantedMessage`）并清除 suppress；not granted → 失败 Toast **一次** + 置 suppress + 清除 pending。
3. **禁止链式触发**：`openAppSettings()` 后不得立即 `request()` / `_loadNearby()` / 再次 `ensure(showUi=true)`。
4. **禁止 resume 自动跳设置**：生命周期回调只做 recheck + Toast，不得自动 `openAppSettings()`。
5. **显式重试**：页面级 gate 提供「重试授权」→ 清除 `suppressSettingsPrompt`（`forceRetry: true`）；若仍为 `settingsRequired` 才允许再次展示「去设置」。
6. **会话边界**：冷启动或登出后清除 suppress；SharedPreferences 仅存 primer 已展示，**不**持久化 suppress。

#### 2.8.4 UI 载体（与 §1.12 对齐）

| 场景 | 载体 |
|------|------|
| JIT 功能（按住说话、发起通话） | **L1 系统弹窗直出**（默认无 L2）；L3 用 gateCard **至多 1 次/会话** |
| 页面级阻塞（选位置、相册） | L2 preBrief（继续/取消）→ L1；L3 用 `AppInlineGateState` / `AppPageErrorState` |
| suppress 后重复触发 | **仅 `AppToast`** |
| 设置返回未授权 | **一次性 Toast**，无 modal |

#### 2.8.5 验证

- **local_contract**：`test/local_contract/core/services/app_permission_coordinator__local_contract_test.dart`
- **adoption 门禁**：`quwoquan_app/scripts/runtime/verify_permission_coordinator_adoption.py`
- **primer 文案门禁**：`quwoquan_app/scripts/runtime/verify_permission_primer_copy.py`
- **user_acceptance**：`specs/ux/app-permission-coordinator-uat-matrix.md`

### 2.9 权限载体决策矩阵（权威边界）

> 代码真相源：`AppPermissionCoordinator.ensure()` + `AppPermissionSurface`（`jit` / `page`）。
> 与 §1.13 错误矩阵并列；permission 子域冲突时以本节 + §2.8 为准。

**判定优先级（自上而下短路）**：

```
phase == granted → 无 UI
phase == restricted → AppToast（permissionRestrictedMessage）
suppressSettingsPrompt → AppToast（permissionStillDeniedMessage），禁止 L3 modal
phase == settingsRequired → L3 gateCard（去设置 + 取消[/重试授权]），仅一次
surface == page 且 primer 未展示 → L2 preBrief（继续/取消）
否则 requestable → L1 仅系统 request（App 层零 modal；JIT 默认跳过 L2）
```

| 载体 | 组件 | 适用阶段 |
|------|------|----------|
| **preBrief** | `CupertinoAlertDialog`（继续/取消） | L2，仅 `AppPermissionSurface.page` |
| **systemSheet** | OS 系统弹窗 | L1 |
| **permissionGate** | `gateCard` / JIT 下 `AppActionErrorFeedback` | L3 |
| **permissionToast** | `AppToast` | L4 / suppress |

**红线**：

- 同一次用户手势（如「按住说话」）App 层 **最多 1 个 modal**（JIT 默认 0 个 L2）。
- L2 主按钮为「继续」时，正文 **禁止** 仅写「请点允许」而不说明系统弹窗。
- L3 标题使用 `permissionSettingsGateTitle`，与 L2 标题区分。
- **禁止** `permission.request()` 后再链式 `record.hasPermission(request: true)`。

### 2.10 JIT 动作失败（以聊天语音为例）

- **分类**：`UiErrorCategory.backgroundAction`（非 `submit`）
- **载体**：输入区上方 **voiceStatusBar**（持久至重试或 dismiss）
- **文案**：`chatVoicePendingRetry`（「语音没发出去，已保存，点重试」）
- **主操作**：**重试** → `voiceOfflineQueue.drain()`，非再次弹权限
- **禁止**：`actionDialog` 与 status bar **同时**出现

### 2.11 文案 key 注册表（权限 + JIT 语音）

| Key | 用途 |
|-----|------|
| `permissionPrimerContinue` | L2 主按钮「继续」 |
| `permissionSettingsGateTitle(label)` | L3 标题 |
| `permissionStillDeniedMessage(label)` | L4 失败 Toast |
| `permissionGrantedMessage(label)` | L4 成功 Toast |
| `permissionRetryAuthorization` | L3 次操作 / 重试授权 |
| `chatVoicePendingRetry` | 语音发送失败 status bar |
| 各 kind `*PrimerMessage` | 必须含「点继续 → 系统弹窗点允许」语义 |

---

## 3. 实现约束（强制）

- 所有错误/权限文案必须来自 l10n（`context.l10n.*`）或 `UITextConstants`，禁止硬编码中文字符串
- 颜色、字号、间距必须使用 `AppTypography`、`AppSpacing`、`AppColors` / `colorScheme`
- 云端错误码映射：优先解析 `CloudException.code`，映射到 domain 对应 l10n；无 code 时使用通用 `loadFailed` / `submitFailed`
- 权限相关：使用 `geolocator` / `permission_handler` 等统一包，禁止各页面自行实现分散逻辑
- 登录门禁：统一经 `AuthGateReason` + `AuthContinuation` 推导提示语义；禁止页面自行拼 “请先登录” + 登录路由
- 列表页：Provider / Notifier 必须显式区分首屏阻塞错误、缓存回退错误、分页追加错误
- 页面组件不得直接依赖 `RuntimeFailureKind` 决定载体；必须经统一 `UiErrorSemanticResolver`
- 新页面/新交互若需要错误态，优先复用统一组件：`AppPageErrorState` / `AppSectionErrorCard` / `AppTransientErrorNotice` / `AppListAppendErrorFooter` / `AppActionErrorFeedback` / `AppInlineGateState`
- 通用错误态禁止默认使用惊叹图标、红色大标题、强边框和巨大刷新图标；列表刷新/分页失败必须使用低打扰载体

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
| **L1a** | Contract | error code / runtime failure / auth gate → `UiErrorSemantic` 映射 | `test/core/errors/`、`test/cloud/**/contract/` |
| **L1b** | Widget | 权限拒绝、云端错误、列表首屏失败、分页失败、登录门禁 UI 渲染 | `test/ui/**/widgets/` |
| **L1c** | Journey | 创作提交流程、选位置失败、未登录续接评论/关注/发消息 | `test/ui/**/journeys/` |
| **L4** | Patrol | 真机权限弹窗、去设置跳转（advisory） | `test/user_acceptance/patrol/content/` |

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

### 5.6 user_acceptance Patrol（可选）

- 真机/模拟器：进入位置选择 → 拒绝权限 → 断言「去设置」按钮可见
- 点击「去设置」→ 断言能打开系统设置（不断言返回后状态）

路径：`test/user_acceptance/patrol/content/` 或 `test/user_acceptance/patrol/integration/location/`

---

## 6. 与现有规则的关系

| 规则 | 关系 |
|------|------|
| `02-dart-coding` | 本规范在错误/权限场景下细化设计系统使用方式 |
| `06-semantic-consistency-audit` | 本规范定义的 token 与形态纳入语义一致性检查范围 |
| `contracts/metadata/*/errors.yaml` | 云端错误码与 user_message 为端侧文案的权威来源 |
| `03-testing` | 本规范第 4、5 节细化测试目录与验证策略，与 03-testing 一致 |
