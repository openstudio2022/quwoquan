import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/notification/app_message_dto.g.dart';
import 'package:quwoquan_app/cloud/services/notification/app_message_navigation.dart';

void main() {
  test('AppMessage target resolves my intersections dimension route', () {
    const message = AppMessageWire(
      messageId: 'msg_1',
      userId: 'user_1',
      source: 'assistant/proactive_intersection',
      sourceId: 'reason_1',
      title: '小趣提醒',
      summary: '你有了新的交集：共同讨论',
      target: AppMessageTargetWire(
        targetType: 'route',
        targetId: 'myIntersections',
        routeId: 'myIntersections',
        routePath: AppRoutePaths.myIntersectionsPathTemplate,
        query: <String, dynamic>{'dimension': 'content'},
      ),
      createdAt: '2026-06-12T00:00:00Z',
    );

    final target = AppMessageNavigationTarget.fromMessage(message);

    expect(
      target?.location,
      AppRoutePaths.myIntersections(dimension: 'content'),
    );
  });

  test('AppMessage target gracefully ignores unknown target', () {
    const message = AppMessageWire(
      messageId: 'msg_2',
      userId: 'user_1',
      source: 'assistant',
      sourceId: 'unknown',
      title: '小趣提醒',
      summary: '你关注的主题有新进展。',
      target: AppMessageTargetWire(targetType: 'unknown', targetId: 'unknown'),
      createdAt: '2026-06-12T00:00:00Z',
    );

    expect(AppMessageNavigationTarget.fromMessage(message), isNull);
  });
}
