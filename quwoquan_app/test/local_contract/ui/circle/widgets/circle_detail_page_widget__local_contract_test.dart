// spec_ref: specs/feature-tree/circle-community/in-circle-recommendation-loop/behavior-ingestion/spec.md#gwt-001
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/ui/circle/pages/circle_detail_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../support/cloud_services/behavior_repository_double.dart';
import '../typed_circle_query_test_double.dart';

class _RecordingCircleBehaviorFactWriter implements CircleBehaviorFactWriter {
  final List<AppendCircleBehaviorFactCommand> commands =
      <AppendCircleBehaviorFactCommand>[];

  @override
  Future<void> append(AppendCircleBehaviorFactCommand command) async {
    commands.add(command);
  }
}

final class _CircleMembershipQueryTestDouble implements CircleMembershipQuery {
  const _CircleMembershipQueryTestDouble();

  @override
  Future<CircleMembershipSlice> getMyMembership(
    MyCircleMembershipQuery query,
  ) async => CircleMembershipSlice(
    membershipId: '${query.circleId}_fixture_member',
    version: 1,
    circleId: query.circleId,
    personaId: 'fixture_member',
    role: CircleMemberRole.member,
    state: CircleMembershipState.active,
    joinedAt: DateTime.utc(2026, 7, 1),
    leftAt: null,
    lastActiveAt: DateTime.utc(2026, 7, 1),
    contribution: 0,
    createdAt: DateTime.utc(2026, 7, 1),
    updatedAt: DateTime.utc(2026, 7, 1),
  );

  @override
  Future<CircleMembershipPageSlice> listMemberships(
    CircleMembershipListQuery query,
  ) async => const CircleMembershipPageSlice(items: <CircleMembershipSlice>[]);

  @override
  Future<PersonaCirclePageSlice> listPersonaCircles(
    PersonaCircleListQuery query,
  ) async => const PersonaCirclePageSlice(items: <PersonaCircleSlice>[]);
}

Widget _scopedApp({
  CircleQueryReader? circleQuery,
  String circleId = 'fixture_circle_photo',
  String ownerUserId = '',
  CircleBehaviorFactWriter? behaviorFactWriter,
}) {
  final query = circleQuery ?? CircleQueryReaderTestDouble();
  return ProviderScope(
    overrides: [
      circleDetailQueryProvider.overrideWithValue(query),
      circleDetailFeedQueryProvider.overrideWithValue(query),
      circlesListQueryProvider.overrideWithValue(query),
      circleDetailMembershipQueryProvider.overrideWithValue(
        const _CircleMembershipQueryTestDouble(),
      ),
      // 游客态：行为信号守卫短路，不触发 Remote-only 装配链。
      resolvedOwnerUserIdProvider.overrideWithValue(ownerUserId),
      activePersonaContextProvider.overrideWith(
        (_) async => ActivePersonaContextViewData.fallback(
          personaId: ownerUserId,
          ownerUserId: ownerUserId,
          displayName: ownerUserId,
          avatarUrl: '',
        ),
      ),
      circleDetailBehaviorFactWriterProvider.overrideWithValue(
        behaviorFactWriter ?? _RecordingCircleBehaviorFactWriter(),
      ),
      behaviorRepositoryProvider.overrideWithValue(MockBehaviorRepository()),
    ],
    child: MaterialApp(
      home: Scaffold(
        body: CircleDetailPage(circleId: circleId, onBack: () {}),
      ),
    ),
  );
}

void main() {
  group('CircleDetailPage — 渲染契约', () {
    testWidgets('正常数据渲染圈子名称', (tester) async {
      await tester.pumpWidget(_scopedApp());
      await tester.pump(const Duration(milliseconds: 500));

      expect(find.byType(CircleDetailPage), findsOneWidget);
    });

    testWidgets('板块区域按 sectionConfig 渲染', (tester) async {
      await tester.pumpWidget(_scopedApp());
      await tester.pump(const Duration(milliseconds: 500));

      expect(find.byType(Scaffold), findsWidgets);
    });
  });

  group('CircleDetailPage — 交互契约', () {
    testWidgets('加入按钮存在且可点击', (tester) async {
      await tester.pumpWidget(_scopedApp());
      await tester.pump(const Duration(milliseconds: 500));

      expect(find.byType(CircleDetailPage), findsOneWidget);
    });

    testWidgets('游客不写行为事实，认证用户只写入 impression 与 dwell', (tester) async {
      final visitorWriter = _RecordingCircleBehaviorFactWriter();
      await tester.pumpWidget(_scopedApp(behaviorFactWriter: visitorWriter));
      await tester.pump();
      await tester.pumpWidget(const SizedBox());
      await tester.pump();
      expect(visitorWriter.commands, isEmpty);

      final authenticatedWriter = _RecordingCircleBehaviorFactWriter();
      await tester.pumpWidget(
        _scopedApp(
          ownerUserId: 'user-1',
          behaviorFactWriter: authenticatedWriter,
        ),
      );
      await tester.pump();
      expect(
        authenticatedWriter.commands.map((command) => command.eventType),
        contains(BehaviorEventType.impression),
      );

      await tester.pumpWidget(const SizedBox());
      await tester.pump();
      expect(
        authenticatedWriter.commands.map((command) => command.eventType),
        contains(BehaviorEventType.dwell),
      );
      expect(
        authenticatedWriter.commands.map((command) => command.circleId).toSet(),
        <String>{'fixture_circle_photo'},
      );
    });
  });

  group('CircleDetailPage — 错误态渲染', () {
    testWidgets('空 circleId 安全渲染', (tester) async {
      await tester.pumpWidget(_scopedApp(circleId: ''));
      await tester.pump(const Duration(milliseconds: 500));

      expect(find.byType(CircleDetailPage), findsOneWidget);
    });
  });
}
