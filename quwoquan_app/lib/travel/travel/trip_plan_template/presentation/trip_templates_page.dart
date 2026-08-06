import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/travel/travel/trip_plan/application/trip_plan_creation_coordinator.dart';
import 'package:quwoquan_app/travel/travel/trip_plan_template/application/trip_template_coordinator.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/errors/runtime_error_display.dart';
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/widgets/app_request_feedback.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/core/widgets/app_modal_presenter.dart';
import 'package:quwoquan_app/core/widgets/error_states/app_error_states.dart';
import 'package:quwoquan_app/ui/travel/travel_text_constants.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class TripTemplatesPage extends ConsumerStatefulWidget {
  const TripTemplatesPage({
    super.key,
    required this.onBack,
    required this.onOpenTrip,
  });

  final VoidCallback onBack;
  final ValueChanged<String> onOpenTrip;

  @override
  ConsumerState<TripTemplatesPage> createState() => _TripTemplatesPageState();
}

final class _TripTemplatesPageState extends ConsumerState<TripTemplatesPage> {
  String? _busyTemplateId;

  @override
  Widget build(BuildContext context) {
    final templates = ref.watch(tripPlanTemplatesProvider);
    return AppScaffold(
      navigationBar: AppNavigationBar(
        leading: AppNavigationBarIconButton(
          icon: CupertinoIcons.back,
          onPressed: widget.onBack,
        ),
        middle: const Text(TravelText.templatesTitle),
      ),
      child: SafeArea(
        child: templates.when(
          loading: AppRequestFeedback.page,
          data: (slice) => slice.templates.isEmpty
              ? const _EmptyTemplates()
              : ListView.separated(
                  padding: EdgeInsets.all(AppSpacing.containerMd),
                  itemCount: slice.templates.length,
                  separatorBuilder: (_, _) =>
                      SizedBox(height: AppSpacing.containerMd),
                  itemBuilder: (context, index) {
                    final template = slice.templates[index];
                    return _TemplateCard(
                      template: template,
                      busy: _busyTemplateId == template.id,
                      onEdit: _busyTemplateId == null
                          ? () => _editTemplate(template)
                          : null,
                      onUse: _busyTemplateId == null
                          ? () => _createFromTemplate(template)
                          : null,
                    );
                  },
                ),
          error: (error, _) => AppPageErrorState(
            semantic: ensureRetryUiErrorSemantic(
              runtimeErrorSemantic(
                context,
                error: error,
                category: UiErrorCategory.pageLoad,
                scope: UiErrorScope.page,
                sourceRouteId: AppUiSurfaces.travelTemplates.routeId,
                sourceSurfaceId: AppUiSurfaces.travelTemplates.id,
                sourceOperationId: AppCloudOperationIds
                    .travelTripPlanTemplateListTripPlanTemplates,
              ),
            ),
            onRecovery: _recoverTemplates,
          ),
        ),
      ),
    );
  }

  Future<UiRecoveryOutcome> _recoverTemplates(UiErrorAction action) async {
    if (action.type != UiErrorActionType.retry &&
        action.type != UiErrorActionType.resubmit) {
      return UiRecoveryOutcome.cancelled;
    }
    try {
      ref.invalidate(tripPlanTemplatesProvider);
      await ref.read(tripPlanTemplatesProvider.future);
      return mounted
          ? UiRecoveryOutcome.recovered
          : UiRecoveryOutcome.superseded;
    } catch (_) {
      return mounted
          ? UiRecoveryOutcome.stillBlocked
          : UiRecoveryOutcome.superseded;
    }
  }

  Future<void> _createFromTemplate(TripPlanTemplate template) async {
    final intent = ref
        .read(tripPlanCreationCoordinatorProvider)
        .prepareFromTemplate(templateId: template.id);
    await _submitTemplateIntent(template, intent);
  }

  Future<void> _editTemplate(TripPlanTemplate template) async {
    final draft = await _promptTemplateRevision(template);
    if (!mounted || draft == null) {
      return;
    }
    final intent = ref
        .read(tripTemplateCoordinatorProvider)
        .prepareRevision(template, title: draft.title, summary: draft.summary);
    await _submitTemplateRevision(template, intent);
  }

  Future<_TemplateRevisionDraft?> _promptTemplateRevision(
    TripPlanTemplate template,
  ) async {
    final titleController = TextEditingController(text: template.title);
    final summaryController = TextEditingController(text: template.summary);
    try {
      return await showAppCupertinoDialog<_TemplateRevisionDraft>(
        context: context,
        builder: (dialogContext) => StatefulBuilder(
          builder: (context, setDialogState) {
            final title = titleController.text.trim();
            return CupertinoAlertDialog(
              title: const Text(TravelText.editTemplateTitle),
              content: Padding(
                padding: EdgeInsets.only(top: AppSpacing.intraGroupSm),
                child: Column(
                  children: <Widget>[
                    const Text(TravelText.editTemplateMessage),
                    SizedBox(height: AppSpacing.containerSm),
                    CupertinoTextField(
                      key: const ValueKey<String>(
                        'travel-template-edit-title-field',
                      ),
                      controller: titleController,
                      autofocus: true,
                      placeholder: TravelText.templateTitleHint,
                      textInputAction: TextInputAction.next,
                      onChanged: (_) => setDialogState(() {}),
                    ),
                    SizedBox(height: AppSpacing.containerSm),
                    CupertinoTextField(
                      key: const ValueKey<String>(
                        'travel-template-edit-summary-field',
                      ),
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
                  key: const ValueKey<String>('travel-template-edit-confirm'),
                  isDefaultAction: true,
                  onPressed: title.isEmpty
                      ? null
                      : () => Navigator.of(dialogContext).pop(
                          _TemplateRevisionDraft(
                            title: title,
                            summary: summaryController.text.trim(),
                          ),
                        ),
                  child: const Text(CommunityText.done),
                ),
              ],
            );
          },
        ),
      );
    } finally {
      titleController.dispose();
      summaryController.dispose();
    }
  }

  Future<void> _submitTemplateRevision(
    TripPlanTemplate template,
    TripTemplateReviseIntent intent,
  ) async {
    setState(() => _busyTemplateId = template.id);
    AppToast.show(context, TravelText.templateUpdating);
    try {
      await ref.read(tripTemplateCoordinatorProvider).revise(intent);
      if (!mounted) {
        return;
      }
      AppToast.dismiss();
      ref.invalidate(tripPlanTemplatesProvider);
      AppToast.show(context, TravelText.templateUpdated);
    } catch (error) {
      if (!mounted) {
        return;
      }
      AppToast.dismiss();
      setState(() => _busyTemplateId = null);
      final semantic = ensureRetryUiErrorSemantic(
        runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.submit,
          scope: UiErrorScope.global,
          sourceRouteId: AppUiSurfaces.travelTemplates.routeId,
          sourceSurfaceId: AppUiSurfaces.travelTemplates.id,
          sourceOperationId:
              AppCloudOperationIds.travelTripPlanTemplateReviseTripPlanTemplate,
        ),
      );
      await AppActionErrorFeedback.show(
        context,
        semantic: semantic,
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await _submitTemplateRevision(template, intent);
          }
        },
      );
    } finally {
      if (mounted && _busyTemplateId != null) {
        setState(() => _busyTemplateId = null);
      }
    }
  }

  Future<void> _submitTemplateIntent(
    TripPlanTemplate template,
    TripPlanCreationIntent intent,
  ) async {
    setState(() => _busyTemplateId = template.id);
    AppToast.show(context, TravelText.templateCreatingTrip);
    try {
      final result = await ref
          .read(tripPlanCreationCoordinatorProvider)
          .create(intent);
      if (!mounted) {
        return;
      }
      AppToast.dismiss();
      widget.onOpenTrip(result.tripId);
    } catch (error) {
      if (!mounted) {
        return;
      }
      AppToast.dismiss();
      setState(() => _busyTemplateId = null);
      final semantic = ensureRetryUiErrorSemantic(
        runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.submit,
          scope: UiErrorScope.global,
          sourceRouteId: AppUiSurfaces.travelTemplates.routeId,
          sourceSurfaceId: AppUiSurfaces.travelTemplates.id,
          sourceOperationId:
              AppCloudOperationIds.travelTripPlanCreateTripPlanFromTemplate,
        ),
      );
      await AppActionErrorFeedback.show(
        context,
        semantic: semantic,
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await _submitTemplateIntent(template, intent);
          }
        },
      );
    } finally {
      if (mounted && _busyTemplateId != null) {
        setState(() => _busyTemplateId = null);
      }
    }
  }
}

final class _TemplateCard extends StatelessWidget {
  const _TemplateCard({
    required this.template,
    required this.busy,
    required this.onEdit,
    required this.onUse,
  });

  final TripPlanTemplate template;
  final bool busy;
  final VoidCallback? onEdit;
  final VoidCallback? onUse;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final summary = (template.summary ?? '').trim();
    return Card(
      margin: EdgeInsets.zero,
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerMd),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              template.title,
              style: TextStyle(
                color: colors.onSurface,
                fontSize: AppTypography.sectionTitle,
                fontWeight: AppTypography.semiBold,
              ),
            ),
            if (summary.isNotEmpty) ...[
              SizedBox(height: AppSpacing.intraGroupXs),
              Text(
                summary,
                style: TextStyle(
                  color: colors.onSurfaceVariant,
                  fontSize: AppTypography.secondary,
                ),
              ),
            ],
            SizedBox(height: AppSpacing.containerSm),
            Text(
              '${template.dayCount}${TravelText.templateDays} · '
              '${template.items.length}${TravelText.templateItems} · '
              '${template.attributions.length}${TravelText.templateAttributions}',
              style: TextStyle(
                color: colors.onSurfaceVariant,
                fontSize: AppTypography.caption,
              ),
            ),
            SizedBox(height: AppSpacing.containerMd),
            OutlinedButton.icon(
              onPressed: onEdit,
              icon: const Icon(CupertinoIcons.pencil),
              label: const Text(TravelText.editTemplate),
            ),
            SizedBox(height: AppSpacing.intraGroupSm),
            FilledButton.icon(
              onPressed: onUse,
              icon: busy
                  ? AppRequestFeedback.inline()
                  : const Icon(CupertinoIcons.add_circled),
              label: const Text(TravelText.useTemplate),
            ),
          ],
        ),
      ),
    );
  }
}

final class _TemplateRevisionDraft {
  const _TemplateRevisionDraft({required this.title, required this.summary});

  final String title;
  final String summary;
}

final class _EmptyTemplates extends StatelessWidget {
  const _EmptyTemplates();

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Center(
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerLg),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              CupertinoIcons.square_stack_3d_up,
              color: colors.onSurfaceVariant,
              size: AppSpacing.iconLarge,
            ),
            SizedBox(height: AppSpacing.containerMd),
            Text(
              TravelText.templatesEmpty,
              textAlign: TextAlign.center,
              style: TextStyle(
                color: colors.onSurfaceVariant,
                fontSize: AppTypography.body,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
