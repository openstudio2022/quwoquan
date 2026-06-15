import 'dart:async';
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
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/chat/models/conversation_dto.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/cloud/chat/models/message_dto.dart';
import 'package:quwoquan_app/cloud/media/media_upload_manager.dart';
import 'package:quwoquan_app/cloud/media/upload_policy.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/components/conversation/conversation_page_scaffold.dart';
import 'package:quwoquan_app/components/conversation/conversation_timeline.dart';
import 'package:quwoquan_app/components/conversation/message_action_menu_overlay.dart';
import 'package:quwoquan_app/components/input/customizable_chat_input_bar.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/models/user_profile_route_extra.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/cloud/services/realtime/realtime_connection_notifier.dart';
import 'package:quwoquan_app/ui/chat/providers/chat_message_provider.dart';
import 'package:quwoquan_app/ui/chat/providers/message_home_rows_provider.dart';
import 'package:quwoquan_app/ui/chat/providers/voice_offline_queue.dart';
import 'package:quwoquan_app/ui/chat/providers/voice_player_manager.dart';
import 'package:quwoquan_app/ui/chat/providers/voice_send_provider.dart';
import 'package:quwoquan_app/ui/chat/widgets/message/chat_message_bubble.dart';
import 'package:quwoquan_app/ui/chat/widgets/voice/voice_recorder.dart';
import 'package:quwoquan_app/ui/rtc/models/call_state.dart';
import 'package:quwoquan_app/ui/rtc/models/call_participant_picker_route_extra.dart';
import 'package:quwoquan_app/ui/rtc/providers/call_session_provider.dart';
import 'package:quwoquan_app/ui/rtc/widgets/call_permission_guard.dart';

String formatChatTime(String? raw) {
  if (raw == null || raw.isEmpty) return '';
  return raw;
}

final RouteObserver<ModalRoute<dynamic>> chatRouteObserver =
    RouteObserver<ModalRoute<dynamic>>();

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

class _ChatConversationPageState extends ConsumerState<ChatConversationPage>
    with RouteAware {
  final TextEditingController _inputController = TextEditingController();
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

  @override
  void initState() {
    super.initState();
    _inputController.addListener(_onInputChanged);
    _realtimeNotifier = ref.read(realtimeConnectionManagerProvider.notifier);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      unawaited(_bootstrapConversation(widget.conversationId));
    });
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _subscribeRouteAware();
  }

  @override
  void dispose() {
    final route = _subscribedRoute;
    if (route != null) {
      chatRouteObserver.unsubscribe(this);
      _subscribedRoute = null;
    }
    _detachRealtime();
    AppToast.dismiss();
    unawaited(_voiceRecorder.dispose());
    _inputController.removeListener(_onInputChanged);
    _inputController.dispose();
    _scrollController.dispose();
    _inputFocusNode.dispose();
    super.dispose();
  }

  Future<void> _bootstrapConversation(String conversationId) async {
    final notifier = ref.read(chatMessageProvider(conversationId).notifier);
    await notifier.loadMessages();
    final marked = await notifier.markConversationRead();
    if (!marked || !mounted) {
      return;
    }
    // 会话列表页 keepAlive 仍在树上；已读回写须在当前帧结束后执行。
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      refreshMessageReadState(ref, conversationId);
    });
  }

  void _subscribeRouteAware() {
    if (widget.embedded || !mounted) {
      return;
    }
    final route = ModalRoute.of(context);
    if (route == null || _subscribedRoute == route) {
      return;
    }
    final previousRoute = _subscribedRoute;
    if (previousRoute != null) {
      chatRouteObserver.unsubscribe(this);
    }
    _subscribedRoute = route;
    chatRouteObserver.subscribe(this, route);
  }

  void _attachRealtime() {
    if (_realtimeAttached) {
      return;
    }
    final notifier = _realtimeNotifier;
    if (notifier == null) {
      return;
    }
    _realtimeAttached = true;
    scheduleMicrotask(() => notifier.onEnterChatDetail(widget.conversationId));
  }

  void _detachRealtime() {
    if (!_realtimeAttached) {
      return;
    }
    _realtimeAttached = false;
    final notifier = _realtimeNotifier;
    if (notifier == null) {
      return;
    }
    scheduleMicrotask(notifier.onLeaveChatDetail);
  }

  @override
  void didPush() {
    _attachRealtime();
  }

  @override
  void didPopNext() {
    _attachRealtime();
  }

  @override
  void didPushNext() {
    _detachRealtime();
  }

  @override
  void didPop() {
    _detachRealtime();
  }

  void _onInputChanged() {
    if (mounted) setState(() {});
  }

  Future<void> _showVoiceSendFailure(Object error) async {
    if (!mounted) {
      return;
    }
    final resolved = runtimeErrorSemantic(
      context,
      error: error,
      category: UiErrorCategory.submit,
      scope: UiErrorScope.global,
    );
    await AppActionErrorFeedback.show(
      context,
      semantic: UiErrorSemantic(
        category: resolved.category,
        scope: resolved.scope,
        title: UITextConstants.chatVoiceSendFailedTitle,
        message: resolved.message,
        secondaryMessage: resolved.secondaryMessage,
        primaryAction:
            resolved.primaryAction ??
            const UiErrorAction(
              type: UiErrorActionType.dismiss,
              label: UITextConstants.confirm,
            ),
        secondaryAction: resolved.secondaryAction,
        dismissible: true,
        sourceCode: resolved.sourceCode,
        failureKind: resolved.failureKind,
        recoveryAction: resolved.recoveryAction,
      ),
    );
  }

  Future<void> _showVoicePermissionFailure({required bool openSettings}) async {
    if (!mounted) {
      return;
    }
    await AppActionErrorFeedback.show(
      context,
      semantic: UiErrorSemantic(
        category: UiErrorCategory.permissionRequired,
        scope: UiErrorScope.global,
        title: UITextConstants.chatVoicePermissionDenied,
        message: openSettings
            ? UITextConstants.chatVoicePermissionOpenSettings
            : UITextConstants.chatVoicePermissionDenied,
        primaryAction: UiErrorAction(
          type: openSettings
              ? UiErrorActionType.openSettings
              : UiErrorActionType.dismiss,
          label: openSettings
              ? UITextConstants.openSettings
              : UITextConstants.confirm,
        ),
        secondaryAction: openSettings
            ? const UiErrorAction(
                type: UiErrorActionType.dismiss,
                label: UITextConstants.cancel,
              )
            : null,
        dismissible: true,
        presentation: UiErrorPresentation.actionDialog,
      ),
      onAction: (action) async {
        if (action.type == UiErrorActionType.openSettings) {
          await openAppSettings();
        }
      },
    );
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

  Future<void> _loadConversationTitle() async {
    if (_resolvedTitle != null) return;
    try {
      final repo = ref.read(chatRepositoryProvider);
      final dto = await repo.getConversation(widget.conversationId);
      if (!mounted) return;
      setState(() {
        _resolvedTitle = dto.title ?? widget.conversationId;
        _conversationDto = dto;
      });
      if (dto.type == 'direct') {
        _loadOtherParticipantId(repo);
      }
    } catch (_) {
      /* best-effort: 加载会话标题失败时回退到 conversationId 作为标题，不阻断聊天 */
    }
  }

  Future<void> _loadOtherParticipantId(ChatRepository repo) async {
    try {
      final currentUserId = ref.read(userDataProvider)?.id ?? '';
      final members = await repo.listMembers(
        conversationId: widget.conversationId,
        limit: 10,
      );
      final others = members.where((m) => m.userId != currentUserId).toList();
      final otherId = others.isEmpty ? null : others.first.userId;
      if (mounted && otherId != null && otherId.isNotEmpty) {
        setState(() => _otherParticipantId = otherId);
        await _loadRelationshipCapability(otherId);
      }
    } catch (_) {
      /* best-effort: 解析单聊对端 userId 失败仅影响关系能力展示，不阻断聊天主流程 */
    }
  }

  Future<void> _loadRelationshipCapability(String otherId) async {
    try {
      final capability = await ref
          .read(relationshipCapabilityRepositoryProvider)
          .getCapability(otherId);
      if (!mounted) return;
      setState(() => _relationshipCapability = capability);
    } catch (_) {
      /* best-effort: 获取关系能力失败时维持空能力态，相关入口按默认隐藏处理 */
    }
  }

  bool get _isGroupChat => _conversationDto?.type == 'group';

  int get _memberCount => _conversationDto?.memberCount ?? 0;

  bool get _isBlockedConversation => _conversationDto?.status == 'blocked';

  bool get _canInitiateOneToOneCall {
    if (_isGroupChat) {
      return true;
    }
    return _otherParticipantId != null &&
        !_isBlockedConversation &&
        (_relationshipCapability?.canStartVoiceCall == true ||
            _relationshipCapability?.canStartVideoCall == true);
  }

  bool get _shouldDisableComposer {
    if (_isGroupChat) {
      return false;
    }
    if (_isBlockedConversation) {
      return true;
    }
    final capability = _relationshipCapability;
    if (capability == null) {
      return false;
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
      return UITextConstants.chatMoreVideo;
    }
    if (_looksLikeImageAttachment(item)) {
      return UITextConstants.chatMorePhoto;
    }
    return UITextConstants.chatMoreFile;
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
        title: UITextConstants.chatAttachmentUploadFailed,
        message: '本地附件不存在，请重新选择后再试。',
      );
      return;
    }
    final category = _attachmentCategory(item);
    final ownerId = ref.read(currentUserIdProvider).trim();
    final uploadManager = ref.read(mediaUploadManagerProvider);
    final queued = await uploadManager.enqueue(
      UploadTask(
        localPath: localPath,
        category: category,
        contentType: _attachmentContentType(item),
        fileSize: await file.length(),
        ownerId: ownerId.isNotEmpty ? ownerId : 'current_user',
        fileName: item.name,
        completionMetadata: <String, dynamic>{
          'fileName': item.name,
          'kind': category.name,
        },
      ),
    );
    final uploaded = await _awaitUploadCompletion(uploadManager, queued);
    final cdnUrl = uploaded.cdnUrl?.trim() ?? '';
    if (uploaded.status == UploadStatus.failed || cdnUrl.isEmpty) {
      await _showAttachmentFailure(
        title: UITextConstants.chatAttachmentUploadFailed,
        message: '附件上传未完成，请稍后再试。',
      );
      return;
    }
    final messageType = _attachmentMessageType(item);
    final mediaPayload = <String, dynamic>{
      'url': cdnUrl,
      'fileName': item.name,
      'mimeType': _attachmentContentType(item),
      'fileSizeBytes': uploaded.fileSize,
    };
    if (messageType == 'image') {
      mediaPayload['thumbnailUrl'] = cdnUrl;
    }
    if (messageType == 'video') {
      mediaPayload['thumbnailUrl'] = cdnUrl;
      mediaPayload['durationMs'] = 0;
    }
    final sent = await notifier.sendMessage(
      messageType,
      messageType == 'image' ? '' : item.name,
      mediaUrl: cdnUrl,
      media: mediaPayload,
    );
    if (!sent) {
      await _showAttachmentFailure(
        title: UITextConstants.chatAttachmentSendFailed,
        message: '附件发送未完成，请稍后再试。',
      );
    }
  }

  Future<bool> _requestMicPermissionForChat() async {
    final micStatus = await Permission.microphone.status;
    if (micStatus.isGranted) {
      return true;
    }
    final requested = await Permission.microphone.request();
    if (requested.isGranted) {
      return true;
    }
    if (requested.isPermanentlyDenied && mounted) {
      await _showVoicePermissionFailure(openSettings: true);
    } else if (mounted) {
      await _showVoicePermissionFailure(openSettings: false);
    }
    return false;
  }

  Future<bool> _startVoiceRecordForChat() async {
    final started = await _voiceRecorder.start();
    if (!started && mounted) {
      AppToast.show(context, UITextConstants.chatVoiceRecordUnavailable);
    }
    return started;
  }

  Future<void> _stopVoiceRecordForChat(Duration duration) async {
    final result = await _voiceRecorder.stop();
    if (!mounted) return;
    if (result == null) {
      AppToast.show(context, UITextConstants.chatVoiceTooShort);
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
          .read(voiceOfflineQueueProvider(widget.conversationId).notifier)
          .enqueue(result);
      await _showVoiceSendFailure(sendState.error!);
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
      AppToast.show(context, UITextConstants.chatVoiceCanceled);
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
    final resolvedMentions = _resolveAssistantMentions(
      text: text,
      mentions: mentions,
    );
    ref
        .read(chatMessageProvider(widget.conversationId).notifier)
        .sendMessage('text', text, mentions: resolvedMentions);
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

  List<String>? _resolveAssistantMentions({
    required String text,
    List<String>? mentions,
  }) {
    if (!_isGroupChat) {
      return null;
    }
    final values = <String>{...?mentions};
    if (text.contains(UITextConstants.commentAtXiaoqu)) {
      values.add('assistant');
    }
    return values.isEmpty ? null : values.toList(growable: false);
  }

  List<ChatInputExtraPanelItem> _buildCallPanelItems() {
    final canCall = _canInitiateOneToOneCall;
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
    if (!_isGroupChat && !_canInitiateOneToOneCall) {
      if (!mounted) {
        return;
      }
      final resolved = runtimeErrorSemantic(
        context,
        error: StateError('relationship gate denied call'),
        category: UiErrorCategory.submit,
        scope: UiErrorScope.global,
      );
      await AppActionErrorFeedback.show(context, semantic: resolved);
      return;
    }
    final requestedType = CallType.fromString(callType);
    final permissionOutcome = await CallPermissionGuard.ensure(
      context,
      callType: requestedType,
    );
    if (!mounted || permissionOutcome == CallPermissionOutcome.blocked) {
      return;
    }
    final effectiveType =
        permissionOutcome == CallPermissionOutcome.fallbackVoiceOnly
        ? CallType.audio
        : requestedType;
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
      callTypeStr: effectiveType.toApiString(),
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
        UITextConstants.chatMutualFollowRtcHint,
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
        UITextConstants.chatBlockedConversationHint,
        style: TextStyle(
          color: AppColors.error,
          fontSize: AppTypography.sm,
          fontWeight: FontWeight.w500,
        ),
      ),
    );
  }

  Widget _buildVoiceSendStatusBar(VoiceSendState state) {
    final queuedCount = ref.watch(
      voiceOfflineQueueProvider(widget.conversationId),
    );
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
      VoiceSendStatus.uploading => UITextConstants.chatVoiceUploading,
      VoiceSendStatus.sending => UITextConstants.chatVoiceSending,
      VoiceSendStatus.failed =>
        state.error ?? UITextConstants.chatVoiceSendFailed,
      _ => UITextConstants.chatVoiceSending,
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
                  onPressed: () => ref
                      .read(voiceSendProvider(widget.conversationId).notifier)
                      .reset(),
                  child: Text(
                    UITextConstants.gotIt,
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
                  '${UITextConstants.chatVoiceQueued} ($queuedCount)',
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
                onPressed: () => ref
                    .read(
                      voiceOfflineQueueProvider(widget.conversationId).notifier,
                    )
                    .drain(),
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
            AppToast.show(context, UITextConstants.copiedToClipboard);
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
      case 'delete':
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
        .map((dto) => dto.toDisplayItem(currentUserId: currentUserId))
        .toList();
    final voiceSendState = ref.watch(voiceSendProvider(widget.conversationId));
    final timelinePadding = EdgeInsets.symmetric(
      horizontal:
          AppSpacing.semantic[DesignSemanticConstants
              .container]?[DesignSemanticConstants.sm] ??
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

    // 时间分隔降噪：仅首条与「距上次展示时间 ≥ 阈值」处居中显示，避免连续
    // 消息每分钟都插一条时间，导致密集分隔（深浅色与移动端一致）。
    final showTimeFlags = _computeTimeSeparatorFlags(displayMessages);

    final bodyContent = Column(
      children: [
        if (widget.searchAnchorContext case final anchor?)
          _SearchAnchorBanner(sourceQuery: anchor.sourceQuery, isDark: isDark),
        Expanded(
          child: ConversationTimeline(
            controller: _scrollController,
            backgroundColor: chatListBg,
            padding: timelinePadding,
            itemCount: displayMessages.length,
            itemBuilder: (context, index) {
              final msg = displayMessages[index];
              final showTime = showTimeFlags[index];
              final timeStr = formatChatTime(msg.timestampLabel);
              return Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (showTime && timeStr.isNotEmpty)
                    Padding(
                      padding: EdgeInsets.only(
                        bottom:
                            AppSpacing.semantic[DesignSemanticConstants
                                .intraGroup]?[DesignSemanticConstants.sm] ??
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
                    isRight: msg.isSelf,
                    bubbleColor: msg.isSelf
                        ? AppColors.chatBubbleOutgoing
                        : AppColors.chatBubbleIncoming,
                    textColor: msg.isSelf ? AppColors.white : fgPrimary,
                    isSelectionMode: _isSelectionMode,
                    isSelected: _selectedIds.contains(msg.id),
                    onLongPressStart: (details) =>
                        _onLongPressMessage(msg, details.globalPosition),
                    onTap: _isSelectionMode
                        ? () => _toggleSelect(msg.id)
                        : null,
                    receiptEnabled: false,
                    memberCount: _memberCount,
                    onAvatarTap: () {
                      final senderId = msg.senderId;
                      if (msg.isSelf) {
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
                          extra: UserProfileRouteExtra(subAccountId: senderId),
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
                AppSpacing.semantic[DesignSemanticConstants
                        .container]?[DesignSemanticConstants.sm] ??
                    AppSpacing.containerSm,
                AppSpacing.chatInputToolbarVerticalPadding,
                AppSpacing.semantic[DesignSemanticConstants
                        .container]?[DesignSemanticConstants.sm] ??
                    AppSpacing.containerSm,
                AppSpacing.chatInputToolbarVerticalPadding,
              ),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (_isBlockedConversation)
                    _buildBlockedConversationHintBar(),
                  if (!_isGroupChat &&
                      _relationshipCapability?.isMutual != true &&
                      _otherParticipantId != null)
                    _buildMutualFollowRtcHintBar(),
                  _buildVoiceSendStatusBar(voiceSendState),
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
                    onCancelRecord: _cancelVoiceRecordForChat,
                    voiceAmplitudeStream: _voiceRecorder.onAmplitude,
                    onSend: _submitChatInput,
                    enableVoiceInput: true,
                    showEmojiButton: true,
                    showXiaoquMentionButton: _isGroupChat,
                    disabled: _shouldDisableComposer,
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
                onPressed: _isSelectionMode ? _cancelSelection : widget.onBack,
              ),
              middle: Text(
                _isSelectionMode
                    ? '已选 ${_selectedIds.length} 条'
                    : _conversationTitle,
                style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
              ),
              trailing: _isSelectionMode
                  ? AppNavigationBarTextAction(
                      label: UITextConstants.messageActionForward,
                      onPressed: () async {
                        final selectedMessages = displayMessages
                            .where((item) => _selectedIds.contains(item.id))
                            .toList(growable: false);
                        await _shareMessages(selectedMessages);
                        _cancelSelection();
                      },
                    )
                  : AppNavigationBarIconButton(
                      icon: CupertinoIcons.ellipsis,
                      onPressed: () => context.push(
                        AppRoutePaths.chatSettings(id: widget.conversationId),
                      ),
                    ),
            ),
      body: WebPageMaxWidthFrame(sideColor: bgColor, child: bodyContent),
      overlays: actionMenuOverlay == null
          ? const <Widget>[]
          : <Widget>[actionMenuOverlay],
    );
  }

  /// 计算每条消息是否需要在其上方居中展示时间分隔。
  ///
  /// 规则：首条恒展示；其余仅当与「上一次展示时间的消息」间隔 ≥ [_timeSeparatorGap]
  /// 时展示。缺少可解析 ISO 时间戳时回退到旧的「标签变化」规则，保证健壮。
  List<bool> _computeTimeSeparatorFlags(List<ChatMessageDisplayItem> items) {
    final flags = List<bool>.filled(items.length, false, growable: false);
    DateTime? lastShown;
    String? lastLabel;
    for (var i = 0; i < items.length; i++) {
      final item = items[i];
      final sentAt = DateTime.tryParse(item.sentAtIso);
      if (sentAt == null) {
        final changed = i == 0 || item.timestampLabel != lastLabel;
        flags[i] = changed;
        if (changed) {
          lastLabel = item.timestampLabel;
        }
        continue;
      }
      if (lastShown == null ||
          (sentAt.difference(lastShown)).abs() >= _timeSeparatorGap) {
        flags[i] = true;
        lastShown = sentAt;
        lastLabel = item.timestampLabel;
      }
    }
    return flags;
  }

  static const Duration _timeSeparatorGap = Duration(minutes: 5);
}

class _SearchAnchorBanner extends StatelessWidget {
  const _SearchAnchorBanner({required this.sourceQuery, required this.isDark});

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
          border: Border.all(
            color: AppColors.primaryColor.withValues(alpha: 0.18),
          ),
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
