// ignore_for_file: dangling_library_doc_comments

/// 组件模块统一导出门面
/// 
/// 提供应用中使用的所有通用组件，包括：
/// - 内容卡片组件（图片、视频、媒体基类）
/// - 导航组件（标签导航、子标签导航）
/// - 助理组件（头像、悬浮球）
/// - 输入组件（Emoji 选择器）
/// - 媒体查看器组件（图片、视频、沉浸式）
/// - 评论系统组件
/// - 更多操作弹窗组件
/// 
/// 注意：底部导航（BottomNavigationWidget）已迁移至 lib/app/shell/，
/// 由 MainAppShell 直接引用，不再通过此门面导出。
/// 
/// 使用示例：
/// ```dart
/// import 'package:quwoquan_app/components/components.dart';
/// 
/// ImagePostCard(...)
/// VideoPostCard(...)
/// TabNavigationWidget(...)
/// ```
/// 
/// 依赖关系：
/// - 依赖 core 模块（设计系统、常量、服务等）
/// - 不依赖 features 模块（避免循环依赖）
/// - 不依赖 app 模块（保持组件独立性）

// ==================== 内容卡片组件 ====================
export 'content/image_post_card.dart';
export 'content/video_post_card.dart';
export 'content/media_post_card.dart';

// ==================== 导航组件 ====================
export 'navigation/tab_navigation.dart';
export 'navigation/centered_scrollable_tab_bar.dart';
export 'media/image/navigation/image_sub_tab_navigation.dart';

// ==================== 助理组件 ====================
export 'assistant/assistant_avatar.dart';
export 'assistant/assistant_floating_ball.dart';

// ==================== 输入组件 ====================
export 'input/unified_emoji_picker.dart';
export 'input/customizable_chat_input_bar.dart';

// ==================== 媒体查看器组件 ====================
export 'media/image/viewer/image_viewer.dart';
export 'media/video/viewer/video_media_viewer.dart';
export 'media/image/viewer/immersive_image_viewer.dart';
export 'media/video/viewer/immersive_video_viewer.dart';
export 'media/video/player/video_player_widget.dart';
export 'media/shared/toolbar/media_viewer_toolbar.dart';
export 'media/shared/viewer/media_assistant_panel.dart';
export 'media/shared/viewer/media_caption_widgets.dart';

// ==================== 用户相关组件 ====================
// AuthorProfile 已迁移至 lib/ui/user/pages/author_profile_page.dart

// ==================== 评论系统组件 ====================
export 'comment_system/comment_viewer.dart';
export 'comment_system/comment_models.dart';
export 'comment_system/comment_viewer_modal.dart';

// ==================== 更多操作弹窗组件 ====================
export 'more_actions_popup/more_action_popup.dart';
export 'more_actions_popup/more_action_types.dart';
export 'more_actions_popup/configs/image_viewer_config.dart';
export 'more_actions_popup/configs/media_post_config.dart';
