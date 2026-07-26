// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/spec.md#sit-001
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/widgets/error_states/app_error_states.dart';
import 'package:quwoquan_app/ui/discovery/widgets/following_subject_strip.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class _FakeFollowingSubjectFacet
    implements FollowingSubjectQuery, FollowedSubjectVisitCommandWriter {
  _FakeFollowingSubjectFacet(this.items);

  final List<FollowingSubjectResult> items;
  final List<MarkFollowedSubjectVisitedCommand> marked =
      <MarkFollowedSubjectVisitedCommand>[];

  @override
  Future<FollowingSubjectSlice> listFollowingSubjects(
    ListFollowingSubjectsQuery query,
  ) async {
    final subjectType = query.subjectType?.trim() ?? '';
    return FollowingSubjectSlice(
      items: items
          .where(
            (item) => subjectType.isEmpty || item.subjectType == subjectType,
          )
          .take(query.limit)
          .toList(growable: false),
    );
  }

  @override
  Future<FollowedSubjectVisitResult> markFollowedSubjectVisited(
    MarkFollowedSubjectVisitedCommand command,
  ) async {
    marked.add(command);
    return FollowedSubjectVisitResult(
      subjectId: command.subjectId,
      subjectType: command.subjectType,
      lastVisitedAt: command.visitedAt.toUtc(),
      hasUnreadChanges: false,
    );
  }
}

final class _FailingFollowingSubjectFacet
    implements FollowingSubjectQuery, FollowedSubjectVisitCommandWriter {
  @override
  Future<FollowingSubjectSlice> listFollowingSubjects(
    ListFollowingSubjectsQuery query,
  ) {
    throw StateError('following subject query failed');
  }

  @override
  Future<FollowedSubjectVisitResult> markFollowedSubjectVisited(
    MarkFollowedSubjectVisitedCommand command,
  ) {
    throw StateError('unreachable');
  }
}

FollowingSubjectResult _subject({
  required String id,
  required String type,
  required bool unread,
}) {
  return FollowingSubjectResult(
    subjectId: id,
    subjectType: type,
    displayName: switch (type) {
      'user' => '旅行摄影师',
      'circle' => '四川旅行圈',
      'homepage' => '九寨沟',
      _ => '未知主体',
    },
    targetRouteId: type,
    targetObjectId: id,
    followedAt: DateTime.utc(2026, 5, 20, 8),
    unreadChangeCount: unread ? 1 : 0,
    hasUnreadChanges: unread,
  );
}

List<Override> _overrides(_FakeFollowingSubjectFacet facet) {
  return <Override>[
    followingSubjectQueryProvider.overrideWithValue(facet),
    followedSubjectVisitCommandWriterProvider.overrideWithValue(facet),
  ];
}

void main() {
  testWidgets('FollowingSubjectStrip shows unread red dots', (tester) async {
    final facet = _FakeFollowingSubjectFacet(<FollowingSubjectResult>[
      _subject(id: 'user_a', type: 'user', unread: true),
      _subject(id: 'circle_a', type: 'circle', unread: false),
      _subject(id: 'home_a', type: 'homepage', unread: true),
    ]);

    await tester.pumpWidget(
      ProviderScope(
        overrides: _overrides(facet),
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

  testWidgets('tap subject writes one nonempty client request id', (
    tester,
  ) async {
    final facet = _FakeFollowingSubjectFacet(<FollowingSubjectResult>[
      _subject(id: 'user_a', type: 'user', unread: true),
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

    await tester.tap(find.text('旅行摄影师'));
    await tester.pump();

    expect(opened?.subjectId, equals('user_a'));
    expect(facet.marked.single.subjectId, equals('user_a'));
    expect(facet.marked.single.clientRequestId, isNotEmpty);
  });

  testWidgets('empty list shows following subject empty copy', (tester) async {
    final facet = _FakeFollowingSubjectFacet(<FollowingSubjectResult>[]);

    await tester.pumpWidget(
      ProviderScope(
        overrides: _overrides(facet),
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

  testWidgets('query failure renders retryable error instead of empty state', (
    tester,
  ) async {
    final facet = _FailingFollowingSubjectFacet();

    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          followingSubjectQueryProvider.overrideWithValue(facet),
          followedSubjectVisitCommandWriterProvider.overrideWithValue(facet),
        ],
        child: const CupertinoApp(home: FollowingSubjectStrip(isDark: false)),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text(UITextConstants.followingSubjectEmptyTitle), findsNothing);
    expect(find.byType(AppSectionErrorState), findsOneWidget);
  });
}
