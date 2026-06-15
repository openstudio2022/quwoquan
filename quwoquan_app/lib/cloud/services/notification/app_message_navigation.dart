import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/notification/app_message_dto.g.dart';

class AppMessageNavigationTarget {
  const AppMessageNavigationTarget._(this.location);

  final String location;

  static AppMessageNavigationTarget? fromMessage(AppMessageWire message) {
    final target = message.target;
    final routeId = target.routeId.trim();
    final routePath = target.routePath.trim();
    final targetId = target.targetId.trim();
    if (routeId == 'myIntersections' ||
        routePath == AppRoutePaths.myIntersectionsPathTemplate ||
        targetId == 'myIntersections') {
      final dimension = (target.query['dimension'] ?? '').toString().trim();
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
