import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/services/notification/app_message_navigation.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('AppMessage target resolves my intersections dimension route', () {
    final message = AppMessage(
      messageId: 'msg_1',
      userId: 'user_1',
      messageType: 'assistant',
      source: 'assistant/proactive_intersection',
      sourceId: 'reason_1',
      destination: const AppMessageDestination(type: 'user', id: 'user_1'),
      title: '小趣提醒',
      summary: '你有了新的交集：共同讨论',
      target: const AppMessageTarget(
        targetType: 'route',
        targetId: 'myIntersections',
        routeId: 'myIntersections',
        routePath: AppRoutePaths.myIntersectionsPathTemplate,
        query: AppMessageRouteQuery(dimension: 'content'),
      ),
      read: false,
      createdAt: DateTime.utc(2026, 6, 12),
    );

    final target = AppMessageNavigationTarget.fromMessage(message);

    expect(
      target?.location,
      AppRoutePaths.myIntersections(dimension: 'content'),
    );
  });

  test('AppMessage target gracefully ignores unknown target', () {
    final message = AppMessage(
      messageId: 'msg_2',
      userId: 'user_1',
      messageType: 'assistant',
      source: 'assistant',
      sourceId: 'unknown',
      destination: const AppMessageDestination(type: 'user', id: 'user_1'),
      title: '小趣提醒',
      summary: '你关注的主题有新进展。',
      target: const AppMessageTarget(
        targetType: 'unknown',
        targetId: 'unknown',
      ),
      read: false,
      createdAt: DateTime.utc(2026, 6, 12),
    );

    expect(AppMessageNavigationTarget.fromMessage(message), isNull);
  });
}
