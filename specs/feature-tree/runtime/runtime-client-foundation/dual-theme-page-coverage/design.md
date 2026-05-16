# design：dual-theme-page-coverage（S6）

## 上游规格评审

- 已对齐 `specs/02_IOS_NATIVE_FRONTEND_UX_SPEC.md` §2.5、§3.2；消费 `app-theme-infrastructure`；与 `dart-semantic-gate`、`ios-native-page-enforcement` 无冲突。  
- **本 baseline**：聚焦 **S6 双色**；**S7（P7 断点/版式）**、**S8（P8 语义 token）** 由并行会话主责 —— S6 修复时 **优先改色与表面材质**，避免同 PR 做大范围布局或全文件 token 重构。

## 方案对比与选型结论

| 方案 | 说明 | 结论 |
|------|------|------|
| **A. 全页矩阵 + 分批 PR** | `page-dual-theme-matrix.md` 登记 `full/partial/no/exempt`，按域关闭 partial | **选用** |
| **B. 仅门禁脚本、无矩阵** | 无法枚举漏页 | 不采纳 |
| **C. 一次 PR 改全库** | 风险高、难回滚 | 不采纳 |

## 方案要点（实现）

1. **单一真相**：`AppTheme` / `CupertinoTheme` + `isDarkProvider`（或等价）；页面内多走 `AppColorsFunctional` / `CupertinoDynamicColor.resolveFrom`。  
2. **交付物**：`page-dual-theme-matrix.md`；横向矩阵 **P6** 与 `dual_theme` 对齐。  
3. **与门禁**：v1 = 矩阵 + `flutter analyze` + `verify_dart_semantic.py`；v2 = Golden/脚本（可选）。  
4. **豁免**：`exemption_reason` 必填；禁止无截止永久豁免。

## 减少散弹式修改的整体策略（推荐主路径）

> **问题**：若按「矩阵一行 = 改一个 `*_page.dart`」推进，会在全库产生 **大量浅层 diff**，难 review、易与 **S7（版式）/ S8（token 命名）** 冲突。  
> **原则**：**先收敛「颜色的定义与分发」与高扇出组件，再改页面装配**；页面文件应尽量只保留 **路由/状态/组合**，不成为色值仓库。

### 层级 L1 — 单入口语义色（改动面：极少文件，收益：全库）

| 动作 | 说明 |
|------|------|
| **扩展 `AppColorsFunctional` / `ColorType`** | 把多处重复的「列表行底、会话胶囊、蒙层、次级表面」等，从 `AppColors.white/black` **抬升**为 **具名 ColorType**，一处定义深浅两路。 |
| **（可选）`ThemeExtension`** | 对 **`MaterialApp` 已注入的 `ThemeData`** 增加 `ThemeExtension<QuwoQuanSurfaces>`（或等价），在 **不引 Riverpod** 的 `StatelessWidget` 内用 `Theme.of(context).extension<>` 取色，减少 `ref.watch(isDarkProvider)` 渗透。 |
| **`AppColors.ios*(context)` 优先** | 凡适用 **系统标签/分隔/填充**，优先 `CupertinoDynamicColor.resolve`，避免手写 `isDark ? a : b` 在业务层复制。 |

**禁止**：在 L1 未完成前，对十几个页面各写一套私有 `_bgLight/_bgDark`。

### 层级 L2 — 高扇出组件与子树（改动面：`components/`、`ui/<domain>/widgets/`，收益：多页自动跟）

| 领域 | 优先改的文件类型 | 说明 |
|------|------------------|------|
| **discovery / partial** | `MomentSocialFeed`、帖子卡片、宫格等 **被 `discovery_page` 引用** 的 widget | 色从组件内收口后，**`discovery_page.dart` 可能无需改或仅减行**。 |
| **chat / partial** | 会话列表 cell、顶部胶囊、空态等 **子组件** | **`chat_page.dart` 保持薄**；黑底白字在子组件统一接 L1 token。 |
| **create / partial** | 发布流 **共用 overlay / 步骤条 / 主按钮** 若已抽组件，只改组件 | 避免在 `create_page` 内联 Stack 上堆硬编码色。 |

**识别方法**：对 partial 页执行 **「查找引用」** —— 先改 **被引用次数高的 Build 方法**，再改页面。

### 层级 L3 — 品牌 / 沉浸 / 多页复制粘贴区（改动面：小模块 + 薄页面）

| 场景 | 策略 |
|------|------|
| **Welcome** | 将 `welcome*` 常量收敛为 **`WelcomeAppearance(isDark)` 或 ThemeExtension** 单模块；花瓣/渐变只在此模块分叉；**`welcome_screen.dart` 只组合**。 |
| **RTC 四通道路由** | 提取 **共享** `CallStageDecoration` / `CallChromeColors`（或复用 L1 中 `ColorType.call*`），四页 **共用**，禁止四文件各维护一套渐变常量。 |
| **WebView 参考页** | 抽 **`AssistantReferenceWebChrome`（壳层）** 统一导航栏/背景/进度条色；页面只负责 `WebView` 与路由。 |

### 层级 L4 — 页面文件（最后、尽量少）

仅当某色 **只在该页出现一次** 且无合理组件归属时，才在 `*_page.dart` 内改；否则 **上移到 L2/L3**。

### 与当前 `plan.yaml` 的对应关系

- **L1** → `s6-slice-l1-shared-color-api`  
- **L2** → `s6-slice-l2-discovery-feed`、`s6-slice-l2-chat-tab`、`s6-slice-l2-create-flow`（**实现顺序：先 L1 再 L2**）  
- **L3** → `s6-slice-l3-welcome-brand`、`s6-slice-l3-rtc-call-chrome`、`s6-slice-l3-assistant-webview-chrome`  
- **L4** → 各 slice 末尾「仅当子树改完仍 residual」的补丁，**不单独开「逐页扫街」slice**。

### 验收侧

- PR review：**优先看 `app_colors` / `AppColorsFunctional` / 新增 extension / `components/` diff**；`*_page.dart` 行数应变少或不变。  
- 矩阵仍按 **页面行** 登记 `dual_theme`，但 **证据** 可写「由 `X 组件` + `ColorType.Y` 收敛」。

## metadata / codegen

不适用（客户端视觉治理，无 `contracts/metadata` 变更）。

## 字段演进 / 迁移 / feature flag

不适用；无 DB 迁移；无业务 feature flag。

## 观测与回滚

- **观测**：矩阵中 `partial` 行数递减；PR 是否同步更新双矩阵。  
- **回滚**：revert 对应 PR + 矩阵行回退。

## 风险

- 大文件（`create_page`、RTC）：按 `plan.yaml` **slice** 拆分。  
- WebView：仅壳层双色。  
- **与 S7/S8 并行**：同一文件若必须同时改色与布局/token，**拆 PR** 或先 S6 再 S7/S8，避免单 PR 难以 review。

## 与 app-theme-infrastructure 边界

| 项 | app-theme-infrastructure | dual-theme-page-coverage (S6) |
|----|--------------------------|-------------------------------|
| Theme/CupertinoTheme 接线 | 主责 | 消费 |
| 单页是否双色达标 | 辅责 | **主责** |
| 全页矩阵 | 否 | **是** |

## T1–T4 证据矩阵（本 L3）

| 层 | 证据 |
|----|------|
| **T1** | `spec.md`、`design.md`、`acceptance.yaml`、`page-dual-theme-matrix.md`、`CR-20260330-012-s6-dual-theme-baseline.yaml` |
| **T2** | `flutter analyze quwoquan_app/lib`、`quwoquan_app/scripts/runtime/verify_dart_semantic.py`、涉及页 PR 更新矩阵 |
| **T3** | 各 **slice** 合并前深浅色手动抽检（列表见 `plan.yaml`） |
| **T4** | 预留：Golden / 截图脚本（`plan` P2 阶段） |
