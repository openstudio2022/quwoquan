import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_membership/application/public/circle_membership_ports.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_membership/presentation/profile_circles_tab.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/profile_mode.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class _PersonaCircleQuery implements PersonaCircleMembershipQuery {
  _PersonaCircleQuery(this.result);

  final Future<PersonaCirclePageSlice> result;
  PersonaCircleListQuery? lastQuery;

  @override
  Future<PersonaCirclePageSlice> listPersonaCircles(
    PersonaCircleListQuery query,
  ) {
    lastQuery = query;
    return result;
  }
}

Widget _testApp(
  _PersonaCircleQuery query, {
  ProfileMode mode = ProfileMode.mine,
}) {
  return ProviderScope(
    child: CupertinoApp(
      home: ProfileCirclesTab(
        mode: mode,
        userId: 'persona-001',
        isDark: false,
        membershipQuery: query,
      ),
    ),
  );
}

PersonaCircleSlice _circle() {
  final timestamp = DateTime.utc(2026, 8, 6);
  return PersonaCircleSlice(
    circleId: 'circle-001',
    name: '旅行摄影圈',
    ownerPersonaId: 'owner-001',
    memberCount: 12,
    postCount: 7,
    weeklyActiveCount: 3,
    status: CircleStatus.active,
    visibility: CircleVisibility.public,
    joinPolicy: CircleJoinPolicy.open,
    kind: CircleKind.interest,
    displaySubjectType: CircleDisplaySubjectType.circle,
    followEnabled: true,
    createdAt: timestamp,
    updatedAt: timestamp,
  );
}

void main() {
  testWidgets('通过公开 query seam 保留 loading 到 empty 终态', (tester) async {
    final completer = Completer<PersonaCirclePageSlice>();
    final query = _PersonaCircleQuery(completer.future);

    await tester.pumpWidget(_testApp(query));

    expect(find.byType(AppRequestFeedback), findsOneWidget);
    expect(query.lastQuery?.personaId, 'persona-001');
    expect(query.lastQuery?.limit, 100);

    completer.complete(PersonaCirclePageSlice(items: <PersonaCircleSlice>[]));
    await tester.pump();
    await tester.pump();

    expect(find.text('还没加入圈子'), findsOneWidget);
    expect(find.text('去发现圈子'), findsOneWidget);
  });

  testWidgets('query 失败保留 section error feedback 终态', (tester) async {
    final completer = Completer<PersonaCirclePageSlice>();
    final query = _PersonaCircleQuery(completer.future);

    await tester.pumpWidget(_testApp(query));
    completer.completeError(StateError('query failed'));
    await tester.pump();

    expect(find.byType(AppRequestFeedback), findsOneWidget);
    expect(find.text('还没加入圈子'), findsNothing);
  });

  testWidgets('query 成功渲染服务端确认的圈子 slice', (tester) async {
    final query = _PersonaCircleQuery(
      Future<PersonaCirclePageSlice>.value(
        PersonaCirclePageSlice(items: <PersonaCircleSlice>[_circle()]),
      ),
    );

    await tester.pumpWidget(_testApp(query, mode: ProfileMode.other));
    await tester.pump();

    expect(find.text('旅行摄影圈'), findsOneWidget);
    expect(find.text('7 创作'), findsOneWidget);
    expect(find.text('Ta 还没加入圈子'), findsNothing);
  });
}
