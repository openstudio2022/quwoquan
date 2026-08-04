import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/application/travel/trip_plan_creation_coordinator.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/errors/runtime_error_display.dart';
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/widgets/app_request_feedback.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/core/widgets/error_states/app_error_states.dart';
import 'package:quwoquan_app/ui/travel/travel_text_constants.dart';
import 'package:quwoquan_app/ui/travel/widgets/trip_item_semantics.dart';
import 'package:quwoquan_app/ui/travel/widgets/trip_plan_create_dialog.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 当前 Persona 的 Trip 目录入口。只消费 Travel Service 的有界
/// keyset slice，不从聊天、本地草稿或假数据推导 Trip 真相。
final class TripPlansPage extends ConsumerStatefulWidget {
  const TripPlansPage({
    super.key,
    required this.onOpenTrip,
    required this.onOpenTemplates,
  });

  final ValueChanged<String> onOpenTrip;
  final VoidCallback onOpenTemplates;

  @override
  ConsumerState<TripPlansPage> createState() => _TripPlansPageState();
}

final class _TripPlansPageState extends ConsumerState<TripPlansPage> {
  final List<TripPlanSummarySlice> _plans = <TripPlanSummarySlice>[];
  TripPlanStatus? _status;
  String? _nextCursor;
  Object? _initialError;
  bool _loading = true;
  bool _loadingMore = false;
  bool _creating = false;

  @override
  void initState() {
    super.initState();
    unawaited(_reload());
  }

  @override
  Widget build(BuildContext context) {
    return AppScaffold(
      navigationBar: AppNavigationBar(
        middle: const Text(TravelText.tripsTitle),
        trailing: Row(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            AppNavigationBarTextAction(
              label: TravelText.openTemplates,
              onPressed: widget.onOpenTemplates,
            ),
            AppNavigationBarIconButton(
              icon: CupertinoIcons.add,
              onPressed: _creating ? null : () => unawaited(_startCreate()),
            ),
          ],
        ),
      ),
      child: SafeArea(child: _buildBody(context)),
    );
  }

  Widget _buildBody(BuildContext context) {
    if (_loading && _plans.isEmpty) {
      return AppRequestFeedback.page();
    }
    final error = _initialError;
    if (error != null && _plans.isEmpty) {
      return AppPageErrorState(
        semantic: _errorSemantic(
          context,
          error: error,
          category: UiErrorCategory.pageLoad,
          scope: UiErrorScope.page,
        ),
        onRecovery: _recoverDirectory,
      );
    }

    return RefreshIndicator.adaptive(
      onRefresh: _reload,
      child: CustomScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        slivers: <Widget>[
          SliverPadding(
            padding: EdgeInsets.fromLTRB(
              AppSpacing.containerMd,
              AppSpacing.containerMd,
              AppSpacing.containerMd,
              AppSpacing.containerSm,
            ),
            sliver: SliverToBoxAdapter(
              child: _TripStatusFilter(
                selected: _status,
                onSelected: _selectStatus,
              ),
            ),
          ),
          if (_plans.isEmpty)
            SliverFillRemaining(
              hasScrollBody: false,
              child: _EmptyTrips(
                filtered: _status != null,
                creating: _creating,
                onCreate: _creating ? null : () => unawaited(_startCreate()),
              ),
            )
          else
            SliverPadding(
              padding: EdgeInsets.fromLTRB(
                AppSpacing.containerMd,
                AppSpacing.containerSm,
                AppSpacing.containerMd,
                AppSpacing.containerLg,
              ),
              sliver: SliverList.separated(
                itemCount: _plans.length + (_nextCursor == null ? 0 : 1),
                separatorBuilder: (_, _) =>
                    SizedBox(height: AppSpacing.containerMd),
                itemBuilder: (context, index) {
                  if (index == _plans.length) {
                    return Center(
                      child: FilledButton.tonal(
                        onPressed: _loadingMore
                            ? null
                            : () => unawaited(_loadMore()),
                        child: _loadingMore
                            ? AppRequestFeedback.inline()
                            : const Text(TravelText.loadMoreTrips),
                      ),
                    );
                  }
                  final plan = _plans[index];
                  return _TripPlanCard(
                    plan: plan,
                    onOpen: () => widget.onOpenTrip(plan.tripId),
                  );
                },
              ),
            ),
        ],
      ),
    );
  }

  Future<void> _selectStatus(TripPlanStatus? status) async {
    if (_status == status || _loading) {
      return;
    }
    setState(() {
      _status = status;
      _plans.clear();
      _nextCursor = null;
      _initialError = null;
      _loading = true;
    });
    await _reload();
  }

  Future<UiRecoveryOutcome> _recoverDirectory(UiErrorAction action) async {
    if (action.type != UiErrorActionType.retry &&
        action.type != UiErrorActionType.resubmit) {
      return UiRecoveryOutcome.cancelled;
    }
    await _reload();
    if (!mounted) {
      return UiRecoveryOutcome.superseded;
    }
    return _initialError == null
        ? UiRecoveryOutcome.recovered
        : UiRecoveryOutcome.stillBlocked;
  }

  Future<void> _reload() async {
    if (mounted) {
      setState(() {
        _loading = true;
        _initialError = null;
      });
    }
    try {
      final page = await ref
          .read(tripPlanDirectoryProvider)
          .list(status: _status);
      if (!mounted) {
        return;
      }
      setState(() {
        _plans
          ..clear()
          ..addAll(page.plans);
        _nextCursor = _usableCursor(page.nextCursor);
        _loading = false;
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _initialError = error;
        _loading = false;
      });
    }
  }

  Future<void> _loadMore() async {
    final cursor = _usableCursor(_nextCursor);
    if (cursor == null || _loadingMore) {
      return;
    }
    setState(() => _loadingMore = true);
    try {
      final page = await ref
          .read(tripPlanDirectoryProvider)
          .list(status: _status, cursor: cursor);
      if (!mounted) {
        return;
      }
      final knownIds = _plans.map((plan) => plan.tripId).toSet();
      setState(() {
        _plans.addAll(page.plans.where((plan) => knownIds.add(plan.tripId)));
        _nextCursor = _usableCursor(page.nextCursor);
        _loadingMore = false;
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() => _loadingMore = false);
      await AppActionErrorFeedback.show(
        context,
        semantic: _errorSemantic(
          context,
          error: error,
          category: UiErrorCategory.listAppend,
          scope: UiErrorScope.global,
        ),
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await _loadMore();
          }
        },
      );
    } finally {
      if (mounted && _loadingMore) {
        setState(() => _loadingMore = false);
      }
    }
  }

  Future<void> _startCreate() async {
    if (_creating) {
      return;
    }
    final title = await showTripPlanCreateDialog(context);
    if (!mounted || title == null) {
      return;
    }
    final intent = ref
        .read(tripPlanCreationCoordinatorProvider)
        .prepareDraft(title: title);
    await _submitCreate(intent);
  }

  Future<void> _submitCreate(TripPlanCreationIntent intent) async {
    if (mounted) {
      setState(() => _creating = true);
    }
    AppToast.show(context, TravelText.tripCreating);
    try {
      final result = await ref
          .read(tripPlanCreationCoordinatorProvider)
          .create(intent);
      if (!mounted) {
        return;
      }
      AppToast.dismiss();
      setState(() => _creating = false);
      widget.onOpenTrip(result.tripId);
    } catch (error) {
      if (!mounted) {
        return;
      }
      AppToast.dismiss();
      setState(() => _creating = false);
      await AppActionErrorFeedback.show(
        context,
        semantic: _errorSemantic(
          context,
          error: error,
          category: UiErrorCategory.submit,
          scope: UiErrorScope.global,
          operationId: AppCloudOperationIds.travelTripPlanCreateTripPlan,
        ),
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await _submitCreate(intent);
          }
        },
      );
    }
  }

  UiErrorSemantic _errorSemantic(
    BuildContext context, {
    required Object error,
    required UiErrorCategory category,
    required UiErrorScope scope,
    String operationId = AppCloudOperationIds.travelTripPlanListTripPlans,
  }) {
    return ensureRetryUiErrorSemantic(
      runtimeErrorSemantic(
        context,
        error: error,
        category: category,
        scope: scope,
        sourceRouteId: AppUiSurfaces.travelTrips.routeId,
        sourceSurfaceId: AppUiSurfaces.travelTrips.id,
        sourceOperationId: operationId,
      ),
    );
  }
}

final class _TripStatusFilter extends StatelessWidget {
  const _TripStatusFilter({required this.selected, required this.onSelected});

  final TripPlanStatus? selected;
  final ValueChanged<TripPlanStatus?> onSelected;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: AppSpacing.intraGroupSm,
      runSpacing: AppSpacing.intraGroupXs,
      children: <Widget>[
        ChoiceChip(
          label: const Text(TravelText.tripFilterAll),
          selected: selected == null,
          onSelected: (_) => onSelected(null),
        ),
        for (final status in const <TripPlanStatus>[
          TripPlanStatus.planning,
          TripPlanStatus.active,
          TripPlanStatus.completed,
        ])
          ChoiceChip(
            label: Text(tripStatusLabel(status)),
            selected: selected == status,
            onSelected: (_) => onSelected(status),
          ),
      ],
    );
  }
}

final class _TripPlanCard extends StatelessWidget {
  const _TripPlanCard({required this.plan, required this.onOpen});

  final TripPlanSummarySlice plan;
  final VoidCallback onOpen;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Card(
      margin: EdgeInsets.zero,
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onOpen,
        child: Padding(
          padding: EdgeInsets.all(AppSpacing.containerMd),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: <Widget>[
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(
                      plan.title,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        color: colors.onSurface,
                        fontSize: AppTypography.sectionTitle,
                        fontWeight: AppTypography.semiBold,
                      ),
                    ),
                    SizedBox(height: AppSpacing.intraGroupXs),
                    Text(
                      '${tripStatusLabel(plan.status)} · '
                      '${plan.itemCount}${TravelText.tripItemCount} · '
                      '${TravelText.tripRevision}${plan.currentRevisionNumber}',
                      style: TextStyle(
                        color: colors.onSurfaceVariant,
                        fontSize: AppTypography.secondary,
                      ),
                    ),
                  ],
                ),
              ),
              SizedBox(width: AppSpacing.intraGroupSm),
              Icon(
                CupertinoIcons.chevron_forward,
                color: colors.onSurfaceVariant,
                size: AppSpacing.iconSmall,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

final class _EmptyTrips extends StatelessWidget {
  const _EmptyTrips({
    required this.filtered,
    required this.creating,
    required this.onCreate,
  });

  final bool filtered;
  final bool creating;
  final VoidCallback? onCreate;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Center(
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerLg),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Icon(
              CupertinoIcons.map_pin_ellipse,
              color: colors.onSurfaceVariant,
              size: AppSpacing.iconLarge,
            ),
            SizedBox(height: AppSpacing.containerMd),
            Text(
              filtered ? TravelText.tripsFilterEmpty : TravelText.tripsEmpty,
              textAlign: TextAlign.center,
              style: TextStyle(
                color: colors.onSurfaceVariant,
                fontSize: AppTypography.body,
              ),
            ),
            SizedBox(height: AppSpacing.containerMd),
            FilledButton.icon(
              onPressed: onCreate,
              icon: creating
                  ? AppRequestFeedback.inline()
                  : const Icon(CupertinoIcons.add_circled),
              label: const Text(TravelText.createTripAction),
            ),
          ],
        ),
      ),
    );
  }
}

String? _usableCursor(String? value) {
  final normalized = value?.trim() ?? '';
  return normalized.isEmpty ? null : normalized;
}
