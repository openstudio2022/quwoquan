import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/di/navigation/app_message_navigation.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('AppMessage target resolves my intersections dimension route', () {
    final message = AppMessage(
      messageId: 'msg_1',
      userId: 'user_1',
      messageType: NotificationType.assistant,
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
      messageType: NotificationType.assistant,
      source: 'assistant',
      sourceId: 'unknown',
      destination: const AppMessageDestination(type: 'user', id: 'user_1'),
      title: '小趣提醒',
      summary: '你关注的主题有新进展。',
      target: const AppMessageTarget(
        targetType: 'unknown',
        targetId: 'unknown',
        query: AppMessageRouteQuery(),
      ),
      read: false,
      createdAt: DateTime.utc(2026, 6, 12),
    );

    expect(AppMessageNavigationTarget.fromMessage(message), isNull);
  });

  test('Report result notification returns to private report progress', () {
    final message = AppMessage(
      messageId: 'msg_report',
      userId: 'user_1',
      messageType: NotificationType.content,
      source: 'report_result',
      sourceId: 'report_1',
      destination: const AppMessageDestination(type: 'user', id: 'user_1'),
      title: '举报处理完成',
      summary: '你提交的举报已处理',
      target: const AppMessageTarget(
        targetType: 'report',
        targetId: 'report_1',
        query: AppMessageRouteQuery(),
      ),
      read: false,
      createdAt: DateTime.utc(2026, 7, 20),
    );

    expect(
      AppMessageNavigationTarget.fromMessage(message)?.location,
      AppRoutePaths.myReports,
    );
  });

  test('Homepage governance result returns to canonical homepage detail', () {
    final message = AppMessage(
      messageId: 'msg_homepage',
      userId: 'persona_1',
      messageType: NotificationType.content,
      source: 'homepage_claim_result',
      sourceId: 'claim_1',
      destination: const AppMessageDestination(type: 'user', id: 'persona_1'),
      title: '主页认领审核完成',
      summary: '你的主页认领申请已通过',
      target: const AppMessageTarget(
        targetType: 'homepage',
        targetId: 'homepage_1',
        query: AppMessageRouteQuery(),
      ),
      read: false,
      createdAt: DateTime.utc(2026, 7, 20),
    );

    expect(
      AppMessageNavigationTarget.fromMessage(message)?.location,
      AppRoutePaths.homepageDetail(id: 'homepage_1'),
    );
  });
}
