# 页级埋点覆盖面 — 全表面分类与 /dev 核对清单

> **目的**：证明 **方案 A + Observer + Shell** 在 /dev 完成后可 **覆盖所有应计次的页面表面**，并标出 **必须补 `RouteSettings.name` 或改 `context.push`** 的代码点。  
> **更新**：/dev 实施时以 `rg` 结果为准刷新本节「待核对文件」表。

## 1. 覆盖原则

| 原则 | 说明 |
|------|------|
| **一次表面一次 open** | 用户可见的全屏（或等价全屏模态页）进入打 **open**，离开打 **return**。 |
| **根栈统一** | 以 **`GoRouter` 配置的根 `Navigator`** 上的 **`AppPageAccessNavigatorObserver`** 为主；**子 `Navigator`** 若未挂同一 Observer，须在 /dev 中 **挂 Observer 或改为命名 `push`**。 |
| **必须有 name** | 依赖 **`route.settings.name`**；**无 name 则 Observer 跳过** → **P4 缺口**。 |

## 2. 表面类别 → 覆盖机制

| ID | 类别 | 覆盖机制 | 典型路径 / 文件 |
|----|------|-----------|------------------|
| **S0** | 欢迎（无路由 → 改为有路由） | GoRoute `/welcome` + Observer | `welcome_screen.dart`（去手写） |
| **S1** | 主壳 Tab | `MainAppShell` | `/` `/circles` `/chat` `/profile` `/assistant` |
| **S2** | GoRouter 顶层全屏 | Observer | `app_router.dart` 内全部 **顶层** `GoRoute` |
| **S3** | ShellRoute 下占位 + 实际页在 Shell 内 | S1 已计 Tab；子页若再 `push` 则 S4 | `MainAppShell` + `HomePage` 等 |
| **S4** | `Navigator.push` 全屏子路由 | **须** `RouteSettings(name)` 或与 GoRouter `push` 一致 | 见 §3 |
| **S5** | 组件内 `*_page.dart`（picker/editor）被 push | 同 S4；name 建议登记 **内部常量**（若未进 `app_routes` 则单列 **`page_access_internal_routes.dart`**） | `create_media_picker_page.dart` 等 |
| **S6** | 纯 Overlay / BottomSheet / 对话框 | **默认不计** pageAccess open（非独立表面）；产品若要计次 → **engagement** 事件 | — |

## 3. 嵌套 push（/dev 已补 `RouteSettings.name`）

以下文件曾含 **`Navigator.push` + `CupertinoPageRoute` / `MaterialPageRoute`**；均已 **`settings: RouteSettings(name: PageAccessInternalRoutes.*)`**（或与 `page_access_log_util` 登记一致），Observer 可解析 `pageName`。

| 文件 | 备注 |
|------|------|
| `lib/ui/assistant/pages/assistant_conversation_page.dart` | 设置 / 引用 Web / Dev replay |
| `lib/ui/assistant/pages/assistant_chat_settings_page.dart` | 会话记录子栈 |
| `lib/ui/content/entry/pages/create_page.dart` | 创作链多模态路由 |
| `lib/ui/content/entry/pages/publish_location_selector_page.dart` | 选址内嵌搜索子页 |
| `lib/components/media/picker/create_media_picker_page.dart` | 相机 / 一键成片预览 |
| `lib/components/input/customizable_chat_input_bar.dart` | 扩展输入全屏 |
| `lib/ui/circle/widgets/circle_shell.dart` | 圈子编辑设置 |
| `lib/ui/circle/providers/circle_media_picker_provider.dart` | 相机 / 相册 |
| `lib/core/widgets/global_surface_actions.dart` | 全局加号建圈 |

**完整枚举命令（/dev 入口）**：

```bash
rg 'Navigator\.of\(context\)\.push|CupertinoPageRoute|MaterialPageRoute' quwoquan_app/lib --glob '*.dart'
```

## 4. 与 `page-horizontal-quality-matrix.md` 的关系

- 矩阵 **每一行** 对应一个 **业务登记页**；**P4=✓** 依赖：**该页进入路径** 落在 **S0–S5** 之一且 **open 可达**。  
- **挂靠面**（如 `PublishLocationSearchPage`）：与父行 **共用** 一次 visit 或 **独立 name** — 须在 `design.md` 实现中 **二选一并写备注**，避免双计或漏计。

## 5. 验收抽样（手工）

- 冷启动（未完成欢迎）：**仅一条** `open` **`route=/welcome`**，`pageName` **非 `route_unknown`**。  
- 欢迎完成进入首页：**`return` welcome** + **`open` Tab 根**。  
- 任意 **GoRouter 全屏页** 进出：**open/return** 成对，`route` 与 **`AppRoutePaths`** 一致。  
- 从 **会话内嵌 push** 打开子页：日志中 **须有** `name`；**不得**静默无 pageAccess。
