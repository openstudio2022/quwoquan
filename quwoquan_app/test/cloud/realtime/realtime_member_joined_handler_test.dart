import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/realtime/realtime_message_handler.dart';
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
            message.type == 'system' && message.content == '契约新成员加入了群聊',
      ),
      isTrue,
    );

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(milliseconds: 50));
  });
}
