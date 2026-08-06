import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/presentation/circle_stats_page.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_group/application/public/circle_group_ports.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_membership/application/public/circle_membership_ports.dart';
import 'package:quwoquan_app/design_system/providers/theme_provider.dart';
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
}
