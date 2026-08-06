import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/travel/travel/trip_timeline_view/application/trip_journey_query.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/travel/travel/trip_guide_assignment/presentation/trip_guide_assignment_panel.dart';
import 'package:quwoquan_app/travel/travel/trip_map_view/presentation/trip_route_overview.dart';
import 'package:quwoquan_app/travel/travel/trip_moment/presentation/trip_moment_inbox_panel.dart';
import 'package:quwoquan_app/travel/travel/trip_timeline_view/presentation/trip_timeline_board.dart';
import 'package:quwoquan_app/ui/travel/travel_text_constants.dart';
import 'package:quwoquan_app/ui/travel/widgets/trip_item_semantics.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class TripJourneyOverview extends StatelessWidget {
  const TripJourneyOverview({
    super.key,
    required this.snapshot,
    this.onAddMoment,
    this.onOpenMap,
    this.onShare,
    this.onSaveTemplate,
    this.onRevisePlan,
    this.onTransitionPlan,
    this.transitionPlanLabel,
    this.onOpenItem,
    this.onOpenPost,
    this.onManageMoment,
    this.activePersonaId = '',
    this.onAdvanceGuideTask,
    this.onCreateGuideAssignment,
    this.onReassignGuideAssignment,
    this.guideAssigneeLabels = const <String, String>{},
    this.guideAssigneeLabelsPending = false,
  });

  final TripJourneySnapshot snapshot;
  final VoidCallback? onAddMoment;
  final VoidCallback? onOpenMap;
  final VoidCallback? onShare;
  final VoidCallback? onSaveTemplate;
  final VoidCallback? onRevisePlan;
  final VoidCallback? onTransitionPlan;
  final String? transitionPlanLabel;
  final ValueChanged<String>? onOpenItem;
  final ValueChanged<String>? onOpenPost;
  final ValueChanged<String>? onManageMoment;
  final String activePersonaId;
  final ValueChanged<TripGuideAssignment>? onAdvanceGuideTask;
  final VoidCallback? onCreateGuideAssignment;
  final ValueChanged<TripGuideAssignment>? onReassignGuideAssignment;
  final Map<String, String> guideAssigneeLabels;
  final bool guideAssigneeLabelsPending;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final canOrganizeAll =
        activePersonaId.isNotEmpty &&
        activePersonaId == snapshot.plan.organizerPersonaId;
    final manageableMomentIds = snapshot.moments.moments
        .where(
          (moment) =>
              moment.status == TripMomentStatus.active &&
              (canOrganizeAll ||
                  moment.attributionPersonaId == activePersonaId),
        )
        .map((moment) => moment.momentId)
        .toSet();
    final personalMoments =
        snapshot.moments.moments
            .where(
              (moment) =>
                  moment.status == TripMomentStatus.active &&
                  moment.attributionPersonaId == activePersonaId &&
                  (moment.visibility == TripMomentVisibility.personal ||
                      moment.assignmentStatus !=
                          TripMomentAssignmentStatus.confirmed),
            )
            .toList(growable: false)
          ..sort((left, right) => right.capturedAt.compareTo(left.capturedAt));
    return LayoutBuilder(
      builder: (context, constraints) {
        final isExpanded =
            constraints.maxWidth >= AppSpacing.expandedBreakpoint;
        final timeline = TripTimelineBoard(
          timeline: snapshot.timeline,
          onOpenItem: onOpenItem,
          onOpenPost: onOpenPost,
          onManageMoment: onManageMoment,
          manageableMomentIds: manageableMomentIds,
        );
        final route = TripRouteOverview(map: snapshot.map);
        return SingleChildScrollView(
          padding: EdgeInsets.all(AppSpacing.containerMd),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                snapshot.plan.title,
                style: TextStyle(
                  color: colors.onSurface,
                  fontSize: AppTypography.iosTitle2,
                  fontWeight: AppTypography.bold,
                ),
              ),
              SizedBox(height: AppSpacing.intraGroupXs),
              Text(
                '${tripStatusLabel(snapshot.plan.status)} · '
                '${TravelText.revisionPrefix} ${snapshot.plan.currentRevisionNumber}',
                style: TextStyle(
                  color: colors.onSurfaceVariant,
                  fontSize: AppTypography.secondary,
                ),
              ),
              SizedBox(height: AppSpacing.containerMd),
              _JourneyMetrics(snapshot: snapshot),
              if (snapshot.guideAssignments.assignments.isNotEmpty ||
                  onCreateGuideAssignment != null) ...[
                SizedBox(height: AppSpacing.containerMd),
                TripGuideAssignmentPanel(
                  plan: snapshot.plan,
                  assignments: snapshot.guideAssignments.assignments,
                  activePersonaId: activePersonaId,
                  onAdvance: onAdvanceGuideTask,
                  onCreate: onCreateGuideAssignment,
                  onReassign: onReassignGuideAssignment,
                  assigneeLabels: guideAssigneeLabels,
                  assigneeLabelsPending: guideAssigneeLabelsPending,
                ),
              ],
              if (snapshot.timeline.revisionChangeReason.trim().isNotEmpty) ...[
                SizedBox(height: AppSpacing.containerMd),
                _RevisionCallout(snapshot: snapshot),
              ],
              if (personalMoments.isNotEmpty && onManageMoment != null) ...[
                SizedBox(height: AppSpacing.containerMd),
                TripMomentInboxPanel(
                  moments: personalMoments,
                  onManage: onManageMoment!,
                ),
              ],
              SizedBox(height: AppSpacing.containerMd),
              Wrap(
                spacing: AppSpacing.containerSm,
                runSpacing: AppSpacing.containerSm,
                children: [
                  if (onRevisePlan != null)
                    _JourneyAction(
                      icon: CupertinoIcons.pencil,
                      label: TravelText.revisePlan,
                      onPressed: onRevisePlan,
                    ),
                  if (onTransitionPlan != null && transitionPlanLabel != null)
                    _JourneyAction(
                      icon: CupertinoIcons.flag,
                      label: transitionPlanLabel!,
                      onPressed: onTransitionPlan,
                    ),
                  _JourneyAction(
                    icon: CupertinoIcons.photo_camera,
                    label: TravelText.addMoment,
                    onPressed: onAddMoment,
                  ),
                  _JourneyAction(
                    icon: CupertinoIcons.map,
                    label: TravelText.openMap,
                    onPressed: onOpenMap,
                  ),
                  _JourneyAction(
                    icon: CupertinoIcons.share,
                    label: TravelText.shareJourney,
                    onPressed: onShare,
                  ),
                  if (onSaveTemplate != null)
                    _JourneyAction(
                      icon: CupertinoIcons.square_stack_3d_up,
                      label: TravelText.saveAsTemplate,
                      onPressed: onSaveTemplate,
                    ),
                ],
              ),
              SizedBox(height: AppSpacing.interGroupLg),
              if (isExpanded)
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(flex: 3, child: timeline),
                    SizedBox(width: AppSpacing.interGroupMd),
                    Expanded(flex: 2, child: route),
                  ],
                )
              else ...[
                timeline,
                SizedBox(height: AppSpacing.interGroupMd),
                route,
              ],
            ],
          ),
        );
      },
    );
  }
}

final class _JourneyMetrics extends StatelessWidget {
  const _JourneyMetrics({required this.snapshot});

  final TripJourneySnapshot snapshot;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: AppSpacing.containerSm,
      runSpacing: AppSpacing.containerSm,
      children: [
        _Metric(
          label: TravelText.members,
          value: snapshot.memberships.memberships.length,
        ),
        _Metric(
          label: TravelText.moments,
          value: snapshot.moments.moments.length,
        ),
        _Metric(
          label: TravelText.linkedPosts,
          value: snapshot.contentLinks.links.length,
        ),
        _Metric(
          label: TravelText.guideTasks,
          value: snapshot.guideAssignments.assignments.length,
        ),
      ],
    );
  }
}

final class _Metric extends StatelessWidget {
  const _Metric({required this.label, required this.value});

  final String label;
  final int value;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.containerSm,
      ),
      decoration: BoxDecoration(
        color: colors.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
      ),
      child: Text(
        '$label $value',
        style: TextStyle(
          color: colors.onSurface,
          fontSize: AppTypography.secondary,
          fontWeight: AppTypography.medium,
        ),
      ),
    );
  }
}

final class _RevisionCallout extends StatelessWidget {
  const _RevisionCallout({required this.snapshot});

  final TripJourneySnapshot snapshot;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: colors.tertiaryContainer,
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
      ),
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerMd),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(
              CupertinoIcons.bell,
              color: colors.onTertiaryContainer,
              size: AppSpacing.iconMedium,
            ),
            SizedBox(width: AppSpacing.containerSm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    TravelText.planChanged,
                    style: TextStyle(
                      color: colors.onTertiaryContainer,
                      fontSize: AppTypography.body,
                      fontWeight: AppTypography.semiBold,
                    ),
                  ),
                  SizedBox(height: AppSpacing.intraGroupXs),
                  Text(
                    snapshot.timeline.revisionChangeReason,
                    style: TextStyle(
                      color: colors.onTertiaryContainer,
                      fontSize: AppTypography.secondary,
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

final class _JourneyAction extends StatelessWidget {
  const _JourneyAction({
    required this.icon,
    required this.label,
    required this.onPressed,
  });

  final IconData icon;
  final String label;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    return OutlinedButton.icon(
      onPressed: onPressed,
      icon: Icon(icon, size: AppSpacing.iconMedium),
      label: Text(label),
    );
  }
}
