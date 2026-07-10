import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/user/following_subject_repository.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/discovery/widgets/following_subject_strip.dart';

class _FakeFollowingSubjectRepository implements FollowingSubjectRepository {
  _FakeFollowingSubjectRepository(this.items);

  final List<FollowingSubjectItem> items;
  final List<FollowingSubjectItem> marked = <FollowingSubjectItem>[];

  @override
  Future<List<FollowingSubjectItem>> listFollowingSubjects({
    String? cursor,
    int limit = 20,
    FollowingSubjectType? subjectType,
  }) async {
    return items
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
    marked.add(subject);
    return FollowingSubjectVisitResult(
      subjectId: subject.subjectId,
      subjectType: subject.subjectType,
      lastVisitedAt: DateTime(2026).toIso8601String(),
      hasUnreadChanges: false,
    );
  }
}

FollowingSubjectItem _subject({
  required String id,
  required FollowingSubjectType type,
  required bool unread,
}) {
  return FollowingSubjectItem(
    subjectId: id,
    subjectType: type,
    displayName: switch (type) {
      FollowingSubjectType.user => '旅行摄影师',
      FollowingSubjectType.circle => '四川旅行圈',
      FollowingSubjectType.homepage => '九寨沟',
    },
    targetRouteId: type.name,
    targetObjectId: id,
    followedAt: '2026-05-20T08:00:00Z',
    hasUnreadChanges: unread,
    unreadChangeCount: unread ? 1 : 0,
  );
}

void main() {
  testWidgets('FollowingSubjectStrip shows unread red dots', (tester) async {
    final repo = _FakeFollowingSubjectRepository([
      _subject(id: 'user_a', type: FollowingSubjectType.user, unread: true),
      _subject(
        id: 'circle_a',
        type: FollowingSubjectType.circle,
        unread: false,
      ),
      _subject(id: 'home_a', type: FollowingSubjectType.homepage, unread: true),
    ]);

    await tester.pumpWidget(
      ProviderScope(
        overrides: [followingSubjectRepositoryProvider.overrideWithValue(repo)],
        child: const CupertinoApp(home: FollowingSubjectStrip(isDark: false)),
      ),
    );
    await tester.pumpAndSettle();

    expect(
      find.text(UITextConstants.followingSubjectStripTitle),
      findsOneWidget,
    );
    expect(find.text('旅行摄影师'), findsOneWidget);
    expect(find.text('四川旅行圈'), findsOneWidget);
    expect(find.text('九寨沟'), findsOneWidget);
    expect(find.byType(FollowingSubjectUnreadDot), findsNWidgets(2));
    expect(
      find.byKey(const ValueKey<String>('following-subject-type-user-user_a')),
      findsOneWidget,
    );
    expect(
      find.byKey(
        const ValueKey<String>('following-subject-type-circle-circle_a'),
      ),
      findsOneWidget,
    );
    expect(
      find.byKey(
        const ValueKey<String>('following-subject-type-homepage-home_a'),
      ),
      findsOneWidget,
    );
  });

  testWidgets('tap subject marks it visited', (tester) async {
    final repo = _FakeFollowingSubjectRepository([
      _subject(id: 'user_a', type: FollowingSubjectType.user, unread: true),
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

    await tester.tap(find.text('旅行摄影师'));
    await tester.pump();

    expect(opened?.subjectId, equals('user_a'));
    expect(repo.marked.single.subjectId, equals('user_a'));
  });

  testWidgets('empty list shows following subject empty copy', (tester) async {
    final repo = _FakeFollowingSubjectRepository(const []);

    await tester.pumpWidget(
      ProviderScope(
        overrides: [followingSubjectRepositoryProvider.overrideWithValue(repo)],
        child: const CupertinoApp(home: FollowingSubjectStrip(isDark: false)),
      ),
    );
    await tester.pumpAndSettle();

    expect(
      find.text(UITextConstants.followingSubjectEmptyTitle),
      findsOneWidget,
    );
    expect(
      find.text(UITextConstants.followingSubjectEmptySubtitle),
      findsOneWidget,
    );
  });
}
