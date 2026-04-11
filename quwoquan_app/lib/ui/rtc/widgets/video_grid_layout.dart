import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/ui/rtc/models/call_participant.dart';
import 'package:quwoquan_app/ui/rtc/widgets/participant_tile.dart';

/// FaceTime-style adaptive grid layout with pagination for >16 participants.
class VideoGridLayout extends StatelessWidget {
  const VideoGridLayout({
    super.key,
    required this.participants,
    this.activeSpeakerId,
  });

  final List<CallParticipant> participants;
  final String? activeSpeakerId;

  @override
  Widget build(BuildContext context) {
    if (participants.isEmpty) return const SizedBox.shrink();

    if (participants.length <= 16) {
      return _buildGrid(participants);
    }

    final pageCount = (participants.length / 16).ceil();
    return PageView.builder(
      itemCount: pageCount,
      itemBuilder: (context, pageIndex) {
        final start = pageIndex * 16;
        final end = math.min(start + 16, participants.length);
        final pageParticipants = participants.sublist(start, end);
        return _buildGrid(pageParticipants);
      },
    );
  }

  Widget _buildGrid(List<CallParticipant> items) {
    final config = _gridConfig(items.length);

    return Padding(
      padding: EdgeInsets.all(AppSpacing.xs),
      child: GridView.builder(
        physics: const NeverScrollableScrollPhysics(),
        shrinkWrap: true,
        gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
          crossAxisCount: config.columns,
          mainAxisSpacing: AppSpacing.xs,
          crossAxisSpacing: AppSpacing.xs,
          childAspectRatio: config.aspectRatio,
        ),
        itemCount: items.length,
        itemBuilder: (context, index) {
          final p = items[index];
          return ParticipantTile(
            participant: p,
            isActiveSpeaker: p.userId == activeSpeakerId,
            borderRadius: BorderRadius.circular(AppSpacing.sm),
          );
        },
      ),
    );
  }

  _GridConfig _gridConfig(int count) {
    return switch (count) {
      1 => const _GridConfig(columns: 1, aspectRatio: 3 / 4),
      2 => const _GridConfig(columns: 1, aspectRatio: 4 / 3),
      3 || 4 => const _GridConfig(columns: 2, aspectRatio: 3 / 4),
      5 || 6 => const _GridConfig(columns: 2, aspectRatio: 1.0),
      7 || 8 || 9 => const _GridConfig(columns: 3, aspectRatio: 3 / 4),
      _ => const _GridConfig(columns: 4, aspectRatio: 3 / 4),
    };
  }
}

class _GridConfig {
  final int columns;
  final double aspectRatio;

  const _GridConfig({required this.columns, required this.aspectRatio});
}
