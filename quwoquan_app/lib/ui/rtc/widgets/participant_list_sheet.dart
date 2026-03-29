import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/constants/settings_semantic_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/widgets/app_modal_surface.dart';
import 'package:quwoquan_app/ui/rtc/models/call_participant.dart';
import 'package:quwoquan_app/ui/rtc/providers/call_participants_provider.dart';

/// Bottom sheet displaying participant list with management controls.
class ParticipantListSheet extends ConsumerWidget {
  const ParticipantListSheet({
    super.key,
    required this.maxParticipants,
    this.onInviteMore,
  });

  final int maxParticipants;
  final VoidCallback? onInviteMore;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final participantsState = ref.watch(callParticipantsProvider);
    final participants = participantsState.participants;
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final outer = SettingsSemanticConstants.conversationSheetOuterHorizontalPadding;
    return AppBottomModalSurface(
      onDismiss: () => Navigator.of(context).pop(),
      backgroundColor:
          SettingsSemanticConstants.conversationSheetPanelBackground(isDark),
      maxHeightRatio: 0.6,
      contentPadding: EdgeInsets.fromLTRB(
        outer,
        0,
        outer,
        outer,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          _buildHeader(participants.length),
          Flexible(
            child: ListView.builder(
              shrinkWrap: true,
              padding: EdgeInsets.symmetric(horizontal: AppSpacing.md),
              itemCount: participants.length,
              itemBuilder: (context, index) {
                return _ParticipantRow(participant: participants[index]);
              },
            ),
          ),
          _buildInviteButton(context),
        ],
      ),
    );
  }

  Widget _buildHeader(int count) {
    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.sm,
      ),
      child: Row(
        children: [
          Text(
            '参与者',
            style: TextStyle(
              fontSize: AppTypography.lg,
              fontWeight: AppTypography.semiBold,
            ),
          ),
          SizedBox(width: AppSpacing.sm),
          Text(
            '$count / $maxParticipants',
            style: TextStyle(
              fontSize: AppTypography.sm,
              color: AppColors.overlayMedium,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildInviteButton(BuildContext context) {
    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.sm,
      ),
      child: SizedBox(
        width: double.infinity,
        height: AppSpacing.minInteractiveSize,
        child: CupertinoButton(
          color: AppColors.primaryColor,
          borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
          onPressed: onInviteMore,
          child: Text(
            '邀请更多',
            style: TextStyle(
              fontSize: AppTypography.md,
              fontWeight: AppTypography.medium,
              color: AppColors.white,
            ),
          ),
        ),
      ),
    );
  }
}

class _ParticipantRow extends StatelessWidget {
  const _ParticipantRow({required this.participant});

  final CallParticipant participant;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.symmetric(vertical: AppSpacing.sm),
      child: Row(
        children: [
          CircleAvatar(
            radius: AppSpacing.twenty,
            backgroundColor: AppColors.primaryColor.withValues(alpha: 0.2),
            backgroundImage: participant.avatarUrl != null
                ? NetworkImage(participant.avatarUrl!)
                : null,
            child: participant.avatarUrl == null
                ? Text(
                    participant.displayName.isNotEmpty
                        ? participant.displayName[0].toUpperCase()
                        : '?',
                    style: TextStyle(
                      fontSize: AppTypography.md,
                      fontWeight: AppTypography.semiBold,
                    ),
                  )
                : null,
          ),
          SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Flexible(
                      child: Text(
                        participant.displayName,
                        style: TextStyle(
                          fontSize: AppTypography.md,
                          fontWeight: AppTypography.medium,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    if (participant.isInitiator) ...[
                      SizedBox(width: AppSpacing.xs),
                      Container(
                        padding: EdgeInsets.symmetric(
                          horizontal: AppSpacing.xs * 2,
                          vertical: AppSpacing.one,
                        ),
                        decoration: BoxDecoration(
                          color: AppColors.primaryColor.withValues(alpha: 0.1),
                          borderRadius: BorderRadius.circular(AppSpacing.xs),
                        ),
                        child: Text(
                          '发起人',
                          style: TextStyle(
                            fontSize: AppTypography.xs,
                            color: AppColors.primaryColor,
                            fontWeight: AppTypography.medium,
                          ),
                        ),
                      ),
                    ],
                  ],
                ),
              ],
            ),
          ),
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (participant.isMuted)
                Icon(
                  CupertinoIcons.mic_off,
                  color: AppColors.error,
                  size: AppSpacing.iconSmall,
                ),
              SizedBox(width: AppSpacing.xs),
              if (!participant.isCameraOn)
                Icon(
                  CupertinoIcons.video_camera_solid,
                  color: AppColors.overlayLight,
                  size: AppSpacing.iconSmall,
                ),
            ],
          ),
        ],
      ),
    );
  }
}
