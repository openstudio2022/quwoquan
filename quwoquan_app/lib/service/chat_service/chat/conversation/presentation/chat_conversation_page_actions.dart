part of 'chat_conversation_page.dart';

abstract class _ChatConversationPageActionsState
    extends _ChatConversationPageMediaActionsState {
  final ChatMentionTextEditingController _inputController =
      ChatMentionTextEditingController();
  final FocusNode _inputFocusNode = FocusNode();

  void _updateSelection(VoidCallback action) => setState(action);

  ConversationViewData? _conversationDto;
  String? _resolvedTitle;
  String? _otherParticipantId;
  RelationshipCapabilityViewData? _relationshipCapability;
  bool _isSelectionMode = false;
  final Set<String> _selectedIds = <String>{};
  ChatMessageDisplayItem? _actionMenuMessage;
  Offset? _actionMenuPosition;

  /// 引用回复目标：contracts `replyToMessageId` 的输入态载体。
  ChatMessageDisplayItem? _replyToTarget;
  ModalRoute<dynamic>? _subscribedRoute;
  bool _realtimeAttached = false;
  RealtimeConversationLifecycle? _realtimeNotifier;

  void _onInputChanged() {
    if (mounted) setState(() {});
  }

  Future<void> _loadConversationTitle() async {
    if (_resolvedTitle != null) return;
    try {
      final repo = ref.read(chatConversationRepositoryProvider);
      final dto = await repo.getConversation(widget.conversationId);
      if (!mounted) return;
      setState(() {
        _resolvedTitle = dto.title ?? widget.conversationId;
        _conversationDto = dto;
      });
      if (dto.type == 'direct') {
        _loadOtherParticipantId();
      }
    } catch (error, stackTrace) {
      // best-effort：回退到 conversationId 作为标题，不阻断聊天；仍上报观测。
      unawaited(
        ref
            .read(exceptionTelemetryPortProvider)
            .recordHandledException(
              source: 'chat.page.load_conversation_title',
              error: error,
              stackTrace: stackTrace,
            ),
      );
    }
  }

  Future<void> _loadOtherParticipantId() async {
    try {
      final currentUserId = ref.read(userDataProvider)?.personaId ?? '';
      final members = await ref
          .read(chatMemberRepositoryProvider)
          .listMembers(conversationId: widget.conversationId, limit: 10);
      final others = members.where((m) => m.userId != currentUserId).toList();
      final otherId = others.isEmpty ? null : others.first.userId;
      if (mounted && otherId != null && otherId.isNotEmpty) {
        setState(() => _otherParticipantId = otherId);
        await _loadRelationshipCapability(otherId);
      }
    } catch (error, stackTrace) {
      // best-effort：仅影响关系能力展示，不阻断聊天主流程；仍上报观测。
      unawaited(
        ref
            .read(exceptionTelemetryPortProvider)
            .recordHandledException(
              source: 'chat.page.load_other_participant',
              error: error,
              stackTrace: stackTrace,
            ),
      );
    }
  }

  Future<void> _loadRelationshipCapability(String otherId) async {
    try {
      final capability = await ref
          .read(relationshipCapabilityRepositoryProvider)
          .getCapability(otherId);
      if (!mounted) return;
      setState(() => _relationshipCapability = capability);
    } catch (error, stackTrace) {
      // best-effort：维持空能力态，相关入口按默认隐藏处理；仍上报观测。
      unawaited(
        ref
            .read(exceptionTelemetryPortProvider)
            .recordHandledException(
              source: 'chat.page.load_relationship_capability',
              error: error,
              stackTrace: stackTrace,
            ),
      );
    }
  }

  bool get _isGroupChat => _conversationDto?.type == 'group';

  Future<ChatInputMentionCandidate?> _requestChatMention(
    BuildContext pickerContext,
  ) async {
    if (!_isGroupChat) {
      return null;
    }
    final currentUserId = ref.read(currentUserIdProvider);
    final allowMentionAll = await _resolveCanMentionAll(currentUserId);
    if (!mounted || !pickerContext.mounted) {
      return null;
    }
    final selected = await ChatMentionPicker.show(
      pickerContext,
      currentUserId: currentUserId,
      allowMentionAll: allowMentionAll,
      searchMembers: (query) => ref
          .read(chatMemberRepositoryProvider)
          .searchMembers(
            conversationId: widget.conversationId,
            query: query,
            limit: ChatListConversationMembersQuery.maximumLimit,
          ),
    );
    if (selected != null && mounted) {
      unawaited(
        ref
            .read(chatInteractionTelemetryTrackerProvider)
            .track(
              action: ChatInteractionAction.mentionSelect,
              outcome: ChatInteractionOutcome.succeeded,
              mentionScope: _mentionScopeFor(selected.kind),
              pageName: PageNames.chatDetail,
              surfaceId: AppUiSurfaces.chatDetail.id,
            ),
      );
    }
    return selected;
  }

  ChatMentionScope _mentionScopeFor(ChatInputMentionKind kind) {
    return switch (kind) {
      ChatInputMentionKind.member => ChatMentionScope.member,
      ChatInputMentionKind.assistant => ChatMentionScope.assistant,
      ChatInputMentionKind.all => ChatMentionScope.all,
    };
  }

  Future<bool> _resolveCanMentionAll(String currentUserId) async {
    final memberState = ref.read(
      conversationMembersProvider(widget.conversationId),
    );
    for (final member in memberState.members) {
      if (member.userId == currentUserId) {
        return member.role == 'owner' || member.role == 'admin';
      }
    }
    try {
      final matches = await ref
          .read(chatMemberRepositoryProvider)
          .searchMembers(
            conversationId: widget.conversationId,
            query: currentUserId,
            limit: 5,
          );
      for (final member in matches) {
        if (member.userId == currentUserId) {
          return member.role == 'owner' || member.role == 'admin';
        }
      }
    } catch (error, stackTrace) {
      unawaited(
        ref
            .read(exceptionTelemetryPortProvider)
            .recordHandledException(
              source: 'chat.mention.resolve_role',
              error: error,
              stackTrace: stackTrace,
            ),
      );
    }
    return false;
  }

  String _memberUserHandle(String personaId) {
    final normalizedPersonaId = personaId.trim();
    if (normalizedPersonaId.isEmpty) {
      return '';
    }
    final members = ref
        .read(conversationMembersProvider(widget.conversationId))
        .members;
    for (final member in members) {
      if (member.userId == normalizedPersonaId &&
          member.memberType != 'assistant') {
        return member.userHandle.trim();
      }
    }
    return '';
  }

  void _openMentionProfile(String targetId) {
    final personaId = targetId.trim();
    if (personaId.isEmpty ||
        personaId == '__all__' ||
        personaId == 'assistant') {
      return;
    }
    final userHandle = _memberUserHandle(personaId);
    if (userHandle.isEmpty) {
      return;
    }
    unawaited(
      ref
          .read(journeyEventTrackerProvider)
          .trackAction(
            journey: 'chat_conversation',
            action: 'mention_clicked',
            pageName: 'chat_conversation',
            targetType: 'user_profile',
          ),
    );
    context.push(
      AppRoutePaths.userProfile(userHandle: userHandle),
      extra: UserProfileRouteExtra(personaId: personaId),
    );
  }

  int get _memberCount {
    if (!_isGroupChat) {
      return _conversationDto?.memberCount ?? 0;
    }
    final roster = ref
        .read(conversationMembersProvider(widget.conversationId))
        .members;
    if (roster.isNotEmpty) {
      return roster.length;
    }
    return _conversationDto?.memberCount ?? 0;
  }

  bool get _isBlockedConversation => _conversationDto?.status == 'blocked';

  RtcCallEntryIntent _directCallIntent(RtcCallEntryMediaType mediaType) {
    return RtcCallEntryIntent.direct(
      mediaType: mediaType,
      targetUserId: _otherParticipantId ?? '',
      capability: _relationshipCapability,
    );
  }

  bool _isDirectCallAvailable(RtcCallEntryMediaType mediaType) {
    return !_isBlockedConversation &&
        _directCallIntent(mediaType).availability.isAvailable;
  }

  bool get _shouldDisableComposer {
    // 会话类型和直聊关系能力尚未解析时 fail-closed，避免加载窗口短暂放开
    // 被拉黑/非互关会话的发送入口。
    if (_conversationDto == null) {
      return true;
    }
    if (_isGroupChat) {
      return false;
    }
    if (_isBlockedConversation) {
      return true;
    }
    final capability = _relationshipCapability;
    if (_otherParticipantId == null || capability == null) {
      return true;
    }
    return !capability.canSendMessage;
  }

  String get _conversationTitle {
    if (_resolvedTitle != null) return _resolvedTitle!;
    _loadConversationTitle();
    return widget.conversationId;
  }

  Future<void> _submitChatInput(ChatInputSubmitPayload payload) async {
    if (_shouldDisableComposer) {
      return;
    }
    // 防御性二次拦截：私信发送是需登录写动作。会话页虽已被路由守卫保护，
    // 这里再兜底一次，避免任何绕过路由的发送路径让游客写入。
    if (!await requireLogin(ref, context, AuthGateReason.sendMessage)) {
      return;
    }
    if (!mounted) return;
    final notifier = ref.read(
      chatMessageTimelineControllerProvider(widget.conversationId),
    );
    if (payload.attachments.isNotEmpty) {
      for (final item in payload.attachments) {
        await _sendChatAttachment(item, notifier);
      }
    }
    var text = payload.text.trim();
    if (text.isNotEmpty) {
      await _sendMessage(draftText: text, mentions: payload.mentions);
    }
  }

  /// 失败气泡的手动重发：经持久化 outbox 以原 clientMsgId 幂等重放；
  /// 仍失败时气泡回落 failed 态并 toast 提示。
  Future<void> _retryFailedMessage(ChatMessageDisplayItem message) async {
    final notifier = ref.read(
      chatMessageTimelineControllerProvider(widget.conversationId),
    );
    try {
      await notifier.retrySendMessage(message.clientMsgId);
    } catch (_) {
      if (mounted) {
        AppToast.show(context, ChatText.chatRetrySendFailed);
      }
    }
  }

  Future<void> _sendMessage({String? draftText, List<String>? mentions}) async {
    if (_shouldDisableComposer) {
      return;
    }
    _inputFocusNode.unfocus();
    await Future<void>.delayed(const Duration(milliseconds: 150));
    final text = (draftText ?? _inputController.text).trim();
    if (text.isEmpty) return;
    if (draftText == null) _inputController.clear();
    final resolvedMentions = _resolveMentions(mentions);
    final replyToMessageId = _replyToTarget?.id.trim();
    final sent = await ref
        .read(chatMessageTimelineControllerProvider(widget.conversationId))
        .sendMessage(
          'text',
          text,
          mentions: resolvedMentions,
          replyToMessageId: (replyToMessageId?.isEmpty ?? true)
              ? null
              : replyToMessageId,
        );
    if (mounted && _replyToTarget != null) {
      setState(() => _replyToTarget = null);
    }
    if (resolvedMentions != null) {
      unawaited(
        ref
            .read(chatInteractionTelemetryTrackerProvider)
            .track(
              action: ChatInteractionAction.mentionSend,
              outcome: sent
                  ? ChatInteractionOutcome.succeeded
                  : ChatInteractionOutcome.failed,
              mentionScope: _mentionScopeForResolvedIds(resolvedMentions),
              memberCount: resolvedMentions.length,
              pageName: PageNames.chatDetail,
              surfaceId: AppUiSurfaces.chatDetail.id,
            ),
      );
    }
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 200),
          curve: Curves.easeOut,
        );
      }
    });
  }

  List<String>? _resolveMentions(List<String>? mentions) {
    if (!_isGroupChat) {
      return null;
    }
    final values = <String>[];
    final seen = <String>{};
    for (final raw in mentions ?? const <String>[]) {
      final value = raw.trim();
      if (value.isNotEmpty && seen.add(value)) {
        values.add(value);
      }
    }
    return values.isEmpty ? null : List<String>.unmodifiable(values);
  }

  ChatMentionScope _mentionScopeForResolvedIds(List<String> mentions) {
    if (mentions.contains('__all__')) return ChatMentionScope.all;
    if (mentions.contains('assistant')) return ChatMentionScope.assistant;
    return ChatMentionScope.member;
  }

  List<ChatInputExtraPanelItem> _buildCallPanelItems() {
    final voiceLabel = _isGroupChat
        ? CallText.callGroupVoice
        : CallText.callVoice;
    final videoLabel = _isGroupChat
        ? CallText.callGroupVideo
        : CallText.callVideo;
    final items = <ChatInputExtraPanelItem>[];
    if (_isGroupChat || _isDirectCallAvailable(RtcCallEntryMediaType.audio)) {
      items.add(
        ChatInputExtraPanelItem(
          icon: CupertinoIcons.phone,
          text: voiceLabel,
          onTap: () async => _initiateCall(RtcCallEntryMediaType.audio),
        ),
      );
    }
    if (_isGroupChat || _isDirectCallAvailable(RtcCallEntryMediaType.video)) {
      items.add(
        ChatInputExtraPanelItem(
          icon: CupertinoIcons.video_camera,
          text: videoLabel,
          onTap: () async => _initiateCall(RtcCallEntryMediaType.video),
        ),
      );
    }
    return items;
  }

  /// 文件消息点击：经系统能力打开交付 URL（有本地文件系统的平台交给
  /// 外部应用，Web 等平台走平台默认处理）；失败给结构化提示。
  Future<void> _openFileMessage(ChatMessageDisplayItem message) async {
    final rawUrl = message.mediaUrl.trim();
    if (rawUrl.isEmpty) {
      AppToast.show(context, ChatText.chatMediaUnavailable);
      return;
    }
    try {
      final uri = Uri.parse(rawUrl);
      final launched = await launchUrl(
        uri,
        mode: ref.read(platformCapabilitiesProvider).hasLocalFileSystem
            ? LaunchMode.externalApplication
            : LaunchMode.platformDefault,
      );
      if (!launched) {
        throw StateError('platform rejected the file delivery URL');
      }
    } catch (_) {
      if (!mounted) return;
      AppToast.show(context, ChatText.chatFileOpenFailed);
    }
  }

  /// 图片消息点击：进入全屏大图查看（黑底 + 双指缩放）；
  /// 交付 URL 缺失时给结构化提示。
  void _openImageMessage(ChatMessageDisplayItem message) {
    final rawUrl = message.imageUrl.trim().isNotEmpty
        ? message.imageUrl.trim()
        : message.mediaUrl.trim();
    if (rawUrl.isEmpty) {
      AppToast.show(context, ChatText.chatMediaUnavailable);
      return;
    }
    unawaited(
      showAppFloatingModal<void>(
        context: context,
        barrierDismissible: false,
        builder: (dialogContext) {
          return ColoredBox(
            key: const ValueKey<String>('chat_image_viewer_surface'),
            color: AppColors.black,
            child: SafeArea(
              child: Stack(
                children: [
                  Positioned.fill(
                    child: GestureDetector(
                      onTap: () => Navigator.of(dialogContext).pop(),
                      child: InteractiveViewer(
                        maxScale: 4,
                        child: Center(
                          child: AppCachedNetworkImage(
                            imageUrl: rawUrl,
                            fit: BoxFit.contain,
                            errorWidget: Icon(
                              CupertinoIcons.photo,
                              color: AppColors.white.withValues(alpha: 0.6),
                              size: AppSpacing.iconLarge,
                            ),
                          ),
                        ),
                      ),
                    ),
                  ),
                  Positioned(
                    top: AppSpacing.intraGroupSm,
                    left: AppSpacing.intraGroupSm,
                    child: CupertinoButton(
                      key: const ValueKey<String>('chat_image_viewer_close'),
                      padding: EdgeInsets.all(AppSpacing.intraGroupXs),
                      onPressed: () => Navigator.of(dialogContext).pop(),
                      child: Icon(CupertinoIcons.xmark, color: AppColors.white),
                    ),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  /// 视频消息点击：resolve 公开交付引用后进入全屏播放（复用 content 域
  /// VideoPlayerWidget 基建）；引用非法时给结构化提示。
  void _openVideoMessage(ChatMessageDisplayItem message) {
    final rawUrl = message.mediaUrl.trim();
    final endpointConfig = ref.read(mediaEndpointConfigProvider);
    if (rawUrl.isEmpty || endpointConfig == null) {
      AppToast.show(context, ChatText.chatMediaUnavailable);
      return;
    }
    final MediaDeliveryReference reference;
    try {
      reference = MediaDeliveryResolver(
        endpointConfig,
      ).resolve(rawUrl, kind: MediaDeliveryKind.video);
    } on MediaDeliveryResolutionException {
      AppToast.show(context, ChatText.chatMediaUnavailable);
      return;
    }
    unawaited(
      showAppFloatingModal<void>(
        context: context,
        barrierDismissible: false,
        builder: (dialogContext) {
          return ColoredBox(
            key: const ValueKey<String>('chat_video_playback_surface'),
            color: AppColors.black,
            child: SafeArea(
              child: Stack(
                children: [
                  Center(
                    child: buildChatVideoMessagePlayerSlot(
                      deliveryReference: reference,
                      onExit: () => Navigator.of(dialogContext).pop(),
                    ),
                  ),
                  Positioned(
                    top: AppSpacing.intraGroupSm,
                    left: AppSpacing.intraGroupSm,
                    child: CupertinoButton(
                      key: const ValueKey<String>('chat_video_playback_close'),
                      padding: EdgeInsets.all(AppSpacing.intraGroupXs),
                      onPressed: () => Navigator.of(dialogContext).pop(),
                      child: Icon(CupertinoIcons.xmark, color: AppColors.white),
                    ),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  RtcCallEntryMediaType _callTypeFromLog(ChatMessageDisplayItem message) {
    for (final attribute in message.card?.attributes ?? const []) {
      if (attribute.name == 'callType') {
        return RtcCallEntryMediaType.fromWireValue(attribute.value);
      }
    }
    return RtcCallEntryMediaType.audio;
  }

  Future<void> _initiateCall(RtcCallEntryMediaType mediaType) async {
    final intent = _isGroupChat
        ? RtcCallEntryIntent.conversation(
            mediaType: mediaType,
            conversationId: widget.conversationId,
            participantCount: _memberCount,
          )
        : _directCallIntent(mediaType);
    await ref
        .read(rtcCallEntryPresenterProvider)
        .start(
          context: context,
          ref: ref,
          intent: intent,
          sourceSurface: AppUiSurfaces.chatDetail,
        );
  }

  Widget _buildMutualFollowRtcHintBar() {
    return Container(
      width: double.infinity,
      margin: EdgeInsets.only(bottom: AppSpacing.sm),
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.sm,
      ),
      decoration: BoxDecoration(
        color: AppColors.primaryColor.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
        border: Border.all(
          color: AppColors.primaryColor.withValues(alpha: 0.18),
        ),
      ),
      child: Text(
        ChatText.chatMutualFollowRtcHint,
        style: TextStyle(
          color: AppColors.primaryColor,
          fontSize: AppTypography.sm,
          fontWeight: FontWeight.w500,
        ),
      ),
    );
  }

  Widget _buildBlockedConversationHintBar() {
    return Container(
      width: double.infinity,
      margin: EdgeInsets.only(bottom: AppSpacing.sm),
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.sm,
      ),
      decoration: BoxDecoration(
        color: AppColors.error.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
        border: Border.all(color: AppColors.error.withValues(alpha: 0.18)),
      ),
      child: Text(
        ChatText.chatBlockedConversationHint,
        style: TextStyle(
          color: AppColors.error,
          fontSize: AppTypography.sm,
          fontWeight: FontWeight.w500,
        ),
      ),
    );
  }

  Widget _buildVoiceSendStatusBar(VoiceSendState state) {
    final queuedCount = ref.watch(chatSendOutboxQueueLengthProvider);
    if (state.status == VoiceSendStatus.idle ||
        state.status == VoiceSendStatus.completed) {
      if (queuedCount > 0) {
        return _buildVoiceQueuedStatusBar(queuedCount);
      }
      return const SizedBox.shrink();
    }
    final isFailed = state.status == VoiceSendStatus.failed;
    final fg = isFailed ? AppColors.error : AppColors.primaryColor;
    final label = switch (state.status) {
      VoiceSendStatus.uploading => ChatText.chatVoiceUploading,
      VoiceSendStatus.sending => ChatText.chatVoiceSending,
      VoiceSendStatus.failed => ChatText.chatVoicePendingRetry,
      _ => ChatText.chatVoiceSending,
    };
    return Padding(
      padding: EdgeInsets.only(bottom: AppSpacing.sm),
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: fg.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
          border: Border.all(color: fg.withValues(alpha: 0.18)),
        ),
        child: Padding(
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.containerSm,
            vertical: AppSpacing.intraGroupSm,
          ),
          child: Row(
            children: [
              Icon(
                isFailed
                    ? CupertinoIcons.arrow_clockwise_circle_fill
                    : CupertinoIcons.waveform,
                size: AppSpacing.iconSmall,
                color: fg,
              ),
              SizedBox(width: AppSpacing.intraGroupXs),
              Expanded(
                child: Text(
                  label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: AppTypography.sm,
                    fontWeight: AppTypography.medium,
                    color: fg,
                  ),
                ),
              ),
              if (isFailed)
                CupertinoButton(
                  padding: EdgeInsets.symmetric(horizontal: AppSpacing.xs),
                  minimumSize: Size.square(AppSpacing.iconButtonMinSizeSm),
                  onPressed: () async {
                    await ref.read(chatSendOutboxControlProvider).drain();
                    ref
                        .read(
                          chatVoiceSendControllerProvider(
                            widget.conversationId,
                          ),
                        )
                        .reset();
                  },
                  child: Text(
                    FoundationText.retry,
                    style: TextStyle(fontSize: AppTypography.sm, color: fg),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildVoiceQueuedStatusBar(int queuedCount) {
    final fg = AppColors.primaryColor;
    return Padding(
      padding: EdgeInsets.only(bottom: AppSpacing.sm),
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: fg.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
          border: Border.all(color: fg.withValues(alpha: 0.18)),
        ),
        child: Padding(
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.containerSm,
            vertical: AppSpacing.intraGroupSm,
          ),
          child: Row(
            children: [
              Icon(CupertinoIcons.clock, size: AppSpacing.iconSmall, color: fg),
              SizedBox(width: AppSpacing.intraGroupXs),
              Expanded(
                child: Text(
                  '${ChatText.chatVoiceQueued} ($queuedCount)',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: AppTypography.sm,
                    fontWeight: AppTypography.medium,
                    color: fg,
                  ),
                ),
              ),
              CupertinoButton(
                padding: EdgeInsets.symmetric(horizontal: AppSpacing.xs),
                minimumSize: Size.square(AppSpacing.iconButtonMinSizeSm),
                onPressed: () =>
                    ref.read(chatSendOutboxControlProvider).drain(),
                child: Text(
                  ContentText.tryAgain,
                  style: TextStyle(fontSize: AppTypography.sm, color: fg),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _onLongPressMessage(
    ChatMessageDisplayItem message,
    Offset globalPosition,
  ) {
    setState(() {
      _actionMenuMessage = message;
      _actionMenuPosition = globalPosition;
    });
  }

  void _onMessageAction(String action) {
    final msg = _actionMenuMessage;
    if (msg == null) return;
    unawaited(
      ref
          .read(journeyEventTrackerProvider)
          .trackAction(
            journey: 'chat_conversation',
            action: 'message_$action',
            pageName: 'chat_conversation',
            targetType: 'message',
            targetKey: msg.id,
          ),
    );
    switch (action) {
      case 'reply':
        setState(() => _replyToTarget = msg);
        _inputFocusNode.requestFocus();
        break;
      case 'forward':
        _shareMessages(<ChatMessageDisplayItem>[msg]);
        break;
      case 'select':
        setState(() {
          _isSelectionMode = true;
          _selectedIds.add(msg.id);
        });
        break;
      case 'copy':
        final content = msg.content;
        if (content.isNotEmpty) {
          Clipboard.setData(ClipboardData(text: content));
          if (mounted) {
            AppToast.show(context, ChatText.copiedToClipboard);
          }
        }
        break;
      case 'recall':
        if (msg.isSelf) {
          if (msg.type == 'audio') {
            unawaited(ref.read(chatVoicePlaybackControlProvider).stop());
          }
          ref
              .read(
                chatMessageTimelineControllerProvider(widget.conversationId),
              )
              .recallMessage(msg.id);
        }
        break;
      case 'receipts':
        if (msg.isSelf) {
          unawaited(_showMessageReceipts(msg));
        }
        break;
    }
    setState(() {
      _actionMenuMessage = null;
      _actionMenuPosition = null;
    });
  }

  Future<List<ChatMessageReceipt>> _loadMessageReceipts(
    ChatMessageDisplayItem message,
  ) async {
    final page = await ref
        .read(messageReceiptFactQueryProvider)
        .getReceipts(
          ChatGetMessageReceiptsQuery(
            conversationId: widget.conversationId,
            messageId: message.id,
          ),
        );
    return page.items;
  }

  Map<String, String> _messageReceiptDisplayNames() {
    return <String, String>{
      for (final member
          in ref
              .read(conversationMembersProvider(widget.conversationId))
              .members)
        member.userId: member.displayName,
    };
  }

  Future<void> _showMessageReceipts(ChatMessageDisplayItem message) async {
    try {
      final receipts = await _loadMessageReceipts(message);
      if (!mounted) return;
      await MessageReceiptSheet.show(
        context,
        receipts: receipts,
        displayNames: _messageReceiptDisplayNames(),
      );
    } catch (error) {
      if (!mounted) return;
      await AppActionErrorFeedback.show(
        context,
        semantic: runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.pageLoad,
          scope: UiErrorScope.section,
        ),
        onAction: (action) async {
          if (action.type != UiErrorActionType.retry &&
              action.type != UiErrorActionType.resubmit) {
            return;
          }
          await _showMessageReceipts(message);
        },
      );
    }
  }

  /// 消息转发主路径是 App 内转发（选联系人/群直达会话）；外部系统分享
  /// 由 ForwardShareSheet 内的分享区承载为次级动作。
  Future<void> _shareMessages(List<ChatMessageDisplayItem> messages) async {
    final lines = messages
        .map((item) => item.content.trim())
        .where((item) => item.isNotEmpty)
        .toList(growable: false);
    if (lines.isEmpty) return;
    final text = lines.join('\n\n');
    final title = lines.first.length > 30
        ? lines.first.substring(0, 30)
        : lines.first;
    await ForwardShareSheet.show(
      context,
      payload: AppForwardPayload(
        kind: AppForwardSubjectKind.chatMessage,
        title: title,
        shareText: text,
      ),
    );
  }
}
