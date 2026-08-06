part of 'trip_journey_page.dart';

mixin _TripJourneyPageTemplateActions on ConsumerState<TripJourneyPage> {
  bool _creatingTemplate = false;

  Future<void> _composeTemplate(TripJourneySnapshot snapshot) async {
    if (_creatingTemplate) {
      return;
    }
    final draft = await _promptTemplateDraft(snapshot.plan.title);
    if (!mounted || draft == null) {
      return;
    }
    final intent = ref
        .read(tripTemplateCoordinatorProvider)
        .prepare(snapshot, title: draft.title, summary: draft.summary);
    await _createTemplate(intent);
  }

  Future<_TripTemplateDraft?> _promptTemplateDraft(String currentTitle) async {
    final titleController = TextEditingController(text: currentTitle.trim());
    final summaryController = TextEditingController();
    try {
      return await showAppCupertinoDialog<_TripTemplateDraft>(
        context: context,
        builder: (dialogContext) => CupertinoAlertDialog(
          title: const Text(TravelText.createTemplateTitle),
          content: Padding(
            padding: EdgeInsets.only(top: AppSpacing.intraGroupSm),
            child: Column(
              children: <Widget>[
                const Text(TravelText.createTemplateMessage),
                SizedBox(height: AppSpacing.containerSm),
                CupertinoTextField(
                  key: const ValueKey<String>('travel-template-title-field'),
                  controller: titleController,
                  autofocus: true,
                  placeholder: TravelText.templateTitleHint,
                  textInputAction: TextInputAction.next,
                ),
                SizedBox(height: AppSpacing.containerSm),
                CupertinoTextField(
                  key: const ValueKey<String>('travel-template-summary-field'),
                  controller: summaryController,
                  minLines: 2,
                  maxLines: 4,
                  placeholder: TravelText.templateSummaryHint,
                  textInputAction: TextInputAction.done,
                ),
              ],
            ),
          ),
          actions: <Widget>[
            CupertinoDialogAction(
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: const Text(FoundationText.cancel),
            ),
            CupertinoDialogAction(
              key: const ValueKey<String>('travel-template-confirm'),
              isDefaultAction: true,
              onPressed: () {
                final title = titleController.text.trim();
                if (title.isEmpty) {
                  return;
                }
                Navigator.of(dialogContext).pop(
                  _TripTemplateDraft(
                    title: title,
                    summary: summaryController.text.trim(),
                  ),
                );
              },
              child: const Text(CommunityText.done),
            ),
          ],
        ),
      );
    } finally {
      titleController.dispose();
      summaryController.dispose();
    }
  }

  Future<void> _createTemplate(TripTemplateCreateIntent intent) async {
    setState(() => _creatingTemplate = true);
    AppToast.show(context, TravelText.templateSaving);
    try {
      await ref.read(tripTemplateCoordinatorProvider).create(intent);
      if (!mounted) {
        return;
      }
      AppToast.dismiss();
      AppToast.show(context, TravelText.templateSaved);
      ref.invalidate(tripPlanTemplatesProvider);
    } catch (error) {
      if (!mounted) {
        return;
      }
      AppToast.dismiss();
      setState(() => _creatingTemplate = false);
      final semantic = ensureRetryUiErrorSemantic(
        runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.submit,
          scope: UiErrorScope.global,
          sourceRouteId: AppUiSurfaces.travelTimeline.routeId,
          sourceSurfaceId: AppUiSurfaces.travelTimeline.id,
          sourceOperationId:
              AppCloudOperationIds.travelTripPlanTemplateCreateTripPlanTemplate,
        ),
      );
      await AppActionErrorFeedback.show(
        context,
        semantic: semantic,
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await _createTemplate(intent);
          }
        },
      );
    } finally {
      if (mounted && _creatingTemplate) {
        setState(() => _creatingTemplate = false);
      }
    }
  }
}

final class _TripTemplateDraft {
  const _TripTemplateDraft({required this.title, required this.summary});

  final String title;
  final String summary;
}
