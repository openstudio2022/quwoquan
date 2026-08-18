part of 'chat_conversation_page.dart';

abstract class _ChatConversationPageMediaActionsState
    extends ConsumerState<ChatConversationPage> {
  final ScrollController _scrollController = ScrollController();
  final ImagePicker _imagePicker = ImagePicker();
  // `late final` 让 recorder 在首次录音时才构造，此时 ConsumerState 的 ref
  // 已可用，异常遥测端口由 ProviderScope 决定（测试可 override）。
  late final VoiceRecorder _voiceRecorder = VoiceRecorder(
    maxDurationMs: kMaxRecordDurationMs + 1000,
    telemetry: ref.read(exceptionTelemetryPortProvider),
  );

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
          label: FoundationText.confirm,
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
            thumbnailProvider: localFileImageProvider(image.path),
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
      thumbnailProvider: localFileImageProvider(picked.path),
    );
  }

  Future<List<ChatInputAttachment>> _pickChatFiles(int remaining) async {
    final files = await FilePicker.pickFiles();
    if (files.isEmpty) return const <ChatInputAttachment>[];
    final now = DateTime.now().millisecondsSinceEpoch;
    final attachments = <ChatInputAttachment>[];
    for (final file in files.take(remaining)) {
      attachments.add(
        ChatInputAttachment(
          id: 'file_${now}_${file.name}',
          type: ChatInputAttachmentType.file,
          name: file.name,
          localPath: file.path,
          subtitle: _formatFileSize(await file.length()),
        ),
      );
    }
    return attachments;
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

  String _attachmentMimeType(ChatInputAttachment item) {
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
    MediaUploadQueue manager,
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
    ChatMessageTimelineController notifier,
  ) async {
    final localPath = _attachmentSourcePath(item);
    if (localPath.isEmpty) {
      await notifier.sendMessage(
        'text',
        '[${_attachmentFallbackLabel(item)}] ${item.name}',
      );
      return;
    }
    final fileStat = await readLocalFileStat(localPath);
    if (!fileStat.exists) {
      await _showAttachmentFailure(
        title: ChatText.chatAttachmentUploadFailed,
        message: ChatText.localAttachmentMissing,
      );
      return;
    }
    final category = _attachmentCategory(item);
    final uploadManager = ref.read(mediaUploadQueueProvider);
    final queued = await uploadManager.enqueue(
      UploadTask(
        localPath: localPath,
        category: category,
        mimeType: _attachmentMimeType(item),
        fileSize: fileStat.length,
      ),
    );
    final uploaded = await _awaitUploadCompletion(uploadManager, queued);
    final assetId = uploaded.assetId?.trim() ?? '';
    if (uploaded.status == UploadStatus.failed || assetId.isEmpty) {
      await _showAttachmentFailure(
        title: ChatText.chatAttachmentUploadFailed,
        message: ChatText.attachmentUploadIncomplete,
      );
      return;
    }
    final messageType = _attachmentMessageType(item);
    final media = ChatMessageMediaViewData(
      assetId: assetId,
      // 乐观气泡继续显示本地源；Message 命令只提交 assetId，远端 ACK/
      // sync projection 才携带 ready MediaAsset 的 canonical delivery URL。
      deliveryUrl: localPath,
      mediaType: messageType,
      fileName: item.name,
      mimeType: _attachmentMimeType(item),
      fileSizeBytes: uploaded.fileSize,
      thumbnailUrl: messageType == 'image' || messageType == 'video'
          ? localPath
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
        .read(chatVoiceSendControllerProvider(widget.conversationId))
        .sendVoice(result);
    if (!mounted) return;
    final sendState = ref.read(
      chatVoiceSendStateProvider(widget.conversationId),
    );
    if (sendState.status == VoiceSendStatus.failed &&
        (sendState.error ?? '').isNotEmpty) {
      await ref
          .read(chatSendOutboxControlProvider)
          .enqueueVoice(
            conversationId: widget.conversationId,
            voice: QueuedChatVoice(
              filePath: result.filePath,
              durationMs: result.durationMs,
              fileSize: result.fileSize,
              waveform: result.waveform,
            ),
          );
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
}
