import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/ui/rtc/models/call_participant.dart';
import 'package:quwoquan_app/ui/rtc/widgets/participant_tile.dart';

/// Speaker-highlight layout (Teams style): large main speaker + bottom thumbnail row.
class SpeakerHighlightLayout extends StatelessWidget {
  const SpeakerHighlightLayout({
    super.key,
    required this.participants,
    required this.activeSpeaker,
    this.lockedSpeakerId,
    this.onTapThumbnail,
  });

  final List<CallParticipant> participants;
  final CallParticipant? activeSpeaker;
  final String? lockedSpeakerId;
  final ValueChanged<String>? onTapThumbnail;

  @override
  Widget build(BuildContext context) {
    final speaker = activeSpeaker ?? (participants.isNotEmpty ? participants.first : null);
    if (speaker == null) return const SizedBox.shrink();

    final thumbnails = participants
        .where((p) => p.userId != speaker.userId)
        .toList();

    return Column(
      children: [
        Expanded(
          flex: 7,
          child: Padding(
            padding: EdgeInsets.all(AppSpacing.xs),
            child: ParticipantTile(
              participant: speaker,
              isActiveSpeaker: true,
              borderRadius: BorderRadius.circular(AppSpacing.sm),
            ),
          ),
        ),
        if (thumbnails.isNotEmpty)
          SizedBox(
            height: AppSpacing.oneHundred,
            child: Padding(
              padding: EdgeInsets.symmetric(
                horizontal: AppSpacing.xs,
                vertical: AppSpacing.xs,
              ),
              child: ListView.separated(
                scrollDirection: Axis.horizontal,
                itemCount: thumbnails.length,
                separatorBuilder: (_, _) => SizedBox(width: AppSpacing.xs),
                itemBuilder: (context, index) {
                  final p = thumbnails[index];
                  final isLocked = p.userId == lockedSpeakerId;
                  return GestureDetector(
                    onTap: () => onTapThumbnail?.call(p.userId),
                    child: SizedBox(
                      width: AppSpacing.oneHundred,
                      child: Stack(
                        children: [
                          Positioned.fill(
                            child: ParticipantTile(
                              participant: p,
                              isActiveSpeaker: isLocked,
                              showName: true,
                              borderRadius:
                                  BorderRadius.circular(AppSpacing.sm),
                            ),
                          ),
                          if (isLocked)
                            Positioned(
                              top: AppSpacing.xs,
                              right: AppSpacing.xs,
                              child: Container(
                                width: AppSpacing.iconSmall,
                                height: AppSpacing.iconSmall,
                                decoration: BoxDecoration(
                                  color: AppColors.primaryColor,
                                  shape: BoxShape.circle,
                                ),
                                child: Icon(
                                  Icons.push_pin,
                                  color: AppColors.white,
                                  size: AppSpacing.xs * 3,
                                ),
                              ),
                            ),
                        ],
                      ),
                    ),
                  );
                },
              ),
            ),
          ),
      ],
    );
  }
}
