import 'dart:async';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' show Material, MaterialType;
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:share_plus/share_plus.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/page_access_internal_routes.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/page_access_log_util.dart';
import 'package:quwoquan_app/runtime/observability/app_trace_context_store.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/application/public/assistant_citation.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/application/public/citation_destination_resolver.dart';
import 'package:quwoquan_app/runtime/di/navigation/citation_destination_navigation_mapper.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/application/public/assistant_transcript_timeline_row.dart';
import 'package:quwoquan_app/design_system/chat/conversation_timeline.dart';
import 'package:quwoquan_app/runtime/di/chat_presentation_slots.dart';
import 'package:quwoquan_app/l10n/copy/assistant_text_constants.dart';
import 'package:quwoquan_app/design_system/semantics/design_semantic_constants.dart';
import 'package:quwoquan_app/design_system/semantics/navigation_semantic_constants.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/page_context/application/public/assistant_open_context.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/design_system/layout/app_scaffold.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/presentation/assistant_reference_webview_page.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/application/personal_assistant_stream_controller.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/presentation/assistant_session_empty_state.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/presentation/assistant_session_inline_error.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/presentation/assistant_history_sheet.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/presentation/assistant_message_bubble.dart';
import 'package:quwoquan_app/design_system/navigation/streaming_scroll_fab.dart';

class PersonalAssistantSessionPage extends ConsumerStatefulWidget {
  const PersonalAssistantSessionPage({
    super.key,
    this.embedded = false,
    this.onBack,
    this.assistantOpenContext,
  });

  final bool embedded;
  final VoidCallback? onBack;
  final AssistantOpenContext? assistantOpenContext;

  @override
  ConsumerState<PersonalAssistantSessionPage> createState() =>
      _PersonalAssistantSessionPageState();
}

class _PersonalAssistantSessionPageState
    extends ConsumerState<PersonalAssistantSessionPage> {
  final TextEditingController _controller = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  final FocusNode _inputFocusNode = FocusNode();
  bool _userScrolledAway = false;
  bool _showScrollFab = false;
  bool _initialQueryHandled = false;

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_onScrollChanged);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      // 页面曝光（R20）：GoRoute 无 name 不经 pageAccess observer，页面自身
      // 直调现行 pageAccess 通道（与 MainAppShell tab 埋点同源）。
      if (!widget.embedded) {
        unawaited(
          writeAppPageAccessOpen(
            location: AppRoutePaths.assistantPersonal,
            pageVisitId: AppTraceContextStore.instance.newPageVisitId(),
            visitRecorder: ref.read(visitRecorderServiceProvider),
            telemetryReporter: ref.read(appTelemetryReporterProvider),
          ),
        );
      }
      final requestedSessionId =
          widget.assistantOpenContext?.sessionId.trim() ?? '';
      final notifier = ref.read(
        personalAssistantStreamControllerProvider.notifier,
      );
      notifier.setOpenContext(widget.assistantOpenContext);
      unawaited(
        (requestedSessionId.isEmpty
                ? notifier.ensureHistoryInitialized()
                : notifier.switchSession(requestedSessionId))
            .then((_) => _sendInitialQueryIfNeeded()),
      );
    });
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

  Future<void> _submitChatInput(String text) async {
    final instruction = text.trim();
    if (instruction.isEmpty) {
      return;
    }
    final runState = ref.read(personalAssistantStreamControllerProvider);
    if (!runState.running) {
      await _sendText(instruction);
      return;
    }
    final accepted = await ref
        .read(personalAssistantStreamControllerProvider.notifier)
        .steerCurrentRun(instruction);
    if (!mounted || accepted) {
      return;
    }
    _controller.value = TextEditingValue(
      text: instruction,
      selection: TextSelection.collapsed(offset: instruction.length),
    );
    _inputFocusNode.requestFocus();
  }

  Future<void> _sendInitialQueryIfNeeded() async {
    if (!mounted || _initialQueryHandled) {
      return;
    }
    _initialQueryHandled = true;
    final query =
        widget.assistantOpenContext?.hints['autoSendQuery']
            ?.toString()
            .trim() ??
        '';
    if (query.isEmpty) {
      return;
    }
    await _sendText(query);
  }

  Future<void> _openReference(AssistantCitation citation) async {
    final destination = citation.resolvedDestination;
    switch (destination) {
      case InternalCitationDestination():
        final navigationTarget =
            CitationDestinationNavigationMapper.resolveInternal(destination);
        if (navigationTarget == null) {
          return;
        }
        ref
            .read(personalAssistantStreamControllerProvider.notifier)
            .reportReferenceOpened(external: false);
        context.push(navigationTarget.routePath);
      case ExternalCitationDestination():
        ref
            .read(personalAssistantStreamControllerProvider.notifier)
            .reportReferenceOpened(external: true);
        await Navigator.of(context).push(
          CupertinoPageRoute<void>(
            // 携带 metadata 登记的 internal location，pageAccess observer 据此
            // 记录 webview 页的进入/停留（assistant_reference_webview_modal）。
            settings: const RouteSettings(
              name: PageAccessInternalRoutes.assistantSessionReferenceWeb,
            ),
            builder: (_) => AssistantReferenceWebViewPage(
              initialUrl: destination.uri.toString(),
              title: citation.title,
              source: citation.source,
            ),
          ),
        );
      case null:
        // 未知对象、无 destination 和非 HTTPS URL 均不可打开，避免错误回退。
        return;
    }
  }

  @override
  Widget build(BuildContext context) {
    final content = _PersonalAssistantSessionBody(
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
      openContext: widget.assistantOpenContext,
    );
    if (widget.embedded) {
      return content;
    }
    return AppScaffold(
      backgroundColor: CupertinoColors.systemBackground.resolveFrom(context),
      navigationBar: AppNavigationBar(
        middle: const Text(AssistantText.assistantEntryFindPersonal),
        leading: widget.onBack == null
            ? null
            : AppNavigationBarIconButton(
                icon: CupertinoIcons.back,
                onPressed: widget.onBack,
              ),
        trailing: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            AppNavigationBarIconButton(
              key: TestKeys.assistantHistoryButton,
              icon: CupertinoIcons.clock,
              onPressed: _openHistorySheet,
            ),
            AppNavigationBarIconButton(
              icon: AppNavigationSemanticConstants.settingsActionIcon,
              onPressed: () => context.push(AppRoutePaths.assistantManagement),
            ),
          ],
        ),
      ),
      child: content,
    );
  }

  Future<void> _openHistorySheet() async {
    final selected = await showAssistantHistorySheet(context);
    if (!mounted || selected == null) {
      return;
    }
    final notifier = ref.read(
      personalAssistantStreamControllerProvider.notifier,
    );
    if (selected.isEmpty) {
      notifier.startNewSession();
      return;
    }
    await notifier.switchSession(selected);
  }
}

class _PersonalAssistantSessionBody extends ConsumerWidget {
  const _PersonalAssistantSessionBody({
    required this.controller,
    required this.scrollController,
    required this.focusNode,
    required this.onSend,
    required this.showScrollFab,
    required this.onScrollToBottom,
    required this.onReferenceTap,
    required this.openContext,
  });

  final TextEditingController controller;
  final ScrollController scrollController;
  final FocusNode focusNode;
  final Future<void> Function(String text) onSend;
  final bool showScrollFab;
  final VoidCallback onScrollToBottom;
  final Future<void> Function(AssistantCitation citation) onReferenceTap;
  final AssistantOpenContext? openContext;

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
    final hasRetryError =
        state.retryAvailable && state.errorMessage.trim().isNotEmpty;
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
            child: state.historyLoading && state.transcript.isEmpty
                ? AppRequestFeedback.section()
                : state.transcript.isEmpty && !hasRetryError
                ? AssistantSessionEmptyState(
                    openContext: openContext,
                    foreground: foreground,
                    onSuggestionSelected: (value) {
                      controller
                        ..text = value
                        ..selection = TextSelection.collapsed(
                          offset: value.length,
                        );
                      focusNode.requestFocus();
                    },
                  )
                : ConversationTimeline(
                    controller: scrollController,
                    backgroundColor: chatListBg,
                    padding: timelinePadding,
                    itemCount:
                        state.transcript.length + (hasRetryError ? 1 : 0),
                    overlays: <Widget>[
                      if (showScrollFab)
                        Positioned(
                          right: AppSpacing.md,
                          bottom: AppSpacing.md,
                          child: StreamingScrollFab(onTap: onScrollToBottom),
                        ),
                    ],
                    itemBuilder: (context, index) {
                      if (index == state.transcript.length) {
                        return AssistantSessionInlineError(
                          state: state,
                          onRetry: ref
                              .read(
                                personalAssistantStreamControllerProvider
                                    .notifier,
                              )
                              .retryLastFailedAction,
                          onOpenSettings: () =>
                              context.push(AppRoutePaths.assistantManagement),
                          onDismiss: ref
                              .read(
                                personalAssistantStreamControllerProvider
                                    .notifier,
                              )
                              .dismissError,
                        );
                      }
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
                            ? _assistantRunningStatusLabel(state.processSummary)
                            : null,
                        canHandlePresentationAction:
                            row is AssistantAnswerTranscriptRow
                            ? ref
                                  .read(
                                    personalAssistantStreamControllerProvider
                                        .notifier,
                                  )
                                  .canHandlePresentationAction
                            : null,
                        onPresentationAction:
                            row is AssistantAnswerTranscriptRow &&
                                row.anchor.runId.trim().isNotEmpty
                            ? (action) {
                                unawaited(
                                  ref
                                      .read(
                                        personalAssistantStreamControllerProvider
                                            .notifier,
                                      )
                                      .handlePresentationAction(
                                        runId: row.anchor.runId,
                                        action: action,
                                      ),
                                );
                              }
                            : null,
                        presentationMediaUrlResolver:
                            row is AssistantAnswerTranscriptRow
                            ? ref
                                  .read(
                                    personalAssistantStreamControllerProvider
                                        .notifier,
                                  )
                                  .resolvePresentationMedia
                            : null,
                        onPresentationFallback: isAssistantMessage
                            ? ref
                                  .read(
                                    personalAssistantStreamControllerProvider
                                        .notifier,
                                  )
                                  .recordPresentationFallback
                            : null,
                        showFeedbackActions:
                            isAssistantMessage &&
                            !state.running &&
                            index == state.transcript.length - 1,
                        feedbackStatus: state.feedbackType,
                        onRegenerateAnswer:
                            isAssistantMessage &&
                                !state.running &&
                                index == state.transcript.length - 1
                            ? () => ref
                                  .read(
                                    personalAssistantStreamControllerProvider
                                        .notifier,
                                  )
                                  .regenerateLastAnswer()
                            : null,
                        onRegenerateOptionSelected:
                            isAssistantMessage &&
                                !state.running &&
                                index == state.transcript.length - 1
                            ? (option) => ref
                                  .read(
                                    personalAssistantStreamControllerProvider
                                        .notifier,
                                  )
                                  .regenerateLastAnswer(option: option)
                            : null,
                        onFeedbackHelpful: isAssistantMessage
                            ? () {
                                unawaited(
                                  ref
                                      .read(
                                        personalAssistantStreamControllerProvider
                                            .notifier,
                                      )
                                      .submitFeedback('useful'),
                                );
                              }
                            : null,
                        onFeedbackUnhelpful: isAssistantMessage
                            ? () {
                                unawaited(
                                  ref
                                      .read(
                                        personalAssistantStreamControllerProvider
                                            .notifier,
                                      )
                                      .submitFeedback('irrelevant'),
                                );
                              }
                            : null,
                        onCopyAnswer: isAssistantMessage
                            ? () {
                                final text = _assistantRowText(row);
                                if (text.isNotEmpty) {
                                  Clipboard.setData(ClipboardData(text: text));
                                  unawaited(
                                    ref
                                        .read(
                                          personalAssistantStreamControllerProvider
                                              .notifier,
                                        )
                                        .submitFeedback('copied'),
                                  );
                                }
                              }
                            : null,
                        onReferenceTap: isAssistantMessage
                            ? onReferenceTap
                            : null,
                        onShareAnswer: isAssistantMessage
                            ? () {
                                final text = _assistantRowText(row);
                                if (text.isNotEmpty) {
                                  SharePlus.instance.share(
                                    ShareParams(text: text),
                                  );
                                }
                              }
                            : null,
                      );
                    },
                  ),
          ),
          if (state.running)
            Padding(
              padding: EdgeInsets.only(bottom: AppSpacing.intraGroupSm),
              child: Center(
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    _RunControlButton(
                      key: state.runStatus == 'paused'
                          ? TestKeys.assistantResumeRunButton
                          : TestKeys.assistantPauseRunButton,
                      icon: state.runStatus == 'paused'
                          ? CupertinoIcons.play_fill
                          : CupertinoIcons.pause_fill,
                      label: state.runStatus == 'paused'
                          ? AssistantText.assistantResumeRun
                          : AssistantText.assistantPauseRun,
                      isDark: isDark,
                      foreground: foreground,
                      onPressed: state.runStatus == 'paused'
                          ? ref
                                .read(
                                  personalAssistantStreamControllerProvider
                                      .notifier,
                                )
                                .resumeCurrentRun
                          : ref
                                .read(
                                  personalAssistantStreamControllerProvider
                                      .notifier,
                                )
                                .pauseCurrentRun,
                    ),
                    SizedBox(width: AppSpacing.xs),
                    _RunControlButton(
                      key: TestKeys.assistantStopGeneratingButton,
                      icon: CupertinoIcons.stop_fill,
                      label: AssistantText.assistantStopGenerating,
                      isDark: isDark,
                      foreground: foreground,
                      onPressed: ref
                          .read(
                            personalAssistantStreamControllerProvider.notifier,
                          )
                          .stopGeneration,
                    ),
                  ],
                ),
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
                  AppSpacing.chatInputToolbarVerticalPadding,
                  AppSpacing.semantic[DesignSemanticConstants
                          .container]?[DesignSemanticConstants.sm] ??
                      AppSpacing.containerSm,
                  AppSpacing.chatInputToolbarVerticalPadding,
                ),
                child: Material(
                  type: MaterialType.transparency,
                  child: ref.watch(assistantChatInputBuilderProvider)(
                    controller: controller,
                    focusNode: focusNode,
                    textFieldKey: TestKeys.assistantChatInputField,
                    hintText: state.running
                        ? AssistantText.assistantSteerPlaceholder
                        : AssistantText.assistantAskPlaceholder,
                    maxTextLength: 5000,
                    maxVisibleLines: 5,
                    onSend: onSend,
                    sendButtonKey: TestKeys.assistantSendButton,
                    showEmojiButton: true,
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _RunControlButton extends StatelessWidget {
  const _RunControlButton({
    super.key,
    required this.icon,
    required this.label,
    required this.isDark,
    required this.foreground,
    required this.onPressed,
  });

  final IconData icon;
  final String label;
  final bool isDark;
  final Color foreground;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.sm,
        vertical: AppSpacing.xs,
      ),
      minimumSize: const Size.square(AppSpacing.minInteractiveSize),
      onPressed: onPressed,
      child: Container(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.md,
          vertical: AppSpacing.xs,
        ),
        decoration: BoxDecoration(
          color: isDark ? AppColors.dark.backgroundSecondary : AppColors.white,
          borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
          border: Border.all(
            color: AppColorsFunctional.getColor(
              isDark,
              ColorType.borderPrimary,
            ),
          ),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Icon(icon, size: AppSpacing.iconSmall, color: foreground),
            SizedBox(width: AppSpacing.xs),
            Text(
              label,
              style: TextStyle(fontSize: AppTypography.sm, color: foreground),
            ),
          ],
        ),
      ),
    );
  }
}

String _assistantRunningStatusLabel(
  PersonalAssistantProcessSummary processSummary,
) {
  if (processSummary.finalAnswerReady ||
      processSummary.finalAnswerSummary.trim().isNotEmpty) {
    return AssistantText.assistantPhaseAnswering;
  }
  if (processSummary.processingSummary.trim().isNotEmpty ||
      processSummary.acceptedCount > 0) {
    return AssistantText.assistantPhaseAnalyzing;
  }
  if (processSummary.retrievalDesignNarrative.trim().isNotEmpty ||
      processSummary.searchCount > 0) {
    return AssistantText.assistantPhaseSearching;
  }
  return AssistantText.assistantPhaseUnderstanding;
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
