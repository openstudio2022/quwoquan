import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/constants/settings_semantic_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/widgets/app_modal_presenter.dart';
import 'package:quwoquan_app/core/widgets/app_modal_surface.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/ui/share/forward_external_share_service.dart';
import 'package:quwoquan_app/ui/share/forward_share_models.dart';
import 'package:quwoquan_app/ui/share/widgets/forward_confirm_sheet.dart';
import 'package:quwoquan_app/ui/share/widgets/forward_recipient_picker_route.dart';
import 'package:quwoquan_app/ui/share/widgets/forward_recipient_widgets.dart';

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
    final repo = ref.read(chatRepositoryProvider);
    final conversations = await repo.listConversations(limit: 30);
    return uniqueForwardRecipients(
      sortForwardRecipientsByRecent(
        conversations.map(AppForwardRecipient.fromConversation),
      ),
    ).take(AppForwardLimits.recentRecipients).toList(growable: false);
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
          Text(
            UITextConstants.forwardMostContacted,
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
                  child: const Center(child: CupertinoActivityIndicator()),
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
                  label: UITextConstants.forwardActionAppContacts,
                  onPressed: _openRecipientPicker,
                ),
              ),
              SizedBox(width: AppSpacing.containerMd),
              Expanded(
                child: _ForwardTargetAction(
                  isDark: isDark,
                  icon: CupertinoIcons.chat_bubble_2_fill,
                  label: UITextConstants.forwardActionWechatFriend,
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
                  label: UITextConstants.forwardActionWechatMoments,
                  onPressed: () => _openExternalShare(
                    ForwardExternalShareTarget.wechatMoments,
                  ),
                ),
              ),
            ],
          ),
          SizedBox(height: AppSpacing.containerLg),
          _ForwardSheetCancelButton(
            isDark: isDark,
            onPressed: () => Navigator.of(context).pop(),
          ),
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
    final result = await ref
        .read(forwardExternalShareServiceProvider)
        .share(payload: widget.payload, target: target);
    if (!mounted) {
      return;
    }
    final message = switch (result.delivery) {
      ForwardExternalShareDelivery.targetedWechat =>
        UITextConstants.forwardOpeningWechat,
      ForwardExternalShareDelivery.systemShareFallback =>
        UITextConstants.forwardShareSystemFallback,
      ForwardExternalShareDelivery.unavailable =>
        UITextConstants.forwardExternalShareUnavailable,
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
          UITextConstants.forwardNoRecentChats,
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

class _ForwardSheetCancelButton extends StatelessWidget {
  const _ForwardSheetCancelButton({
    required this.isDark,
    required this.onPressed,
  });

  final bool isDark;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final primary =
        SettingsSemanticConstants.conversationSheetPrimaryLabelColor(isDark);
    return DecoratedBox(
      decoration: BoxDecoration(
        border: Border(
          top: BorderSide(
            color: SettingsSemanticConstants.blockBorderColor(isDark),
            width: AppSpacing.hairline,
          ),
        ),
      ),
      child: CupertinoButton(
        padding: EdgeInsets.only(top: AppSpacing.containerMd),
        onPressed: onPressed,
        child: Text(
          UITextConstants.cancel,
          style: TextStyle(
            fontSize: AppTypography.iosBody,
            fontWeight: AppTypography.medium,
            color: primary,
          ),
        ),
      ),
    );
  }
}
