// spec_ref: specs/feature-tree/chat-conversation/group-creation-member-management/group-member-roster-version-sync/spec.md#gwt-002
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/di/conversation_members_provider.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation_membership/presentation/group_member_search_page.dart';
import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart';

import '../../../../../support/service/chat_service/chat/conversation/chat_repository_typed_double.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_seed_refs.dart';

const _conversationId = 'fixture_conv_group';

void main() {
  testWidgets(
    'authoritative refresh failure retains confirmed roster and retry recovers',
    (tester) async {
      final repository = _RefreshableMembersRepository();
      final container = ProviderContainer(
        overrides: <Override>[
          chatRepositoryCompositionProvider.overrideWithValue(repository),
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
}

final class _RefreshableMembersRepository extends MockChatRepository {
  bool failReads = false;

  @override
  Future<List<ConversationMemberListRow>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = 20,
    String? role,
    String? sort,
  }) {
    if (failReads) {
      throw Exception('membership refresh unavailable');
    }
    return super.listMembers(
      conversationId: conversationId,
      cursor: cursor,
      limit: limit,
      role: role,
      sort: sort,
    );
  }
}
