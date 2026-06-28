import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_conversation_member_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/cloud/services/realtime/realtime_message_handler.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/chat/providers/chat_message_provider.dart';

void main() {
  testWidgets('MemberJoined 插入系统消息', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        child: Consumer(
          builder: (context, ref, _) {
            WidgetsBinding.instance.addPostFrameCallback((_) {
              RealtimeMessageHandler(ref.read).handle({
                'type': 'MemberJoined',
                'conversationId': 'fixture_conv_group',
                'payload': {
                  'userId': 'fixture_user_new_member',
                  'userName': '契约新成员',
                  'displayName': '契约新成员',
                  'timestamp': '2026-06-10T14:05:00Z',
                },
              });
            });
            return const MaterialApp(home: SizedBox());
          },
        ),
      ),
    );

    await tester.pump();
    await tester.pump(const Duration(milliseconds: 220));

    final messages = tester.container()
        .read(chatMessageProvider('fixture_conv_group'))
        .messages;
    expect(
      messages.any(
        (message) =>
            message.type == 'system' && message.content == '契约新成员加入了讨论',
      ),
      isTrue,
    );
    expect(
      messages.any((message) => (message.content ?? '').contains('群聊')),
      isFalse,
    );

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(milliseconds: 50));
  });

  testWidgets('MemberJoined 触发成员列表 load', (tester) async {
    final repo = _CountingMembersRepo();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [chatRepositoryProvider.overrideWithValue(repo)],
        child: Consumer(
          builder: (context, ref, _) {
            WidgetsBinding.instance.addPostFrameCallback((_) {
              RealtimeMessageHandler(ref.read).handle({
                'type': 'MemberJoined',
                'conversationId': 'conv_002',
                'payload': {
                  'userId': 'user_099',
                  'displayName': '契约新成员',
                  'timestamp': '2026-06-10T14:05:00Z',
                },
              });
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
  Future<List<ChatConversationMemberDto>> listMembers({
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
