// spec_ref: specs/feature-tree/chat-conversation/group-creation-member-management/group-member-roster-version-sync/spec.md#gwt-002
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/feedback/app_empty_state.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/feedback/skeleton/app_skeleton.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/di/conversation_members_provider.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation_membership/application/public/chat_member_repository.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation_membership/presentation/group_member_search_page.dart';
import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart';

import '../../../../../support/service/chat_service/chat/conversation/chat_repository_facet_overrides.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_repository_facets_typed_double.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_seed_refs.dart';

const _conversationId = 'fixture_conv_group';

void main() {
  testWidgets(
    'authoritative refresh failure retains confirmed roster and retry recovers',
    (tester) async {
      final repository = _RefreshableMembersRepository();
      final container = ProviderContainer(
        overrides: <Override>[
          ...chatTestRepositoryOverrides(member: repository),
          currentUserIdProvider.overrideWithValue(chatCurrentUserProfileId()),
        ],
      );
      addTearDown(container.dispose);
      final notifier = container.read(
        conversationMembersProvider(_conversationId).notifier,
      );
      expect(await notifier.load(), isTrue);

      await tester.pumpWidget(
        UncontrolledProviderScope(
          container: container,
          child: const MaterialApp(
            home: GroupMemberSearchPage(conversationId: _conversationId),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('契约同伴一'), findsOneWidget);

      repository.failReads = true;
      expect(await notifier.load(), isFalse);
      await tester.pump();
      expect(find.text('契约同伴一'), findsOneWidget);
      expect(find.byType(AppSectionErrorCard), findsOneWidget);

      repository.failReads = false;
      final recoveryAction = find.descendant(
        of: find.byType(AppSectionErrorCard),
        matching: find.byType(CupertinoButton),
      );
      expect(recoveryAction, findsWidgets);
      await tester.tap(recoveryAction.last);
      await tester.pumpAndSettle();

      expect(
        container.read(conversationMembersProvider(_conversationId)).error,
        isNull,
      );
      expect(find.text('契约同伴一'), findsOneWidget);
    },
  );

  _emptyAndSkeletonCases();
}

// spec_ref: specs/feature-tree/chat-conversation/chat-experience-optimization/spec.md#open-002
void _emptyAndSkeletonCases() {
  testWidgets('成员搜索无匹配呈现标准空态组件', (tester) async {
    final container = ProviderContainer(
      overrides: <Override>[
        ...chatTestRepositoryOverrides(),
        currentUserIdProvider.overrideWithValue(chatCurrentUserProfileId()),
      ],
    );
    addTearDown(container.dispose);
    final notifier = container.read(
      conversationMembersProvider(_conversationId).notifier,
    );
    expect(await notifier.load(), isTrue);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(
          home: GroupMemberSearchPage(conversationId: _conversationId),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byType(CupertinoSearchTextField),
      '不存在的成员关键字',
    );
    await tester.pumpAndSettle();

    expect(
      find.byType(AppEmptyState),
      findsOneWidget,
      reason: '成员搜索无匹配必须使用 design system 标准空态',
    );
  });

  testWidgets('成员搜索初始加载呈现共享骨架屏', (tester) async {
    final container = ProviderContainer(
      overrides: <Override>[
        ...chatTestRepositoryOverrides(member: _SlowMembersRepository()),
        currentUserIdProvider.overrideWithValue(chatCurrentUserProfileId()),
      ],
    );
    addTearDown(container.dispose);
    final notifier = container.read(
      conversationMembersProvider(_conversationId).notifier,
    );
    final loading = notifier.load();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(
          home: GroupMemberSearchPage(conversationId: _conversationId),
        ),
      ),
    );
    await tester.pump();
    expect(
      find.byType(AppSkeletonListRows),
      findsOneWidget,
      reason: '成员加载中必须使用共享列表骨架',
    );
    await tester.pump(const Duration(milliseconds: 400));
    await loading;
    await tester.pumpAndSettle();
  });
}

final class _SlowMembersRepository extends Fake
    implements ChatMemberRepository {
  final ChatMemberRepository _delegate = ChatTestFacets().member;

  @override
  Future<List<ConversationMemberListRow>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = 20,
    String? role,
    MemberListSort? sort,
  }) async {
    await Future<void>.delayed(const Duration(milliseconds: 300));
    return _delegate.listMembers(
      conversationId: conversationId,
      cursor: cursor,
      limit: limit,
      role: role,
      sort: sort,
    );
  }
}

final class _RefreshableMembersRepository extends Fake
    implements ChatMemberRepository {
  final ChatMemberRepository _delegate = ChatTestFacets().member;
  bool failReads = false;

  @override
  Future<List<ConversationMemberListRow>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = 20,
    String? role,
    MemberListSort? sort,
  }) {
    if (failReads) {
      throw Exception('membership refresh unavailable');
    }
    return _delegate.listMembers(
      conversationId: conversationId,
      cursor: cursor,
      limit: limit,
      role: role,
      sort: sort,
    );
  }
}
