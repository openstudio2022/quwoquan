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
}
