import 'package:flutter/foundation.dart';

/// Stable [Key] constants for widget and integration tests.
///
/// Production widgets use these keys on key interaction elements so tests
/// can locate them reliably without depending on i18n text strings.
///
/// 使用方式：
///   生产代码：`key: TestKeys.likeButton`
///   flutter_test：`find.byKey(TestKeys.likeButton)`
///   Patrol：`$(TestKeys.likeButton).tap()`
class TestKeys {
  TestKeys._();

  // ── Pages ───────────────────────────────────────────────────────────
  static const discoveryPage = ValueKey<String>('discovery_page');
  static const discoveryCreateButton = ValueKey<String>(
    'discovery_create_button',
  );
  static const createPage = ValueKey<String>('create_page');
  static const assistantTabPage = ValueKey<String>('assistant_tab_page');
  static const assistantDialogPage = ValueKey<String>('assistant_dialog_page');
  static const fullscreenModalSurface = ValueKey<String>(
    'fullscreen_modal_surface',
  );
  static const globalSearchLauncherButton = ValueKey<String>(
    'global_search_launcher_button',
  );
  static const globalSearchObjectSelector = ValueKey<String>(
    'global_search_object_selector',
  );
  static const searchContentSelectorButton = ValueKey<String>(
    'search_content_selector_button',
  );
  static const searchContentSheet = ValueKey<String>('search_content_sheet');
  static const searchContentSheetDoneButton = ValueKey<String>(
    'search_content_sheet_done_button',
  );
  static const searchContentSheetResetButton = ValueKey<String>(
    'search_content_sheet_reset_button',
  );
  static const searchContentArticleToggle = ValueKey<String>(
    'search_content_article_toggle',
  );
  static const searchContentImageToggle = ValueKey<String>(
    'search_content_image_toggle',
  );
  static const searchContentVideoToggle = ValueKey<String>(
    'search_content_video_toggle',
  );
  static const searchContentMomentToggle = ValueKey<String>(
    'search_content_moment_toggle',
  );
  static const globalSearchScopeRail = ValueKey<String>(
    'global_search_scope_rail',
  );
  static const globalSearchContentTypeRail = ValueKey<String>(
    'global_search_content_type_rail',
  );
  static const searchScopeAllChip = ValueKey<String>('search_scope_all_chip');
  static const searchScopeContactsChip = ValueKey<String>(
    'search_scope_contacts_chip',
  );
  static const searchScopeChatRecordsChip = ValueKey<String>(
    'search_scope_chat_records_chip',
  );
  static const searchScopeDirectChatChip = ValueKey<String>(
    'search_scope_direct_chat_chip',
  );
  static const searchScopeGroupChatChip = ValueKey<String>(
    'search_scope_group_chat_chip',
  );
  static const searchScopeCirclesChip = ValueKey<String>(
    'search_scope_circles_chip',
  );
  static const searchScopeContentChip = ValueKey<String>(
    'search_scope_content_chip',
  );
  static const searchContentTypeAllChip = ValueKey<String>(
    'search_content_type_all_chip',
  );
  static const searchContentTypeArticleChip = ValueKey<String>(
    'search_content_type_article_chip',
  );
  static const searchContentTypeImageChip = ValueKey<String>(
    'search_content_type_image_chip',
  );
  static const searchContentTypeVideoChip = ValueKey<String>(
    'search_content_type_video_chip',
  );
  static const searchContentTypeMomentChip = ValueKey<String>(
    'search_content_type_moment_chip',
  );
  static const searchObjectSheet = ValueKey<String>('search_object_sheet');
  static const searchObjectResetButton = ValueKey<String>(
    'search_object_reset_button',
  );
  static const searchObjectDoneButton = ValueKey<String>(
    'search_object_done_button',
  );
  static const searchHistoryExpandButton = ValueKey<String>(
    'search_history_expand_button',
  );
  static const searchHistoryManageButton = ValueKey<String>(
    'search_history_manage_button',
  );
  static const searchHistoryClearButton = ValueKey<String>(
    'search_history_clear_button',
  );
  static const searchHistoryDoneButton = ValueKey<String>(
    'search_history_done_button',
  );
  static const modalBottomSheetPanel = ValueKey<String>(
    'modal_bottom_sheet_panel',
  );

  // ── Feed / Grid ──────────────────────────────────────────────────────
  static const photoFeedGrid = ValueKey<String>('photo_feed_grid');
  static const videoFeedList = ValueKey<String>('video_feed_list');

  // ── Post Card ────────────────────────────────────────────────────────
  static const photoPostCard = ValueKey<String>('photo_post_card');
  static const videoPostCard = ValueKey<String>('video_post_card');
  static const articlePostCard = ValueKey<String>('article_post_card');
  static const momentPostCard = ValueKey<String>('moment_post_card');

  // ── Video ────────────────────────────────────────────────────────────
  static const videoDurationText = ValueKey<String>('video_duration_text');

  // ── Post Interaction ────────────────────────────────────────────────
  static const likeButton = ValueKey<String>('like_button');
  static const likeCountText = ValueKey<String>('like_count_text');
  static const favoriteButton = ValueKey<String>('favorite_button');
  static const favoriteCountText = ValueKey<String>('favorite_count_text');
  static const commentButton = ValueKey<String>('comment_button');
  static const commentCountText = ValueKey<String>('comment_count_text');
  static const shareButton = ValueKey<String>('share_button');

  // ── Comment Input ───────────────────────────────────────────────────
  static const commentInputBar = ValueKey<String>('comment_input_bar');
  static const submitCommentButton = ValueKey<String>('submit_comment_button');
  static const commentTextField = ValueKey<String>('comment_text_field');
  static const assistantChatInputField = ValueKey<String>(
    'assistant_chat_input_field',
  );
  static const assistantSendButton = ValueKey<String>('assistant_send_button');
  static const chatInputVoiceToggleButton = ValueKey<String>(
    'chat_input_voice_toggle_button',
  );
  static const chatInputEmojiToggleButton = ValueKey<String>(
    'chat_input_emoji_toggle_button',
  );
  static const chatInputMoreButton = ValueKey<String>('chat_input_more_button');
  static const chatInputExpandButton = ValueKey<String>(
    'chat_input_expand_button',
  );
  static const chatInputCollapseButton = ValueKey<String>(
    'chat_input_collapse_button',
  );
  static const chatInputExpandedEmojiToggleButton = ValueKey<String>(
    'chat_input_expanded_emoji_toggle_button',
  );
  static const assistantProcessHeader = ValueKey<String>(
    'assistant_process_header',
  );

  // ── Assistant Internal Tabs ─────────────────────────────────────────
  static const assistantScheduleTab = ValueKey<String>(
    'assistant_schedule_tab',
  );
  static const assistantDialogTab = ValueKey<String>('assistant_dialog_tab');
  static const assistantSkillsTab = ValueKey<String>('assistant_skills_tab');

  // ── Author / Profile ────────────────────────────────────────────────
  static const authorAvatar = ValueKey<String>('author_avatar');
  static const authorName = ValueKey<String>('author_name');

  // ── Error / Toast ───────────────────────────────────────────────────
  static const errorToast = ValueKey<String>('error_toast');
  static const retryButton = ValueKey<String>('retry_button');

  // ── Create Flow ─────────────────────────────────────────────────────
  static const createActionGallery = ValueKey<String>('create_action_gallery');
  static const createActionWrite = ValueKey<String>('create_action_write');
  static const createActionCapture = ValueKey<String>('create_action_capture');
  static const createIdentityMoment = ValueKey<String>(
    'create_identity_moment',
  );
  static const createIdentityWork = ValueKey<String>('create_identity_work');
  static const createWorkFormatImage = ValueKey<String>(
    'create_work_format_image',
  );
  static const createWorkFormatVideo = ValueKey<String>(
    'create_work_format_video',
  );
  static const createWorkFormatNote = ValueKey<String>(
    'create_work_format_note',
  );
  static const createPublishButton = ValueKey<String>('create_publish_button');
  static const createDraftsButton = ValueKey<String>('create_drafts_button');
  static const createCloseButton = ValueKey<String>('create_close_button');
  static const createTitleToggle = ValueKey<String>('create_title_toggle');
  static const createTitleInput = ValueKey<String>('create_title_input');
  static const createBodyInput = ValueKey<String>('create_body_input');
  static const createMediaAddButton = ValueKey<String>(
    'create_media_add_button',
  );
  static const createPublishConfirmSheet = ValueKey<String>(
    'create_publish_confirm_sheet',
  );
  static const createPublishConfirmButton = ValueKey<String>(
    'create_publish_confirm_button',
  );
  static const homepagePickerPage = ValueKey<String>('homepage_picker_page');
  static const homepagePickerSearchField = ValueKey<String>(
    'homepage_picker_search_field',
  );
  static const homepagePickerCancelButton = ValueKey<String>(
    'homepage_picker_cancel_button',
  );
  static const homepagePickerConfirmButton = ValueKey<String>(
    'homepage_picker_confirm_button',
  );
  static const homepagePickerClearSelectionTile = ValueKey<String>(
    'homepage_picker_clear_selection_tile',
  );
  static const homepagePickerResultTile = ValueKey<String>(
    'homepage_picker_result_tile',
  );
  static const homepagePickerSuggestButton = ValueKey<String>(
    'homepage_picker_suggest_button',
  );
  static const suggestHomepagePage = ValueKey<String>('suggest_homepage_page');
  static const suggestHomepageSubmitButton = ValueKey<String>(
    'suggest_homepage_submit_button',
  );
  static const publishCircleSelectPage = ValueKey<String>(
    'publish_circle_select_page',
  );
  static const publishCircleCancelButton = ValueKey<String>(
    'publish_circle_cancel_button',
  );
  static const publishCircleConfirmButton = ValueKey<String>(
    'publish_circle_confirm_button',
  );
  static const homepageDetailPage = ValueKey<String>('homepage_detail_page');
  static const homepageDetailAttachButton = ValueKey<String>(
    'homepage_detail_attach_button',
  );
  static const createMediaModeAddImage = ValueKey<String>(
    'create_media_mode_add_image',
  );
  static const createMediaModeAddVideo = ValueKey<String>(
    'create_media_mode_add_video',
  );
  static const createMediaRemoveButton = ValueKey<String>(
    'create_media_remove_button',
  );
  static const createSettingsSummary = ValueKey<String>(
    'create_settings_summary',
  );
  static const createSettingsPage = ValueKey<String>('create_settings_page');
  static const createTitleHint = ValueKey<String>('create_title_hint');
  static const createSaveAndExitButton = ValueKey<String>(
    'create_save_and_exit_button',
  );
  static const createDiscardAndExitButton = ValueKey<String>(
    'create_discard_and_exit_button',
  );
  static const createMomentInput = ValueKey<String>('create_moment_input');
  static const createPhotoTitleInput = ValueKey<String>(
    'create_photo_title_input',
  );
  static const createPhotoBodyInput = ValueKey<String>(
    'create_photo_body_input',
  );
  static const createVideoTitleInput = ValueKey<String>(
    'create_video_title_input',
  );
  static const createVideoBodyInput = ValueKey<String>(
    'create_video_body_input',
  );
  static const createArticleTitleInput = ValueKey<String>(
    'create_article_title_input',
  );
  static const createArticleBodyInput = ValueKey<String>(
    'create_article_body_input',
  );
  static const createAccessoryBar = ValueKey<String>('create_accessory_bar');
  static const createAccessoryPanel = ValueKey<String>(
    'create_accessory_panel',
  );
  static const createAccessoryImageButton = ValueKey<String>(
    'create_accessory_image_button',
  );
  static const createAccessoryEmojiButton = ValueKey<String>(
    'create_accessory_emoji_button',
  );
  static const createAccessoryStructureButton = ValueKey<String>(
    'create_accessory_structure_button',
  );
  static const createAccessoryTemplateButton = ValueKey<String>(
    'create_accessory_template_button',
  );
  static const createAccessoryFontButton = ValueKey<String>(
    'create_accessory_font_button',
  );
  static const createEmojiPanel = ValueKey<String>('create_emoji_panel');
  static const createStructurePanel = ValueKey<String>(
    'create_structure_panel',
  );
  static const createTemplatePanel = ValueKey<String>('create_template_panel');
  static const createFontPanel = ValueKey<String>('create_font_panel');
  static const createArticleCoverNoneOption = ValueKey<String>(
    'create_article_cover_none_option',
  );

  // ── Article Reader / Preview ─────────────────────────────────────────
  static const articlePageCurlLayer = ValueKey<String>(
    'article_page_curl_layer',
  );
  static const articleBookStylePager = ValueKey<String>(
    'article_book_style_pager',
  );
  static const articlePageCurlHotzoneTopLeft = ValueKey<String>(
    'article_page_curl_hotzone_top_left',
  );
  static const articlePageCurlHotzoneTopRight = ValueKey<String>(
    'article_page_curl_hotzone_top_right',
  );
  static const articlePageCurlHotzoneBottomLeft = ValueKey<String>(
    'article_page_curl_hotzone_bottom_left',
  );
  static const articlePageCurlHotzoneBottomRight = ValueKey<String>(
    'article_page_curl_hotzone_bottom_right',
  );
  static const articlePreviewCoverStrip = ValueKey<String>(
    'article_preview_cover_strip',
  );
}
