part of 'profile_interaction_tab.dart';

/// 「我的主页·收到」行尾内联动作子系统（小红书式即时反馈，失败回滚）：
/// 评论类活动 → 赞 / 回复评论；点赞类活动 → 谢谢 / 私信。
///
/// 通过 mixin 复用 [ProfileInteractionTab] State 的 [widget] / [ref] /
/// [setState] / [mounted]，独占本子系统的全部本地态字段，与主文件同库（part）。
/// 拆出仅为收敛主文件行数（R03/R24），不构成第二数据源；公共行为 / TestKeys 不变。
mixin _ProfileInlineActionsMixin on ConsumerState<ProfileInteractionTab> {
  String? _commentActivityRoute(
    ProfileInteractionActivityViewData item, {
    bool replyToComment = false,
  });

  void _trackCommentActivityDeeplink(
    ProfileInteractionActivityViewData item, {
    required String postId,
  });

  // ── 内联动作本地态（小红书式即时反馈，失败回滚）──────────────────────────
  /// 评论类活动「赞」乐观态：activityId → 浏览者反应（覆盖 item.viewerReaction）。
  final Map<String, String> _commentReactionByActivity = <String, String>{};

  /// 评论类活动「赞」请求进行中的 activityId（防重复点击）。
  final Set<String> _commentReactionInFlight = <String>{};

  /// 点赞类活动「谢谢」已确认（本地感谢标记，不可重复）的 activityId。
  final Set<String> _thankedActivityIds = <String>{};

  /// 点赞类活动「私信」发送中 / 已发送的 activityId。
  final Set<String> _directMessageInFlight = <String>{};
  final Set<String> _directMessageSentActivityIds = <String>{};

  bool _isCommentActivity(ProfileInteractionActivityViewData item) {
    final kind = item.commentKind.trim().toLowerCase();
    if (kind.isNotEmpty && kind != 'none') return true;
    final commentFilterId = InteractionSubTab.comments.id;
    return item.filterKeys.map((key) => key.trim()).contains(commentFilterId);
  }

  /// 行尾内联动作区（仅「我的主页」收到方向）：
  /// 点赞类活动 → 谢谢 / 私信；评论类活动 → 赞 / 回复评论。
  /// 其它活动（转发等）返回空列表，保持原有行为不变。
  List<Widget> _buildInlineActionArea(
    BuildContext context,
    ProfileInteractionActivityViewData item, {
    required InteractionDirection direction,
  }) {
    if (widget.mode != ProfileMode.mine ||
        direction != InteractionDirection.received) {
      return const <Widget>[];
    }

    final leftInset =
        AppSpacing.containerMd +
        AppSpacing.avatarUserMd +
        AppSpacing.containerSm;
    final actionPadding = EdgeInsets.only(
      left: leftInset,
      right: AppSpacing.containerMd,
      bottom: AppSpacing.containerSm,
    );

    if (_isCommentActivity(item)) {
      final commentId = item.commentId.trim();
      final postId = item.previewObjectId.trim();
      if (commentId.isEmpty || postId.isEmpty) {
        return const <Widget>[];
      }
      final liked = _effectiveReaction(item) == 'like';
      final busy = _commentReactionInFlight.contains(item.activityId);
      return <Widget>[
        Padding(
          padding: actionPadding,
          child: Row(
            mainAxisAlignment: MainAxisAlignment.end,
            children: <Widget>[
              _InteractionActionChip(
                actionKey: ValueKey<String>(
                  'profile-interaction-like-${item.activityId}',
                ),
                icon: liked ? CupertinoIcons.heart_fill : CupertinoIcons.heart,
                label: liked
                    ? UITextConstants.profileInteractionCommentLiked
                    : UITextConstants.profileInteractionLikeComment,
                active: liked,
                busy: busy,
                isDark: widget.isDark,
                onPressed: busy ? null : () => _toggleCommentLike(item),
              ),
              SizedBox(width: AppSpacing.containerSm),
              _InteractionActionChip(
                actionKey: ValueKey<String>(
                  'profile-interaction-reply-${item.activityId}',
                ),
                icon: CupertinoIcons.arrowshape_turn_up_left,
                label: UITextConstants.profileInteractionReplyComment,
                isDark: widget.isDark,
                onPressed: () => _openCommentReplyDetail(context, item),
              ),
            ],
          ),
        ),
      ];
    }

    if (_isLikeActivity(item)) {
      final thanked = _thankedActivityIds.contains(item.activityId);
      final dmSent = _directMessageSentActivityIds.contains(item.activityId);
      final dmBusy = _directMessageInFlight.contains(item.activityId);
      final canDirectMessage = item.displaySubAccountId.trim().isNotEmpty;
      return <Widget>[
        Padding(
          padding: actionPadding,
          child: Row(
            mainAxisAlignment: MainAxisAlignment.end,
            children: <Widget>[
              _InteractionActionChip(
                actionKey: ValueKey<String>(
                  'profile-interaction-thank-${item.activityId}',
                ),
                icon: thanked
                    ? CupertinoIcons.heart_fill
                    : CupertinoIcons.heart,
                label: thanked
                    ? UITextConstants.profileInteractionThanked
                    : UITextConstants.profileInteractionThank,
                active: thanked,
                isDark: widget.isDark,
                onPressed: thanked ? null : () => _markThanked(item),
              ),
              SizedBox(width: AppSpacing.containerSm),
              _InteractionActionChip(
                actionKey: ValueKey<String>(
                  'profile-interaction-dm-${item.activityId}',
                ),
                icon: dmSent
                    ? CupertinoIcons.checkmark_alt
                    : CupertinoIcons.paperplane,
                label: UITextConstants.profileDirectMessage,
                active: dmSent,
                busy: dmBusy,
                isDark: widget.isDark,
                onPressed: (!canDirectMessage || dmBusy || dmSent)
                    ? null
                    : () => _sendThanksDirectMessage(item),
              ),
            ],
          ),
        ),
      ];
    }

    return const <Widget>[];
  }

  /// 浏览者对该评论的有效反应（本地乐观态覆盖契约字段）。
  String _effectiveReaction(ProfileInteractionActivityViewData item) {
    return _commentReactionByActivity[item.activityId] ?? item.viewerReaction;
  }

  void _openCommentReplyDetail(
    BuildContext context,
    ProfileInteractionActivityViewData item,
  ) {
    final route = _commentActivityRoute(item, replyToComment: true);
    if (route == null) {
      AppToast.show(context, UITextConstants.profileCommentOriginalUnavailable);
      return;
    }
    _trackCommentActivityDeeplink(item, postId: item.previewObjectId.trim());
    context.push(route);
  }

  /// 点赞类活动：非评论活动且 filterKeys 命中 likes 子分类。
  bool _isLikeActivity(ProfileInteractionActivityViewData item) {
    if (_isCommentActivity(item)) {
      return false;
    }
    final likeFilterId = InteractionSubTab.likes.id;
    return item.filterKeys.map((key) => key.trim()).contains(likeFilterId);
  }

  /// 评论类活动「赞」：乐观切换 viewerReaction，失败回滚 + 反馈。
  Future<void> _toggleCommentLike(
    ProfileInteractionActivityViewData item,
  ) async {
    final commentId = item.commentId.trim();
    if (commentId.isEmpty ||
        _commentReactionInFlight.contains(item.activityId)) {
      return;
    }
    final previous = _effectiveReaction(item);
    final next = previous == 'like' ? 'none' : 'like';
    setState(() {
      _commentReactionByActivity[item.activityId] = next;
      _commentReactionInFlight.add(item.activityId);
    });
    try {
      await ref
          .read(profileCommentsContentCommentFacetProvider)
          .reactToComment(
            ReactToContentCommentCommand(
              commentId: commentId,
              reaction: next == 'like'
                  ? ContentCommentReactionValue.like
                  : ContentCommentReactionValue.none,
            ),
          );
      if (mounted) {
        setState(() => _commentReactionInFlight.remove(item.activityId));
      }
    } catch (error, stackTrace) {
      FlutterError.reportError(
        FlutterErrorDetails(
          exception: error,
          stack: stackTrace,
          library: 'profile interaction tab',
          context: ErrorDescription('reacting to interaction comment'),
        ),
      );
      if (mounted) {
        setState(() {
          _commentReactionByActivity[item.activityId] = previous;
          _commentReactionInFlight.remove(item.activityId);
        });
        await AppActionErrorFeedback.show(
          context,
          semantic: runtimeErrorSemantic(
            context,
            error: error,
            category: UiErrorCategory.backgroundAction,
            scope: UiErrorScope.global,
            allowRetry: false,
          ),
        );
      }
    }
  }

  /// 点赞类活动「谢谢」：本地感谢确认态（不可重复）。
  /// 决策：感谢标记而非回赞——该活动只携带「对方赞了我的内容」，
  /// 没有对方内容/评论标识可供 reactToComment 回赞，且发私信由「私信」承担，
  /// 故以即时本地确认表达感谢，避免发出误导性的伪后端写入。
  void _markThanked(ProfileInteractionActivityViewData item) {
    if (_thankedActivityIds.contains(item.activityId)) {
      return;
    }
    setState(() => _thankedActivityIds.add(item.activityId));
    AppToast.show(
      context,
      UITextConstants.profileInteractionThanksAcknowledged,
    );
  }

  /// 点赞类活动「私信」：经 chat 仓库直接发送一条预置感谢私信。
  Future<void> _sendThanksDirectMessage(
    ProfileInteractionActivityViewData item,
  ) async {
    final userId = item.displaySubAccountId.trim();
    if (userId.isEmpty ||
        _directMessageInFlight.contains(item.activityId) ||
        _directMessageSentActivityIds.contains(item.activityId)) {
      return;
    }
    setState(() => _directMessageInFlight.add(item.activityId));
    try {
      final chat = ref.read(chatRepositoryProvider);
      final conversation = await chat.createConversation(
        type: 'direct',
        initialMemberIds: <String>[userId],
      );
      final conversationId = conversation.conversationId.trim();
      if (conversationId.isEmpty) {
        throw StateError('createConversation returned empty conversationId');
      }
      final activeContext = await ref.read(activePersonaContextProvider.future);
      await ref
          .read(chatMessageCommandWriterProvider)
          .sendMessage(
            ChatSendMessageCommand(
              conversationId: conversationId,
              type: 'text',
              content: UITextConstants.profileInteractionThanksLikeMessage,
              senderDisplayNameSnapshot: activeContext.displayName,
              senderAvatarUrlSnapshot: activeContext.avatarUrl,
              personaContextVersion: _positivePersonaVersion(
                activeContext.contextVersion,
              ),
              clientMsgId: 'profile-interaction-thanks-${item.activityId}',
            ),
          );
      if (!mounted) {
        return;
      }
      setState(() {
        _directMessageInFlight.remove(item.activityId);
        _directMessageSentActivityIds.add(item.activityId);
      });
      AppToast.show(
        context,
        UITextConstants.profileInteractionDirectMessageSent,
      );
    } catch (error, stackTrace) {
      FlutterError.reportError(
        FlutterErrorDetails(
          exception: error,
          stack: stackTrace,
          library: 'profile interaction tab',
          context: ErrorDescription('sending thanks direct message'),
        ),
      );
      if (mounted) {
        setState(() => _directMessageInFlight.remove(item.activityId));
        AppToast.show(
          context,
          UITextConstants.profileInteractionDirectMessageFailed,
        );
      }
    }
  }

  int? _positivePersonaVersion(String raw) {
    final parsed = int.tryParse(raw.trim());
    return parsed != null && parsed > 0 ? parsed : null;
  }
}
