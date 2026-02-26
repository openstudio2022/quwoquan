// ignore_for_file: unnecessary_non_null_assertion
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_staggered_grid_view/flutter_staggered_grid_view.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/components/comment_system/comment_viewer_modal.dart';
import 'package:quwoquan_app/components/comment_system/comment_models.dart';
import 'package:quwoquan_app/components/more_actions_popup/more_action_popup.dart';
import 'package:quwoquan_app/components/more_actions_popup/configs/media_post_config.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/models/user_profile_route_extra.dart';
import 'package:quwoquan_app/ui/content/post_summary_view.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/discovery/providers/discovery_feed_provider.dart';
import 'package:quwoquan_app/components/navigation/tab_navigation.dart';
import 'package:quwoquan_app/components/navigation/centered_scrollable_tab_bar.dart';
import 'package:quwoquan_app/components/assistant/assistant_avatar.dart';
import 'package:quwoquan_app/features/assistant/context/assistant_open_context.dart';
import 'package:quwoquan_app/features/assistant/widgets/assistant_half_sheet.dart';
import 'package:quwoquan_app/cloud/content/generated/content_ui_config.g.dart';

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

  @override
  bool get wantKeepAlive => true;

  /// 一级分类从 ContentUIConfig.discoveryTabs 驱动，顺序/label/contentType 由 codegen 管理。
  List<Map<String, String>> get _categories => ContentUIConfig.discoveryTabs
      .map((tab) => <String, String>{'id': tab.id, 'label': _tabLabelFor(tab.labelKey)})
      .toList(growable: false);

  /// Maps labelKey (from ui_config.yaml) to a localized display string.
  static String _tabLabelFor(String labelKey) {
    switch (labelKey) {
      case 'tab_photo': return UITextConstants.discoveryTabPhoto;
      case 'tab_video': return UITextConstants.discoveryTabVideo;
      case 'tab_moment': return UITextConstants.discoveryTabMoment;
      case 'tab_article': return UITextConstants.discoveryTabArticle;
      default: return labelKey;
    }
  }

  DiscoveryTabConfig? _tabConfigFor(String tabId) =>
      ContentUIConfig.discoveryTabs.cast<DiscoveryTabConfig?>().firstWhere(
        (t) => t!.id == tabId,
        orElse: () => null,
      );

  bool get _isVideoMode =>
      _tabConfigFor(_activeType)?.layout == 'full_width_vertical_pager';

  List<String> get _primaryTabIds =>
      _categories.map((category) => category['id']!).toList(growable: false);

  void _setActiveType(String id) {
    setState(() => _activeType = id);
    _ensureFeedLoaded(id);
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
    final contentId = post is PostBaseDto
        ? post.id
        : (post is Map ? (post['id']?.toString() ?? '') : '');
    if (contentId.isEmpty) return;
    ref.read(behaviorRepositoryProvider).reportSingle(
      contentId: contentId,
      action: action,
      tags: const <String>[],
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
        _ensureFeedLoaded(id);
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

  /// 视频沉浸：竖滑列表、顶栏/右侧栏/左下文案常显；使用 discoveryFeedProvider 共享 feed
  Widget _buildVideoImmersionView(bool isDark, {String tabId = 'video'}) {
    final feedMap = ref.watch(discoveryFeedMapProvider);
    final feedAsync = ref.watch(discoveryFeedProvider(tabId));
    final fallbackRaw = ref.watch(appContentRepositoryProvider).discoveryVideoData;
    final dtos = feedAsync.value?.items ??
        fallbackRaw.map(postBaseDtoFromMap).toList(growable: false);
    final videos = dtos;
    if (!feedMap.containsKey(tabId)) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        ref.read(discoveryFeedMapProvider.notifier).load(tabId);
      });
    }
    if (feedAsync.isLoading && videos.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }
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
      onUserClick: (userId, {String? avatarUrl, String? displayName, String? backgroundUrl}) {
        context.push(
          '/user/$userId',
          extra: UserProfileRouteExtra(
            avatar: avatarUrl,
            displayName: displayName,
            backgroundImage: backgroundUrl,
          ),
        );
      },
      onAssistantTap: _openAssistantHalfSheet,
      onCommentTap: _onMomentCommentTap,
      onShareTap: _onMomentShareTap,
      followingUsers: ref.watch(discoveryStateProvider).followingUsers,
      onFollowClick: (authorId, _) =>
          ref.read(discoveryStateProvider).toggleFollow(authorId),
      onVideoTap: (post, index) {
        _onPostTap(post, index, feedPosts: videos.toList(), category: tabId);
      },
    );
  }

  Widget _buildContentForTab(String tabId, bool isDark) {
    switch (_tabConfigFor(tabId)?.layout) {
      case 'full_width_vertical_pager':
        return _buildVideoImmersionView(isDark, tabId: tabId);
      case 'list_with_optional_media':
        return _buildMomentContent(isDark, tabId: tabId);
      case 'list_with_cover':
        return _buildArticleContent(isDark, tabId: tabId);
      default:
        return _buildPhotoContent(isDark, tabId: tabId);
    }
  }

  double _contentHorizontalPadding(BuildContext context) =>
      AppSpacing.feedContentHorizontal(context);

  Widget _buildMomentContent(bool isDark, {String tabId = 'moment'}) {
    final feedMap = ref.watch(discoveryFeedMapProvider);
    final feedAsync = ref.watch(discoveryFeedProvider(tabId));
    final fallbackRaw = ref.watch(appContentRepositoryProvider).discoveryMomentData;
    final dtos = feedAsync.value?.items ??
        fallbackRaw.map(postBaseDtoFromMap).toList(growable: false);
    final moments = dtos.whereType<MomentPostDto>().toList(growable: false);
    final horizontal = _contentHorizontalPadding(context);
    if (!feedMap.containsKey(tabId)) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        ref.read(discoveryFeedMapProvider.notifier).load(tabId);
      });
    }
    if (feedAsync.isLoading && moments.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }
    return ListView.builder(
      padding: EdgeInsets.only(
        top: AppSpacing.containerSm,
        bottom: MediaQuery.of(context).padding.bottom +
            AppSpacing.bottomNavHeight +
            AppSpacing.interGroupMd,
      ),
      itemCount: moments.length,
      itemBuilder: (context, index) {
        final dto = moments[index];
        final isFirst = index == 0;
        return Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: EdgeInsets.symmetric(horizontal: horizontal),
              child: _MomentPostCard(
                item: dto,
                isDark: isDark,
                isFirst: isFirst,
                onUserTap: (id) {
                  context.push('/user/$id', extra: <String, String?>{
                    'avatar': dto.avatarUrl,
                    'displayName': dto.displayName,
                    'backgroundImage': dto.authorBackgroundUrl,
                  });
                },
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
  }

  Widget _buildArticleContent(bool isDark, {String tabId = 'article'}) {
    final feedMap = ref.watch(discoveryFeedMapProvider);
    final feedAsync = ref.watch(discoveryFeedProvider(tabId));
    final fallbackRaw = ref.watch(appContentRepositoryProvider).discoveryArticleData;
    final dtos = feedAsync.value?.items ??
        fallbackRaw.map(postBaseDtoFromMap).toList(growable: false);
    final articles = dtos.whereType<ArticlePostDto>().toList(growable: false);
    final horizontal = _contentHorizontalPadding(context);
    if (!feedMap.containsKey(tabId)) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        ref.read(discoveryFeedMapProvider.notifier).load(tabId);
      });
    }
    if (feedAsync.isLoading && articles.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }
    return ListView.builder(
      padding: EdgeInsets.only(
        top: AppSpacing.containerSm,
        bottom: MediaQuery.of(context).padding.bottom +
            AppSpacing.bottomNavHeight +
            AppSpacing.interGroupMd,
      ),
      itemCount: articles.length,
      itemBuilder: (context, index) {
        final dto = articles[index];
        final isFirst = index == 0;
        return Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: EdgeInsets.symmetric(horizontal: horizontal),
              child: _ArticleCardPlaceholder(
                article: dto,
                isDark: isDark,
                isFirst: isFirst,
                onTap: () {
                  _trackBehavior('click', dto);
                  context.push('/article/${dto.id}');  // article route
                },
                onUserTap: () {
                  context.push('/user/${dto.authorId}', extra: <String, String?>{
                    'avatar': dto.avatarUrl,
                    'displayName': dto.displayName,
                    'backgroundImage': dto.authorBackgroundUrl,
                  });
                },
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
  }

  static const double _photoMinAspectRatio = 6 / 19; // 最大高宽比限制 6:19

  double? _aspectRatioFromImageUrl(String url) {
    if (url.isEmpty) return null;
    final uri = Uri.tryParse(url);
    if (uri == null) return null;
    final w = double.tryParse(uri.queryParameters['w'] ?? '');
    final h = double.tryParse(uri.queryParameters['h'] ?? '');
    if (w != null && h != null && h > 0) return w / h;
    return null;
  }

  double _photoItemHeight(double cardWidth, PhotoPostDto post, int index) {
    double ratio = post.aspectRatio ?? 0;
    if (ratio <= 0 && post.imageUrls.isNotEmpty) {
      final fromImage = _aspectRatioFromImageUrl(post.imageUrls.first);
      if (fromImage != null && fromImage > 0) ratio = fromImage;
    }
    if (ratio <= 0) {
      final fromCover = _aspectRatioFromImageUrl(post.coverUrl);
      if (fromCover != null && fromCover > 0) ratio = fromCover;
    }
    if (ratio <= 0) {
      ratio = 0.75 + (post.id.hashCode % 7) * 0.15;
    }
    if (ratio < _photoMinAspectRatio) ratio = _photoMinAspectRatio;
    return cardWidth / ratio;
  }

  static int? _displayLikesCount(DiscoveryState homeState, PostBaseDto post) {
    final n = homeState.getPostLikesCount(post.id);
    if (n > 0) return n;
    return post.likeCount > 0 ? post.likeCount : null;
  }

  static int? _displayBookmarksCount(DiscoveryState homeState, PostBaseDto post) {
    final n = homeState.getPostBookmarksCount(post.id);
    if (n > 0) return n;
    return post.favoriteCount > 0 ? post.favoriteCount : null;
  }

  Widget _buildPhotoContent(bool isDark, {String tabId = 'photo'}) {
    final homeState = ref.watch(discoveryStateProvider);
    final feedMap = ref.watch(discoveryFeedMapProvider);
    final feedAsync = ref.watch(discoveryFeedProvider(tabId));
    final fallbackRaw = ref.watch(appContentRepositoryProvider).discoveryPhotoData;
    final dtos = feedAsync.value?.items ??
        fallbackRaw.map(postBaseDtoFromMap).toList(growable: false);
    final photos = dtos.whereType<PhotoPostDto>().toList(growable: false);
    final screenWidth = MediaQuery.of(context).size.width;
    final horizontal = _contentHorizontalPadding(context);
    final horizontalPadding = horizontal * 2;
    final gap = AppSpacing.interGroupSm;
    final cardWidth = (screenWidth - horizontalPadding - gap) / 2;

    // 仅在没有该 tab 的 feed 时拉取；从图片浏览返回后复用已有 feed，不刷新
    if (!feedMap.containsKey(tabId)) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        ref.read(discoveryFeedMapProvider.notifier).load(tabId);
      });
    }
    if (feedAsync.isLoading && photos.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }
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
            childCount: photos.length,
            itemBuilder: (context, index) {
              final post = photos[index];
              final height = _photoItemHeight(cardWidth, post, index);
              final likesDisplay = _displayLikesCount(homeState, post);
              final bookmarksDisplay = _displayBookmarksCount(homeState, post);
              return SizedBox(
                height: height,
                child: _DiscoveryItemCard(
                  post: post,
                  onTap: () => _onPostTap(post, index, feedPosts: photos, category: tabId),
                  isLiked: homeState.likedPosts.contains(post.id),
                  isSaved: homeState.savedPosts.contains(post.id),
                  likesCount: likesDisplay,
                  bookmarksCount: bookmarksDisplay,
                ),
              );
            },
          ),
        ),
      ],
    );
  }

  /// 触发指定 tab 的 feed 加载（若已有数据则跳过）
  void _ensureFeedLoaded(String tabId) {
    final feedMap = ref.read(discoveryFeedMapProvider);
    if (!feedMap.containsKey(tabId)) {
      ref.read(discoveryFeedMapProvider.notifier).load(tabId);
    }
  }


  void _onPostTap(
    PostBaseDto post,
    int mediaIndex, {
    List<PostBaseDto>? feedPosts,
    String? category,
  }) {
    _trackBehavior('click', post);
    // Resolve tab config by matching post.type (API ContentType) against ContentUIConfig.
    final tabConfig = ContentUIConfig.discoveryTabs.cast<DiscoveryTabConfig?>().firstWhere(
      (t) => t!.contentType == post.type,
      orElse: () => null,
    );
    if (tabConfig?.layout == 'list_with_cover') {
      context.push('/article/${post.id}');
      return;
    }
    final postViews = feedPosts?.map(PostSummaryView.fromDto).toList();
    if (tabConfig?.layout == 'full_width_vertical_pager') {
      if (postViews != null && postViews.isNotEmpty) {
        context.push(
          '/video-viewer/$mediaIndex',
          extra: MediaViewerExtra(
            posts: postViews,
            initialIndex: mediaIndex,
            category: category ?? tabConfig!.id,
          ),
        );
      } else {
        context.push('/video-viewer/$mediaIndex');
      }
      return;
    }
    if (postViews != null && postViews.isNotEmpty) {
      context.push(
        '/media-viewer/photo/$mediaIndex',
        extra: MediaViewerExtra(
          posts: postViews,
          initialIndex: mediaIndex,
          category: category ?? (tabConfig?.id ?? 'photo'),
        ),
      );
    } else {
      context.push('/media-viewer/photo/$mediaIndex');
    }
  }

  void _onMomentCommentTap(BuildContext context, dynamic post) {
    final postId = post is PostBaseDto
        ? post.id
        : (post is Map ? post['id']?.toString() ?? '' : '');
    CommentViewer.showModal(
      context: context,
      postId: postId,
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

String _toTimeAgo(DateTime time, AppLocalizations l10n) {
  final delta = DateTime.now().difference(time).inHours;
  if (delta < 1) return l10n.justNow;
  if (delta < 24) return l10n.hoursAgoTemplate(delta);
  return '${time.month}-${time.day}';
}

String _toDate(DateTime time) {
  return '${time.year}-${time.month.toString().padLeft(2, '0')}-${time.day.toString().padLeft(2, '0')}';
}

/// 微趣卡片：1:1 复制 MomentPost.tsx 结构（简化版，后续补全转发引用、九宫格等）
class _MomentPostCard extends StatefulWidget {
  final MomentPostDto item;
  final bool isDark;
  final bool isFirst;
  final void Function(String) onUserTap;
  final void Function(PostBaseDto, int) onPostTap;
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
                onTap: () => widget.onUserTap(item.authorId),
                child: CircleAvatar(
                  radius: AppSpacing.avatarUserMd / 2,
                  backgroundImage: NetworkImage(item.avatarUrl),
                ),
              ),
              SizedBox(width: AppSpacing.sm.w),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      item.displayName,
                      style: TextStyle(
                        fontSize: AppTypography.base,
                        fontWeight: AppTypography.medium,
                        color: fg,
                      ),
                    ),
                    SizedBox(height: AppSpacing.intraGroupXs / 2),
                    Text(
                      _toTimeAgo(item.createdAt, context.l10n),
                      style: TextStyle(
                        fontSize: AppTypography.sm,
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
            item.body,
            style: TextStyle(
              fontSize: AppTypography.lg,
              color: fg,
              height: 1.4,
            ),
            maxLines: 10,
            overflow: TextOverflow.ellipsis,
          ),
          if (item.hasImages) ...[
            SizedBox(height: AppSpacing.interGroupXs),
            GestureDetector(
              onTap: () => widget.onPostTap(item, 0),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
                child: AspectRatio(
                  aspectRatio: 4 / 3,
                  child: Image.network(
                    item.imageUrls.first,
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
                      '${item.likeCount + (_isLiked ? 1 : 0)}',
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
                      '${item.favoriteCount + (_isBookmarked ? 1 : 0)}',
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
                      '${item.commentCount}',
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
  final ArticlePostDto article;
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
                    backgroundImage: NetworkImage(article.avatarUrl),
                  ),
                ),
                SizedBox(width: AppSpacing.interGroupXs),
                Text(
                  article.displayName,
                  style: TextStyle(
                    fontSize: AppTypography.base,
                    fontWeight: AppTypography.medium,
                    color: fg,
                  ),
                ),
                const Spacer(),
                Text(
                  _toDate(article.createdAt),
                  style: TextStyle(fontSize: AppTypography.base, color: muted),
                ),
              ],
            ),
            SizedBox(height: AppSpacing.intraGroupSm),
            Text(
              article.type,
              style: TextStyle(
                fontSize: AppTypography.sm,
                color: AppColors.primaryColor,
                fontWeight: AppTypography.bold,
              ),
            ),
            SizedBox(height: AppSpacing.intraGroupXs),
            Text(
              article.title,
              style: TextStyle(
                fontSize: AppTypography.lg,
                fontWeight: AppTypography.semiBold,
                color: fg,
              ),
            ),
            SizedBox(height: AppSpacing.intraGroupXs),
            Text(
              article.body,
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
                      ' ${article.likeCount} ',
                      style: TextStyle(fontSize: AppTypography.base, color: muted),
                    ),
                    AppStarIcon(size: AppSpacing.iconMedium, color: muted),
                    Text(
                      ' ${article.favoriteCount} ',
                      style: TextStyle(fontSize: AppTypography.base, color: muted),
                    ),
                    AppBubbleIcon(size: AppSpacing.iconMedium, color: muted),
                    Text(
                      ' ${article.commentCount} ',
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

/// 美图/视频卡片：缩略图用 CachedNetworkImage，占位与降级；多图角标、视频 Play 角标；与详情一致的点赞/收藏状态
class _DiscoveryItemCard extends StatelessWidget {
  final PostBaseDto post;
  final VoidCallback onTap;
  final bool isLiked;
  final bool isSaved;
  final int? likesCount;
  final int? bookmarksCount;

  const _DiscoveryItemCard({
    required this.post,
    required this.onTap,
    this.isLiked = false,
    this.isSaved = false,
    this.likesCount,
    this.bookmarksCount,
  });

  @override
  Widget build(BuildContext context) {
    String thumb;
    int imageCount;
    if (post is PhotoPostDto) {
      final photo = post as PhotoPostDto;
      thumb = photo.coverUrl.trim().isNotEmpty
          ? photo.coverUrl
          : (photo.imageUrls.isNotEmpty ? photo.imageUrls.first : '');
      imageCount = photo.imageUrls.length;
    } else if (post is VideoPostDto) {
      thumb = (post as VideoPostDto).thumbnailUrl.trim();
      imageCount = 1;
    } else {
      thumb = '';
      imageCount = 1;
    }
    final isVideo = post.type == 'video';

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
              child: thumb.isEmpty
                  ? Container(
                      color: Colors.grey.shade300,
                      child: Icon(
                        Icons.image_not_supported_outlined,
                        size: AppSpacing.largeButtonSize,
                        color: Colors.grey.shade600,
                      ),
                    )
                  : CachedNetworkImage(
                      imageUrl: thumb,
                      fit: BoxFit.cover,
                      placeholder: (context, url) => Container(
                        color: Colors.grey.shade300,
                        child: Center(
                          child: SizedBox(
                            width: AppSpacing.largeButtonSize,
                            height: AppSpacing.largeButtonSize,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: Colors.grey.shade600,
                            ),
                          ),
                        ),
                      ),
                      errorWidget: (context, url, error) => Container(
                        color: Colors.grey.shade300,
                        child: Icon(
                          Icons.image_not_supported_outlined,
                          size: AppSpacing.largeButtonSize,
                          color: Colors.grey.shade600,
                        ),
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
            Positioned(
              left: 8,
              bottom: 8,
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    isLiked ? Icons.favorite : Icons.favorite_border,
                    size: AppSpacing.iconSmall,
                    color: isLiked ? Colors.red : Colors.white.withValues(alpha: 0.9),
                  ),
                  if (likesCount != null && likesCount! > 0) ...[
                    SizedBox(width: AppSpacing.xs),
                    Text(
                      '$likesCount',
                      style: TextStyle(
                        fontSize: AppTypography.xs,
                        color: Colors.white.withValues(alpha: 0.9),
                      ),
                    ),
                  ],
                  SizedBox(width: AppSpacing.intraGroupSm),
                  Icon(
                    isSaved ? Icons.bookmark : Icons.bookmark_border,
                    size: AppSpacing.iconSmall,
                    color: isSaved ? Colors.amber : Colors.white.withValues(alpha: 0.9),
                  ),
                  if (bookmarksCount != null && bookmarksCount! > 0) ...[
                    SizedBox(width: AppSpacing.xs),
                    Text(
                      '$bookmarksCount',
                      style: TextStyle(
                        fontSize: AppTypography.xs,
                        color: Colors.white.withValues(alpha: 0.9),
                      ),
                    ),
                  ],
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
    this.onVideoTap,
    this.followingUsers,
    this.onFollowClick,
  });

  final List<Map<String, String>> categories;
  final String activeTab;
  final List<PostBaseDto> videos;
  final bool isUIVisible;
  /// 是否启用「点击视频区域切换 overlay」的剧场模式；false 时 overlay 常显、点击无切换。
  final bool theaterModeTapToToggle;
  final void Function(String id) onTabChange;
  final VoidCallback onToggleUI;
  final void Function(String userId, {String? avatarUrl, String? displayName, String? backgroundUrl}) onUserClick;
  final VoidCallback onAssistantTap;
  final void Function(BuildContext context, dynamic post)? onCommentTap;
  final void Function(BuildContext context, dynamic post)? onShareTap;
  final void Function(PostBaseDto post, int index)? onVideoTap;
  final Set<String>? followingUsers;
  final void Function(String authorId, bool isFollowing)? onFollowClick;

  @override
  State<_VideoImmersionView> createState() => _VideoImmersionViewState();
}

class _VideoImmersionViewState extends State<_VideoImmersionView>
    with TickerProviderStateMixin {
  late PageController _pageController;
  final Set<int> _likedIndexes = {};
  final Set<int> _savedIndexes = {};
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
    // Only switch to non-video tabs (video is handled via full-screen pager, not tab switch).
    final nextTab = ContentUIConfig.discoveryTabs.cast<DiscoveryTabConfig?>().firstWhere(
      (t) => t!.id == nextId,
      orElse: () => null,
    );
    if (nextTab?.layout != 'full_width_vertical_pager') {
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
                  final authorId = post.authorId;
                  final authorAvatar = post.avatarUrl;
                  final authorName = post.displayName;
                  final authorBg = post.authorBackgroundUrl;
                  final thumbnail = post is VideoPostDto ? post.thumbnailUrl : '';
                  final isLiked = _likedIndexes.contains(index);
                  return GestureDetector(
                    onTap: () {
                      if (widget.onVideoTap != null) {
                        widget.onVideoTap!(post, index);
                      } else if (widget.theaterModeTapToToggle) {
                        widget.onToggleUI();
                      }
                    },
                    child: Stack(
                      fit: StackFit.expand,
                      children: [
                        // 背景图
                        Image.network(
                          thumbnail,
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
                                    onTap: () => widget.onUserClick(
                                      authorId,
                                      avatarUrl: authorAvatar,
                                      displayName: authorName,
                                      backgroundUrl: authorBg,
                                    ),
                                    child: SizedBox(
                                      width: AppSpacing.followButtonWidth,
                                      child: Stack(
                                        clipBehavior: Clip.none,
                                        alignment: Alignment.center,
                                        children: [
                                          CircleAvatar(
                                            radius: AppSpacing.buttonHeight / 2,
                                            backgroundColor: Colors.white,
                                            backgroundImage: NetworkImage(authorAvatar),
                                          ),
                                          if (!(widget.followingUsers?.contains(authorId) ?? false))
                                            Positioned(
                                              left: 0,
                                              right: 0,
                                              bottom: -AppSpacing.buttonHeightXs /
                                                  2,
                                              child: Center(
                                                child: IntrinsicWidth(
                                                  child: GestureDetector(
                                                    onTap: () {
                                                      widget.onFollowClick?.call(authorId, true);
                                                    },
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
                                    '${post.likeCount + (isLiked ? 1 : 0)}',
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
                                    '${post.commentCount}',
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
                                  onTap: () => widget.onUserClick(
                                    authorId,
                                    avatarUrl: authorAvatar,
                                    displayName: authorName,
                                    backgroundUrl: authorBg,
                                  ),
                                  child: Text(
                                    '@$authorName',
                                    style: TextStyle(
                                      fontSize: AppTypography.lg,
                                      fontWeight: AppTypography.medium,
                                      color: Colors.white,
                                    ),
                                  ),
                                ),
                                SizedBox(height: AppSpacing.intraGroupXs),
                                Text(
                                  post is VideoPostDto ? (post.body ?? '') : '',
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
                                        '${UITextConstants.discovery} • $authorName 创作的原声',
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
                    final tab = ContentUIConfig.discoveryTabs.cast<DiscoveryTabConfig?>().firstWhere(
                      (t) => t!.id == id, orElse: () => null);
                    if (tab?.layout != 'full_width_vertical_pager') widget.onTabChange(id);
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
