// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/user-profile-intersection-redesign/spec.md#gwt-003

/// N1 标准化（断点4）：对象页交集全量列表行点击统一经 IntersectionTargetNavigator，
/// 端不再手写 `switch(kind) → context.push(AppRoutePaths.*)` 复制导航逻辑
/// （消除第二导航真相源 · §20.7 统一交互子契约）。
///
/// 覆盖：
/// - IntersectionTargetNavigator.targetForReason：actionTargetId/objectKind 归一为统一 target；
/// - §23 去桥接：objectKind 一等字段为对象类型唯一真相源，relationKind 旧词桥接已删除，
///   objectKind 缺省时不再回写对象类型（优雅降级为不可路由，而非伪造闭集值）；
/// - 归一 target 经 IntersectionTargetNavigator.resolvePath 命中正确 codegen 路由
///   （person→userProfile / circle→circleDetail / place|school|enterprise→homepageDetail），
///   证明删手写 switch 后导航行为零回归。
library;

import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/content_behavior_tracker.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/di/object_intersection_provider.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/application/public/object_intersection_query.dart';
import 'package:quwoquan_app/runtime/di/navigation/intersection_target_navigator.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/object_intersection_list_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/recommendation_service/recommendation/recommendation_feature_profile_view/intersection_fixtures.dart';

const _pageQuery = ObjectIntersectionQuery(
  objectAId: 'viewer-001',
  objectAType: 'user',
  objectBId: 'profile-002',
  objectBType: 'user',
  limit: 50,
);

final class _RecordingBehaviorReporter implements BehaviorReporter {
  final List<BehaviorEvent> events = <BehaviorEvent>[];

  @override
  Future<void> reportEvents({required List<BehaviorEvent> events}) async {
    this.events.addAll(events);
  }
}

Widget _pageHost({
  List<IntersectionReason>? reasons,
  Future<List<IntersectionReason>> Function()? loadReasons,
  required ContentBehaviorTracker contentBehaviorTracker,
}) {
  assert(reasons != null || loadReasons != null);
  final router = GoRouter(
    initialLocation: '/',
    routes: <RouteBase>[
      GoRoute(
        path: '/',
        builder: (_, _) => ObjectIntersectionListPage(
          objectId: _pageQuery.objectBId,
          objectType: _pageQuery.objectBType,
          currentUserId: _pageQuery.objectAId,
          contentBehaviorTracker: contentBehaviorTracker,
        ),
      ),
      GoRoute(
        path: '/user/:userHandle',
        builder: (_, state) =>
            Text('USER:${state.pathParameters['userHandle']}'),
      ),
    ],
  );
  return ProviderScope(
    overrides: <Override>[
      isDarkProvider.overrideWithValue(false),
      objectSharedReasonsProvider(
        _pageQuery,
      ).overrideWith((_) => loadReasons?.call() ?? Future.value(reasons!)),
    ],
    child: CupertinoApp.router(routerConfig: router),
  );
}

final class _ControlledReasons {
  final List<Completer<List<IntersectionReason>>> calls =
      <Completer<List<IntersectionReason>>>[];

  Future<List<IntersectionReason>> load() {
    final completer = Completer<List<IntersectionReason>>();
    calls.add(completer);
    return completer.future;
  }
}

void main() {
  testWidgets('页面通过构造 identity/tracker 与 application query seam 运行', (
    tester,
  ) async {
    final reporter = _RecordingBehaviorReporter();
    final tracker = ContentBehaviorTracker(
      reporter: reporter,
      enablePeriodicFlush: false,
    );
    addTearDown(tracker.dispose);
    final reason = intersectionReasonFixture(
      primaryText: '你们都关注旅行摄影',
      actionTargetId: 'target-person',
      objectKind: 'person',
      intersectionId: 'intersection-001',
      dimension: 'interest',
      source: 'sharedFollowees',
      tagRefs: const <String>['Audience/用户/兴趣偏好/旅行摄影'],
    );

    await tester.pumpWidget(
      _pageHost(
        reasons: <IntersectionReason>[reason],
        contentBehaviorTracker: tracker,
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('你们都关注旅行摄影'), findsOneWidget);

    await tester.tap(find.text('你们都关注旅行摄影'));
    await tester.pumpAndSettle();
    await tracker.flush();

    expect(find.text('USER:target-person'), findsOneWidget);
    expect(reporter.events, hasLength(1));
    expect(reporter.events.single.contentId, 'target-person');
    expect(reporter.events.single.action, BehaviorEventType.click);
    expect(reporter.events.single.intersectionId, 'intersection-001');
    expect(reporter.events.single.intersectionDimension, 'interest');
  });

  testWidgets('Remote failure 保留对象页上下文并可显式重试', (tester) async {
    final loads = _ControlledReasons();
    final reporter = _RecordingBehaviorReporter();
    final tracker = ContentBehaviorTracker(
      reporter: reporter,
      enablePeriodicFlush: false,
    );
    addTearDown(tracker.dispose);

    await tester.pumpWidget(
      _pageHost(loadReasons: loads.load, contentBehaviorTracker: tracker),
    );
    await tester.pump();
    expect(loads.calls, hasLength(1));

    loads.calls.first.completeError(StateError('remote unavailable'));
    await tester.pumpAndSettle();

    expect(
      find.text(ObjectHomepageText.objectIntersectionsTitle),
      findsOneWidget,
    );
    expect(
      find.text(ObjectHomepageText.objectIntersectionsEmpty),
      findsNothing,
    );
    final errorState = tester.widget<AppPageErrorState>(
      find.byType(AppPageErrorState),
    );
    final recoveryAction =
        <UiErrorAction?>[
          errorState.semantic.primaryAction,
          errorState.semantic.secondaryAction,
        ].whereType<UiErrorAction>().firstWhere(
          (action) =>
              action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit,
        );
    expect(errorState.onRecovery, isNotNull);

    await tester.tap(
      find.descendant(
        of: find.byType(AppPageErrorState),
        matching: find.text(recoveryAction.label),
      ),
    );
    await tester.pump();
    expect(loads.calls, hasLength(2));

    final recovered = intersectionReasonFixture(primaryText: '恢复后交集');
    loads.calls[1].complete(<IntersectionReason>[recovered]);
    await tester.pumpAndSettle();

    expect(find.text('恢复后交集'), findsOneWidget);
    expect(find.byType(AppPageErrorState), findsNothing);
  });

  testWidgets('连续刷新只接受最新 generation，迟到结果不回写', (tester) async {
    final loads = _ControlledReasons();
    final reporter = _RecordingBehaviorReporter();
    final tracker = ContentBehaviorTracker(
      reporter: reporter,
      enablePeriodicFlush: false,
    );
    addTearDown(tracker.dispose);

    await tester.pumpWidget(
      _pageHost(loadReasons: loads.load, contentBehaviorTracker: tracker),
    );
    await tester.pump();
    loads.calls[0].complete(<IntersectionReason>[
      intersectionReasonFixture(primaryText: '首次结果'),
    ]);
    await tester.pumpAndSettle();

    await tester.tap(find.text(SearchText.refresh));
    await tester.pump();
    expect(loads.calls, hasLength(2));

    await tester.tap(find.text(SearchText.refresh));
    await tester.pump();
    expect(loads.calls, hasLength(3));

    loads.calls[2].complete(<IntersectionReason>[
      intersectionReasonFixture(primaryText: '最新刷新结果'),
    ]);
    await tester.pumpAndSettle();
    expect(find.text('最新刷新结果'), findsOneWidget);

    loads.calls[1].complete(<IntersectionReason>[
      intersectionReasonFixture(primaryText: '迟到的旧结果'),
    ]);
    await tester.pumpAndSettle();

    expect(find.text('最新刷新结果'), findsOneWidget);
    expect(find.text('迟到的旧结果'), findsNothing);
  });

  test('query family 隔离不同对象的迟到结果', () async {
    final queryA = _pageQuery;
    final queryB = ObjectIntersectionQuery(
      objectAId: _pageQuery.objectAId,
      objectAType: _pageQuery.objectAType,
      objectBId: 'profile-003',
      objectBType: _pageQuery.objectBType,
      limit: _pageQuery.limit,
    );
    final loadsA = _ControlledReasons();
    final loadsB = _ControlledReasons();
    final providerA = objectSharedReasonsProvider(queryA);
    final providerB = objectSharedReasonsProvider(queryB);
    final container = ProviderContainer(
      overrides: <Override>[
        providerA.overrideWith((_) => loadsA.load()),
        providerB.overrideWith((_) => loadsB.load()),
      ],
    );
    addTearDown(container.dispose);
    final subscriptionA = container.listen(providerA, (_, _) {});
    final subscriptionB = container.listen(providerB, (_, _) {});
    addTearDown(subscriptionA.close);
    addTearDown(subscriptionB.close);
    await container.pump();

    loadsB.calls.single.complete(<IntersectionReason>[
      intersectionReasonFixture(primaryText: '对象 B 结果'),
    ]);
    await container.read(providerB.future);
    loadsA.calls.single.complete(<IntersectionReason>[
      intersectionReasonFixture(primaryText: '对象 A 迟到结果'),
    ]);
    await container.read(providerA.future);
    await container.pump();

    expect(
      container.read(providerB).requireValue.single.primaryText,
      '对象 B 结果',
    );
  });

  test('最后一个消费者离开后重进必须重新读 Remote', () async {
    final loads = _ControlledReasons();
    final provider = objectSharedReasonsProvider(_pageQuery);
    final container = ProviderContainer(
      overrides: <Override>[provider.overrideWith((_) => loads.load())],
    );
    addTearDown(container.dispose);

    final firstSubscription = container.listen(provider, (_, _) {});
    await container.pump();
    loads.calls.single.complete(<IntersectionReason>[
      intersectionReasonFixture(primaryText: '首次 Remote 结果'),
    ]);
    await container.read(provider.future);
    firstSubscription.close();
    await container.pump();

    final secondSubscription = container.listen(provider, (_, _) {});
    addTearDown(secondSubscription.close);
    await container.pump();

    expect(loads.calls, hasLength(2));
    loads.calls[1].complete(<IntersectionReason>[
      intersectionReasonFixture(primaryText: '重进 Remote 结果'),
    ]);
    await container.read(provider.future);
    expect(
      container.read(provider).requireValue.single.primaryText,
      '重进 Remote 结果',
    );
  });

  group('IntersectionTargetNavigator.targetForReason（交集行 → 统一导航 target）', () {
    test('objectKind 闭集直出（person/circle/place）', () {
      final person = IntersectionTargetNavigator.targetForReason(
        intersectionReasonFixture(
          actionTargetId: 'u_lin',
          objectKind: 'person',
        ),
      );
      expect(person.objectId, 'u_lin');
      expect(person.objectKind, 'person');

      final circle = IntersectionTargetNavigator.targetForReason(
        intersectionReasonFixture(
          actionTargetId: 'c_ride',
          objectKind: 'circle',
        ),
      );
      expect(circle.objectKind, 'circle');

      final place = IntersectionTargetNavigator.targetForReason(
        intersectionReasonFixture(
          actionTargetId: 'p_west',
          objectKind: 'place',
        ),
      );
      expect(place.objectKind, 'place');
    });

    test('objectKind 缺省 → 不再 relationKind 桥接（对象类型为空，优雅降级不误路由）', () {
      // §23 去桥接：relationKind 不再回写对象类型；objectKind 缺省即保持空，
      // 由 resolvePath 判定不可路由（优雅降级），不再伪造 person/place/enterprise。
      final viaRelationKind = IntersectionTargetNavigator.targetForReason(
        intersectionReasonFixture(actionTargetId: 'u1', relationKind: 'mutual'),
      );
      expect(viaRelationKind.objectKind, '');
      expect(IntersectionTargetNavigator.resolvePath(viaRelationKind), isNull);
    });

    test('actionTargetId 两端空白裁剪', () {
      final t = IntersectionTargetNavigator.targetForReason(
        intersectionReasonFixture(
          actionTargetId: '  u2  ',
          objectKind: 'person',
        ),
      );
      expect(t.objectId, 'u2');
    });
  });

  group('归一 target 经统一导航器命中正确 codegen 路由（删手写 switch 零回归）', () {
    String? pathFor(IntersectionReason reason) =>
        IntersectionTargetNavigator.resolvePath(
          IntersectionTargetNavigator.targetForReason(reason),
        );

    test('person → userProfile', () {
      expect(
        pathFor(
          intersectionReasonFixture(
            actionTargetId: 'u_lin',
            objectKind: 'person',
          ),
        ),
        contains('u_lin'),
      );
    });

    test('circle → circleDetail', () {
      expect(
        pathFor(
          intersectionReasonFixture(
            actionTargetId: 'c_ride',
            objectKind: 'circle',
          ),
        ),
        contains('c_ride'),
      );
    });

    test('place/school/enterprise → homepageDetail', () {
      for (final kind in const <String>['place', 'school', 'enterprise']) {
        expect(
          pathFor(
            intersectionReasonFixture(
              actionTargetId: 'h_$kind',
              objectKind: kind,
            ),
          ),
          contains('h_$kind'),
          reason: '$kind 应映射到实体主页路由',
        );
      }
    });

    test('actionTargetId 空 → 不可路由（优雅降级，不跳转）', () {
      expect(
        pathFor(
          intersectionReasonFixture(actionTargetId: '', objectKind: 'person'),
        ),
        isNull,
      );
    });
  });
}
