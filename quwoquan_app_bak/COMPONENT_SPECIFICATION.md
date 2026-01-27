# 趣我圈App 组件功能规格文档

## 📋 文档概述

本文档详细描述了趣我圈App中所有组件的功能规格、接口定义、使用场景和技术实现。组件按照功能模块进行分类，每个组件包含详细的API说明、使用示例和注意事项。

---

## 🏗️ 组件架构概览

### 组件分类
- **核心UI组件**：基础界面元素和布局组件
- **内容展示组件**：媒体内容、用户资料展示
- **交互功能组件**：评论系统、更多操作、导航
- **响应式组件**：适配不同设备的组件
- **工具组件**：通用功能和工具类组件

---

## 📱 核心UI组件

### 1. BottomNavigation - 底部导航栏
**文件位置**：`lib/shared/components/bottom_navigation.dart`

#### 功能描述
提供应用的主要导航入口，包含首页、搜索、创作、聊天、个人中心五个标签页。

#### 核心功能
- ✅ 五个主要功能入口导航
- ✅ 当前页面高亮显示
- ✅ 点击切换页面
- ✅ 响应式设计适配

#### API接口
```dart
class BottomNavigation extends ConsumerWidget {
  final int currentIndex;
  final Function(int) onTap;
  final BuildContext context;
}
```

#### 使用示例
```dart
BottomNavigation(
  currentIndex: _currentIndex,
  onTap: (index) => setState(() => _currentIndex = index),
  context: context,
)
```

---

### 2. TabNavigation - 标签导航
**文件位置**：`lib/shared/components/tab_navigation.dart`

#### 功能描述
提供水平滚动的标签导航，支持动态标签和状态管理。

#### 核心功能
- ✅ 水平滚动标签页
- ✅ 动态标签内容
- ✅ 状态持久化
- ✅ 响应式布局

#### API接口
```dart
class TabNavigation extends ConsumerStatefulWidget {
  final List<String> tabs;
  final int initialIndex;
  final Function(int) onTabChanged;
}
```

---

## 🎨 内容展示组件

### 3. AuthorProfile - 作者主页
**文件位置**：`lib/shared/components/author_profile.dart`

#### 功能描述
完整的用户个人主页组件，展示用户信息、作品集、统计数据等。

#### 核心功能
- ✅ 用户基本信息展示（头像、用户名、简介）
- ✅ 统计数据（作品数、粉丝数、关注数）
- ✅ 作品网格展示（瀑布流布局）
- ✅ 标签页导航（作品、收藏、点赞）
- ✅ 关注/取消关注功能
- ✅ 吸顶头部和按钮
- ✅ 加载状态和错误处理
- ✅ 响应式设计

#### API接口
```dart
class AuthorProfile extends ConsumerStatefulWidget {
  final String username;                    // 用户名
  final VoidCallback onBack;               // 返回回调
  final Function? onPhotoClick;            // 图片点击回调
  final Function(String, bool)? onFollowClick; // 关注回调
  final Function? onCommentsClick;         // 评论回调
  final Function? onLikeClick;             // 点赞回调
  final Function? onSaveClick;             // 收藏回调
  final Function? onShareClick;            // 分享回调
  final bool modal;                        // 弹窗模式
  final bool isCurrentUser;                // 是否当前用户
  final Function(bool)? onStickyHeaderChange; // 吸顶状态回调
}
```

#### 使用示例
```dart
AuthorProfile(
  username: 'user123',
  onBack: () => context.pop(),
  onPhotoClick: (post, index, posts, source, userData) {
    // 处理图片点击
  },
  onFollowClick: (username, isFollowing) {
    // 处理关注操作
  },
  modal: false,
  isCurrentUser: false,
)
```

---

### 4. MediaPostCard - 媒体帖子卡片
**文件位置**：`lib/shared/components/media_post_card.dart`

#### 功能描述
媒体帖子的基础卡片组件，支持图片和视频内容展示。

#### 核心功能
- ✅ 媒体内容展示（图片/视频）
- ✅ 用户信息展示
- ✅ 互动按钮（点赞、评论、分享、收藏）
- ✅ 更多操作菜单
- ✅ 加载状态处理
- ✅ 响应式设计

#### API接口
```dart
abstract class MediaPostCard extends ConsumerStatefulWidget {
  final Map<String, dynamic> post;         // 帖子数据
  final Function(Map<String, dynamic>) onPostTap; // 帖子点击
  final Function(String) onUserTap;        // 用户点击
  final Function(String)? onLike;          // 点赞回调
  final Function(String)? onComment;       // 评论回调
  final Function(String)? onShare;         // 分享回调
  final Function(String)? onBookmark;      // 收藏回调
  final Function(String)? onMore;          // 更多操作回调
}
```

---

### 5. ImagePostCard - 图片帖子卡片
**文件位置**：`lib/shared/components/image_post_card.dart`

#### 功能描述
继承自MediaPostCard，专门处理图片内容的展示。

#### 核心功能
- ✅ 单张图片展示
- ✅ 多张图片指示器
- ✅ 图片点击进入查看器
- ✅ 正方形比例适配
- ✅ 加载状态处理

#### API接口
```dart
class ImagePostCard extends MediaPostCard {
  const ImagePostCard({
    super.key,
    required super.post,
    required super.onPostTap,
    required super.onUserTap,
    // ... 其他参数
  });
}
```

---

### 6. VideoPostCard - 视频帖子卡片
**文件位置**：`lib/shared/components/video_post_card.dart`

#### 功能描述
继承自MediaPostCard，专门处理视频内容的展示。

#### 核心功能
- ✅ 视频播放控制
- ✅ 播放状态管理
- ✅ 视频缩略图
- ✅ 播放按钮覆盖

---

## 🖼️ 媒体查看器组件

### 7. ImmersiveMediaViewer - 沉浸式媒体查看器
**文件位置**：`lib/shared/components/immersive_media_viewer.dart`

#### 功能描述
全屏沉浸式媒体查看器，支持图片和视频的浏览、缩放、播放控制。

#### 核心功能
- ✅ 全屏沉浸式体验
- ✅ 图片缩放和拖拽
- ✅ 视频播放控制
- ✅ 自动隐藏工具栏
- ✅ 滑动切换媒体
- ✅ 作者信息和关注按钮
- ✅ 底部操作栏
- ✅ 手势控制
- ✅ 响应式设计

#### API接口
```dart
class ImmersiveMediaViewer extends ConsumerStatefulWidget {
  final List<Map<String, dynamic>> posts;  // 媒体列表
  final int initialIndex;                  // 初始索引
  final String source;                     // 来源标识
  final VoidCallback? onClose;             // 关闭回调
  final Function(String)? onUserClick;     // 用户点击回调
  final Function(String)? onFollowClick;   // 关注回调
  final Function? onLikeClick;             // 点赞回调
  final Function? onCommentClick;          // 评论回调
  final Function? onShareClick;            // 分享回调
  final Function? onSaveClick;             // 保存回调
}
```

#### 使用示例
```dart
ImmersiveMediaViewer(
  posts: mediaPosts,
  initialIndex: 0,
  source: 'userProfile',
  onClose: () => context.pop(),
  onUserClick: (username) => context.push('/profile/$username'),
  onFollowClick: (userId) => _handleFollow(userId),
)
```

---

### 8. ImageViewer - 图片查看器
**文件位置**：`lib/shared/components/image_viewer.dart`

#### 功能描述
基础的图片查看器组件，支持缩放、拖拽等操作。

#### 核心功能
- ✅ 图片缩放（双指缩放）
- ✅ 图片拖拽
- ✅ 双击缩放
- ✅ 边界检测
- ✅ 加载状态

---

## 💬 评论系统组件

### 9. CommentViewer - 评论查看器
**文件位置**：`lib/shared/components/comment_system/comment_viewer.dart`

#### 功能描述
主要的评论查看器组件，支持模态弹窗和全屏两种显示模式。

#### 核心功能
- ✅ 模态弹窗和全屏两种模式
- ✅ 评论列表展示
- ✅ 评论输入功能
- ✅ 实时数据加载
- ✅ 交互状态管理
- ✅ 错误处理

#### API接口
```dart
class CommentViewer extends ConsumerStatefulWidget {
  final String postId;                     // 帖子ID
  final List<CommentModel> initialComments; // 初始评论
  final CommentConfig config;              // 评论配置
  final CommentDisplayMode displayMode;    // 显示模式
  final CommentModalHeight modalHeight;    // 弹窗高度
  final Function(String)? onCommentAdded;  // 评论添加回调
  final Function(CommentModel)? onCommentLiked; // 评论点赞回调
  final Function(String, String)? onReplyAdded; // 回复添加回调
  final Function(CommentModel)? onUserTapped; // 用户点击回调
  final VoidCallback? onLoadMore;          // 加载更多回调
  final VoidCallback? onClose;             // 关闭回调
}
```

#### 使用示例
```dart
CommentViewer.showModal(
  context: context,
  postId: 'post_123',
  config: CommentConfig(
    title: '评论',
    allowReplies: true,
    maxReplies: 5,
  ),
  modalHeight: CommentModalHeight.third,
  onCommentAdded: (commentId) {
    // 处理新评论
  },
)
```

---

### 10. CommentModal - 评论模态弹窗
**文件位置**：`lib/shared/components/comment_system/comment_modal.dart`

#### 功能描述
可拖拽的评论模态弹窗组件，支持高度调节。

#### 核心功能
- ✅ 可拖拽调整高度
- ✅ 模态弹窗显示
- ✅ 高度范围限制
- ✅ 手势识别
- ✅ 动画效果

#### API接口
```dart
class CommentModal extends StatefulWidget {
  final String title;                      // 标题
  final Widget child;                      // 内容组件
  final CommentModalHeight height;         // 弹窗高度
  final VoidCallback? onClose;             // 关闭回调
  final bool showDragHandle;               // 显示拖拽手柄
}
```

---

### 11. CommentHierarchy - 评论层级显示
**文件位置**：`lib/shared/components/comment_system/comment_hierarchy.dart`

#### 功能描述
评论的层级结构展示组件，支持主评论和回复的展示。

#### 核心功能
- ✅ 主评论展示
- ✅ 回复列表展示
- ✅ 展开/收起功能
- ✅ 楼层编号显示
- ✅ 用户信息展示
- ✅ 交互按钮

#### API接口
```dart
class CommentHierarchy extends StatelessWidget {
  final CommentModel comment;              // 评论数据
  final Function(CommentModel)? onLike;    // 点赞回调
  final Function(CommentModel)? onReply;   // 回复回调
  final Function(CommentModel)? onUserTap; // 用户点击回调
  final bool showAllReplies;               // 显示所有回复
  final Function(bool)? onToggleReplies;   // 切换回复显示
}
```

---

### 12. CommentInput - 评论输入组件
**文件位置**：`lib/shared/components/comment_system/comment_input.dart`

#### 功能描述
评论和回复的输入组件，支持文本输入和提交。

#### 核心功能
- ✅ 文本输入框
- ✅ 提交按钮
- ✅ 输入验证
- ✅ 字数限制
- ✅ 占位符文本

#### API接口
```dart
class CommentInput extends StatefulWidget {
  final String placeholder;                // 占位符
  final Function(String) onSubmit;         // 提交回调
  final int maxLength;                     // 最大长度
  final bool enabled;                      // 是否启用
  final String? initialText;               // 初始文本
}
```

---

### 13. CommentList - 评论列表
**文件位置**：`lib/shared/components/comment_system/comment_list.dart`

#### 功能描述
评论列表的展示组件，支持滚动和加载更多。

#### 核心功能
- ✅ 评论列表展示
- ✅ 滚动加载更多
- ✅ 空状态处理
- ✅ 加载状态指示

---

## ⚙️ 更多操作组件

### 14. MoreActionPopup - 更多操作弹窗
**文件位置**：`lib/shared/components/more_actions_popup/more_action_popup.dart`

#### 功能描述
通用的更多操作弹窗组件，支持动态配置和样式定制。

#### 核心功能
- ✅ 动态配置操作项
- ✅ 水平操作按钮
- ✅ 底部操作列表
- ✅ 权限控制
- ✅ 样式定制
- ✅ 国际化支持
- ✅ 响应式设计

#### API接口
```dart
class MoreActionPopup extends ConsumerWidget {
  final MoreActionConfig config;           // 配置对象
  final bool showDragHandle;               // 显示拖拽手柄
  final bool isScrollControlled;           // 滚动控制
  final VoidCallback? onClose;             // 关闭回调
}

// 静态显示方法
static Future<void> show({
  required BuildContext context,
  required MoreActionConfig config,
  bool showDragHandle = true,
  bool isScrollControlled = true,
})
```

#### 使用示例
```dart
MoreActionPopup.show(
  context: context,
  config: MediaPostMoreActionConfig(
    post: postData,
    onReward: () => _handleReward(),
    onSave: () => _handleSave(),
    onShare: () => _handleShare(),
    onReport: () => _handleReport(),
  ),
)
```

---

### 15. MoreActionConfig - 更多操作配置
**文件位置**：`lib/shared/components/more_actions_popup/more_action_config.dart`

#### 功能描述
更多操作弹窗的配置基类，定义操作项的抽象接口。

#### 核心功能
- ✅ 抽象配置接口
- ✅ 操作项定义
- ✅ 权限控制
- ✅ 样式配置

#### API接口
```dart
abstract class MoreActionConfig {
  String get title;                        // 标题
  List<MoreActionItem> get horizontalItems; // 水平操作项
  List<MoreActionItem> get bottomActions;   // 底部操作项
  MoreActionStyle get style;               // 样式
  bool Function(String)? get permissionChecker; // 权限检查
}

class MoreActionItem {
  final MoreActionType type;               // 操作类型
  final String title;                      // 标题
  final IconData icon;                     // 图标
  final String? subtitle;                  // 副标题
  final VoidCallback? onTap;               // 点击回调
  final bool permission;                   // 权限
  final bool enabled;                      // 是否启用
}
```

---

### 16. 配置类组件

#### MediaPostMoreActionConfig
**文件位置**：`lib/shared/components/more_actions_popup/configs/media_post_config.dart`

媒体帖子专用的更多操作配置，包含打赏、收藏、分享、举报等操作。

#### ImageViewerMoreActionConfig
**文件位置**：`lib/shared/components/more_actions_popup/configs/image_viewer_config.dart`

图片查看器专用的更多操作配置，包含分享、保存、设为壁纸等操作。

#### ProfileMoreActionConfig
**文件位置**：`lib/shared/components/more_actions_popup/configs/profile_config.dart`

用户资料专用的更多操作配置，包含关注、私信、查看资料等操作。

---

## 📊 内容展示组件

### 17. FeedSection - 动态流区域
**文件位置**：`lib/shared/components/feed_section.dart`

#### 功能描述
展示动态流内容的组件，支持分类和滚动加载。

#### 核心功能
- ✅ 动态内容展示
- ✅ 分类筛选
- ✅ 无限滚动
- ✅ 加载状态
- ✅ 空状态处理

---

### 18. StoriesSection - 故事区域
**文件位置**：`lib/shared/components/stories_section.dart`

#### 功能描述
展示用户故事的横向滚动组件。

#### 核心功能
- ✅ 横向滚动故事
- ✅ 故事状态指示
- ✅ 用户头像展示
- ✅ 点击交互

---

### 19. ImageCategoryTabs - 图片分类标签
**文件位置**：`lib/shared/components/image_category_tabs.dart`

#### 功能描述
图片分类的标签导航组件。

#### 核心功能
- ✅ 分类标签展示
- ✅ 标签切换
- ✅ 选中状态指示

---

## 🔧 工具和响应式组件

### 20. CommentResponsive - 评论响应式工具
**文件位置**：`lib/shared/components/comment_system/comment_responsive.dart`

#### 功能描述
评论系统的响应式设计工具类，提供不同设备下的尺寸计算。

#### 核心功能
- ✅ 响应式高度计算
- ✅ 字体大小适配
- ✅ 图标尺寸适配
- ✅ 间距适配

#### API接口
```dart
class CommentResponsive {
  static double getModalHeight(ScreenType screenType, CommentModalHeight height);
  static double getFontSize(ScreenType screenType, FontSizeType type);
  static double getIconSize(ScreenType screenType, IconSizeType type);
  static EdgeInsets getPadding(ScreenType screenType, PaddingType type);
}
```

---

### 21. MoreActionResponsive - 更多操作响应式工具
**文件位置**：`lib/shared/components/more_actions_popup/more_action_responsive.dart`

#### 功能描述
更多操作弹窗的响应式设计工具类。

#### 核心功能
- ✅ 弹窗高度计算
- ✅ 字体大小适配
- ✅ 图标尺寸适配
- ✅ 间距适配

---

### 22. MoreActionUtils - 更多操作工具类
**文件位置**：`lib/shared/components/more_actions_popup/more_action_utils.dart`

#### 功能描述
更多操作功能的工具类，提供通用的操作方法。

#### 核心功能
- ✅ 权限检查
- ✅ Toast提示
- ✅ 确认对话框
- ✅ 剪贴板操作
- ✅ 分享功能
- ✅ 网络检查
- ✅ 时间格式化
- ✅ 数量格式化

---

## 🎨 样式和主题组件

### 23. MoreActionStyle - 更多操作样式
**文件位置**：`lib/shared/components/more_actions_popup/more_action_style.dart`

#### 功能描述
更多操作弹窗的样式定义类。

#### 核心功能
- ✅ 颜色主题
- ✅ 字体样式
- ✅ 边框圆角
- ✅ 明暗主题适配

---

### 24. SharedWidget - 共享组件
**文件位置**：`lib/shared/components/shared_widget.dart`

#### 功能描述
通用的共享组件集合。

#### 核心功能
- ✅ 通用UI元素
- ✅ 可复用组件
- ✅ 标准样式

---

## 📱 页面组件

### 25. ImmersiveMediaViewerPage - 沉浸式媒体查看器页面
**文件位置**：`lib/features/media_viewer/pages/immersive_media_viewer_page.dart`

#### 功能描述
沉浸式媒体查看器的页面包装器。

#### 核心功能
- ✅ 页面路由管理
- ✅ 数据加载
- ✅ 状态管理
- ✅ 导航处理

---

## 🔄 状态管理组件

### 26. MediaViewerState - 媒体查看器状态
**文件位置**：`lib/shared/components/media_viewer/media_viewer_state.dart`

#### 功能描述
媒体查看器的状态管理类。

#### 核心功能
- ✅ 播放状态管理
- ✅ 索引状态管理
- ✅ 控制栏状态管理

---

### 27. TabNavigationState - 标签导航状态
**文件位置**：`lib/shared/components/tab_navigation/tab_navigation_state.dart`

#### 功能描述
标签导航的状态管理类。

#### 核心功能
- ✅ 标签状态管理
- ✅ 索引状态管理
- ✅ 持久化状态

---

## 📋 数据模型组件

### 28. CommentModel - 评论数据模型
**文件位置**：`lib/shared/components/comment_system/comment_models.dart`

#### 功能描述
评论系统的数据模型定义。

#### 核心功能
- ✅ 评论数据结构
- ✅ 用户信息
- ✅ 交互状态
- ✅ 楼层编号

#### API接口
```dart
class CommentModel {
  final String id;                         // 评论ID
  final String postId;                     // 帖子ID
  final String userId;                     // 用户ID
  final String username;                   // 用户名
  final String? displayName;               // 显示名称
  final String? avatar;                    // 头像URL
  final String content;                    // 评论内容
  final DateTime createdAt;                // 创建时间
  final List<CommentModel> replies;        // 回复列表
  final int likeCount;                     // 点赞数
  final bool isLiked;                      // 是否已点赞
  final int floorNumber;                   // 楼层号
  final String? location;                  // 位置
  final String? deviceInfo;                // 设备信息
  final String? userRole;                  // 用户角色
}
```

---

## 🎯 组件使用指南

### 通用使用原则

1. **响应式设计**：所有组件都支持响应式设计，自动适配不同设备
2. **主题适配**：组件支持明暗主题自动切换
3. **国际化**：所有文本都使用国际化常量，支持多语言
4. **权限控制**：涉及用户操作的组件都支持权限检查
5. **错误处理**：所有组件都包含完善的错误处理机制

### 组件组合使用

#### 典型的帖子展示组合
```dart
// 帖子卡片 + 更多操作
ImagePostCard(
  post: postData,
  onPostTap: (post) => _showMediaViewer(post),
  onUserTap: (username) => _showUserProfile(username),
  onMore: (postId) => _showMoreActions(postId),
)

// 更多操作弹窗
MoreActionPopup.show(
  context: context,
  config: MediaPostMoreActionConfig(
    post: postData,
    onReward: _handleReward,
    onSave: _handleSave,
    onShare: _handleShare,
  ),
)
```

#### 典型的评论系统组合
```dart
// 评论查看器
CommentViewer.showModal(
  context: context,
  postId: postId,
  config: CommentConfig(
    title: '评论',
    allowReplies: true,
  ),
  onCommentAdded: _handleNewComment,
)
```

---

## 🔧 技术实现细节

### 状态管理
- 使用Riverpod进行状态管理
- 支持Provider和Consumer模式
- 异步状态处理

### 响应式设计
- 基于ScreenUtil的屏幕适配
- 支持不同设备类型（手机、平板、桌面）
- 动态尺寸计算

### 导航管理
- 使用GoRouter进行路由管理
- 支持路由参数传递
- 导航栈安全处理

### 数据服务
- 抽象服务接口
- Mock数据支持
- 真实API集成准备

---

## 📈 组件扩展指南

### 添加新组件
1. 在`lib/shared/components/`目录下创建新组件文件
2. 遵循现有的命名和结构规范
3. 实现响应式设计
4. 添加必要的文档和注释
5. 更新本文档

### 扩展现有组件
1. 保持向后兼容性
2. 添加新功能时使用可选参数
3. 更新API文档
4. 添加使用示例

---

## 🐛 已知问题和限制

### 当前限制
1. 部分组件仍在开发中，功能可能不完整
2. 某些高级功能需要后端API支持
3. 部分组件的性能优化还在进行中

### 计划改进
1. 增加更多的动画效果
2. 优化组件的性能
3. 增加更多的自定义选项
4. 完善错误处理机制

---

## 📚 相关文档

- [编码规范](04_CODING_RULES.md)
- [设计系统](03_DESIGN_RULES.md)
- [API设计规范](04.2_API_DESIGN_RULES.md)
- [测试规范](05_TESTING_RULES.md)

---

*本文档会随着组件的发展持续更新，请关注最新版本。*
