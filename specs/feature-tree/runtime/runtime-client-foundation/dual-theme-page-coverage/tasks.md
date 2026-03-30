# dual-theme-page-coverage（S6）任务

| ID | 任务 | 产出 |
|----|------|------|
| M1 | 枚举全页面 + shell，建 `page-dual-theme-matrix.md` | 矩阵 v1 ✅ |
| M2 | 按 **plan.yaml v3：L1→L2→L3** 关闭 **partial**；**优先改 design_system/components，少改 *_page.dart** | W1–W5 `/dev` 矩阵 `partial` 已清零 ✅ |
| M3 | PR 流程：大改页须更新矩阵 | 流程固化 |
| M4 | （可选 P2）Golden / 脚本抽检 | v2 |
| **M-baseline-s6** | CR-012 + 规格冻结；S7/S8 正交 | ✅ |

## Partial 行与 slice 映射（/dev 勾选）

> **v3**：welcome 单独 L3；discovery/chat/create 走 **L2（组件优先）**；RTC/WebView 走 **L3 共享模块**。**先做 `s6-slice-l1-shared-color-api`**。

| 路径 | dual_theme（完成态） | slice（v3） |
|------|---------------------|-------------|
| `welcome_screen.dart` | full ✅ | **s6-slice-l3-welcome-brand** |
| `discovery_page.dart` | full ✅ | **s6-slice-l2-discovery-feed**（子组件为主） |
| `chat_page.dart` | full ✅ | **s6-slice-l2-chat-tab**（子组件为主） |
| `create_page.dart` | full ✅ | **s6-slice-l2-create-flow**（共用 UI 为主） |
| RTC 四页 | full ✅ | **s6-slice-l3-rtc-call-chrome** |
| `assistant_reference_webview_page.dart` | full ✅ | **s6-slice-l3-assistant-webview-chrome** |

**前置**：**s6-slice-l1-shared-color-api**（全 partial 修复前尽量先合，避免 L2 重复 `isDark ? a : b`）。

**双矩阵巡检**：`s6-slice-matrix-sync`。

**豁免行**：`unified_media_viewer_page`、`one_tap_movie_preview`、`circles_hub_page`（T0）— 见矩阵 `exempt`。
