import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/design_system/chat/chat_conversation_avatar_tokens.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/app_toast.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/gathering_text_constants.dart';
import 'package:quwoquan_app/runtime/di/gathering_dependencies.dart'
    show gatheringCommandWriterProvider;
import 'package:quwoquan_app/runtime/di/runtime_observability_dependencies.dart'
    show exceptionTelemetryPortProvider;
import 'package:quwoquan_app/runtime/errors/ui_error_models.dart'
    show UiErrorTone;
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/domain/gathering_models.dart'
    show GatheringParticipationCommandInput;
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show
        AppMessage,
        AppMessageGatheringInvitation,
        AppMessageGatheringInvitationAction,
        AppMessageGatheringInvitationActionIntent,
        AppMessageGatheringInvitationStatus;

/// 通知收件箱内的 Gathering 邀请专卡（1对1 邀约与多人邀请共用）。
///
/// 只渲染披露安全的邀请快照（purpose/schedule/place 已由 Circle 按未加入
/// viewer 披露策略裁剪），accept/decline 直接携带消息 action intent 的
/// owner versions 打 Circle typed op——不本地推断版本、不半持久化状态；
/// 动作成功后由 [onResolved] 让收件箱刷新云端事实。
class GatheringInvitationInboxCard extends ConsumerStatefulWidget {
  const GatheringInvitationInboxCard({
    super.key,
    required this.message,
    required this.invitation,
    required this.onResolved,
    required this.fgPrimary,
    required this.fgSecondary,
    required this.backgroundColor,
  });

  final AppMessage message;
  final AppMessageGatheringInvitation invitation;

  /// accept/decline 成功后的收件箱收口（标记已读 + 刷新云端 inbox）。
  final Future<void> Function() onResolved;
  final Color fgPrimary;
  final Color fgSecondary;
  final Color backgroundColor;

  static Key acceptKeyFor(String messageId) =>
      ValueKey<String>('gathering-invitation-accept-$messageId');
  static Key declineKeyFor(String messageId) =>
      ValueKey<String>('gathering-invitation-decline-$messageId');

  @override
  ConsumerState<GatheringInvitationInboxCard> createState() =>
      _GatheringInvitationInboxCardState();
}

class _GatheringInvitationInboxCardState
    extends ConsumerState<GatheringInvitationInboxCard> {
  bool _submitting = false;

  AppMessageGatheringInvitationActionIntent? _intentFor(
    AppMessageGatheringInvitationAction action,
  ) {
    for (final intent in widget.invitation.actionIntents) {
      if (intent.action == action) {
        return intent;
      }
    }
    return null;
  }

  Future<void> _dispatch(AppMessageGatheringInvitationAction action) async {
    final intent = _intentFor(action);
    if (intent == null || _submitting) {
      return;
    }
    setState(() => _submitting = true);
    final writer = ref.read(gatheringCommandWriterProvider);
    final input = GatheringParticipationCommandInput(
      idempotencyKey:
          'invitation:${widget.message.messageId}:${action.wireName}',
      gatheringId: widget.invitation.gatheringId,
      expectedGatheringVersion: intent.expectedGatheringVersion,
      expectedParticipationVersion: intent.expectedParticipationVersion,
    );
    try {
      if (action == AppMessageGatheringInvitationAction.accept) {
        final result = await writer.acceptInvitation(input);
        await widget.onResolved();
        if (!mounted) return;
        context.push(AppRoutePaths.gatheringDetail(id: result.gatheringId));
      } else {
        await writer.declineInvitation(input);
        await widget.onResolved();
        if (!mounted) return;
        AppToast.show(context, GatheringText.invitationDeclinedFeedback);
      }
    } catch (error, stackTrace) {
      unawaited(
        ref
            .read(exceptionTelemetryPortProvider)
            .recordHandledException(
              source: 'circle.gathering_invitation.inbox_${action.wireName}',
              error: error,
              stackTrace: stackTrace,
            ),
      );
      if (mounted) {
        AppToast.show(
          context,
          GatheringText.invitationActionFailedToast,
          tone: UiErrorTone.caution,
        );
      }
    } finally {
      if (mounted) {
        setState(() => _submitting = false);
      }
    }
  }

  String get _scheduleLabel {
    final schedule = widget.invitation.schedule;
    final dateLabel = schedule.dateLabel?.trim() ?? '';
    if (dateLabel.isNotEmpty) {
      return dateLabel;
    }
    final startAt = schedule.startAt;
    if (startAt == null) {
      return '';
    }
    final local = startAt.toLocal();
    return '${local.month}月${local.day}日 '
        '${local.hour.toString().padLeft(2, '0')}:'
        '${local.minute.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    final invitation = widget.invitation;
    final pending =
        invitation.status == AppMessageGatheringInvitationStatus.pending;
    final place = invitation.place.coarsePlaceLabel?.trim() ?? '';
    final schedule = _scheduleLabel;
    final subtitle = <String>[
      if (schedule.isNotEmpty) schedule,
      if (place.isNotEmpty) place,
    ].join(' · ');
    return Container(
      key: ValueKey<String>(
        'gathering-invitation-card-${widget.message.messageId}',
      ),
      color: widget.backgroundColor,
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.sm + AppSpacing.xs,
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: <Widget>[
          Container(
            width: ChatConversationAvatarTokens.listSize,
            height: ChatConversationAvatarTokens.listSize,
            decoration: BoxDecoration(
              color: AppColors.iosAccent(context).withValues(alpha: 0.12),
              borderRadius: BorderRadius.circular(AppSpacing.radiusTen),
            ),
            child: Icon(
              CupertinoIcons.calendar_badge_plus,
              size: AppSpacing.twentyEight,
              color: AppColors.iosAccent(context),
            ),
          ),
          SizedBox(width: AppSpacing.intraGroupMd),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  '${GatheringText.invitationCardTitlePrefix}'
                  '${invitation.purposeSummary}',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: AppTypography.iosBody,
                    fontWeight: AppTypography.semiBold,
                    color: widget.fgPrimary,
                  ),
                ),
                if (subtitle.isNotEmpty) ...<Widget>[
                  SizedBox(height: AppSpacing.intraGroupXs),
                  Text(
                    subtitle,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: AppTypography.iosFootnote,
                      color: widget.fgSecondary,
                    ),
                  ),
                ],
              ],
            ),
          ),
          if (pending) ...<Widget>[
            SizedBox(width: AppSpacing.intraGroupSm),
            CupertinoButton(
              key: GatheringInvitationInboxCard.declineKeyFor(
                widget.message.messageId,
              ),
              padding: EdgeInsets.symmetric(
                horizontal: AppSpacing.containerSm,
                vertical: AppSpacing.intraGroupXs,
              ),
              minimumSize: Size.zero,
              onPressed: _submitting
                  ? null
                  : () => unawaited(
                      _dispatch(AppMessageGatheringInvitationAction.decline),
                    ),
              child: Text(
                GatheringText.invitationCardDecline,
                style: TextStyle(
                  fontSize: AppTypography.iosFootnote,
                  color: widget.fgSecondary,
                ),
              ),
            ),
            CupertinoButton(
              key: GatheringInvitationInboxCard.acceptKeyFor(
                widget.message.messageId,
              ),
              padding: EdgeInsets.symmetric(
                horizontal: AppSpacing.containerSm,
                vertical: AppSpacing.intraGroupXs,
              ),
              minimumSize: Size.zero,
              color: AppColors.iosAccent(context),
              borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
              onPressed: _submitting
                  ? null
                  : () => unawaited(
                      _dispatch(AppMessageGatheringInvitationAction.accept),
                    ),
              child: Text(
                GatheringText.invitationCardAccept,
                style: TextStyle(
                  fontSize: AppTypography.iosFootnote,
                  fontWeight: AppTypography.semiBold,
                  color: CupertinoColors.white,
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}
