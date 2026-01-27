/// 组件模块统一导出门面
/// 
/// 提供应用中使用的所有通用组件，包括：
/// - 帖子卡片组件（图片、视频、媒体）
/// - 导航组件（标签导航、底部导航、子标签导航）
/// - 媒体查看器组件（图片、视频、沉浸式）
/// - 评论系统组件
/// - 更多操作弹窗组件
/// - 其他通用组件
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

// ==================== 帖子卡片组件 ====================
export 'image_post_card.dart';
export 'video_post_card.dart';
export 'media_post_card.dart';

// ==================== 导航组件 ====================
export 'tab_navigation.dart';
export 'bottom_navigation.dart';
export 'image_sub_tab_navigation.dart';

// ==================== 媒体查看器组件 ====================
export 'image_viewer.dart';
export 'video_media_viewer.dart';
export 'immersive_media_viewer.dart';
export 'video_player_widget.dart';

// ==================== 内容区域组件 ====================
export 'feed_section.dart';
export 'post_list_section.dart';
export 'stories_section.dart';

// ==================== 用户相关组件 ====================
export 'author_profile.dart';

// ==================== 评论系统组件 ====================
export 'comment_system/comment_viewer.dart';
export 'comment_system/comment_models.dart';
export 'comment_system/comment_viewer_modal.dart';

// ==================== 更多操作弹窗组件 ====================
export 'more_actions_popup/more_action_popup.dart';
export 'more_actions_popup/more_action_types.dart';
export 'more_actions_popup/configs/image_viewer_config.dart';
export 'more_actions_popup/configs/media_post_config.dart';
