import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/design_system/actions/app_follow_button.dart';
import 'package:quwoquan_app/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/app_providers_app_state.dart'
    show currentUserIdProvider;
import 'package:quwoquan_app/runtime/di/client_state_sync_dependencies.dart';
import 'package:quwoquan_app/runtime/di/user_relationship_state_dependencies.dart';
import 'package:quwoquan_app/runtime/transport/state_sync/client_state_sync.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/presentation/circle_stats_page.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_group/application/public/circle_group_ports.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_membership/application/public/circle_membership_ports.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/user_profile_route_extra.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class _RecordingCircleGroupQueries implements CircleGroupQueries {
  CircleGroupListQuery? lastListQuery;

  @override
  Future<CircleGroupSlice> get(CircleGroupQuery query) =>
      throw UnsupportedError('get is outside this page contract');

  @override
  Future<CircleGroupPageSlice> list(CircleGroupListQuery query) async {
    lastListQuery = query;
    final now = DateTime.utc(2026, 8, 6);
    return CircleGroupPageSlice(
      items: <CircleGroupSlice>[
        CircleGroupSlice(
          groupId: 'group-001',
          version: 1,
          circleId: query.circleId,
          groupType: CircleGroupType.publicGroup,
          name: '测试群聊',
          visibility: CircleGroupVisibility.public,
          joinPolicy: CircleGroupJoinPolicy.applyOnly,
          conversationId: 'conversation-001',
          storageEnabled: true,
          noticeEnabled: true,
          isDefaultPublicGroup: true,
          status: CircleGroupStatus.active,
          memberCount: 12,
          createdAt: now,
          updatedAt: now,
        ),
      ],
    );
  }

  @override
  Future<CircleGroupPageSlice> search(CircleGroupSearchQuery query) =>
      throw UnsupportedError('search is outside this page contract');
}

final class _RecordingCircleMembershipQueries
    implements CircleMembershipQueries {
  CircleMembershipListQuery? lastListQuery;

  @override
  Future<CircleMembershipSlice> getMyMembership(
    MyCircleMembershipQuery query,
  ) => throw UnsupportedError('getMyMembership is outside this page contract');

  @override
  Future<CircleMembershipPageSlice> listMemberships(
    CircleMembershipListQuery query,
  ) async {
    lastListQuery = query;
    final now = DateTime.utc(2026, 8, 6);
    return CircleMembershipPageSlice(
      items: <CircleMembershipSlice>[
        CircleMembershipSlice(
          membershipId: 'membership-001',
          version: 1,
          circleId: query.circleId,
          personaId: 'fixture_persona',
          role: CircleMemberRole.member,
          state: CircleMembershipState.active,
          joinedAt: now,
          lastActiveAt: now,
          contribution: 0,
          createdAt: now,
          updatedAt: now,
        ),
      ],
    );
  }

  @override
  Future<PersonaCirclePageSlice> listPersonaCircles(
    PersonaCircleListQuery query,
  ) => throw UnsupportedError(
    'listPersonaCircles is outside this page contract',
  );
}

Widget _testApp({
  required String type,
  required _RecordingCircleGroupQueries groupQueries,
  required _RecordingCircleMembershipQueries membershipQueries,
  required List<String> visitedCircleIds,
}) => ProviderScope(
  overrides: [isDarkProvider.overrideWithValue(false)],
  child: CupertinoApp(
    home: CircleStatsPage(
      circleId: 'circle-001',
      type: type,
      recordVisit: (circleId) async => visitedCircleIds.add(circleId),
      groupQueries: groupQueries,
      membershipQueries: membershipQueries,
    ),
  ),
);

class _AuthenticatedStatsSession extends AuthSessionController {
  @override
  AuthSessionState build() => const AuthSessionState(
    status: AuthSessionStatus.authenticated,
    accessToken: 'circle-stats-test-token',
    refreshToken: 'circle-stats-test-refresh-token',
    ownerId: 'viewer_001',
    activePersonaId: 'viewer_001',
    accountState: 'active',
    identityOrigin: 'widget-test',
    installId: 'circle-stats-widget-test-install',
  );
}

const _statsSyncConfig = ClientStateSyncConfig(
  flushDelay: Duration(hours: 1),
  retryDelay: Duration(minutes: 5),
  maxBatchSize: 20,
  maxPendingAge: Duration(hours: 72),
  flushOnForegroundResume: true,
  flushOnNetworkRecovered: true,
);

/// 带路由与真实关注链路的宿主：断言导航与 outbox 意图。
Widget _routedApp({
  required String type,
  required _RecordingCircleGroupQueries groupQueries,
  required _RecordingCircleMembershipQueries membershipQueries,
  required GoRouter router,
  String viewerId = 'viewer_001',
}) {
  Map<String, dynamic>? persisted;
  return ProviderScope(
    overrides: <Override>[
      isDarkProvider.overrideWithValue(false),
      authSessionControllerProvider.overrideWith(
        _AuthenticatedStatsSession.new,
      ),
      currentUserIdProvider.overrideWithValue(viewerId),
      clientStateSyncRuntimeDependenciesProvider.overrideWithValue(
        ClientStateSyncRuntimeDependencies(
          readConfig: () => _statsSyncConfig,
          readPersistedState: () async => persisted,
          writePersistedState: (next) async => persisted = next,
          executeEntry: (_) async {},
        ),
      ),
    ],
    child: CupertinoApp.router(routerConfig: router),
  );
}

GoRouter _statsRouter({
  required String type,
  required _RecordingCircleGroupQueries groupQueries,
  required _RecordingCircleMembershipQueries membershipQueries,
  required void Function(String route, Object? extra) onNavigated,
}) => GoRouter(
  initialLocation: '/stats',
  routes: <RouteBase>[
    GoRoute(
      path: '/stats',
      builder: (_, _) => CircleStatsPage(
        circleId: 'circle-001',
        type: type,
        recordVisit: (_) async {},
        groupQueries: groupQueries,
        membershipQueries: membershipQueries,
      ),
    ),
    GoRoute(
      path: AppRoutePaths.userProfilePathTemplate.replaceAll(
        '{userHandle}',
        ':userHandle',
      ),
      builder: (_, state) {
        onNavigated(
          'userProfile:${state.pathParameters['userHandle']}',
          state.extra,
        );
        return const Text('PROFILE', textDirection: TextDirection.ltr);
      },
    ),
    GoRoute(
      path: AppRoutePaths.chatDetailPathTemplate.replaceAll('{id}', ':id'),
      builder: (_, state) {
        onNavigated('chatDetail:${state.pathParameters['id']}', state.extra);
        return const Text('CHAT', textDirection: TextDirection.ltr);
      },
    ),
  ],
);

void main() {
  testWidgets('群聊列表只通过 CircleGroupQueries 公开查询面加载', (tester) async {
    final groupQueries = _RecordingCircleGroupQueries();
    final membershipQueries = _RecordingCircleMembershipQueries();
    final visitedCircleIds = <String>[];

    await tester.pumpWidget(
      _testApp(
        type: 'groups',
        groupQueries: groupQueries,
        membershipQueries: membershipQueries,
        visitedCircleIds: visitedCircleIds,
      ),
    );
    await tester.pumpAndSettle();

    expect(groupQueries.lastListQuery?.circleId, 'circle-001');
    expect(groupQueries.lastListQuery?.limit, 100);
    expect(membershipQueries.lastListQuery, isNull);
    expect(visitedCircleIds, <String>['circle-001']);
    expect(find.text('测试群聊'), findsOneWidget);
    expect(find.text('12 人'), findsOneWidget);
  });

  testWidgets('成员列表只通过 CircleMembershipQueries 公开查询面加载', (tester) async {
    final groupQueries = _RecordingCircleGroupQueries();
    final membershipQueries = _RecordingCircleMembershipQueries();
    final visitedCircleIds = <String>[];

    await tester.pumpWidget(
      _testApp(
        type: 'members',
        groupQueries: groupQueries,
        membershipQueries: membershipQueries,
        visitedCircleIds: visitedCircleIds,
      ),
    );
    await tester.pumpAndSettle();

    expect(membershipQueries.lastListQuery?.circleId, 'circle-001');
    expect(membershipQueries.lastListQuery?.limit, 100);
    expect(groupQueries.lastListQuery, isNull);
    expect(visitedCircleIds, <String>['circle-001']);
    expect(find.text('fixture_persona'), findsOneWidget);
  });

  testWidgets('成员行点击进入用户主页并携带 persona 快照', (tester) async {
    final navigations = <String>[];
    Object? capturedExtra;
    final router = _statsRouter(
      type: 'members',
      groupQueries: _RecordingCircleGroupQueries(),
      membershipQueries: _RecordingCircleMembershipQueries(),
      onNavigated: (route, extra) {
        navigations.add(route);
        capturedExtra = extra;
      },
    );
    addTearDown(router.dispose);
    await tester.pumpWidget(
      _routedApp(
        type: 'members',
        groupQueries: _RecordingCircleGroupQueries(),
        membershipQueries: _RecordingCircleMembershipQueries(),
        router: router,
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(
      find.byKey(
        const ValueKey<String>('circle-stats-member-row-fixture_persona'),
      ),
    );
    await tester.pumpAndSettle();

    expect(navigations, <String>['userProfile:fixture_persona']);
    final extra = capturedExtra as UserProfileRouteExtra?;
    expect(extra?.safePersonaId, 'fixture_persona');
  });

  testWidgets('成员关注为真实关注意图：本地关系态更新且写入持久 outbox', (tester) async {
    final router = _statsRouter(
      type: 'members',
      groupQueries: _RecordingCircleGroupQueries(),
      membershipQueries: _RecordingCircleMembershipQueries(),
      onNavigated: (_, _) {},
    );
    addTearDown(router.dispose);
    await tester.pumpWidget(
      _routedApp(
        type: 'members',
        groupQueries: _RecordingCircleGroupQueries(),
        membershipQueries: _RecordingCircleMembershipQueries(),
        router: router,
      ),
    );
    await tester.pumpAndSettle();

    final container = ProviderScope.containerOf(
      tester.element(find.byType(CircleStatsPage)),
    );
    expect(
      container
          .read(userRelationshipStateProvider)
          .isFollowing('fixture_persona'),
      isFalse,
    );

    await tester.tap(
      find.byKey(
        const ValueKey<String>('circle-stats-member-follow-fixture_persona'),
      ),
    );
    await tester.pumpAndSettle();

    expect(
      container
          .read(userRelationshipStateProvider)
          .isFollowing('fixture_persona'),
      isTrue,
    );
    final outboxEntry = container
        .read(clientStateSyncOutboxProvider)
        .entryFor(
          objectType: 'profile',
          objectId: 'fixture_persona',
          intentType: 'follow',
        );
    expect(outboxEntry, isNotNull);
    expect(find.byType(AppFollowButton), findsOneWidget);
  });

  testWidgets('查看者自己的成员行不显示关注按钮', (tester) async {
    final router = _statsRouter(
      type: 'members',
      groupQueries: _RecordingCircleGroupQueries(),
      membershipQueries: _RecordingCircleMembershipQueries(),
      onNavigated: (_, _) {},
    );
    addTearDown(router.dispose);
    await tester.pumpWidget(
      _routedApp(
        type: 'members',
        groupQueries: _RecordingCircleGroupQueries(),
        membershipQueries: _RecordingCircleMembershipQueries(),
        router: router,
        viewerId: 'fixture_persona',
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('fixture_persona'), findsOneWidget);
    expect(find.byType(AppFollowButton), findsNothing);
  });

  testWidgets('群聊行绑定会话时点击进入群聊', (tester) async {
    final navigations = <String>[];
    final router = _statsRouter(
      type: 'groups',
      groupQueries: _RecordingCircleGroupQueries(),
      membershipQueries: _RecordingCircleMembershipQueries(),
      onNavigated: (route, _) => navigations.add(route),
    );
    addTearDown(router.dispose);
    await tester.pumpWidget(
      _routedApp(
        type: 'groups',
        groupQueries: _RecordingCircleGroupQueries(),
        membershipQueries: _RecordingCircleMembershipQueries(),
        router: router,
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(
      find.byKey(const ValueKey<String>('circle-stats-group-row-group-001')),
    );
    await tester.pumpAndSettle();

    expect(navigations, <String>['chatDetail:conversation-001']);
  });
}
