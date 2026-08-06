import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/design_system/semantics/settings_semantic_constants.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/design_system/surfaces/app_modal_presenter.dart';
import 'package:quwoquan_app/design_system/surfaces/app_modal_surface.dart';
import 'package:quwoquan_app/design_system/feedback/app_toast.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/runtime/shell/share/forward_external_share_service.dart';
import 'package:quwoquan_app/runtime/di/share/forward_share_models.dart';
import 'package:quwoquan_app/runtime/di/share/forward_confirm_sheet.dart';
import 'package:quwoquan_app/runtime/shell/share/forward_recipient_picker_route.dart';
import 'package:quwoquan_app/runtime/shell/share/forward_recipient_widgets.dart';

class ForwardShareSheet extends ConsumerStatefulWidget {
  const ForwardShareSheet({super.key, required this.payload});

  final AppForwardPayload payload;

  static Future<void> show(
    BuildContext context, {
    required AppForwardPayload payload,
  }) {
    return showAppBottomModal<void>(
      context: context,
      builder: (sheetContext) => ForwardShareSheet(payload: payload),
    );
  }

  @override
  ConsumerState<ForwardShareSheet> createState() => _ForwardShareSheetState();
}

class _ForwardShareSheetState extends ConsumerState<ForwardShareSheet> {
  late Future<List<AppForwardRecipient>> _recentFuture;

  @override
  void initState() {
    super.initState();
    _recentFuture = _loadRecentRecipients();
  }

  Future<List<AppForwardRecipient>> _loadRecentRecipients() async {
    final repo = ref.read(chatConversationRepositoryProvider);
    final conversations = await repo.listConversations(limit: 30);
    return uniqueForwardRecipients(
      sortForwardRecipientsByRecent(
        conversations.map(AppForwardRecipient.fromConversation),
      ),
    ).take(AppForwardLimits.recentRecipients).toList(growable: false);
  }

  void _retryRecentRecipients() {
    setState(() {
      _recentFuture = _loadRecentRecipients();
    });
  }

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final primary =
        SettingsSemanticConstants.conversationSheetPrimaryLabelColor(isDark);
    return AppBottomModalSurface(
      onDismiss: () => Navigator.of(context).pop(),
      backgroundColor:
          SettingsSemanticConstants.conversationSheetPanelBackground(isDark),
      contentPadding: EdgeInsets.fromLTRB(
        SettingsSemanticConstants.conversationSheetOuterHorizontalPadding,
        SettingsSemanticConstants.conversationSheetOuterHorizontalPadding,
        SettingsSemanticConstants.conversationSheetOuterHorizontalPadding,
        SettingsSemanticConstants.conversationSheetOuterHorizontalPadding,
      ),
      maxHeightRatio: AppSpacing.modalSheetMaxHeightRatio,
      showHandle: false,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          _ForwardShareHeader(primary: primary),
          Text(
            ChatText.forwardMostContacted,
            style: TextStyle(
              fontSize: AppTypography.iosTitle3,
              fontWeight: AppTypography.semiBold,
              color: primary,
            ),
          ),
          SizedBox(height: AppSpacing.containerMd),
          FutureBuilder<List<AppForwardRecipient>>(
            future: _recentFuture,
            builder: (context, snapshot) {
              if (snapshot.connectionState != ConnectionState.done) {
                return SizedBox(
                  height: AppSpacing.avatarUserXl + AppSpacing.containerLg,
                  child: AppRequestFeedback.section(),
                );
              }
              if (snapshot.hasError) {
                return AppSectionErrorCard(
                  margin: EdgeInsets.zero,
                  semantic: ensureRetryUiErrorSemantic(
                    runtimeErrorSemantic(
                      context,
                      error:
                          snapshot.error ??
                          StateError(FoundationText.loadFailed),
                      category: UiErrorCategory.sectionLoad,
                      scope: UiErrorScope.section,
                    ),
                  ),
                  onAction: (action) async {
                    if (action.type == UiErrorActionType.retry ||
                        action.type == UiErrorActionType.resubmit) {
                      _retryRecentRecipients();
                    }
                  },
                );
              }
              final recipients = snapshot.data ?? const <AppForwardRecipient>[];
              if (recipients.isEmpty) {
                return _RecentEmptyState(isDark: isDark);
              }
              return ForwardRecentRecipientRail(
                isDark: isDark,
                recipients: recipients,
                maxCount: AppForwardLimits.recentRecipients,
                onRecipientTap: _handleRecentRecipient,
              );
            },
          ),
          SizedBox(height: AppSpacing.containerLg),
          Row(
            children: <Widget>[
              Expanded(
                child: _ForwardTargetAction(
                  isDark: isDark,
                  icon: CupertinoIcons.person_2_fill,
                  label: ChatText.forwardActionAppContacts,
                  onPressed: _openRecipientPicker,
                ),
              ),
              SizedBox(width: AppSpacing.containerMd),
              Expanded(
                child: _ForwardTargetAction(
                  isDark: isDark,
                  icon: CupertinoIcons.chat_bubble_2_fill,
                  label: ChatText.forwardActionWechatFriend,
                  onPressed: () => _openExternalShare(
                    ForwardExternalShareTarget.wechatFriend,
                  ),
                ),
              ),
              SizedBox(width: AppSpacing.containerMd),
              Expanded(
                child: _ForwardTargetAction(
                  isDark: isDark,
                  icon: CupertinoIcons.circle_grid_3x3_fill,
                  label: ChatText.forwardActionWechatMoments,
                  onPressed: () => _openExternalShare(
                    ForwardExternalShareTarget.wechatMoments,
                  ),
                ),
              ),
            ],
          ),
          SizedBox(height: AppSpacing.containerLg),
        ],
      ),
    );
  }

  Future<void> _handleRecentRecipient(AppForwardRecipient recipient) async {
    final sent = await ForwardConfirmSheet.show(
      context,
      payload: widget.payload,
      recipient: recipient,
    );
    if (sent == true && mounted) {
      Navigator.of(context).pop();
    }
  }

  Future<void> _openRecipientPicker() async {
    final rootNavigator = Navigator.of(context, rootNavigator: true);
    final payload = widget.payload;
    await dismissAppModalAndRun(
      context,
      action: () => rootNavigator.push<bool>(
        CupertinoPageRoute<bool>(
          builder: (_) => ForwardRecipientPickerRoute(payload: payload),
        ),
      ),
    );
  }

  Future<void> _openExternalShare(ForwardExternalShareTarget target) async {
    late final ForwardExternalShareResult result;
    try {
      result = await ref
          .read(forwardExternalShareServiceProvider)
          .share(payload: widget.payload, target: target);
    } catch (error) {
      if (!mounted) {
        return;
      }
      await AppActionErrorFeedback.show(
        context,
        semantic: ensureRetryUiErrorSemantic(
          runtimeErrorSemantic(
            context,
            error: error,
            category: UiErrorCategory.submit,
            scope: UiErrorScope.dialog,
          ),
        ),
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await _openExternalShare(target);
          }
        },
      );
      return;
    }
    if (!mounted) {
      return;
    }
    if (result.delivery == ForwardExternalShareDelivery.cancelled) {
      return;
    }
    final message = switch (result.delivery) {
      ForwardExternalShareDelivery.wechatAccepted =>
        ChatText.forwardOpeningWechat,
      ForwardExternalShareDelivery.wechatCompleted => ChatText.shareCompleted,
      ForwardExternalShareDelivery.systemShareFallback =>
        ChatText.forwardShareSystemFallback,
      ForwardExternalShareDelivery.cancelled => '',
      ForwardExternalShareDelivery.unavailable =>
        ChatText.forwardExternalShareUnavailable,
    };
    AppToast.show(context, message);
  }
}

class _RecentEmptyState extends StatelessWidget {
  const _RecentEmptyState({required this.isDark});

  final bool isDark;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: AppSpacing.avatarUserXl + AppSpacing.containerLg,
      child: Center(
        child: Text(
          ChatText.forwardNoRecentChats,
          style: TextStyle(
            fontSize: AppTypography.iosFootnote,
            color:
                SettingsSemanticConstants.conversationSheetSecondaryLabelColor(
                  isDark,
                ),
          ),
        ),
      ),
    );
  }
}

class _ForwardTargetAction extends StatelessWidget {
  const _ForwardTargetAction({
    required this.isDark,
    required this.icon,
    required this.label,
    required this.onPressed,
  });

  final bool isDark;
  final IconData icon;
  final String label;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final primary =
        SettingsSemanticConstants.conversationSheetPrimaryLabelColor(isDark);
    final secondary =
        SettingsSemanticConstants.conversationSheetSecondaryLabelColor(isDark);
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: onPressed,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Container(
            width: AppSpacing.largeButtonSize,
            height: AppSpacing.largeButtonSize,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: SettingsSemanticConstants.blockBackground(isDark),
              borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
              border: Border.all(
                color: SettingsSemanticConstants.blockBorderColor(isDark),
                width: AppSpacing.hairline,
              ),
            ),
            child: Icon(icon, size: AppSpacing.iconLarge, color: primary),
          ),
          SizedBox(height: AppSpacing.intraGroupXs),
          Text(
            label,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: AppTypography.iosCaption1,
              color: secondary,
            ),
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
          ),
        ],
      ),
    );
  }
}

class _ForwardShareHeader extends StatelessWidget {
  const _ForwardShareHeader({required this.primary});

  final Color primary;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: AppSpacing.modalHeaderHeight,
      child: Stack(
        alignment: Alignment.center,
        children: <Widget>[
          Text(
            ChatText.shareTo,
            style: TextStyle(
              fontSize: AppTypography.iosTitle3,
              fontWeight: AppTypography.semiBold,
              color: primary,
            ),
          ),
          PositionedDirectional(
            end: 0,
            child: CupertinoButton(
              key: const ValueKey<String>('forward-share-close-button'),
              padding: EdgeInsets.zero,
              minimumSize: const Size(
                AppSpacing.minInteractiveSize,
                AppSpacing.minInteractiveSize,
              ),
              onPressed: () => Navigator.of(context).maybePop(),
              child: Icon(
                CupertinoIcons.xmark,
                size: AppSpacing.iconMedium,
                color: primary,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
