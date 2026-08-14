import 'package:quwoquan_app/design_system/feedback/app_empty_state.dart';
import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_pages.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/forms/settings/settings_inset_form_page.dart';
import 'package:quwoquan_app/design_system/layout/web_page_max_width_frame.dart';
import 'package:quwoquan_app/design_system/semantics/settings_semantic_constants.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/surfaces/app_modal_presenter.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/runtime/observability/trackers/chat_interaction_telemetry_tracker.dart';
import 'package:quwoquan_app/runtime/observability/trackers/page_lifecycle_observability.dart';
import 'package:quwoquan_app/design_system/feedback/app_toast.dart';
import 'package:quwoquan_app/runtime/di/conversation_members_provider.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/group_home_provider.dart';

/// 群公告查看与编辑页。
///
/// 对齐业界群公告语义：owner/admin 可编辑并发布（发布即通过
/// system_announcement 消息触达全员）；普通成员只读。
/// 权威字段来自 GroupHome（Conversation.announcement），发布走
/// metadata UpdateAnnouncement 命令。
class ChatAnnouncementPage extends ConsumerStatefulWidget {
  const ChatAnnouncementPage({super.key, required this.conversationId});

  final String conversationId;

  @override
  ConsumerState<ChatAnnouncementPage> createState() =>
      _ChatAnnouncementPageState();
}

class _ChatAnnouncementPageState extends ConsumerState<ChatAnnouncementPage> {
  static const int _announcementMaxLength = 2000;

  final TextEditingController _controller = TextEditingController();
  bool _hydrated = false;
  bool _submitting = false;
  bool _loadResultRecorded = false;
  late final PageLifecycleObservability _observability;
  late final DateTime _enteredAt;

  void _recordPageState({
    required String phase,
    Object? error,
    int? itemCount,
    int? durationMs,
  }) {
    _observability.recordPageState(
      pageName: PageNames.chatAnnouncement,
      route: AppUiSurfaces.chatAnnouncement.routeId,
      surface: AppUiSurfaces.chatAnnouncement.id,
      phase: phase,
      error: error,
      itemCount: itemCount,
      durationMs: durationMs,
    );
  }

  @override
  void initState() {
    super.initState();
    _observability = ref.read(pageLifecycleObservabilityProvider);
    _enteredAt = DateTime.now();
    _recordPageState(phase: 'enter');
    _recordPageState(phase: 'onlineLoading');
  }

  @override
  void dispose() {
    _recordPageState(
      phase: 'exit',
      durationMs: DateTime.now().difference(_enteredAt).inMilliseconds,
    );
    _controller.dispose();
    super.dispose();
  }

  Future<void> _publish() async {
    if (_submitting) {
      return;
    }
    final next = _controller.text.trim();
    final confirmed = await showAppCupertinoDialog<bool>(
      context: context,
      builder: (dialogContext) => CupertinoAlertDialog(
        title: Text(ChatText.groupAnnouncementEditTitle),
        content: Text(ChatText.groupAnnouncementPublishConfirm),
        actions: [
          CupertinoDialogAction(
            child: Text(FoundationText.cancel),
            onPressed: () => Navigator.pop(dialogContext, false),
          ),
          CupertinoDialogAction(
            isDefaultAction: true,
            child: Text(ChatText.groupAnnouncementPublish),
            onPressed: () => Navigator.pop(dialogContext, true),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) {
      return;
    }
    setState(() => _submitting = true);
    try {
      await ref
          .read(conversationMembersProvider(widget.conversationId).notifier)
          .updateAnnouncement(next);
      ref.invalidate(groupHomeProvider(widget.conversationId));
      if (!mounted) return;
      AppToast.show(
        context,
        next.isEmpty
            ? ChatText.groupAnnouncementCleared
            : ChatText.groupAnnouncementPublished,
      );
      _recordPageState(phase: 'updateSuccess');
      unawaited(
        ref
            .read(chatInteractionTelemetryTrackerProvider)
            .track(
              action: ChatInteractionAction.groupGovernance,
              outcome: ChatInteractionOutcome.succeeded,
              governanceAction: ChatGovernanceAction.announcementUpdate,
              pageName: PageNames.chatAnnouncement,
              surfaceId: AppUiSurfaces.chatAnnouncement.id,
            ),
      );
      context.pop();
    } catch (error) {
      _recordPageState(phase: 'updateFailure', error: error);
      unawaited(
        ref
            .read(chatInteractionTelemetryTrackerProvider)
            .track(
              action: ChatInteractionAction.groupGovernance,
              outcome: ChatInteractionOutcome.failed,
              governanceAction: ChatGovernanceAction.announcementUpdate,
              pageName: PageNames.chatAnnouncement,
              surfaceId: AppUiSurfaces.chatAnnouncement.id,
              error: error,
            ),
      );
      if (!mounted) return;
      final resolved = runtimeErrorSemantic(
        context,
        error: error,
        category: UiErrorCategory.submit,
        scope: UiErrorScope.global,
      );
      await AppActionErrorFeedback.show(context, semantic: resolved);
    } finally {
      if (mounted) {
        setState(() => _submitting = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final groupHomeAsync = ref.watch(groupHomeProvider(widget.conversationId));
    final groupHome = groupHomeAsync.value;
    final membersState = ref.watch(
      conversationMembersProvider(widget.conversationId),
    );
    final canEdit = membersState.isAdminOrOwner;
    final loadError = groupHomeAsync.hasError
        ? groupHomeAsync.error
        : membersState.error;
    if (!_loadResultRecorded && loadError != null) {
      _loadResultRecorded = true;
      _recordPageState(phase: 'failure', error: loadError);
    } else if (!_loadResultRecorded &&
        groupHome != null &&
        !membersState.isLoading) {
      _loadResultRecorded = true;
      _recordPageState(
        phase: 'contentReady',
        itemCount: groupHome.announcement.trim().isEmpty ? 0 : 1,
      );
    }
    if (loadError != null && groupHome == null) {
      return SettingsInsetFormPageScaffold(
        isDark: isDark,
        title: ChatText.groupAnnouncementEditTitle,
        onBack: () => context.pop(),
        body: AppPageErrorState(
          semantic: runtimeErrorSemantic(
            context,
            error: loadError,
            category: UiErrorCategory.pageLoad,
            scope: UiErrorScope.page,
          ),
          onRecovery: (action) async {
            if (action.type == UiErrorActionType.retry ||
                action.type == UiErrorActionType.resubmit) {
              ref.invalidate(groupHomeProvider(widget.conversationId));
              await ref
                  .read(
                    conversationMembersProvider(widget.conversationId).notifier,
                  )
                  .load();
              return UiRecoveryOutcome.superseded;
            }
            return UiRecoveryOutcome.cancelled;
          },
        ),
      );
    }
    final announcement = groupHome?.announcement.trim() ?? '';
    if (!_hydrated && groupHome != null) {
      _hydrated = true;
      _controller.text = announcement;
    }

    final secondaryText = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );

    return SettingsInsetFormPageScaffold(
      isDark: isDark,
      title: ChatText.groupAnnouncementEditTitle,
      onBack: () => context.pop(),
      trailing: canEdit
          ? CupertinoButton(
              key: const ValueKey('chat_announcement_publish_button'),
              padding: EdgeInsets.zero,
              onPressed: _submitting ? null : _publish,
              child: _submitting
                  ? AppRequestFeedback.inline()
                  : Text(
                      ChatText.groupAnnouncementPublish,
                      style: TextStyle(
                        fontSize: AppTypography.base,
                        fontWeight: AppTypography.medium,
                        color: AppColors.primaryColor,
                      ),
                    ),
            )
          : null,
      body: WebPageMaxWidthFrame(
        child: SafeArea(
          bottom: false,
          child: ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: EdgeInsets.only(
              left: SettingsSemanticConstants.insetFormListHorizontalPadding,
              right: SettingsSemanticConstants.insetFormListHorizontalPadding,
              top: AppSpacing.intraGroupSm,
              bottom: AppSpacing.xl + MediaQuery.paddingOf(context).bottom,
            ),
            children: [
              if (groupHomeAsync.isLoading && groupHome == null)
                AppRequestFeedback.section()
              else if (canEdit)
                SettingsInsetGroupedSection(
                  isDark: isDark,
                  density: SettingsInsetSectionDensity.standard,
                  child: CupertinoTextField(
                    key: const ValueKey('chat_announcement_editor'),
                    controller: _controller,
                    placeholder: ChatText.groupAnnouncementHint,
                    maxLength: _announcementMaxLength,
                    maxLines: 12,
                    minLines: 6,
                    decoration: const BoxDecoration(),
                    style: TextStyle(
                      fontSize: AppTypography.base,
                      color: SettingsSemanticConstants.labelColor(isDark),
                    ),
                  ),
                )
              else ...[
                SettingsInsetGroupedSection(
                  isDark: isDark,
                  density: SettingsInsetSectionDensity.standard,
                  child: announcement.isEmpty
                      ? const AppEmptyState(
                          key: ValueKey('chat_announcement_readonly_body'),
                          icon: CupertinoIcons.doc_plaintext,
                          title: ChatText.groupAnnouncementEmpty,
                          density: AppEmptyStateDensity.dense,
                        )
                      : Padding(
                          padding: EdgeInsets.all(AppSpacing.md),
                          child: Text(
                            announcement,
                            key: const ValueKey(
                              'chat_announcement_readonly_body',
                            ),
                            style: TextStyle(
                              fontSize: AppTypography.base,
                              color: SettingsSemanticConstants.labelColor(
                                isDark,
                              ),
                            ),
                          ),
                        ),
                ),
                SizedBox(height: AppSpacing.intraGroupSm),
                Padding(
                  padding: EdgeInsets.symmetric(horizontal: AppSpacing.md),
                  child: Text(
                    ChatText.groupAnnouncementViewOnlyNote,
                    style: TextStyle(
                      fontSize: AppTypography.sm,
                      color: secondaryText,
                    ),
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
