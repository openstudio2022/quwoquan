import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/application/travel/trip_travelogue_draft.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/errors/runtime_error_display.dart';
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/widgets/app_request_feedback.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/core/widgets/error_states/app_error_states.dart';
import 'package:quwoquan_app/ui/content/entry/adapters/trip_share_draft_writer.dart';
import 'package:quwoquan_app/ui/content/entry/providers/create_draft_store_provider.dart';
import 'package:quwoquan_app/ui/travel/sharing/trip_share_snapshot_view.dart';
import 'package:quwoquan_app/ui/travel/sharing/trip_travelogue_draft_composer.dart';
import 'package:quwoquan_app/ui/travel/travel_text_constants.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class TripSharePage extends ConsumerStatefulWidget {
  const TripSharePage({
    super.key,
    required this.snapshotId,
    required this.onBack,
    required this.onOpenDraft,
  });

  final String snapshotId;
  final VoidCallback onBack;
  final ValueChanged<String> onOpenDraft;

  @override
  ConsumerState<TripSharePage> createState() => _TripSharePageState();
}

final class _TripSharePageState extends ConsumerState<TripSharePage> {
  var _creatingTravelogue = false;

  @override
  Widget build(BuildContext context) {
    final snapshot = ref.watch(tripShareSnapshotProvider(widget.snapshotId));
    return AppScaffold(
      navigationBar: AppNavigationBar(
        leading: AppNavigationBarIconButton(
          icon: CupertinoIcons.back,
          onPressed: widget.onBack,
        ),
        middle: const Text(TravelText.shareSnapshot),
      ),
      child: SafeArea(
        child: snapshot.when(
          loading: AppRequestFeedback.page,
          data: (value) => Column(
            children: <Widget>[
              Expanded(child: TripShareSnapshotView(snapshot: value)),
              Padding(
                padding: EdgeInsets.fromLTRB(
                  AppSpacing.containerMd,
                  AppSpacing.containerSm,
                  AppSpacing.containerMd,
                  AppSpacing.containerMd,
                ),
                child: SizedBox(
                  width: double.infinity,
                  child: FilledButton.icon(
                    onPressed: _creatingTravelogue
                        ? null
                        : () => _createTravelogue(value),
                    icon: _creatingTravelogue
                        ? AppRequestFeedback.inline()
                        : const Icon(CupertinoIcons.book),
                    label: Text(
                      _creatingTravelogue
                          ? TravelText.creatingTravelogue
                          : TravelText.createTravelogue,
                    ),
                  ),
                ),
              ),
            ],
          ),
          error: (error, _) => AppPageErrorState(
            semantic: ensureRetryUiErrorSemantic(
              runtimeErrorSemantic(
                context,
                error: error,
                category: UiErrorCategory.pageLoad,
                scope: UiErrorScope.page,
                sourceRouteId: AppUiSurfaces.travelShare.routeId,
                sourceSurfaceId: AppUiSurfaces.travelShare.id,
              ),
            ),
            onRecovery: _recoverSnapshot,
          ),
        ),
      ),
    );
  }

  Future<UiRecoveryOutcome> _recoverSnapshot(UiErrorAction action) async {
    if (action.type != UiErrorActionType.retry &&
        action.type != UiErrorActionType.resubmit) {
      return UiRecoveryOutcome.cancelled;
    }
    try {
      ref.invalidate(tripShareSnapshotProvider(widget.snapshotId));
      await ref.read(tripShareSnapshotProvider(widget.snapshotId).future);
      return mounted
          ? UiRecoveryOutcome.recovered
          : UiRecoveryOutcome.superseded;
    } catch (_) {
      return mounted
          ? UiRecoveryOutcome.stillBlocked
          : UiRecoveryOutcome.superseded;
    }
  }

  Future<void> _createTravelogue(TripShareSnapshot snapshot) async {
    setState(() => _creatingTravelogue = true);
    try {
      final coordinator = TripTravelogueDraftCoordinator(
        composer: const TravelTextTripTravelogueDraftComposer(),
        writer: TripShareDraftWriter(
          repository: ref.read(createDraftRepositoryProvider),
          clock: () => DateTime.now().millisecondsSinceEpoch,
        ),
        draftIdFactory: (snapshotId) => 'travelogue-${snapshotId.trim()}',
      );
      final draftId = await coordinator.create(snapshot);
      if (!mounted) {
        return;
      }
      AppToast.show(context, TravelText.travelogueCreated);
      widget.onOpenDraft(draftId);
    } catch (_) {
      if (mounted) {
        AppToast.show(context, TravelText.travelogueCreateFailed);
      }
    } finally {
      if (mounted) {
        setState(() => _creatingTravelogue = false);
      }
    }
  }
}
