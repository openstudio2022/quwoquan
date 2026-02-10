import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:photo_view/photo_view.dart';

import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/components/more_actions_popup/configs/media_post_config.dart';
import 'package:quwoquan_app/components/comment_system/comment_viewer.dart';
import 'package:quwoquan_app/components/comment_system/comment_models.dart';
import 'package:quwoquan_app/components/more_actions_popup/more_action_popup.dart';
import 'package:quwoquan_app/components/media/shared/toolbar/media_viewer_toolbar.dart';
import 'package:quwoquan_app/components/media/shared/viewer/media_assistant_panel.dart';
import 'package:quwoquan_app/components/media/shared/viewer/media_caption_widgets.dart';

/// 沉浸式图片查看器 - 基于Figma原型实现
/// 支持与作者主页、评论和帖子的完整联动
class ImmersiveImageViewer extends ConsumerStatefulWidget {
  final bool isOpen;
  final VoidCallback onClose;
  final List<MediaItem> mediaItems;
  final int initialIndex;
  final List<dynamic> posts;
  final int initialPostIndex;
  final Function(String) onUserClick;
  final Function(String, bool)? onFollowClick;
  final Function(dynamic)? onCommentsClick;
  final Function(dynamic)? onMoreClick;
  final Function(dynamic)? onLikeClick;
  final Function(dynamic)? onSaveClick;
  final Function(dynamic)? onShareClick;
  final Set<String>? followingUsers;
  final Set<String>? savedPosts;
  final Set<String>? likedPosts;
  final Function(dynamic)? getPostLikesCount;
  final Function(dynamic)? getPostBookmarksCount;
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
  });

  @override
  ConsumerState<ImmersiveImageViewer> createState() => _ImmersiveImageViewerState();
}

class _ImmersiveImageViewerState extends ConsumerState<ImmersiveImageViewer> 
    with TickerProviderStateMixin {
  late PageController _pageController;
  late AnimationController _fadeController;
  late AnimationController _controlsController;
  final TextEditingController _assistantInputController = TextEditingController();
  final ScrollController _assistantScrollController = ScrollController();
  final FocusNode _assistantInputFocusNode = FocusNode();
  
  int _currentPostIndex = 0;
  bool _showControls = true;
  
  // 本地状态
  bool _isLiked = false;
  bool _isSaved = false;
  bool _isFollowing = false;
  bool _isAuthorSelected = false; // 作者选中状态
  int _likesCount = 0;
  int _savesCount = 0;
  int _commentsCount = 0;
  int _sharesCount = 0;
  bool _isPureMode = false;
  final Map<String, bool> _expandedCaptions = {};
  final Map<String, double> _imageAspectRatios = {};

  @override
  void initState() {
    super.initState();
    _currentPostIndex = widget.initialPostIndex;
    
    _pageController = PageController(initialPage: _currentPostIndex);
    
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
    _fadeController.dispose();
    _controlsController.dispose();
    _assistantInputController.dispose();
    _assistantScrollController.dispose();
    _assistantInputFocusNode.dispose();
    _restoreSystemUiMode();
    super.dispose();
  }

  @override
  void didUpdateWidget(ImmersiveImageViewer oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.likedPosts != widget.likedPosts ||
        oldWidget.savedPosts != widget.savedPosts ||
        oldWidget.getPostLikesCount != widget.getPostLikesCount ||
        oldWidget.getPostBookmarksCount != widget.getPostBookmarksCount) {
      _initializePostState();
    }
  }

  void _initializePostState() {
    if (widget.posts.isNotEmpty && _currentPostIndex < widget.posts.length) {
      final currentPost = widget.posts[_currentPostIndex];
      _isLiked = widget.likedPosts?.contains(currentPost['id']?.toString()) ?? false;
      _isSaved = widget.savedPosts?.contains(currentPost['id']?.toString()) ?? false;
      _isFollowing = widget.followingUsers?.contains(currentPost['username']) ?? false;
      _likesCount = widget.getPostLikesCount?.call(currentPost) ?? 0;
      _savesCount = widget.getPostBookmarksCount?.call(currentPost) ?? 0;
      _commentsCount = currentPost['commentsCount'] ?? 0;
      _sharesCount = currentPost['sharesCount'] ?? currentPost['shareCount'] ?? 0;
    }
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
          statusBarColor: Colors.transparent,
          statusBarIconBrightness: Brightness.dark,
          statusBarBrightness: Brightness.light,
          systemNavigationBarColor: Colors.transparent,
          systemNavigationBarIconBrightness: Brightness.dark,
        ),
      );
      return;
    }

    SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
    SystemChrome.setSystemUIOverlayStyle(
      const SystemUiOverlayStyle(
        statusBarColor: Colors.transparent,
        statusBarIconBrightness: Brightness.dark,
        statusBarBrightness: Brightness.light,
        systemNavigationBarColor: Colors.transparent,
        systemNavigationBarIconBrightness: Brightness.dark,
      ),
    );
  }

  void _restoreSystemUiMode() {
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
    SystemChrome.setSystemUIOverlayStyle(
      const SystemUiOverlayStyle(
        statusBarColor: Colors.transparent,
        statusBarIconBrightness: Brightness.dark,
        statusBarBrightness: Brightness.light,
        systemNavigationBarColor: Colors.transparent,
        systemNavigationBarIconBrightness: Brightness.dark,
      ),
    );
  }

  void _handlePageChanged(int index) {
    setState(() {
      _currentPostIndex = index;
    });
    _initializePostState();
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
    
    if (widget.posts.isNotEmpty && _currentPostIndex < widget.posts.length) {
      widget.onLikeClick?.call(widget.posts[_currentPostIndex]);
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
    
    if (widget.posts.isNotEmpty && _currentPostIndex < widget.posts.length) {
      widget.onSaveClick?.call(widget.posts[_currentPostIndex]);
    }
  }

  void _handleFollowClick() {
    if (widget.posts.isNotEmpty && _currentPostIndex < widget.posts.length) {
      final currentPost = widget.posts[_currentPostIndex];
      setState(() {
        _isFollowing = !_isFollowing;
      });
      final username = currentPost['username']?.toString() ??
          currentPost['publisher']?['username']?.toString();
      if (username == null || username.isEmpty) return;
      widget.onFollowClick?.call(username, _isFollowing);
    }
  }

  void _handleCommentsClick() {
    if (widget.posts.isNotEmpty && _currentPostIndex < widget.posts.length) {
      final currentPost = widget.posts[_currentPostIndex];
      
      // 显示评论弹窗
      final commentConfig = CommentConfig();

      CommentViewer.showModal(
        context: context,
        postId: currentPost['id'] ?? 'mock_post_id',
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
    if (widget.posts.isNotEmpty && _currentPostIndex < widget.posts.length) {
      final currentPost = widget.posts[_currentPostIndex];
      
      // 显示更多操作弹窗（1:1 PostActionSheet：复制链接、保存、举报等）
      final config = MediaPostMoreActionConfig(
        post: currentPost,
        onReward: () => debugPrint('Reward post: ${currentPost['id']}'),
        onSave: () => _handleSaveClick(),
        onMessage: () => debugPrint('Message user: ${currentPost['username']}'),
        onCopyLink: () {
          final link = 'https://quwoquan.app/post/${currentPost['id'] ?? ''}';
          Clipboard.setData(ClipboardData(text: link));
          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(content: Text(UITextConstants.copyLink)),
            );
          }
        },
        onViewOriginal: () => debugPrint('View original: ${currentPost['id']}'),
        onFontSettings: () => debugPrint('Font settings'),
        onThemeToggle: () => debugPrint('Theme toggle'),
        onFeedback: () => debugPrint('Feedback'),
        onNotInterested: () => debugPrint('Not interested'),
        onBlockUser: () => debugPrint('Block user: ${currentPost['username']}'),
        onReport: () => debugPrint('Report post: ${currentPost['id']}'),
      );

      MoreActionPopup.show(
        context: context,
        config: config,
      );
    }
  }

  void _handleShareClick() {
    if (widget.posts.isNotEmpty && _currentPostIndex < widget.posts.length) {
      final currentPost = widget.posts[_currentPostIndex];
      widget.onShareClick?.call(currentPost);
    }
  }

  void _handleAssistantClick() {
    final currentPost = widget.posts.isNotEmpty && _currentPostIndex < widget.posts.length
        ? widget.posts[_currentPostIndex]
        : null;
    _showAssistantPanel(currentPost);
  }

  void _showAssistantPanel(dynamic post) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final suggestions = _buildAssistantSuggestions(post);
    final contextId = post?['id']?.toString() ?? 'media-viewer';
    AssistantChatStore.normalizeMessages();
    final summaryText = AssistantChatStore.buildSummary(
      contextId: contextId,
      title: _getPostTitle(post),
      caption: _getPostCaption(post),
    );
    final summaryCards = AssistantChatStore.buildSummaryCards();
    AssistantChatStore.ensureSummaryForContext(
      contextId: contextId,
      summaryText: summaryText,
      cards: summaryCards,
    );
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (context) {
        return MediaAssistantPanel(
          isDark: isDark,
          titleText:
              '${AppConceptConstants.assistantLabel}${UITextConstants.assistantPanelTitleSuffix}',
          messages: AssistantChatStore.messages,
          scrollController: _assistantScrollController,
          inputController: _assistantInputController,
          inputFocusNode: _assistantInputFocusNode,
          suggestions: suggestions,
          onClose: () => Navigator.pop(context),
          onSend: _handleAssistantSend,
          onSuggestionTap: (text) {
            _assistantInputController.text = text;
            _assistantInputFocusNode.requestFocus();
          },
          onAssistantAvatarTap: widget.onAssistantClick,
        );
      },
    );
  }

  List<String> _buildAssistantSuggestions(dynamic post) {
    final suggestions = <String>[
      UITextConstants.assistantAskAboutSummary,
      UITextConstants.assistantAskAboutRecommendations,
      UITextConstants.assistantAskAboutComments,
    ];
    final content = _getPostCaption(post);
    if (content.isNotEmpty) {
      suggestions.insert(1, UITextConstants.assistantAskAboutOutfit);
    }
    suggestions.add(UITextConstants.assistantAskAboutLocation);
    return suggestions;
  }

  void _handleAssistantSend() {
    final text = _assistantInputController.text.trim();
    if (text.isEmpty) return;
    AssistantChatStore.addUserMessage(text);
    AssistantChatStore.addAssistantMessage(
      '${UITextConstants.assistantAutoResponsePrefix}$text',
    );
    _assistantInputController.clear();
    _assistantInputFocusNode.unfocus();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_assistantScrollController.hasClients) return;
      _assistantScrollController.animateTo(
        _assistantScrollController.position.maxScrollExtent,
        duration: const Duration(milliseconds: 250),
        curve: Curves.easeOut,
      );
    });
  }

  void _handleAuthorTap() {
    if (widget.posts.isEmpty || _currentPostIndex >= widget.posts.length) return;
    final currentPost = widget.posts[_currentPostIndex];
    final username = currentPost['username']?.toString() ??
        currentPost['publisher']?['username']?.toString();
    if (username == null || username.isEmpty) return;
    widget.onUserClick(username);
  }

  void _resolveImageAspectRatio(String imageUrl) {
    if (_imageAspectRatios.containsKey(imageUrl)) return;
    final stream = NetworkImage(imageUrl).resolve(const ImageConfiguration());
    stream.addListener(
      ImageStreamListener((info, _) {
        final ratio = info.image.width / info.image.height;
        if (!mounted) return;
        setState(() {
          _imageAspectRatios[imageUrl] = ratio;
        });
      }),
    );
  }

  String _getPostTitle(dynamic post) {
    final title = post?['title'];
    return title?.toString() ?? '';
  }

  String _getPostCaption(dynamic post) {
    final content = post?['content'] ?? post?['caption'];
    return content?.toString() ?? '';
  }

  String _getAuthorName(dynamic post) {
    return post?['displayName']?.toString() ??
        post?['username']?.toString() ??
        post?['publisher']?['displayName']?.toString() ??
        post?['publisher']?['username']?.toString() ??
        UITextConstants.unknownUser;
  }

  String? _getAuthorAvatar(dynamic post) {
    return post?['avatar']?.toString() ??
        post?['publisher']?['avatar']?.toString();
  }

  Widget _buildMediaPage(
    BuildContext context,
    dynamic post,
    MediaItem mediaItem,
    bool isDark,
    bool isActive,
    bool showCaption,
  ) {
    final title = _getPostTitle(post);
    final caption = _getPostCaption(post);
    final hasTextLayout = title.isNotEmpty || caption.isNotEmpty;
    final shouldShowCaption = showCaption && hasTextLayout;
    final postId = post?['id']?.toString() ?? '';
    final isExpanded = _expandedCaptions[postId] ?? false;
    final imageUrl = mediaItem.url;

    _resolveImageAspectRatio(imageUrl);

    return LayoutBuilder(
      builder: (context, constraints) {
        final horizontalPadding = context.safeGetContainerSpacing(SpacingSize.md);
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
        final captionBottomOffset = MediaQuery.of(context).padding.bottom +
            AppSpacing.buttonHeight +
            context.safeGetIntraGroupSpacing(SpacingSize.md);
        final captionReservedHeight = hasTextLayout ? (textBlockHeight + captionBottomOffset) : 0.0;

        final availableHeight = constraints.maxHeight;
        final imageAspectRatio = _imageAspectRatios[imageUrl] ??
            mediaItem.aspectRatio ??
            (constraints.maxWidth / constraints.maxHeight);
        final naturalImageHeight = constraints.maxWidth / imageAspectRatio;
        final availableForImage = availableHeight - captionReservedHeight;
        final canPlaceTextBelow = availableForImage > 0;
        final imageHeight = canPlaceTextBelow
            ? math.min(naturalImageHeight, availableForImage)
            : availableHeight;
        final remainingHeight = canPlaceTextBelow ? (availableForImage - imageHeight) : 0.0;
        final topBottomPadding = remainingHeight > 0 ? remainingHeight / 2 : 0.0;
        final shouldOverlayText = hasTextLayout && (!canPlaceTextBelow || remainingHeight <= 0);

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
    dynamic post,
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
          tag: 'photo_${post['id']}_${mediaItem.url}',
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

  @override
  Widget build(BuildContext context) {
    if (!widget.isOpen) return const SizedBox.shrink();

    final isDark = Theme.of(context).brightness == Brightness.dark;
    final currentPost = widget.posts.isNotEmpty && _currentPostIndex < widget.posts.length
        ? widget.posts[_currentPostIndex]
        : null;

    return Material(
      color: AppColors.black,
      child: Stack(
        children: [
          PageView.builder(
            controller: _pageController,
            itemCount: widget.posts.length,
            onPageChanged: _handlePageChanged,
            itemBuilder: (context, index) {
              final post = widget.posts[index];
              final mediaItem = widget.mediaItems.isNotEmpty
                  ? widget.mediaItems[index % widget.mediaItems.length]
                  : MediaItem(
                      type: ContentTypeConstants.image,
                      url: (post?['images'] is List && (post['images'] as List).isNotEmpty)
                          ? (post['images'] as List).first.toString()
                          : (post?['imageUrl']?.toString() ?? ''),
                    );
              return _buildMediaPage(
                context,
                post,
                mediaItem,
                isDark,
                index == _currentPostIndex,
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
                    positionText: '${_currentPostIndex + 1}/${widget.posts.length}',
                    authorName: _getAuthorName(currentPost),
                    authorAvatarUrl: _getAuthorAvatar(currentPost),
                    isFollowing: _isFollowing,
                    onFollow: _handleFollowClick,
                    onAuthorTap: _handleAuthorTap,
                    onMore: _handleMoreClick,
                    showPosition: widget.posts.length > 1,
                  ),
                  const Spacer(),
                  MediaViewerBottomBar(
                    shareCount: _sharesCount,
                    commentCount: _commentsCount,
                    likeCount: _likesCount,
                    saveCount: _savesCount,
                    isLiked: _isLiked,
                    isSaved: _isSaved,
                    onShare: _handleShareClick,
                    onComment: _handleCommentsClick,
                    onLike: _handleLikeClick,
                    onSave: _handleSaveClick,
                    onAssistant: _handleAssistantClick,
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
