import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_dimension_tally.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_inbox_summary.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_repository.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/user/widgets/my_intersection_inbox_card.dart';

/// SIT1 · 我的主页「我的交集」聚合入口卡（T2 模块交互）。
///
/// done_when：展示交集总数与最多 3 个维度的变化红点/数字，超 3 维度可展开更多；
/// 维度简报句来自云侧（briefText），端不编造事实；点击维度行进入分组列表页。
void main() {
  Widget host(IntersectionRepository repo) {
    return ProviderScope(
      overrides: [intersectionRepositoryProvider.overrideWithValue(repo)],
      child: CupertinoApp.router(
        routerConfig: GoRouter(
          initialLocation: '/',
          routes: <RouteBase>[
            GoRoute(
              path: '/',
              builder: (_, _) => const CupertinoPageScaffold(
                child: SafeArea(child: MyIntersectionInboxCard(isDark: false)),
              ),
            ),
            GoRoute(
              path: '/profile/intersections',
              builder: (_, state) =>
                  Text('INBOX:${state.uri.queryParameters['dimension'] ?? ''}'),
            ),
          ],
        ),
      ),
    );
  }

  testWidgets('展示总数红点与最多 3 行维度简报，超出折叠为展开更多', (tester) async {
    final repo = _StubIntersectionRepository(
      summary: IntersectionInboxSummary(
        totalCount: 21,
        totalNewCount: 7,
        dimensions: <IntersectionDimensionTally>[
          IntersectionDimensionTally(
            dimension: 'relationship',
            label: '关系',
            count: 8,
            newCount: 3,
            briefText: '3 位联系人新加入了你关注的圈子',
            subtitleText: '张晓明、王晨、阿远',
          ),
          IntersectionDimensionTally(
            dimension: 'interest',
            label: '兴趣',
            count: 6,
            newCount: 2,
            briefText: '2 个兴趣相投的人也在看川西攻略',
            subtitleText: '川西攻略、雪山线路',
          ),
          IntersectionDimensionTally(
            dimension: 'location',
            label: '地点',
            count: 4,
            newCount: 1,
            briefText: '1 位同城用户最近活跃',
          ),
          IntersectionDimensionTally(
            dimension: 'content',
            label: '内容',
            count: 3,
            newCount: 1,
            briefText: '1 位作者与你内容偏好高度重合',
          ),
        ],
      ),
    );

    await tester.pumpWidget(host(repo));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    // 总数未读红点。
    expect(find.text('7'), findsOneWidget);
    expect(find.text(UITextConstants.myIntersectionsTitle), findsWidgets);

    // 折叠态：仅展示前 3 条云侧简报句，第 4 条隐藏。
    expect(find.text('3 位联系人新加入了你关注的圈子'), findsOneWidget);
    expect(find.text('张晓明、王晨、阿远'), findsOneWidget);
    expect(find.text('2 个兴趣相投的人也在看川西攻略'), findsOneWidget);
    expect(find.text('川西攻略、雪山线路'), findsOneWidget);
    expect(find.text('1 位同城用户最近活跃'), findsOneWidget);
    expect(find.text('1 位作者与你内容偏好高度重合'), findsNothing);
    expect(find.byIcon(CupertinoIcons.chevron_down), findsOneWidget);

    // 标题同行展开更多 → 第 4 条出现，并切换为向上图标。
    await tester.tap(find.text(UITextConstants.intersectionExpandMore));
    await tester.pumpAndSettle();
    expect(find.text('1 位作者与你内容偏好高度重合'), findsOneWidget);
    expect(find.byIcon(CupertinoIcons.chevron_up), findsOneWidget);
  });

  testWidgets('点击维度简报行进入对应维度分组列表页', (tester) async {
    final repo = _StubIntersectionRepository(
      summary: IntersectionInboxSummary(
        totalCount: 4,
        totalNewCount: 2,
        dimensions: <IntersectionDimensionTally>[
          IntersectionDimensionTally(
            dimension: 'relationship',
            label: '关系',
            count: 4,
            newCount: 2,
            briefText: '2 位联系人来过你的主页',
          ),
        ],
      ),
    );

    await tester.pumpWidget(host(repo));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    await tester.tap(find.text('2 位联系人来过你的主页'));
    await tester.pumpAndSettle();
    expect(find.text('INBOX:relationship'), findsOneWidget);
  });

  testWidgets('总数为 0 时展示空态文案，不渲染维度行', (tester) async {
    final repo = _StubIntersectionRepository(
      summary: IntersectionInboxSummary(totalCount: 0, totalNewCount: 0),
    );

    await tester.pumpWidget(host(repo));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.text(UITextConstants.myIntersectionsEmpty), findsOneWidget);
  });

  testWidgets('契约 seed 默认 Mock：折叠 3 维度，展开更多切换为收起', (tester) async {
    // 使用真实默认 MockIntersectionRepository（契约 fixture 同源，5 维度），
    // 验证端云字段对齐下的折叠/展开行为（R12 Mock 与契约一致）。
    final container = ProviderContainer();
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const CupertinoApp(
          home: CupertinoPageScaffold(
            child: SafeArea(
              child: Padding(
                padding: EdgeInsets.all(16),
                child: MyIntersectionInboxCard(isDark: false),
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.text(UITextConstants.myIntersectionsTitle), findsOneWidget);
    expect(find.text(UITextConstants.intersectionExpandMore), findsOneWidget);
    expect(find.byIcon(CupertinoIcons.chevron_down), findsOneWidget);

    await tester.tap(find.text(UITextConstants.intersectionExpandMore));
    await tester.pump();
    expect(find.text(UITextConstants.intersectionCollapse), findsOneWidget);
    expect(find.byIcon(CupertinoIcons.chevron_up), findsOneWidget);
  });
}

class _StubIntersectionRepository implements IntersectionRepository {
  _StubIntersectionRepository({required this.summary});

  final IntersectionInboxSummary summary;

  @override
  Future<IntersectionInboxSummary> getMyIntersectionSummary() async => summary;

  @override
  Future<List<IntersectionReason>> listMyIntersections({
    String? dimension,
    int limit = 50,
  }) async => const <IntersectionReason>[];

  @override
  Future<void> markIntersectionsVisited({String? dimension}) async {}

  @override
  Future<List<IntersectionReason>> getFeedIntersections({
    String? channel,
    int limit = 4,
  }) async => const <IntersectionReason>[];

  @override
  Future<void> reportExposure({required List<String> objectIds}) async {}

  @override
  Future<List<IntersectionReason>> getObjectIntersections({
    required String objectId,
    required String objectType,
    int limit = 8,
  }) async => const <IntersectionReason>[];
}
