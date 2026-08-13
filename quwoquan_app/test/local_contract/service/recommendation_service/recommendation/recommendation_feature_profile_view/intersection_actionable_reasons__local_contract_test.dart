// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/spec.md#req-008
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/spec.md#sit-008
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/l10n/copy/discovery_feed_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/content_service/content/intersection_visit_state/adapters/intersection_repository.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/domain/intersection_actionable_reasons.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/my_intersection_inbox_card.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/cloud_boundary_test_scope.dart';
import '../../../../../support/service/recommendation_service/recommendation/recommendation_feature_profile_view/intersection_fixtures.dart';

void main() {
  final now = DateTime.utc(2026, 8, 13, 12);

  IntersectionReason reason({
    String id = 'ix',
    String intersectionClass = 'fact',
    String expiresAt = '',
    List<IntersectionActionHint> actionHints =
        const <IntersectionActionHint>[],
  }) {
    return intersectionReasonFixture(
      intersectionId: id,
      intersectionClass: intersectionClass,
      expiresAt: expiresAt,
      actionHints: actionHints,
    );
  }

  IntersectionActionHint hint({
    String actionKey = 'start_gathering',
    String label = '约一次',
    bool isPrimary = false,
    int priority = 1,
  }) {
    return intersectionActionHintFixture(
      actionKey: actionKey,
      label: label,
      isPrimary: isPrimary,
      priority: priority,
    );
  }

  group('isActionableIntersectionReason（REQ-008 可约判定，事实全部来自云侧字段）', () {
    test('actionHints 非空且无过期时间 → 可行动', () {
      expect(
        isActionableIntersectionReason(
          reason(actionHints: <IntersectionActionHint>[hint()]),
          now: now,
        ),
        isTrue,
      );
    });

    test('actionHints 为空 → 不可行动', () {
      expect(isActionableIntersectionReason(reason(), now: now), isFalse);
    });

    test('expiresAt 未到期 → 可行动；已过期 → 不可行动', () {
      expect(
        isActionableIntersectionReason(
          reason(
            expiresAt: '2026-08-20T00:00:00Z',
            actionHints: <IntersectionActionHint>[hint()],
          ),
          now: now,
        ),
        isTrue,
      );
      expect(
        isActionableIntersectionReason(
          reason(
            expiresAt: '2026-08-01T00:00:00Z',
            actionHints: <IntersectionActionHint>[hint()],
          ),
          now: now,
        ),
        isFalse,
      );
    });

    test('expiresAt 无法解析按已过期处理（宁可少置顶，不虚假承诺行动窗口）', () {
      expect(
        isActionableIntersectionReason(
          reason(
            expiresAt: 'not-a-timestamp',
            actionHints: <IntersectionActionHint>[hint()],
          ),
          now: now,
        ),
        isFalse,
      );
    });

    test('affinity 概率推荐不进入可约分组（分通道诚实）', () {
      expect(
        isActionableIntersectionReason(
          reason(
            intersectionClass: 'affinity',
            actionHints: <IntersectionActionHint>[hint()],
          ),
          now: now,
        ),
        isFalse,
      );
    });
  });

  group('actionableIntersectionReasons（保序 = 云侧排序主权）', () {
    test('筛选后保持输入顺序，不重排组内顺序', () {
      final items = <IntersectionReason>[
        reason(id: 'a', actionHints: <IntersectionActionHint>[hint()]),
        reason(id: 'b'),
        reason(id: 'c', actionHints: <IntersectionActionHint>[hint()]),
        reason(
          id: 'd',
          expiresAt: '2026-08-01T00:00:00Z',
          actionHints: <IntersectionActionHint>[hint()],
        ),
      ];
      final actionable = actionableIntersectionReasons(items, now: now);
      expect(
        actionable.map((item) => item.intersectionId).toList(),
        <String>['a', 'c'],
      );
    });
  });

  group('primaryIntersectionActionHint（首个 isPrimary，缺省回落第一个）', () {
    test('优先返回首个 isPrimary hint', () {
      final selected = primaryIntersectionActionHint(
        reason(
          actionHints: <IntersectionActionHint>[
            hint(actionKey: 'open_object', label: '进入主页'),
            hint(actionKey: 'start_gathering', label: '约一次', isPrimary: true),
          ],
        ),
      );
      expect(selected?.actionKey, 'start_gathering');
      expect(selected?.label, '约一次');
    });

    test('无 isPrimary 时回落第一个 hint；空 hints 返回 null', () {
      final selected = primaryIntersectionActionHint(
        reason(
          actionHints: <IntersectionActionHint>[
            hint(actionKey: 'open_object', label: '进入主页'),
          ],
        ),
      );
      expect(selected?.actionKey, 'open_object');
      expect(primaryIntersectionActionHint(reason()), isNull);
    });
  });

  group('收件箱预览卡「可约 N」入口（REQ-008）', () {
    Future<void> pumpCard(
      WidgetTester tester,
      _PreviewIntersectionRepository repo,
    ) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            ...sealedCloudBoundaryOverrides(),
            intersectionRepositoryProvider.overrideWithValue(repo),
          ],
          child: CupertinoApp.router(
            routerConfig: GoRouter(
              initialLocation: '/',
              routes: <GoRoute>[
                GoRoute(
                  path: '/',
                  builder: (_, _) => const CupertinoPageScaffold(
                    child: SingleChildScrollView(
                      child: MyIntersectionInboxCard(isDark: false),
                    ),
                  ),
                ),
                GoRoute(
                  path: '/profile/intersections',
                  builder: (_, _) => const Text('INBOX_LIST'),
                ),
              ],
            ),
          ),
        ),
      );
      // 防卡死模式：有限帧 pump。
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 50));
    }

    IntersectionReason previewReason({
      required String id,
      List<IntersectionActionHint> actionHints =
          const <IntersectionActionHint>[],
    }) {
      return intersectionReasonFixture(
        kind: 'coWishlistedEntity',
        dimension: 'location',
        intersectionClass: 'fact',
        intersectionId: id,
        objectKind: 'place',
        actionTargetId: 'entity_$id',
        primaryText: '你们都想去黄龙',
        primarySpans: <IntersectionTextSpan>[
          intersectionTextSpanFixture(text: '你们都想去黄龙', role: 'plain'),
        ],
        actionHints: actionHints,
      );
    }

    testWidgets('存在可行动交集时展示「可约 N」入口并可进入详情页', (tester) async {
      final repo = _PreviewIntersectionRepository(
        items: <IntersectionReason>[
          previewReason(
            id: 'a',
            actionHints: <IntersectionActionHint>[
              hint(isPrimary: true),
            ],
          ),
          previewReason(id: 'b'),
        ],
      );
      await pumpCard(tester, repo);
      expect(
        find.byKey(const ValueKey<String>('my-intersections-actionable-entry')),
        findsOneWidget,
      );
      expect(
        find.text(DiscoveryFeedText.intersectionActionableEntry(1)),
        findsOneWidget,
      );
      await tester.tap(
        find.byKey(const ValueKey<String>('my-intersections-actionable-entry')),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 50));
      expect(find.text('INBOX_LIST'), findsOneWidget);
    });

    testWidgets('无可行动交集时不渲染「可约」入口（诚实不虚标）', (tester) async {
      final repo = _PreviewIntersectionRepository(
        items: <IntersectionReason>[previewReason(id: 'a')],
      );
      await pumpCard(tester, repo);
      expect(
        find.byKey(const ValueKey<String>('my-intersections-actionable-entry')),
        findsNothing,
      );
    });
  });
}

/// 收件箱预览替身：回放固定 preview items 与摘要。
final class _PreviewIntersectionRepository implements IntersectionRepository {
  _PreviewIntersectionRepository({required this.items});

  final List<IntersectionReason> items;

  @override
  Future<List<IntersectionReason>> listMyIntersections({
    String? dimension,
    String? filter,
    String? sourceRef,
    String? timeBucket,
    String? cursor,
    int limit = 50,
  }) async => items;

  @override
  Future<IntersectionInboxSummary> getMyIntersectionSummary() async =>
      intersectionInboxSummaryFixture(totalCount: items.length);

  @override
  Future<List<IntersectionReason>> getObjectIntersections({
    required String objectId,
    required String objectType,
    int limit = 8,
  }) async => const <IntersectionReason>[];
}
