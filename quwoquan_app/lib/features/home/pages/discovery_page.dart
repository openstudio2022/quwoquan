import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/components/assistant_floating_ball.dart';
import 'package:quwoquan_app/components/tab_navigation.dart';

/// 发现页
///
/// 1:1 复制自 趣我圈2026/src/components/Home.tsx → DiscoveryFeed.tsx
/// Tab: 微趣(moment)/美图(photo)/视频(video)/文章(article)，与 CATEGORIES 一致
class DiscoveryPage extends ConsumerStatefulWidget {
  const DiscoveryPage({super.key});

  @override
  ConsumerState<DiscoveryPage> createState() => _DiscoveryPageState();
}

class _DiscoveryPageState extends ConsumerState<DiscoveryPage>
    with TickerProviderStateMixin, AutomaticKeepAliveClientMixin {
  /// 与 DiscoveryFeed.tsx activeType 一致
  String _activeType = 'moment';
  /// 与 DiscoveryFeed.tsx isUIVisible 一致，视频模式下可切换
  bool _isUIVisible = true;
  /// 保存 notifier 供 dispose 回调使用，避免 dispose 后使用 ref
  VideoForceDarkNotifier? _videoForceDarkNotifier;

  @override
  bool get wantKeepAlive => true;

  /// 与 DiscoveryFeed.tsx CATEGORIES 完全一致
  static const List<Map<String, String>> _categories = [
    {'id': 'moment', 'label': UITextConstants.discoveryTabMoment},
    {'id': 'photo', 'label': UITextConstants.discoveryTabPhoto},
    {'id': 'video', 'label': UITextConstants.discoveryTabVideo},
    {'id': 'article', 'label': UITextConstants.discoveryTabArticle},
  ];

  bool get _isVideoMode => _activeType == 'video';

  List<String> get _primaryTabIds =>
      _categories.map((category) => category['id']!).toList(growable: false);

  void _setActiveType(String id) {
    setState(() => _activeType = id);
    _applyVideoForceDark();
  }

  void _switchPrimaryByDelta(int delta) {
    final ids = _primaryTabIds;
    final currentIndex = ids.indexOf(_activeType);
    if (currentIndex < 0) return;
    final nextIndex = currentIndex + delta;
    if (nextIndex < 0 || nextIndex >= ids.length) {
      HapticFeedback.selectionClick();
      return;
    }
    _setActiveType(ids[nextIndex]);
  }

  void _onPrimaryDragEnd(DragEndDetails details) {
    final velocity = details.primaryVelocity ?? 0;
    if (velocity.abs() < 220) return;
    _switchPrimaryByDelta(velocity < 0 ? 1 : -1);
  }

  void _onTheaterModeChange(bool isHidden) {
    // TODO: 与 App.tsx isBottomNavHidden 一致，需 Shell 提供 bottomNavVisibilityProvider
  }

  /// 在非 build/initState/dispose 中更新，避免 “modify provider while building”
  void _applyVideoForceDark() {
    ref.read(videoForceDarkProvider.notifier).setForceDark(_isVideoMode);
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _videoForceDarkNotifier = ref.read(videoForceDarkProvider.notifier);
      _applyVideoForceDark();
    });
  }

  @override
  void dispose() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _videoForceDarkNotifier?.setForceDark(false);
    });
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final isDark = ref.watch(effectiveIsDarkProvider);
    if (_isVideoMode && !_isUIVisible) _onTheaterModeChange(true);
    if (!_isVideoMode) _onTheaterModeChange(false);

    return Scaffold(
      backgroundColor: _isVideoMode
          ? Colors.black
          : AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
      body: Stack(
        children: [
          if (_isVideoMode)
            _buildVideoImmersionView(isDark)
          else
            Column(
              children: [
                _buildHeader(isDark),
                Expanded(child: _buildContent(isDark)),
              ],
            ),
          AssistantFloatingBall(onTap: () => context.push('/assistant')),
        ],
      ),
    );
  }

  /// 发现页主导航：与圈子/首页复用同一 Tab 组件与字级。
  Widget _buildHeader(bool isDark) {
    final tabs = _categories
        .map((cat) => TabItem(id: cat['id']!, label: cat['label']!))
        .toList(growable: false);

    return Container(
      decoration: BoxDecoration(
        color: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
      ),
      child: SafeArea(
        bottom: false,
        child: TabNavigationWidget(
          activeTab: _activeType,
          isDark: isDark,
          tabs: tabs,
          mode: TabNavigationMode.compactPill,
          onTabChange: _setActiveType,
          onHorizontalDragEnd: _onPrimaryDragEnd,
          trailingActions: [
            IconButton(
              icon: Icon(
                Icons.search,
                size: AppSpacing.iconMedium,
                color: AppColorsFunctional.getColor(
                  isDark,
                  ColorType.foregroundSecondary,
                ),
              ),
              onPressed: () {},
              style: IconButton.styleFrom(
                minimumSize: Size.square(AppSpacing.iconButtonMinSizeSm),
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// 1:1 复制 VideoImmersionView.tsx：顶栏（返回/胶囊 Tab/搜索）、竖滑视频列表、点击切换 UI、下拉退出
  Widget _buildVideoImmersionView(bool isDark) {
    final videos = ref.watch(appContentRepositoryProvider).discoveryVideoData;
    return _VideoImmersionView(
      categories: _categories,
      activeTab: _activeType,
      videos: videos,
      isUIVisible: _isUIVisible,
      onBack: () {
        setState(() => _activeType = 'moment');
        _applyVideoForceDark();
      },
      onTabChange: (id) {
        setState(() => _activeType = id);
        _applyVideoForceDark();
      },
      onToggleUI: () {
        setState(() => _isUIVisible = !_isUIVisible);
        _onTheaterModeChange(!_isUIVisible);
      },
      onUserClick: (userId) => context.push('/user/$userId'),
    );
  }

  /// 1:1 复制 DiscoveryFeed.tsx 内容区：moment/article→RecommendFeed；photo→MasonryLayoutEngine（video 由 _buildVideoImmersionView 全屏展示）
  Widget _buildContent(bool isDark) {
    switch (_activeType) {
      case 'video':
        return const SizedBox.shrink(); // 视频模式由 _buildVideoImmersionView 独占
      case 'moment':
        return _buildMomentContent(isDark);
      case 'article':
        return _buildArticleContent(isDark);
      case 'photo':
        return _buildPhotoContent(isDark);
      default:
        return _buildMomentContent(isDark);
    }
  }

  /// 微趣流：1:1 使用 DiscoveryFeed.tsx activeType===moment 的 discoveryData，RecommendFeed 等价
  Widget _buildMomentContent(bool isDark) {
    final items = ref.watch(appContentRepositoryProvider).discoveryMomentData;
    return ListView.builder(
      padding: EdgeInsets.only(
        bottom: MediaQuery.of(context).padding.bottom +
            AppSpacing.bottomNavHeight +
            AppSpacing.interGroupMd,
      ),
      itemCount: items.length + 1,
      itemBuilder: (context, index) {
        if (index == items.length) {
          return Padding(
            padding: EdgeInsets.symmetric(vertical: AppSpacing.interGroupXl),
            child: Center(
              child: Text(
                UITextConstants.discoveryEndHint,
                style: TextStyle(
                  fontSize: AppTypography.sm,
                  color: AppColorsFunctional.getColor(
                    isDark,
                    ColorType.foregroundSecondary,
                  ),
                ),
              ),
            ),
          );
        }
        return _MomentPostCard(
          item: items[index],
          isDark: isDark,
          onUserTap: (id) => context.push('/user/$id'),
          onPostTap: (post, i) => _onPostTap(post, i),
        );
      },
    );
  }

  /// 文章流：1:1 使用 DiscoveryFeed.tsx activeType===article 的 discoveryData
  Widget _buildArticleContent(bool isDark) {
    final items = ref.watch(appContentRepositoryProvider).discoveryArticleData;
    return ListView.builder(
      padding: EdgeInsets.only(
        bottom: MediaQuery.of(context).padding.bottom +
            AppSpacing.bottomNavHeight +
            AppSpacing.interGroupMd,
      ),
      itemCount: items.length + 1,
      itemBuilder: (context, index) {
        if (index == items.length) {
          return Padding(
            padding: EdgeInsets.symmetric(vertical: AppSpacing.interGroupXl),
            child: Center(
              child: Text(
                UITextConstants.discoveryEndHint,
                style: TextStyle(
                  fontSize: AppTypography.sm,
                  color: AppColorsFunctional.getColor(
                    isDark,
                    ColorType.foregroundSecondary,
                  ),
                ),
              ),
            ),
          );
        }
        final article = items[index];
        return _ArticleCardPlaceholder(
          article: article,
          isDark: isDark,
          onTap: () => context.push('/article/${article['id']}'),
          onUserTap: () => context.push('/user/${article['author']?['name'] ?? ''}'),
        );
      },
    );
  }

  /// 美图流：1:1 使用 DiscoveryFeed.tsx photo 的 discoveryData，MasonryLayoutEngine + DiscoveryItem 等价
  Widget _buildPhotoContent(bool isDark) {
    final items = ref.watch(appContentRepositoryProvider).discoveryPhotoData;
    return GridView.builder(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.containerSm,
        AppSpacing.containerSm,
        AppSpacing.containerSm,
        MediaQuery.of(context).padding.bottom +
            AppSpacing.bottomNavHeight +
            AppSpacing.interGroupLg,
      ),
      gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 2,
        mainAxisSpacing: AppSpacing.interGroupSm,
        crossAxisSpacing: AppSpacing.interGroupSm,
        childAspectRatio: 0.75,
      ),
      itemCount: items.length,
      itemBuilder: (context, index) {
        final d = items[index];
        return _DiscoveryItemCard(
          post: d,
          onTap: () => _onPostTap(d, 0),
        );
      },
    );
  }

  void _onPostTap(dynamic post, int mediaIndex) {
    final type = post['type'] as String? ?? 'image';
    if (type == 'article') {
      context.push('/article/${post['id'] ?? ''}');
      return;
    }
    context.push('/media-viewer/images/0'); // TODO: 传 post 与 index
  }
}

/// 微趣卡片：1:1 复制 MomentPost.tsx 结构（简化版，后续补全转发引用、九宫格等）
class _MomentPostCard extends StatelessWidget {
  final Map<String, dynamic> item;
  final bool isDark;
  final void Function(String) onUserTap;
  final void Function(dynamic, int) onPostTap;

  const _MomentPostCard({
    required this.item,
    required this.isDark,
    required this.onUserTap,
    required this.onPostTap,
  });

  @override
  Widget build(BuildContext context) {
    final user = item['user'] as Map<String, dynamic>? ?? {};
    final fg = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final muted = AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    final borderColor = AppColorsFunctional.getColor(isDark, ColorType.borderPrimary);

    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.md.w,
        vertical: AppSpacing.md.h,
      ),
      decoration: BoxDecoration(
        color: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
        border: Border(bottom: BorderSide(color: borderColor)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              GestureDetector(
                onTap: () => onUserTap(user['id']?.toString() ?? user['name']?.toString() ?? ''),
                child: CircleAvatar(
                  radius: AppSpacing.avatarUserMd / 2,
                  backgroundImage: NetworkImage(
                    user['avatar']?.toString() ?? 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=100',
                  ),
                ),
              ),
              SizedBox(width: AppSpacing.sm.w),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Text(
                          user['name']?.toString() ?? '',
                          style: TextStyle(
                            fontSize: AppTypography.base,
                            fontWeight: AppTypography.medium,
                            color: fg,
                          ),
                        ),
                        if (user['badge'] != null) ...[
                          SizedBox(width: AppSpacing.intraGroupXs),
                          Container(
                            padding: EdgeInsets.symmetric(
                              horizontal: AppSpacing.intraGroupXs,
                              vertical: AppSpacing.intraGroupXs / 2,
                            ),
                            decoration: BoxDecoration(
                              color: AppColors.warning,
                              borderRadius: BorderRadius.circular(
                                AppSpacing.smallBorderRadius / 2,
                              ),
                            ),
                            child: Text(
                              'V${user['badge']}',
                              style: TextStyle(
                                fontSize: AppTypography.xs,
                                fontWeight: AppTypography.bold,
                                color: Colors.white,
                              ),
                            ),
                          ),
                        ],
                      ],
                    ),
                    SizedBox(height: AppSpacing.intraGroupXs / 2),
                    Text(
                      item['timeAgo']?.toString() ?? '',
                      style: TextStyle(
                        fontSize: AppTypography.sm,
                        color: muted,
                      ),
                    ),
                    if (item['source'] != null)
                      Text(
                        item['source'].toString(),
                        style: TextStyle(
                          fontSize: AppTypography.xs,
                          color: muted,
                        ),
                      ),
                  ],
                ),
              ),
            ],
          ),
          SizedBox(height: AppSpacing.interGroupXs),
          Text(
            item['content']?.toString() ?? '',
            style: TextStyle(
              fontSize: AppTypography.lg,
              color: fg,
              height: 1.4,
            ),
            maxLines: 10,
            overflow: TextOverflow.ellipsis,
          ),
          if (item['quotedPost'] != null) ...[
            SizedBox(height: AppSpacing.interGroupXs),
            Container(
              padding: EdgeInsets.all(AppSpacing.sm.w),
              decoration: BoxDecoration(
                color: AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary),
                borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '@${(item['quotedPost'] as Map)['user']}',
                    style: TextStyle(
                      fontSize: AppTypography.sm,
                      fontWeight: AppTypography.medium,
                      color: fg,
                    ),
                  ),
                  SizedBox(height: AppSpacing.intraGroupXs),
                  Text(
                    (item['quotedPost'] as Map)['content']?.toString() ?? '',
                    style: TextStyle(
                      fontSize: AppTypography.sm,
                      color: muted,
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ),
          ],
          if (item['media'] != null && (item['media'] as List).isNotEmpty) ...[
            SizedBox(height: AppSpacing.interGroupXs),
            GestureDetector(
              onTap: () => onPostTap(item, 0),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
                child: AspectRatio(
                  aspectRatio: 4 / 3,
                  child: Image.network(
                    (item['media'] as List).first['url']?.toString() ??
                        (item['media'] as List).first['thumbnail']?.toString() ??
                        '',
                    width: double.infinity,
                    fit: BoxFit.cover,
                    errorBuilder: (context, error, stackTrace) => Container(
                      color: borderColor,
                      child: const Icon(Icons.broken_image_outlined),
                    ),
                  ),
                ),
              ),
            ),
          ],
          SizedBox(height: AppSpacing.interGroupSm),
          Row(
            children: [
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  _actionChip(CupertinoIcons.heart, '${item['likes'] ?? 0}', isDark),
                  SizedBox(width: AppSpacing.intraGroupMd),
                  _actionChipWidget(
                    AppStarIcon(
                      size: AppSpacing.iconMedium,
                      color: AppColorsFunctional.getColor(
                        isDark,
                        ColorType.foregroundSecondary,
                      ),
                    ),
                    '${item['bookmarks'] ?? item['saves'] ?? 0}',
                    isDark,
                  ),
                  SizedBox(width: AppSpacing.intraGroupMd),
                  _actionChipWidget(
                    AppBubbleIcon(
                      size: AppSpacing.iconMedium,
                      color: AppColorsFunctional.getColor(
                        isDark,
                        ColorType.foregroundSecondary,
                      ),
                    ),
                    '${item['comments'] ?? 0}',
                    isDark,
                  ),
                ],
              ),
              const Spacer(),
              _actionChip(CupertinoIcons.arrowshape_turn_up_right, '${item['shares'] ?? 0}', isDark),
            ],
          ),
        ],
      ),
    );
  }

  Widget _actionChip(IconData icon, String count, bool isDark) {
    final muted = AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: AppSpacing.iconMedium, color: muted),
        SizedBox(width: AppSpacing.intraGroupXs),
        Text(
          count,
          style: TextStyle(fontSize: AppTypography.sm, color: muted),
        ),
      ],
    );
  }

  Widget _actionChipWidget(Widget iconWidget, String count, bool isDark) {
    final muted = AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        iconWidget,
        SizedBox(width: AppSpacing.intraGroupXs),
        Text(
          count,
          style: TextStyle(fontSize: AppTypography.sm, color: muted),
        ),
      ],
    );
  }
}

/// 文章卡片占位：1:1 复制 ArticleCard 结构（简化，后续接 ArticleDetailView）
class _ArticleCardPlaceholder extends StatelessWidget {
  final Map<String, dynamic> article;
  final bool isDark;
  final VoidCallback onTap;
  final VoidCallback onUserTap;

  const _ArticleCardPlaceholder({
    required this.article,
    required this.isDark,
    required this.onTap,
    required this.onUserTap,
  });

  @override
  Widget build(BuildContext context) {
    final fg = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final muted = AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    final author = article['author'] as Map<String, dynamic>? ?? {};
    final stats = article['stats'] as Map<String, dynamic>? ?? {};

    return InkWell(
      onTap: onTap,
      child: Container(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.md.w,
          vertical: AppSpacing.md.h,
        ),
        decoration: BoxDecoration(
          color: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
          border: Border(
            bottom: BorderSide(
              color: AppColorsFunctional.getColor(isDark, ColorType.borderPrimary),
            ),
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                GestureDetector(
                  onTap: onUserTap,
                  child: CircleAvatar(
                    radius: AppSpacing.avatarUserSm / 2,
                    backgroundImage: NetworkImage(
                      author['avatar']?.toString() ??
                          'https://images.unsplash.com/photo-1531427186611-ecfd6d936c79?w=100',
                    ),
                  ),
                ),
                SizedBox(width: AppSpacing.interGroupXs),
                Text(
                  author['name']?.toString() ?? '',
                  style: TextStyle(
                    fontSize: AppTypography.base,
                    fontWeight: AppTypography.medium,
                    color: fg,
                  ),
                ),
                const Spacer(),
                Text(
                  article['date']?.toString() ?? '',
                  style: TextStyle(fontSize: AppTypography.base, color: muted),
                ),
              ],
            ),
            SizedBox(height: AppSpacing.intraGroupSm),
            Text(
              article['category']?.toString() ?? '',
              style: TextStyle(
                fontSize: AppTypography.sm,
                color: AppColors.primaryColor,
                fontWeight: AppTypography.bold,
              ),
            ),
            SizedBox(height: AppSpacing.intraGroupXs),
            Text(
              article['title']?.toString() ?? '',
              style: TextStyle(
                fontSize: AppTypography.lg,
                fontWeight: AppTypography.semiBold,
                color: fg,
              ),
            ),
            SizedBox(height: AppSpacing.intraGroupXs),
            Text(
              article['description']?.toString() ?? '',
              style: TextStyle(fontSize: AppTypography.base, color: fg),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
            SizedBox(height: AppSpacing.interGroupXs),
            Row(
              children: [
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      CupertinoIcons.heart,
                      size: AppSpacing.iconMedium,
                      color: muted,
                    ),
                    Text(
                      ' ${stats['likes'] ?? 0} ',
                      style: TextStyle(fontSize: AppTypography.base, color: muted),
                    ),
                    AppStarIcon(size: AppSpacing.iconMedium, color: muted),
                    Text(
                      ' ${stats['bookmarks'] ?? stats['saves'] ?? 0} ',
                      style: TextStyle(fontSize: AppTypography.base, color: muted),
                    ),
                    AppBubbleIcon(size: AppSpacing.iconMedium, color: muted),
                    Text(
                      ' ${stats['comments'] ?? 0} ',
                      style: TextStyle(fontSize: AppTypography.base, color: muted),
                    ),
                  ],
                ),
                const Spacer(),
                Icon(
                  CupertinoIcons.arrowshape_turn_up_right,
                  size: AppSpacing.iconMedium,
                  color: muted,
                ),
                Text(
                  ' ${stats['shares'] ?? 0}',
                  style: TextStyle(fontSize: AppTypography.base, color: muted),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

/// 1:1 复制 DiscoveryItem.tsx：缩略图、多图角标、视频 Play 角标
class _DiscoveryItemCard extends StatelessWidget {
  final Map<String, dynamic> post;
  final VoidCallback onTap;

  const _DiscoveryItemCard({required this.post, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final images = post['images'] as List?;
    final thumb = post['thumbnail']?.toString() ??
        (images != null && images.isNotEmpty ? images.first.toString() : null) ??
        'https://images.unsplash.com/photo-1519904981063-b0cf448d479e?w=800';
    final isVideo = post['type'] == 'video';
    final imageCount = (post['images'] as List?)?.length ?? 1;

    return GestureDetector(
      onTap: onTap,
      child: Container(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
          color: Colors.grey.shade200,
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.06),
              blurRadius: 4,
              offset: const Offset(0, 1),
            ),
          ],
        ),
        child: Stack(
          fit: StackFit.expand,
          children: [
            ClipRRect(
              borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
              child: Image.network(
                thumb,
                fit: BoxFit.cover,
                  errorBuilder: (context, error, stackTrace) => Icon(
                    Icons.broken_image_outlined,
                    size: AppSpacing.largeButtonSize,
                  ),
              ),
            ),
            Positioned(
              top: 8,
              right: 8,
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (!isVideo && imageCount > 1)
                    Container(
                      padding: EdgeInsets.symmetric(
                        horizontal: AppSpacing.intraGroupSm,
                        vertical: AppSpacing.xs / 2,
                      ),
                      decoration: BoxDecoration(
                        color: Colors.black.withValues(alpha: 0.25),
                        borderRadius:
                            BorderRadius.circular(AppSpacing.smallBorderRadius),
                        border: Border.all(color: Colors.white.withValues(alpha: 0.1)),
                      ),
                      child: Text(
                        '$imageCount',
                        style: TextStyle(
                          fontSize: AppTypography.xs,
                          fontWeight: AppTypography.black,
                          color: Colors.white.withValues(alpha: 0.9),
                        ),
                      ),
                    ),
                  if (isVideo)
                    Container(
                      padding: EdgeInsets.all(AppSpacing.xs),
                      decoration: BoxDecoration(
                        color: Colors.black.withValues(alpha: 0.25),
                        shape: BoxShape.circle,
                        border: Border.all(color: Colors.white.withValues(alpha: 0.1)),
                      ),
                      child: Icon(
                        Icons.play_arrow,
                        size: AppSpacing.iconSmall,
                        color: Colors.white,
                      ),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// 1:1 复制 VideoImmersionView.tsx：顶栏（返回/胶囊/搜索）、竖滑整屏视频、右侧互动栏、左下文案与音乐
class _VideoImmersionView extends StatefulWidget {
  const _VideoImmersionView({
    required this.categories,
    required this.activeTab,
    required this.videos,
    required this.isUIVisible,
    required this.onBack,
    required this.onTabChange,
    required this.onToggleUI,
    required this.onUserClick,
  });

  final List<Map<String, String>> categories;
  final String activeTab;
  final List<Map<String, dynamic>> videos;
  final bool isUIVisible;
  final VoidCallback onBack;
  final void Function(String id) onTabChange;
  final VoidCallback onToggleUI;
  final void Function(String userId) onUserClick;

  @override
  State<_VideoImmersionView> createState() => _VideoImmersionViewState();
}

class _VideoImmersionViewState extends State<_VideoImmersionView> {
  late PageController _pageController;
  final Set<int> _likedIndexes = {};

  List<String> get _primaryTabIds =>
      widget.categories.map((category) => category['id']!).toList(growable: false);

  void _switchPrimaryByDelta(int delta) {
    final currentIndex = _primaryTabIds.indexOf(widget.activeTab);
    if (currentIndex < 0) return;
    final nextIndex = currentIndex + delta;
    if (nextIndex < 0 || nextIndex >= _primaryTabIds.length) {
      HapticFeedback.selectionClick();
      return;
    }
    final nextId = _primaryTabIds[nextIndex];
    if (nextId != 'video') {
      widget.onTabChange(nextId);
    }
  }

  void _onPrimaryDragEnd(DragEndDetails details) {
    final velocity = details.primaryVelocity ?? 0;
    if (velocity.abs() < 220) return;
    _switchPrimaryByDelta(velocity < 0 ? 1 : -1);
  }

  @override
  void initState() {
    super.initState();
    _pageController = PageController();
  }

  @override
  void dispose() {
    _pageController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      color: Colors.black,
      child: SafeArea(
        top: true,
        bottom: false,
        child: Column(
          children: [
            // 顶栏：返回 | 胶囊 Tab | 搜索（1:1 VideoImmersionView header）
            AnimatedOpacity(
              opacity: widget.isUIVisible ? 1 : 0,
              duration: const Duration(milliseconds: 200),
              child: Container(
                height: AppSpacing.toolbarHeight,
                padding: EdgeInsets.symmetric(horizontal: AppSpacing.sm),
                child: Row(
                  children: [
                    IconButton(
                      icon: const Icon(Icons.chevron_left, color: Colors.white),
                      onPressed: widget.onBack,
                      style: IconButton.styleFrom(
                        backgroundColor: Colors.white.withValues(alpha: 0.2),
                      ),
                    ),
                    Expanded(
                      child: GestureDetector(
                        behavior: HitTestBehavior.translucent,
                        onHorizontalDragEnd: _onPrimaryDragEnd,
                        child: Container(
                          padding: EdgeInsets.all(AppSpacing.xs / 2),
                          decoration: BoxDecoration(
                            color: Colors.white.withValues(alpha: 0.1),
                            borderRadius: BorderRadius.circular(
                              AppSpacing.circularBorderRadius,
                            ),
                          ),
                          child: Stack(
                            children: [
                              SingleChildScrollView(
                                scrollDirection: Axis.horizontal,
                                child: Row(
                                  children: widget.categories.map((cat) {
                                final isActive = widget.activeTab == cat['id'];
                                return Padding(
                                  padding: EdgeInsets.only(right: AppSpacing.intraGroupSm),
                                  child: Material(
                                    color: Colors.transparent,
                                    child: InkWell(
                                      onTap: () {
                                        if (cat['id'] != 'video') {
                                          widget.onTabChange(cat['id']!);
                                        }
                                      },
                                      borderRadius: BorderRadius.circular(
                                        AppSpacing.circularBorderRadius,
                                      ),
                                      child: ConstrainedBox(
                                        constraints: BoxConstraints(
                                          minWidth: AppSpacing.minInteractiveSize,
                                          minHeight: AppSpacing.minInteractiveSize,
                                        ),
                                        child: Container(
                                          padding: EdgeInsets.symmetric(
                                            horizontal: AppSpacing.containerSm,
                                            vertical: AppSpacing.intraGroupXs,
                                          ),
                                          decoration: BoxDecoration(
                                            color: isActive
                                                ? Colors.white.withValues(alpha: 0.2)
                                                : Colors.transparent,
                                            borderRadius: BorderRadius.circular(
                                              AppSpacing.circularBorderRadius,
                                            ),
                                          ),
                                          child: Text(
                                            cat['label']!,
                                            style: TextStyle(
                                              fontSize: AppTypography.base,
                                              fontWeight: isActive
                                                  ? AppTypography.bold
                                                  : AppTypography.medium,
                                              color: isActive
                                                  ? Colors.white
                                                  : Colors.white.withValues(alpha: 0.5),
                                            ),
                                          ),
                                        ),
                                      ),
                                    ),
                                  ),
                                );
                              }).toList(),
                                ),
                              ),
                              Positioned(
                                right: 0,
                                top: 0,
                                bottom: 0,
                                child: IgnorePointer(
                                  child: Container(
                                    width: AppSpacing.lg,
                                    decoration: BoxDecoration(
                                      gradient: LinearGradient(
                                        begin: Alignment.centerLeft,
                                        end: Alignment.centerRight,
                                        colors: [
                                          Colors.transparent,
                                          Colors.white.withValues(alpha: 0.15),
                                        ],
                                      ),
                                    ),
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                    IconButton(
                      icon: Icon(
                        Icons.search,
                        color: Colors.white,
                        size: AppSpacing.iconMedium,
                      ),
                      onPressed: () {},
                      style: IconButton.styleFrom(
                        minimumSize: Size.square(AppSpacing.iconButtonMinSizeSm),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            // 竖滑视频列表
            Expanded(
              child: PageView.builder(
                controller: _pageController,
                scrollDirection: Axis.vertical,
                itemCount: widget.videos.length,
                onPageChanged: (_) {},
                itemBuilder: (context, index) {
                  final post = widget.videos[index];
                  final author = post['author'] is Map ? Map<String, dynamic>.from(post['author'] as Map) : <String, dynamic>{};
                  final authorId = author['id'] as String? ?? author['name'] as String? ?? '';
                  final isLiked = _likedIndexes.contains(index);
                  return GestureDetector(
                    onTap: widget.onToggleUI,
                    child: Stack(
                      fit: StackFit.expand,
                      children: [
                        // 背景图
                        Image.network(
                          post['thumbnail'] as String? ?? '',
                          fit: BoxFit.cover,
                          errorBuilder: (context, error, stackTrace) =>
                              Container(color: Colors.grey.shade900),
                        ),
                        // 底部渐变
                        Container(
                          decoration: BoxDecoration(
                            gradient: LinearGradient(
                              begin: Alignment.topCenter,
                              end: Alignment.bottomCenter,
                              colors: [Colors.transparent, Colors.black.withValues(alpha: 0.8)],
                            ),
                          ),
                        ),
                        // 右侧互动栏（吸收点击，避免触发整页 onToggleUI）
                        if (widget.isUIVisible)
                          Positioned(
                            right: AppSpacing.containerMd,
                            bottom: AppSpacing.bottomNavHeight + AppSpacing.interGroupMd,
                            child: GestureDetector(
                              onTap: () {},
                              behavior: HitTestBehavior.opaque,
                              child: Column(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                GestureDetector(
                                  onTap: () => widget.onUserClick(authorId),
                                  child: Column(
                                    children: [
                                      CircleAvatar(
                                        radius: AppSpacing.buttonHeight / 2,
                                        backgroundColor: Colors.white,
                                        backgroundImage: NetworkImage(author['avatar'] as String? ?? ''),
                                      ),
                                      SizedBox(height: AppSpacing.intraGroupXs),
                                      Icon(
                                        Icons.add_circle,
                                        color: AppColors.primaryColor,
                                        size: AppSpacing.iconMedium,
                                      ),
                                    ],
                                  ),
                                ),
                                SizedBox(height: AppSpacing.interGroupLg),
                                _videoAction(CupertinoIcons.heart, isLiked, '${post['likes'] ?? ''}', () => setState(() {
                                  if (_likedIndexes.contains(index)) {
                                    _likedIndexes.remove(index);
                                  } else {
                                    _likedIndexes.add(index);
                                  }
                                })),
                                _videoActionWidget(AppStarIcon(size: AppSpacing.iconMedium, color: Colors.white.withValues(alpha: 0.78)), UITextConstants.bookmarks, () {}),
                                _videoActionWidget(AppBubbleIcon(size: AppSpacing.iconMedium, color: Colors.white.withValues(alpha: 0.78)), '${post['comments'] ?? ''}', () {}),
                                _videoAction(CupertinoIcons.arrowshape_turn_up_right, false, '${post['shares'] ?? ''}', () {}),
                                SizedBox(height: AppSpacing.interGroupMd),
                                Container(
                                  width: 40.w,
                                  height: 40.w,
                                  decoration: BoxDecoration(
                                    shape: BoxShape.circle,
                                    border: Border.all(color: Colors.white24, width: 2),
                                    image: DecorationImage(
                                      image: NetworkImage(author['avatar'] as String? ?? ''),
                                      fit: BoxFit.cover,
                                    ),
                                  ),
                                ),
                              ],
                            ),
                            ),
                          ),
                        // 左下文案
                        if (widget.isUIVisible)
                          Positioned(
                            left: AppSpacing.containerMd,
                            right: 80,
                            bottom: AppSpacing.buttonHeight,
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                GestureDetector(
                                  onTap: () => widget.onUserClick(authorId),
                                  child: Text(
                                    '@${author['name'] ?? ''}',
                                    style: TextStyle(
                                      fontSize: AppTypography.lg,
                                      fontWeight: AppTypography.medium,
                                      color: Colors.white,
                                    ),
                                  ),
                                ),
                                SizedBox(height: AppSpacing.intraGroupXs),
                                Text(
                                  '${post['content'] ?? ''}',
                                  style: TextStyle(
                                    fontSize: AppTypography.base,
                                    color: Colors.white.withValues(alpha: 0.9),
                                  ),
                                  maxLines: 3,
                                  overflow: TextOverflow.ellipsis,
                                ),
                                SizedBox(height: AppSpacing.interGroupXs),
                                Row(
                                  children: [
                                    Icon(
                                      Icons.music_note,
                                      size: AppSpacing.iconSmall,
                                      color: Colors.white,
                                    ),
                                    SizedBox(width: AppSpacing.intraGroupSm),
                                    Expanded(
                                      child: Text(
                                        '${post['musicName'] ?? ''} • ${author['name'] ?? ''} 创作的原声',
                                        style: TextStyle(
                                          fontSize: AppTypography.sm,
                                          color: Colors.white.withValues(alpha: 0.8),
                                        ),
                                        overflow: TextOverflow.ellipsis,
                                      ),
                                    ),
                                  ],
                                ),
                              ],
                            ),
                          ),
                      ],
                    ),
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _videoAction(IconData icon, bool filled, String label, VoidCallback onTap) {
    return Column(
      children: [
        IconButton(
          icon: Icon(
            icon == CupertinoIcons.heart
                ? (filled ? CupertinoIcons.heart_fill : CupertinoIcons.heart)
                : icon,
            color: filled
                ? Colors.white
                : Colors.white.withValues(alpha: 0.78),
            size: AppSpacing.iconMedium,
          ),
          onPressed: onTap,
          style: IconButton.styleFrom(
            minimumSize: Size.square(AppSpacing.iconButtonMinSizeSm),
          ),
        ),
        Text(
          label,
          style: TextStyle(
            fontSize: AppTypography.sm,
            fontWeight: AppTypography.bold,
            color: Colors.white,
          ),
        ),
        SizedBox(height: AppSpacing.interGroupMd),
      ],
    );
  }

  Widget _videoActionWidget(Widget iconWidget, String label, VoidCallback onTap) {
    return Column(
      children: [
        IconButton(
          icon: iconWidget,
          onPressed: onTap,
          style: IconButton.styleFrom(
            minimumSize: Size.square(AppSpacing.iconButtonMinSizeSm),
          ),
        ),
        Text(
          label,
          style: TextStyle(
            fontSize: AppTypography.sm,
            fontWeight: AppTypography.bold,
            color: Colors.white,
          ),
        ),
        SizedBox(height: AppSpacing.interGroupMd),
      ],
    );
  }
}
