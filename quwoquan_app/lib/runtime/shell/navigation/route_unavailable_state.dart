import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/layout/app_scaffold.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';

/// Runtime-shell fallback for a route whose typed production composition is
/// unavailable. Business owners supply only their canonical surface and title.
class RouteUnavailableState extends StatelessWidget {
  const RouteUnavailableState({
    super.key,
    required this.error,
    required this.surface,
    required this.pageTitle,
  });

  final Object error;
  final AppUiSurface surface;
  final String pageTitle;

  @override
  Widget build(BuildContext context) {
    return AppScaffold(
      navigationBar: CupertinoNavigationBar(middle: Text(pageTitle)),
      child: SafeArea(
        child: KeyedSubtree(
          key: ValueKey<String>('${surface.id}-route-unavailable'),
          child: AppPageErrorState(
            semantic: runtimeErrorSemantic(
              context,
              error: error,
              category: UiErrorCategory.pageLoad,
              scope: UiErrorScope.page,
              sourceRouteId: surface.routeId,
              sourceSurfaceId: surface.id,
            ),
          ),
        ),
      ),
    );
  }
}
