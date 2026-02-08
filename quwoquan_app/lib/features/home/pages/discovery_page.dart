import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/components/assistant_floating_ball.dart';
import 'package:quwoquan_app/data/mock/prototype_mock_data.dart';

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
    {'id': 'moment', 'label': '微趣'},
    {'id': 'photo', 'label': '美图'},
    {'id': 'video', 'label': '视频'},
    {'id': 'article', 'label': '文章'},
  ];

  bool get _isVideoMode => _activeType == 'video';

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

  /// 1:1 复制 DiscoveryFeed.tsx Motion.header：sticky top-0 z-40 safe-top，左侧占位、中间胶囊、右侧搜索
  Widget _buildHeader(bool isDark) {
    return AnimatedContainer(
      duration: const Duration(milliseconds: 500),
      decoration: BoxDecoration(
        color: _isVideoMode
            ? null
            : AppColorsFunctional
                .getColor(isDark, ColorType.backgroundPrimary)
                .withValues(alpha: 0.9),
        gradient: _isVideoMode
            ? const LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [Color(0x99000000), Colors.transparent],
              )
            : null,
        border: _isVideoMode
            ? null
            : Border(
                bottom: BorderSide(
                  color: AppColorsFunctional.getColor(isDark, ColorType.borderPrimary),
                  width: 1,
                ),
              ),
      ),
      child: SafeArea(
        bottom: false,
        child: AnimatedOpacity(
          opacity: (_isVideoMode && !_isUIVisible) ? 0 : 1,
          duration: const Duration(milliseconds: 200),
          child: SizedBox(
            height: 56,
            child: Row(
              children: [
                const SizedBox(width: 32),
                Expanded(
                  child: Center(
                    child: Container(
                      padding: const EdgeInsets.all(2),
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(999),
                        color: _isVideoMode
                            ? Colors.white.withValues(alpha: 0.1)
                            : AppColorsFunctional
                                .getColor(isDark, ColorType.backgroundSecondary)
                                .withValues(alpha: 0.8),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: _categories.map((cat) {
                          final isActive = _activeType == cat['id'];
                          return GestureDetector(
                            onTap: () {
                              setState(() => _activeType = cat['id']!);
                              _applyVideoForceDark();
                            },
                            child: AnimatedContainer(
                              duration: const Duration(milliseconds: 200),
                              padding: const EdgeInsets.symmetric(
                                horizontal: 16,
                                vertical: 4,
                              ),
                              decoration: BoxDecoration(
                                borderRadius: BorderRadius.circular(999),
                                color: isActive
                                    ? (_isVideoMode
                                        ? Colors.white.withValues(alpha: 0.2)
                                        : AppColorsFunctional.getColor(
                                            isDark,
                                            ColorType.backgroundPrimary,
                                          ))
                                    : Colors.transparent,
                                boxShadow: isActive && !_isVideoMode
                                    ? [
                                        BoxShadow(
                                          color: Colors.black.withValues(alpha: 0.06),
                                          blurRadius: 4,
                                          offset: const Offset(0, 1),
                                        ),
                                      ]
                                    : null,
                              ),
                              child: Text(
                                cat['label']!,
                                style: TextStyle(
                                  fontSize: 13.sp,
                                  fontWeight: FontWeight.w900,
                                  color: isActive
                                      ? (_isVideoMode
                                          ? Colors.white
                                          : AppColors.primaryColor)
                                      : (_isVideoMode
                                          ? Colors.white.withValues(alpha: 0.5)
                                          : AppColorsFunctional.getColor(
                                              isDark,
                                              ColorType.foregroundSecondary,
                                            )),
                                ),
                              ),
                            ),
                          );
                        }).toList(),
                      ),
                    ),
                  ),
                ),
                IconButton(
                  icon: Icon(
                    Icons.search,
                    size: 20,
                    color: _isVideoMode
                        ? Colors.white
                        : AppColorsFunctional.getColor(
                            isDark,
                            ColorType.foregroundSecondary,
                          ),
                  ),
                  onPressed: () {},
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  /// 1:1 复制 VideoImmersionView.tsx：顶栏（返回/胶囊 Tab/搜索）、竖滑视频列表、点击切换 UI、下拉退出
  Widget _buildVideoImmersionView(bool isDark) {
    final videos = PrototypeMockData.discoveryVideoData;
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
    final items = PrototypeMockData.discoveryMomentData;
    return ListView.builder(
      padding: EdgeInsets.only(
        bottom: MediaQuery.of(context).padding.bottom + 80,
      ),
      itemCount: items.length + 1,
      itemBuilder: (context, index) {
        if (index == items.length) {
          return Padding(
            padding: const EdgeInsets.symmetric(vertical: 40),
            child: Center(
              child: Text(
                '— 已显示全部推荐内容 —',
                style: TextStyle(
                  fontSize: 13.sp,
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
    final items = PrototypeMockData.discoveryArticleData;
    return ListView.builder(
      padding: EdgeInsets.only(
        bottom: MediaQuery.of(context).padding.bottom + 80,
      ),
      itemCount: items.length + 1,
      itemBuilder: (context, index) {
        if (index == items.length) {
          return Padding(
            padding: const EdgeInsets.symmetric(vertical: 40),
            child: Center(
              child: Text(
                '— 已显示全部推荐内容 —',
                style: TextStyle(
                  fontSize: 13.sp,
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
    final items = PrototypeMockData.discoveryPhotoData;
    return GridView.builder(
      padding: EdgeInsets.fromLTRB(
        8,
        8,
        8,
        MediaQuery.of(context).padding.bottom + 80 + 24,
      ),
      gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 2,
        mainAxisSpacing: 8,
        crossAxisSpacing: 8,
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
                  radius: 22,
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
                            fontSize: 15.sp,
                            fontWeight: FontWeight.w800,
                            color: fg,
                          ),
                        ),
                        if (user['badge'] != null) ...[
                          SizedBox(width: 4.w),
                          Container(
                            padding: EdgeInsets.symmetric(horizontal: 4.w, vertical: 2.h),
                            decoration: BoxDecoration(
                              color: AppColors.warning,
                              borderRadius: BorderRadius.circular(2),
                            ),
                            child: Text(
                              'V${user['badge']}',
                              style: TextStyle(
                                fontSize: 9.sp,
                                fontWeight: FontWeight.w700,
                                color: Colors.white,
                              ),
                            ),
                          ),
                        ],
                      ],
                    ),
                    SizedBox(height: 2.h),
                    Text(
                      item['timeAgo']?.toString() ?? '',
                      style: TextStyle(
                        fontSize: 12.sp,
                        color: muted,
                      ),
                    ),
                    if (item['source'] != null)
                      Text(
                        item['source'].toString(),
                        style: TextStyle(fontSize: 11.sp, color: muted),
                      ),
                  ],
                ),
              ),
            ],
          ),
          SizedBox(height: 8.h),
          Text(
            item['content']?.toString() ?? '',
            style: TextStyle(fontSize: 15.sp, color: fg, height: 1.4),
            maxLines: 10,
            overflow: TextOverflow.ellipsis,
          ),
          if (item['quotedPost'] != null) ...[
            SizedBox(height: 8.h),
            Container(
              padding: EdgeInsets.all(AppSpacing.sm.w),
              decoration: BoxDecoration(
                color: AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '@${(item['quotedPost'] as Map)['user']}',
                    style: TextStyle(
                      fontSize: 13.sp,
                      fontWeight: FontWeight.w700,
                      color: AppColors.primaryColor,
                    ),
                  ),
                  SizedBox(height: 4.h),
                  Text(
                    (item['quotedPost'] as Map)['content']?.toString() ?? '',
                    style: TextStyle(fontSize: 13.sp, color: muted),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ),
          ],
          if (item['media'] != null && (item['media'] as List).isNotEmpty) ...[
            SizedBox(height: 8.h),
            GestureDetector(
              onTap: () => onPostTap(item, 0),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(8),
                child: Image.network(
                  (item['media'] as List).first['url']?.toString() ??
                      (item['media'] as List).first['thumbnail']?.toString() ??
                      '',
                  width: double.infinity,
                  height: 200,
                  fit: BoxFit.cover,
                  errorBuilder: (_, __, ___) => Container(
                    height: 200,
                    color: borderColor,
                    child: const Icon(Icons.broken_image_outlined),
                  ),
                ),
              ),
            ),
          ],
          SizedBox(height: 10.h),
          Row(
            children: [
              _actionChip(Icons.thumb_up_outlined, '${item['likes'] ?? 0}', isDark),
              SizedBox(width: 16.w),
              _actionChip(Icons.chat_bubble_outline, '${item['comments'] ?? 0}', isDark),
              SizedBox(width: 16.w),
              _actionChip(Icons.share_outlined, '${item['shares'] ?? 0}', isDark),
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
        Icon(icon, size: 18, color: muted),
        SizedBox(width: 4.w),
        Text(
          count,
          style: TextStyle(fontSize: 13.sp, color: muted),
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
            Text(
              article['category']?.toString() ?? '',
              style: TextStyle(
                fontSize: 12.sp,
                color: AppColors.primaryColor,
                fontWeight: FontWeight.w700,
              ),
            ),
            SizedBox(height: 4.h),
            Text(
              article['title']?.toString() ?? '',
              style: TextStyle(
                fontSize: 17.sp,
                fontWeight: FontWeight.w900,
                color: fg,
              ),
            ),
            SizedBox(height: 4.h),
            Text(
              article['description']?.toString() ?? '',
              style: TextStyle(fontSize: 14.sp, color: muted),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
            SizedBox(height: 8.h),
            Row(
              children: [
                GestureDetector(
                  onTap: onUserTap,
                  child: CircleAvatar(
                    radius: 14,
                    backgroundImage: NetworkImage(
                      author['avatar']?.toString() ?? 'https://images.unsplash.com/photo-1531427186611-ecfd6d936c79?w=100',
                    ),
                  ),
                ),
                SizedBox(width: 8.w),
                Text(
                  author['name']?.toString() ?? '',
                  style: TextStyle(fontSize: 13.sp, fontWeight: FontWeight.w600, color: fg),
                ),
                const Spacer(),
                Text(
                  article['date']?.toString() ?? '',
                  style: TextStyle(fontSize: 12.sp, color: muted),
                ),
              ],
            ),
            SizedBox(height: 6.h),
            Row(
              children: [
                Icon(Icons.thumb_up_outlined, size: 14, color: muted),
                Text(' ${stats['likes'] ?? 0} ', style: TextStyle(fontSize: 12.sp, color: muted)),
                Icon(Icons.chat_bubble_outline, size: 14, color: muted),
                Text(' ${stats['comments'] ?? 0} ', style: TextStyle(fontSize: 12.sp, color: muted)),
                Icon(Icons.share_outlined, size: 14, color: muted),
                Text(' ${stats['shares'] ?? 0}', style: TextStyle(fontSize: 12.sp, color: muted)),
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
          borderRadius: BorderRadius.circular(8),
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
              borderRadius: BorderRadius.circular(8),
              child: Image.network(
                thumb,
                fit: BoxFit.cover,
                errorBuilder: (_, __, ___) => const Icon(Icons.broken_image_outlined, size: 48),
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
                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                      decoration: BoxDecoration(
                        color: Colors.black.withValues(alpha: 0.25),
                        borderRadius: BorderRadius.circular(4),
                        border: Border.all(color: Colors.white.withValues(alpha: 0.1)),
                      ),
                      child: Text(
                        '$imageCount',
                        style: TextStyle(
                          fontSize: 10,
                          fontWeight: FontWeight.w900,
                          color: Colors.white.withValues(alpha: 0.9),
                        ),
                      ),
                    ),
                  if (isVideo)
                    Container(
                      padding: const EdgeInsets.all(4),
                      decoration: BoxDecoration(
                        color: Colors.black.withValues(alpha: 0.25),
                        shape: BoxShape.circle,
                        border: Border.all(color: Colors.white.withValues(alpha: 0.1)),
                      ),
                      child: Icon(Icons.play_arrow, size: 14, color: Colors.white),
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
                height: 56,
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
                      child: Center(
                        child: Container(
                          padding: const EdgeInsets.all(2),
                          decoration: BoxDecoration(
                            color: Colors.white.withValues(alpha: 0.1),
                            borderRadius: BorderRadius.circular(999),
                          ),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: widget.categories.map((cat) {
                              final isActive = widget.activeTab == cat['id'];
                              return GestureDetector(
                                onTap: () {
                                  if (cat['id'] != 'video') widget.onTabChange(cat['id']!);
                                },
                                child: Container(
                                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
                                  decoration: BoxDecoration(
                                    color: isActive ? Colors.white.withValues(alpha: 0.2) : Colors.transparent,
                                    borderRadius: BorderRadius.circular(999),
                                  ),
                                  child: Text(
                                    cat['label']!,
                                    style: TextStyle(
                                      fontSize: 13.sp,
                                      fontWeight: FontWeight.w900,
                                      color: isActive ? Colors.white : Colors.white.withValues(alpha: 0.5),
                                    ),
                                  ),
                                ),
                              );
                            }).toList(),
                          ),
                        ),
                      ),
                    ),
                    IconButton(
                      icon: Icon(Icons.search, color: Colors.white, size: 20.sp),
                      onPressed: () {},
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
                          errorBuilder: (_, __, ___) => Container(color: Colors.grey.shade900),
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
                            right: 16,
                            bottom: 80,
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
                                        radius: 24.r,
                                        backgroundColor: Colors.white,
                                        backgroundImage: NetworkImage(author['avatar'] as String? ?? ''),
                                      ),
                                      SizedBox(height: 4.h),
                                      Icon(Icons.add_circle, color: AppColors.primaryColor, size: 20.sp),
                                    ],
                                  ),
                                ),
                                SizedBox(height: 24.h),
                                _videoAction(Icons.favorite, isLiked, '${post['likes'] ?? ''}', () => setState(() {
                                  if (_likedIndexes.contains(index)) {
                                    _likedIndexes.remove(index);
                                  } else {
                                    _likedIndexes.add(index);
                                  }
                                })),
                                _videoAction(Icons.chat_bubble_outline, false, '${post['comments'] ?? ''}', () {}),
                                _videoAction(Icons.bookmark_border, false, '收藏', () {}),
                                _videoAction(Icons.share, false, '${post['shares'] ?? ''}', () {}),
                                SizedBox(height: 16.h),
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
                            left: 16,
                            right: 80,
                            bottom: 48,
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                GestureDetector(
                                  onTap: () => widget.onUserClick(authorId),
                                  child: Text(
                                    '@${author['name'] ?? ''}',
                                    style: TextStyle(fontSize: 16.sp, fontWeight: FontWeight.w900, color: Colors.white),
                                  ),
                                ),
                                SizedBox(height: 4.h),
                                Text(
                                  '${post['content'] ?? ''}',
                                  style: TextStyle(fontSize: 14.sp, color: Colors.white.withValues(alpha: 0.9)),
                                  maxLines: 3,
                                  overflow: TextOverflow.ellipsis,
                                ),
                                SizedBox(height: 8.h),
                                Row(
                                  children: [
                                    Icon(Icons.music_note, size: 16.sp, color: Colors.white),
                                    SizedBox(width: 6.w),
                                    Expanded(
                                      child: Text(
                                        '${post['musicName'] ?? ''} • ${author['name'] ?? ''} 创作的原声',
                                        style: TextStyle(fontSize: 13.sp, color: Colors.white.withValues(alpha: 0.8)),
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
            icon == Icons.favorite ? (filled ? Icons.favorite : Icons.favorite_border) : icon,
            color: filled ? AppColors.primaryColor : Colors.white,
            size: 28.sp,
          ),
          onPressed: onTap,
        ),
        Text(label, style: TextStyle(fontSize: 12.sp, fontWeight: FontWeight.w700, color: Colors.white)),
        SizedBox(height: 16.h),
      ],
    );
  }
}
