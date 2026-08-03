import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/application/travel/trip_guide_assignment_coordinator.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/ui/travel/travel_text_constants.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class TripGuideAssignmentPanel extends StatelessWidget {
  const TripGuideAssignmentPanel({
    super.key,
    required this.plan,
    required this.assignments,
    required this.activePersonaId,
    this.onAdvance,
    this.onCreate,
    this.onReassign,
    this.assigneeLabels = const <String, String>{},
    this.assigneeLabelsPending = false,
  });

  final TripPlanSlice plan;
  final List<TripGuideAssignment> assignments;
  final String activePersonaId;
  final ValueChanged<TripGuideAssignment>? onAdvance;
  final VoidCallback? onCreate;
  final ValueChanged<TripGuideAssignment>? onReassign;
  final Map<String, String> assigneeLabels;
  final bool assigneeLabelsPending;

  @override
  Widget build(BuildContext context) {
    if (assignments.isEmpty && onCreate == null) {
      return const SizedBox.shrink();
    }
    final colors = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Row(
          children: <Widget>[
            Expanded(
              child: Text(
                TravelText.guideTasks,
                style: TextStyle(
                  color: colors.onSurface,
                  fontSize: AppTypography.sectionTitle,
                  fontWeight: AppTypography.semiBold,
                ),
              ),
            ),
            if (onCreate != null)
              FilledButton.tonalIcon(
                onPressed: onCreate,
                icon: const Icon(CupertinoIcons.person_add),
                label: const Text(TravelText.guideCreateTask),
              ),
          ],
        ),
        SizedBox(height: AppSpacing.intraGroupSm),
        for (final assignment in assignments) ...[
          _GuideTaskCard(
            assignment: assignment,
            canAdvance: _canAdvance(assignment),
            onAdvance: onAdvance == null ? null : () => onAdvance!(assignment),
            canReassign: _canReassign(assignment),
            onReassign: onReassign == null
                ? null
                : () => onReassign!(assignment),
            assigneeLabel: assigneeLabels[assignment.assigneePersonaId],
            assigneeLabelPending: assigneeLabelsPending,
          ),
          SizedBox(height: AppSpacing.containerSm),
        ],
      ],
    );
  }

  bool _canAdvance(TripGuideAssignment assignment) {
    final personaId = activePersonaId.trim();
    return personaId.isNotEmpty &&
        (personaId == assignment.assigneePersonaId ||
            personaId == plan.organizerPersonaId) &&
        nextTripGuideAssignmentStatus(assignment.status) != null;
  }

  bool _canReassign(TripGuideAssignment assignment) {
    return activePersonaId.trim() == plan.organizerPersonaId &&
        assignment.status != TripGuideAssignmentStatus.completed;
  }
}

final class _GuideTaskCard extends StatelessWidget {
  const _GuideTaskCard({
    required this.assignment,
    required this.canAdvance,
    required this.onAdvance,
    required this.canReassign,
    required this.onReassign,
    required this.assigneeLabel,
    required this.assigneeLabelPending,
  });

  final TripGuideAssignment assignment;
  final bool canAdvance;
  final VoidCallback? onAdvance;
  final bool canReassign;
  final VoidCallback? onReassign;
  final String? assigneeLabel;
  final bool assigneeLabelPending;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final dueAt = assignment.dueAt?.toLocal();
    return DecoratedBox(
      decoration: BoxDecoration(
        color: colors.surfaceContainerLow,
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
        border: Border.all(color: colors.outlineVariant),
      ),
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerMd),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Text(
              assignment.title,
              style: TextStyle(
                color: colors.onSurface,
                fontSize: AppTypography.body,
                fontWeight: AppTypography.semiBold,
              ),
            ),
            SizedBox(height: AppSpacing.intraGroupXs),
            Text(
              '${TravelText.guideAssigneePrefix} '
              '${_assigneeDisplayLabel()}',
              style: TextStyle(
                color: colors.onSurfaceVariant,
                fontSize: AppTypography.secondary,
              ),
            ),
            SizedBox(height: AppSpacing.intraGroupXs),
            Wrap(
              spacing: AppSpacing.intraGroupSm,
              runSpacing: AppSpacing.intraGroupXs,
              children: <Widget>[
                _GuideBadge(label: _guideRoleLabel(assignment.role)),
                _GuideBadge(label: _guideTaskLabel(assignment.taskKind)),
                _GuideBadge(label: _guideStatusLabel(assignment.status)),
                if (assignment.publicQualificationPersonaId != null)
                  const _GuideBadge(
                    label: TravelText.guideQualificationPublic,
                    icon: CupertinoIcons.checkmark_seal,
                  ),
              ],
            ),
            if (dueAt != null) ...[
              SizedBox(height: AppSpacing.intraGroupSm),
              Text(
                '${TravelText.guideDuePrefix} '
                '${MaterialLocalizations.of(context).formatCompactDate(dueAt)} '
                '${MaterialLocalizations.of(context).formatTimeOfDay(TimeOfDay.fromDateTime(dueAt))}',
                style: TextStyle(
                  color: colors.onSurfaceVariant,
                  fontSize: AppTypography.secondary,
                ),
              ),
            ],
            if ((canReassign && onReassign != null) ||
                (canAdvance && onAdvance != null)) ...[
              SizedBox(height: AppSpacing.containerSm),
              Align(
                alignment: AlignmentDirectional.centerEnd,
                child: Wrap(
                  spacing: AppSpacing.containerSm,
                  children: <Widget>[
                    if (canReassign && onReassign != null)
                      TextButton.icon(
                        onPressed: onReassign,
                        icon: const Icon(CupertinoIcons.person_2),
                        label: const Text(TravelText.guideReassignTask),
                      ),
                    if (canAdvance && onAdvance != null)
                      FilledButton.tonal(
                        onPressed: onAdvance,
                        child: Text(_guideActionLabel(assignment.status)),
                      ),
                  ],
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  String _assigneeDisplayLabel() {
    final label = assigneeLabel?.trim() ?? '';
    if (label.isNotEmpty) {
      return label;
    }
    return assigneeLabelPending
        ? TravelText.guideAssigneeLoading
        : TravelText.guideAssigneeUnavailable;
  }
}

final class _GuideBadge extends StatelessWidget {
  const _GuideBadge({required this.label, this.icon});

  final String label;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.intraGroupXs,
      ),
      decoration: BoxDecoration(
        color: colors.secondaryContainer,
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          if (icon != null) ...[
            Icon(
              icon,
              color: colors.onSecondaryContainer,
              size: AppSpacing.iconSmall,
            ),
            SizedBox(width: AppSpacing.intraGroupXs),
          ],
          Text(
            label,
            style: TextStyle(
              color: colors.onSecondaryContainer,
              fontSize: AppTypography.caption,
            ),
          ),
        ],
      ),
    );
  }
}

String _guideRoleLabel(TripGuideRole role) => switch (role) {
  TripGuideRole.leader => TravelText.guideRoleLeader,
  TripGuideRole.assistantGuide => TravelText.guideRoleAssistant,
  TripGuideRole.licensedGuide => TravelText.guideRoleLicensed,
  TripGuideRole.localExpert => TravelText.guideRoleLocalExpert,
};

String _guideTaskLabel(TripGuideTaskKind kind) => switch (kind) {
  TripGuideTaskKind.collection => TravelText.guideTaskCollection,
  TripGuideTaskKind.briefing => TravelText.guideTaskBriefing,
  TripGuideTaskKind.routeGuidance => TravelText.guideTaskRoute,
  TripGuideTaskKind.commentary => TravelText.guideTaskCommentary,
  TripGuideTaskKind.generalSupport => TravelText.guideTaskSupport,
};

String _guideStatusLabel(TripGuideAssignmentStatus status) => switch (status) {
  TripGuideAssignmentStatus.assigned => TravelText.guideStatusAssigned,
  TripGuideAssignmentStatus.accepted => TravelText.guideStatusAccepted,
  TripGuideAssignmentStatus.inProgress => TravelText.guideStatusInProgress,
  TripGuideAssignmentStatus.completed => TravelText.guideStatusCompleted,
  TripGuideAssignmentStatus.cancelled => TravelText.guideStatusCancelled,
};

String _guideActionLabel(TripGuideAssignmentStatus status) => switch (status) {
  TripGuideAssignmentStatus.assigned => TravelText.guideActionAccept,
  TripGuideAssignmentStatus.accepted => TravelText.guideActionStart,
  TripGuideAssignmentStatus.inProgress => TravelText.guideActionComplete,
  TripGuideAssignmentStatus.completed ||
  TripGuideAssignmentStatus.cancelled => TravelText.guideStatusCompleted,
};
