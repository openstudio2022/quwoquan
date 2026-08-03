part of 'trip_journey_page.dart';

mixin _TripJourneyPageGuideAssignmentActions on ConsumerState<TripJourneyPage> {
  String? _puttingGuideTaskKey;

  Future<void> _composeGuideAssignment(
    TripJourneySnapshot snapshot,
    String actorPersonaId,
  ) async {
    final assignee = await _selectGuideAssignee(snapshot);
    if (!mounted || assignee == null) {
      return;
    }
    final role = await _selectGuideRole();
    if (!mounted || role == null) {
      return;
    }
    final taskKind = await _selectGuideTaskKind();
    if (!mounted || taskKind == null) {
      return;
    }
    final title = await _promptGuideTaskTitle();
    if (!mounted || title == null) {
      return;
    }
    final intent = ref
        .read(tripGuideAssignmentCoordinatorProvider)
        .prepareCreate(
          snapshot: snapshot,
          actorPersonaId: actorPersonaId,
          assigneePersonaId: assignee.personaId,
          role: role,
          taskKind: taskKind,
          title: title,
        );
    await _putGuideAssignment(intent);
  }

  Future<void> _reassignGuideAssignment(
    TripJourneySnapshot snapshot,
    String actorPersonaId,
    TripGuideAssignment assignment,
  ) async {
    final assignee = await _selectGuideAssignee(snapshot);
    if (!mounted || assignee == null) {
      return;
    }
    final intent = ref
        .read(tripGuideAssignmentCoordinatorProvider)
        .prepareReassign(
          snapshot: snapshot,
          actorPersonaId: actorPersonaId,
          assignment: assignment,
          assigneePersonaId: assignee.personaId,
        );
    await _putGuideAssignment(intent);
  }

  Future<_GuideAssigneeOption?> _selectGuideAssignee(
    TripJourneySnapshot snapshot,
  ) async {
    AppToast.show(context, TravelText.guideMembersLoading);
    try {
      final labels = await ref.read(
        tripGuideAssigneeLabelsProvider(snapshot.plan.tripId).future,
      );
      final memberships = snapshot.memberships.memberships
          .where((membership) => membership.state == TripMembershipState.active)
          .toList(growable: false);
      final options = memberships
          .map((membership) {
            final displayName = labels[membership.personaId]?.trim() ?? '';
            if (displayName.isEmpty) {
              throw StateError('Trip member has no public display label');
            }
            return _GuideAssigneeOption(
              personaId: membership.personaId,
              label: '$displayName · ${_membershipRoleLabel(membership.role)}',
            );
          })
          .toList(growable: false);
      AppToast.dismiss();
      options.sort((left, right) => left.label.compareTo(right.label));
      if (options.isEmpty) {
        throw StateError('Trip has no active member to assign');
      }
      if (!mounted) {
        return null;
      }
      return showAppActionSheet<_GuideAssigneeOption>(
        context,
        title: TravelText.guideSelectAssignee,
        sections: <AppActionSheetSection<_GuideAssigneeOption>>[
          AppActionSheetSection<_GuideAssigneeOption>(
            items: <AppActionSheetItem<_GuideAssigneeOption>>[
              for (final option in options)
                AppActionSheetItem<_GuideAssigneeOption>(
                  value: option,
                  label: option.label,
                  icon: CupertinoIcons.person,
                ),
            ],
          ),
        ],
      );
    } catch (error) {
      AppToast.dismiss();
      if (!mounted) {
        return null;
      }
      final semantic = ensureRetryUiErrorSemantic(
        runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.pageLoad,
          scope: UiErrorScope.global,
          sourceRouteId: AppUiSurfaces.travelTimeline.routeId,
          sourceSurfaceId: AppUiSurfaces.travelTimeline.id,
          sourceOperationId:
              AppCloudOperationIds.userUserAccountGetPersonaProfile,
        ),
      );
      await AppActionErrorFeedback.show(context, semantic: semantic);
      return null;
    }
  }

  Future<TripGuideRole?> _selectGuideRole() {
    return showAppActionSheet<TripGuideRole>(
      context,
      title: TravelText.guideSelectRole,
      sections: const <AppActionSheetSection<TripGuideRole>>[
        AppActionSheetSection<TripGuideRole>(
          items: <AppActionSheetItem<TripGuideRole>>[
            AppActionSheetItem<TripGuideRole>(
              value: TripGuideRole.leader,
              label: TravelText.guideRoleLeader,
            ),
            AppActionSheetItem<TripGuideRole>(
              value: TripGuideRole.assistantGuide,
              label: TravelText.guideRoleAssistant,
            ),
            AppActionSheetItem<TripGuideRole>(
              value: TripGuideRole.licensedGuide,
              label: TravelText.guideRoleLicensed,
            ),
            AppActionSheetItem<TripGuideRole>(
              value: TripGuideRole.localExpert,
              label: TravelText.guideRoleLocalExpert,
            ),
          ],
        ),
      ],
    );
  }

  Future<TripGuideTaskKind?> _selectGuideTaskKind() {
    return showAppActionSheet<TripGuideTaskKind>(
      context,
      title: TravelText.guideSelectTaskKind,
      sections: const <AppActionSheetSection<TripGuideTaskKind>>[
        AppActionSheetSection<TripGuideTaskKind>(
          items: <AppActionSheetItem<TripGuideTaskKind>>[
            AppActionSheetItem<TripGuideTaskKind>(
              value: TripGuideTaskKind.collection,
              label: TravelText.guideTaskCollection,
            ),
            AppActionSheetItem<TripGuideTaskKind>(
              value: TripGuideTaskKind.briefing,
              label: TravelText.guideTaskBriefing,
            ),
            AppActionSheetItem<TripGuideTaskKind>(
              value: TripGuideTaskKind.routeGuidance,
              label: TravelText.guideTaskRoute,
            ),
            AppActionSheetItem<TripGuideTaskKind>(
              value: TripGuideTaskKind.commentary,
              label: TravelText.guideTaskCommentary,
            ),
            AppActionSheetItem<TripGuideTaskKind>(
              value: TripGuideTaskKind.generalSupport,
              label: TravelText.guideTaskSupport,
            ),
          ],
        ),
      ],
    );
  }

  Future<String?> _promptGuideTaskTitle() async {
    final controller = TextEditingController();
    try {
      final title = await showAppCupertinoDialog<String>(
        context: context,
        builder: (dialogContext) => CupertinoAlertDialog(
          title: const Text(TravelText.guideTaskTitle),
          content: Padding(
            padding: EdgeInsets.only(top: AppSpacing.intraGroupSm),
            child: CupertinoTextField(
              key: const ValueKey<String>('travel-guide-task-title-field'),
              controller: controller,
              autofocus: true,
              placeholder: TravelText.guideTaskTitleHint,
              textInputAction: TextInputAction.done,
              onSubmitted: (value) =>
                  Navigator.of(dialogContext).pop(value.trim()),
            ),
          ),
          actions: <Widget>[
            CupertinoDialogAction(
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: const Text(FoundationText.cancel),
            ),
            CupertinoDialogAction(
              isDefaultAction: true,
              onPressed: () =>
                  Navigator.of(dialogContext).pop(controller.text.trim()),
              child: const Text(CommunityText.done),
            ),
          ],
        ),
      );
      final normalized = title?.trim() ?? '';
      return normalized.isEmpty ? null : normalized;
    } finally {
      controller.dispose();
    }
  }

  Future<void> _putGuideAssignment(TripGuidePutIntent intent) async {
    setState(() => _puttingGuideTaskKey = intent.command.taskKey);
    AppToast.show(context, TravelText.guideAssignmentSaving);
    try {
      await ref.read(tripGuideAssignmentCoordinatorProvider).put(intent);
      if (!mounted) {
        return;
      }
      AppToast.dismiss();
      AppToast.show(context, TravelText.guideAssignmentSaved);
      ref.invalidate(tripJourneySnapshotProvider(widget.tripId));
    } catch (error) {
      if (!mounted) {
        return;
      }
      AppToast.dismiss();
      setState(() => _puttingGuideTaskKey = null);
      final semantic = ensureRetryUiErrorSemantic(
        runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.submit,
          scope: UiErrorScope.global,
          sourceRouteId: AppUiSurfaces.travelTimeline.routeId,
          sourceSurfaceId: AppUiSurfaces.travelTimeline.id,
          sourceOperationId: AppCloudOperationIds
              .travelTripGuideAssignmentPutTripGuideAssignment,
        ),
      );
      await AppActionErrorFeedback.show(
        context,
        semantic: semantic,
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await _putGuideAssignment(intent);
          }
        },
      );
    } finally {
      if (mounted && _puttingGuideTaskKey != null) {
        setState(() => _puttingGuideTaskKey = null);
      }
    }
  }
}

final class _GuideAssigneeOption {
  const _GuideAssigneeOption({required this.personaId, required this.label});

  final String personaId;
  final String label;
}

String _membershipRoleLabel(TripMembershipRole role) => switch (role) {
  TripMembershipRole.organizer => TravelText.membershipOrganizer,
  TripMembershipRole.participant => TravelText.membershipParticipant,
  TripMembershipRole.leader => TravelText.membershipLeader,
  TripMembershipRole.assistantGuide => TravelText.membershipAssistantGuide,
  TripMembershipRole.guide => TravelText.membershipGuide,
  TripMembershipRole.localExpert => TravelText.membershipLocalExpert,
};
