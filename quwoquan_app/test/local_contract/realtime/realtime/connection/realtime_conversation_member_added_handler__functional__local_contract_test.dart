import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart';
import '../../../../support/cloud_services/chat_repository_mock.dart';
import 'package:quwoquan_app/realtime/realtime/connection/presentation/realtime_message_handler.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/chat/providers/chat_message_provider.dart';

import '../../../../support/realtime/realtime/connection/connection_typed_double.dart';

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
        .read(chatMessageProvider('fixture_conv_group'))
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
    int limit = CloudApiDefaults.pageLimit,
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
