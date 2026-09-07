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

  test(
    'Gathering invitation and facilitation notifications open canonical detail',
    () {
      for (final source in <String>[
        'gathering_invitation',
        'intersection_facilitation',
      ]) {
        final message = AppMessage(
          messageId: 'msg_$source',
          userId: 'persona_1',
          messageType: NotificationType.circle,
          source: source,
          sourceId: 'source_1',
          destination: const AppMessageDestination(
            type: 'user',
            id: 'persona_1',
          ),
          title: '行动有新进展',
          summary: '点击查看行动详情',
          target: const AppMessageTarget(
            targetType: 'gathering',
            targetId: 'gathering_1',
            query: AppMessageRouteQuery(),
          ),
          read: false,
          createdAt: DateTime.utc(2026, 9, 5),
        );

        expect(
          AppMessageNavigationTarget.fromMessage(message)?.location,
          AppRoutePaths.gatheringDetail(id: 'gathering_1'),
        );
      }
    },
  );

  test('评论通知定位宿主作品与目标评论，route fallback 仍可用', () {
    final commentMessage = AppMessage(
      messageId: 'msg_comment',
      userId: 'persona_1',
      messageType: NotificationType.content,
      source: 'comment_mention',
      sourceId: 'comment_42',
      destination: const AppMessageDestination(type: 'user', id: 'persona_1'),
      title: '有人提到了你',
      summary: '点击查看评论',
      target: const AppMessageTarget(
        targetType: 'post',
        targetId: 'post_42',
        query: AppMessageRouteQuery(),
      ),
      read: false,
      createdAt: DateTime.utc(2026, 9, 5),
    );
    final commentLocation = AppMessageNavigationTarget.fromMessage(
      commentMessage,
    )?.location;
    expect(commentLocation, contains('/works/browser/post_42'));
    expect(commentLocation, contains('openComments=true'));
    expect(commentLocation, contains('targetCommentId=comment_42'));

    final fallbackMessage = AppMessage(
      messageId: 'msg_fallback',
      userId: 'persona_1',
      messageType: NotificationType.content,
      source: 'generic_route',
      sourceId: 'source_1',
      destination: const AppMessageDestination(type: 'user', id: 'persona_1'),
      title: '查看详情',
      summary: '点击继续',
      target: const AppMessageTarget(
        targetType: 'route',
        targetId: 'future_route',
        routePath: '/future/path?source=message',
        query: AppMessageRouteQuery(),
      ),
      read: false,
      createdAt: DateTime.utc(2026, 9, 5),
    );
    expect(
      AppMessageNavigationTarget.fromMessage(fallbackMessage)?.location,
      '/future/path?source=message',
    );
  });

  test('Assistant run notification resumes the canonical personal route', () {
    final message = AppMessage(
      messageId: 'msg_assistant_run',
      userId: 'user_1',
      messageType: NotificationType.assistant,
      source: 'assistant_subscription',
      sourceId: 'sub_1',
      destination: const AppMessageDestination(type: 'user', id: 'user_1'),
      title: '小趣任务有新进展',
      summary: '点击继续查看后台任务',
      target: const AppMessageTarget(
        targetType: 'assistant_run',
        targetId: 'arn_run/with space',
        query: AppMessageRouteQuery(),
      ),
      read: false,
      createdAt: DateTime.utc(2026, 8, 8),
    );

    expect(
      AppMessageNavigationTarget.fromMessage(message)?.location,
      '${AppRoutePaths.assistantPersonal}?runId=arn_run%2Fwith+space',
    );
  });
}
