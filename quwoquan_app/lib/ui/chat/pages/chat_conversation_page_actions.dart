part of 'chat_conversation_page.dart';

abstract class _ChatConversationPageActionsState
    extends ConsumerState<ChatConversationPage> {
  final ChatMentionTextEditingController _inputController =
      ChatMentionTextEditingController();
  final ScrollController _scrollController = ScrollController();
  final FocusNode _inputFocusNode = FocusNode();
  final ImagePicker _imagePicker = ImagePicker();
  final VoiceRecorder _voiceRecorder = VoiceRecorder(
    maxDurationMs: kMaxRecordDurationMs + 1000,
  );

  ConversationDto? _conversationDto;
  String? _resolvedTitle;
  String? _otherParticipantId;
  RelationshipCapabilityDto? _relationshipCapability;
  bool _isSelectionMode = false;
  final Set<String> _selectedIds = <String>{};
  ChatMessageDisplayItem? _actionMenuMessage;
  Offset? _actionMenuPosition;
  ModalRoute<dynamic>? _subscribedRoute;
  bool _realtimeAttached = false;
  RealtimeConnectionNotifier? _realtimeNotifier;

  void _onInputChanged() {
    if (mounted) setState(() {});
  }

  Future<bool> _requestMicPermissionForChat() async {
    final outcome = await MicrophonePermissionGuard.ensure(
      context,
      surface: AppPermissionSurface.jit,
    );
    return outcome == MicrophonePermissionOutcome.granted;
  }

  Future<void> _showAttachmentFailure({
    required String title,
    required String message,
  }) async {
    if (!mounted) {
      return;
    }
    await AppActionErrorFeedback.show(
      context,
      semantic: UiErrorSemantic(
        category: UiErrorCategory.submit,
        scope: UiErrorScope.global,
        title: title,
        message: message,
        primaryAction: const UiErrorAction(
          type: UiErrorActionType.dismiss,
          label: UITextConstants.confirm,
        ),
        dismissible: true,
        presentation: UiErrorPresentation.actionDialog,
        tone: UiErrorTone.caution,
      ),
    );
  }

  Future<bool> _startVoiceRecordForChat() async {
    final started = await _voiceRecorder.start();
    if (!started && mounted) {
      AppToast.show(context, ChatText.chatVoiceRecordUnavailable);
    }
    return started;
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
        AppExceptionTelemetryService.instance.recordHandledException(
          source: 'chat.page.load_conversation_title',
          error: error,
          stackTrace: stackTrace,
        ),
      );
    }
  }

  Future<void> _loadOtherParticipantId() async {
    try {
      final currentUserId = ref.read(userDataProvider)?.id ?? '';
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
        AppExceptionTelemetryService.instance.recordHandledException(
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
        AppExceptionTelemetryService.instance.recordHandledException(
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
            limit: 50,
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
        AppExceptionTelemetryService.instance.recordHandledException(
          source: 'chat.mention.resolve_role',
          error: error,
          stackTrace: stackTrace,
        ),
      );
    }
    return false;
  }

  void _openMentionProfile(String targetId) {
    final resolved = targetId.trim();
    if (resolved.isEmpty || resolved == '__all__' || resolved == 'assistant') {
      return;
    }
    final members = ref
        .read(conversationMembersProvider(widget.conversationId))
        .members;
    for (final member in members) {
      if (member.userId == resolved && member.memberType == 'assistant') {
        return;
      }
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
      AppRoutePaths.userProfile(username: resolved),
      extra: UserProfileRouteExtra(subAccountId: resolved),
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

  Future<List<ChatInputAttachment>> _pickChatImages(int remaining) async {
    final picked = await _imagePicker.pickMultiImage(
      imageQuality: 85,
      limit: remaining,
    );
    return picked
        .take(remaining)
        .map<ChatInputAttachment>(
          (image) => ChatInputAttachment(
            id: 'img_${DateTime.now().millisecondsSinceEpoch}_${image.name}',
            type: ChatInputAttachmentType.image,
            name: image.name,
            localPath: image.path,
            subtitle: '',
            thumbnailProvider: FileImage(File(image.path)),
          ),
        )
        .toList(growable: false);
  }

  Future<ChatInputAttachment?> _captureChatPhoto() async {
    final picked = await _imagePicker.pickImage(
      source: ImageSource.camera,
      imageQuality: 85,
    );
    if (picked == null) return null;
    return ChatInputAttachment(
      id: 'cam_${DateTime.now().millisecondsSinceEpoch}_${picked.name}',
      type: ChatInputAttachmentType.image,
      name: picked.name,
      localPath: picked.path,
      thumbnailProvider: FileImage(File(picked.path)),
    );
  }

  Future<List<ChatInputAttachment>> _pickChatFiles(int remaining) async {
    final result = await FilePicker.pickFiles();
    if (result == null) return const <ChatInputAttachment>[];
    final now = DateTime.now().millisecondsSinceEpoch;
    return result.files
        .take(remaining)
        .map<ChatInputAttachment>(
          (file) => ChatInputAttachment(
            id: 'file_${now}_${file.name}',
            type: ChatInputAttachmentType.file,
            name: file.name,
            localPath: file.path,
            subtitle: _formatFileSize(file.size),
          ),
        )
        .toList(growable: false);
  }

  String _formatFileSize(int bytes) {
    if (bytes < 1024) return '${bytes}B';
    if (bytes < 1024 * 1024) {
      return '${(bytes / 1024).toStringAsFixed(1)}KB';
    }
    if (bytes < 1024 * 1024 * 1024) {
      return '${(bytes / (1024 * 1024)).toStringAsFixed(2)}MB';
    }
    return '${(bytes / (1024 * 1024 * 1024)).toStringAsFixed(2)}GB';
  }

  static const Set<String> _imageExtensions = <String>{
    'jpg',
    'jpeg',
    'png',
    'gif',
    'webp',
    'heic',
  };

  static const Set<String> _videoExtensions = <String>{
    'mp4',
    'mov',
    'm4v',
    'avi',
    'mkv',
    'webm',
    '3gp',
  };

  String _attachmentSourcePath(ChatInputAttachment item) {
    return item.localPath?.trim() ?? '';
  }

  String _attachmentExtension(ChatInputAttachment item) {
    final source = _attachmentSourcePath(item).isNotEmpty
        ? _attachmentSourcePath(item)
        : item.name;
    final dot = source.lastIndexOf('.');
    if (dot < 0 || dot == source.length - 1) {
      return '';
    }
    return source.substring(dot + 1).toLowerCase();
  }

  bool _looksLikeImageAttachment(ChatInputAttachment item) {
    if (item.type == ChatInputAttachmentType.image) return true;
    return _imageExtensions.contains(_attachmentExtension(item));
  }

  bool _looksLikeVideoAttachment(ChatInputAttachment item) {
    return _videoExtensions.contains(_attachmentExtension(item));
  }

  MediaCategory _attachmentCategory(ChatInputAttachment item) {
    if (_looksLikeImageAttachment(item)) {
      return MediaCategory.chatImage;
    }
    if (_looksLikeVideoAttachment(item)) {
      return MediaCategory.chatVideo;
    }
    return MediaCategory.chatFile;
  }

  String _attachmentContentType(ChatInputAttachment item) {
    final ext = _attachmentExtension(item);
    switch (ext) {
      case 'jpg':
      case 'jpeg':
        return 'image/jpeg';
      case 'png':
        return 'image/png';
      case 'gif':
        return 'image/gif';
      case 'webp':
        return 'image/webp';
      case 'heic':
        return 'image/heic';
      case 'mp4':
      case 'm4v':
      case '3gp':
        return 'video/mp4';
      case 'mov':
        return 'video/quicktime';
      case 'avi':
        return 'video/x-msvideo';
      case 'mkv':
        return 'video/x-matroska';
      case 'webm':
        return 'video/webm';
      default:
        return _attachmentCategory(item) == MediaCategory.chatImage
            ? 'image/*'
            : _attachmentCategory(item) == MediaCategory.chatVideo
            ? 'video/*'
            : 'application/octet-stream';
    }
  }

  String _attachmentMessageType(ChatInputAttachment item) {
    if (_looksLikeImageAttachment(item)) return 'image';
    if (_looksLikeVideoAttachment(item)) return 'video';
    return 'file';
  }

  String _attachmentFallbackLabel(ChatInputAttachment item) {
    if (_looksLikeVideoAttachment(item)) {
      return ChatText.chatMoreVideo;
    }
    if (_looksLikeImageAttachment(item)) {
      return ChatText.chatMorePhoto;
    }
    return ChatText.chatMoreFile;
  }

  Future<UploadTask> _awaitUploadCompletion(
    MediaUploadManager manager,
    UploadTask task,
  ) async {
    if (task.status == UploadStatus.completed ||
        task.status == UploadStatus.failed) {
      return task;
    }
    final completer = Completer<UploadTask>();
    late final StreamSubscription<UploadTask> subscription;
    subscription = manager.onTaskUpdate.listen((update) {
      if (update.localPath != task.localPath) return;
      if (update.status != UploadStatus.completed &&
          update.status != UploadStatus.failed) {
        return;
      }
      if (!completer.isCompleted) {
        completer.complete(update);
      }
      unawaited(subscription.cancel());
    });
    return completer.future.timeout(
      const Duration(seconds: 120),
      onTimeout: () {
        unawaited(subscription.cancel());
        return task
          ..status = UploadStatus.failed
          ..error = 'upload timeout';
      },
    );
  }

  Future<void> _sendChatAttachment(
    ChatInputAttachment item,
    ChatMessageNotifier notifier,
  ) async {
    final localPath = _attachmentSourcePath(item);
    if (localPath.isEmpty) {
      await notifier.sendMessage(
        'text',
        '[${_attachmentFallbackLabel(item)}] ${item.name}',
      );
      return;
    }
    final file = File(localPath);
    if (!await file.exists()) {
      await _showAttachmentFailure(
        title: ChatText.chatAttachmentUploadFailed,
        message: ChatText.localAttachmentMissing,
      );
      return;
    }
    final category = _attachmentCategory(item);
    final uploadManager = ref.read(mediaUploadManagerProvider);
    final queued = await uploadManager.enqueue(
      UploadTask(
        localPath: localPath,
        category: category,
        contentType: _attachmentContentType(item),
        fileSize: await file.length(),
      ),
    );
    final uploaded = await _awaitUploadCompletion(uploadManager, queued);
    final cdnUrl = uploaded.cdnUrl?.trim() ?? '';
    final assetId = uploaded.assetId?.trim() ?? '';
    if (uploaded.status == UploadStatus.failed ||
        cdnUrl.isEmpty ||
        assetId.isEmpty) {
      await _showAttachmentFailure(
        title: ChatText.chatAttachmentUploadFailed,
        message: ChatText.attachmentUploadIncomplete,
      );
      return;
    }
    final messageType = _attachmentMessageType(item);
    final media = ChatMessageMediaViewData(
      assetId: assetId,
      deliveryUrl: cdnUrl,
      mediaType: messageType,
      fileName: item.name,
      contentType: _attachmentContentType(item),
      fileSizeBytes: uploaded.fileSize,
      thumbnailUrl: messageType == 'image' || messageType == 'video'
          ? cdnUrl
          : null,
    );
    final sent = await notifier.sendMessage(
      messageType,
      messageType == 'image' ? '' : item.name,
      media: media,
    );
    if (!sent) {
      await _showAttachmentFailure(
        title: ChatText.chatAttachmentSendFailed,
        message: ChatText.attachmentSendIncomplete,
      );
    }
  }

  Future<void> _stopVoiceRecordForChat(Duration duration) async {
    final result = await _voiceRecorder.stop();
    if (!mounted) return;
    if (result == null) {
      AppToast.show(context, ChatText.chatVoiceTooShort);
      return;
    }
    if (!await requireLogin(ref, context, AuthGateReason.sendMessage)) {
      return;
    }
    if (!mounted) return;
    await ref
        .read(voiceSendProvider(widget.conversationId).notifier)
        .sendVoice(result);
    if (!mounted) return;
    final sendState = ref.read(voiceSendProvider(widget.conversationId));
    if (sendState.status == VoiceSendStatus.failed &&
        (sendState.error ?? '').isNotEmpty) {
      await ref
          .read(chatSendOutboxProvider.notifier)
          .enqueueVoice(conversationId: widget.conversationId, result: result);
      return;
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

  Future<void> _cancelVoiceRecordForChat() async {
    await _voiceRecorder.cancel();
    if (mounted) {
      AppToast.show(context, ChatText.chatVoiceCanceled);
    }
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
      chatMessageProvider(widget.conversationId).notifier,
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
    final sent = await ref
        .read(chatMessageProvider(widget.conversationId).notifier)
        .sendMessage('text', text, mentions: resolvedMentions);
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
        ? UITextConstants.callGroupVoice
        : UITextConstants.callVoice;
    final videoLabel = _isGroupChat
        ? UITextConstants.callGroupVideo
        : UITextConstants.callVideo;
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
    final queuedCount = ref.watch(chatSendOutboxProvider);
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
                    await ref.read(chatSendOutboxProvider.notifier).drain();
                    ref
                        .read(voiceSendProvider(widget.conversationId).notifier)
                        .reset();
                  },
                  child: Text(
                    UITextConstants.retry,
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
                    ref.read(chatSendOutboxProvider.notifier).drain(),
                child: Text(
                  UITextConstants.tryAgain,
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
            unawaited(ref.read(voicePlayerManagerProvider.notifier).stop());
          }
          ref
              .read(chatMessageProvider(widget.conversationId).notifier)
              .recallMessage(msg.id);
        }
        break;
    }
    setState(() {
      _actionMenuMessage = null;
      _actionMenuPosition = null;
    });
  }

  Future<void> _shareMessages(List<ChatMessageDisplayItem> messages) async {
    final lines = messages
        .map((item) => item.content.trim())
        .where((item) => item.isNotEmpty)
        .toList(growable: false);
    if (lines.isEmpty) return;
    final text = lines.join('\n\n');
    await SharePlus.instance.share(ShareParams(text: text));
  }

  void _toggleSelect(String id) {
    setState(() {
      if (_selectedIds.contains(id)) {
        _selectedIds.remove(id);
      } else {
        _selectedIds.add(id);
      }
    });
  }

  void _cancelSelection() {
    setState(() {
      _isSelectionMode = false;
      _selectedIds.clear();
    });
  }
}
