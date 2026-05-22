# 工具栏 Chrome 全量清单

> 目标：所有页面的顶部工具栏、底部工具栏、返回/更多/设置按钮、输入栏都必须归属到一个明确的 chrome 语义族。没有明确豁免的页面必须消费 `AppSpacing.appChrome*` 与 `AppNavigationSemanticConstants`。

## Chrome 语义族

| 语义族 | 适用页面 | 统一入口 |
|---|---|---|
| 一级 Tab chrome | 首页、趣信、圈子 Hub、发现主导航 | `appChromeTopSafeInset`、`appChromeTopBarHeight`、`GlobalTopBarIconButton` |
| 普通导航 chrome | 标准内页、WebView、统计页、资料编辑页 | `AppNavigationBar`、`AppNavigationBarIconButton`、`AppNavigationBarTextAction` |
| 设置 Inset chrome | 聊天信息、群管理、圈子设置、助手管理、设置页 | `SettingsInsetFormPageScaffold` / `SettingsInsetMemberPickerPageScaffold` |
| 选择器 chrome | 发布圈子、主页选择、媒体选择器 | `IosSelectionPageScaffold` 或选择器专用 bottom action token |
| Overlay 资料 chrome | 用户主页、圈子主页、实体主页详情 | `ProfileIosIconButton` + overlay surface token |
| 沉浸媒体 chrome | 精品/媒体浏览器、图片/视频 viewer | `ImmersiveToolbarIconButton`、`ImmersiveEngagementBar`、`MediaViewerBottomBar` |
| 对话输入 chrome | 聊天、找私助、评论输入 | `CustomizableChatInputBar`、`CommentInput`、对应 bottom safe token |
| 通话舞台 chrome | RTC 来电/去电/语音/视频页 | RTC 专用控件 token，登记豁免 |

## 必须整改清单

- 聊天链路：`chat_page.dart`、`chat_conversation_page.dart`、`chat_settings_page.dart`、`group_manage_page.dart`、`group_admins_page.dart`、`group_member_search_page.dart`、`transfer_ownership_page.dart`、`start_group_chat_page.dart`。
- 助手链路：`personal_assistant_conversation_page.dart`、`assistant_management_page.dart`、`assistant_skill_center_page.dart`、`assistant_reference_webview_page.dart`、`assistant_dev_replay_panel.dart`、`assistant_half_sheet.dart`。
- 搜索/评论/内容：`discovery_page.dart`、`global_search_page.dart`、`search_network_results_page.dart`、`comment_viewer_modal.dart`、`comment_viewer.dart`、`article_detail_page.dart`、`media_viewer_toolbar.dart`、`media_assistant_panel.dart`。
- 编辑器/实体：`article_typography_page.dart`、`image_editor_top_bar.dart`、`create_media_picker_page.dart`、`camera_capture_page.dart`、`homepage_detail_shell.dart`。

## 显式豁免清单

- `welcome_screen.dart`：品牌欢迎屏，无传统 toolbar。
- RTC 通话页：`incoming_call_page.dart`、`outgoing_call_page.dart`、`voice_call_page.dart`、`video_call_page.dart` 使用通话舞台 chrome。
- 设置 Inset 与选择器页并非未统一，而是归属专用 chrome 语义族；二级页面必须登记在本清单，不能遗漏。
