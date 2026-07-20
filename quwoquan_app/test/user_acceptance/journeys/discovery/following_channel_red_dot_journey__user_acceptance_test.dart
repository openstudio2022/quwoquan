// B3 关注频道红点旅程（UAT）：
//   Given 关注频道内有带未读变化的关注对象
//   When 用户点击该对象进入详情
//   Then 服务端 mark-visited 水位推进，红点在频道刷新后清除且不复现
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/user/following_subject_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/discovery/widgets/following_subject_strip.dart';

/// 有状态 fake：mark-visited 后同一主体的未读位持久清除，
/// 模拟服务端 FollowedSubjectVisitState 水位（重放安全）。
class _StatefulFollowingSubjectRepository
    implements FollowingSubjectRepository {
  _StatefulFollowingSubjectRepository(List<FollowingSubjectItem> seed)
    : _items = List<FollowingSubjectItem>.from(seed);

  final List<FollowingSubjectItem> _items;
  final List<String> markedClientRequestIds = <String>[];

  @override
  Future<List<FollowingSubjectItem>> listFollowingSubjects({
    String? cursor,
    int limit = 20,
    FollowingSubjectType? subjectType,
  }) async {
    return _items
        .where((item) => subjectType == null || item.subjectType == subjectType)
        .take(limit)
        .toList(growable: false);
  }

  @override
  Future<FollowingSubjectVisitResult> markFollowingSubjectVisited({
    required FollowingSubjectItem subject,
    DateTime? visitedAt,
    String? clientRequestId,
  }) async {
    markedClientRequestIds.add(clientRequestId ?? '');
    final visitedIso = (visitedAt ?? DateTime.utc(2026, 6, 2)).toIso8601String();
    final index = _items.indexWhere(
      (item) =>
          item.subjectId == subject.subjectId &&
          item.subjectType == subject.subjectType,
    );
    if (index >= 0) {
      _items[index] = _items[index].copyWith(
        hasUnreadChanges: false,
        unreadChangeCount: 0,
        lastVisitedAt: visitedIso,
      );
    }
    return FollowingSubjectVisitResult(
      subjectId: subject.subjectId,
      subjectType: subject.subjectType,
      lastVisitedAt: visitedIso,
      hasUnreadChanges: false,
    );
  }
}

FollowingSubjectItem _seedSubject({
  required String id,
  required FollowingSubjectType type,
  required String displayName,
  required bool unread,
}) {
  return FollowingSubjectItem(
    subjectId: id,
    subjectType: type,
    displayName: displayName,
    targetRouteId: type.name,
    targetObjectId: id,
    followedAt: '2026-05-20T08:00:00Z',
    hasUnreadChanges: unread,
    unreadChangeCount: unread ? 2 : 0,
  );
}

void main() {
  testWidgets('关注频道红点点击后清除且刷新不复现（UAT 旅程）', (tester) async {
    final repo = _StatefulFollowingSubjectRepository([
      _seedSubject(
        id: 'homepage_emeishan',
        type: FollowingSubjectType.homepage,
        displayName: '峨眉山',
        unread: true,
      ),
      _seedSubject(
        id: 'user_photographer',
        type: FollowingSubjectType.user,
        displayName: '旅行摄影师',
        unread: false,
      ),
    ]);
    FollowingSubjectItem? opened;

    await tester.pumpWidget(
      ProviderScope(
        overrides: [followingSubjectRepositoryProvider.overrideWithValue(repo)],
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

    // Then：跳转触发 + mark-visited 上报 + 红点清除。
    expect(opened?.subjectId, 'homepage_emeishan');
    expect(repo.markedClientRequestIds, hasLength(1));
    expect(find.byType(FollowingSubjectUnreadDot), findsNothing);

    // And：频道重建（模拟回到首页刷新）后红点不复现——水位已服务端持久。
    await tester.pumpWidget(
      ProviderScope(
        overrides: [followingSubjectRepositoryProvider.overrideWithValue(repo)],
        child: const CupertinoApp(home: FollowingSubjectStrip(isDark: false)),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.byType(FollowingSubjectUnreadDot), findsNothing);
    expect(find.text('峨眉山'), findsOneWidget);
  });
}
