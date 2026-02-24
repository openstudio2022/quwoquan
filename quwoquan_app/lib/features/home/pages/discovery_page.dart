// ignore_for_file: unnecessary_non_null_assertion
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_staggered_grid_view/flutter_staggered_grid_view.dart';
import 'package:quwoquan_app/cloud/runtime/generated/post_runtime_metadata.g.dart';
import 'package:quwoquan_app/components/comment_system/comment_viewer_modal.dart';
import 'package:quwoquan_app/components/comment_system/comment_models.dart';
import 'package:quwoquan_app/components/more_actions_popup/more_action_popup.dart';
import 'package:quwoquan_app/components/more_actions_popup/configs/media_post_config.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/components/tab_navigation.dart';
import 'package:quwoquan_app/components/centered_scrollable_tab_bar.dart';
import 'package:quwoquan_app/components/assistant_avatar.dart';
import 'package:quwoquan_app/features/assistant/context/assistant_open_context.dart';
import 'package:quwoquan_app/features/assistant/widgets/assistant_half_sheet.dart';

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
  /// 与 design-clarification-2026-02：微趣|美图|视频|文章，默认美图
  String _activeType = 'photo';
  /// 保存 notifier 供 dispose 回调使用，避免 dispose 后使用 ref
  VideoForceDarkNotifier? _videoForceDarkNotifier;
  BottomNavHiddenNotifier? _bottomNavHiddenNotifier;
  late PageController _primaryPageController;
  final Map<String, Future<List<Map<String, dynamic>>>> _discoveryFeedFutures =
      <String, Future<List<Map<String, dynamic>>>>{};

  @override
  bool get wantKeepAlive => true;

  /// 一级分类：微趣|美图|视频|文章（design-clarification-2026-02）
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
    _ensureFeedFuture(id);
    _recordDiscoveryVisit(id);
    _applyVideoForceDark();
    final index = _primaryTabIds.indexOf(id);
    if (index < 0) return;
    if (_primaryPageController.hasClients &&
        index != _primaryPageController.page?.round()) {
      _primaryPageController.animateToPage(
        index,
        duration: const Duration(milliseconds: 300),
        curve: Curves.easeInOut,
      );
    } else if (!_primaryPageController.hasClients) {
      // 从视频全屏切到其他 tab 时 PageView 未挂载，下一帧挂载后需同步到正确页
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        if (_primaryPageController.hasClients) {
          _primaryPageController.jumpToPage(index);
        }
      });
    }
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

  /// 在非 build/initState/dispose 中更新，避免 “modify provider while building”
  void _applyVideoForceDark() {
    ref.read(videoForceDarkProvider.notifier).setForceDark(_isVideoMode);
    ref.read(bottomNavHiddenProvider.notifier).setHidden(_isVideoMode);
  }

  void _trackBehavior(String action, dynamic post, {double? duration}) {
    final contentId = post is Map ? (post['id']?.toString() ?? '') : '';
    if (contentId.isEmpty) return;
    final tags = post is Map
        ? ((post['tags'] as List?)?.cast<String>() ?? <String>[])
        : <String>[];
    ref.read(behaviorRepositoryProvider).reportSingle(
      contentId: contentId,
      action: action,
      tags: tags,
      duration: duration,
    );
  }

  void _recordDiscoveryVisit(String tabId) {
    ref.read(visitRecorderServiceProvider).recordVisit(
          VisitTarget.page('discovery_$tabId'),
        );
  }

  void _openAssistantHalfSheet() {
    final target = VisitTarget.page('discovery_$_activeType');
    final service = ref.read(visitRecorderServiceProvider);
    final ctx = AssistantOpenContext(
      source: AssistantSource.discovery,
      tab: _activeType,
      visitTarget: target,
      experienceLevel: service.getExperience(target),
    );
    AssistantHalfSheet.show(context, ctx);
  }

  @override
  void initState() {
    super.initState();
    _primaryPageController = PageController(
      initialPage: _primaryTabIds.indexOf(_activeType).clamp(0, _primaryTabIds.length - 1),
    );
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _videoForceDarkNotifier = ref.read(videoForceDarkProvider.notifier);
      _bottomNavHiddenNotifier = ref.read(bottomNavHiddenProvider.notifier);
      _applyVideoForceDark();
      _recordDiscoveryVisit(_activeType);
      for (final id in _primaryTabIds) {
        _ensureFeedFuture(id);
      }
    });
  }

  @override
  void dispose() {
    _primaryPageController.dispose();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _videoForceDarkNotifier?.setForceDark(false);
      _bottomNavHiddenNotifier?.setHidden(false);
    });
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final themeDark = ref.watch(effectiveIsDarkProvider);
    final isDark = themeDark || _isVideoMode;

    // 从视频全屏返回时确保 PageView 显示与 _activeType 一致的页
    if (!_isVideoMode && _primaryPageController.hasClients) {
      final expectedIndex = _primaryTabIds.indexOf(_activeType);
      if (expectedIndex != -1 &&
          (_primaryPageController.page?.round() ?? -1) != expectedIndex) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (!mounted) return;
          if (!_isVideoMode &&
              _primaryPageController.hasClients &&
              _primaryTabIds.contains(_activeType)) {
            _primaryPageController.jumpToPage(
              _primaryTabIds.indexOf(_activeType),
            );
          }
        });
      }
    }

    final body = Column(
      children: [
        _buildHeader(isDark),
        Expanded(
          child: PageView(
            controller: _primaryPageController,
            onPageChanged: (index) {
              final id = _primaryTabIds[index];
              if (id != _activeType) {
                setState(() => _activeType = id);
                _applyVideoForceDark();
              }
            },
            children: _primaryTabIds
                .map((id) => _buildContentForTab(id, isDark))
                .toList(growable: false),
          ),
        ),
      ],
    );

    return Scaffold(
      backgroundColor: _isVideoMode
          ? Colors.black
          : AppColorsFunctional.getColor(themeDark, ColorType.backgroundPrimary),
      body: _isVideoMode
          ? AnnotatedRegion<SystemUiOverlayStyle>(
              value: const SystemUiOverlayStyle(
                statusBarColor: Colors.transparent,
                statusBarIconBrightness: Brightness.light,
                statusBarBrightness: Brightness.dark,
              ),
              child: _buildVideoImmersionView(isDark),
            )
          : body,
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
        border: Border(
          bottom: BorderSide(
            color: AppColorsFunctional.getColor(isDark, ColorType.borderPrimary),
            width: 1,
          ),
        ),
      ),
      child: SafeArea(
        bottom: false,
        child: CenteredScrollableTabBar(
          tabs: tabs,
          activeTab: _activeType,
          isDark: isDark,
          leftAlignedCompactMode: true,
          onTabChange: _setActiveType,
          onHorizontalDragEnd: _onPrimaryDragEnd,
          trailingActions: [
            IconButton(
              tooltip: UITextConstants.assistantEntryFind,
              icon: AssistantAvatar(radius: AppSpacing.iconMedium / 2),
              onPressed: _openAssistantHalfSheet,
              style: IconButton.styleFrom(
                minimumSize: Size.square(AppSpacing.iconButtonMinSizeSm),
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// 视频沉浸：竖滑列表、顶栏/右侧栏/左下文案常显；使用频道流模式（[theaterModeTapToToggle] = false），不启用剧场点击切换。
  /// 底部导航仅由 [ _applyVideoForceDark ] 控制（在视频频道时隐藏，离开或 dispose 时恢复）。
  Widget _buildVideoImmersionView(bool isDark) {
    final fallback = ref.watch(appContentRepositoryProvider).discoveryVideoData;
    return FutureBuilder<List<Map<String, dynamic>>>(
      future: _ensureFeedFuture('video'),
      builder: (context, snapshot) {
        final posts = snapshot.data ?? fallback;
        final videos = posts.map(_toVideoItem).toList(growable: false);
        return _VideoImmersionView(
          categories: _categories,
          activeTab: _activeType,
          videos: videos,
          isUIVisible: true,
          theaterModeTapToToggle: false,
          onTabChange: (id) {
            _setActiveType(id);
            _applyVideoForceDark();
          },
          onToggleUI: () {},
          onUserClick: (userId) => context.push('/user/$userId'),
          onAssistantTap: _openAssistantHalfSheet,
          onCommentTap: _onMomentCommentTap,
          onShareTap: _onMomentShareTap,
        );
      },
    );
  }

  Widget _buildContentForTab(String tabId, bool isDark) {
    switch (tabId) {
      case 'video':
        return _buildVideoImmersionView(isDark);
      case 'moment':
        return _buildMomentContent(isDark);
      case 'article':
        return _buildArticleContent(isDark);
      case 'photo':
        return _buildPhotoContent(isDark);
      default:
        return _buildPhotoContent(isDark);
    }
  }

  double _contentHorizontalPadding(BuildContext context) =>
      AppSpacing.feedContentHorizontal(context);

  Widget _buildMomentContent(bool isDark) {
    final fallback = ref.watch(appContentRepositoryProvider).discoveryMomentData;
    final horizontal = _contentHorizontalPadding(context);
    return FutureBuilder<List<Map<String, dynamic>>>(
      future: _ensureFeedFuture('moment'),
      builder: (context, snapshot) {
        final source = snapshot.data ?? fallback;
        final moments = source.map(_toMomentItem).toList(growable: false);
        return ListView.builder(
          padding: EdgeInsets.only(
            top: AppSpacing.containerSm,
            bottom: MediaQuery.of(context).padding.bottom +
                AppSpacing.bottomNavHeight +
                AppSpacing.interGroupMd,
          ),
          itemCount: moments.length,
          itemBuilder: (context, index) {
            final isFirst = index == 0;
            return Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Padding(
                  padding: EdgeInsets.symmetric(horizontal: horizontal),
                  child: _MomentPostCard(
                    item: moments[index],
                    isDark: isDark,
                    isFirst: isFirst,
                    onUserTap: (id) => context.push('/user/$id'),
                    onPostTap: (post, i) => _onPostTap(post, i),
                    onCommentTap: (post) => _onMomentCommentTap(context, post),
                    onShareTap: (post) => _onMomentShareTap(context, post),
                    onMoreTap: (post) => _onMomentMoreTap(context, post),
                    onBehavior: _trackBehavior,
                  ),
                ),
                if (index < moments.length - 1)
                  Container(
                    height: AppSpacing.sm,
                    color: AppColorsFunctional.getColor(
                      isDark,
                      ColorType.backgroundTertiary,
                    ),
                  ),
              ],
            );
          },
        );
      },
    );
  }

  Widget _buildArticleContent(bool isDark) {
    final fallback = ref.watch(appContentRepositoryProvider).discoveryArticleData;
    final horizontal = _contentHorizontalPadding(context);
    return FutureBuilder<List<Map<String, dynamic>>>(
      future: _ensureFeedFuture('article'),
      builder: (context, snapshot) {
        final source = snapshot.data ?? fallback;
        final articles = source.map(_toArticleItem).toList(growable: false);
        return ListView.builder(
          padding: EdgeInsets.only(
            top: AppSpacing.containerSm,
            bottom: MediaQuery.of(context).padding.bottom +
                AppSpacing.bottomNavHeight +
                AppSpacing.interGroupMd,
          ),
          itemCount: articles.length,
          itemBuilder: (context, index) {
            final article = articles[index];
            final isFirst = index == 0;
            return Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Padding(
                  padding: EdgeInsets.symmetric(horizontal: horizontal),
                  child: _ArticleCardPlaceholder(
                    article: article,
                    isDark: isDark,
                    isFirst: isFirst,
                    onTap: () {
                      _trackBehavior('click', article);
                      context.push('/article/${article['id']}');
                    },
                    onUserTap: () => context.push(
                      '/user/${article['author']?['name'] ?? ''}',
                    ),
                  ),
                ),
                if (index < articles.length - 1)
                  Container(
                    height: AppSpacing.sm,
                    color: AppColorsFunctional.getColor(
                      isDark,
                      ColorType.backgroundTertiary,
                    ),
                  ),
              ],
            );
          },
        );
      },
    );
  }

  /// 美图流：不规则瀑布流，单图高按宽高比自适应，最大 9:16
  static const double _photoMaxAspectRatio = 16 / 9;

  double _photoItemHeight(double cardWidth, Map<String, dynamic> post) {
    final ratio = (post['aspectRatio'] as num?)?.toDouble() ?? 1.0;
    if (ratio <= 0) return cardWidth;
    final heightByImage = cardWidth / ratio;
    final maxHeight = cardWidth * _photoMaxAspectRatio;
    return heightByImage > maxHeight ? maxHeight : heightByImage;
  }

  Widget _buildPhotoContent(bool isDark) {
    final fallback = ref.watch(appContentRepositoryProvider).discoveryPhotoData;
    final screenWidth = MediaQuery.of(context).size.width;
    final horizontal = _contentHorizontalPadding(context);
    final horizontalPadding = horizontal * 2;
    final gap = AppSpacing.interGroupSm;
    final cardWidth = (screenWidth - horizontalPadding - gap) / 2;

    return FutureBuilder<List<Map<String, dynamic>>>(
      future: _ensureFeedFuture('photo'),
      builder: (context, snapshot) {
        final source = snapshot.data ?? fallback;
        final items = source.map(_toPhotoItem).toList(growable: false);
        return CustomScrollView(
          slivers: [
            SliverPadding(
              padding: EdgeInsets.fromLTRB(
                horizontal,
                AppSpacing.containerSm,
                horizontal,
                MediaQuery.of(context).padding.bottom +
                    AppSpacing.bottomNavHeight +
                    AppSpacing.interGroupLg,
              ),
              sliver: SliverMasonryGrid.count(
                crossAxisCount: 2,
                mainAxisSpacing: AppSpacing.interGroupSm,
                crossAxisSpacing: gap,
                childCount: items.length,
                itemBuilder: (context, index) {
                  final post = items[index];
                  final height = _photoItemHeight(cardWidth, post);
                  return SizedBox(
                    height: height,
                    child: _DiscoveryItemCard(
                      post: post,
                      onTap: () => _onPostTap(post, 0),
                    ),
                  );
                },
              ),
            ),
          ],
        );
      },
    );
  }

  Future<List<Map<String, dynamic>>> _fetchDiscoveryFeed(String tabId) async {
    final dataService = ref.read(dataServiceProvider);
    final category =
        GeneratedPostRuntimeMetadata.appTabToFeedCategory[tabId] ??
        GeneratedPostRuntimeMetadata.appTabToFeedCategory['moment'] ??
        'recommended';
    final posts = await dataService.getDataList(
      endpoint: '/posts',
      params: <String, dynamic>{'category': category},
      limit: GeneratedPostRuntimeMetadata.feedDefaultLimit,
    );
    return posts;
  }

  Future<List<Map<String, dynamic>>> _ensureFeedFuture(String tabId) {
    return _discoveryFeedFutures.putIfAbsent(
      tabId,
      () => _fetchDiscoveryFeed(tabId),
    );
  }

  Map<String, dynamic> _toMomentItem(Map<String, dynamic> post) {
    final user = <String, dynamic>{
      'id': post['authorId']?.toString() ?? post['username']?.toString() ?? '',
      'name':
          post['displayName']?.toString() ?? post['username']?.toString() ?? '',
      'avatar':
          post['avatarUrl']?.toString() ?? post['avatar']?.toString() ?? '',
      'badge': post['badge'],
    };
    final images = (post['images'] as List? ?? const <dynamic>[])
        .map((e) => <String, dynamic>{'url': e.toString()})
        .toList(growable: false);
    final content = (post['content']?.toString().isNotEmpty == true)
        ? post['content'].toString()
        : (post['caption']?.toString() ?? '');
    return <String, dynamic>{
      ...post,
      'user': user,
      'content': content,
      'timeAgo': _toTimeAgo(post['createdAt']?.toString()),
      'media': images,
      'bookmarks': post['bookmarks'] ?? post['savesCount'] ?? 0,
      'comments': post['comments'] ?? post['commentsCount'] ?? 0,
      'likes': post['likes'] ?? post['likesCount'] ?? 0,
    };
  }

  Map<String, dynamic> _toArticleItem(Map<String, dynamic> post) {
    final author = <String, dynamic>{
      'name':
          post['displayName']?.toString() ?? post['username']?.toString() ?? '',
      'avatar':
          post['avatarUrl']?.toString() ?? post['avatar']?.toString() ?? '',
      'badge': post['badge']?.toString(),
    };
    return <String, dynamic>{
      ...post,
      'category': post['contentType']?.toString() ?? 'article',
      'title': post['title']?.toString() ?? '',
      'description':
          post['description']?.toString() ??
          post['body']?.toString() ??
          post['caption']?.toString() ??
          '',
      'date': _toDate(post['createdAt']?.toString()),
      'author': author,
      'stats': <String, dynamic>{
        'likes': post['likes'] ?? post['likesCount'] ?? 0,
        'bookmarks': post['bookmarks'] ?? post['savesCount'] ?? 0,
        'comments': post['comments'] ?? post['commentsCount'] ?? 0,
      },
    };
  }

  Map<String, dynamic> _toPhotoItem(Map<String, dynamic> post) {
    final images = (post['images'] as List? ?? const <dynamic>[]);
    final thumb = post['thumbnail']?.toString() ??
        post['thumbnailUrl']?.toString() ??
        (images.isNotEmpty ? images.first.toString() : '');
    return <String, dynamic>{
      ...post,
      'type': post['type']?.toString() ?? 'image',
      'thumbnail': thumb,
      'images': images,
      'aspectRatio': (post['aspectRatio'] as num?)?.toDouble() ?? 1.0,
    };
  }

  Map<String, dynamic> _toVideoItem(Map<String, dynamic> post) {
    final author = <String, dynamic>{
      'id': post['authorId']?.toString() ?? '',
      'name':
          post['displayName']?.toString() ?? post['username']?.toString() ?? '',
      'avatar':
          post['avatarUrl']?.toString() ?? post['avatar']?.toString() ?? '',
    };
    final images = (post['images'] as List? ?? const <dynamic>[]);
    final thumb = post['thumbnail']?.toString() ??
        post['thumbnailUrl']?.toString() ??
        (images.isNotEmpty ? images.first.toString() : '');
    final content = (post['content']?.toString().isNotEmpty == true)
        ? post['content'].toString()
        : (post['caption']?.toString() ?? '');
    return <String, dynamic>{
      ...post,
      'author': author,
      'thumbnail': thumb,
      'content': content,
      'likes': post['likes'] ?? post['likesCount'] ?? 0,
      'comments': post['comments'] ?? post['commentsCount'] ?? 0,
      'musicName': post['musicName']?.toString() ?? UITextConstants.discovery,
    };
  }

  String _toTimeAgo(String? iso) {
    if (iso == null || iso.isEmpty) return '';
    final time = DateTime.tryParse(iso);
    if (time == null) return '';
    final delta = DateTime.now().difference(time).inHours;
    if (delta < 1) return '刚刚';
    if (delta < 24) return '$delta小时前';
    return '${time.month}-${time.day}';
  }

  String _toDate(String? iso) {
    if (iso == null || iso.isEmpty) return '';
    final time = DateTime.tryParse(iso);
    if (time == null) return '';
    return '${time.year}-${time.month.toString().padLeft(2, '0')}-${time.day.toString().padLeft(2, '0')}';
  }

  void _onPostTap(dynamic post, int mediaIndex) {
    _trackBehavior('click', post);
    final type = post['type'] as String? ?? 'image';
    if (type == 'article') {
      context.push('/article/${post['id'] ?? ''}');
      return;
    }
    context.push('/media-viewer/images/$mediaIndex');
  }

  void _onMomentCommentTap(BuildContext context, dynamic post) {
    CommentViewer.showModal(
      context: context,
      postId: post['id']?.toString() ?? '',
      initialComments: [],
      config: const CommentConfig(enabled: true),
    );
  }

  void _onMomentShareTap(BuildContext context, dynamic post) {
    _trackBehavior('share', post);
    showModalBottomSheet<void>(
      context: context,
      builder: (context) => SafeArea(
        child: Padding(
          padding: EdgeInsets.all(AppSpacing.containerMd),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                UITextConstants.shareTo,
                style: TextStyle(
                  fontSize: AppTypography.lg,
                  fontWeight: AppTypography.semiBold,
                ),
              ),
              SizedBox(height: AppSpacing.interGroupMd),
              ListTile(
                leading: const Icon(Icons.chat_bubble_outline),
                title: Text(UITextConstants.shareTargetWechat),
                onTap: () => Navigator.pop(context),
              ),
              ListTile(
                leading: const Icon(Icons.people_outline),
                title: Text(UITextConstants.shareTargetMoments),
                onTap: () => Navigator.pop(context),
              ),
              ListTile(
                leading: const Icon(Icons.link),
                title: Text(UITextConstants.copyLink),
                onTap: () => Navigator.pop(context),
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _onMomentMoreTap(BuildContext context, dynamic post) {
    MoreActionPopup.show(
      context: context,
      config: MediaPostMoreActionConfig(post: post),
    );
  }
}

/// 微趣卡片：1:1 复制 MomentPost.tsx 结构（简化版，后续补全转发引用、九宫格等）
class _MomentPostCard extends StatefulWidget {
  final Map<String, dynamic> item;
  final bool isDark;
  final bool isFirst;
  final void Function(String) onUserTap;
  final void Function(dynamic, int) onPostTap;
  final void Function(dynamic)? onCommentTap;
  final void Function(dynamic)? onShareTap;
  final void Function(dynamic)? onMoreTap;
  final void Function(String action, dynamic post)? onBehavior;

  const _MomentPostCard({
    required this.item,
    required this.isDark,
    this.isFirst = false,
    required this.onUserTap,
    required this.onPostTap,
    this.onCommentTap,
    this.onShareTap,
    this.onMoreTap,
    this.onBehavior,
  });

  @override
  State<_MomentPostCard> createState() => _MomentPostCardState();
}

class _MomentPostCardState extends State<_MomentPostCard>
    with SingleTickerProviderStateMixin {
  bool _isLiked = false;
  bool _isBookmarked = false;
  late AnimationController _likeAnimationController;

  @override
  void initState() {
    super.initState();
    _likeAnimationController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 200),
    );
  }

  @override
  void dispose() {
    _likeAnimationController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final item = widget.item;
    final isDark = widget.isDark;
    final isFirst = widget.isFirst;
    final user = item['user'] as Map<String, dynamic>? ?? {};
    final fg = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final muted = AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    final quotedBg = AppColorsFunctional.getColor(isDark, ColorType.backgroundQuoted);
    final likeColor = _isLiked ? AppColors.error : muted;
    final bookmarkColor = _isBookmarked ? AppColors.warning : muted;

    final borderRadius = isFirst
        ? BorderRadius.only(
            bottomLeft: Radius.circular(AppSpacing.borderRadius),
            bottomRight: Radius.circular(AppSpacing.borderRadius),
          )
        : BorderRadius.circular(AppSpacing.borderRadius);

    return Container(
      padding: EdgeInsets.symmetric(vertical: AppSpacing.md.h),
      decoration: BoxDecoration(
        color: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
        borderRadius: borderRadius,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              GestureDetector(
                onTap: () => widget.onUserTap(user['id']?.toString() ?? user['name']?.toString() ?? ''),
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
              if (widget.onMoreTap != null)
                IconButton(
                  icon: Icon(Icons.more_horiz, size: AppSpacing.iconMedium, color: muted),
                  onPressed: () => widget.onMoreTap!(item),
                  style: IconButton.styleFrom(
                    minimumSize: Size.square(AppSpacing.iconButtonMinSizeSm),
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
                color: quotedBg,
                borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '@${(item['quotedPost'] as Map)['user']}',
                    style: TextStyle(
                      fontSize: AppTypography.base,
                      fontWeight: AppTypography.medium,
                      color: fg,
                    ),
                  ),
                  SizedBox(height: AppSpacing.intraGroupXs),
                  Text(
                    (item['quotedPost'] as Map)['content']?.toString() ?? '',
                    style: TextStyle(
                      fontSize: AppTypography.base,
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
              onTap: () => widget.onPostTap(item, 0),
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
                      color: quotedBg,
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
                  GestureDetector(
                    onTap: () {
                      setState(() => _isLiked = !_isLiked);
                      _likeAnimationController.forward(from: 0);
                      _likeAnimationController.reverse();
                      if (_isLiked) widget.onBehavior?.call('like', item);
                    },
                    child: _actionChip(
                      _isLiked ? CupertinoIcons.heart_fill : CupertinoIcons.heart,
                      '${(item['likes'] as int? ?? 0) + (_isLiked ? 1 : 0)}',
                      isDark,
                      iconColor: likeColor,
                    ),
                  ),
                  SizedBox(width: AppSpacing.intraGroupMd),
                  GestureDetector(
                    onTap: () {
                      setState(() => _isBookmarked = !_isBookmarked);
                      if (_isBookmarked) widget.onBehavior?.call('favorite', item);
                    },
                    child: _actionChipWidget(
                      AppStarIcon(
                        size: AppSpacing.iconMedium,
                        color: bookmarkColor,
                      ),
                      '${((item['bookmarks'] ?? item['saves'] ?? 0) as num).toInt() + (_isBookmarked ? 1 : 0)}',
                      isDark,
                    ),
                  ),
                  SizedBox(width: AppSpacing.intraGroupMd),
                  GestureDetector(
                    onTap: () => widget.onCommentTap?.call(item),
                    child: _actionChipWidget(
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
                  ),
                ],
              ),
              const Spacer(),
              GestureDetector(
                onTap: () => widget.onShareTap?.call(item),
                child: _actionChip(CupertinoIcons.arrowshape_turn_up_right, UITextConstants.share, isDark),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _actionChip(IconData icon, String count, bool isDark, {Color? iconColor}) {
    final muted = AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: AppSpacing.iconMedium, color: iconColor ?? muted),
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
  final bool isFirst;
  final VoidCallback onTap;
  final VoidCallback onUserTap;

  const _ArticleCardPlaceholder({
    required this.article,
    required this.isDark,
    this.isFirst = false,
    required this.onTap,
    required this.onUserTap,
  });

  @override
  Widget build(BuildContext context) {
    final fg = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final muted = AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    final author = article['author'] as Map<String, dynamic>? ?? {};
    final stats = article['stats'] as Map<String, dynamic>? ?? {};

    final borderRadius = isFirst
        ? BorderRadius.only(
            bottomLeft: Radius.circular(AppSpacing.borderRadius),
            bottomRight: Radius.circular(AppSpacing.borderRadius),
          )
        : BorderRadius.circular(AppSpacing.borderRadius);

    return InkWell(
      onTap: onTap,
      child: Container(
        padding: EdgeInsets.symmetric(vertical: AppSpacing.md.h),
        decoration: BoxDecoration(
          color: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
          borderRadius: borderRadius,
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
                  ' ${UITextConstants.share}',
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

/// 竖滑整屏视频、顶栏/右侧互动栏/左下文案与音乐。
///
/// [theaterModeTapToToggle] 语义：
/// - **true**（剧场模式）：点击视频区域可切换 overlay（顶栏、右侧栏、左下文案）显隐，
///   宿主可在此回调中联动底部导航等；适用于独立全屏剧场/播放器场景。
/// - **false**（频道流模式）：overlay 常显，点击不触发切换；底部导航仅由宿主按「是否在视频」控制。
///   适用于发现页视频频道等列表流场景。
class _VideoImmersionView extends StatefulWidget {
  const _VideoImmersionView({
    required this.categories,
    required this.activeTab,
    required this.videos,
    required this.isUIVisible,
    required this.theaterModeTapToToggle,
    required this.onTabChange,
    required this.onToggleUI,
    required this.onUserClick,
    required this.onAssistantTap,
    this.onCommentTap,
    this.onShareTap,
  });

  final List<Map<String, String>> categories;
  final String activeTab;
  final List<Map<String, dynamic>> videos;
  final bool isUIVisible;
  /// 是否启用「点击视频区域切换 overlay」的剧场模式；false 时 overlay 常显、点击无切换。
  final bool theaterModeTapToToggle;
  final void Function(String id) onTabChange;
  final VoidCallback onToggleUI;
  final void Function(String userId) onUserClick;
  final VoidCallback onAssistantTap;
  final void Function(BuildContext context, dynamic post)? onCommentTap;
  final void Function(BuildContext context, dynamic post)? onShareTap;

  @override
  State<_VideoImmersionView> createState() => _VideoImmersionViewState();
}

class _VideoImmersionViewState extends State<_VideoImmersionView>
    with TickerProviderStateMixin {
  late PageController _pageController;
  final Set<int> _likedIndexes = {};
  final Set<int> _savedIndexes = {};
  final Set<int> _followedIndexes = {};
  late AnimationController _likeAnimationController;
  late AnimationController _bookmarkAnimationController;
  late Animation<double> _likeScaleAnimation;
  late Animation<double> _bookmarkScaleAnimation;

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
    _likeAnimationController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 200),
    );
    _bookmarkAnimationController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 200),
    );
    _likeScaleAnimation = TweenSequence<double>(
      <TweenSequenceItem<double>>[
        TweenSequenceItem(
          tween: Tween<double>(begin: 1.0, end: 1.2)
              .chain(CurveTween(curve: Curves.easeOut)),
          weight: 50,
        ),
        TweenSequenceItem(
          tween: Tween<double>(begin: 1.2, end: 1.0)
              .chain(CurveTween(curve: Curves.easeIn)),
          weight: 50,
        ),
      ],
    ).animate(_likeAnimationController);
    _bookmarkScaleAnimation = TweenSequence<double>(
      <TweenSequenceItem<double>>[
        TweenSequenceItem(
          tween: Tween<double>(begin: 1.0, end: 1.2)
              .chain(CurveTween(curve: Curves.easeOut)),
          weight: 50,
        ),
        TweenSequenceItem(
          tween: Tween<double>(begin: 1.2, end: 1.0)
              .chain(CurveTween(curve: Curves.easeIn)),
          weight: 50,
        ),
      ],
    ).animate(_bookmarkAnimationController);
  }

  @override
  void dispose() {
    _pageController.dispose();
    _likeAnimationController.dispose();
    _bookmarkAnimationController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      color: Colors.black,
      child: Stack(
        fit: StackFit.expand,
        children: [
          // 视频仅从状态栏下开始，不侵入状态栏；仅侵入顶部工具栏（透明透出视频）
          Positioned(
            top: MediaQuery.of(context).padding.top,
            left: 0,
            right: 0,
            bottom: 0,
            child: GestureDetector(
              behavior: HitTestBehavior.translucent,
              onHorizontalDragEnd: _onPrimaryDragEnd,
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
                    onTap: widget.theaterModeTapToToggle ? widget.onToggleUI : null,
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
                            bottom: AppSpacing.interGroupMd +
                                MediaQuery.of(context).padding.bottom,
                            child: GestureDetector(
                              onTap: () {},
                              behavior: HitTestBehavior.opaque,
                              child: Column(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  GestureDetector(
                                    onTap: () => widget.onUserClick(authorId),
                                    child: SizedBox(
                                      width: AppSpacing.followButtonWidth,
                                      child: Stack(
                                        clipBehavior: Clip.none,
                                        alignment: Alignment.center,
                                        children: [
                                          CircleAvatar(
                                            radius: AppSpacing.buttonHeight / 2,
                                            backgroundColor: Colors.white,
                                            backgroundImage: NetworkImage(
                                              author['avatar'] as String? ?? '',
                                            ),
                                          ),
                                          if (!_followedIndexes.contains(index))
                                            Positioned(
                                              left: 0,
                                              right: 0,
                                              bottom: -AppSpacing.buttonHeightXs /
                                                  2,
                                              child: Center(
                                                child: IntrinsicWidth(
                                                  child: GestureDetector(
                                                    onTap: () => setState(() {
                                                      _followedIndexes.add(index);
                                                    }),
                                                    child: Container(
                                                      padding:
                                                          AppSpacing.buttonPaddingCompact(
                                                        context,
                                                        DesignSemanticConstants.sm,
                                                      ),
                                                      height: AppSpacing
                                                          .buttonHeightForSizeCompact(
                                                        DesignSemanticConstants.sm,
                                                      ),
                                                      decoration: BoxDecoration(
                                                        color:
                                                            AppColors.primaryColor,
                                                        borderRadius:
                                                            BorderRadius.circular(
                                                          AppSpacing
                                                              .circularBorderRadius,
                                                        ),
                                                      ),
                                                      child: Center(
                                                        child: Text(
                                                          '+ ${UITextConstants.follow}',
                                                          style: TextStyle(
                                                            fontSize:
                                                                AppTypography.sm,
                                                            fontWeight:
                                                                AppTypography.medium,
                                                            color: AppColors.white,
                                                          ),
                                                          overflow:
                                                              TextOverflow.clip,
                                                          maxLines: 1,
                                                        ),
                                                      ),
                                                    ),
                                                  ),
                                                ),
                                              ),
                                            ),
                                        ],
                                      ),
                                    ),
                                  ),
                                  SizedBox(height: AppSpacing.interGroupLg),
                                  _videoAction(
                                    CupertinoIcons.heart,
                                    isLiked,
                                    '${(int.tryParse('${post['likes'] ?? ''}') ?? 0) + (isLiked ? 1 : 0)}',
                                    () {
                                      setState(() {
                                        if (_likedIndexes.contains(index)) {
                                          _likedIndexes.remove(index);
                                        } else {
                                          _likedIndexes.add(index);
                                        }
                                      });
                                      _likeAnimationController.forward(from: 0);
                                    },
                                    scaleAnimation: _likeScaleAnimation,
                                  ),
                                  _videoActionWidget(
                                    AppStarIcon(
                                      size: AppSpacing.iconMedium,
                                      filled: _savedIndexes.contains(index),
                                      color: _savedIndexes.contains(index)
                                          ? AppColors.warning
                                          : Colors.white.withValues(alpha: 0.78),
                                    ),
                                    UITextConstants.bookmarks,
                                    () {
                                      setState(() {
                                        if (_savedIndexes.contains(index)) {
                                          _savedIndexes.remove(index);
                                        } else {
                                          _savedIndexes.add(index);
                                        }
                                      });
                                      _bookmarkAnimationController.forward(from: 0);
                                    },
                                    scaleAnimation: _bookmarkScaleAnimation,
                                  ),
                                  _videoActionWidget(
                                    AppBubbleIcon(
                                      size: AppSpacing.iconMedium,
                                      color: Colors.white.withValues(alpha: 0.78),
                                    ),
                                    '${post['comments'] ?? ''}',
                                    () => widget.onCommentTap?.call(context, post),
                                  ),
                                  _videoActionWidget(
                                    Icon(
                                      CupertinoIcons.arrowshape_turn_up_right,
                                      size: AppSpacing.iconMedium,
                                      color: Colors.white.withValues(alpha: 0.78),
                                    ),
                                    UITextConstants.share,
                                    () => widget.onShareTap?.call(context, post),
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
          ),
          Positioned(
            top: 0,
            left: 0,
            right: 0,
            child: SafeArea(
              top: true,
              bottom: false,
              child: AnimatedOpacity(
                opacity: widget.isUIVisible ? 1 : 0,
                duration: const Duration(milliseconds: 200),
                child: CenteredScrollableTabBar(
                  tabs: widget.categories
                      .map((c) => TabItem(id: c['id']!, label: c['label']!))
                      .toList(growable: false),
                  activeTab: widget.activeTab,
                  isDark: true,
                  transparentBackground: true,
                  leftAlignedCompactMode: true,
                  onTabChange: (id) {
                    if (id != 'video') widget.onTabChange(id);
                  },
                  onHorizontalDragEnd: _onPrimaryDragEnd,
                  trailingActions: [
                    IconButton(
                      tooltip: UITextConstants.assistantEntryFind,
                      icon: AssistantAvatar(radius: AppSpacing.iconMedium / 2),
                      onPressed: widget.onAssistantTap,
                      style: IconButton.styleFrom(
                        minimumSize: Size.square(AppSpacing.iconButtonMinSizeSm),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _videoAction(
    IconData icon,
    bool filled,
    String label,
    VoidCallback onTap, {
    Animation<double>? scaleAnimation,
  }) {
    final iconToken = AppSpacing.semantic[DesignSemanticConstants.intraGroup]?[
            DesignSemanticConstants.xs] ??
        AppSpacing.intraGroupXs;
    final iconWidget = Icon(
      icon == CupertinoIcons.heart
          ? (filled ? CupertinoIcons.heart_fill : CupertinoIcons.heart)
          : icon,
      color: filled
          ? AppColors.error
          : Colors.white.withValues(alpha: 0.78),
      size: AppSpacing.iconMedium,
    );
    return Padding(
      padding: EdgeInsets.only(bottom: AppSpacing.interGroupMd),
      child: GestureDetector(
        onTap: onTap,
        behavior: HitTestBehavior.opaque,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            scaleAnimation != null
                ? ScaleTransition(
                    scale: scaleAnimation,
                    child: iconWidget,
                  )
                : iconWidget,
            SizedBox(height: iconToken),
            Text(
              label,
              style: TextStyle(
                fontSize: AppTypography.sm,
                fontWeight: AppTypography.bold,
                color: Colors.white,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _videoActionWidget(
    Widget iconWidget,
    String label,
    VoidCallback onTap, {
    Animation<double>? scaleAnimation,
  }) {
    final iconToken = AppSpacing.semantic[DesignSemanticConstants.intraGroup]?[
            DesignSemanticConstants.xs] ??
        AppSpacing.intraGroupXs;
    final child = scaleAnimation != null
        ? ScaleTransition(
            scale: scaleAnimation,
            child: iconWidget,
          )
        : iconWidget;
    return Padding(
      padding: EdgeInsets.only(bottom: AppSpacing.interGroupMd),
      child: GestureDetector(
        onTap: onTap,
        behavior: HitTestBehavior.opaque,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            child,
            SizedBox(height: iconToken),
            Text(
              label,
              style: TextStyle(
                fontSize: AppTypography.sm,
                fontWeight: AppTypography.bold,
                color: Colors.white,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
