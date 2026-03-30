/// [RouteSettings.name] for full-screen pushes that are not registered in [AppRoutePaths].
///
/// Keep in sync with [pageNameFromRouteLocation] in `page_access_log_util.dart`.
abstract final class PageAccessInternalRoutes {
  static const String createMediaPicker = 'page_internal_create_media_picker';
  static const String createMediaPickerConfirm = 'page_internal_create_media_picker_confirm';
  static const String createMediaPickerOneTapMovie = 'page_internal_create_media_picker_one_tap_movie';
  static const String createPageCamera = 'page_internal_create_camera';
  static const String createPageVideoEditor = 'page_internal_create_video_editor';
  static const String createPageImagePreview = 'page_internal_create_image_preview';
  static const String createPagePublishSettings = 'page_internal_create_publish_settings';
  static const String createPagePublishConfirm = 'page_internal_create_publish_confirm';
  static const String createPageArticlePreview = 'page_internal_create_article_preview';
  static const String createPageLocationPicker = 'page_internal_create_location_picker';
  static const String createPagePublishCircleSelect = 'page_internal_create_publish_circle_select';
  static const String createPageHomepageSearch = 'page_internal_create_homepage_search';

  static const String circleShellEditSettings = 'page_internal_circle_edit_settings';

  static const String circleMediaPickerCamera = 'page_internal_circle_media_camera';
  static const String circleMediaPickerGallery = 'page_internal_circle_media_gallery';

  static const String globalSurfaceCircleEditCreate = 'page_internal_global_circle_edit_create';

  static const String publishLocationSearch = 'page_internal_publish_location_search';

  static const String chatInputExpandedDraft = 'page_internal_chat_input_expanded_draft';

  static const String assistantConversationChatSettings = 'page_internal_assistant_conversation_chat_settings';
  static const String assistantConversationReferenceWeb = 'page_internal_assistant_conversation_reference_web';
  static const String assistantConversationDevReplay = 'page_internal_assistant_conversation_dev_replay';

  static const String assistantChatSettingsHistory = 'page_internal_assistant_chat_settings_history';
}
