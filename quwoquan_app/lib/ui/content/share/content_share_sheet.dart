import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/auth/auth_gate.dart';
import 'package:quwoquan_app/core/constants/settings_semantic_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/errors/runtime_error_display.dart';
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';
import 'package:quwoquan_app/core/widgets/app_modal_presenter.dart';
import 'package:quwoquan_app/core/widgets/app_modal_surface.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/core/widgets/error_states/app_error_states.dart';
import 'package:quwoquan_app/ui/content/share/content_circle_share_picker_route.dart';
import 'package:quwoquan_app/ui/content/share/content_share_actions.dart';
import 'package:quwoquan_app/ui/content/share/content_share_template.dart';
import 'package:quwoquan_app/ui/share/forward_external_share_service.dart';
import 'package:quwoquan_app/ui/share/forward_share_models.dart';
import 'package:quwoquan_app/ui/share/widgets/forward_confirm_sheet.dart';
import 'package:quwoquan_app/ui/share/widgets/forward_recipient_picker_route.dart';
import 'package:quwoquan_app/ui/share/widgets/forward_recipient_widgets.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef ContentShareExternalCallback =
    Future<void> Function(ForwardExternalShareTarget target);

class ContentShareSheet extends StatefulWidget {
  const ContentShareSheet({
    super.key,
    required this.template,
    this.actionHandler = const DefaultContentShareActionHandler(),
    this.onActionCompleted,
    this.recentRecipients,
    this.onRecentRecipientsRetry,
    this.onRecentRecipientTap,
    this.onCircleTap,
    this.onGroupTap,
    this.onMessageTap,
    this.onExternalShare,
  });

  final ContentShareTemplate template;
  final ContentShareActionHandler actionHandler;
  final Future<void> Function(ContentShareActionResult result)?
  onActionCompleted;
  final Future<List<AppForwardRecipient>>? recentRecipients;
  final VoidCallback? onRecentRecipientsRetry;
  final ValueChanged<AppForwardRecipient>? onRecentRecipientTap;
  final VoidCallback? onCircleTap;
  final VoidCallback? onGroupTap;
  final VoidCallback? onMessageTap;
  final ContentShareExternalCallback? onExternalShare;

  static Future<void> show(
    BuildContext context, {
    required ContentShareTemplate template,
    ContentShareActionHandler actionHandler =
        const DefaultContentShareActionHandler(),
    Future<void> Function(ContentShareActionResult result)? onActionCompleted,
    CirclePostPlacementCommandWriter? circlePostPlacementWriter,
    CircleMembershipQuery? circleMembershipQuery,
    ContentOutboundShareAppendWriter? outboundShareWriter,
  }) {
    return showAppBottomModal<void>(
      context: context,
      builder: (sheetContext) {
        final isDark =
            CupertinoTheme.of(sheetContext).brightness == Brightness.dark;
        return AppBottomModalSurface(
          panelKey: const ValueKey<String>('content-share-panel'),
          onDismiss: () => Navigator.of(sheetContext).pop(),
          backgroundColor:
              SettingsSemanticConstants.conversationSheetPanelBackground(
                isDark,
              ),
          contentPadding: EdgeInsets.fromLTRB(
            SettingsSemanticConstants.conversationSheetOuterHorizontalPadding,
            0,
            SettingsSemanticConstants.conversationSheetOuterHorizontalPadding,
            SettingsSemanticConstants.conversationSheetOuterHorizontalPadding,
          ),
          maxHeightRatio: AppSpacing.modalSheetMaxHeightRatio,
          showHandle: false,
          child: _ConnectedContentShareSheet(
            template: template,
            actionHandler: actionHandler,
            onActionCompleted: onActionCompleted,
            circlePostPlacementWriter: circlePostPlacementWriter,
            circleMembershipQuery: circleMembershipQuery,
            outboundShareWriter: outboundShareWriter,
          ),
        );
      },
    );
  }

  @override
  State<ContentShareSheet> createState() => _ContentShareSheetState();
}

class _ConnectedContentShareSheet extends ConsumerStatefulWidget {
  const _ConnectedContentShareSheet({
    required this.template,
    required this.actionHandler,
    this.onActionCompleted,
    this.circlePostPlacementWriter,
    this.circleMembershipQuery,
    this.outboundShareWriter,
  });

  final ContentShareTemplate template;
  final ContentShareActionHandler actionHandler;
  final Future<void> Function(ContentShareActionResult result)?
  onActionCompleted;
  final CirclePostPlacementCommandWriter? circlePostPlacementWriter;
  final CircleMembershipQuery? circleMembershipQuery;
  final ContentOutboundShareAppendWriter? outboundShareWriter;

  @override
  ConsumerState<_ConnectedContentShareSheet> createState() =>
      _ConnectedContentShareSheetState();
}

class _ConnectedContentShareSheetState
    extends ConsumerState<_ConnectedContentShareSheet> {
  late final AppForwardPayload _payload;
  late Future<List<AppForwardRecipient>> _recentFuture;

  @override
  void initState() {
    super.initState();
    _payload = AppForwardPayload(
      kind: AppForwardSubjectKind.post,
      title: widget.template.shareTitle,
      subtitle: widget.template.shareSummary,
      thumbnailUrl: widget.template.coverUrl,
      deeplink: widget.template.deeplink,
      landingUrl: widget.template.landingUrl,
      shareText: <String>[
        widget.template.shareTitle,
        widget.template.shareSummary,
        widget.template.landingUrl,
      ].where((value) => value.trim().isNotEmpty).join('\n'),
      extra: <String, Object?>{
        'postId': widget.template.postId,
        'shareId': widget.template.shareId,
        'permission': widget.template.permission,
      },
    );
    _recentFuture = _loadRecentRecipients();
  }

  Future<List<AppForwardRecipient>> _loadRecentRecipients() async {
    final conversations = await ref
        .read(chatRepositoryProvider)
        .listConversations(limit: 30);
    return uniqueForwardRecipients(
      sortForwardRecipientsByRecent(
        conversations.map(AppForwardRecipient.fromConversation),
      ),
    ).take(AppForwardLimits.recentRecipients).toList(growable: false);
  }

  @override
  Widget build(BuildContext context) {
    return ContentShareSheet(
      template: widget.template,
      actionHandler: widget.actionHandler,
      onActionCompleted: _handleActionCompleted,
      recentRecipients: _recentFuture,
      onRecentRecipientsRetry: _retryRecentRecipients,
      onRecentRecipientTap: (recipient) => runWhenLoggedIn(
        ref,
        context,
        AuthGateReason.sendMessage,
        () => _shareToRecentRecipient(recipient),
      ),
      onCircleTap:
          widget.circlePostPlacementWriter == null ||
              widget.circleMembershipQuery == null
          ? null
          : () => runWhenLoggedIn(
              ref,
              context,
              AuthGateReason.generic,
              _openCirclePicker,
            ),
      onGroupTap: () => runWhenLoggedIn(
        ref,
        context,
        AuthGateReason.sendMessage,
        () => _openRecipientPicker(ForwardRecipientPickerMode.groups),
      ),
      onMessageTap: () => runWhenLoggedIn(
        ref,
        context,
        AuthGateReason.sendMessage,
        () => _openRecipientPicker(ForwardRecipientPickerMode.messages),
      ),
      onExternalShare: _shareExternal,
    );
  }

  void _retryRecentRecipients() {
    setState(() {
      _recentFuture = _loadRecentRecipients();
    });
  }

  Future<void> _shareToRecentRecipient(AppForwardRecipient recipient) async {
    final sent = await ForwardConfirmSheet.show(
      context,
      payload: _payload,
      recipient: recipient,
    );
    if (sent != true) {
      return;
    }
    await _complete(
      recipient.kind == AppForwardRecipientKind.group
          ? 'group_chat'
          : 'direct_message',
    );
    if (mounted) {
      Navigator.of(context).pop();
    }
  }

  void _openCirclePicker() {
    final rootNavigator = Navigator.of(context, rootNavigator: true);
    final postId = widget.template.postId;
    final onCompleted = widget.onActionCompleted;
    dismissAppModalAndRun(
      context,
      action: () async {
        final shared = await rootNavigator.push<bool>(
          CupertinoPageRoute<bool>(
            builder: (_) => ContentCircleSharePickerRoute(
              postId: postId,
              placementWriter: widget.circlePostPlacementWriter!,
              membershipQuery: widget.circleMembershipQuery!,
            ),
          ),
        );
        if (shared == true) {
          await onCompleted?.call(
            const ContentShareActionResult(
              actionId: 'circle_repost',
              success: true,
            ),
          );
        }
      },
    );
  }

  void _openRecipientPicker(ForwardRecipientPickerMode mode) {
    final rootNavigator = Navigator.of(context, rootNavigator: true);
    final payload = _payload;
    final onCompleted = widget.onActionCompleted;
    dismissAppModalAndRun(
      context,
      action: () async {
        final sent = await rootNavigator.push<bool>(
          CupertinoPageRoute<bool>(
            builder: (_) =>
                ForwardRecipientPickerRoute(payload: payload, mode: mode),
          ),
        );
        if (sent == true) {
          await onCompleted?.call(
            ContentShareActionResult(
              actionId: mode == ForwardRecipientPickerMode.groups
                  ? 'group_chat'
                  : 'direct_message',
              success: true,
            ),
          );
        }
      },
    );
  }

  Future<void> _shareExternal(ForwardExternalShareTarget target) async {
    late final ForwardExternalShareResult result;
    try {
      result = await ref
          .read(forwardExternalShareServiceProvider)
          .share(payload: _payload, target: target);
    } catch (error) {
      if (!mounted) {
        return;
      }
      await AppActionErrorFeedback.show(
        context,
        semantic: runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.submit,
          scope: UiErrorScope.dialog,
        ),
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await _shareExternal(target);
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
        UITextConstants.forwardOpeningWechat,
      ForwardExternalShareDelivery.wechatCompleted =>
        UITextConstants.shareCompleted,
      ForwardExternalShareDelivery.systemShareFallback =>
        UITextConstants.forwardShareSystemFallback,
      ForwardExternalShareDelivery.cancelled => '',
      ForwardExternalShareDelivery.unavailable =>
        UITextConstants.forwardExternalShareUnavailable,
    };
    AppToast.show(context, message);
    if (result.delivery == ForwardExternalShareDelivery.wechatCompleted) {
      await _complete(
        target == ForwardExternalShareTarget.wechatFriend
            ? 'wechat_friend'
            : 'wechat_moments',
        destinationKind: 'external_app',
        destination: target.name,
        providerReceiptId: result.requestId,
      );
    }
  }

  Future<void> _complete(
    String actionId, {
    String? destinationKind,
    String? destination,
    String? providerReceiptId,
  }) async {
    await _handleActionCompleted(
      ContentShareActionResult(
        actionId: actionId,
        success: true,
        destinationKind: destinationKind,
        destination: destination,
        providerReceiptId: providerReceiptId,
      ),
    );
  }

  Future<void> _handleActionCompleted(ContentShareActionResult result) async {
    final writer = widget.outboundShareWriter;
    if (writer != null && result.isConfirmedOutboundDelivery) {
      final referralId = widget.template.shareId.trim();
      if (referralId.isEmpty) {
        throw StateError('outbound_share_missing_referral_id');
      }
      await writer.appendOutboundShare(
        CreateContentOutboundShareCommand(
          postId: widget.template.postId,
          channel: result.actionId,
          destinationKind: result.destinationKind!,
          destination: result.destination,
          referralId: referralId,
          providerReceiptId: result.providerReceiptId!,
          clientConfirmedAt: DateTime.now().toUtc(),
        ),
      );
    }
    await widget.onActionCompleted?.call(result);
  }
}

class _ContentShareSheetState extends State<ContentShareSheet> {
  String? _busyActionId;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final primaryText =
        SettingsSemanticConstants.conversationSheetPrimaryLabelColor(isDark);
    final secondaryText =
        SettingsSemanticConstants.conversationSheetSecondaryLabelColor(isDark);

    return SingleChildScrollView(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          _ShareHeader(primaryText: primaryText),
          _SharePreviewCard(
            template: widget.template,
            primaryText: primaryText,
            secondaryText: secondaryText,
          ),
          if ((widget.template.notice ?? '').trim().isNotEmpty) ...<Widget>[
            SizedBox(height: AppSpacing.intraGroupSm),
            Text(
              widget.template.notice!.trim(),
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: AppTypography.iosFootnote,
                color: widget.template.isBlocked
                    ? AppColors.iosDestructive(context)
                    : secondaryText,
              ),
            ),
          ],
          if (widget.template.isBlocked) ...<Widget>[
            SizedBox(height: AppSpacing.interGroupMd),
            _BlockedShareNotice(primaryText: primaryText),
          ] else ...<Widget>[
            SizedBox(height: AppSpacing.interGroupMd),
            _ShareSectionTitle(
              title: UITextConstants.shareInternalTitle,
              color: primaryText,
            ),
            if (widget.recentRecipients != null) ...<Widget>[
              SizedBox(height: AppSpacing.containerSm),
              FutureBuilder<List<AppForwardRecipient>>(
                future: widget.recentRecipients,
                builder: (context, snapshot) {
                  if (snapshot.connectionState != ConnectionState.done) {
                    return SizedBox(
                      height: AppSpacing.avatarUserXl,
                      child: const Center(child: CupertinoActivityIndicator()),
                    );
                  }
                  if (snapshot.hasError) {
                    return AppSectionErrorCard(
                      margin: EdgeInsets.zero,
                      semantic: runtimeErrorSemantic(
                        context,
                        error:
                            snapshot.error ??
                            StateError(UITextConstants.loadFailed),
                        category: UiErrorCategory.sectionLoad,
                        scope: UiErrorScope.section,
                      ),
                      onAction: (action) async {
                        if (action.type == UiErrorActionType.retry ||
                            action.type == UiErrorActionType.resubmit) {
                          widget.onRecentRecipientsRetry?.call();
                        }
                      },
                    );
                  }
                  final recipients =
                      snapshot.data ?? const <AppForwardRecipient>[];
                  if (recipients.isEmpty) {
                    return const SizedBox.shrink();
                  }
                  return ForwardRecentRecipientRail(
                    isDark: isDark,
                    recipients: recipients,
                    maxCount: AppForwardLimits.recentRecipients,
                    onRecipientTap: (recipient) =>
                        widget.onRecentRecipientTap?.call(recipient),
                  );
                },
              ),
            ],
            SizedBox(height: AppSpacing.containerSm),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceAround,
              children: <Widget>[
                _ShareTargetAction(
                  icon: CupertinoIcons.circle_grid_hex_fill,
                  label: UITextConstants.shareTargetCircle,
                  color: AppColors.iosAccent(context),
                  onPressed: widget.onCircleTap,
                ),
                _ShareTargetAction(
                  icon: CupertinoIcons.person_3_fill,
                  label: UITextConstants.shareTargetGroup,
                  color: CupertinoDynamicColor.resolve(
                    CupertinoColors.systemOrange,
                    context,
                  ),
                  onPressed: widget.onGroupTap,
                ),
                _ShareTargetAction(
                  icon: CupertinoIcons.chat_bubble_2_fill,
                  label: UITextConstants.shareTargetMessage,
                  color: CupertinoDynamicColor.resolve(
                    CupertinoColors.systemBlue,
                    context,
                  ),
                  onPressed: widget.onMessageTap,
                ),
              ],
            ),
            SizedBox(height: AppSpacing.interGroupMd),
            Divider(
              height: AppSpacing.hairline,
              color: AppColors.iosSeparator(context),
            ),
            SizedBox(height: AppSpacing.interGroupMd),
            _ShareSectionTitle(
              title: UITextConstants.shareExternalTitle,
              color: primaryText,
            ),
            SizedBox(height: AppSpacing.containerSm),
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                children: <Widget>[
                  _ShareTargetAction(
                    icon: CupertinoIcons.chat_bubble_2_fill,
                    label: UITextConstants.forwardActionWechatFriend,
                    color: AppColors.success,
                    busy: _busyActionId == 'wechat_friend',
                    onPressed: widget.onExternalShare == null
                        ? null
                        : () => _handleExternal(
                            'wechat_friend',
                            ForwardExternalShareTarget.wechatFriend,
                          ),
                  ),
                  _actionSpacer,
                  _ShareTargetAction(
                    icon: CupertinoIcons.circle_grid_3x3_fill,
                    label: UITextConstants.forwardActionWechatMoments,
                    color: AppColors.success,
                    busy: _busyActionId == 'wechat_moments',
                    onPressed: widget.onExternalShare == null
                        ? null
                        : () => _handleExternal(
                            'wechat_moments',
                            ForwardExternalShareTarget.wechatMoments,
                          ),
                  ),
                  for (final action in widget.template.actions) ...<Widget>[
                    _actionSpacer,
                    _ShareTargetAction(
                      icon: _iconForAction(action.id),
                      label: action.id == 'system_share'
                          ? UITextConstants.shareActionMore
                          : action.label,
                      color: primaryText,
                      busy: _busyActionId == action.id,
                      onPressed: _busyActionId == null
                          ? () => _handleAction(action)
                          : null,
                    ),
                  ],
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget get _actionSpacer => SizedBox(width: AppSpacing.containerMd);

  Future<void> _handleExternal(
    String actionId,
    ForwardExternalShareTarget target,
  ) async {
    if (_busyActionId != null) {
      return;
    }
    setState(() => _busyActionId = actionId);
    await widget.onExternalShare?.call(target);
    if (mounted) {
      setState(() => _busyActionId = null);
    }
  }

  Future<void> _handleAction(ContentShareAction action) async {
    setState(() => _busyActionId = action.id);
    final result = await widget.actionHandler.execute(
      context,
      widget.template,
      action,
    );
    if (!mounted) {
      return;
    }
    setState(() => _busyActionId = null);
    if (result.success) {
      await widget.onActionCompleted?.call(result);
    }
  }

  IconData _iconForAction(String actionId) {
    return switch (actionId) {
      'save_poster' => CupertinoIcons.photo_fill,
      'system_share' => CupertinoIcons.ellipsis,
      _ => CupertinoIcons.link,
    };
  }
}

class _ShareHeader extends StatelessWidget {
  const _ShareHeader({required this.primaryText});

  final Color primaryText;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: AppSpacing.modalHeaderHeight,
      child: Stack(
        alignment: Alignment.center,
        children: <Widget>[
          Text(
            UITextConstants.shareTo,
            style: TextStyle(
              fontSize: AppTypography.iosTitle3,
              fontWeight: AppTypography.semiBold,
              color: primaryText,
            ),
          ),
          PositionedDirectional(
            end: 0,
            child: CupertinoButton(
              key: const ValueKey<String>('content-share-close-button'),
              padding: EdgeInsets.zero,
              minimumSize: const Size(
                AppSpacing.minInteractiveSize,
                AppSpacing.minInteractiveSize,
              ),
              onPressed: () => Navigator.of(context).maybePop(),
              child: Icon(
                CupertinoIcons.xmark,
                size: AppSpacing.iconMedium,
                color: primaryText,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _SharePreviewCard extends StatelessWidget {
  const _SharePreviewCard({
    required this.template,
    required this.primaryText,
    required this.secondaryText,
  });

  final ContentShareTemplate template;
  final Color primaryText;
  final Color secondaryText;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.iosGroupedSurface(context),
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
      ),
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerSm),
        child: Row(
          children: <Widget>[
            ClipRRect(
              borderRadius: BorderRadius.circular(
                AppSpacing.contentPreviewCornerRadius,
              ),
              child: SizedBox(
                width: AppSpacing.largeButtonSize,
                height: AppSpacing.largeButtonSize,
                child: template.coverUrl.trim().isEmpty
                    ? ColoredBox(
                        color: AppColors.iosTintedFill(context),
                        child: Icon(
                          CupertinoIcons.doc_richtext,
                          color: AppColors.iosAccent(context),
                        ),
                      )
                    : AppCachedNetworkImage(
                        imageUrl: template.coverUrl,
                        fit: BoxFit.cover,
                        width: AppSpacing.largeButtonSize,
                        height: AppSpacing.largeButtonSize,
                        cdnPreset: CdnImagePreset.thumbnail,
                        errorWidget: ColoredBox(
                          color: AppColors.iosTintedFill(context),
                          child: Icon(
                            CupertinoIcons.doc_richtext,
                            color: AppColors.iosAccent(context),
                          ),
                        ),
                      ),
              ),
            ),
            SizedBox(width: AppSpacing.containerSm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    template.title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: AppTypography.iosCaption1,
                      color: AppColors.iosAccent(context),
                    ),
                  ),
                  SizedBox(height: AppSpacing.intraGroupXs),
                  Text(
                    template.shareTitle,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: AppTypography.iosSubheadline,
                      fontWeight: AppTypography.semiBold,
                      color: primaryText,
                    ),
                  ),
                  if (template.shareSummary.trim().isNotEmpty)
                    Text(
                      template.shareSummary,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: AppTypography.iosCaption1,
                        color: secondaryText,
                      ),
                    ),
                  Text(
                    template.subtitle,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: AppTypography.iosCaption2,
                      color: secondaryText,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ShareSectionTitle extends StatelessWidget {
  const _ShareSectionTitle({required this.title, required this.color});

  final String title;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Text(
      title,
      style: TextStyle(
        fontSize: AppTypography.iosSubheadline,
        fontWeight: AppTypography.semiBold,
        color: color,
      ),
    );
  }
}

class _ShareTargetAction extends StatelessWidget {
  const _ShareTargetAction({
    required this.icon,
    required this.label,
    required this.color,
    required this.onPressed,
    this.busy = false,
  });

  final IconData icon;
  final String label;
  final Color color;
  final VoidCallback? onPressed;
  final bool busy;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: AppSpacing.largeButtonSize + AppSpacing.containerMd,
      child: CupertinoButton(
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
                color: color.withValues(alpha: 0.12),
                shape: BoxShape.circle,
              ),
              child: busy
                  ? const CupertinoActivityIndicator()
                  : Icon(icon, size: AppSpacing.iconLarge, color: color),
            ),
            SizedBox(height: AppSpacing.intraGroupXs),
            Text(
              label,
              textAlign: TextAlign.center,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: AppTypography.iosCaption2,
                color: AppColors.iosSecondaryLabel(context),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _BlockedShareNotice extends StatelessWidget {
  const _BlockedShareNotice({required this.primaryText});

  final Color primaryText;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.iosSecondaryFill(context),
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
      ),
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerMd),
        child: Row(
          children: <Widget>[
            Icon(
              CupertinoIcons.lock_fill,
              color: AppColors.iosSecondaryLabel(context),
            ),
            SizedBox(width: AppSpacing.containerSm),
            Expanded(
              child: Text(
                UITextConstants.sharePrivateBlocked,
                style: TextStyle(
                  fontSize: AppTypography.iosSubheadline,
                  color: primaryText,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
