import 'dart:math' as math;
import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:photo_view/photo_view.dart';

import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/components/video_player_widget.dart';
import 'package:quwoquan_app/components/more_actions_popup/configs/media_post_config.dart';
import 'package:quwoquan_app/components/comment_system/comment_viewer.dart';
import 'package:quwoquan_app/components/comment_system/comment_models.dart';
import 'package:quwoquan_app/components/more_actions_popup/more_action_popup.dart';
import 'package:quwoquan_app/components/media_viewer_toolbar.dart';
import 'package:quwoquan_app/components/assistant_avatar.dart';

/// 沉浸式媒体查看器 - 基于Figma原型实现
/// 支持与作者主页、评论和帖子的完整联动
class ImmersiveMediaViewer extends ConsumerStatefulWidget {
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

  const ImmersiveMediaViewer({
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
  ConsumerState<ImmersiveMediaViewer> createState() => _ImmersiveMediaViewerState();
}

class _ImmersiveMediaViewerState extends ConsumerState<ImmersiveMediaViewer> 
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
  void didUpdateWidget(ImmersiveMediaViewer oldWidget) {
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
    return;
    if (widget.source == 'userProfile') return;
    
    Future.delayed(const Duration(seconds: 3), () {
      if (mounted && _showControls) {
        setState(() {
          _showControls = false;
        });
        _controlsController.reverse();
      }
    });
  }

  void _toggleControls() {
    setState(() {
      _isPureMode = !_isPureMode;
    });
    if (_isPureMode) {
      _controlsController.reverse();
    } else {
      _controlsController.forward();
    }
    _applySystemUiMode();
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
        return Container(
          decoration: BoxDecoration(
            color: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
            borderRadius: BorderRadius.only(
              topLeft: Radius.circular(AppSpacing.largeBorderRadius),
              topRight: Radius.circular(AppSpacing.largeBorderRadius),
            ),
            boxShadow: [
              BoxShadow(
                color: AppColors.black.withValues(alpha: 0.12),
                blurRadius: AppSpacing.lg,
                offset: const Offset(0, -4),
              ),
            ],
          ),
          child: SafeArea(
            top: false,
            child: Padding(
              padding: EdgeInsets.symmetric(
                horizontal: context.safeGetContainerSpacing(SpacingSize.md),
                vertical: context.safeGetIntraGroupSpacing(SpacingSize.md),
              ),
              child: SizedBox(
                height: MediaQuery.of(context).size.height * AppSpacing.assistantPanelHeightRatioMax,
                child: Column(
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Center(
                            child: Text(
                              '${AppConceptConstants.assistantLabel}${UITextConstants.assistantPanelTitleSuffix}',
                              style: TextStyle(
                                fontSize: AppTypography.lg.sp,
                                fontWeight: FontWeight.w600,
                                color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
                              ),
                            ),
                          ),
                        ),
                        IconButton(
                          onPressed: () => Navigator.pop(context),
                          icon: Icon(
                            Icons.close,
                            size: AppSpacing.iconMedium,
                            color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
                          ),
                        ),
                      ],
                    ),
                    SizedBox(height: context.safeGetIntraGroupSpacing(SpacingSize.sm)),
                    Expanded(
                      child: ValueListenableBuilder<List<AssistantChatMessage>>(
                        valueListenable: AssistantChatStore.messages,
                        builder: (context, messages, child) {
                          return ListView.builder(
                            controller: _assistantScrollController,
                            padding: EdgeInsets.zero,
                            itemCount: messages.length,
                            itemBuilder: (context, index) {
                              final message = messages[index];
                              return _buildAssistantMessageBubble(
                                context,
                                isDark,
                                message,
                              );
                            },
                          );
                        },
                      ),
                    ),
                    SizedBox(height: context.safeGetIntraGroupSpacing(SpacingSize.sm)),
                    Align(
                      alignment: Alignment.centerLeft,
                      child: Text(
                        UITextConstants.assistantPromptFollowUp,
                        style: TextStyle(
                          fontSize: AppTypography.sm.sp,
                          color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
                        ),
                      ),
                    ),
                    SizedBox(height: context.safeGetIntraGroupSpacing(SpacingSize.sm)),
                    Align(
                      alignment: Alignment.centerLeft,
                      child: Wrap(
                        spacing: context.safeGetIntraGroupSpacing(SpacingSize.sm),
                        runSpacing: context.safeGetIntraGroupSpacing(SpacingSize.sm),
                        children: suggestions
                            .map((text) => _buildSuggestionChip(context, isDark, text))
                            .toList(),
                      ),
                    ),
                    SizedBox(height: context.safeGetInterGroupSpacing(SpacingSize.sm)),
                    _buildAssistantInput(context, isDark),
                  ],
                ),
              ),
            ),
          ),
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

  Widget _buildSuggestionChip(BuildContext context, bool isDark, String text) {
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: context.safeGetContainerSpacing(SpacingSize.sm),
        vertical: context.safeGetIntraGroupSpacing(SpacingSize.xs),
      ),
      decoration: BoxDecoration(
        color: AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary),
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        border: Border.all(
          color: AppColorsFunctional.getColor(isDark, ColorType.foregroundTertiary)
              .withValues(alpha: 0.2),
        ),
        boxShadow: [
          BoxShadow(
            color: AppColors.black.withValues(alpha: 0.08),
            blurRadius: AppSpacing.sm,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: InkWell(
        onTap: () {
          _assistantInputController.text = text;
          _assistantInputFocusNode.requestFocus();
        },
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        child: Padding(
          padding: EdgeInsets.symmetric(
            horizontal: context.safeGetIntraGroupSpacing(SpacingSize.xs),
            vertical: context.safeGetIntraGroupSpacing(SpacingSize.xs),
          ),
          child: Text(
            text,
            style: TextStyle(
              fontSize: AppTypography.sm.sp,
              color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildAssistantInput(BuildContext context, bool isDark) {
    return Row(
      children: [
        Expanded(
          child: Container(
            padding: EdgeInsets.symmetric(
              horizontal: context.safeGetContainerSpacing(SpacingSize.sm),
              vertical: context.safeGetIntraGroupSpacing(SpacingSize.xs),
            ),
            decoration: BoxDecoration(
              color: AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary),
              borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
              border: Border.all(
                color: AppColorsFunctional.getColor(isDark, ColorType.foregroundTertiary)
                    .withValues(alpha: 0.2),
              ),
              boxShadow: [
                BoxShadow(
                  color: AppColors.black.withValues(alpha: 0.08),
                  blurRadius: AppSpacing.sm,
                  offset: const Offset(0, 2),
                ),
              ],
            ),
            child: TextField(
              controller: _assistantInputController,
              focusNode: _assistantInputFocusNode,
              decoration: InputDecoration(
                isDense: true,
                border: InputBorder.none,
                hintText: UITextConstants.assistantAskPlaceholder,
                hintStyle: TextStyle(
                  color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
                  fontSize: AppTypography.sm.sp,
                ),
              ),
              style: TextStyle(
                color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
                fontSize: AppTypography.sm.sp,
              ),
              onSubmitted: (_) => _handleAssistantSend(),
            ),
          ),
        ),
        SizedBox(width: context.safeGetIntraGroupSpacing(SpacingSize.sm)),
        Container(
          decoration: BoxDecoration(
            color: AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary),
            borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
            border: Border.all(
              color: AppColorsFunctional.getColor(isDark, ColorType.foregroundTertiary)
                  .withValues(alpha: 0.2),
            ),
            boxShadow: [
              BoxShadow(
                color: AppColors.black.withValues(alpha: 0.08),
                blurRadius: AppSpacing.sm,
                offset: const Offset(0, 2),
              ),
            ],
          ),
          child: InkWell(
            onTap: _handleAssistantSend,
            borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
            child: Padding(
              padding: EdgeInsets.all(context.safeGetIntraGroupSpacing(SpacingSize.xs)),
              child: Icon(
                Icons.send,
                color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
                size: AppSpacing.iconMedium,
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildAssistantMessageBubble(
    BuildContext context,
    bool isDark,
    AssistantChatMessage message,
  ) {
    final messageKind = message.kind ?? 'text';
    final bubbleSelf = AppColors.chatBubbleOutgoing;
    final bubbleOther = AppColors.chatBubbleIncoming;
    final fgPrimary = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final isSelf = message.isSelf;
    final bubbleColor = isSelf ? bubbleSelf : bubbleOther;
    final textColor = isSelf ? AppColors.white : fgPrimary;
    final align = isSelf ? CrossAxisAlignment.end : CrossAxisAlignment.start;

    final selfAvatarUrl = _getSelfAvatarUrl();
    return Padding(
      padding: EdgeInsets.symmetric(
        vertical: context.safeGetIntraGroupSpacing(SpacingSize.xs),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: isSelf ? MainAxisAlignment.end : MainAxisAlignment.start,
        children: [
          if (!isSelf)
            Padding(
              padding: EdgeInsets.only(right: context.safeGetIntraGroupSpacing(SpacingSize.sm)),
              child: AssistantAvatar(
                radius: AppSpacing.iconMedium,
                onTap: widget.onAssistantClick,
              ),
            ),
          Flexible(
            child: Column(
              crossAxisAlignment: align,
              children: [
                if (messageKind == 'summary_cards')
                  _buildAssistantSummaryCards(context, isDark, message)
                else
                  Container(
                    padding: EdgeInsets.symmetric(
                      horizontal: context.safeGetContainerSpacing(SpacingSize.sm),
                      vertical: context.safeGetIntraGroupSpacing(SpacingSize.xs),
                    ),
                    decoration: BoxDecoration(
                      color: bubbleColor,
                      borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
                      boxShadow: [
                        BoxShadow(
                          color: AppColors.black.withValues(alpha: 0.08),
                          blurRadius: AppSpacing.sm,
                          offset: const Offset(0, 2),
                        ),
                      ],
                    ),
                    child: Text(
                      message.text,
                      style: TextStyle(
                        color: textColor,
                        fontSize: AppTypography.base.sp,
                      ),
                    ),
                  ),
              ],
            ),
          ),
          if (isSelf)
            Padding(
              padding: EdgeInsets.only(left: context.safeGetIntraGroupSpacing(SpacingSize.sm)),
              child: CircleAvatar(
                radius: AppSpacing.iconMedium,
                backgroundColor: AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary),
                backgroundImage:
                    selfAvatarUrl != null ? NetworkImage(selfAvatarUrl) : null,
                child: selfAvatarUrl == null
                    ? Icon(
                        Icons.person,
                        size: AppSpacing.iconSmall,
                        color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
                      )
                    : null,
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildAssistantSummaryCards(
    BuildContext context,
    bool isDark,
    AssistantChatMessage message,
  ) {
    final cards = message.cards ?? [];
    final summaryText = message.text.trim();
    final fgPrimary = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final fgSecondary = AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    final cardBg = AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (summaryText.isNotEmpty)
          Container(
            padding: EdgeInsets.symmetric(
              horizontal: context.safeGetContainerSpacing(SpacingSize.sm),
              vertical: context.safeGetIntraGroupSpacing(SpacingSize.sm),
            ),
            decoration: BoxDecoration(
              color: cardBg,
              borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
              border: Border.all(
                color: AppColorsFunctional.getColor(isDark, ColorType.foregroundTertiary)
                    .withValues(alpha: 0.2),
              ),
              boxShadow: [
                BoxShadow(
                  color: AppColors.black.withValues(alpha: 0.08),
                  blurRadius: AppSpacing.sm,
                  offset: const Offset(0, 2),
                ),
              ],
            ),
            child: Text(
              summaryText,
              style: TextStyle(
                color: fgPrimary,
                fontSize: AppTypography.base.sp,
              ),
            ),
          ),
        if (summaryText.isNotEmpty)
          SizedBox(height: context.safeGetIntraGroupSpacing(SpacingSize.sm)),
        ...cards.map(
          (card) => Padding(
            padding: EdgeInsets.only(bottom: context.safeGetIntraGroupSpacing(SpacingSize.sm)),
            child: Container(
              padding: EdgeInsets.symmetric(
                horizontal: context.safeGetContainerSpacing(SpacingSize.sm),
                vertical: context.safeGetIntraGroupSpacing(SpacingSize.sm),
              ),
              decoration: BoxDecoration(
                color: cardBg,
                borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
                border: Border.all(
                  color: AppColorsFunctional.getColor(isDark, ColorType.foregroundTertiary)
                      .withValues(alpha: 0.2),
                ),
                boxShadow: [
                  BoxShadow(
                    color: AppColors.black.withValues(alpha: 0.08),
                    blurRadius: AppSpacing.sm,
                    offset: const Offset(0, 2),
                  ),
                ],
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    card.title,
                    style: TextStyle(
                      color: fgPrimary,
                      fontSize: AppTypography.base.sp,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  SizedBox(height: context.safeGetIntraGroupSpacing(SpacingSize.xs)),
                  Text(
                    card.body,
                    style: TextStyle(
                      color: fgSecondary,
                      fontSize: AppTypography.sm.sp,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }

  String? _getSelfAvatarUrl() {
    final user = ref.read(userDataProvider);
    return user?.avatarUrlOrAvatar;
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

    if (mediaItem.type == 'image') {
      _resolveImageAspectRatio(imageUrl);
    }

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
              child: _buildMediaContent(context, post, mediaItem, isActive),
            ),
            if (!shouldOverlayText && shouldShowCaption)
              Positioned(
                left: 0,
                right: 0,
                bottom: captionBottomOffset,
                child: _buildCaptionBlock(
                  context,
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
                child: _buildBlurCaptionOverlay(
                  context,
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
    bool isActive,
  ) {
    if (mediaItem.type == 'video') {
      return GestureDetector(
        onTap: _toggleControls,
        child: VideoPlayerWidget(
          videoUrl: mediaItem.url,
          autoPlay: isActive,
          showControls: true,
          aspectRatio: mediaItem.aspectRatio ?? 9 / 16,
          onTap: _toggleControls,
        ),
      );
    }
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

  Widget _buildCaptionBlock(
    BuildContext context, {
    required String title,
    required String caption,
    required bool isExpanded,
    required VoidCallback onToggle,
  }) {
    final horizontalPadding = context.safeGetContainerSpacing(SpacingSize.md);
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

    return Padding(
      padding: EdgeInsets.symmetric(horizontal: horizontalPadding),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (title.isNotEmpty)
            Padding(
              padding: EdgeInsets.only(
                bottom: context.safeGetIntraGroupSpacing(SpacingSize.xs),
              ),
              child: Text(title, style: titleStyle),
            ),
          if (caption.isNotEmpty)
            _buildExpandableCaption(
              context,
              caption: caption,
              isExpanded: isExpanded,
              onToggle: onToggle,
              captionStyle: captionStyle,
            ),
        ],
      ),
    );
  }

  Widget _buildBlurCaptionOverlay(
    BuildContext context, {
    required String title,
    required String caption,
    required bool isExpanded,
    required VoidCallback onToggle,
  }) {
    return ClipRect(
      child: BackdropFilter(
        filter: ImageFilter.blur(
          sigmaX: AppSpacing.sm,
          sigmaY: AppSpacing.sm,
        ),
        child: Container(
          padding: EdgeInsets.symmetric(
            vertical: context.safeGetIntraGroupSpacing(SpacingSize.sm),
          ),
          color: AppColors.overlayLight,
          child: _buildCaptionBlock(
            context,
            title: title,
            caption: caption,
            isExpanded: isExpanded,
            onToggle: onToggle,
          ),
        ),
      ),
    );
  }

  Widget _buildExpandableCaption(
    BuildContext context, {
    required String caption,
    required bool isExpanded,
    required VoidCallback onToggle,
    required TextStyle captionStyle,
  }) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final textPainter = TextPainter(
          text: TextSpan(text: caption, style: captionStyle),
          maxLines: isExpanded ? null : 3,
          textDirection: TextDirection.ltr,
        )..layout(maxWidth: constraints.maxWidth);
        final isOverflow = textPainter.didExceedMaxLines;

        if (!isOverflow) {
          return Text(caption, style: captionStyle);
        }

        return GestureDetector(
          onTap: onToggle,
          child: Text.rich(
            TextSpan(
              children: [
                TextSpan(
                  text: isExpanded ? caption : _truncateCaption(caption, textPainter, constraints.maxWidth),
                  style: captionStyle,
                ),
                TextSpan(
                  text: isExpanded ? UITextConstants.collapse : UITextConstants.fullText,
                  style: captionStyle.copyWith(
                    color: AppColors.primaryColor,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  String _truncateCaption(String caption, TextPainter textPainter, double maxWidth) {
    final position = textPainter.getPositionForOffset(Offset(maxWidth, textPainter.height));
    final truncatedLength = (position.offset - 4).clamp(0, caption.length);
    return '${caption.substring(0, truncatedLength)}${UITextConstants.ellipsis}';
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
              child: _isPureMode
                  ? const SizedBox.shrink()
                  : Column(
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
