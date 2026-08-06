import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_repository_typed_double.dart';
import 'package:quwoquan_app/runtime/di/realtime_message_handler.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/di/chat_message_application_dependencies.dart';

import '../../../../../support/service/realtime_gateway/realtime/connection/connection_typed_double.dart';

void main() {
  final memberAddedEvent = FixtureRealtimeEventCatalog.eventsForConversation(
    'fixture_conv_group',
  ).single;

  testWidgets('ConversationMemberAdded 不伪造未持久化 Message', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          chatRepositoryCompositionProvider.overrideWithValue(
            MockChatRepository(),
          ),
        ],
        child: Consumer(
          builder: (context, ref, _) {
            WidgetsBinding.instance.addPostFrameCallback((_) {
              RealtimeMessageHandler(ref.read).handle(memberAddedEvent);
            });
            return const MaterialApp(home: SizedBox());
          },
        ),
      ),
    );

    await tester.pump();
    await tester.pump(const Duration(milliseconds: 220));

    final messages = tester
        .container()
        .read(chatMessageTimelineProvider('fixture_conv_group'))
        .messages;
    expect(messages.any((message) => message.type == 'system'), isFalse);

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(milliseconds: 50));
  });

  testWidgets('ConversationMemberAdded 触发成员列表 load', (tester) async {
    final repo = _CountingMembersRepo();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [chatRepositoryCompositionProvider.overrideWithValue(repo)],
        child: Consumer(
          builder: (context, ref, _) {
            WidgetsBinding.instance.addPostFrameCallback((_) {
              RealtimeMessageHandler(ref.read).handle(memberAddedEvent);
            });
            return const MaterialApp(home: SizedBox());
          },
        ),
      ),
    );

    await tester.pump();
    await tester.pump(const Duration(milliseconds: 200));
    expect(repo.listMembersCallCount, greaterThanOrEqualTo(1));
  });
}

class _CountingMembersRepo extends MockChatRepository {
  int listMembersCallCount = 0;

  @override
  Future<List<ConversationMemberListRow>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = ChatListConversationMembersQuery.defaultLimit,
    String? role,
    String? sort,
  }) async {
    listMembersCallCount++;
    return super.listMembers(
      conversationId: conversationId,
      cursor: cursor,
      limit: limit,
      role: role,
      sort: sort,
    );
  }
}
