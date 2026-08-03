import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/errors/runtime_error_display.dart';
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/widgets/app_request_feedback.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/error_states/app_error_states.dart';
import 'package:quwoquan_app/ui/travel/map/trip_route_overview.dart';
import 'package:quwoquan_app/ui/travel/travel_text_constants.dart';

final class TripMapPage extends ConsumerWidget {
  const TripMapPage({super.key, required this.tripId, required this.onBack});

  final String tripId;
  final VoidCallback onBack;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final map = ref.watch(tripMapProvider(tripId));
    return AppScaffold(
      navigationBar: AppNavigationBar(
        leading: AppNavigationBarIconButton(
          icon: CupertinoIcons.back,
          onPressed: onBack,
        ),
        middle: const Text(TravelText.routeMap),
      ),
      child: SafeArea(
        child: map.when(
          loading: AppRequestFeedback.page,
          data: (projection) => SingleChildScrollView(
            padding: EdgeInsets.all(AppSpacing.containerMd),
            child: TripRouteOverview(map: projection),
          ),
          error: (error, _) => AppPageErrorState(
            semantic: ensureRetryUiErrorSemantic(
              runtimeErrorSemantic(
                context,
                error: error,
                category: UiErrorCategory.pageLoad,
                scope: UiErrorScope.page,
                sourceRouteId: AppUiSurfaces.travelMap.routeId,
                sourceSurfaceId: AppUiSurfaces.travelMap.id,
              ),
            ),
            onAction: (action) async {
              if (action.type == UiErrorActionType.retry ||
                  action.type == UiErrorActionType.resubmit) {
                ref.invalidate(tripMapProvider(tripId));
              }
            },
          ),
        ),
      ),
    );
  }
}
