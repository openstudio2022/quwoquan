// 圈子创作流连续分页契约：端侧只保存并携带服务端 cursor 追加加载（不重排、
// 按 postId 去重不重不漏）、cursor 耗尽后不再请求、加载更多失败保留已加载
// 内容并给出 canonical 可重试反馈（不产生伪成功事实）。
// spec_ref: specs/feature-tree/circle-community/activity-member-governance/activity-stream-paging/spec.md#gwt-001
// spec_ref: specs/feature-tree/circle-community/activity-member-governance/activity-stream-paging/spec.md#gwt-001.t1
// spec_ref: specs/feature-tree/circle-community/activity-member-governance/activity-stream-paging/spec.md#gwt-001.t2
// spec_ref: specs/feature-tree/circle-community/activity-member-governance/activity-stream-paging/spec.md#gwt-001.t3
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-002.t1
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/di/circle_creations_presentation_slots.dart'
    show circleCreationsParticipantSlots;
import 'package:quwoquan_app/service/circle_service/circle_management/circle/presentation/section_creations.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/application/circle_state_provider.dart'
    show CircleRole;
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/circle_service/circle_management/circle/circle_contract_test_builders.dart';
import '../../../../../support/service/circle_service/circle_management/circle/typed_circle_query_test_double.dart';

const String _circleId = 'fixture_circle_photo';

CircleFeedItemView _photoItem(String postId) => buildCircleFeedItemContract(
  circleId: _circleId,
  placementId: 'placement-$postId',
  postId: postId,
  contentType: 'image',
  contentIdentity: 'work',
  authorId: 'fixture_user_photo',
  authorDisplayName: '契约摄影师',
  body: '分页契约 $postId',
  coverUrl: 'media/image/$postId.jpg',
  imageUrls: <String>['media/image/$postId.jpg'],
  likeCount: 1,
);

Widget _wrap(Widget child, {required CircleFeedQueryTestDouble feedQuery}) {
  return ProviderScope(
    overrides: [
      circleDetailQueryProvider.overrideWithValue(
        CircleQueryReaderTestDouble(),
      ),
      circlesListQueryProvider.overrideWithValue(CircleQueryReaderTestDouble()),
      circleDetailFeedQueryProvider.overrideWithValue(feedQuery),
    ],
    child: MaterialApp.router(
      routerConfig: GoRouter(
        initialLocation: '/',
        routes: [
          GoRoute(
            path: '/',
            builder: (_, _) => Scaffold(body: child),
          ),
          GoRoute(
            path: '/works/browser/:workId',
            builder: (_, _) => const SizedBox(),
          ),
        ],
      ),
    ),
  );
}

Widget _section() => const SizedBox(
  height: 600,
  child: SectionCreations(
    circleId: _circleId,
    isDark: false,
    role: CircleRole.member,
    participantSlots: circleCreationsParticipantSlots,
  ),
);

Future<void> _tapLoadMore(WidgetTester tester) async {
  await tester.ensureVisible(
    find.byKey(const ValueKey<String>('circle-creations-load-more')),
  );
  await tester.tap(
    find.byKey(const ValueKey<String>('circle-creations-load-more')),
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('触底追加下一页且按 postId 去重不重不漏', (tester) async {
    final feedQuery = CircleFeedQueryTestDouble((query) {
      if (query.cursor == null) {
        return CircleFeedPageSlice(
          items: <CircleFeedItemView>[_photoItem('p1'), _photoItem('p2')],
          cursor: 'cursor-1',
        );
      }
      expect(query.cursor, 'cursor-1');
      // 服务端可能因窗口漂移重发边界项：p2 重复，端侧必须去重。
      return CircleFeedPageSlice(
        items: <CircleFeedItemView>[_photoItem('p2'), _photoItem('p3')],
      );
    });
    await tester.pumpWidget(_wrap(_section(), feedQuery: feedQuery));
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey<String>('circle-record-grid-p1')),
      findsOneWidget,
    );

    // 有 cursor 时加载更多入口常驻（首屏不满一屏也可达）。
    await _tapLoadMore(tester);

    expect(feedQuery.receivedQueries, hasLength(2));
    expect(feedQuery.receivedQueries.last.cursor, 'cursor-1');
    expect(
      find.byKey(const ValueKey<String>('circle-record-grid-p3')),
      findsOneWidget,
    );
    // p2 去重：只渲染一份。
    expect(
      find.byKey(const ValueKey<String>('circle-record-grid-p2')),
      findsOneWidget,
    );

    // cursor 耗尽：入口消失，不再发起请求。
    expect(
      find.byKey(const ValueKey<String>('circle-creations-load-more')),
      findsNothing,
    );
    expect(feedQuery.receivedQueries, hasLength(2));
  });

  testWidgets('加载更多失败保留已加载内容并可重试，不产生伪成功', (tester) async {
    var failNext = true;
    final feedQuery = CircleFeedQueryTestDouble((query) {
      if (query.cursor == null) {
        return CircleFeedPageSlice(
          items: <CircleFeedItemView>[_photoItem('p1'), _photoItem('p2')],
          cursor: 'cursor-1',
        );
      }
      if (failNext) {
        failNext = false;
        throw StateError('feed page unavailable');
      }
      return CircleFeedPageSlice(items: <CircleFeedItemView>[_photoItem('p3')]);
    });
    await tester.pumpWidget(_wrap(_section(), feedQuery: feedQuery));
    await tester.pumpAndSettle();

    await _tapLoadMore(tester);

    // 失败保留已加载内容（不清空、不伪造第二页）。
    expect(
      find.byKey(const ValueKey<String>('circle-record-grid-p1')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('circle-record-grid-p3')),
      findsNothing,
    );
    // canonical 失败反馈：footer 呈现可重试入口。
    expect(
      find.text(CommunityText.circleCreationsLoadMoreFailed),
      findsOneWidget,
    );

    await _tapLoadMore(tester);

    expect(
      find.byKey(const ValueKey<String>('circle-record-grid-p3')),
      findsOneWidget,
    );
    expect(feedQuery.receivedQueries, hasLength(3));
  });
}
