import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/auth/auth_continuation.dart';
import 'package:quwoquan_app/core/auth/auth_gate.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/constants/chat_text_constants.dart';
import 'package:quwoquan_app/core/constants/settings_semantic_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/errors/runtime_error_display.dart';
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/trackers/journey_event_tracker.dart';
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

part 'content_share_sheet_components.dart';

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
    this.journeyEventTracker,
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
  final JourneyEventTracker? journeyEventTracker;

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
  List<AppForwardRecipient> _recentRecipients = const <AppForwardRecipient>[];
  bool _continuationResumeScheduled = false;

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
    _recentFuture = ref.read(authSessionControllerProvider).isAuthenticated
        ? _loadRecentRecipients()
        : Future<List<AppForwardRecipient>>.value(
            const <AppForwardRecipient>[],
          );
  }

  Future<List<AppForwardRecipient>> _loadRecentRecipients() async {
    final conversations = await ref
        .read(chatConversationRepositoryProvider)
        .listConversations(limit: 30);
    final recipients = uniqueForwardRecipients(
      sortForwardRecipientsByRecent(
        conversations.map(AppForwardRecipient.fromConversation),
      ),
    ).take(AppForwardLimits.recentRecipients).toList(growable: false);
    _recentRecipients = recipients;
    return recipients;
  }

  @override
  Widget build(BuildContext context) {
    ref.listen<AuthSessionState>(authSessionControllerProvider, (
      AuthSessionState? previous,
      AuthSessionState next,
    ) {
      if (next.isAuthenticated &&
          (previous == null || !previous.isAuthenticated)) {
        _scheduleContinuationResume();
      }
    });
    return ContentShareSheet(
      template: widget.template,
      actionHandler: widget.actionHandler,
      onActionCompleted: _handleActionCompleted,
      recentRecipients: _recentFuture,
      onRecentRecipientsRetry: _retryRecentRecipients,
      onRecentRecipientTap: (recipient) => _runOrContinueShare(
        target: ContentShareContinuationTarget.recentRecipient,
        reason: AuthGateReason.sendMessage,
        recipientId: recipient.id,
        action: () => _shareToRecentRecipient(recipient),
      ),
      onCircleTap:
          widget.circlePostPlacementWriter == null ||
              widget.circleMembershipQuery == null
          ? null
          : () => _runOrContinueShare(
              target: ContentShareContinuationTarget.circlePlacement,
              reason: AuthGateReason.generic,
              action: _openCirclePicker,
            ),
      onGroupTap: () => _runOrContinueShare(
        target: ContentShareContinuationTarget.groupChat,
        reason: AuthGateReason.sendMessage,
        action: () => _openRecipientPicker(ForwardRecipientPickerMode.groups),
      ),
      onMessageTap: () => _runOrContinueShare(
        target: ContentShareContinuationTarget.directMessage,
        reason: AuthGateReason.sendMessage,
        action: () => _openRecipientPicker(ForwardRecipientPickerMode.messages),
      ),
      onExternalShare: _shareExternal,
      journeyEventTracker: ref.read(journeyEventTrackerProvider),
    );
  }

  void _runOrContinueShare({
    required ContentShareContinuationTarget target,
    required AuthGateReason reason,
    required VoidCallback action,
    String? recipientId,
  }) {
    if (ref.read(authSessionControllerProvider).isAuthenticated) {
      action();
      return;
    }
    final accepted = ref
        .read(authContinuationProvider.notifier)
        .set(
          ShareContentContinuation(
            postId: widget.template.postId,
            target: target,
            recipientId: recipientId,
          ),
          ownerToken: 'content-share:${widget.template.postId}:${target.name}',
        );
    if (!accepted) {
      return;
    }
    unawaited(
      requireLogin(
        ref,
        context,
        reason,
        dismissFallback: AppRoutePaths.home,
        dismissPolicy: LoginDismissPolicy.safeFallback,
      ),
    );
  }

  void _scheduleContinuationResume({int remainingFrames = 30}) {
    if (_continuationResumeScheduled) {
      return;
    }
    _continuationResumeScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _continuationResumeScheduled = false;
      if (!mounted ||
          !ref.read(authSessionControllerProvider).isAuthenticated) {
        return;
      }
      if (!(ModalRoute.of(context)?.isCurrent ?? true)) {
        if (remainingFrames > 0) {
          _scheduleContinuationResume(remainingFrames: remainingFrames - 1);
        }
        return;
      }
      final pending = ref
          .read(authContinuationProvider.notifier)
          .take<ShareContentContinuation>();
      if (pending == null) {
        _retryRecentRecipients();
        return;
      }
      if (pending.postId != widget.template.postId) {
        ref.read(authContinuationProvider.notifier).set(pending);
        return;
      }
      _retryRecentRecipients();
      switch (pending.target) {
        case ContentShareContinuationTarget.recentRecipient:
          unawaited(_resumeRecentRecipient(pending.recipientId));
          return;
        case ContentShareContinuationTarget.circlePlacement:
          _openCirclePicker();
          return;
        case ContentShareContinuationTarget.groupChat:
          _openRecipientPicker(ForwardRecipientPickerMode.groups);
          return;
        case ContentShareContinuationTarget.directMessage:
          _openRecipientPicker(ForwardRecipientPickerMode.messages);
          return;
      }
    });
  }

  Future<void> _resumeRecentRecipient(String? recipientId) async {
    final targetId = recipientId?.trim() ?? '';
    if (targetId.isEmpty) {
      return;
    }
    try {
      var recipients = _recentRecipients;
      if (!recipients.any((recipient) => recipient.id == targetId)) {
        recipients = await _loadRecentRecipients();
        if (mounted) {
          setState(() {
            _recentFuture = Future<List<AppForwardRecipient>>.value(recipients);
          });
        }
      }
      AppForwardRecipient? matched;
      for (final recipient in recipients) {
        if (recipient.id == targetId) {
          matched = recipient;
          break;
        }
      }
      if (matched == null) {
        throw StateError(ChatText.forwardCardUnavailable);
      }
      await _shareToRecentRecipient(matched);
    } catch (error) {
      if (!mounted) {
        return;
      }
      await AppActionErrorFeedback.show(
        context,
        semantic: runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.sectionLoad,
          scope: UiErrorScope.section,
        ),
      );
    }
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
    final stopwatch = Stopwatch()..start();
    late final ForwardExternalShareResult result;
    try {
      result = await ref
          .read(forwardExternalShareServiceProvider)
          .share(payload: _payload, target: target);
    } catch (error) {
      stopwatch.stop();
      if (!mounted) {
        return;
      }
      await _trackExternalShare(
        target: target,
        result: 'failure',
        durationMs: stopwatch.elapsedMilliseconds,
        error: error,
      );
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
      stopwatch.stop();
      await _trackExternalShare(
        target: target,
        result: 'dismissed',
        durationMs: stopwatch.elapsedMilliseconds,
      );
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
    if (result.delivery == ForwardExternalShareDelivery.wechatCompleted) {
      try {
        await _complete(
          target == ForwardExternalShareTarget.wechatFriend
              ? 'wechat_friend'
              : 'wechat_moments',
          destinationKind: 'external_app',
          destination: target.name,
          providerReceiptId: result.requestId,
        );
      } catch (error) {
        stopwatch.stop();
        if (!mounted) {
          return;
        }
        await _trackExternalShare(
          target: target,
          result: 'failure',
          durationMs: stopwatch.elapsedMilliseconds,
          error: error,
        );
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
              await _complete(
                target == ForwardExternalShareTarget.wechatFriend
                    ? 'wechat_friend'
                    : 'wechat_moments',
                destinationKind: 'external_app',
                destination: target.name,
                providerReceiptId: result.requestId,
              );
            }
          },
        );
        return;
      }
    }
    stopwatch.stop();
    await _trackExternalShare(
      target: target,
      result: result.delivery == ForwardExternalShareDelivery.unavailable
          ? 'failure'
          : 'success',
      durationMs: stopwatch.elapsedMilliseconds,
    );
  }

  Future<void> _trackExternalShare({
    required ForwardExternalShareTarget target,
    required String result,
    required int durationMs,
    Object? error,
  }) {
    return ref
        .read(journeyEventTrackerProvider)
        .trackAction(
          journey: 'content_share',
          action: target.name,
          pageName: 'content_share_sheet',
          targetType: 'post',
          targetKey: widget.template.postId,
          error: error,
          payload: <String, Object?>{
            'result': result,
            'durationMs': durationMs,
          },
        );
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
              title: ChatText.shareInternalTitle,
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
                  label: ChatText.shareTargetGroup,
                  color: CupertinoDynamicColor.resolve(
                    CupertinoColors.systemOrange,
                    context,
                  ),
                  onPressed: widget.onGroupTap,
                ),
                _ShareTargetAction(
                  icon: CupertinoIcons.chat_bubble_2_fill,
                  label: ChatText.shareTargetMessage,
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
              title: ChatText.shareExternalTitle,
              color: primaryText,
            ),
            SizedBox(height: AppSpacing.containerSm),
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                children: <Widget>[
                  _ShareTargetAction(
                    icon: CupertinoIcons.chat_bubble_2_fill,
                    label: ChatText.forwardActionWechatFriend,
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
                    label: ChatText.forwardActionWechatMoments,
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
                          ? ChatText.shareActionMore
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
    final stopwatch = Stopwatch()..start();
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
    Object? completionError;
    if (result.success) {
      try {
        await widget.onActionCompleted?.call(result);
      } catch (error) {
        completionError = error;
      }
    }
    stopwatch.stop();
    await widget.journeyEventTracker?.trackAction(
      journey: 'content_share',
      action: action.id,
      pageName: 'content_share_sheet',
      targetType: 'post',
      targetKey: widget.template.postId,
      error: completionError ?? result.error,
      payload: <String, Object?>{
        'result': completionError != null
            ? 'failure'
            : result.dismissed
            ? 'dismissed'
            : result.success
            ? 'success'
            : 'failure',
        'durationMs': stopwatch.elapsedMilliseconds,
      },
    );
    if (completionError != null && mounted) {
      await AppActionErrorFeedback.show(
        context,
        semantic: runtimeErrorSemantic(
          context,
          error: completionError,
          category: UiErrorCategory.submit,
          scope: UiErrorScope.dialog,
        ),
        onAction: (retryAction) async {
          if (retryAction.type == UiErrorActionType.retry ||
              retryAction.type == UiErrorActionType.resubmit) {
            await widget.onActionCompleted?.call(result);
          }
        },
      );
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
