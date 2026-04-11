import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:share_plus/share_plus.dart';
import 'package:speech_to_text/speech_to_text.dart' as stt;
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/navigation/page_access_internal_routes.dart';
import 'package:quwoquan_app/assistant/application/assistant_providers.dart';
import 'package:quwoquan_app/assistant/application/transcript/assistant_feedback_target.dart';
import 'package:quwoquan_app/assistant/transcript/citation/assistant_citation.dart';
import 'package:quwoquan_app/assistant/transcript/persisted_timeline/persisted_timeline_turn_codec.dart';
import 'package:quwoquan_app/assistant/transcript/row/assistant_transcript_timeline_row.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/components/conversation/conversation_page_scaffold.dart';
import 'package:quwoquan_app/components/conversation/conversation_timeline.dart';
import 'package:quwoquan_app/components/conversation/cupertino_conversation_sheet.dart';
import 'package:quwoquan_app/components/conversation/message_action_menu_overlay.dart';
import 'package:quwoquan_app/components/input/customizable_chat_input_bar.dart';
import 'package:quwoquan_app/core/constants/app_concept_constants.dart';
import 'package:quwoquan_app/core/constants/design_semantic_constants.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/widgets/app_action_sheet.dart';
import 'package:quwoquan_app/core/models/assistant_open_context.dart';
import 'package:quwoquan_app/core/models/user_profile_route_extra.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/ui/assistant/pages/assistant_chat_settings_page.dart';
import 'package:quwoquan_app/ui/assistant/pages/assistant_dev_replay_page.dart';
import 'package:quwoquan_app/ui/assistant/pages/assistant_reference_webview_page.dart';
import 'package:quwoquan_app/ui/assistant/providers/assistant_conversation_controller.dart';
import 'package:quwoquan_app/ui/assistant/widgets/assistant_half_sheet.dart';
import 'package:quwoquan_app/ui/assistant/models/assistant_ui_usage_stats_view_data.dart';
import 'package:quwoquan_app/ui/assistant/widgets/message/assistant_journey_view_model.dart';
import 'package:quwoquan_app/ui/assistant/widgets/message/assistant_message_bubble.dart';
import 'package:quwoquan_app/ui/assistant/widgets/message/assistant_turn_message_resolver.dart';
import 'package:quwoquan_app/ui/assistant/widgets/message/regenerate_options_popup.dart';
import 'package:quwoquan_app/ui/chat/widgets/message/streaming_scroll_fab.dart';

String _formatAssistantChatTime(String? raw) {
  if (raw == null || raw.isEmpty) return '';
  return raw;
}

class AssistantConversationPage extends ConsumerStatefulWidget {
  const AssistantConversationPage({
    super.key,
    required this.onBack,
    this.assistantOpenContext,
    this.embedded = false,
  });

  final VoidCallback onBack;
  final AssistantOpenContext? assistantOpenContext;
  final bool embedded;

  @override
  ConsumerState<AssistantConversationPage> createState() =>
      _AssistantConversationPageState();
}

class _AssistantConversationPageState
    extends ConsumerState<AssistantConversationPage> {
  final TextEditingController _inputController = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  final FocusNode _inputFocusNode = FocusNode();
  final ImagePicker _imagePicker = ImagePicker();
  final stt.SpeechToText _speechToText = stt.SpeechToText();

  late final AssistantConversationController _controller;

  AssistantTranscriptTimelineRow? _actionMenuRow;
  Offset? _actionMenuPosition;
  bool _isSelectionMode = false;
  final Set<String> _selectedIds = <String>{};
  double _lastViewportWidth = 390;
  bool _userScrolledAway = false;
  bool _showScrollFab = false;
  bool _speechReady = false;
  String _lastAsrText = '';

  @override
  void initState() {
    super.initState();
    _controller = AssistantConversationController(
      ref: ref,
      openContext: widget.assistantOpenContext,
    )..addListener(_handleControllerChanged);
    _scrollController.addListener(_onScrollChanged);
    _inputController.addListener(_onInputChanged);
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      await _controller.initialize();
      if (!mounted) {
        return;
      }
      final autoSendQuery =
          widget.assistantOpenContext?.hints['autoSendQuery']
              ?.toString()
              .trim() ??
          '';
      if (autoSendQuery.isNotEmpty) {
        await _sendMessage(draftText: autoSendQuery);
      }
    });
  }

  @override
  void dispose() {
    _controller.removeListener(_handleControllerChanged);
    _controller.dispose();
    _inputController.removeListener(_onInputChanged);
    _inputController.dispose();
    _scrollController.dispose();
    _inputFocusNode.dispose();
    super.dispose();
  }

  void _handleControllerChanged() {
    if (!mounted) return;
    setState(() {});
    if (_userScrolledAway) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !_scrollController.hasClients) return;
      final maxScroll = _scrollController.position.maxScrollExtent;
      final currentScroll = _scrollController.offset;
      if (maxScroll - currentScroll > 80) {
        _scrollController.animateTo(
          maxScroll,
          duration: const Duration(milliseconds: 150),
          curve: Curves.easeOut,
        );
      }
    });
  }

  void _onInputChanged() {
    if (mounted) setState(() {});
  }

  Future<void> _loadOlderAssistantHistory() async {
    if (_controller.assistantLoadingOlderHistory ||
        _controller.assistantHiddenHistory.isEmpty) {
      return;
    }
    final previousOffset = _scrollController.hasClients
        ? _scrollController.offset
        : 0.0;
    final previousMaxExtent = _scrollController.hasClients
        ? _scrollController.position.maxScrollExtent
        : 0.0;
    await _controller.loadOlderHistory();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !_scrollController.hasClients) return;
      final nextMaxExtent = _scrollController.position.maxScrollExtent;
      final delta = nextMaxExtent - previousMaxExtent;
      _scrollController.jumpTo(previousOffset + delta);
    });
  }

  void _onScrollChanged() {
    if (!_scrollController.hasClients) return;
    final maxScroll = _scrollController.position.maxScrollExtent;
    final currentScroll = _scrollController.offset;
    final isNearBottom = maxScroll - currentScroll < 80;

    if (_controller.assistantHiddenHistory.isNotEmpty &&
        !_controller.assistantResponding &&
        !_controller.assistantLoadingOlderHistory &&
        currentScroll <= AppSpacing.sm) {
      _loadOlderAssistantHistory();
    }

    if (_controller.assistantResponding) {
      if (!isNearBottom && !_userScrolledAway) {
        setState(() {
          _userScrolledAway = true;
          _showScrollFab = true;
        });
      } else if (isNearBottom && _userScrolledAway) {
        setState(() {
          _userScrolledAway = false;
          _showScrollFab = false;
        });
      }
    } else if (_showScrollFab) {
      setState(() => _showScrollFab = false);
    }
  }

  Future<List<ChatInputAttachment>> _pickChatImages(int remaining) async {
    final picked = await _imagePicker.pickMultiImage(
      imageQuality: 85,
      limit: remaining,
    );
    return picked
        .map<ChatInputAttachment>(
          (item) => ChatInputAttachment(
            id: item.path,
            type: ChatInputAttachmentType.image,
            name: item.name,
            subtitle: File(item.path).existsSync()
                ? _formatFileSize(File(item.path).lengthSync())
                : null,
            thumbnailProvider: FileImage(File(item.path)),
          ),
        )
        .toList(growable: false);
  }

  Future<ChatInputAttachment?> _captureChatPhoto() async {
    final captured = await _imagePicker.pickImage(
      source: ImageSource.camera,
      imageQuality: 85,
    );
    if (captured == null) return null;
    return ChatInputAttachment(
      id: captured.path,
      type: ChatInputAttachmentType.image,
      name: captured.name,
      subtitle: File(captured.path).existsSync()
          ? _formatFileSize(File(captured.path).lengthSync())
          : null,
      thumbnailProvider: FileImage(File(captured.path)),
    );
  }

  Future<List<ChatInputAttachment>> _pickChatFiles(int remaining) async {
    final result = await FilePicker.pickFiles(
      allowMultiple: remaining > 1,
      withData: false,
    );
    final files = result?.files ?? const <PlatformFile>[];
    return files
        .take(remaining)
        .map<ChatInputAttachment>(
          (file) => ChatInputAttachment(
            id: file.path ?? file.name,
            type: ChatInputAttachmentType.file,
            name: file.name,
            subtitle: _formatFileSize(file.size),
          ),
        )
        .toList(growable: false);
  }

  String _formatFileSize(int bytes) {
    if (bytes <= 0) return '0 B';
    const units = <String>['B', 'KB', 'MB', 'GB'];
    var value = bytes.toDouble();
    var unitIndex = 0;
    while (value >= 1024 && unitIndex < units.length - 1) {
      value /= 1024;
      unitIndex += 1;
    }
    final decimals = value >= 10 || unitIndex == 0 ? 0 : 1;
    return '${value.toStringAsFixed(decimals)} ${units[unitIndex]}';
  }

  Future<bool> _ensureSpeechReady() async {
    if (_speechReady) return true;
    _speechReady = await _speechToText.initialize();
    return _speechReady;
  }

  Future<bool> _requestMicPermissionForChat() async {
    final status = await Permission.microphone.request();
    return status.isGranted;
  }

  Future<void> _startVoiceRecordForChat() async {
    final granted = await _requestMicPermissionForChat();
    if (!granted) return;
    await _ensureSpeechReady();
    if (!_speechReady) return;
    _lastAsrText = '';
    await _speechToText.listen(
      onResult: (result) {
        _lastAsrText = result.recognizedWords.trim();
      },
      listenOptions: stt.SpeechListenOptions(
        cancelOnError: true,
        listenMode: stt.ListenMode.dictation,
      ),
      localeId: 'zh_CN',
    );
  }

  Future<void> _stopVoiceRecordForChat(Duration duration) async {
    if (_speechToText.isListening) {
      await _speechToText.stop();
    }
  }

  Future<String?> _voiceAsrForChat(Duration duration) async {
    await Future<void>.delayed(const Duration(milliseconds: 180));
    final recognized = _lastAsrText.trim();
    return recognized.isEmpty ? null : recognized;
  }

  Future<void> _submitChatInput(ChatInputSubmitPayload payload) async {
    if (payload.attachments.isNotEmpty) {
      _controller.appendOutgoingAttachments(payload.attachments);
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
    if (draftText == null) {
      _inputController.clear();
    }
    _userScrolledAway = false;
    _showScrollFab = false;
    await _controller.sendMessage(
      text: text,
      viewportWidth: _lastViewportWidth,
    );
  }

  Future<void> _openAssistantSettingsPage() async {
    await Navigator.of(context).push(
      CupertinoPageRoute<void>(
        builder: (_) => AssistantChatSettingsPage(
          currentSessionId: _controller.effectiveAssistantSessionId,
          currentTopicTitle: _controller.assistantTopicTitle,
          currentBackend: _controller.assistantBackend,
          onOpenTrace: _openAssistantDevReplayPage,
          onSessionSelected: _controller.switchSession,
          onBackendSelected: _controller.selectBackend,
        ),
      ),
    );
    if (!mounted) return;
    await _controller.syncSessionInfo();
  }

  AssistantJourneyViewModel _journeyViewModelFromRow(
    AssistantTranscriptTimelineRow row, {
    bool isRunning = false,
  }) {
    final usageMap = switch (row) {
      AssistantAnswerTranscriptRow r => r.uiUsageStats,
      _ => assistantUiUsageStatsMapFromMessageField(
          assistantTranscriptRowToProtocolMap(row)['uiUsageStats'],
        ),
    };
    final elapsedMs = switch (row) {
      AssistantAnswerTranscriptRow r => r.persisted.assistantElapsedMs,
      _ => 0,
    };
    return _controller.buildJourneyViewModel(
      journey: resolveAssistantJourneyFromTranscriptRow(row),
      processTimeline: resolveAssistantProcessTimelineFromTranscriptRow(row),
      isRunning: isRunning,
      displayState: resolvePersistedAssistantDisplayStateFromTranscriptRow(row),
      understandingSnapshot:
          resolveAssistantUnderstandingSnapshotFromTranscriptRow(row),
      retrievalProcessing:
          resolveAssistantRetrievalProcessingFromTranscriptRow(row),
      answerProcessing: resolveAssistantAnswerProcessingFromTranscriptRow(row),
      usageStats: AssistantUiUsageStatsViewData.fromProtocolMap(usageMap),
      elapsedMs: elapsedMs,
    );
  }

  Future<void> _submitAssistantFeedback({
    required AssistantFeedbackTarget target,
    required String explicitThumb,
    required List<String> reasonCodes,
    String correctionText = '',
  }) async {
    await _controller.submitFeedback(
      target: target,
      explicitThumb: explicitThumb,
      reasonCodes: reasonCodes,
      correctionText: correctionText,
    );
    if (!mounted) return;
    AppToast.show(context, UITextConstants.assistantFeedbackSubmitted);
  }

  void _showAssistantToast(String message) {
    if (!mounted) return;
    AppToast.show(context, message);
  }

  Future<void> _showAssistantNegativeFeedbackSheet(
    AssistantAnswerTranscriptRow row,
  ) async {
    final reasons = <MapEntry<String, String>>[
      MapEntry('off_topic', UITextConstants.assistantFeedbackReasonOffTopic),
      MapEntry(
        'insufficient',
        UITextConstants.assistantFeedbackReasonInsufficient,
      ),
      MapEntry('incorrect', UITextConstants.assistantFeedbackReasonIncorrect),
      MapEntry('style', UITextConstants.assistantFeedbackReasonStyle),
      MapEntry('privacy', UITextConstants.assistantFeedbackReasonPrivacy),
    ];
    final selected = <String>{};
    final submitted = await showCupertinoModalPopup<bool>(
      context: context,
      builder: (popupContext) {
        return StatefulBuilder(
          builder: (sheetContext, setSheetState) {
            final labelColor = CupertinoDynamicColor.resolve(
              CupertinoColors.label,
              sheetContext,
            );
            final secondaryLabel = CupertinoDynamicColor.resolve(
              CupertinoColors.secondaryLabel,
              sheetContext,
            );
            final separator = CupertinoDynamicColor.resolve(
              CupertinoColors.separator,
              sheetContext,
            );
            final tagBackground = CupertinoDynamicColor.resolve(
              CupertinoColors.tertiarySystemGroupedBackground,
              sheetContext,
            );
            return CupertinoConversationSheet(
              child: Padding(
                padding: EdgeInsets.all(
                  AppSpacing.semantic[DesignSemanticConstants
                          .container]?[DesignSemanticConstants.md] ??
                      AppSpacing.containerMd,
                ),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      UITextConstants.assistantFeedbackReasonTitle,
                      style: TextStyle(
                        fontSize: AppTypography.base,
                        fontWeight: FontWeight.w600,
                        color: labelColor,
                      ),
                    ),
                    SizedBox(height: AppSpacing.xs),
                    Text(
                      '可多选，用于持续改进回答质量。',
                      style: TextStyle(
                        fontSize: AppTypography.sm,
                        color: secondaryLabel,
                      ),
                    ),
                    SizedBox(height: AppSpacing.sm),
                    Flexible(
                      child: SingleChildScrollView(
                        child: Wrap(
                          spacing: AppSpacing.xs,
                          runSpacing: AppSpacing.xs,
                          children: reasons
                              .map((reason) {
                                final isSelected = selected.contains(
                                  reason.key,
                                );
                                return CupertinoButton(
                                  padding: EdgeInsets.zero,
                                  minimumSize: Size.square(
                                    AppSpacing.minInteractiveSize,
                                  ),
                                  onPressed: () {
                                    setSheetState(() {
                                      if (isSelected) {
                                        selected.remove(reason.key);
                                      } else {
                                        selected.add(reason.key);
                                      }
                                    });
                                  },
                                  child: AnimatedContainer(
                                    duration: const Duration(milliseconds: 160),
                                    padding: EdgeInsets.symmetric(
                                      horizontal: AppSpacing.md,
                                      vertical: AppSpacing.sm,
                                    ),
                                    decoration: BoxDecoration(
                                      color: isSelected
                                          ? AppColors.primaryColor.withValues(
                                              alpha: 0.12,
                                            )
                                          : tagBackground,
                                      borderRadius: BorderRadius.circular(
                                        AppSpacing.fullBorderRadius,
                                      ),
                                      border: Border.all(
                                        color: isSelected
                                            ? AppColors.primaryColor
                                            : separator.withValues(alpha: 0.4),
                                      ),
                                    ),
                                    child: Text(
                                      reason.value,
                                      style: TextStyle(
                                        fontSize: AppTypography.sm,
                                        fontWeight: FontWeight.w500,
                                        color: isSelected
                                            ? AppColors.primaryColor
                                            : labelColor,
                                      ),
                                    ),
                                  ),
                                );
                              })
                              .toList(growable: false),
                        ),
                      ),
                    ),
                    SizedBox(height: AppSpacing.md),
                    Row(
                      children: [
                        Expanded(
                          child: CupertinoButton(
                            padding: EdgeInsets.symmetric(
                              vertical: AppSpacing.sm,
                            ),
                            color: tagBackground,
                            borderRadius: BorderRadius.circular(
                              AppSpacing.fullBorderRadius,
                            ),
                            onPressed: () => Navigator.of(sheetContext).pop(),
                            child: const Text(UITextConstants.cancel),
                          ),
                        ),
                        SizedBox(width: AppSpacing.sm),
                        Expanded(
                          child: CupertinoButton.filled(
                            padding: EdgeInsets.symmetric(
                              vertical: AppSpacing.sm,
                            ),
                            borderRadius: BorderRadius.circular(
                              AppSpacing.fullBorderRadius,
                            ),
                            onPressed: () =>
                                Navigator.of(sheetContext).pop(true),
                            child: const Text(UITextConstants.confirm),
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            );
          },
        );
      },
    );
    if (submitted != true) return;
    await _submitAssistantFeedback(
      target: AssistantFeedbackTarget.fromAssistantRow(row),
      explicitThumb: 'down',
      reasonCodes: selected.toList(growable: false),
    );
  }

  Future<void> _showAssistantCorrectionSheet(
    AssistantAnswerTranscriptRow row,
  ) async {
    final controller = TextEditingController();
    final submitted = await showCupertinoModalPopup<bool>(
      context: context,
      builder: (popupContext) {
        final labelColor = CupertinoDynamicColor.resolve(
          CupertinoColors.label,
          popupContext,
        );
        final secondaryLabel = CupertinoDynamicColor.resolve(
          CupertinoColors.secondaryLabel,
          popupContext,
        );
        final fieldBackground = CupertinoDynamicColor.resolve(
          CupertinoColors.tertiarySystemGroupedBackground,
          popupContext,
        );
        return CupertinoConversationSheet(
          child: Padding(
            padding: EdgeInsets.all(
              AppSpacing.semantic[DesignSemanticConstants
                      .container]?[DesignSemanticConstants.md] ??
                  AppSpacing.containerMd,
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  UITextConstants.assistantCorrectionTitle,
                  style: TextStyle(
                    fontSize: AppTypography.base,
                    fontWeight: FontWeight.w600,
                    color: labelColor,
                  ),
                ),
                SizedBox(height: AppSpacing.xs),
                Text(
                  '补充你期望的正确答案或表达方式。',
                  style: TextStyle(
                    fontSize: AppTypography.sm,
                    color: secondaryLabel,
                  ),
                ),
                SizedBox(height: AppSpacing.sm),
                CupertinoTextField(
                  controller: controller,
                  minLines: 2,
                  maxLines: 4,
                  placeholder: UITextConstants.assistantCorrectionHint,
                  padding: EdgeInsets.symmetric(
                    horizontal: AppSpacing.md,
                    vertical: AppSpacing.md,
                  ),
                  decoration: BoxDecoration(
                    color: fieldBackground,
                    borderRadius: BorderRadius.circular(
                      AppSpacing.largeBorderRadius,
                    ),
                  ),
                ),
                SizedBox(height: AppSpacing.md),
                Row(
                  children: [
                    Expanded(
                      child: CupertinoButton(
                        padding: EdgeInsets.symmetric(vertical: AppSpacing.sm),
                        color: fieldBackground,
                        borderRadius: BorderRadius.circular(
                          AppSpacing.fullBorderRadius,
                        ),
                        onPressed: () => Navigator.of(popupContext).pop(),
                        child: const Text(UITextConstants.cancel),
                      ),
                    ),
                    SizedBox(width: AppSpacing.sm),
                    Expanded(
                      child: CupertinoButton.filled(
                        padding: EdgeInsets.symmetric(vertical: AppSpacing.sm),
                        borderRadius: BorderRadius.circular(
                          AppSpacing.fullBorderRadius,
                        ),
                        onPressed: () => Navigator.of(popupContext).pop(true),
                        child: const Text(UITextConstants.confirm),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        );
      },
    );
    if (submitted != true) return;
    final correction = controller.text.trim();
    if (correction.isEmpty) return;
    await _submitAssistantFeedback(
      target: AssistantFeedbackTarget.fromAssistantRow(row),
      explicitThumb: 'down',
      reasonCodes: const <String>['correction'],
      correctionText: correction,
    );
  }

  Future<void> _recordAssistantImplicitFeedback({
    required AssistantFeedbackTarget target,
    bool copiedAnswer = false,
    bool sharedAnswer = false,
    bool favoritedAnswer = false,
    bool regeneratedAnswer = false,
    bool styleAdjusted = false,
    bool modelSwitched = false,
    bool referenceOpened = false,
    List<String> userTags = const <String>[],
  }) async {
    await _controller.recordImplicitFeedback(
      target: target,
      copiedAnswer: copiedAnswer,
      sharedAnswer: sharedAnswer,
      favoritedAnswer: favoritedAnswer,
      regeneratedAnswer: regeneratedAnswer,
      styleAdjusted: styleAdjusted,
      modelSwitched: modelSwitched,
      referenceOpened: referenceOpened,
      userTags: userTags,
    );
  }

  Future<void> _sendAssistantRewrite({
    required AssistantAnswerTranscriptRow row,
    required RegenerateOption option,
  }) async {
    final originalQuery = row.anchor.sourceQuery.trim();
    if (originalQuery.isEmpty) return;
    final previousAnswer = <String>[
      resolvePersistedAssistantDisplayPlainTextFromTranscriptRow(row),
      resolvePersistedAssistantDisplayMarkdownFromTranscriptRow(row),
      row.content.trim(),
    ].firstWhere((item) => item.trim().isNotEmpty, orElse: () => '');
    final rewriteMode = switch (option) {
      RegenerateOption.regenerate => RewriteMode.regenerate,
      RegenerateOption.concise => RewriteMode.concise,
      RegenerateOption.detailed => RewriteMode.detailed,
      RegenerateOption.casual => RewriteMode.casual,
      RegenerateOption.deepThink => RewriteMode.deepThink,
    };
    await _recordAssistantImplicitFeedback(
      target: AssistantFeedbackTarget.fromAssistantRow(row),
      regeneratedAnswer: option == RegenerateOption.regenerate,
      styleAdjusted:
          option == RegenerateOption.concise ||
          option == RegenerateOption.detailed ||
          option == RegenerateOption.casual,
      userTags: <String>[option.name],
    );
    await _controller.sendRewrite(
      query: originalQuery,
      rewrite: RewriteInstruction(
        mode: rewriteMode,
        originalQuery: originalQuery,
        previousAnswer: previousAnswer,
      ),
    );
  }

  Future<void> _switchAssistantModelAndRegenerate(
    AssistantAnswerTranscriptRow row,
  ) async {
    final models = ref.read(assistantGatewayProvider).listAvailableModels();
    if (models.isEmpty) {
      if (!mounted) return;
      AppToast.show(context, UITextConstants.assistantModelUnavailable);
      return;
    }
    final currentModel = ref.read(assistantGatewayProvider).currentModel();
    final selected = await showAppActionSheet<String>(
      context,
      title: UITextConstants.assistantModelSelectorTitle,
      message: UITextConstants.assistantModelSelectorHint,
      sections: [
        AppActionSheetSection<String>(
          items: models
              .map(
                (modelRef) => AppActionSheetItem<String>(
                  value: modelRef,
                  label: modelRef,
                  isSelected: modelRef == currentModel,
                ),
              )
              .toList(growable: false),
        ),
      ],
    );
    if (selected == null || selected.trim().isEmpty) return;
    ref.read(assistantGatewayProvider).switchModel(selected);
    await _recordAssistantImplicitFeedback(
      target: AssistantFeedbackTarget.fromAssistantRow(row),
      modelSwitched: true,
      userTags: const <String>['model_switch'],
    );
    await _sendAssistantRewrite(row: row, option: RegenerateOption.regenerate);
  }

  Future<void> _onAssistantReferenceTap(
    AssistantAnswerTranscriptRow row,
    AssistantCitation citation,
  ) async {
    final url = citation.url.trim();
    if (url.isEmpty) return;
    final uri = Uri.tryParse(url);
    final allowOpen = uri != null && _controller.isReferenceHostAllowed(uri);
    if (!allowOpen) {
      await Clipboard.setData(ClipboardData(text: url));
      if (!mounted) return;
      AppToast.show(context, UITextConstants.assistantReferenceHostBlocked);
      await _recordAssistantImplicitFeedback(
        target: AssistantFeedbackTarget.fromAssistantRow(row),
        referenceOpened: true,
        userTags: const <String>['reference_copy'],
      );
      return;
    }
    try {
      await Navigator.of(context).push(
        CupertinoPageRoute<void>(
          settings: const RouteSettings(
            name: PageAccessInternalRoutes.assistantConversationReferenceWeb,
          ),
          builder: (_) => AssistantReferenceWebViewPage(
            initialUrl: url,
            title: citation.title,
            source: citation.source,
          ),
        ),
      );
      await _recordAssistantImplicitFeedback(
        target: AssistantFeedbackTarget.fromAssistantRow(row),
        referenceOpened: true,
        userTags: const <String>['reference_open'],
      );
    } catch (_) {
      await Clipboard.setData(ClipboardData(text: url));
      if (!mounted) return;
      AppToast.show(context, UITextConstants.assistantReferenceOpenFailed);
      await _recordAssistantImplicitFeedback(
        target: AssistantFeedbackTarget.fromAssistantRow(row),
        referenceOpened: true,
        userTags: const <String>['reference_copy'],
      );
    }
  }

  void _openAssistantDevReplayPage() {
    Navigator.of(context).push(
      CupertinoPageRoute<void>(
        settings: const RouteSettings(
          name: PageAccessInternalRoutes.assistantConversationDevReplay,
        ),
        builder: (_) => AssistantDevReplayPage(
          records: _controller.replayRecords
              .map((r) => Map<String, Object?>.from(r.toJson()))
              .toList(growable: false),
          loadScoreSnapshot: () async {
            final snap = await ref
                .read(assistantLearningServiceProvider)
                .latestScoreSnapshot();
            return Map<String, Object?>.from(snap);
          },
        ),
      ),
    );
  }

  void _onLongPressMessage(
    AssistantTranscriptTimelineRow row,
    Offset globalPosition,
  ) {
    setState(() {
      _actionMenuRow = row;
      _actionMenuPosition = globalPosition;
    });
  }

  String _rowPlainContent(AssistantTranscriptTimelineRow row) {
    return switch (row) {
      UserTranscriptTimelineRow r => r.content,
      AssistantAnswerTranscriptRow r => r.content,
      ErrorTranscriptTimelineRow r => r.content,
    };
  }

  String _rowTimestamp(AssistantTranscriptTimelineRow row) {
    return switch (row) {
      UserTranscriptTimelineRow r => r.timestamp,
      AssistantAnswerTranscriptRow r => r.timestamp,
      ErrorTranscriptTimelineRow r => r.timestamp,
    };
  }

  void _onMessageAction(String action) {
    final row = _actionMenuRow;
    if (row == null) return;
    switch (action) {
      case 'forward':
        _shareRows(<AssistantTranscriptTimelineRow>[row]);
        break;
      case 'select':
        setState(() {
          _isSelectionMode = true;
          _selectedIds.add(row.id);
        });
        break;
      case 'copy':
        final content = _rowPlainContent(row);
        if (content.isNotEmpty) {
          Clipboard.setData(ClipboardData(text: content));
          if (mounted) {
            AppToast.show(context, UITextConstants.copiedToClipboard);
          }
        }
        break;
      case 'recall':
      case 'delete':
        _controller.removeMessageById(row.id);
        break;
    }
    setState(() {
      _actionMenuRow = null;
      _actionMenuPosition = null;
    });
  }

  Future<void> _shareRows(List<AssistantTranscriptTimelineRow> rows) async {
    if (rows.isEmpty) return;
    final lines = rows
        .map((r) => _rowPlainContent(r).trim())
        .where((line) => line.isNotEmpty)
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
    _lastViewportWidth = MediaQuery.of(context).size.width;
    final isDark = ref.watch(isDarkProvider);
    final bgColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final bubbleSelf = AppColors.chatBubbleOutgoing;
    final bubbleOther = AppColors.chatBubbleIncoming;
    final borderColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.borderPrimary,
    );
    final chatListBg = isDark ? bgColor : AppColors.chatBackground;
    final displayRows = _controller.transcriptRows;
    final latestAssistantTextMessageId = displayRows.reversed
        .whereType<AssistantAnswerTranscriptRow>()
        .where(
          (r) =>
              r.type == 'text' &&
              r.senderId == AppConceptConstants.assistantSenderId,
        )
        .map((r) => r.id)
        .firstWhere((id) => id.isNotEmpty, orElse: () => '');
    final timelinePadding = EdgeInsets.symmetric(
      horizontal:
          AppSpacing.semantic[DesignSemanticConstants
              .container]?[DesignSemanticConstants.sm] ??
          AppSpacing.containerSm,
      vertical: AppSpacing.md,
    );
    final timelineOverlays = <Widget>[
      if (_controller.showAssistantHistoryPeek ||
          _controller.assistantLoadingOlderHistory)
        Positioned(
          top: AppSpacing.sm,
          left: 0,
          right: 0,
          child: Center(
            child: GestureDetector(
              onTap: _controller.assistantLoadingOlderHistory
                  ? null
                  : _loadOlderAssistantHistory,
              child: AnimatedOpacity(
                opacity: 1,
                duration: const Duration(milliseconds: 180),
                child: Container(
                  padding: EdgeInsets.symmetric(
                    horizontal: AppSpacing.containerSm,
                    vertical: AppSpacing.xs,
                  ),
                  decoration: BoxDecoration(
                    color: isDark
                        ? bgColor.withValues(alpha: 0.92)
                        : AppColors.white.withValues(alpha: 0.94),
                    borderRadius: BorderRadius.circular(
                      AppSpacing.fullBorderRadius,
                    ),
                    border: Border.all(
                      color: borderColor.withValues(alpha: 0.18),
                    ),
                    boxShadow: [
                      BoxShadow(
                        color: AppColors.black.withValues(alpha: 0.04),
                        blurRadius: AppSpacing.sm,
                      ),
                    ],
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      if (_controller.assistantLoadingOlderHistory)
                        Padding(
                          padding: EdgeInsets.only(right: AppSpacing.xs),
                          child: const CupertinoActivityIndicator(),
                        )
                      else
                        Icon(
                          CupertinoIcons.chevron_up,
                          size: AppSpacing.iconSmall,
                          color: fgPrimary.withValues(alpha: 0.56),
                        ),
                      if (!_controller.assistantLoadingOlderHistory)
                        SizedBox(width: AppSpacing.xs / 2),
                      Text(
                        UITextConstants.assistantViewHistory,
                        style: TextStyle(
                          fontSize: AppTypography.sm,
                          color: fgPrimary.withValues(alpha: 0.72),
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      if (_showScrollFab)
        Positioned(
          right: AppSpacing.md,
          bottom: AppSpacing.md,
          child: StreamingScrollFab(
            onTap: () {
              _scrollController.animateTo(
                _scrollController.position.maxScrollExtent,
                duration: const Duration(milliseconds: 300),
                curve: Curves.easeOut,
              );
              setState(() => _userScrolledAway = false);
            },
          ),
        ),
    ];
    final actionMenuOverlay =
        _actionMenuRow != null && _actionMenuPosition != null
        ? ConversationMessageActionMenuOverlay(
            message: PersistedTimelineTurnCodec.encode(_actionMenuRow!),
            position: _actionMenuPosition!,
            onAction: _onMessageAction,
            onClose: () => setState(() {
              _actionMenuRow = null;
              _actionMenuPosition = null;
            }),
          )
        : null;

    final bodyContent = Column(
      children: [
        Expanded(
          child: ConversationTimeline(
            controller: _scrollController,
            backgroundColor: chatListBg,
            padding: timelinePadding,
            itemCount: displayRows.length,
            overlays: timelineOverlays,
            itemBuilder: (context, index) {
              final row = displayRows[index];
              final prevTime = index > 0
                  ? _rowTimestamp(displayRows[index - 1])
                  : null;
              final rowTs = _rowTimestamp(row);
              final showTime = index == 0 || rowTs != prevTime;
              final timeStr = _formatAssistantChatTime(rowTs);
              final isUserRow = row is UserTranscriptTimelineRow;
              final isAssistantAnswerRow = row is AssistantAnswerTranscriptRow;
              final isErrorRow = row is ErrorTranscriptTimelineRow;
              final isAssistantMessage = isAssistantAnswerRow || isErrorRow;
              final answerRow = isAssistantAnswerRow ? row : null;
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
                  AssistantMessageBubble(
                    transcriptRow: row,
                    isRight: isUserRow,
                    bubbleColor: isUserRow ? bubbleSelf : bubbleOther,
                    textColor: isUserRow ? AppColors.white : fgPrimary,
                    isSelectionMode: _isSelectionMode,
                    isSelected: _selectedIds.contains(row.id),
                    onLongPressStart: (details) =>
                        _onLongPressMessage(row, details.globalPosition),
                    onTap: _isSelectionMode
                        ? () => _toggleSelect(row.id)
                        : null,
                    hideAvatarAndName: true,
                    useFullWidth: true,
                    renderSelfTextWithoutBubble: true,
                    journeyViewModel:
                        index == displayRows.length - 1 &&
                            isAssistantMessage &&
                            _controller.assistantResponding
                        ? _controller.buildJourneyViewModel(
                            journey: _controller.currentJourney,
                            processTimeline: _controller.currentProcessTimeline,
                            isRunning: true,
                            displayState:
                                resolvePersistedAssistantDisplayStateFromTranscriptRow(
                              row,
                            ),
                            understandingSnapshot:
                                _controller.currentUnderstandingSnapshot,
                            retrievalProcessing:
                                _controller.currentRetrievalProcessing,
                            answerProcessing:
                                resolveAssistantAnswerProcessingFromTranscriptRow(
                              row,
                            ),
                            elapsedMs: _controller.currentJourneyElapsedMs,
                          )
                        : (isAssistantMessage
                              ? _journeyViewModelFromRow(row)
                              : null),
                    answerGateOpen:
                        !_controller.assistantResponding ||
                        index != displayRows.length - 1 ||
                        !isAssistantMessage ||
                        _controller.answerGateOpen,
                    isAssistantRunning:
                        _controller.assistantResponding &&
                        index == displayRows.length - 1 &&
                        isAssistantMessage,
                    expandProcessByDefault:
                        isAssistantMessage && index == displayRows.length - 1,
                    runningStatusLabel:
                        _controller.assistantResponding &&
                            index == displayRows.length - 1 &&
                            isAssistantMessage
                        ? (_controller.assistantPhaseLabel.isNotEmpty
                              ? _controller.assistantPhaseLabel
                              : UITextConstants.assistantPhaseUnderstanding)
                        : null,
                    showFeedbackActions:
                        answerRow != null &&
                        !_controller.assistantResponding &&
                        !_isSelectionMode &&
                        answerRow.type == 'text' &&
                        answerRow.id == latestAssistantTextMessageId,
                    feedbackStatus:
                        _controller.feedbackStatusByMessageId[row.id] ?? '',
                    onFeedbackHelpful: answerRow != null
                        ? () => _submitAssistantFeedback(
                            target: AssistantFeedbackTarget.fromAssistantRow(
                              answerRow,
                            ),
                            explicitThumb: 'up',
                            reasonCodes: const <String>[],
                          )
                        : null,
                    onFeedbackUnhelpful: answerRow != null
                        ? () => _showAssistantNegativeFeedbackSheet(answerRow)
                        : null,
                    onFeedbackCorrect: answerRow != null
                        ? () => _showAssistantCorrectionSheet(answerRow)
                        : null,
                    onCopyAnswer: answerRow != null
                        ? () async {
                            final content = answerRow.content;
                            if (content.isEmpty) return;
                            await Clipboard.setData(
                              ClipboardData(text: content),
                            );
                            _showAssistantToast(
                              UITextConstants.copiedToClipboard,
                            );
                            await _recordAssistantImplicitFeedback(
                              target: AssistantFeedbackTarget.fromAssistantRow(
                                answerRow,
                              ),
                              copiedAnswer: true,
                            );
                          }
                        : null,
                    onShareAnswer: answerRow != null
                        ? () async {
                            final content = answerRow.content;
                            if (content.isNotEmpty) {
                              await SharePlus.instance.share(
                                ShareParams(text: content),
                              );
                            }
                            await _recordAssistantImplicitFeedback(
                              target: AssistantFeedbackTarget.fromAssistantRow(
                                answerRow,
                              ),
                              sharedAnswer: true,
                            );
                          }
                        : null,
                    onFavoriteAnswer: answerRow != null
                        ? () async {
                            await _recordAssistantImplicitFeedback(
                              target: AssistantFeedbackTarget.fromAssistantRow(
                                answerRow,
                              ),
                              favoritedAnswer: true,
                            );
                            _showAssistantToast(
                              UITextConstants.assistantBookmarked,
                            );
                          }
                        : null,
                    onRegenerateAnswer: answerRow != null
                        ? () => _sendAssistantRewrite(
                            row: answerRow,
                            option: RegenerateOption.regenerate,
                          )
                        : null,
                    onRegenerateOptionSelected: answerRow != null
                        ? (option) => _sendAssistantRewrite(
                            row: answerRow,
                            option: option,
                          )
                        : null,
                    onBriefAnswer: answerRow != null
                        ? () => _sendAssistantRewrite(
                            row: answerRow,
                            option: RegenerateOption.concise,
                          )
                        : null,
                    onDetailedAnswer: answerRow != null
                        ? () => _sendAssistantRewrite(
                            row: answerRow,
                            option: RegenerateOption.detailed,
                          )
                        : null,
                    onSwitchModelAnswer: answerRow != null
                        ? () => _switchAssistantModelAndRegenerate(answerRow)
                        : null,
                    onActionHintTap: answerRow != null
                        ? (hint) async {
                            _inputController.text = hint;
                            await _sendMessage();
                          }
                        : null,
                    onReferenceTap: answerRow != null
                        ? (refItem) =>
                              _onAssistantReferenceTap(answerRow, refItem)
                        : null,
                    onAvatarTap: isAssistantMessage
                        ? () {
                            final target = VisitTarget.page('chat');
                            final service = ref.read(
                              visitRecorderServiceProvider,
                            );
                            final ctx = AssistantOpenContext(
                              source: AssistantSource.chat,
                              visitTarget: target,
                              experienceLevel: service.getExperience(target),
                            );
                            AssistantHalfSheet.show(context, ctx);
                          }
                        : () {
                            final senderId = switch (row) {
                              UserTranscriptTimelineRow r => r.senderId,
                              AssistantAnswerTranscriptRow r => r.senderId,
                              ErrorTranscriptTimelineRow r => r.senderId,
                            };
                            if (isUserRow) {
                              final currentUser = ref.read(userDataProvider);
                              final userId =
                                  currentUser?.username ?? currentUser?.id;
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
                    showAssistantAvatar: false,
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
                AppSpacing.sm,
                AppSpacing.semantic[DesignSemanticConstants
                        .container]?[DesignSemanticConstants.sm] ??
                    AppSpacing.containerSm,
                AppSpacing.sm,
              ),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  CustomizableChatInputBar(
                    controller: _inputController,
                    focusNode: _inputFocusNode,
                    textFieldKey: TestKeys.assistantChatInputField,
                    hintText: UITextConstants.assistantAskPlaceholder,
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
                    sendButtonKey: TestKeys.assistantSendButton,
                    showEmojiButton: true,
                    extraPanelItems: const <ChatInputExtraPanelItem>[],
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
                    : AppConceptConstants.assistantDisplayTitle,
                style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
              ),
              trailing: _isSelectionMode
                  ? CupertinoButton(
                      padding: EdgeInsets.zero,
                      onPressed: () async {
                        final selectedRows = _controller.transcriptRows
                            .where((item) => _selectedIds.contains(item.id))
                            .toList(growable: false);
                        await _shareRows(selectedRows);
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
                      icon: CupertinoIcons.gear,
                      onPressed: _openAssistantSettingsPage,
                    ),
            ),
      body: bodyContent,
      overlays: actionMenuOverlay == null
          ? const <Widget>[]
          : <Widget>[actionMenuOverlay],
    );
  }
}
