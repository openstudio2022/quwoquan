import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:share_plus/share_plus.dart';
import 'package:quwoquan_app/assistant/transcript/citation/assistant_citation.dart';
import 'package:quwoquan_app/assistant/transcript/row/assistant_transcript_timeline_row.dart';
import 'package:quwoquan_app/components/conversation/conversation_timeline.dart';
import 'package:quwoquan_app/components/input/customizable_chat_input_bar.dart';
import 'package:quwoquan_app/core/constants/design_semantic_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/assistant/pages/assistant_reference_webview_page.dart';
import 'package:quwoquan_app/ui/assistant/providers/personal_assistant_stream_controller.dart';
import 'package:quwoquan_app/ui/assistant/widgets/message/assistant_message_bubble.dart';
import 'package:quwoquan_app/ui/chat/widgets/message/streaming_scroll_fab.dart';

class PersonalAssistantConversationPage extends ConsumerStatefulWidget {
  const PersonalAssistantConversationPage({
    super.key,
    this.embedded = false,
    this.onBack,
  });

  final bool embedded;
  final VoidCallback? onBack;

  @override
  ConsumerState<PersonalAssistantConversationPage> createState() =>
      _PersonalAssistantConversationPageState();
}

class _PersonalAssistantConversationPageState
    extends ConsumerState<PersonalAssistantConversationPage> {
  final TextEditingController _controller = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  final FocusNode _inputFocusNode = FocusNode();
  bool _userScrolledAway = false;
  bool _showScrollFab = false;

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_onScrollChanged);
  }

  @override
  void dispose() {
    _scrollController.removeListener(_onScrollChanged);
    _scrollController.dispose();
    _controller.dispose();
    _inputFocusNode.dispose();
    super.dispose();
  }

  void _onScrollChanged() {
    if (!_scrollController.hasClients) {
      return;
    }
    final maxScroll = _scrollController.position.maxScrollExtent;
    final currentScroll = _scrollController.offset;
    final isNearBottom = maxScroll - currentScroll < 80;
    final state = ref.read(personalAssistantStreamControllerProvider);
    if (state.running) {
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

  Future<void> _sendText(String text) async {
    final trimmed = text.trim();
    if (trimmed.isEmpty) {
      return;
    }
    _inputFocusNode.unfocus();
    _controller.clear();
    await ref
        .read(personalAssistantStreamControllerProvider.notifier)
        .send(trimmed);
  }

  Future<void> _submitChatInput(ChatInputSubmitPayload payload) async {
    var text = payload.text.trim();
    if (payload.isVoiceMessage && text.isEmpty) {
      text = '语音消息（${payload.voiceDuration.inSeconds}s）';
    }
    await _sendText(text);
  }

  Future<void> _openReference(AssistantCitation citation) async {
    final url = citation.url.trim();
    if (url.isEmpty) return;
    final uri = Uri.tryParse(url);
    if (uri == null || !(uri.isScheme('https') || uri.isScheme('http'))) {
      await Clipboard.setData(ClipboardData(text: url));
      return;
    }
    await Navigator.of(context).push(
      CupertinoPageRoute<void>(
        builder: (_) => AssistantReferenceWebViewPage(
          initialUrl: url,
          title: citation.title,
          source: citation.source,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final content = _PersonalAssistantConversationBody(
      controller: _controller,
      scrollController: _scrollController,
      focusNode: _inputFocusNode,
      onSend: _submitChatInput,
      showScrollFab: _showScrollFab,
      onScrollToBottom: () {
        if (!_scrollController.hasClients) {
          return;
        }
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
        setState(() => _userScrolledAway = false);
      },
      onReferenceTap: _openReference,
    );
    if (widget.embedded) {
      return content;
    }
    return CupertinoPageScaffold(
      navigationBar: CupertinoNavigationBar(
        middle: const Text(UITextConstants.assistantEntryFindPersonal),
        leading: widget.onBack == null
            ? null
            : CupertinoButton(
                padding: EdgeInsets.zero,
                onPressed: widget.onBack,
                child: const Icon(CupertinoIcons.back),
              ),
      ),
      child: SafeArea(child: content),
    );
  }
}

class _PersonalAssistantConversationBody extends ConsumerWidget {
  const _PersonalAssistantConversationBody({
    required this.controller,
    required this.scrollController,
    required this.focusNode,
    required this.onSend,
    required this.showScrollFab,
    required this.onScrollToBottom,
    required this.onReferenceTap,
  });

  final TextEditingController controller;
  final ScrollController scrollController;
  final FocusNode focusNode;
  final Future<void> Function(ChatInputSubmitPayload payload) onSend;
  final bool showScrollFab;
  final VoidCallback onScrollToBottom;
  final Future<void> Function(AssistantCitation citation) onReferenceTap;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isDark = ref.watch(isDarkProvider);
    final state = ref.watch(personalAssistantStreamControllerProvider);
    final background = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );
    final foreground = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final chatListBg = isDark ? background : AppColors.chatBackground;
    final bubbleSelf = AppColors.chatBubbleOutgoing;
    final bubbleOther = AppColors.chatBubbleIncoming;
    final timelinePadding = EdgeInsets.symmetric(
      horizontal:
          AppSpacing.semantic[DesignSemanticConstants
              .container]?[DesignSemanticConstants.sm] ??
          AppSpacing.containerSm,
      vertical: AppSpacing.md,
    );
    return ColoredBox(
      color: background,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Expanded(
            child: ConversationTimeline(
              controller: scrollController,
              backgroundColor: chatListBg,
              padding: timelinePadding,
              itemCount: state.transcript.length,
              overlays: <Widget>[
                if (showScrollFab)
                  Positioned(
                    right: AppSpacing.md,
                    bottom: AppSpacing.md,
                    child: StreamingScrollFab(onTap: onScrollToBottom),
                  ),
              ],
              itemBuilder: (context, index) {
                final row = state.transcript[index];
                final isUserRow = row is UserTranscriptTimelineRow;
                final isAssistantMessage =
                    row is AssistantAnswerTranscriptRow ||
                    row is ErrorTranscriptTimelineRow;
                return AssistantMessageBubble(
                  transcriptRow: row,
                  isRight: isUserRow,
                  bubbleColor: isUserRow ? bubbleSelf : bubbleOther,
                  textColor: isUserRow ? AppColors.white : foreground,
                  isSelectionMode: false,
                  isSelected: false,
                  onLongPressStart: (_) {},
                  hideAvatarAndName: true,
                  useFullWidth: true,
                  renderSelfTextWithoutBubble: true,
                  answerGateOpen:
                      !state.running ||
                      index != state.transcript.length - 1 ||
                      !isAssistantMessage ||
                      state.answerGateOpen,
                  isAssistantRunning:
                      state.running &&
                      index == state.transcript.length - 1 &&
                      isAssistantMessage,
                  expandProcessByDefault:
                      isAssistantMessage &&
                      index == state.transcript.length - 1,
                  runningStatusLabel:
                      state.running &&
                          index == state.transcript.length - 1 &&
                          isAssistantMessage
                      ? UITextConstants.assistantPhaseUnderstanding
                      : null,
                  showFeedbackActions:
                      isAssistantMessage &&
                      !state.running &&
                      index == state.transcript.length - 1,
                  feedbackStatus: state.feedbackMessage,
                  onFeedbackHelpful: isAssistantMessage
                      ? () => ref
                            .read(
                              personalAssistantStreamControllerProvider
                                  .notifier,
                            )
                            .submitFeedback('useful')
                      : null,
                  onFeedbackUnhelpful: isAssistantMessage
                      ? () => ref
                            .read(
                              personalAssistantStreamControllerProvider
                                  .notifier,
                            )
                            .submitFeedback('irrelevant')
                      : null,
                  onCopyAnswer: isAssistantMessage
                      ? () {
                          final text = _assistantRowText(row);
                          if (text.isNotEmpty) {
                            Clipboard.setData(ClipboardData(text: text));
                            ref
                                .read(
                                  personalAssistantStreamControllerProvider
                                      .notifier,
                                )
                                .submitFeedback('copied');
                          }
                        }
                      : null,
                  onReferenceTap: isAssistantMessage ? onReferenceTap : null,
                  onShareAnswer: isAssistantMessage
                      ? () {
                          final text = _assistantRowText(row);
                          if (text.isNotEmpty) {
                            SharePlus.instance.share(ShareParams(text: text));
                          }
                        }
                      : null,
                );
              },
            ),
          ),
          ColoredBox(
            color: isDark ? background : AppColors.chatToolbarBackground,
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
                child: CustomizableChatInputBar(
                  controller: controller,
                  focusNode: focusNode,
                  textFieldKey: TestKeys.assistantChatInputField,
                  hintText: UITextConstants.assistantAskPlaceholder,
                  maxTextLength: 5000,
                  maxVisibleLines: 5,
                  onSend: state.running ? (_) async {} : onSend,
                  sendButtonKey: TestKeys.assistantSendButton,
                  showEmojiButton: true,
                  extraPanelItems: const <ChatInputExtraPanelItem>[],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

String _assistantRowText(AssistantTranscriptTimelineRow row) {
  return switch (row) {
    AssistantAnswerTranscriptRow r =>
      (r.content.trim().isNotEmpty
          ? r.content.trim()
          : r.persisted.displayMarkdown.trim()),
    ErrorTranscriptTimelineRow r => r.content.trim(),
    UserTranscriptTimelineRow r => r.content.trim(),
  };
}
