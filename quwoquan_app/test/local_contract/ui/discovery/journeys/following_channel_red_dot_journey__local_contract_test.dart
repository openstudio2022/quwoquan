// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/spec.md#sit-001
// 关注频道红点旅程（UAT）：
//   Given 关注频道内有带未读变化的关注对象
//   When 用户点击该对象进入详情
//   Then 服务端 mark-visited 水位推进，红点在频道刷新后清除且不复现
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/discovery/widgets/following_subject_strip.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Test-only typed facet: one command updates the same query projection that
/// renders the following-channel red dot.
final class _StatefulFollowingSubjectFacet
    implements FollowingSubjectQuery, FollowedSubjectVisitCommandWriter {
  _StatefulFollowingSubjectFacet(List<FollowingSubjectResult> seed)
    : _items = List<FollowingSubjectResult>.from(seed);

  final List<FollowingSubjectResult> _items;
  final List<String> markedClientRequestIds = <String>[];

  @override
  Future<FollowingSubjectSlice> listFollowingSubjects(
    ListFollowingSubjectsQuery query,
  ) async {
    return FollowingSubjectSlice(
      items: List<FollowingSubjectResult>.unmodifiable(_items),
    );
  }

  @override
  Future<FollowedSubjectVisitResult> markFollowedSubjectVisited(
    MarkFollowedSubjectVisitedCommand command,
  ) async {
    markedClientRequestIds.add(command.clientRequestId ?? '');
    final index = _items.indexWhere(
      (item) =>
          item.subjectId == command.subjectId &&
          item.subjectType == command.subjectType,
    );
    if (index >= 0) {
      final current = _items[index];
      _items[index] = FollowingSubjectResult(
        subjectId: current.subjectId,
        subjectType: current.subjectType,
        displayName: current.displayName,
        avatarUrl: current.avatarUrl,
        coverUrl: current.coverUrl,
        subtitle: current.subtitle,
        targetRouteId: current.targetRouteId,
        targetObjectId: current.targetObjectId,
        followedAt: current.followedAt,
        lastVisitedAt: command.visitedAt.toUtc(),
        latestChangedAt: current.latestChangedAt,
        unreadChangeCount: 0,
        hasUnreadChanges: false,
        latestChangeReason: current.latestChangeReason,
      );
    }
    return FollowedSubjectVisitResult(
      subjectId: command.subjectId,
      subjectType: command.subjectType,
      lastVisitedAt: command.visitedAt.toUtc(),
      hasUnreadChanges: false,
    );
  }
}

FollowingSubjectResult _seedSubject({
  required String id,
  required FollowSubjectKind type,
  required String displayName,
  required bool unread,
}) {
  return FollowingSubjectResult(
    subjectId: id,
    subjectType: type,
    displayName: displayName,
    targetRouteId: type.wireValue,
    targetObjectId: id,
    followedAt: DateTime.utc(2026, 5, 20, 8),
    unreadChangeCount: unread ? 2 : 0,
    hasUnreadChanges: unread,
  );
}

List<Override> _overrides(_StatefulFollowingSubjectFacet facet) {
  return <Override>[
    followingSubjectQueryProvider.overrideWithValue(facet),
    followedSubjectVisitCommandWriterProvider.overrideWithValue(facet),
  ];
}

void main() {
  testWidgets('关注频道红点点击后清除且刷新不复现（UAT 旅程）', (tester) async {
    final facet = _StatefulFollowingSubjectFacet(<FollowingSubjectResult>[
      _seedSubject(
        id: 'homepage_emeishan',
        type: FollowSubjectKind.homepage,
        displayName: '峨眉山',
        unread: true,
      ),
      _seedSubject(
        id: 'user_photographer',
        type: FollowSubjectKind.persona,
        displayName: '旅行摄影师',
        unread: false,
      ),
    ]);
    FollowingSubjectResult? opened;

    await tester.pumpWidget(
      ProviderScope(
        overrides: _overrides(facet),
        child: CupertinoApp(
          home: FollowingSubjectStrip(
            isDark: false,
            onSubjectOpen: (item) => opened = item,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    // Given：未读主体带红点。
    expect(find.byType(FollowingSubjectUnreadDot), findsOneWidget);

    // When：点击带红点的关注对象。
    await tester.tap(find.text('峨眉山'));
    await tester.pumpAndSettle();

    // Then：跳转触发 + 同一 typed command 更新 query 投影，红点清除。
    expect(opened?.subjectId, 'homepage_emeishan');
    expect(facet.markedClientRequestIds, hasLength(1));
    expect(facet.markedClientRequestIds.single, isNotEmpty);
    expect(find.byType(FollowingSubjectUnreadDot), findsNothing);

    // And：频道重建（模拟回到首页刷新）后红点不复现——水位已持久到 query 投影。
    await tester.pumpWidget(
      ProviderScope(
        overrides: _overrides(facet),
        child: const CupertinoApp(home: FollowingSubjectStrip(isDark: false)),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.byType(FollowingSubjectUnreadDot), findsNothing);
    expect(find.text('峨眉山'), findsOneWidget);
  });
}
