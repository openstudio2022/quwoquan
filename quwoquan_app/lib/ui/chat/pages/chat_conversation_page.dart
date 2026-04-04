import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:share_plus/share_plus.dart';
import 'package:speech_to_text/speech_to_text.dart' as stt;
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/chat/models/conversation_dto.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/cloud/chat/models/message_dto.dart';
import 'package:quwoquan_app/cloud/services/realtime/realtime_connection_manager.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/components/conversation/conversation_page_scaffold.dart';
import 'package:quwoquan_app/components/conversation/conversation_timeline.dart';
import 'package:quwoquan_app/components/conversation/message_action_menu_overlay.dart';
import 'package:quwoquan_app/components/input/customizable_chat_input_bar.dart';
import 'package:quwoquan_app/core/constants/design_semantic_constants.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/models/search_models.dart';
import 'package:quwoquan_app/core/models/user_profile_route_extra.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/ui/chat/providers/chat_inbox_provider.dart';
import 'package:quwoquan_app/ui/chat/providers/chat_message_provider.dart';
import 'package:quwoquan_app/ui/chat/widgets/message/chat_message_bubble.dart';
import 'package:quwoquan_app/ui/rtc/models/call_participant_picker_route_extra.dart';
import 'package:quwoquan_app/ui/rtc/providers/call_session_provider.dart';

String formatChatTime(String? raw) {
  if (raw == null || raw.isEmpty) return '';
  return raw;
}

class ChatConversationPage extends ConsumerStatefulWidget {
  const ChatConversationPage({
    super.key,
    required this.conversationId,
    required this.onBack,
    this.searchAnchorContext,
    this.embedded = false,
  });

  final String conversationId;
  final VoidCallback onBack;
  final SearchConversationAnchorContext? searchAnchorContext;
  final bool embedded;

  @override
  ConsumerState<ChatConversationPage> createState() =>
      _ChatConversationPageState();
}

class _ChatConversationPageState extends ConsumerState<ChatConversationPage> {
  final TextEditingController _inputController = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  final FocusNode _inputFocusNode = FocusNode();
  final ImagePicker _imagePicker = ImagePicker();
  final stt.SpeechToText _speechToText = stt.SpeechToText();

  ConversationDto? _conversationDto;
  String? _resolvedTitle;
  String? _otherParticipantId;
  RelationshipCapabilityDto? _relationshipCapability;
  bool _isSelectionMode = false;
  final Set<String> _selectedIds = <String>{};
  Map<String, Object?>? _actionMenuMessage;
  Offset? _actionMenuPosition;
  bool _speechReady = false;
  String _lastAsrText = '';

  @override
  void initState() {
    super.initState();
    _inputController.addListener(_onInputChanged);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      Future<void>(() async {
        final notifier = ref.read(
          chatMessageProvider(widget.conversationId).notifier,
        );
        await notifier.loadMessages();
        final marked = await notifier.markConversationRead();
        if (marked && mounted) {
          ref
              .read(chatInboxListProvider.notifier)
              .markConversationRead(widget.conversationId);
        }
      });
      ref
          .read(realtimeConnectionManagerProvider.notifier)
          .onEnterChatDetail(widget.conversationId);
    });
  }

  @override
  void deactivate() {
    ref.read(realtimeConnectionManagerProvider.notifier).onLeaveChatDetail();
    super.deactivate();
  }

  @override
  void dispose() {
    _speechToText.cancel();
    _inputController.removeListener(_onInputChanged);
    _inputController.dispose();
    _scrollController.dispose();
    _inputFocusNode.dispose();
    super.dispose();
  }

  void _onInputChanged() {
    if (mounted) setState(() {});
  }

  Future<void> _loadConversationTitle() async {
    if (_resolvedTitle != null) return;
    try {
      final repo = ref.read(chatRepositoryProvider);
      final conv = await repo.getConversation(widget.conversationId);
      final dto = ConversationDto.fromMap(conv);
      if (!mounted) return;
      setState(() {
        _resolvedTitle = dto.title ?? widget.conversationId;
        _conversationDto = dto;
      });
      if (dto.type == 'direct') {
        _loadOtherParticipantId(repo);
      }
    } catch (_) {}
  }

  Future<void> _loadOtherParticipantId(ChatRepository repo) async {
    try {
      final currentUserId = ref.read(userDataProvider)?.id ?? '';
      final members = await repo.listMembers(
        conversationId: widget.conversationId,
        limit: 10,
      );
      final others = members.where((m) => m.userId != currentUserId).toList();
      final otherId =
          others.isEmpty ? null : others.first.userId;
      if (mounted && otherId != null && otherId.isNotEmpty) {
        setState(() => _otherParticipantId = otherId);
        await _loadRelationshipCapability(otherId);
      }
    } catch (_) {}
  }

  Future<void> _loadRelationshipCapability(String otherId) async {
    try {
      final capability = await ref
          .read(relationshipCapabilityRepositoryProvider)
          .getCapability(otherId);
      if (!mounted) return;
      setState(() => _relationshipCapability = capability);
    } catch (_) {}
  }

  bool get _isGroupChat => _conversationDto?.type == 'group';

  int get _memberCount => _conversationDto?.memberCount ?? 0;

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
      thumbnailProvider: FileImage(File(picked.path)),
    );
  }

  Future<List<ChatInputAttachment>> _pickChatFiles(int remaining) async {
    final result = await FilePicker.platform.pickFiles(
      allowMultiple: true,
      withData: false,
    );
    if (result == null) return const <ChatInputAttachment>[];
    final now = DateTime.now().millisecondsSinceEpoch;
    return result.files
        .take(remaining)
        .map<ChatInputAttachment>(
          (file) => ChatInputAttachment(
            id: 'file_${now}_${file.name}',
            type: ChatInputAttachmentType.file,
            name: file.name,
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

  Future<bool> _ensureSpeechReady() async {
    if (_speechReady) return true;
    _speechReady = await _speechToText.initialize(
      onError: (_) {},
      onStatus: (_) {},
    );
    return _speechReady;
  }

  Future<bool> _requestMicPermissionForChat() async {
    final micStatus = await Permission.microphone.status;
    if (micStatus.isGranted) {
      return _ensureSpeechReady();
    }
    final requested = await Permission.microphone.request();
    if (requested.isGranted) {
      return _ensureSpeechReady();
    }
    if (requested.isPermanentlyDenied && mounted) {
      AppToast.show(context, UITextConstants.chatVoicePermissionDenied);
      openAppSettings();
    }
    return false;
  }

  Future<void> _startVoiceRecordForChat() async {
    _lastAsrText = '';
    if (!await _ensureSpeechReady()) return;
    if (_speechToText.isListening) {
      await _speechToText.stop();
    }
    await _speechToText.listen(
      onResult: (result) {
        _lastAsrText = result.recognizedWords.trim();
      },
      listenOptions: stt.SpeechListenOptions(
        partialResults: true,
        cancelOnError: true,
        listenMode: stt.ListenMode.dictation,
      ),
      localeId: 'zh_CN',
      pauseFor: const Duration(seconds: 2),
      listenFor: const Duration(minutes: 2),
    );
  }

  Future<void> _stopVoiceRecordForChat(Duration duration) async {
    if (_speechToText.isListening) {
      await _speechToText.stop();
    }
    await Future<void>.delayed(const Duration(milliseconds: 120));
  }

  Future<String?> _voiceAsrForChat(Duration duration) async {
    final text = _lastAsrText.trim();
    if (text.isNotEmpty) return text;
    if (duration.inMilliseconds < 500) return null;
    return '语音消息（${duration.inSeconds}s）';
  }

  Future<void> _submitChatInput(ChatInputSubmitPayload payload) async {
    final notifier = ref.read(chatMessageProvider(widget.conversationId).notifier);
    if (payload.attachments.isNotEmpty) {
      for (final item in payload.attachments) {
        final kind = item.type == ChatInputAttachmentType.image
            ? UITextConstants.chatMorePhoto
            : UITextConstants.chatMoreFile;
        await notifier.sendMessage('text', '[$kind] ${item.name}');
      }
    }
    var text = payload.text.trim();
    if (payload.isVoiceMessage && text.isEmpty) {
      text = '语音消息（${payload.voiceDuration.inSeconds}s）';
    }
    if (text.isNotEmpty) {
      await _sendMessage(draftText: text);
    }
  }

  Future<void> _sendMessage({String? draftText}) async {
    _inputFocusNode.unfocus();
    await Future<void>.delayed(const Duration(milliseconds: 150));
    final text = (draftText ?? _inputController.text).trim();
    if (text.isEmpty) return;
    if (draftText == null) _inputController.clear();
    ref
        .read(chatMessageProvider(widget.conversationId).notifier)
        .sendMessage('text', text);
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

  List<ChatInputExtraPanelItem> _buildCallPanelItems() {
    final canCall =
        _isGroupChat ||
        (_otherParticipantId != null &&
            (_relationshipCapability?.canStartVoiceCall == true ||
                _relationshipCapability?.canStartVideoCall == true));
    if (!canCall) return const <ChatInputExtraPanelItem>[];
    final voiceLabel = _isGroupChat
        ? UITextConstants.callGroupVoice
        : UITextConstants.callVoice;
    final videoLabel = _isGroupChat
        ? UITextConstants.callGroupVideo
        : UITextConstants.callVideo;
    final items = <ChatInputExtraPanelItem>[
      ChatInputExtraPanelItem(
        icon: CupertinoIcons.phone,
        text: voiceLabel,
        onTap: () async => _initiateCall('voice'),
      ),
      ChatInputExtraPanelItem(
        icon: CupertinoIcons.video_camera,
        text: videoLabel,
        onTap: () async => _initiateCall('video'),
      ),
    ];
    if (kDebugMode) {
      items.addAll(<ChatInputExtraPanelItem>[
        ChatInputExtraPanelItem(
          icon: CupertinoIcons.phone_badge_plus,
          text: UITextConstants.callDebugSimulateIncomingVoice,
          onTap: () async => _simulateIncomingCall('voice'),
        ),
        ChatInputExtraPanelItem(
          icon: CupertinoIcons.video_camera_solid,
          text: UITextConstants.callDebugSimulateIncomingVideo,
          onTap: () async => _simulateIncomingCall('video'),
        ),
      ]);
    }
    return items;
  }

  Future<void> _initiateCall(String callType) async {
    final notifier = ref.read(callSessionProvider.notifier);
    final List<String> targetIds;
    if (_isGroupChat) {
      final result = await context.push<List<String>>(
        AppRoutePaths.rtcPickParticipants,
        extra: CallParticipantPickerRouteExtra(
          conversationId: widget.conversationId,
          defaultSelectAll: _memberCount <= 8,
        ),
      );
      if (result == null || result.isEmpty || !mounted) return;
      targetIds = result;
    } else {
      final otherId = _otherParticipantId;
      if (otherId == null || otherId.isEmpty) return;
      targetIds = <String>[otherId];
    }
    final callId = await notifier.initiateCall(
      callTypeStr: callType,
      targetUserIds: targetIds,
      conversationId: widget.conversationId,
    );
    if (callId != null && mounted) {
      context.push(AppRoutePaths.rtcOutgoing(callId: callId));
    }
  }

  Future<void> _simulateIncomingCall(String callType) async {
    final callId = 'debug_incoming_${DateTime.now().millisecondsSinceEpoch}';
    ref
        .read(callSessionProvider.notifier)
        .debugSeedIncomingCall(
          callId: callId,
          callerName: _conversationTitle,
          callType: callType,
          conversationId: widget.conversationId,
        );
    if (!mounted) return;
    await context.push(AppRoutePaths.rtcIncoming(callId: callId));
  }

  Future<void> _sendSameInterestRequest() async {
    final otherId = _otherParticipantId;
    if (otherId == null || otherId.isEmpty) return;
    try {
      await ref
          .read(greetingRepositoryProvider)
          .sendGreeting(
            targetSubAccountId: otherId,
            requestMessage: '想和你成为同好，一起聊聊吧',
            source: 'chat',
          );
      if (!mounted) return;
      AppToast.show(context, '已发送同好邀请');
    } catch (_) {
      if (!mounted) return;
      AppToast.show(context, '发送失败，请稍后再试');
    }
  }

  Widget _buildSameInterestPromptBar() {
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
      child: Row(
        children: [
          Expanded(
            child: Text(
              '成为同好后可直接发起语音和视频通话',
              style: TextStyle(
                color: AppColors.primaryColor,
                fontSize: AppTypography.sm,
                fontWeight: FontWeight.w500,
              ),
            ),
          ),
          SizedBox(width: AppSpacing.sm),
          CupertinoButton(
            padding: EdgeInsets.symmetric(
              horizontal: AppSpacing.sm,
              vertical: AppSpacing.xs,
            ),
            color: AppColors.primaryColor,
            borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
            onPressed: _sendSameInterestRequest,
            child: Text(
              UITextConstants.profileAddSameInterest,
              style: TextStyle(
                color: AppColors.white,
                fontSize: AppTypography.sm,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ],
      ),
    );
  }

  void _onLongPressMessage(
    Map<String, Object?> message,
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
    switch (action) {
      case 'forward':
        _shareMessages(<Map<String, Object?>>[msg]);
        break;
      case 'select':
        setState(() {
          _isSelectionMode = true;
          _selectedIds.add(msg['id'] as String);
        });
        break;
      case 'copy':
        final content = msg['content'] as String? ?? '';
        if (content.isNotEmpty) {
          Clipboard.setData(ClipboardData(text: content));
          if (mounted) {
            AppToast.show(context, UITextConstants.copiedToClipboard);
          }
        }
        break;
      case 'recall':
        if (msg['isSelf'] == true) {
          ref
              .read(chatMessageProvider(widget.conversationId).notifier)
              .recallMessage((msg['id'] as String?) ?? '');
        }
        break;
      case 'delete':
        break;
    }
    setState(() {
      _actionMenuMessage = null;
      _actionMenuPosition = null;
    });
  }

  Future<void> _shareMessages(List<Map<String, Object?>> messages) async {
    final lines = messages
        .map((item) => (item['content'] as String?)?.trim() ?? '')
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

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final currentUserId = ref.watch(currentUserIdProvider);
    final bgColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final chatListBg = isDark ? bgColor : AppColors.chatBackground;
    final displayMessages = ref
        .watch(chatMessageProvider(widget.conversationId))
        .messages
        .map((dto) => dto.toDisplayMap(currentUserId: currentUserId))
        .toList();
    final timelinePadding = EdgeInsets.symmetric(
      horizontal:
          AppSpacing.semantic[DesignSemanticConstants.container]?[DesignSemanticConstants.sm] ??
          AppSpacing.containerSm,
      vertical: AppSpacing.md,
    );
    final actionMenuOverlay =
        _actionMenuMessage != null && _actionMenuPosition != null
        ? ConversationMessageActionMenuOverlay(
            message: _actionMenuMessage!,
            position: _actionMenuPosition!,
            onAction: _onMessageAction,
            onClose: () => setState(() {
              _actionMenuMessage = null;
              _actionMenuPosition = null;
            }),
          )
        : null;

    final bodyContent = Column(
      children: [
          if (widget.searchAnchorContext case final anchor?)
            _SearchAnchorBanner(
              sourceQuery: anchor.sourceQuery,
              isDark: isDark,
            ),
          Expanded(
            child: ConversationTimeline(
              controller: _scrollController,
              backgroundColor: chatListBg,
              padding: timelinePadding,
              itemCount: displayMessages.length,
              itemBuilder: (context, index) {
                final msg = displayMessages[index];
                final prevTime = index > 0
                    ? displayMessages[index - 1]['timestamp'] as String?
                    : null;
                final showTime = index == 0 || msg['timestamp'] != prevTime;
                final timeStr = formatChatTime(msg['timestamp'] as String?);
                return Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    if (showTime && timeStr.isNotEmpty)
                      Padding(
                        padding: EdgeInsets.only(
                          bottom:
                              AppSpacing.semantic[DesignSemanticConstants.intraGroup]?[DesignSemanticConstants.sm] ??
                              AppSpacing.intraGroupSm,
                        ),
                        child: Center(
                          child: Text(
                            timeStr,
                            style: TextStyle(
                              fontSize: AppTypography.sm,
                              color: fgPrimary.withValues(alpha: 0.5),
                            ),
                          ),
                        ),
                      ),
                    ChatMessageBubble(
                      message: msg,
                      isRight: msg['isSelf'] == true,
                      bubbleColor: msg['isSelf'] == true
                          ? AppColors.chatBubbleOutgoing
                          : AppColors.chatBubbleIncoming,
                      textColor: msg['isSelf'] == true ? AppColors.white : fgPrimary,
                      isSelectionMode: _isSelectionMode,
                      isSelected: _selectedIds.contains(msg['id']),
                      onLongPressStart: (details) => _onLongPressMessage(
                        Map<String, Object?>.from(msg),
                        details.globalPosition,
                      ),
                      onTap: _isSelectionMode
                          ? () => _toggleSelect(msg['id'] as String)
                          : null,
                      receiptEnabled: false,
                      memberCount: _memberCount,
                      messageStatus: msg['status'] as String?,
                      onAvatarTap: () {
                        final senderId = msg['senderId'] as String? ?? '';
                        if (msg['isSelf'] == true) {
                          final currentUser = ref.read(userDataProvider);
                          final userId = currentUser?.username ?? currentUser?.id;
                          if (userId != null && userId.isNotEmpty) {
                            context.push(
                              AppRoutePaths.userProfile(username: userId),
                            );
                          }
                        } else if (senderId.isNotEmpty) {
                          context.push(
                            AppRoutePaths.userProfile(username: senderId),
                            extra: UserProfileRouteExtra(
                              profileSubjectId: senderId,
                            ),
                          );
                        }
                      },
                    ),
                  ],
                );
              },
            ),
          ),
          ColoredBox(
            color: isDark ? bgColor : AppColors.chatToolbarBackground,
            child: SafeArea(
              top: false,
              child: Padding(
                padding: EdgeInsets.fromLTRB(
                  AppSpacing.semantic[DesignSemanticConstants.container]?[DesignSemanticConstants.sm] ??
                      AppSpacing.containerSm,
                  AppSpacing.sm,
                  AppSpacing.semantic[DesignSemanticConstants.container]?[DesignSemanticConstants.sm] ??
                      AppSpacing.containerSm,
                  AppSpacing.sm,
                ),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    if (!_isGroupChat &&
                        _relationshipCapability?.isSameInterest != true &&
                        _otherParticipantId != null)
                      _buildSameInterestPromptBar(),
                    CustomizableChatInputBar(
                      controller: _inputController,
                      focusNode: _inputFocusNode,
                      maxTextLength: 5000,
                      maxVisibleLines: 5,
                      onPickImages: _pickChatImages,
                      onCapturePhoto: _captureChatPhoto,
                      onPickFiles: _pickChatFiles,
                      onRequestMicPermission: _requestMicPermissionForChat,
                      onStartRecord: _startVoiceRecordForChat,
                      onStopRecord: _stopVoiceRecordForChat,
                      onVoiceAsrTransform: _voiceAsrForChat,
                      onSend: _submitChatInput,
                      showEmojiButton: true,
                      extraPanelItems: _buildCallPanelItems(),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
    );

    return ConversationPageScaffold(
      embedded: widget.embedded,
      backgroundColor: bgColor,
      navigationBar: widget.embedded
          ? null
          : AppNavigationBar(
              backgroundColor: bgColor,
              leading: AppNavigationBarIconButton(
                icon: _isSelectionMode
                    ? CupertinoIcons.xmark
                    : CupertinoIcons.back,
                onPressed:
                    _isSelectionMode ? _cancelSelection : widget.onBack,
              ),
              middle: Text(
                _isSelectionMode
                    ? '已选 ${_selectedIds.length} 条'
                    : _conversationTitle,
                style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
              ),
              trailing: _isSelectionMode
                  ? CupertinoButton(
                      padding: EdgeInsets.zero,
                      onPressed: () async {
                        final selectedMessages = displayMessages
                            .where(
                              (item) => _selectedIds.contains(
                                (item['id'] as String?) ?? '',
                              ),
                            )
                            .toList(growable: false);
                        await _shareMessages(selectedMessages);
                        _cancelSelection();
                      },
                      child: Text(
                        UITextConstants.messageActionForward,
                        style: TextStyle(
                          color: AppNavigationSemanticConstants.barTitleColor(
                            isDark,
                          ),
                          fontSize: AppTypography.iosNavTitle,
                          fontWeight: AppTypography.semiBold,
                        ),
                      ),
                    )
                  : AppNavigationBarIconButton(
                      icon: CupertinoIcons.ellipsis,
                      onPressed: () => context.push(
                        AppRoutePaths.chatSettings(id: widget.conversationId),
                      ),
                    ),
            ),
      body: bodyContent,
      overlays: actionMenuOverlay == null
          ? const <Widget>[]
          : <Widget>[actionMenuOverlay],
    );
  }
}

class _SearchAnchorBanner extends StatelessWidget {
  const _SearchAnchorBanner({
    required this.sourceQuery,
    required this.isDark,
  });

  final String? sourceQuery;
  final bool isDark;

  @override
  Widget build(BuildContext context) {
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    return Padding(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.containerSm,
        AppSpacing.containerSm,
        AppSpacing.containerSm,
        0,
      ),
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: AppColors.primaryColor.withValues(alpha: 0.1),
          borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
          border: Border.all(color: AppColors.primaryColor.withValues(alpha: 0.18)),
        ),
        child: Padding(
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.containerSm,
            vertical: AppSpacing.intraGroupSm,
          ),
          child: Row(
            children: [
              Icon(
                CupertinoIcons.scope,
                size: AppSpacing.iconSmall,
                color: AppColors.primaryColor,
              ),
              SizedBox(width: AppSpacing.intraGroupXs),
              Expanded(
                child: Text(
                  sourceQuery == null || sourceQuery!.isEmpty
                      ? '已从搜索结果进入该聊天，消息锚点将在后续服务接入后补齐。'
                      : '已从“$sourceQuery”定位到相关聊天，消息锚点将在后续服务接入后补齐。',
                  style: TextStyle(
                    fontSize: AppTypography.iosCaption1,
                    color: fgPrimary,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
