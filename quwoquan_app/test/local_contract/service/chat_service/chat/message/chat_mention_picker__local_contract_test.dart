import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/chat/chat_mention_text_editing_controller.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/chat_mention_picker.dart';
import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart';

void main() {
  testWidgets('选择器排除自己与 assistant，并把服务端查询结果映射为稳定 ID', (tester) async {
    final queries = <String>[];
    ChatInputMentionCandidate? selected;

    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) => CupertinoButton(
            child: const Text('open'),
            onPressed: () async {
              selected = await ChatMentionPicker.show(
                context,
                currentUserId: 'user_me',
                allowMentionAll: false,
                searchMembers: (query) async {
                  queries.add(query);
                  return <ConversationMemberListRow>[
                    ConversationMemberListRow(
                      userId: 'user_me',
                      userHandle: 'user_me',
                      displayName: '我',
                      avatarUrl: '',
                      role: 'member',
                      memberType: 'user',
                      joinedAt: null,
                      isCurrentUser: true,
                    ),
                    ConversationMemberListRow(
                      userId: 'assistant',
                      userHandle: 'assistant',
                      displayName: '小趣',
                      avatarUrl: '',
                      role: 'member',
                      memberType: 'assistant',
                      joinedAt: null,
                      isCurrentUser: false,
                    ),
                    ConversationMemberListRow(
                      userId: 'user_zhang',
                      userHandle: 'user_zhang',
                      displayName: '张三',
                      avatarUrl: '',
                      role: 'member',
                      memberType: 'user',
                      joinedAt: null,
                      isCurrentUser: false,
                    ),
                  ];
                },
              );
            },
          ),
        ),
      ),
    );

    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    expect(queries, <String>['']);
    expect(find.text('我'), findsNothing);
    expect(find.text('小趣'), findsNothing);
    expect(find.text('张三'), findsOneWidget);
    expect(find.text(ChatText.mentionAll), findsNothing);

    await tester.enterText(find.byType(CupertinoSearchTextField), '张');
    await tester.pump(const Duration(milliseconds: 300));
    await tester.pumpAndSettle();
    expect(queries.last, '张');

    await tester.tap(find.text('张三'));
    await tester.pumpAndSettle();
    expect(selected?.id, 'user_zhang');
    expect(selected?.displayName, '张三');
  });

  testWidgets('只有 owner/admin 入口显示 @所有人并返回保留目标', (tester) async {
    ChatInputMentionCandidate? selected;
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) => CupertinoButton(
            child: const Text('open'),
            onPressed: () async {
              selected = await ChatMentionPicker.show(
                context,
                currentUserId: 'owner',
                allowMentionAll: true,
                searchMembers: (_) async => const <ConversationMemberListRow>[],
              );
            },
          ),
        ),
      ),
    );

    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    expect(find.text(ChatText.mentionAll), findsOneWidget);
    await tester.tap(find.text(ChatText.mentionAll));
    await tester.pumpAndSettle();

    expect(selected?.id, '__all__');
    expect(selected?.kind, ChatInputMentionKind.all);
  });
}
