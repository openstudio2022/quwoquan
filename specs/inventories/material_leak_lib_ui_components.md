# lib/ui + lib/components Material 泄露清单

- **生成时间（UTC）**：2026-07-20T08:12:15Z
- **范围**：`quwoquan_app/lib/ui`、`quwoquan_app/lib/components` 下全部 `.dart`
- **复跑**：`python3 quwoquan_app/scripts/runtime/scan_material_leaks.py`
- **说明**：`material_import` 表示是否 `import 'package:flutter/material.dart'`；`signals` 为启发式正则命中次数（注释/字符串可能误报），用于排期与分桶，不作严格证明。

## 摘要

| 指标 | 数量 |
| --- | ---: |
| Dart 文件总数 | 637 |
| 任意形式依赖 material.dart（含 `show`） | 85 |
| 整库 import material（非 show） | 78 |
| 仅 `show …` 从 material 引用符号 | 7 |
| 未 import material.dart | 552 |

## 全局 signal 命中（跨文件合计）

| signal | hits |
| --- | ---: |
| `chip` | 2 |
| `colors_dot` | 1 |
| `divider` | 12 |
| `list_tile` | 1 |
| `material` | 9 |
| `material_page_route` | 9 |
| `range_slider` | 1 |
| `slider` | 4 |
| `theme_of` | 3 |
| `tooltip` | 1 |

## 按文件（有 material import 或存在 signal 命中）

| path | zone | material | cupertino | signals（摘要） |
| --- | --- | --- | --- | --- |
| `quwoquan_app/lib/components/assistant/assistant_avatar.dart` | components | full | no | — |
| `quwoquan_app/lib/components/assistant/petal_mark.dart` | components | full | no | — |
| `quwoquan_app/lib/components/avatar/conversation_avatar.dart` | components | full | no | — |
| `quwoquan_app/lib/components/conversation/conversation_timeline.dart` | components | full | no | — |
| `quwoquan_app/lib/components/conversation/message_action_menu_overlay.dart` | components | full | yes | — |
| `quwoquan_app/lib/components/conversation/message_bubble_frame.dart` | components | full | no | — |
| `quwoquan_app/lib/components/input/customizable_chat_input_bar.dart` | components | full | yes | — |
| `quwoquan_app/lib/components/media/image/editor/bottom_bar/image_editor_bottom_bar.dart` | components | full | no | — |
| `quwoquan_app/lib/components/media/image/editor/icons/image_editor_semantic_icon.dart` | components | full | no | — |
| `quwoquan_app/lib/components/media/image/editor/image_editor_page.dart` | components | full | yes | — |
| `quwoquan_app/lib/components/media/image/editor/image_editor_page_completion.dart` | components | none | no | `list_tile`×1 |
| `quwoquan_app/lib/components/media/image/editor/image_editor_page_params.dart` | components | full | no | — |
| `quwoquan_app/lib/components/media/image/editor/panels/hsl/image_editor_hsl_models.dart` | components | full | no | — |
| `quwoquan_app/lib/components/media/image/editor/panels/image_editor_operation_panel.dart` | components | full | yes | — |
| `quwoquan_app/lib/components/media/image/editor/panels/image_editor_operation_panel_controls.dart` | components | none | no | `slider`×2 |
| `quwoquan_app/lib/components/media/image/editor/panels/image_editor_rotate_overlay.dart` | components | full | no | — |
| `quwoquan_app/lib/components/media/image/editor/panels/local/image_editor_local_models.dart` | components | full | no | — |
| `quwoquan_app/lib/components/media/image/editor/shared/editor_session_ops_strip.dart` | components | full | no | — |
| `quwoquan_app/lib/components/media/image/editor/tool_list/image_editor_pro_tool_entries.dart` | components | full | no | — |
| `quwoquan_app/lib/components/media/image/editor/tool_list/image_editor_tool_constants.dart` | components | full | no | — |
| `quwoquan_app/lib/components/media/image/editor/tool_list/image_editor_tool_entry_chip.dart` | components | full | no | — |
| `quwoquan_app/lib/components/media/image/navigation/image_sub_tab_navigation.dart` | components | full | no | — |
| `quwoquan_app/lib/components/media/picker/create_media_picker_page.dart` | components | full | yes | — |
| `quwoquan_app/lib/components/media/picker/create_media_picker_page_state.dart` | components | none | no | `divider`×1, `material_page_route`×3 |
| `quwoquan_app/lib/components/media/picker/desktop/desktop_image_picker_page.dart` | components | full | yes | — |
| `quwoquan_app/lib/components/media/picker/one_tap_movie_preview_page.dart` | components | full | yes | — |
| `quwoquan_app/lib/components/media/reorderable/media_reorderable_view.dart` | components | full | no | — |
| `quwoquan_app/lib/components/media/shared/pageflip/media_page_flip_book.dart` | components | full | no | — |
| `quwoquan_app/lib/components/media/shared/toolbar/immersive_engagement_bar.dart` | components | full | yes | — |
| `quwoquan_app/lib/components/media/shared/toolbar/media_viewer_toolbar.dart` | components | full | yes | — |
| `quwoquan_app/lib/components/media/shared/viewer/media_assistant_panel.dart` | components | full | yes | — |
| `quwoquan_app/lib/components/media/shared/viewer/media_caption_widgets.dart` | components | full | no | — |
| `quwoquan_app/lib/components/media/video/player/video_playback_center_glyph.dart` | components | full | no | — |
| `quwoquan_app/lib/components/media/video/player/video_playback_timeline.dart` | components | full | no | — |
| `quwoquan_app/lib/components/media/video/player/video_player_surface_builder.dart` | components | full | yes | — |
| `quwoquan_app/lib/components/media/video/player/video_player_widget.dart` | components | full | no | — |
| `quwoquan_app/lib/components/media/video/player/video_timeline_preview.dart` | components | full | no | — |
| `quwoquan_app/lib/components/media/video/viewer/video_media_viewer.dart` | components | full | yes | — |
| `quwoquan_app/lib/components/settings_conversation/more_actions_popup/configs/media_post_config.dart` | components | full | no | — |
| `quwoquan_app/lib/ui/assistant/pages/assistant_reference_webview_page.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/assistant/pages/assistant_skill_center_page.dart` | ui | show (show TimeOfDay) | yes | — |
| `quwoquan_app/lib/ui/assistant/pages/personal_assistant_conversation_page.dart` | ui | show (show Material, MaterialType) | yes | `material`×1 |
| `quwoquan_app/lib/ui/assistant/widgets/assistant_half_sheet.dart` | ui | full | yes | `chip`×2, `colors_dot`×1 |
| `quwoquan_app/lib/ui/assistant/widgets/message/assistant_answer_content.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/assistant/widgets/message/assistant_message_bubble.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/chat/pages/chat_page.dart` | ui | full | yes | `divider`×3 |
| `quwoquan_app/lib/ui/chat/pages/chat_page_state.dart` | ui | none | no | `divider`×1 |
| `quwoquan_app/lib/ui/chat/pages/start_group_chat_group_picker_sheet.dart` | ui | none | no | `divider`×1 |
| `quwoquan_app/lib/ui/chat/pages/start_group_chat_page.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/chat/pages/start_group_chat_page_widgets.dart` | ui | none | no | `divider`×2 |
| `quwoquan_app/lib/ui/chat/widgets/message/chat_message_bubble.dart` | ui | full | yes | `theme_of`×1 |
| `quwoquan_app/lib/ui/chat/widgets/message/rtc_call_log_bubble.dart` | ui | full | yes | `theme_of`×1 |
| `quwoquan_app/lib/ui/chat/widgets/message/streaming_scroll_fab.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/chat/widgets/session/assistant_session_header.dart` | ui | full | no | — |
| `quwoquan_app/lib/ui/circle/constants/circle_channel_manage_layout.dart` | ui | full | no | — |
| `quwoquan_app/lib/ui/circle/constants/circle_channel_manage_style.dart` | ui | full | no | — |
| `quwoquan_app/lib/ui/circle/pages/circle_detail_page.dart` | ui | full | no | — |
| `quwoquan_app/lib/ui/circle/pages/circle_stats_page.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/circle/pages/home_circles_hub_page.dart` | ui | full | yes | `material`×3 |
| `quwoquan_app/lib/ui/circle/widgets/my_circles_rail.dart` | ui | full | no | — |
| `quwoquan_app/lib/ui/circle/widgets/rectangular_circle_card.dart` | ui | full | no | — |
| `quwoquan_app/lib/ui/circle/widgets/section_creations.dart` | ui | full | yes | `tooltip`×1 |
| `quwoquan_app/lib/ui/circle/widgets/section_storage.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/content/entry/pages/article_typography_page.dart` | ui | show (show Material, MaterialType) | yes | `material`×1 |
| `quwoquan_app/lib/ui/content/entry/pages/create_page.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/content/entry/pages/create_page_state.dart` | ui | none | no | `material`×1 |
| `quwoquan_app/lib/ui/content/entry/pages/create_page_state_chrome_helpers.dart` | ui | none | no | `material`×1 |
| `quwoquan_app/lib/ui/content/entry/pages/create_page_state_helpers.dart` | ui | none | no | `material_page_route`×5 |
| `quwoquan_app/lib/ui/content/entry/pages/create_page_state_media_helpers.dart` | ui | none | no | `material_page_route`×1 |
| `quwoquan_app/lib/ui/content/entry/pages/video_editor_page.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/content/entry/pages/video_editor_page_state.dart` | ui | none | no | `range_slider`×1, `slider`×1 |
| `quwoquan_app/lib/ui/content/entry/pages/video_editor_page_state_cover.dart` | ui | none | no | `slider`×1 |
| `quwoquan_app/lib/ui/content/entry/widgets/article_editor_accessory_panels.dart` | ui | show (show Icons, TextDirection, TextPainter, TextSpan, TextStyle) | yes | — |
| `quwoquan_app/lib/ui/content/entry/widgets/create_entry_sheet.dart` | ui | full | no | — |
| `quwoquan_app/lib/ui/content/share/content_share_actions.dart` | ui | full | no | — |
| `quwoquan_app/lib/ui/content/share/content_share_sheet.dart` | ui | full | yes | `divider`×1 |
| `quwoquan_app/lib/ui/discovery/pages/home_page.dart` | ui | show (show Material, MaterialType) | yes | `material`×2 |
| `quwoquan_app/lib/ui/discovery/widgets/home_multi_form_feed.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/discovery/widgets/home_multi_form_feed_scroll.dart` | ui | none | no | `divider`×1 |
| `quwoquan_app/lib/ui/discovery/widgets/works_immersive_viewer.dart` | ui | show (show Theme) | yes | — |
| `quwoquan_app/lib/ui/discovery/widgets/works_immersive_viewer_presentation.dart` | ui | none | no | `theme_of`×1 |
| `quwoquan_app/lib/ui/rtc/pages/call_participant_picker_page.dart` | ui | full | yes | — |
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
| `quwoquan_app/lib/ui/user/pages/login_page.dart` | ui | show (show Icons) | yes | — |
| `quwoquan_app/lib/ui/user/pages/my_profile_page.dart` | ui | full | yes | `divider`×1 |
| `quwoquan_app/lib/ui/user/pages/other_profile_page.dart` | ui | full | no | — |
| `quwoquan_app/lib/ui/user/widgets/circle_card.dart` | ui | full | no | — |
| `quwoquan_app/lib/ui/user/widgets/circle_compact_card.dart` | ui | full | yes | — |
| `quwoquan_app/lib/ui/user/widgets/creation_visibility_popup.dart` | ui | full | no | — |
| `quwoquan_app/lib/ui/user/widgets/profile_interaction_tab.dart` | ui | full | yes | `divider`×1 |

## 未 import material 且无表中 signal 命中的文件

以下文件在本脚本的 signal 规则下未记到典型 Material 控件模式；仍可能通过其他库间接依赖 Material（例如 `flutter/widgets.dart` 不包含 Material 组件，但父级 `Material` 祖先由路由/壳注入）。

- `quwoquan_app/lib/components/assistant/assistant_floating_ball.dart`
- `quwoquan_app/lib/components/avatar/rounded_square_avatar.dart`
- `quwoquan_app/lib/components/comment_system/comment_composer_models.dart`
- `quwoquan_app/lib/components/comment_system/comment_draft_store.dart`
- `quwoquan_app/lib/components/comment_system/comment_models.dart`
- `quwoquan_app/lib/components/comment_system/comment_toolbar.dart`
- `quwoquan_app/lib/components/components.dart`
- `quwoquan_app/lib/components/content/content_time_label.dart`
- `quwoquan_app/lib/components/content/intersection_reason_chip.dart`
- `quwoquan_app/lib/components/content/record_post_card.dart`
- `quwoquan_app/lib/components/conversation/conversation_link_action_sheet.dart`
- `quwoquan_app/lib/components/conversation/conversation_page_scaffold.dart`
- `quwoquan_app/lib/components/conversation/cupertino_conversation_sheet.dart`
- `quwoquan_app/lib/components/input/customizable_chat_input_bar_attachments.part.dart`
- `quwoquan_app/lib/components/input/customizable_chat_input_bar_composer.part.dart`
- `quwoquan_app/lib/components/input/customizable_chat_input_bar_layout.part.dart`
- `quwoquan_app/lib/components/input/customizable_chat_input_bar_voice.part.dart`
- `quwoquan_app/lib/components/input/unified_emoji_picker.dart`
- `quwoquan_app/lib/components/media/app_media_image.dart`
- `quwoquan_app/lib/components/media/camera/camera_capture_page.dart`
- `quwoquan_app/lib/components/media/camera/camera_capture_page_state.dart`
- `quwoquan_app/lib/components/media/camera/camera_capture_page_state_helpers.dart`
- `quwoquan_app/lib/components/media/camera/camera_capture_shell.dart`
- `quwoquan_app/lib/components/media/camera/camera_filter_strip.dart`
- `quwoquan_app/lib/components/media/camera/camera_session_models.dart`
- `quwoquan_app/lib/components/media/image/book/image_book_canvas.dart`
- `quwoquan_app/lib/components/media/image/book/image_book_page_surface.dart`
- `quwoquan_app/lib/components/media/image/editor/filter/image_editor_filter_feature_extractor.dart`
- `quwoquan_app/lib/components/media/image/editor/filter/image_editor_filter_matrix.dart`
- `quwoquan_app/lib/components/media/image/editor/filter/image_editor_filter_models.dart`
- `quwoquan_app/lib/components/media/image/editor/filter/image_editor_filter_recommendation_models.dart`
- `quwoquan_app/lib/components/media/image/editor/filter/image_editor_filter_recommender.dart`
- `quwoquan_app/lib/components/media/image/editor/filter/image_editor_filter_repository.dart`
- `quwoquan_app/lib/components/media/image/editor/filter/image_editor_filter_scene_classifier.dart`
- `quwoquan_app/lib/components/media/image/editor/image_editor_page_color_matrices.dart`
- `quwoquan_app/lib/components/media/image/editor/image_editor_page_crop_overlay.dart`
- `quwoquan_app/lib/components/media/image/editor/image_editor_page_crop_rotate.dart`
- `quwoquan_app/lib/components/media/image/editor/image_editor_page_curve_wb.dart`
- `quwoquan_app/lib/components/media/image/editor/image_editor_page_filter_logic.dart`
- `quwoquan_app/lib/components/media/image/editor/image_editor_page_history_logic.dart`
- `quwoquan_app/lib/components/media/image/editor/image_editor_page_local_preview_layers.dart`
- `quwoquan_app/lib/components/media/image/editor/image_editor_page_mosaic_text.dart`
- `quwoquan_app/lib/components/media/image/editor/image_editor_page_preview_layers.dart`
- `quwoquan_app/lib/components/media/image/editor/image_editor_page_pro_adjustments.dart`
- `quwoquan_app/lib/components/media/image/editor/image_editor_page_pro_tools.dart`
- `quwoquan_app/lib/components/media/image/editor/models/image_editor_step.dart`
- `quwoquan_app/lib/components/media/image/editor/models/image_editor_step_payload.dart`
- `quwoquan_app/lib/components/media/image/editor/panels/curves/image_editor_curve_models.dart`
- `quwoquan_app/lib/components/media/image/editor/panels/curves/image_editor_curve_panel.dart`
- `quwoquan_app/lib/components/media/image/editor/panels/image_editor_operation_panel_filter.dart`
- `quwoquan_app/lib/components/media/image/editor/panels/image_editor_operation_panel_pro.dart`
- `quwoquan_app/lib/components/media/image/editor/panels/mosaic/image_editor_mosaic_models.dart`
- `quwoquan_app/lib/components/media/image/editor/panels/text/image_editor_text_models.dart`
- `quwoquan_app/lib/components/media/image/editor/shared/image_editor_export_engine.dart`
- `quwoquan_app/lib/components/media/image/editor/shared/image_editor_step_stack.dart`
- `quwoquan_app/lib/components/media/image/editor/top_bar/image_editor_top_bar.dart`
- `quwoquan_app/lib/components/media/picker/create_media_picker_page_chrome.dart`
- `quwoquan_app/lib/components/media/picker/create_media_picker_page_state_helpers.dart`
- `quwoquan_app/lib/components/media/picker/create_media_picker_presentation.dart`
- `quwoquan_app/lib/components/media/picker/desktop/desktop_image_album_scanner.dart`
- `quwoquan_app/lib/components/media/picker/desktop/desktop_picker_services.dart`
- `quwoquan_app/lib/components/media/picker/desktop/desktop_thumbnail_image_provider.dart`
- `quwoquan_app/lib/components/media/picker/image_pick_gateway.dart`
- `quwoquan_app/lib/components/media/picker/one_tap_movie_composer.dart`
- `quwoquan_app/lib/components/media/shared/gesture/immersive_gesture_intent_controller.dart`
- `quwoquan_app/lib/components/media/shared/gesture/immersive_pointer_gesture_layer.dart`
- `quwoquan_app/lib/components/media/shared/media_creation_bottom_button.dart`
- `quwoquan_app/lib/components/media/shared/toolbar/immersive_intersection_statement.dart`
- `quwoquan_app/lib/components/media/shared/viewer/immersive_media_failure_content.dart`
- `quwoquan_app/lib/components/media/shared/viewer/immersive_viewer_layout.dart`
- `quwoquan_app/lib/components/media/video/player/video_playback_failure_overlay.dart`
- `quwoquan_app/lib/components/media/video/player/video_playback_session.dart`
- `quwoquan_app/lib/components/media/video/player/video_playback_session_models.dart`
- `quwoquan_app/lib/components/media/video/player/video_player_support.dart`
- `quwoquan_app/lib/components/media/video/player/video_player_widget_api.dart`
- `quwoquan_app/lib/components/navigation/centered_scrollable_tab_bar.dart`
- `quwoquan_app/lib/components/navigation/home_primary_tab_strip.dart`
- `quwoquan_app/lib/components/navigation/secondary_capsule_tab_bar.dart`
- `quwoquan_app/lib/components/navigation/tab_navigation.dart`
- `quwoquan_app/lib/components/navigation/tab_swipe_switch_region.dart`
- `quwoquan_app/lib/components/object_page/interactive_intersection_text.dart`
- `quwoquan_app/lib/components/object_page/intersection_entity.dart`
- `quwoquan_app/lib/components/object_page/intersection_icon_resolver.dart`
- `quwoquan_app/lib/components/object_page/intersection_lifecycle_badge.dart`
- `quwoquan_app/lib/components/object_page/intersection_object_cover.dart`
- `quwoquan_app/lib/components/object_page/intersection_propagation_view.dart`
- `quwoquan_app/lib/components/object_page/intersection_statement_card.dart`
- `quwoquan_app/lib/components/object_page/intersection_statement_row.dart`
- `quwoquan_app/lib/components/object_page/intersection_target_navigator.dart`
- `quwoquan_app/lib/components/object_page/intersection_visual_cluster.dart`
- `quwoquan_app/lib/components/object_page/object_action_bar.dart`
- `quwoquan_app/lib/components/object_page/object_chrome_actions.dart`
- `quwoquan_app/lib/components/object_page/object_impact_preview_card.dart`
- `quwoquan_app/lib/components/object_page/object_insight_primitives.dart`
- `quwoquan_app/lib/components/object_page/object_intersection_card.dart`
- `quwoquan_app/lib/components/object_page/object_intersection_card_skeleton.dart`
- `quwoquan_app/lib/components/object_page/object_intersection_provider.dart`
- `quwoquan_app/lib/components/object_page/object_intersection_section.dart`
- `quwoquan_app/lib/components/object_page/object_meta_chip.dart`
- `quwoquan_app/lib/components/object_page/object_page_sections.dart`
- `quwoquan_app/lib/components/object_page/object_page_shell.dart`
- `quwoquan_app/lib/components/object_page/object_secondary_filter_bar.dart`
- `quwoquan_app/lib/components/object_page/object_slogan_card.dart`
- `quwoquan_app/lib/components/object_page/object_stats_row.dart`
- `quwoquan_app/lib/components/object_page/profile_ios_components.dart`
- `quwoquan_app/lib/components/pageflip/backward_render_frame_builder.dart`
- `quwoquan_app/lib/components/pageflip/book_layout.dart`
- `quwoquan_app/lib/components/pageflip/controller.dart`
- `quwoquan_app/lib/components/pageflip/curl_light_model.dart`
- `quwoquan_app/lib/components/pageflip/curl_mesh_builder.dart`
- `quwoquan_app/lib/components/pageflip/curl_renderer.dart`
- `quwoquan_app/lib/components/pageflip/forward_render_frame_builder.dart`
- `quwoquan_app/lib/components/pageflip/geometry.dart`
- `quwoquan_app/lib/components/pageflip/page_surface_snapshot.dart`
- `quwoquan_app/lib/components/pageflip/pointer_bridge.dart`
- `quwoquan_app/lib/components/pageflip/release_policy.dart`
- `quwoquan_app/lib/components/pageflip/render_frame.dart`
- `quwoquan_app/lib/components/pageflip/reverse_curl_calculation.dart`
- `quwoquan_app/lib/components/pageflip/spread_model.dart`
- `quwoquan_app/lib/components/pageflip/types.dart`
- `quwoquan_app/lib/components/post/post_preview_card.dart`
- `quwoquan_app/lib/components/post/post_preview_list_tile.dart`
- `quwoquan_app/lib/components/search/embedded/embedded_member_search_bar_plain.dart`
- `quwoquan_app/lib/components/search/embedded/embedded_member_search_bar_with_chips.dart`
- `quwoquan_app/lib/components/search/embedded/embedded_member_search_page_shell.dart`
- `quwoquan_app/lib/components/search/embedded/grouped_member_list_sections.dart`
- `quwoquan_app/lib/components/search/embedded/inset_grouped_member_list_card.dart`
- `quwoquan_app/lib/components/search/embedded/member_list_tiles.dart`
- `quwoquan_app/lib/components/search/embedded/member_query_filter.dart`
- `quwoquan_app/lib/components/search/search_embedded.dart`
- `quwoquan_app/lib/components/settings_conversation/more_actions_popup/more_action_popup.dart`
- `quwoquan_app/lib/components/settings_conversation/settings_conversation.dart`
- `quwoquan_app/lib/components/settings_conversation/sheet/conversation_sheet.dart`
- `quwoquan_app/lib/components/settings_form/settings_form.dart`
- `quwoquan_app/lib/components/settings_form/settings_inset_form_page.dart`
- `quwoquan_app/lib/ui/assistant/assistant_conversation_model_history_text.dart`
- `quwoquan_app/lib/ui/assistant/config/assistant_prompt_config.dart`
- `quwoquan_app/lib/ui/assistant/models/assistant_context_scope_read_view.dart`
- `quwoquan_app/lib/ui/assistant/models/assistant_display_fallbacks.dart`
- `quwoquan_app/lib/ui/assistant/models/assistant_privacy_policy_hint_read_view.dart`
- `quwoquan_app/lib/ui/assistant/models/assistant_structured_run_response_read_view.dart`
- `quwoquan_app/lib/ui/assistant/models/assistant_transcript_bubble_envelope.dart`
- `quwoquan_app/lib/ui/assistant/models/assistant_ui_usage_stats_view_data.dart`
- `quwoquan_app/lib/ui/assistant/pages/assistant_management_page.dart`
- `quwoquan_app/lib/ui/assistant/pages/assistant_skill_center_models.dart`
- `quwoquan_app/lib/ui/assistant/pages/assistant_skill_center_sections.dart`
- `quwoquan_app/lib/ui/assistant/providers/assistant_history_loader.dart`
- `quwoquan_app/lib/ui/assistant/providers/personal_assistant_stream_controller.dart`
- `quwoquan_app/lib/ui/assistant/providers/personal_assistant_stream_controller_projection.dart`
- `quwoquan_app/lib/ui/assistant/widgets/assistant_conversation_empty_state.dart`
- `quwoquan_app/lib/ui/assistant/widgets/assistant_conversation_inline_error.dart`
- `quwoquan_app/lib/ui/assistant/widgets/assistant_history_sheet.dart`
- `quwoquan_app/lib/ui/assistant/widgets/message/assistant_answer_toolbar.dart`
- `quwoquan_app/lib/ui/assistant/widgets/message/assistant_journey_view_model.dart`
- `quwoquan_app/lib/ui/assistant/widgets/message/assistant_process_drawer.dart`
- `quwoquan_app/lib/ui/assistant/widgets/message/assistant_turn_message_resolver.dart`
- `quwoquan_app/lib/ui/assistant/widgets/message/regenerate_options_popup.dart`
- `quwoquan_app/lib/ui/chat/models/chat_contacts_row.dart`
- `quwoquan_app/lib/ui/chat/models/chat_list_item_view_model.dart`
- `quwoquan_app/lib/ui/chat/models/chat_message_media_view_data.dart`
- `quwoquan_app/lib/ui/chat/models/start_group_pickable_member.dart`
- `quwoquan_app/lib/ui/chat/pages/chat_announcement_page.dart`
- `quwoquan_app/lib/ui/chat/pages/chat_conversation_page.dart`
- `quwoquan_app/lib/ui/chat/pages/chat_conversation_page_actions.dart`
- `quwoquan_app/lib/ui/chat/pages/chat_display_fallbacks.dart`
- `quwoquan_app/lib/ui/chat/pages/chat_page_visit_recorder.dart`
- `quwoquan_app/lib/ui/chat/pages/chat_page_visit_tracking.dart`
- `quwoquan_app/lib/ui/chat/pages/chat_settings_page.dart`
- `quwoquan_app/lib/ui/chat/pages/greeting_inbox_page.dart`
- `quwoquan_app/lib/ui/chat/pages/greeting_inbox_page_widgets.dart`
- `quwoquan_app/lib/ui/chat/pages/group_admins_page.dart`
- `quwoquan_app/lib/ui/chat/pages/group_manage_page.dart`
- `quwoquan_app/lib/ui/chat/pages/group_member_search_page.dart`
- `quwoquan_app/lib/ui/chat/pages/start_group_chat_member_sheet.dart`
- `quwoquan_app/lib/ui/chat/pages/transfer_ownership_page.dart`
- `quwoquan_app/lib/ui/chat/providers/chat_contacts_rows_provider.dart`
- `quwoquan_app/lib/ui/chat/providers/chat_inbox_provider.dart`
- `quwoquan_app/lib/ui/chat/providers/chat_message_provider.dart`
- `quwoquan_app/lib/ui/chat/providers/chat_send_outbox.dart`
- `quwoquan_app/lib/ui/chat/providers/chat_settings_provider.dart`
- `quwoquan_app/lib/ui/chat/providers/conversation_members_provider.dart`
- `quwoquan_app/lib/ui/chat/providers/greeting_inbox_provider.dart`
- `quwoquan_app/lib/ui/chat/providers/group_home_provider.dart`
- `quwoquan_app/lib/ui/chat/providers/message_home_rows_provider.dart`
- `quwoquan_app/lib/ui/chat/providers/notification_inbox_provider.dart`
- `quwoquan_app/lib/ui/chat/providers/start_group_from_group_provider.dart`
- `quwoquan_app/lib/ui/chat/providers/start_group_member_wizard_provider.dart`
- `quwoquan_app/lib/ui/chat/providers/voice_player_manager.dart`
- `quwoquan_app/lib/ui/chat/providers/voice_send_provider.dart`
- `quwoquan_app/lib/ui/chat/services/start_group_chat_wire.dart`
- `quwoquan_app/lib/ui/chat/utils/chat_contact_initials.dart`
- `quwoquan_app/lib/ui/chat/utils/chat_pinyin_match.dart`
- `quwoquan_app/lib/ui/chat/widgets/chat_conversation_avatar_tokens.dart`
- `quwoquan_app/lib/ui/chat/widgets/message/assistant_answer_toolbar.dart`
- `quwoquan_app/lib/ui/chat/widgets/message/assistant_journey_view_model.dart`
- `quwoquan_app/lib/ui/chat/widgets/message/assistant_process_drawer.dart`
- `quwoquan_app/lib/ui/chat/widgets/message/assistant_turn_message_resolver.dart`
- `quwoquan_app/lib/ui/chat/widgets/message/regenerate_options_popup.dart`
- `quwoquan_app/lib/ui/chat/widgets/message/voice_message_bubble.dart`
- `quwoquan_app/lib/ui/chat/widgets/message/voice_waveform_painter.dart`
- `quwoquan_app/lib/ui/chat/widgets/voice/voice_recorder.dart`
- `quwoquan_app/lib/ui/circle/models/circle_edit_submit_payload.dart`
- `quwoquan_app/lib/ui/circle/models/circle_hub_feed_post_entry.dart`
- `quwoquan_app/lib/ui/circle/models/circle_page_tab.dart`
- `quwoquan_app/lib/ui/circle/models/circle_stats_list_view_data.dart`
- `quwoquan_app/lib/ui/circle/models/circle_stats_view_data.dart`
- `quwoquan_app/lib/ui/circle/models/circle_tab.dart`
- `quwoquan_app/lib/ui/circle/pages/circle_edit_settings_page.dart`
- `quwoquan_app/lib/ui/circle/pages/circle_edit_settings_page_state.dart`
- `quwoquan_app/lib/ui/circle/pages/circle_edit_settings_page_state_helpers.dart`
- `quwoquan_app/lib/ui/circle/pages/circles_hub_page.dart`
- `quwoquan_app/lib/ui/circle/pages/circles_page.dart`
- `quwoquan_app/lib/ui/circle/pages/home_circles_hub_page_widgets.dart`
- `quwoquan_app/lib/ui/circle/providers/circle_impact_provider.dart`
- `quwoquan_app/lib/ui/circle/providers/circle_state_provider.dart`
- `quwoquan_app/lib/ui/circle/services/circle_stats_row_wire.dart`
- `quwoquan_app/lib/ui/circle/services/home_circles_hub_media_viewer_wiring.dart`
- `quwoquan_app/lib/ui/circle/services/home_circles_hub_wire.dart`
- `quwoquan_app/lib/ui/circle/widgets/circle_action_bar.dart`
- `quwoquan_app/lib/ui/circle/widgets/circle_header.dart`
- `quwoquan_app/lib/ui/circle/widgets/circle_shell.dart`
- `quwoquan_app/lib/ui/circle/widgets/circle_shell_builders.dart`
- `quwoquan_app/lib/ui/circle/widgets/circle_shell_components.dart`
- `quwoquan_app/lib/ui/circle/widgets/home_circles_category_tab.dart`
- `quwoquan_app/lib/ui/circle/widgets/home_circles_entity_bridge_strip.dart`
- `quwoquan_app/lib/ui/circle/widgets/media_viewer_result_absorber.dart`
- `quwoquan_app/lib/ui/circle/widgets/section_chat.dart`
- `quwoquan_app/lib/ui/circle/widgets/section_creations_state.dart`
- `quwoquan_app/lib/ui/circle/widgets/section_creations_state_helpers.dart`
- `quwoquan_app/lib/ui/circle/widgets/section_members.dart`
- `quwoquan_app/lib/ui/content/article_reader/article_reader.dart`
- `quwoquan_app/lib/ui/content/article_reader/content/article_reader_content.dart`
- `quwoquan_app/lib/ui/content/article_reader/content/article_reader_page_surfaces.dart`
- `quwoquan_app/lib/ui/content/article_reader/content/article_reader_page_surfaces_backdrops.dart`
- `quwoquan_app/lib/ui/content/article_reader/content/article_reader_page_surfaces_blocks.dart`
- `quwoquan_app/lib/ui/content/article_reader/content/article_reader_pagination.dart`
- `quwoquan_app/lib/ui/content/article_reader/hosts/article_detail_reader_adapter.dart`
- `quwoquan_app/lib/ui/content/article_reader/hosts/article_editor_reader_adapter.dart`
- `quwoquan_app/lib/ui/content/article_reader/hosts/article_reader_host_adapter.dart`
- `quwoquan_app/lib/ui/content/article_reader/hosts/immersive_browser_reader_adapter.dart`
- `quwoquan_app/lib/ui/content/article_reader/pageflip/diagnostics/article_reader_debug_mapper.dart`
- `quwoquan_app/lib/ui/content/article_reader/pageflip/diagnostics/article_reader_debug_state.dart`
- `quwoquan_app/lib/ui/content/article_reader/pageflip/diagnostics/article_reader_diagnostic_signatures.dart`
- `quwoquan_app/lib/ui/content/article_reader/pageflip/host/article_read_only_book_deck.dart`
- `quwoquan_app/lib/ui/content/article_reader/pageflip/host/article_reader_flip_host.dart`
- `quwoquan_app/lib/ui/content/article_reader/pageflip/host/article_reader_stage_widgets.dart`
- `quwoquan_app/lib/ui/content/article_reader/pageflip/layers/article_reader_dynamic_layers.dart`
- `quwoquan_app/lib/ui/content/article_reader/pageflip/layers/article_reader_soft_page_geometry.dart`
- `quwoquan_app/lib/ui/content/article_reader/pageflip/layers/backward_leaf_verso_pixel_probe.dart`
- `quwoquan_app/lib/ui/content/article_reader/pageflip/layers/backward_leaf_verso_uv_mesh.dart`
- `quwoquan_app/lib/ui/content/article_reader/pageflip/layers/backward_sheet_partition.dart`
- `quwoquan_app/lib/ui/content/article_reader/pageflip/modes/article_reader_mode_strategy.dart`
- `quwoquan_app/lib/ui/content/article_reader/pageflip/modes/single_page_mode_strategy.dart`
- `quwoquan_app/lib/ui/content/article_reader/pageflip/modes/spread_double_page_mode_strategy.dart`
- `quwoquan_app/lib/ui/content/article_reader/pageflip/pipelines/article_reader_flip_pipeline.dart`
- `quwoquan_app/lib/ui/content/article_reader/pageflip/pipelines/backward_article_flip_pipeline.dart`
- `quwoquan_app/lib/ui/content/article_reader/pageflip/pipelines/forward_article_flip_pipeline.dart`
- `quwoquan_app/lib/ui/content/article_reader/pageflip/texture/article_reader_texture_cache.dart`
- `quwoquan_app/lib/ui/content/article_reader/pageflip/texture/article_reader_texture_capture_layer.dart`
- `quwoquan_app/lib/ui/content/article_reader/templates/article_reader_template_theme.dart`
- `quwoquan_app/lib/ui/content/article_reader/templates/article_reader_template_thumbnail.dart`
- `quwoquan_app/lib/ui/content/article_reader/templates/article_reader_templates.dart`
- `quwoquan_app/lib/ui/content/article_render/markdown/article_markdown_codec.dart`
- `quwoquan_app/lib/ui/content/article_render/markdown/immersive_markdown_reader.dart`
- `quwoquan_app/lib/ui/content/article_render/markdown/qwq_markdown.dart`
- `quwoquan_app/lib/ui/content/article_render/markdown/qwq_markdown_ast.dart`
- `quwoquan_app/lib/ui/content/article_render/markdown/qwq_markdown_pagination.dart`
- `quwoquan_app/lib/ui/content/article_render/markdown/qwq_markdown_parser.dart`
- `quwoquan_app/lib/ui/content/article_render/services/article_flow_layout_engine.dart`
- `quwoquan_app/lib/ui/content/article_render/services/article_image_intrinsic_registry.dart`
- `quwoquan_app/lib/ui/content/article_render/services/article_pagination_engine.dart`
- `quwoquan_app/lib/ui/content/comments/providers/comment_provider.dart`
- `quwoquan_app/lib/ui/content/comments/providers/comment_provider_counts_sync.dart`
- `quwoquan_app/lib/ui/content/comments/providers/comment_provider_reply_tree.dart`
- `quwoquan_app/lib/ui/content/comments/providers/comment_provider_state.dart`
- `quwoquan_app/lib/ui/content/comments/widgets/comment_detail_surface.dart`
- `quwoquan_app/lib/ui/content/comments/widgets/comment_input_overlay.dart`
- `quwoquan_app/lib/ui/content/comments/widgets/comment_input_overlay_components.dart`
- `quwoquan_app/lib/ui/content/comments/widgets/comment_thread_atoms.dart`
- `quwoquan_app/lib/ui/content/comments/widgets/comment_thread_rows.dart`
- `quwoquan_app/lib/ui/content/comments/widgets/comment_thread_view.dart`
- `quwoquan_app/lib/ui/content/comments/widgets/comment_viewer.dart`
- `quwoquan_app/lib/ui/content/comments/widgets/comment_viewer_modal.dart`
- `quwoquan_app/lib/ui/content/comments/widgets/immersive_comment_split_sheet.dart`
- `quwoquan_app/lib/ui/content/entry/pages/create_page_state_draft_helpers.dart`
- `quwoquan_app/lib/ui/content/entry/pages/create_page_state_surface_helpers.dart`
- `quwoquan_app/lib/ui/content/entry/pages/local_draft_page.dart`
- `quwoquan_app/lib/ui/content/entry/pages/publish_circle_select_page.dart`
- `quwoquan_app/lib/ui/content/entry/pages/publish_location_selector_page.dart`
- `quwoquan_app/lib/ui/content/entry/providers/create_draft_store_provider.dart`
- `quwoquan_app/lib/ui/content/entry/providers/create_editor_provider.dart`
- `quwoquan_app/lib/ui/content/entry/providers/create_editor_provider_document_operations.dart`
- `quwoquan_app/lib/ui/content/entry/providers/create_editor_provider_media_operations.dart`
- `quwoquan_app/lib/ui/content/entry/providers/create_editor_provider_node_editing_operations.dart`
- `quwoquan_app/lib/ui/content/entry/providers/create_editor_provider_node_structure_operations.dart`
- `quwoquan_app/lib/ui/content/entry/providers/post_publication_intent_queue_provider.dart`
- `quwoquan_app/lib/ui/content/entry/publish_draft_projection_bridge.dart`
- `quwoquan_app/lib/ui/content/entry/services/article_entity_mention_picker.dart`
- `quwoquan_app/lib/ui/content/entry/services/create_draft_local_storage.dart`
- `quwoquan_app/lib/ui/content/entry/services/create_draft_session_controller.dart`
- `quwoquan_app/lib/ui/content/entry/services/create_page_provider_bridge.dart`
- `quwoquan_app/lib/ui/content/entry/services/create_page_remote_helpers.dart`
- `quwoquan_app/lib/ui/content/entry/services/ios_video_editing_service.dart`
- `quwoquan_app/lib/ui/content/entry/services/publish_circle_services.dart`
- `quwoquan_app/lib/ui/content/entry/widgets/article_editor.dart`
- `quwoquan_app/lib/ui/content/entry/widgets/article_editor_accessory_controls.dart`
- `quwoquan_app/lib/ui/content/entry/widgets/article_editor_accessory_selection_panels.dart`
- `quwoquan_app/lib/ui/content/entry/widgets/article_editor_accessory_style_panels.dart`
- `quwoquan_app/lib/ui/content/entry/widgets/article_editor_content_builders.dart`
- `quwoquan_app/lib/ui/content/entry/widgets/article_preview_book_pager.dart`
- `quwoquan_app/lib/ui/content/entry/widgets/article_typography_thumbnail_raster.dart`
- `quwoquan_app/lib/ui/content/entry/widgets/article_wrap_layout.dart`
- `quwoquan_app/lib/ui/content/entry/widgets/article_wrap_paragraph_editor.dart`
- `quwoquan_app/lib/ui/content/entry/widgets/create_action_sheet.dart`
- `quwoquan_app/lib/ui/content/entry/widgets/create_draft_picker_flow.dart`
- `quwoquan_app/lib/ui/content/entry/widgets/create_draft_picker_sheet.dart`
- `quwoquan_app/lib/ui/content/entry/widgets/create_publish_confirm_sheet.dart`
- `quwoquan_app/lib/ui/content/entry/widgets/create_publish_confirm_sheet_widgets.dart`
- `quwoquan_app/lib/ui/content/models/article_detail_view.dart`
- `quwoquan_app/lib/ui/content/models/article_document_models.dart`
- `quwoquan_app/lib/ui/content/models/article_editor_projection.dart`
- `quwoquan_app/lib/ui/content/models/article_presentation_layout_models.dart`
- `quwoquan_app/lib/ui/content/models/article_presentation_models.dart`
- `quwoquan_app/lib/ui/content/models/article_theme.dart`
- `quwoquan_app/lib/ui/content/models/content_route_models.dart`
- `quwoquan_app/lib/ui/content/models/content_surface_view.dart`
- `quwoquan_app/lib/ui/content/models/content_surface_view_mapper.dart`
- `quwoquan_app/lib/ui/content/models/create_editor_models.dart`
- `quwoquan_app/lib/ui/content/models/create_editor_models_article_blocks.dart`
- `quwoquan_app/lib/ui/content/models/create_editor_models_draft.dart`
- `quwoquan_app/lib/ui/content/models/create_editor_undo_snapshot.dart`
- `quwoquan_app/lib/ui/content/models/create_entry_arguments.dart`
- `quwoquan_app/lib/ui/content/models/post_read_ui_bundle.dart`
- `quwoquan_app/lib/ui/content/models/publish_settings_models.dart`
- `quwoquan_app/lib/ui/content/seo/markdown_seo_html_renderer.dart`
- `quwoquan_app/lib/ui/content/services/post_view_projection.dart`
- `quwoquan_app/lib/ui/content/services/single_post_media_viewer.dart`
- `quwoquan_app/lib/ui/content/share/content_circle_share_picker_route.dart`
- `quwoquan_app/lib/ui/content/share/content_share_sheet_components.dart`
- `quwoquan_app/lib/ui/content/share/content_share_template.dart`
- `quwoquan_app/lib/ui/content/widgets/article_content_block_renderer.dart`
- `quwoquan_app/lib/ui/content/widgets/article_paged_canvas.dart`
- `quwoquan_app/lib/ui/discovery/models/home_feed_layout_policy.dart`
- `quwoquan_app/lib/ui/discovery/models/home_feed_video_autoplay_policy.dart`
- `quwoquan_app/lib/ui/discovery/models/home_feed_video_focus_coordinator.dart`
- `quwoquan_app/lib/ui/discovery/pages/unified_media_viewer_page.dart`
- `quwoquan_app/lib/ui/discovery/pages/work_browser_entry_page.dart`
- `quwoquan_app/lib/ui/discovery/providers/discovery_feed_provider.dart`
- `quwoquan_app/lib/ui/discovery/providers/discovery_state.dart`
- `quwoquan_app/lib/ui/discovery/providers/feed_realtime_patch_provider.dart`
- `quwoquan_app/lib/ui/discovery/providers/video_force_dark_provider.dart`
- `quwoquan_app/lib/ui/discovery/services/discovery_share_template.dart`
- `quwoquan_app/lib/ui/discovery/services/home_feed_media_viewer_wiring.dart`
- `quwoquan_app/lib/ui/discovery/services/home_feed_post_open_action.dart`
- `quwoquan_app/lib/ui/discovery/services/media_viewer_interaction_bridge.dart`
- `quwoquan_app/lib/ui/discovery/widgets/following_subject_strip.dart`
- `quwoquan_app/lib/ui/discovery/widgets/home_multi_form_feed_actions.dart`
- `quwoquan_app/lib/ui/discovery/widgets/home_multi_form_feed_media.dart`
- `quwoquan_app/lib/ui/discovery/widgets/home_multi_form_feed_media_autoplay.dart`
- `quwoquan_app/lib/ui/discovery/widgets/home_multi_form_feed_media_grid.dart`
- `quwoquan_app/lib/ui/discovery/widgets/home_multi_form_feed_object_cards.dart`
- `quwoquan_app/lib/ui/discovery/widgets/home_multi_form_feed_post_cards.dart`
- `quwoquan_app/lib/ui/discovery/widgets/home_multi_form_feed_report_actions.dart`
- `quwoquan_app/lib/ui/discovery/widgets/home_multi_form_feed_states.dart`
- `quwoquan_app/lib/ui/discovery/widgets/works_immersive_viewer_build.dart`
- `quwoquan_app/lib/ui/discovery/widgets/works_immersive_viewer_canvas.dart`
- `quwoquan_app/lib/ui/discovery/widgets/works_immersive_viewer_controls.dart`
- `quwoquan_app/lib/ui/discovery/widgets/works_immersive_viewer_engagement_actions.dart`
- `quwoquan_app/lib/ui/discovery/widgets/works_immersive_viewer_intersection_actions.dart`
- `quwoquan_app/lib/ui/discovery/widgets/works_immersive_viewer_lifecycle.dart`
- `quwoquan_app/lib/ui/discovery/widgets/works_immersive_viewer_observability.dart`
- `quwoquan_app/lib/ui/discovery/widgets/works_immersive_viewer_paging.dart`
- `quwoquan_app/lib/ui/discovery/widgets/works_immersive_viewer_social_actions.dart`
- `quwoquan_app/lib/ui/discovery/widgets/works_immersive_viewer_video_chrome.dart`
- `quwoquan_app/lib/ui/entity/models/homepage_action_observability.dart`
- `quwoquan_app/lib/ui/entity/models/homepage_route_models.dart`
- `quwoquan_app/lib/ui/entity/models/homepage_tab.dart`
- `quwoquan_app/lib/ui/entity/models/homepage_type_labels.dart`
- `quwoquan_app/lib/ui/entity/models/homepage_write_access.dart`
- `quwoquan_app/lib/ui/entity/pages/homepage_claim_page.dart`
- `quwoquan_app/lib/ui/entity/pages/homepage_detail_page.dart`
- `quwoquan_app/lib/ui/entity/pages/homepage_introduction_page.dart`
- `quwoquan_app/lib/ui/entity/pages/homepage_introduction_page_content.dart`
- `quwoquan_app/lib/ui/entity/pages/homepage_introduction_page_related.dart`
- `quwoquan_app/lib/ui/entity/pages/homepage_maintenance_page.dart`
- `quwoquan_app/lib/ui/entity/pages/homepage_picker_page.dart`
- `quwoquan_app/lib/ui/entity/pages/homepage_status_report_page.dart`
- `quwoquan_app/lib/ui/entity/pages/homepage_status_report_page_state.dart`
- `quwoquan_app/lib/ui/entity/pages/suggest_homepage_page.dart`
- `quwoquan_app/lib/ui/entity/providers/entity_impact_provider.dart`
- `quwoquan_app/lib/ui/entity/providers/homepage_introduction_provider.dart`
- `quwoquan_app/lib/ui/entity/widgets/homepage_detail_shell.dart`
- `quwoquan_app/lib/ui/entity/widgets/homepage_detail_shell_builders.dart`
- `quwoquan_app/lib/ui/entity/widgets/homepage_detail_shell_components.dart`
- `quwoquan_app/lib/ui/entity/widgets/homepage_detail_shell_components2.dart`
- `quwoquan_app/lib/ui/entity/widgets/homepage_review_section.dart`
- `quwoquan_app/lib/ui/entity/widgets/homepage_review_sheet.dart`
- `quwoquan_app/lib/ui/entity/widgets/homepage_summary_card.dart`
- `quwoquan_app/lib/ui/interest_match/pages/interest_match_page.dart`
- `quwoquan_app/lib/ui/intersection/pages/object_intersection_list_page.dart`
- `quwoquan_app/lib/ui/rtc/models/call_layout_mode.dart`
- `quwoquan_app/lib/ui/rtc/models/call_participant.dart`
- `quwoquan_app/lib/ui/rtc/models/call_participant_picker_route_extra.dart`
- `quwoquan_app/lib/ui/rtc/models/call_picker_participant_row.dart`
- `quwoquan_app/lib/ui/rtc/models/call_session_signal_projection.dart`
- `quwoquan_app/lib/ui/rtc/models/call_session_state.dart`
- `quwoquan_app/lib/ui/rtc/models/call_state.dart`
- `quwoquan_app/lib/ui/rtc/pages/incoming_call_page.dart`
- `quwoquan_app/lib/ui/rtc/pages/outgoing_call_page.dart`
- `quwoquan_app/lib/ui/rtc/pages/video_call_page.dart`
- `quwoquan_app/lib/ui/rtc/providers/call_participants_provider.dart`
- `quwoquan_app/lib/ui/rtc/providers/call_session_provider.dart`
- `quwoquan_app/lib/ui/rtc/providers/call_timer_provider.dart`
- `quwoquan_app/lib/ui/rtc/providers/media_device_provider.dart`
- `quwoquan_app/lib/ui/rtc/widgets/call_controls_bar.dart`
- `quwoquan_app/lib/ui/rtc/widgets/call_permission_guard.dart`
- `quwoquan_app/lib/ui/rtc/widgets/call_stage_banner.dart`
- `quwoquan_app/lib/ui/rtc/widgets/call_stage_chrome.dart`
- `quwoquan_app/lib/ui/rtc/widgets/video_call_screen_share_status.dart`
- `quwoquan_app/lib/ui/search/models/recent_search_read_presentation.dart`
- `quwoquan_app/lib/ui/search/models/search_result_tab_spec.dart`
- `quwoquan_app/lib/ui/search/pages/global_search_page.dart`
- `quwoquan_app/lib/ui/search/pages/global_search_page_history_widgets.dart`
- `quwoquan_app/lib/ui/search/pages/global_search_page_inspiration_widgets.dart`
- `quwoquan_app/lib/ui/search/pages/global_search_page_state.dart`
- `quwoquan_app/lib/ui/search/pages/global_search_page_state_history.dart`
- `quwoquan_app/lib/ui/search/pages/global_search_page_state_navigation.dart`
- `quwoquan_app/lib/ui/search/pages/global_search_page_state_suggestions.dart`
- `quwoquan_app/lib/ui/search/pages/global_search_page_suggestion_widgets.dart`
- `quwoquan_app/lib/ui/search/pages/location_place_landing_page.dart`
- `quwoquan_app/lib/ui/search/pages/search_network_results_page.dart`
- `quwoquan_app/lib/ui/search/pages/search_network_results_page_card_widgets.dart`
- `quwoquan_app/lib/ui/search/pages/search_network_results_page_models.dart`
- `quwoquan_app/lib/ui/search/pages/search_network_results_page_state.dart`
- `quwoquan_app/lib/ui/search/pages/search_network_results_page_state_data_navigation.dart`
- `quwoquan_app/lib/ui/search/pages/search_network_results_page_state_helpers.dart`
- `quwoquan_app/lib/ui/search/pages/search_network_results_page_state_loading.dart`
- `quwoquan_app/lib/ui/search/pages/search_network_results_page_state_view_helpers.dart`
- `quwoquan_app/lib/ui/search/pages/search_network_results_page_status_widgets.dart`
- `quwoquan_app/lib/ui/search/providers/search_coordinator.dart`
- `quwoquan_app/lib/ui/search/providers/search_coordinator_execution.dart`
- `quwoquan_app/lib/ui/search/providers/search_coordinator_suggestion_builders.dart`
- `quwoquan_app/lib/ui/search/providers/search_coordinator_suggestions.dart`
- `quwoquan_app/lib/ui/search/providers/search_coordinator_support.dart`
- `quwoquan_app/lib/ui/search/services/search_network_results_media_wiring.dart`
- `quwoquan_app/lib/ui/settings/pages/blocked_keywords_page.dart`
- `quwoquan_app/lib/ui/settings/pages/my_reports_page.dart`
- `quwoquan_app/lib/ui/settings/pages/settings_about_page.dart`
- `quwoquan_app/lib/ui/settings/pages/settings_account_security_page.dart`
- `quwoquan_app/lib/ui/settings/pages/settings_calls_page.dart`
- `quwoquan_app/lib/ui/settings/pages/settings_dark_mode_page.dart`
- `quwoquan_app/lib/ui/settings/pages/settings_notifications_page.dart`
- `quwoquan_app/lib/ui/settings/pages/settings_page.dart`
- `quwoquan_app/lib/ui/settings/pages/settings_permissions_page.dart`
- `quwoquan_app/lib/ui/settings/pages/settings_privacy_page.dart`
- `quwoquan_app/lib/ui/settings/providers/user_settings_provider.dart`
- `quwoquan_app/lib/ui/settings/widgets/settings_appearance_labels.dart`
- `quwoquan_app/lib/ui/share/forward_external_share_service.dart`
- `quwoquan_app/lib/ui/share/forward_share_models.dart`
- `quwoquan_app/lib/ui/share/widgets/forward_confirm_sheet.dart`
- `quwoquan_app/lib/ui/share/widgets/forward_recipient_picker_route.dart`
- `quwoquan_app/lib/ui/share/widgets/forward_recipient_widgets.dart`
- `quwoquan_app/lib/ui/share/widgets/forward_share_sheet.dart`
- `quwoquan_app/lib/ui/user/models/contact_candidate_vm.dart`
- `quwoquan_app/lib/ui/user/models/profile_mode.dart`
- `quwoquan_app/lib/ui/user/models/profile_tab.dart`
- `quwoquan_app/lib/ui/user/models/share_interaction_models.dart`
- `quwoquan_app/lib/ui/user/pages/add_contact_page.dart`
- `quwoquan_app/lib/ui/user/pages/blocked_users_page.dart`
- `quwoquan_app/lib/ui/user/pages/career_interest_page.dart`
- `quwoquan_app/lib/ui/user/pages/career_interest_page_widgets.dart`
- `quwoquan_app/lib/ui/user/pages/contact_confirm_page.dart`
- `quwoquan_app/lib/ui/user/pages/contact_search_result_page.dart`
- `quwoquan_app/lib/ui/user/pages/edit_profile_page.dart`
- `quwoquan_app/lib/ui/user/pages/edit_profile_page_phone_qr.dart`
- `quwoquan_app/lib/ui/user/pages/edit_profile_page_sections.dart`
- `quwoquan_app/lib/ui/user/pages/legal_document_page.dart`
- `quwoquan_app/lib/ui/user/pages/login_page_auth_flow.dart`
- `quwoquan_app/lib/ui/user/pages/login_page_entry_surfaces.dart`
- `quwoquan_app/lib/ui/user/pages/login_page_form_controls.dart`
- `quwoquan_app/lib/ui/user/pages/login_page_frame.dart`
- `quwoquan_app/lib/ui/user/pages/login_page_models.dart`
- `quwoquan_app/lib/ui/user/pages/login_page_phone_flow.dart`
- `quwoquan_app/lib/ui/user/pages/login_page_social_actions.dart`
- `quwoquan_app/lib/ui/user/pages/login_page_top_bar.dart`
- `quwoquan_app/lib/ui/user/pages/my_footprint_page.dart`
- `quwoquan_app/lib/ui/user/pages/my_intersection_inbox_page.dart`
- `quwoquan_app/lib/ui/user/pages/my_qr_code_page.dart`
- `quwoquan_app/lib/ui/user/pages/persona_management_form_page.dart`
- `quwoquan_app/lib/ui/user/pages/persona_management_page.dart`
- `quwoquan_app/lib/ui/user/pages/phone_contacts_page.dart`
- `quwoquan_app/lib/ui/user/pages/profile_stats_page.dart`
- `quwoquan_app/lib/ui/user/pages/profile_stats_page_widgets.dart`
- `quwoquan_app/lib/ui/user/pages/scan_contact_qr_page.dart`
- `quwoquan_app/lib/ui/user/providers/author_impact_provider.dart`
- `quwoquan_app/lib/ui/user/providers/my_footprint_provider.dart`
- `quwoquan_app/lib/ui/user/providers/my_intersection_inbox_provider.dart`
- `quwoquan_app/lib/ui/user/providers/persona_management_provider.dart`
- `quwoquan_app/lib/ui/user/providers/profile_state_provider.dart`
- `quwoquan_app/lib/ui/user/providers/share_interaction_provider.dart`
- `quwoquan_app/lib/ui/user/services/contact_hash_service.dart`
- `quwoquan_app/lib/ui/user/services/contact_qr_image_analyzer.dart`
- `quwoquan_app/lib/ui/user/services/qr_payload_parser.dart`
- `quwoquan_app/lib/ui/user/utils/profile_comment_detail_route.dart`
- `quwoquan_app/lib/ui/user/widgets/add_contact_entry_card.dart`
- `quwoquan_app/lib/ui/user/widgets/author_impact_card.dart`
- `quwoquan_app/lib/ui/user/widgets/author_impact_evidence.dart`
- `quwoquan_app/lib/ui/user/widgets/contact_candidate_row.dart`
- `quwoquan_app/lib/ui/user/widgets/my_intersection_impact_timeline.dart`
- `quwoquan_app/lib/ui/user/widgets/my_intersection_inbox_card.dart`
- `quwoquan_app/lib/ui/user/widgets/my_intersection_inbox_timeline.dart`
- `quwoquan_app/lib/ui/user/widgets/my_qr_card.dart`
- `quwoquan_app/lib/ui/user/widgets/other_profile_intersection_card.dart`
- `quwoquan_app/lib/ui/user/widgets/profile_action_bar.dart`
- `quwoquan_app/lib/ui/user/widgets/profile_circles_tab.dart`
- `quwoquan_app/lib/ui/user/widgets/profile_completeness_card.dart`
- `quwoquan_app/lib/ui/user/widgets/profile_footprint_tab.dart`
- `quwoquan_app/lib/ui/user/widgets/profile_header.dart`
- `quwoquan_app/lib/ui/user/widgets/profile_interaction_tab_inline_actions.dart`
- `quwoquan_app/lib/ui/user/widgets/profile_interaction_tab_widgets.dart`
- `quwoquan_app/lib/ui/user/widgets/profile_secondary_tab_bar.dart`
- `quwoquan_app/lib/ui/user/widgets/profile_shell.dart`
- `quwoquan_app/lib/ui/user/widgets/profile_shell_builders.dart`
- `quwoquan_app/lib/ui/user/widgets/profile_shell_builders_more.dart`
- `quwoquan_app/lib/ui/user/widgets/profile_shell_builders_parts.dart`
- `quwoquan_app/lib/ui/user/widgets/profile_slogan_card.dart`
- `quwoquan_app/lib/ui/user/widgets/profile_stats_row.dart`
- `quwoquan_app/lib/ui/user/widgets/profile_update_proposal_review_sheet.dart`
- `quwoquan_app/lib/ui/user/widgets/profile_works_tab.dart`
- `quwoquan_app/lib/ui/user/widgets/share_interaction/share_empty_state.dart`
- `quwoquan_app/lib/ui/user/widgets/share_interaction/share_interaction_list.dart`
- `quwoquan_app/lib/ui/user/widgets/share_interaction/share_interaction_row.dart`
- `quwoquan_app/lib/ui/user/widgets/share_interaction/share_target_preview.dart`
- `quwoquan_app/lib/ui/welcome/pages/welcome_screen.dart`
- `quwoquan_app/lib/ui/welcome/welcome_appearance.dart`
- `quwoquan_app/lib/ui/welcome/welcome_motion_timeline.dart`
- `quwoquan_app/lib/ui/welcome/widgets/welcome_brand_cluster.dart`
- `quwoquan_app/lib/ui/welcome/widgets/welcome_flower_mark.dart`
