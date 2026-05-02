import 'dart:async';

import 'dart:math' as math;
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:photo_view/photo_view.dart';
import 'package:quwoquan_app/core/links/app_public_content_links.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';

import 'package:quwoquan_app/components/settings_conversation/more_actions_popup/configs/media_post_config.dart';
import 'package:quwoquan_app/components/comment_system/comment_viewer.dart';
import 'package:quwoquan_app/components/comment_system/comment_models.dart';
import 'package:quwoquan_app/components/settings_conversation/more_actions_popup/more_action_popup.dart';
import 'package:quwoquan_app/components/media/shared/toolbar/immersive_engagement_bar.dart';
import 'package:quwoquan_app/components/media/shared/toolbar/media_viewer_toolbar.dart';
import 'package:quwoquan_app/components/media/shared/viewer/immersive_viewer_layout.dart';
import 'package:quwoquan_app/components/media/shared/viewer/media_caption_widgets.dart';
import 'package:quwoquan_app/ui/content/post_summary_view.dart';

/// 沉浸式图片查看器 - 基于Figma原型实现
/// 支持与作者主页、评论和帖子的完整联动
class ImmersiveImageViewer extends ConsumerStatefulWidget {
  final bool isOpen;
  final VoidCallback onClose;
  final List<MediaItem> mediaItems;
  final int initialIndex;
  final List<PostSummaryView> posts;
  final int initialPostIndex;

  /// username 必填；avatarUrl、displayName、backgroundUrl 可选，传入后作者页优先展示以与浏览页一致
  final void Function(
    String username, {
    String? avatarUrl,
    String? displayName,
    String? backgroundUrl,
  })
  onUserClick;
  final Function(String, bool)? onFollowClick;
  final Function(PostSummaryView)? onCommentsClick;
  final Function(PostSummaryView)? onMoreClick;
  final Function(PostSummaryView)? onLikeClick;
  final Function(PostSummaryView)? onSaveClick;
  final Function(PostSummaryView)? onShareClick;
  final Set<String>? followingUsers;
  final Set<String>? savedPosts;
  final Set<String>? likedPosts;
  final Function(PostSummaryView)? getPostLikesCount;
  final Function(PostSummaryView)? getPostBookmarksCount;
  final bool isBlocked;
  final String? source; // 'feed' | 'userProfile'
  final Map<String, dynamic>? userProfileData;
  final bool isCommentsOpen;
  final double commentsHeight;
  final bool enableHeroAnimation;
  final Map<String, dynamic>? heroAnimationSource;
  final Function(String)? onHeroAnimationComplete;

  /// 私人助理入口（中间图标，点击跳转助理主页）
  final VoidCallback? onAssistantClick;

  /// 滑动接近末尾时回调（用于加载更多）
  final VoidCallback? onNearEnd;

  /// flat：一维横向（作品/美图）；nested：外垂直（微趣）× 内横向（同微趣图）
  final String layoutMode;

  /// 同微趣内图片索引（nested 模式使用）
  final int initialImageIndex;

  /// 'full'（默认）| 'backOnly'：backOnly 时顶栏仅返回、更多
  final String toolbarMode;

  const ImmersiveImageViewer({
    super.key,
    required this.isOpen,
    required this.onClose,
    required this.mediaItems,
    required this.initialIndex,
    required this.posts,
    required this.initialPostIndex,
    required this.onUserClick,
    this.onFollowClick,
    this.onCommentsClick,
    this.onMoreClick,
    this.onLikeClick,
    this.onSaveClick,
    this.onShareClick,
    this.followingUsers,
    this.savedPosts,
    this.likedPosts,
    this.getPostLikesCount,
    this.getPostBookmarksCount,
    this.isBlocked = false,
    this.source,
    this.userProfileData,
    this.isCommentsOpen = false,
    this.commentsHeight = 0,
    this.enableHeroAnimation = false,
    this.heroAnimationSource,
    this.onHeroAnimationComplete,
    this.onAssistantClick,
    this.onNearEnd,
    this.layoutMode = 'flat',
    this.initialImageIndex = 0,
    this.toolbarMode = 'full',
  });

  @override
  ConsumerState<ImmersiveImageViewer> createState() =>
      _ImmersiveImageViewerState();
}

class _ImmersiveImageViewerState extends ConsumerState<ImmersiveImageViewer>
    with TickerProviderStateMixin {
  late PageController _pageController;
  PageController? _outerPageController;
  final Map<int, PageController> _innerControllers = {};
  late AnimationController _fadeController;
  late AnimationController _controlsController;

  int _currentEntryIndex = 0;
  int _currentPostIndex = 0;
  int _currentImageIndex = 0;
  List<_ViewerImageEntry> _mediaEntries = const <_ViewerImageEntry>[];

  // 本地状态
  bool _isLiked = false;
  bool _isSaved = false;
  bool _isFollowing = false;
  int _likesCount = 0;
  int _savesCount = 0;
  int _commentsCount = 0;
  int _sharesCount = 0;
  bool _showFollowButton = false;
  Timer? _followButtonTimer;
  bool _isPureMode = false;
  final Map<String, bool> _expandedCaptions = {};
  final Map<String, double> _imageAspectRatios = {};
  final Set<String> _resolvingImageAspectRatios = <String>{};

  @override
  void initState() {
    super.initState();
    _rebuildMediaEntries();
    final useNested = widget.layoutMode == 'nested';
    if (useNested && widget.posts.isNotEmpty) {
      _currentPostIndex = widget.initialPostIndex.clamp(
        0,
        widget.posts.length - 1,
      );
      final urls = _collectPostImageUrls(widget.posts[_currentPostIndex]);
      _currentImageIndex = widget.initialImageIndex.clamp(
        0,
        urls.isEmpty ? 0 : urls.length - 1,
      );
      _outerPageController = PageController(initialPage: _currentPostIndex);
    }
    _pageController = PageController(initialPage: _currentEntryIndex);

    _fadeController = AnimationController(
      duration: const Duration(milliseconds: 300),
      vsync: this,
    );

    _controlsController = AnimationController(
      duration: const Duration(milliseconds: 200),
      vsync: this,
    );
    _controlsController.value = 1.0; // 默认显示工具栏

    _initializePostState();
    _startAutoHideTimer();
    _applySystemUiMode();
  }

  @override
  void dispose() {
    _pageController.dispose();
    _outerPageController?.dispose();
    for (final c in _innerControllers.values) {
      c.dispose();
    }
    _innerControllers.clear();
    _fadeController.dispose();
    _controlsController.dispose();
    _followButtonTimer?.cancel();
    _restoreSystemUiMode();
    super.dispose();
  }

  @override
  void didUpdateWidget(ImmersiveImageViewer oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.likedPosts != widget.likedPosts ||
        oldWidget.savedPosts != widget.savedPosts ||
        oldWidget.followingUsers != widget.followingUsers ||
        oldWidget.posts != widget.posts ||
        oldWidget.getPostLikesCount != widget.getPostLikesCount ||
        oldWidget.getPostBookmarksCount != widget.getPostBookmarksCount) {
      _rebuildMediaEntries(keepCurrent: true);
      _initializePostState();
    }
  }

  _ViewerImageEntry? get _currentEntry =>
      (_mediaEntries.isNotEmpty && _currentEntryIndex < _mediaEntries.length)
      ? _mediaEntries[_currentEntryIndex]
      : null;

  int get _effectivePostIndex => widget.layoutMode == 'nested'
      ? _currentPostIndex
      : (_currentEntry?.postIndex ?? 0);

  PostSummaryView? get _currentPost =>
      (widget.posts.isNotEmpty && _effectivePostIndex < widget.posts.length)
      ? widget.posts[_effectivePostIndex]
      : null;

  List<String> _collectPostImageUrls(PostSummaryView post) {
    final images = (post.images ?? const <String>[])
        .map((e) => e.trim())
        .where((e) => e.isNotEmpty)
        .toList(growable: false);
    final valid = images
        .where((e) => e.startsWith('http://') || e.startsWith('https://'))
        .toList(growable: false);
    if (valid.isNotEmpty) return valid;
    final thumb =
        post.thumbnail?.trim() ??
        post.thumbnailUrl?.trim() ??
        post.coverUrl?.trim() ??
        '';
    if (thumb.isNotEmpty) return <String>[thumb];
    return const <String>[];
  }

  String? _usernameFromPost(PostSummaryView post) {
    final username = post.authorId;
    return username.isNotEmpty ? username : null;
  }

  void _rebuildMediaEntries({bool keepCurrent = false}) {
    final oldEntry = keepCurrent ? _currentEntry : null;
    final entries = <_ViewerImageEntry>[];
    for (var postIndex = 0; postIndex < widget.posts.length; postIndex++) {
      final post = widget.posts[postIndex];
      final urls = _collectPostImageUrls(post);
      for (var imageIndex = 0; imageIndex < urls.length; imageIndex++) {
        entries.add(
          _ViewerImageEntry(
            postIndex: postIndex,
            imageIndex: imageIndex,
            imageUrl: urls[imageIndex],
          ),
        );
      }
    }
    _mediaEntries = entries;
    if (_mediaEntries.isEmpty) {
      _currentEntryIndex = 0;
      return;
    }
    if (keepCurrent && oldEntry != null) {
      final preserved = _mediaEntries.indexWhere(
        (e) =>
            e.postIndex == oldEntry.postIndex &&
            e.imageIndex == oldEntry.imageIndex,
      );
      if (preserved >= 0) {
        _currentEntryIndex = preserved;
        return;
      }
    }
    final initialPost = widget.initialPostIndex.clamp(
      0,
      widget.posts.length - 1,
    );
    final firstOfPost = _mediaEntries.indexWhere(
      (e) => e.postIndex == initialPost,
    );
    _currentEntryIndex = firstOfPost >= 0 ? firstOfPost : 0;
  }

  void _initializePostState() {
    final currentPost = _currentPost;
    if (currentPost != null) {
      _isLiked = widget.likedPosts?.contains(currentPost.id) ?? false;
      _isSaved = widget.savedPosts?.contains(currentPost.id) ?? false;
      final username = _usernameFromPost(currentPost);
      _isFollowing = username != null
          ? (widget.followingUsers?.contains(username) ?? false)
          : false;
      _likesCount = widget.getPostLikesCount?.call(currentPost) ?? 0;
      _savesCount = widget.getPostBookmarksCount?.call(currentPost) ?? 0;
      _commentsCount = currentPost.commentsCount;
      _sharesCount = currentPost.sharesCount;
      _startFollowDelay();
    }
  }

  void _startFollowDelay() {
    _followButtonTimer?.cancel();
    if (mounted) {
      setState(() => _showFollowButton = false);
    } else {
      _showFollowButton = false;
    }
    _followButtonTimer = Timer(const Duration(seconds: 3), () {
      if (!mounted) return;
      setState(() => _showFollowButton = true);
    });
  }

  void _startAutoHideTimer() {
    // 工具栏始终显示，不自动隐藏（与图片浏览器保持一致）
  }

  void _toggleControls() {
    if (_isPureMode) {
      setState(() => _isPureMode = false);
      _controlsController.forward();
      _applySystemUiMode();
    } else {
      // 先执行淡出动画，动画结束后再更新状态，避免控件被立即移出树导致无淡出效果
      _controlsController.reverse();
      void listener(AnimationStatus status) {
        if (status == AnimationStatus.dismissed) {
          _controlsController.removeStatusListener(listener);
          if (mounted) {
            setState(() => _isPureMode = true);
            _applySystemUiMode();
          }
        }
      }

      _controlsController.addStatusListener(listener);
    }
  }

  void _applySystemUiMode() {
    if (_isPureMode) {
      SystemChrome.setEnabledSystemUIMode(SystemUiMode.immersiveSticky);
      SystemChrome.setSystemUIOverlayStyle(
        const SystemUiOverlayStyle(
          statusBarColor: AppColors.transparent,
          statusBarIconBrightness: Brightness.dark,
          statusBarBrightness: Brightness.light,
          systemNavigationBarColor: AppColors.transparent,
          systemNavigationBarIconBrightness: Brightness.dark,
        ),
      );
      return;
    }

    SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
    SystemChrome.setSystemUIOverlayStyle(
      const SystemUiOverlayStyle(
        statusBarColor: AppColors.transparent,
        statusBarIconBrightness: Brightness.dark,
        statusBarBrightness: Brightness.light,
        systemNavigationBarColor: AppColors.transparent,
        systemNavigationBarIconBrightness: Brightness.dark,
      ),
    );
  }

  void _restoreSystemUiMode() {
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
    SystemChrome.setSystemUIOverlayStyle(
      const SystemUiOverlayStyle(
        statusBarColor: AppColors.transparent,
        statusBarIconBrightness: Brightness.dark,
        statusBarBrightness: Brightness.light,
        systemNavigationBarColor: AppColors.transparent,
        systemNavigationBarIconBrightness: Brightness.dark,
      ),
    );
  }

  void _handlePageChanged(int index) {
    setState(() {
      _currentEntryIndex = index;
    });
    _initializePostState();
    if (widget.onNearEnd != null &&
        _mediaEntries.length > 1 &&
        index >= _mediaEntries.length - 2) {
      widget.onNearEnd!();
    }
  }

  void _handleLikeClick() {
    setState(() {
      _isLiked = !_isLiked;
      if (_isLiked) {
        _likesCount++;
      } else {
        _likesCount = (_likesCount - 1).clamp(0, double.infinity).toInt();
      }
    });

    final currentPost = _currentPost;
    if (currentPost != null) {
      widget.onLikeClick?.call(currentPost);
    }
  }

  void _handleSaveClick() {
    setState(() {
      _isSaved = !_isSaved;
      if (_isSaved) {
        _savesCount++;
      } else {
        _savesCount = (_savesCount - 1).clamp(0, double.infinity).toInt();
      }
    });

    final currentPost = _currentPost;
    if (currentPost != null) {
      widget.onSaveClick?.call(currentPost);
    }
  }

  void _handleFollowClick() {
    final currentPost = _currentPost;
    if (currentPost != null) {
      setState(() {
        _isFollowing = !_isFollowing;
      });
      final username = _usernameFromPost(currentPost);
      if (username == null || username.isEmpty) return;
      widget.onFollowClick?.call(username, _isFollowing);
    }
  }

  void _handleCommentsClick() {
    final currentPost = _currentPost;
    if (currentPost != null) {
      // 显示评论弹窗
      final commentConfig = CommentConfig();

      CommentViewer.showModal(
        context: context,
        postId: currentPost.id.isNotEmpty ? currentPost.id : 'mock_post_id',
        initialComments: [],
        config: commentConfig,
        modalHeight: CommentModalHeight.adaptive,
        onCommentAdded: (commentId) {
          debugPrint('Comment added: $commentId');
        },
        onCommentLiked: (comment) {
          debugPrint('Comment liked: ${comment.id}');
        },
        onReplyAdded: (commentId, replyId) {
          debugPrint('Reply added: $replyId to $commentId');
        },
        onUserTapped: (userId) {
          debugPrint('User tapped: $userId');
        },
        onLoadMoreComments: (postId) {
          debugPrint('Load more comments for post: $postId');
        },
        onClose: () {
          debugPrint('Comment modal closed');
        },
      );
    }
  }

  void _handleMoreClick() {
    final currentPost = _currentPost;
    if (currentPost != null) {
      // 显示更多操作弹窗（1:1 PostActionSheet：复制链接、保存、举报等）
      final config = MediaPostMoreActionConfig(
        onReward: () => debugPrint('Reward post: ${currentPost.id}'),
        onSave: () => _handleSaveClick(),
        onMessage: () => debugPrint('Message user: ${currentPost.authorId}'),
        onCopyLink: () {
          final link = AppPublicContentLinks.postWebUrl(currentPost.id);
          Clipboard.setData(ClipboardData(text: link));
          if (mounted) {
            AppToast.show(context, UITextConstants.copyLink);
          }
        },
        onViewOriginal: () => debugPrint('View original: ${currentPost.id}'),
        onFontSettings: () => debugPrint('Font settings'),
        onThemeToggle: () => debugPrint('Theme toggle'),
        onFeedback: () => debugPrint('Feedback'),
        onNotInterested: () => debugPrint('Not interested'),
        onBlockUser: () => debugPrint('Block user: ${currentPost.authorId}'),
        onReport: () => debugPrint('Report post: ${currentPost.id}'),
      );

      MoreActionPopup.show(context: context, config: config);
    }
  }

  void _handleShareClick() {
    final currentPost = _currentPost;
    if (currentPost != null) {
      widget.onShareClick?.call(currentPost);
    }
  }

  void _handleAuthorTap() {
    final currentPost = _currentPost;
    if (currentPost == null) return;
    final username = currentPost.authorId;
    if (username.isEmpty) return;
    final avatarUrl = currentPost.avatarUrl;
    final displayName = currentPost.displayName;
    final backgroundUrl = currentPost.backgroundImage;
    widget.onUserClick(
      username,
      avatarUrl: avatarUrl.isEmpty ? null : avatarUrl,
      displayName: displayName.isEmpty ? null : displayName,
      backgroundUrl: (backgroundUrl ?? '').isEmpty ? null : backgroundUrl,
    );
  }

  void _resolveImageAspectRatio(String imageUrl) {
    if (imageUrl.isEmpty ||
        _imageAspectRatios.containsKey(imageUrl) ||
        _resolvingImageAspectRatios.contains(imageUrl)) {
      return;
    }
    _resolvingImageAspectRatios.add(imageUrl);
    final stream = NetworkImage(imageUrl).resolve(const ImageConfiguration());
    stream.addListener(
      ImageStreamListener(
        (info, _) {
          final ratio = info.image.width / info.image.height;
          _resolvingImageAspectRatios.remove(imageUrl);
          if (_imageAspectRatios[imageUrl] == ratio) return;
          _imageAspectRatios[imageUrl] = ratio;
          if (!mounted) return;
          // 避免在 build 过程中触发 setState 导致异常
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (!mounted) return;
            setState(() {});
          });
        },
        onError: (Object _, StackTrace? _) {
          _resolvingImageAspectRatios.remove(imageUrl);
        },
      ),
    );
  }

  String _getPostTitle(PostSummaryView? post) {
    return post?.title ?? '';
  }

  String _getPostCaption(PostSummaryView? post) {
    return post?.body ?? '';
  }

  String _getAuthorName(PostSummaryView? post) {
    if (post == null) return UITextConstants.unknownUser;
    final name = post.author.name;
    return name.isNotEmpty ? name : UITextConstants.unknownUser;
  }

  String? _getAuthorAvatar(PostSummaryView? post) {
    final avatar = post?.avatarUrl ?? post?.author.avatar;
    return avatar?.isEmpty == true ? null : avatar;
  }

  Widget _buildMediaPage(
    BuildContext context,
    PostSummaryView post,
    MediaItem mediaItem,
    bool isDark,
    bool isActive,
    bool showCaption,
  ) {
    final title = _getPostTitle(post);
    final caption = _getPostCaption(post);
    final hasTextLayout = title.isNotEmpty || caption.isNotEmpty;
    final shouldShowCaption = showCaption && hasTextLayout;
    final postId = post.id;
    final isExpanded = _expandedCaptions[postId] ?? false;
    final imageUrl = mediaItem.url;

    _resolveImageAspectRatio(imageUrl);

    return LayoutBuilder(
      builder: (context, constraints) {
        final horizontalPadding = context.safeGetContainerSpacing(
          SpacingSize.md,
        );
        final maxTextWidth = constraints.maxWidth - horizontalPadding * 2;
        final titleStyle = TextStyle(
          color: AppColors.white,
          fontSize: AppTypography.lg.sp,
          fontWeight: FontWeight.w600,
        );
        final captionStyle = TextStyle(
          color: AppColors.white,
          fontSize: AppTypography.base.sp,
          fontWeight: FontWeight.normal,
        );
        final titleHeight = title.isNotEmpty
            ? _measureTextHeight(
                text: title,
                style: titleStyle,
                maxWidth: maxTextWidth,
                maxLines: 1,
              )
            : 0.0;
        final captionMaxLines = isExpanded ? null : 3;
        final captionHeight = caption.isNotEmpty
            ? _measureTextHeight(
                text: caption,
                style: captionStyle,
                maxWidth: maxTextWidth,
                maxLines: captionMaxLines,
              )
            : 0.0;
        final textSpacing = (title.isNotEmpty && caption.isNotEmpty)
            ? context.safeGetIntraGroupSpacing(SpacingSize.xs)
            : 0.0;
        final textBlockHeight = titleHeight + captionHeight + textSpacing;
        final captionBottomOffset =
            MediaQuery.of(context).padding.bottom +
            AppSpacing.buttonHeight +
            context.safeGetIntraGroupSpacing(SpacingSize.md);
        final captionReservedHeight = hasTextLayout
            ? (textBlockHeight + captionBottomOffset)
            : 0.0;

        final availableHeight = constraints.maxHeight;
        final imageAspectRatio =
            _imageAspectRatios[imageUrl] ??
            mediaItem.aspectRatio ??
            (constraints.maxWidth / constraints.maxHeight);
        final naturalImageHeight = constraints.maxWidth / imageAspectRatio;
        final availableForImage = availableHeight - captionReservedHeight;
        final canPlaceTextBelow = availableForImage > 0;
        final imageHeight = canPlaceTextBelow
            ? math.min(naturalImageHeight, availableForImage)
            : availableHeight;
        final remainingHeight = canPlaceTextBelow
            ? (availableForImage - imageHeight)
            : 0.0;
        final topBottomPadding = remainingHeight > 0
            ? remainingHeight / 2
            : 0.0;
        final shouldOverlayText =
            hasTextLayout && (!canPlaceTextBelow || remainingHeight <= 0);

        return Stack(
          children: [
            Positioned(
              top: topBottomPadding,
              left: 0,
              right: 0,
              height: imageHeight,
              child: _buildMediaContent(context, post, mediaItem),
            ),
            if (!shouldOverlayText && shouldShowCaption)
              Positioned(
                left: 0,
                right: 0,
                bottom: captionBottomOffset,
                child: MediaCaptionBlock(
                  title: title,
                  caption: caption,
                  isExpanded: isExpanded,
                  onToggle: () => _toggleCaptionExpanded(postId),
                ),
              ),
            if (shouldOverlayText && shouldShowCaption)
              Positioned(
                left: 0,
                right: 0,
                bottom: captionBottomOffset,
                child: MediaBlurCaptionOverlay(
                  title: title,
                  caption: caption,
                  isExpanded: isExpanded,
                  onToggle: () => _toggleCaptionExpanded(postId),
                ),
              ),
          ],
        );
      },
    );
  }

  Widget _buildMediaContent(
    BuildContext context,
    PostSummaryView post,
    MediaItem mediaItem,
  ) {
    if (mediaItem.url.isEmpty) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              Icons.image_not_supported_outlined,
              color: AppColors.overlayLight,
              size: AppSpacing.iconLarge,
            ),
            SizedBox(height: context.safeGetIntraGroupSpacing(SpacingSize.xs)),
            Text(
              UITextConstants.loadFailed,
              style: TextStyle(
                color: AppColors.overlayLight,
                fontSize: AppTypography.sm.sp,
              ),
            ),
          ],
        ),
      );
    }
    return GestureDetector(
      onTap: _toggleControls,
      child: PhotoView(
        imageProvider: NetworkImage(mediaItem.url),
        minScale: PhotoViewComputedScale.contained,
        maxScale: PhotoViewComputedScale.covered * 2.0,
        heroAttributes: PhotoViewHeroAttributes(
          tag: 'photo_${post.id}_${mediaItem.url}',
        ),
        onTapDown: (context, details, controllerValue) {
          _toggleControls();
        },
      ),
    );
  }

  double _measureTextHeight({
    required String text,
    required TextStyle style,
    required double maxWidth,
    int? maxLines,
  }) {
    final painter = TextPainter(
      text: TextSpan(text: text, style: style),
      maxLines: maxLines,
      textDirection: TextDirection.ltr,
    )..layout(maxWidth: maxWidth);
    return painter.height;
  }

  void _toggleCaptionExpanded(String postId) {
    setState(() {
      _expandedCaptions[postId] = !(_expandedCaptions[postId] ?? false);
    });
  }

  Widget _buildNestedPageView(bool isDark) {
    return PageView.builder(
      controller: _outerPageController,
      scrollDirection: Axis.vertical,
      itemCount: widget.posts.length,
      onPageChanged: (postIdx) {
        setState(() {
          _currentPostIndex = postIdx;
          _currentImageIndex = 0;
        });
        _initializePostState();
        if (widget.onNearEnd != null && postIdx >= widget.posts.length - 2) {
          widget.onNearEnd!();
        }
      },
      itemBuilder: (context, postIdx) {
        final post = widget.posts[postIdx];
        final urls = _collectPostImageUrls(post);
        if (urls.isEmpty) {
          return const Center(child: SizedBox.shrink());
        }
        final initialPage = postIdx == widget.initialPostIndex
            ? widget.initialImageIndex.clamp(0, urls.length - 1)
            : 0;
        final controller = _innerControllers.putIfAbsent(
          postIdx,
          () => PageController(initialPage: initialPage),
        );
        return PageView.builder(
          controller: controller,
          scrollDirection: Axis.horizontal,
          itemCount: urls.length,
          onPageChanged: (imgIdx) {
            if (postIdx == _currentPostIndex) {
              setState(() => _currentImageIndex = imgIdx);
            }
          },
          itemBuilder: (context, imgIdx) {
            final mediaItem = MediaItem(
              type: ContentTypeConstants.image,
              url: urls[imgIdx],
              aspectRatio: post.aspectRatio,
            );
            final isActive =
                postIdx == _currentPostIndex && imgIdx == _currentImageIndex;
            return _buildMediaPage(
              context,
              post,
              mediaItem,
              isDark,
              isActive,
              !_isPureMode,
            );
          },
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.isOpen) return const SizedBox.shrink();

    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final currentPost = _currentPost;
    final currentEntry = _currentEntry;
    final currentPostImages = currentPost == null
        ? const <String>[]
        : _collectPostImageUrls(currentPost);
    final useNested = widget.layoutMode == 'nested';
    final positionText = useNested
        ? (currentPostImages.isEmpty
              ? '1/1'
              : '${_currentImageIndex + 1}/${currentPostImages.length}')
        : (currentEntry == null || currentPostImages.isEmpty
              ? '1/1'
              : '${currentEntry.imageIndex + 1}/${currentPostImages.length}');
    final showPosition = useNested
        ? (widget.posts.length > 1 || currentPostImages.length > 1)
        : (_mediaEntries.length > 1);

    // 阻断 MaterialApp DefaultTextStyle 合并导致的误装饰（黄下划线），与全屏作品流一致。
    return DefaultTextStyle.merge(
      style: const TextStyle(
        decoration: TextDecoration.none,
        decorationThickness: 0,
      ),
      child: ColoredBox(
        color: AppColors.black,
        child: Stack(
          children: [
            if (useNested)
              _buildNestedPageView(isDark)
            else
              PageView.builder(
                controller: _pageController,
                itemCount: _mediaEntries.length,
                onPageChanged: _handlePageChanged,
                itemBuilder: (context, index) {
                  final entry = _mediaEntries[index];
                  final post = widget.posts[entry.postIndex];
                  final mediaItem = MediaItem(
                    type: ContentTypeConstants.image,
                    url: entry.imageUrl,
                    aspectRatio: post.aspectRatio,
                  );
                  return _buildMediaPage(
                    context,
                    post,
                    mediaItem,
                    isDark,
                    index == _currentEntryIndex,
                    !_isPureMode,
                  );
                },
              ),
            // 控制栏始终构建以便淡出动画生效，用 IgnorePointer 在纯模式屏蔽点击
            Positioned.fill(
              child: AnimatedBuilder(
                animation: _controlsController,
                builder: (context, child) {
                  return IgnorePointer(
                    ignoring: _isPureMode,
                    child: Opacity(
                      opacity: _controlsController.value,
                      child: child,
                    ),
                  );
                },
                child: Column(
                  children: [
                    MediaViewerTopBar(
                      onBack: widget.onClose,
                      positionText: positionText,
                      authorName: _getAuthorName(currentPost),
                      authorAvatarUrl: _getAuthorAvatar(currentPost),
                      isFollowing: _isFollowing,
                      onFollow: _handleFollowClick,
                      onAuthorTap: _handleAuthorTap,
                      onMore: _handleMoreClick,
                      showPosition: showPosition,
                      toolbarMode: widget.toolbarMode,
                      layoutSpec: ImmersiveViewerStageLayoutSpec.mediaStage,
                    ),
                    const Spacer(),
                    ImmersiveEngagementBar(
                      layoutSpec: ImmersiveViewerStageLayoutSpec.mediaStage,
                      avatarUrl: _getAuthorAvatar(currentPost) ?? '',
                      displayName: _getAuthorName(currentPost),
                      circleName: UITextConstants.discoveryRailMoment,
                      likeCount: _likesCount,
                      shareCount: _sharesCount,
                      commentCount: _commentsCount,
                      isLiked: _isLiked,
                      isFollowing: _isFollowing,
                      onUserTap: _handleAuthorTap,
                      onCircleTap: () {},
                      onFollowTap: _handleFollowClick,
                      onLikeTap: _handleLikeClick,
                      onCommentTap: _handleCommentsClick,
                      onShareTap: _handleShareClick,
                      showFollowButton: _showFollowButton,
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ViewerImageEntry {
  final int postIndex;
  final int imageIndex;
  final String imageUrl;

  const _ViewerImageEntry({
    required this.postIndex,
    required this.imageIndex,
    required this.imageUrl,
  });
}
