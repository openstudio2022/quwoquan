# S2：元数据驱动契约（P2）— 全页落实检查与基线锁定（2026-03-30）

> **会话代号**：S2（见 [`nine-session-rollout-plan.md`](./nine-session-rollout-plan.md)）  
> **横向维度**：P2 — 定义见 [`page-horizontal-quality-spec.md`](../page-horizontal-quality-spec.md) §「P2」  
> **L1 / L2 / L3（横向登记）**：`runtime` → `runtime-client-foundation` → `page-horizontal-quality`  
> **L3（契约专题）**：同 L2 下 [`metadata-driven-client-data-contract`](../metadata-driven-client-data-contract/spec.md)（与 P2 同向）

---

## 1. 真相源与符号映射（S2 退出口径）

| 清单 `status` | 矩阵 P2 列 | 含义 |
|---------------|------------|------|
| `compliant` | **✓** | 该页在云契约消费面已达登记目标态 |
| `partial` / `legacy_map` | **○** | 仍有 Map/旁路或未收敛 DTO，须随域切片继续改码 |
| `exempt` | **—** | 无产品云行模型或开发者/壳/本地工具等豁免（须与清单 `note` 一致） |

**权威顺序**（与九会话规划一致）：`specs/gates/metadata_driven_ui_gap_inventory.yaml` 的 `status` → 推导矩阵 P2；二者冲突时 **先改清单再改矩阵**。

---

## 2. 自动化核对结论（2026-03-30）

- **矩阵数据行**（`lib/` 路径行）：**64** 行。  
- **清单登记**：上述 64 路径 **均在** `metadata_driven_ui_gap_inventory.yaml` 的 `ui_pages` 中（与 `verify_page_matrix_scan_complete.py` 一致）。  
- **P2 ↔ status 对齐**：对 64 行逐格校验，`compliant`/`partial`/`exempt` 与 **✓**/**○**/**—** **0 处不一致**。  
- **矩阵外清单项（合理）**：`quwoquan_app/lib/components/content/media_post_card.dart` — **partial**，`target_dto: PostBaseDto`；属 Feed 关键组件，**不占矩阵行**，S2 审计须在改 Feed 契约时同步看该条。

---

## 3. 统计摘要（矩阵 64 行）

| 清单 status | 行数 | 矩阵 P2 |
|-------------|------|---------|
| `partial` | 51 | ○ |
| `exempt` | 12 | — |
| `compliant` | 1 | ✓ |
| **合计** | **64** | — |

- **`target_dto: TBD`**（矩阵行内）：**35** 行 — 不阻塞 S2「检查 + 对齐 + 基线锁定」，但须在后续 `/dev` 按域补 metadata/codegen 后回填清单。  
- **唯一 `compliant` 页面**：`lib/ui/settings/pages/settings_page.dart`（矩阵 P2 **✓**）。

---

## 4. S2 基线锁定声明

在 **不修改业务代码** 的前提下，本会话可认定 **S2 规格与登记基线已锁定**：

1. **P2 定义**已写在 `page-horizontal-quality-spec.md`，且与 `metadata-driven-client-data-contract/spec.md` 交叉引用一致。  
2. **全页路径**无漏登记；**矩阵 P2** 与 **清单 status** 已对齐。  
3. **待办不属于 S2 关门条件**：将 `partial` 提升为 `compliant`、`TBD` 填实、以及 `media_post_card` 收敛 — 归入后续域级 `/dev` 与 S9 收口。

下一步若要 **自动化防漂移**，可实现 `explore-baseline-readiness-20260329.md` §4-G3 所述「矩阵↔清单 P2 对齐」脚本（默认 warn，STRICT 失败）。

---

## 5. 全页逐行对照表（矩阵章节顺序）

以下表格由 `page-horizontal-quality-matrix.md` 与 `metadata_driven_ui_gap_inventory.yaml` 在 **2026-03-30** 合并生成；**挂靠子面**（如 `PublishLocationSearchPage`、`_AssistantConversationHistoryPage`）结论仍记在父行备注，与矩阵正文一致。

### app / shell

| 路径 | 类型 | 矩阵 P2 | 清单 status | 域 | target_dto | 备注（清单） |
|------|------|---------|-------------|-----|------------|----------------|
| `lib/app/shell/main_app_shell.dart` | T1 | — | exempt | app_shell |  | 壳层导航；无云行模型 |
| `lib/app/shell/bottom_navigation.dart` | T1 | — | exempt | app_shell |  | 底栏；无云行模型 |

### welcome

| 路径 | 类型 | 矩阵 P2 | 清单 status | 域 | target_dto | 备注（清单） |
|------|------|---------|-------------|-----|------------|----------------|
| `lib/ui/welcome/pages/welcome_screen.dart` | T2 | — | exempt | welcome |  | 欢迎流以本地为主；无业务云 DTO 行模型 |

### discovery

| 路径 | 类型 | 矩阵 P2 | 清单 status | 域 | target_dto | 备注（清单） |
|------|------|---------|-------------|-----|------------|----------------|
| `lib/ui/discovery/pages/home_page.dart` | T1 | ○ | partial | content | PostBaseDto | Tab 根；沉浸/作品流消费 PostBaseDto |
| `lib/ui/discovery/pages/discovery_page.dart` | T7 | ○ | partial | content | PostBaseDto | Feed 行以 PostBaseDto 为主；少量 raw 映射用于分享/埋点兼容 |

### assistant

| 路径 | 类型 | 矩阵 P2 | 清单 status | 域 | target_dto | 备注（清单） |
|------|------|---------|-------------|-----|------------|----------------|
| `lib/ui/assistant/pages/assistant_tab_page.dart` | T1 | ○ | partial | assistant | TBD |  |
| `lib/ui/assistant/pages/assistant_management_page.dart` | T2 | ○ | partial | assistant | TBD |  |
| `lib/ui/assistant/pages/assistant_reference_webview_page.dart` | T2 | — | exempt | assistant |  | WebView；云契约 — |
| `lib/ui/assistant/pages/assistant_conversation_page.dart` | T2 | ○ | partial | assistant | TBD | 引擎契约与云 API 分层；云调用须 codegen |
| `lib/ui/assistant/pages/assistant_dev_replay_page.dart` | T2 | — | exempt | assistant |  | 开发工具 |
| `lib/ui/assistant/pages/assistant_skill_center_page.dart` | T2 | ○ | partial | assistant | TBD |  |
| `lib/ui/assistant/pages/assistant_chat_settings_page.dart` | T2 | ○ | partial | assistant | TBD |  |

### chat

| 路径 | 类型 | 矩阵 P2 | 清单 status | 域 | target_dto | 备注（清单） |
|------|------|---------|-------------|-----|------------|----------------|
| `lib/ui/chat/pages/chat_page.dart` | T1 | ○ | partial | chat | ChatInboxDto | 主列表 ChatInboxDto；密信/联系人 Tab 等仍有 Map 或旁路 |
| `lib/ui/chat/pages/chat_detail_page.dart` | T2 | ○ | partial | chat | TBD | 委托 ChatConversationPage；契约随子页 |
| `lib/ui/chat/pages/chat_conversation_page.dart` | T7 | ○ | partial | chat | TBD | 消息气泡动态结构；长期与 conversation metadata 对齐 |
| `lib/ui/chat/pages/chat_settings_page.dart` | T2 | ○ | partial | chat | ChatConversationMemberDto | 成员列表 ChatConversationMemberDto；会话元数据等可继续收口 |
| `lib/ui/chat/pages/start_group_chat_page.dart` | T4 | ○ | partial | chat | ChatInboxDto | listInbox/Contacts/Members/Circle 已 DTO；消息等仍 Map |
| `lib/ui/chat/pages/transfer_ownership_page.dart` | T3 | ○ | partial | chat | ChatConversationMemberDto |  |
| `lib/ui/chat/pages/group_member_search_page.dart` | T3 | ○ | partial | chat | ChatConversationMemberDto |  |
| `lib/ui/chat/pages/group_manage_page.dart` | T3 | ○ | partial | chat | TBD |  |
| `lib/ui/chat/pages/group_admins_page.dart` | T3 | ○ | partial | chat | ChatConversationMemberDto |  |

### circle

| 路径 | 类型 | 矩阵 P2 | 清单 status | 域 | target_dto | 备注（清单） |
|------|------|---------|-------------|-----|------------|----------------|
| `lib/ui/circle/pages/home_circles_hub_page.dart` | T1 | ○ | partial | circle | TBD |  |
| `lib/ui/circle/pages/circles_page.dart` | T1 | ○ | partial | circle | TBD |  |
| `lib/ui/circle/pages/circle_detail_page.dart` | T2 | ○ | partial | circle | TBD |  |
| `lib/ui/circle/pages/circle_edit_settings_page.dart` | T5 | ○ | partial | circle | TBD |  |
| `lib/ui/circle/pages/circle_stats_page.dart` | T3 | ○ | partial | circle | TBD |  |
| `lib/ui/circle/pages/circles_hub_page.dart` | T0 | — | exempt | circle |  | 仅 export，无独立云契约 |

### content

| 路径 | 类型 | 矩阵 P2 | 清单 status | 域 | target_dto | 备注（清单） |
|------|------|---------|-------------|-----|------------|----------------|
| `lib/ui/content/pages/article_detail_page.dart` | T2 | ○ | partial | content | PostBaseDto |  |
| `lib/ui/content/pages/photo_detail_page.dart` | T2 | ○ | partial | content | PostBaseDto |  |
| `lib/ui/content/pages/video_detail_page.dart` | T2 | ○ | partial | content | PostBaseDto |  |
| `lib/ui/content/pages/unified_media_viewer_page.dart` | T2 | ○ | partial | content | PostBaseDto |  |

### content / entry（创作与发布子域）

| 路径 | 类型 | 矩阵 P2 | 清单 status | 域 | target_dto | 备注（清单） |
|------|------|---------|-------------|-----|------------|----------------|
| `lib/ui/content/entry/pages/create_page.dart` | T4 | ○ | partial | content | TBD |  |
| `lib/ui/content/entry/pages/article_preview_page.dart` | T5 | ○ | partial | content | TBD |  |
| `lib/ui/content/entry/pages/publish_location_selector_page.dart` | T5 | ○ | partial | content | TBD |  |
| `lib/ui/content/entry/pages/video_editor_page.dart` | T5 | ○ | partial | content | TBD |  |
| `lib/ui/content/entry/pages/publish_circle_select_page.dart` | T5 | ○ | partial | content | TBD |  |

### entity（主页实体）

| 路径 | 类型 | 矩阵 P2 | 清单 status | 域 | target_dto | 备注（清单） |
|------|------|---------|-------------|-----|------------|----------------|
| `lib/ui/entity/pages/suggest_homepage_page.dart` | T4 | ○ | partial | entity | TBD |  |
| `lib/ui/entity/pages/homepage_picker_page.dart` | T4 | ○ | partial | entity | TBD |  |
| `lib/ui/entity/pages/homepage_claim_page.dart` | T2 | ○ | partial | entity | TBD |  |
| `lib/ui/entity/pages/homepage_maintenance_page.dart` | T2 | ○ | partial | entity | TBD |  |
| `lib/ui/entity/pages/homepage_status_report_page.dart` | T2 | ○ | partial | entity | TBD |  |
| `lib/ui/entity/pages/homepage_detail_page.dart` | T2 | ○ | partial | entity | TBD |  |

### rtc

| 路径 | 类型 | 矩阵 P2 | 清单 status | 域 | target_dto | 备注（清单） |
|------|------|---------|-------------|-----|------------|----------------|
| `lib/ui/rtc/pages/incoming_call_page.dart` | T2 | ○ | partial | rtc | TBD |  |
| `lib/ui/rtc/pages/outgoing_call_page.dart` | T2 | ○ | partial | rtc | TBD |  |
| `lib/ui/rtc/pages/voice_call_page.dart` | T2 | ○ | partial | rtc | TBD |  |
| `lib/ui/rtc/pages/video_call_page.dart` | T2 | ○ | partial | rtc | TBD |  |
| `lib/ui/rtc/pages/call_participant_picker_page.dart` | T2 | ○ | partial | rtc | ChatInboxDto | ChatInboxDto / ChatConversationMemberDto / ChatContactRowDto |

### search

| 路径 | 类型 | 矩阵 P2 | 清单 status | 域 | target_dto | 备注（清单） |
|------|------|---------|-------------|-----|------------|----------------|
| `lib/ui/search/pages/global_search_page.dart` | T2 | ○ | partial | search | TBD |  |
| `lib/ui/search/pages/search_network_results_page.dart` | T3 | ○ | partial | search | TBD |  |

### settings

| 路径 | 类型 | 矩阵 P2 | 清单 status | 域 | target_dto | 备注（清单） |
|------|------|---------|-------------|-----|------------|----------------|
| `lib/ui/settings/pages/settings_page.dart` | T2 | ✓ | compliant | settings | N/A | 以本地/Cupertino 为主；云上外观设置走 codegen 错误码路径 |
| `lib/ui/settings/pages/developer_settings_page.dart` | T2 | — | exempt | settings |  | 开发者工具；无产品云契约 |

### user

| 路径 | 类型 | 矩阵 P2 | 清单 status | 域 | target_dto | 备注（清单） |
|------|------|---------|-------------|-----|------------|----------------|
| `lib/ui/user/pages/my_profile_page.dart` | T2 | ○ | partial | user | UserProfileDto |  |
| `lib/ui/user/pages/other_profile_page.dart` | T2 | ○ | partial | user | UserProfileDto |  |
| `lib/ui/user/pages/edit_profile_page.dart` | T2 | ○ | partial | user | UserProfileDto |  |
| `lib/ui/user/pages/persona_management_page.dart` | T7 | ○ | partial | user | TBD |  |
| `lib/ui/user/pages/sub_account_management_page.dart` | T2 | ○ | partial | user | TBD |  |
| `lib/ui/user/pages/resonance_page.dart` | T2 | ○ | partial | user | TBD |  |
| `lib/ui/user/pages/profile_stats_page.dart` | T2 | ○ | partial | user | TBD |  |
| `lib/ui/user/pages/profile_comments_page.dart` | T2 | ○ | partial | user | TBD |  |

### components（跨域复用全屏 / 骨架）

| 路径 | 类型 | 矩阵 P2 | 清单 status | 域 | target_dto | 备注（清单） |
|------|------|---------|-------------|-----|------------|----------------|
| `lib/components/settings_form/settings_inset_form_page.dart` | T6 | — | exempt | components_shell |  | 复用壳；无云契约 |
| `lib/components/media/image/editor/image_editor_page.dart` | T5 | — | exempt | components_shell |  | 本地编辑为主 |
| `lib/components/media/camera/camera_capture_page.dart` | T5 | — | exempt | components_shell |  | 本地相机；无云行模型 |
| `lib/components/media/picker/create_media_picker_page.dart` | T5 | — | exempt | components_shell |  | 本地选择器 |
| `lib/components/media/picker/one_tap_movie_preview_page.dart` | T5 | — | exempt | components_shell |  | 本地预览 |

### 矩阵外（清单登记）

| 路径 | 矩阵 | 清单 status | 域 | target_dto | 备注（清单） |
|------|------|-------------|-----|------------|----------------|
| `lib/components/content/media_post_card.dart` | 不占行 | partial | content | PostBaseDto | 卡片基类已 PostBaseDto；更多操作配置仍为 dynamic |

---

## 6. 变更记录

| 日期 | 说明 |
|------|------|
| 2026-03-30 | S2 全页核对：64 行矩阵 ↔ 清单 P2 对齐；统计与基线锁定声明；附全表 |
