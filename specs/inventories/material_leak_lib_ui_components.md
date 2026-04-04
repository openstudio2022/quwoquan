# lib/ui + lib/components Material 泄露清单

- **生成时间（UTC）**：2026-03-29T17:20:01Z
- **范围**：`quwoquan_app/lib/ui`、`quwoquan_app/lib/components` 下全部 `.dart`
- **复跑**：`python3 scripts/scan_material_leaks.py`
- **说明**：`material_import` 表示是否 `import 'package:flutter/material.dart'`；`signals` 为启发式正则命中次数（注释/字符串可能误报），用于排期与分桶，不作严格证明。

## 摘要

| 指标 | 数量 |
| --- | ---: |
| Dart 文件总数 | 248 |
| 任意形式依赖 material.dart（含 `show`） | 136 |
| 整库 import material（非 show） | 134 |
| 仅 `show …` 从 material 引用符号 | 2 |
| 未 import material.dart | 112 |

## 全局 signal 命中（跨文件合计）

| signal | hits |
| --- | ---: |
| `card` | 1 |
| `chip` | 2 |
| `divider` | 6 |
| `list_tile` | 1 |
| `material_page_route` | 6 |
| `range_slider` | 1 |
| `slider` | 6 |
| `tab_controller` | 2 |
| `tooltip` | 1 |
| `vertical_divider` | 1 |

## 按文件（有 material import 或存在 signal 命中）

| path | zone | material | cupertino | signals（摘要） |
| --- | --- | --- | --- | --- |
| `quwoquan_app/lib/components/assistant/assistant_avatar.dart` | components | full | no | — |
| `quwoquan_app/lib/components/assistant/assistant_floating_ball.dart` | components | full | yes | — |
| `quwoquan_app/lib/components/assistant/petal_mark.dart` | components | full | no | — |
| `quwoquan_app/lib/components/avatar/group_avatar_grid.dart` | components | full | yes | — |
| `quwoquan_app/lib/components/avatar/rounded_square_avatar.dart` | components | full | yes | — |
| `quwoquan_app/lib/components/comment_system/comment_models.dart` | components | full | no | — |
| `quwoquan_app/lib/components/comment_system/comment_viewer.dart` | components | full | yes | — |
| `quwoquan_app/lib/components/comment_system/comment_viewer_modal.dart` | components | full | yes | — |
| `quwoquan_app/lib/components/content/image_post_card.dart` | components | full | yes | — |
| `quwoquan_app/lib/components/content/media_post_card.dart` | components | full | yes | — |
| `quwoquan_app/lib/components/content/video_post_card.dart` | components | full | yes | — |
| `quwoquan_app/lib/components/conversation/conversation_timeline.dart` | components | full | no | — |
| `quwoquan_app/lib/components/conversation/message_action_menu_overlay.dart` | components | full | yes | — |
| `quwoquan_app/lib/components/conversation/message_bubble_frame.dart` | components | full | no | — |
| `quwoquan_app/lib/components/input/customizable_chat_input_bar.dart` | components | full | yes | — |
| `quwoquan_app/lib/components/input/unified_emoji_picker.dart` | components | full | yes | — |
| `quwoquan_app/lib/components/media/camera/camera_capture_page.dart` | components | full | yes | — |
| `quwoquan_app/lib/components/media/image/editor/bottom_bar/image_editor_bottom_bar.dart` | components | full | no | — |
| `quwoquan_app/lib/components/media/image/editor/icons/image_editor_semantic_icon.dart` | components | full | no | — |
| `quwoquan_app/lib/components/media/image/editor/image_editor_page.dart` | components | full | yes | `list_tile`×1 |
| `quwoquan_app/lib/components/media/image/editor/panels/hsl/image_editor_hsl_models.dart` | components | full | no | — |
| `quwoquan_app/lib/components/media/image/editor/panels/image_editor_curve_overlay_bar.dart` | components | full | yes | `slider`×2 |
| `quwoquan_app/lib/components/media/image/editor/panels/image_editor_operation_panel.dart` | components | full | yes | `slider`×2 |
| `quwoquan_app/lib/components/media/image/editor/panels/image_editor_rotate_overlay.dart` | components | full | no | — |
| `quwoquan_app/lib/components/media/image/editor/panels/local/image_editor_local_models.dart` | components | full | no | — |
| `quwoquan_app/lib/components/media/image/editor/shared/editor_session_ops_strip.dart` | components | full | no | — |
| `quwoquan_app/lib/components/media/image/editor/tool_list/image_editor_pro_tool_entries.dart` | components | full | no | — |
| `quwoquan_app/lib/components/media/image/editor/tool_list/image_editor_pro_tool_list.dart` | components | full | yes | — |
| `quwoquan_app/lib/components/media/image/editor/tool_list/image_editor_tool_entry_chip.dart` | components | full | no | — |
| `quwoquan_app/lib/components/media/image/editor/top_bar/image_editor_top_bar.dart` | components | full | yes | — |
| `quwoquan_app/lib/components/media/image/navigation/image_sub_tab_navigation.dart` | components | full | no | — |
| `quwoquan_app/lib/components/media/image/viewer/image_viewer.dart` | components | full | yes | — |
| `quwoquan_app/lib/components/media/image/viewer/immersive_image_viewer.dart` | components | full | yes | — |
| `quwoquan_app/lib/components/media/picker/create_media_picker_page.dart` | components | full | yes | `material_page_route`×2 |
| `quwoquan_app/lib/components/media/picker/one_tap_movie_preview_page.dart` | components | full | yes | — |
| `quwoquan_app/lib/components/media/shared/toolbar/immersive_engagement_bar.dart` | components | full | yes | — |
| `quwoquan_app/lib/components/media/shared/toolbar/media_viewer_toolbar.dart` | components | full | yes | — |
| `quwoquan_app/lib/components/media/shared/viewer/media_assistant_panel.dart` | components | full | yes | — |
| `quwoquan_app/lib/components/media/shared/viewer/media_caption_widgets.dart` | components | full | no | — |
| `quwoquan_app/lib/components/media/video/player/video_player_widget.dart` | components | full | no | — |
| `quwoquan_app/lib/components/media/video/viewer/immersive_video_viewer.dart` | components | full | yes | — |
| `quwoquan_app/lib/components/media/video/viewer/video_media_viewer.dart` | components | full | yes | — |
| `quwoquan_app/lib/components/navigation/centered_scrollable_tab_bar.dart` | components | full | yes | — |
| `quwoquan_app/lib/components/navigation/home_primary_tab_strip.dart` | components | full | yes | — |
| `quwoquan_app/lib/components/navigation/secondary_capsule_tab_bar.dart` | components | full | yes | — |
| `quwoquan_app/lib/components/navigation/tab_navigation.dart` | components | full | yes | — |
| `quwoquan_app/lib/components/post/post_preview_card.dart` | components | full | yes | — |
| `quwoquan_app/lib/components/post/post_preview_list_tile.dart` | components | full | yes | — |
| `quwoquan_app/lib/components/search/embedded/embedded_member_search_bar_with_chips.dart` | components | show (show Colors) | yes | — |
| `quwoquan_app/lib/components/search/embedded/member_list_tiles.dart` | components | full | yes | — |
| `quwoquan_app/lib/components/settings_conversation/more_actions_popup/configs/image_viewer_config.dart` | components | full | no | — |
| `quwoquan_app/lib/components/settings_conversation/more_actions_popup/configs/media_post_config.dart` | components | full | no | — |
| `quwoquan_app/lib/components/settings_conversation/more_actions_popup/more_action_popup.dart` | components | full | yes | — |
| `quwoquan_app/lib/components/settings_conversation/more_actions_popup/more_action_types.dart` | components | full | no | — |
| `quwoquan_app/lib/ui/assistant/pages/assistant_conversation_page.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/assistant/pages/assistant_dev_replay_page.dart` | ui | full | yes | `card`×1 |
| `quwoquan_app/lib/ui/assistant/pages/assistant_management_page.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/assistant/pages/assistant_reference_webview_page.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/assistant/pages/assistant_tab_page.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/assistant/widgets/assistant_half_sheet.dart` | ui | full | yes | `chip`×2 |
| `quwoquan_app/lib/ui/assistant/widgets/message/assistant_answer_content.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/assistant/widgets/message/assistant_answer_toolbar.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/assistant/widgets/message/assistant_message_bubble.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/assistant/widgets/message/assistant_process_drawer.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/assistant/widgets/message/regenerate_options_popup.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/chat/pages/chat_conversation_page.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/chat/pages/chat_page.dart` | ui | full | yes | `divider`×1 |
| `quwoquan_app/lib/ui/chat/pages/chat_settings_page.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/chat/pages/start_group_chat_page.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/chat/widgets/message/chat_message_bubble.dart` | ui | full | no | — |
| `quwoquan_app/lib/ui/chat/widgets/message/streaming_scroll_fab.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/chat/widgets/session/assistant_session_header.dart` | ui | full | no | — |
| `quwoquan_app/lib/ui/circle/pages/circle_detail_page.dart` | ui | full | no | — |
| `quwoquan_app/lib/ui/circle/pages/circle_edit_settings_page.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/circle/pages/circle_stats_page.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/circle/pages/circles_page.dart` | ui | full | yes | `divider`×1, `vertical_divider`×1 |
| `quwoquan_app/lib/ui/circle/pages/home_circles_hub_page.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/circle/widgets/circle_action_bar.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/circle/widgets/circle_header.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/circle/widgets/circle_shell.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/circle/widgets/circle_stats_row.dart` | ui | full | no | — |
| `quwoquan_app/lib/ui/circle/widgets/my_circles_rail.dart` | ui | full | no | — |
| `quwoquan_app/lib/ui/circle/widgets/rectangular_circle_card.dart` | ui | full | no | — |
| `quwoquan_app/lib/ui/circle/widgets/section_chat.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/circle/widgets/section_creations.dart` | ui | full | yes | `tooltip`×1 |
| `quwoquan_app/lib/ui/circle/widgets/section_interaction.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/circle/widgets/section_storage.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/content/entry/pages/article_preview_page.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/content/entry/pages/create_page.dart` | ui | full | yes | `material_page_route`×4 |
| `quwoquan_app/lib/ui/content/entry/pages/publish_location_selector_page.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/content/entry/pages/video_editor_page.dart` | ui | full | yes | `range_slider`×1, `slider`×2 |
| `quwoquan_app/lib/ui/content/entry/widgets/create_entry_sheet.dart` | ui | full | no | — |
| `quwoquan_app/lib/ui/content/entry/widgets/article_editor.dart` | ui | show (show Colors) | yes | — |
| `quwoquan_app/lib/ui/content/pages/article_detail_page.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/content/share/content_share_actions.dart` | ui | full | no | — |
| `quwoquan_app/lib/ui/content/share/content_share_sheet.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/content/widgets/article_paged_canvas.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/discovery/pages/discovery_page.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/discovery/pages/home_page.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/discovery/providers/discovery_state.dart` | ui | full | no | — |
| `quwoquan_app/lib/ui/discovery/widgets/moment_social_feed.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/discovery/widgets/works_immersive_viewer.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/entity/pages/homepage_status_report_page.dart` | ui | full | yes | `divider`×1 |
| `quwoquan_app/lib/ui/entity/widgets/homepage_detail_shell.dart` | ui | full | yes | `divider`×1 |
| `quwoquan_app/lib/ui/rtc/pages/call_participant_picker_page.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/rtc/pages/incoming_call_page.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/rtc/pages/outgoing_call_page.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/rtc/pages/video_call_page.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/rtc/pages/voice_call_page.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/rtc/widgets/active_call_bar.dart` | ui | full | no | — |
| `quwoquan_app/lib/ui/rtc/widgets/call_duration_badge.dart` | ui | full | no | — |
| `quwoquan_app/lib/ui/rtc/widgets/call_quality_indicator.dart` | ui | full | no | — |
| `quwoquan_app/lib/ui/rtc/widgets/caller_avatar_pulse.dart` | ui | full | no | — |
| `quwoquan_app/lib/ui/rtc/widgets/participant_list_sheet.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/rtc/widgets/participant_tile.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/rtc/widgets/pip_call_overlay.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/rtc/widgets/speaker_highlight_layout.dart` | ui | full | no | — |
| `quwoquan_app/lib/ui/rtc/widgets/video_grid_layout.dart` | ui | full | no | — |
| `quwoquan_app/lib/ui/settings/pages/settings_page.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/user/pages/edit_profile_page.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/user/pages/my_profile_page.dart` | ui | full | no | — |
| `quwoquan_app/lib/ui/user/pages/other_profile_page.dart` | ui | full | no | — |
| `quwoquan_app/lib/ui/user/pages/persona_management_page.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/user/pages/profile_comments_page.dart` | ui | full | yes | `tab_controller`×2 |
| `quwoquan_app/lib/ui/user/pages/profile_stats_page.dart` | ui | full | yes | `divider`×2 |
| `quwoquan_app/lib/ui/user/pages/resonance_page.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/user/widgets/circle_card.dart` | ui | full | no | — |
| `quwoquan_app/lib/ui/user/widgets/circle_compact_card.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/user/widgets/creation_visibility_popup.dart` | ui | full | no | — |
| `quwoquan_app/lib/ui/user/widgets/profile_header.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/user/widgets/profile_interaction_tab.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/user/widgets/profile_ios_components.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/user/widgets/profile_lifestyle_tab.dart` | ui | full | no | — |
| `quwoquan_app/lib/ui/user/widgets/profile_moments_tab.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/user/widgets/profile_shell.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/welcome/pages/welcome_screen.dart` | ui | full | no | — |

## 未 import material 且无表中 signal 命中的文件

以下文件在本脚本的 signal 规则下未记到典型 Material 控件模式；仍可能通过其他库间接依赖 Material（例如 `flutter/widgets.dart` 不包含 Material 组件，但父级 `Material` 祖先由路由/壳注入）。

- `quwoquan_app/lib/components/components.dart`
- `quwoquan_app/lib/components/conversation/conversation_link_action_sheet.dart`
- `quwoquan_app/lib/components/conversation/conversation_page_scaffold.dart`
- `quwoquan_app/lib/components/conversation/cupertino_conversation_sheet.dart`
- `quwoquan_app/lib/components/media/image/editor/filter/image_editor_filter_feature_extractor.dart`
- `quwoquan_app/lib/components/media/image/editor/filter/image_editor_filter_models.dart`
- `quwoquan_app/lib/components/media/image/editor/filter/image_editor_filter_recommendation_models.dart`
- `quwoquan_app/lib/components/media/image/editor/filter/image_editor_filter_recommender.dart`
- `quwoquan_app/lib/components/media/image/editor/filter/image_editor_filter_repository.dart`
- `quwoquan_app/lib/components/media/image/editor/filter/image_editor_filter_scene_classifier.dart`
- `quwoquan_app/lib/components/media/image/editor/models/image_editor_step.dart`
- `quwoquan_app/lib/components/media/image/editor/tool_list/image_editor_tool_constants.dart`
- `quwoquan_app/lib/components/navigation/tab_swipe_switch_region.dart`
- `quwoquan_app/lib/components/search/embedded/embedded_member_search_bar_plain.dart`
- `quwoquan_app/lib/components/search/embedded/embedded_member_search_page_shell.dart`
- `quwoquan_app/lib/components/search/embedded/grouped_member_list_sections.dart`
- `quwoquan_app/lib/components/search/embedded/inset_grouped_member_list_card.dart`
- `quwoquan_app/lib/components/search/embedded/member_query_filter.dart`
- `quwoquan_app/lib/components/search/search_embedded.dart`
- `quwoquan_app/lib/components/settings_conversation/settings_conversation.dart`
- `quwoquan_app/lib/components/settings_conversation/sheet/conversation_sheet.dart`
- `quwoquan_app/lib/components/settings_form/settings_form.dart`
- `quwoquan_app/lib/components/settings_form/settings_inset_form_page.dart`
- `quwoquan_app/lib/ui/assistant/config/assistant_prompt_config.dart`
- `quwoquan_app/lib/ui/assistant/models/assistant_display_fallbacks.dart`
- `quwoquan_app/lib/ui/assistant/pages/assistant_chat_settings_page.dart`
- `quwoquan_app/lib/ui/assistant/pages/assistant_skill_center_page.dart`
- `quwoquan_app/lib/ui/assistant/providers/assistant_conversation_controller.dart`
- `quwoquan_app/lib/ui/assistant/widgets/message/assistant_journey_view_model.dart`
- `quwoquan_app/lib/ui/assistant/widgets/message/assistant_turn_message_resolver.dart`
- `quwoquan_app/lib/ui/chat/models/chat_list_item_view_model.dart`
- `quwoquan_app/lib/ui/chat/pages/chat_detail_page.dart`
- `quwoquan_app/lib/ui/chat/pages/chat_display_fallbacks.dart`
- `quwoquan_app/lib/ui/chat/pages/group_admins_page.dart`
- `quwoquan_app/lib/ui/chat/pages/group_manage_page.dart`
- `quwoquan_app/lib/ui/chat/pages/group_member_search_page.dart`
- `quwoquan_app/lib/ui/chat/pages/transfer_ownership_page.dart`
- `quwoquan_app/lib/ui/chat/providers/chat_inbox_provider.dart`
- `quwoquan_app/lib/ui/chat/providers/chat_message_provider.dart`
- `quwoquan_app/lib/ui/chat/providers/chat_settings_provider.dart`
- `quwoquan_app/lib/ui/chat/providers/conversation_members_provider.dart`
- `quwoquan_app/lib/ui/chat/providers/voice_offline_queue.dart`
- `quwoquan_app/lib/ui/chat/providers/voice_player_manager.dart`
- `quwoquan_app/lib/ui/chat/providers/voice_send_provider.dart`
- `quwoquan_app/lib/ui/chat/widgets/message/assistant_answer_toolbar.dart`
- `quwoquan_app/lib/ui/chat/widgets/message/assistant_journey_view_model.dart`
- `quwoquan_app/lib/ui/chat/widgets/message/assistant_process_drawer.dart`
- `quwoquan_app/lib/ui/chat/widgets/message/assistant_turn_message_resolver.dart`
- `quwoquan_app/lib/ui/chat/widgets/message/regenerate_options_popup.dart`
- `quwoquan_app/lib/ui/chat/widgets/message/voice_message_bubble.dart`
- `quwoquan_app/lib/ui/chat/widgets/message/voice_waveform_painter.dart`
- `quwoquan_app/lib/ui/chat/widgets/voice/voice_record_overlay.dart`
- `quwoquan_app/lib/ui/chat/widgets/voice/voice_recorder.dart`
- `quwoquan_app/lib/ui/circle/models/circle_tab.dart`
- `quwoquan_app/lib/ui/circle/pages/circles_hub_page.dart`
- `quwoquan_app/lib/ui/circle/providers/circle_media_picker_provider.dart`
- `quwoquan_app/lib/ui/circle/providers/circle_state_provider.dart`
- `quwoquan_app/lib/ui/circle/widgets/circle_media_image.dart`
- `quwoquan_app/lib/ui/circle/widgets/home_circles_category_tab.dart`
- `quwoquan_app/lib/ui/circle/widgets/media_viewer_result_absorber.dart`
- `quwoquan_app/lib/ui/content/article_detail_view.dart`
- `quwoquan_app/lib/ui/content/article_document_models.dart`
- `quwoquan_app/lib/ui/content/article_pagination_engine.dart`
- `quwoquan_app/lib/ui/content/article_presentation_models.dart`
- `quwoquan_app/lib/ui/content/entry/models/create_editor_models.dart`
- `quwoquan_app/lib/ui/content/entry/models/publish_settings_models.dart`
- `quwoquan_app/lib/ui/content/entry/pages/publish_circle_select_page.dart`
- `quwoquan_app/lib/ui/content/entry/providers/create_editor_provider.dart`
- `quwoquan_app/lib/ui/content/entry/services/ios_video_editing_service.dart`
- `quwoquan_app/lib/ui/content/entry/services/publish_settings_services.dart`
- `quwoquan_app/lib/ui/content/entry/widgets/article_editor.dart`
- `quwoquan_app/lib/ui/content/entry/widgets/article_editor_accessory_panels.dart`
- `quwoquan_app/lib/ui/content/entry/widgets/create_action_sheet.dart`
- `quwoquan_app/lib/ui/content/pages/photo_detail_page.dart`
- `quwoquan_app/lib/ui/content/pages/unified_media_viewer_page.dart`
- `quwoquan_app/lib/ui/content/pages/video_detail_page.dart`
- `quwoquan_app/lib/ui/content/post_summary_view.dart`
- `quwoquan_app/lib/ui/content/post_view_projection.dart`
- `quwoquan_app/lib/ui/content/providers/comment_provider.dart`
- `quwoquan_app/lib/ui/content/share/content_share_template.dart`
- `quwoquan_app/lib/ui/content/widgets/article_content_block_renderer.dart`
- `quwoquan_app/lib/ui/discovery/providers/discovery_feed_provider.dart`
- `quwoquan_app/lib/ui/discovery/providers/video_force_dark_provider.dart`
- `quwoquan_app/lib/ui/entity/models/homepage_route_models.dart`
- `quwoquan_app/lib/ui/entity/pages/homepage_claim_page.dart`
- `quwoquan_app/lib/ui/entity/pages/homepage_detail_page.dart`
- `quwoquan_app/lib/ui/entity/pages/homepage_maintenance_page.dart`
- `quwoquan_app/lib/ui/entity/pages/homepage_picker_page.dart`
- `quwoquan_app/lib/ui/entity/pages/suggest_homepage_page.dart`
- `quwoquan_app/lib/ui/entity/widgets/homepage_summary_card.dart`
- `quwoquan_app/lib/ui/rtc/models/call_layout_mode.dart`
- `quwoquan_app/lib/ui/rtc/models/call_participant.dart`
- `quwoquan_app/lib/ui/rtc/models/call_state.dart`
- `quwoquan_app/lib/ui/rtc/providers/call_participants_provider.dart`
- `quwoquan_app/lib/ui/rtc/providers/call_session_provider.dart`
- `quwoquan_app/lib/ui/rtc/providers/call_timer_provider.dart`
- `quwoquan_app/lib/ui/rtc/providers/media_device_provider.dart`
- `quwoquan_app/lib/ui/rtc/widgets/call_controls_bar.dart`
- `quwoquan_app/lib/ui/search/pages/global_search_page.dart`
- `quwoquan_app/lib/ui/search/pages/search_network_results_page.dart`
- `quwoquan_app/lib/ui/search/providers/search_coordinator.dart`
- `quwoquan_app/lib/ui/settings/pages/developer_settings_page.dart`
- `quwoquan_app/lib/ui/user/models/profile_mode.dart`
- `quwoquan_app/lib/ui/user/models/profile_tab.dart`
- `quwoquan_app/lib/ui/user/pages/sub_account_management_page.dart`
- `quwoquan_app/lib/ui/user/providers/profile_comments_provider.dart`
- `quwoquan_app/lib/ui/user/providers/profile_state_provider.dart`
- `quwoquan_app/lib/ui/user/widgets/profile_action_bar.dart`
- `quwoquan_app/lib/ui/user/widgets/profile_circles_tab.dart`
- `quwoquan_app/lib/ui/user/widgets/profile_resonance_card.dart`
- `quwoquan_app/lib/ui/user/widgets/profile_stats_row.dart`
- `quwoquan_app/lib/ui/user/widgets/profile_works_tab.dart`
