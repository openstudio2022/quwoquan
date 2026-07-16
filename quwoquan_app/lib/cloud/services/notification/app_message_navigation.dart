import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

class AppMessageNavigationTarget {
  const AppMessageNavigationTarget._(this.location);

  final String location;

  static AppMessageNavigationTarget? fromMessage(AppMessage message) {
    final target = message.target;
    final routeId = target.routeId?.trim() ?? '';
    final routePath = target.routePath?.trim() ?? '';
    final targetId = target.targetId.trim();
    if (routeId == 'myIntersections' ||
        routePath == AppRoutePaths.myIntersectionsPathTemplate ||
        targetId == 'myIntersections') {
      final dimension = target.query.dimension?.trim() ?? '';
      return AppMessageNavigationTarget._(
        AppRoutePaths.myIntersections(
          dimension: dimension.isEmpty ? null : dimension,
        ),
      );
    }
    if (routePath.startsWith('/')) {
      return AppMessageNavigationTarget._(routePath);
    }
    return null;
  }
}
