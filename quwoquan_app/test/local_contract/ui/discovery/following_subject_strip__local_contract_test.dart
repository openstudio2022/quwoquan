// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/spec.md#sit-001
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/widgets/error_states/app_error_states.dart';
import 'package:quwoquan_app/content/content/post/presentation/following_subject_strip.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class _FakeFollowingSubjectFacet
    implements FollowingSubjectQuery, FollowedSubjectVisitCommandWriter {
  _FakeFollowingSubjectFacet(this.items);

  final List<FollowingSubjectItemView> items;
  final List<MarkFollowedSubjectVisitedCommand> marked =
      <MarkFollowedSubjectVisitedCommand>[];

  @override
  Future<FollowingSubjectSlice> listFollowingSubjects(
    ListFollowingSubjectsQuery query,
  ) async {
    return FollowingSubjectSlice(
      items: items
          .where(
            (item) =>
                query.subjectType == null ||
                item.subjectType == query.subjectType,
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

FollowingSubjectItemView _subject({
  required String id,
  required FollowSubjectKind type,
  required bool unread,
}) {
  return FollowingSubjectItemView(
    subjectId: id,
    subjectType: type,
    displayName: switch (type) {
      FollowSubjectKind.persona => '旅行摄影师',
      FollowSubjectKind.circle => '四川旅行圈',
      FollowSubjectKind.homepage => '九寨沟',
      FollowSubjectKind.location => '川西',
    },
    targetRouteId: type.wireName,
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
    final facet = _FakeFollowingSubjectFacet(<FollowingSubjectItemView>[
      _subject(id: 'user_a', type: FollowSubjectKind.persona, unread: true),
      _subject(id: 'circle_a', type: FollowSubjectKind.circle, unread: false),
      _subject(id: 'home_a', type: FollowSubjectKind.homepage, unread: true),
    ]);

    await tester.pumpWidget(
      ProviderScope(
        overrides: _overrides(facet),
        child: const CupertinoApp(home: FollowingSubjectStrip(isDark: false)),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text(DiscoveryText.followingSubjectStripTitle), findsOneWidget);
    expect(find.text('旅行摄影师'), findsOneWidget);
    expect(find.text('四川旅行圈'), findsOneWidget);
    expect(find.text('九寨沟'), findsOneWidget);
    expect(find.byType(FollowingSubjectUnreadDot), findsNWidgets(2));
    expect(
      find.byKey(
        const ValueKey<String>('following-subject-type-persona-user_a'),
      ),
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
    final facet = _FakeFollowingSubjectFacet(<FollowingSubjectItemView>[
      _subject(id: 'user_a', type: FollowSubjectKind.persona, unread: true),
    ]);
    FollowingSubjectItemView? opened;

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
    final facet = _FakeFollowingSubjectFacet(<FollowingSubjectItemView>[]);

    await tester.pumpWidget(
      ProviderScope(
        overrides: _overrides(facet),
        child: const CupertinoApp(home: FollowingSubjectStrip(isDark: false)),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text(DiscoveryText.followingSubjectEmptyTitle), findsOneWidget);
    expect(
      find.text(DiscoveryText.followingSubjectEmptySubtitle),
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

    expect(find.text(DiscoveryText.followingSubjectEmptyTitle), findsNothing);
    expect(find.byType(AppSectionErrorState), findsOneWidget);
  });
}
