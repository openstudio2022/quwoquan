import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/cloud/services/user/user_profile_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/chat/pages/start_group_chat_page.dart';
import 'package:quwoquan_app/ui/chat/providers/chat_contacts_rows_provider.dart';
import 'package:quwoquan_app/ui/chat/providers/chat_inbox_provider.dart';
import '../../../common/chat/chat_mock_seed_refs.dart';

void _suppressImageErrors() {
  final original = FlutterError.onError;
  FlutterError.onError = (FlutterErrorDetails details) {
    final message = details.exception.toString();
    if (message.contains('HTTP request failed') ||
        message.contains('NetworkImageLoadException')) {
      return;
    }
    original?.call(details);
  };
}

Future<void> _pumpStartGroupChatPage(
  WidgetTester tester, {
  required ProviderContainer container,
  String? conversationId,
}) async {
  await tester.pumpWidget(
    UncontrolledProviderScope(
      container: container,
      child: MaterialApp.router(
        routerConfig: GoRouter(
          initialLocation: '/chat/start-group',
          routes: [
            GoRoute(
              path: '/chat/start-group',
              builder: (context, state) => StartGroupChatPage(
                conversationId: conversationId,
                onBack: () {},
              ),
            ),
            GoRoute(
              path: '/chat/:id',
              builder: (_, state) =>
                  Scaffold(body: Text('chat:${state.pathParameters['id']}')),
            ),
          ],
        ),
      ),
    ),
  );
  await tester.pump();
  await tester.pump(const Duration(seconds: 1));
}

ProviderContainer _buildContainer(MockChatRepository repository) {
  final container = ProviderContainer(
    overrides: [
      chatRepositoryProvider.overrideWithValue(repository),
      userProfileRepositoryProvider.overrideWithValue(
        const MockUserProfileRepository(),
      ),
    ],
  );
  addTearDown(container.dispose);
  return container;
}

Map<String, dynamic> _groupConversation(
  String id,
  String title, {
  String avatarUrl = '',
  int memberCount = 2,
}) {
  final now = DateTime.utc(2026, 1, 1).toIso8601String();
  return <String, dynamic>{
    '_id': id,
    'id': id,
    'conversationId': id,
    'type': 'group',
    'title': title,
    'avatarUrl': avatarUrl,
    'creatorId': chatCurrentUserProfileId(),
    'maxSeq': 0,
    'memberCount': memberCount,
    'maxGroupSize': 500,
    'receiptEnabled': true,
    'lastMessagePreview': '',
    'lastMessageTime': now,
    'messageCount': 0,
    'status': 'active',
    'createdAt': now,
    'updatedAt': now,
  };
}

Map<String, dynamic> _member(
  String userId, {
  required int order,
  String role = 'member',
  bool isCurrentUser = false,
  String? avatarUrl,
}) {
  return <String, dynamic>{
    'userId': userId,
    'displayName': chatDisplayNameFor(userId),
    'avatarUrl': avatarUrl ?? chatAvatarUrlFor(userId),
    'role': role,
    'isCurrentUser': isCurrentUser,
    'joinedAt': DateTime.utc(
      2026,
      1,
      1,
    ).add(Duration(seconds: order)).toIso8601String(),
  };
}

void main() {
  testWidgets('选中联系人后可提交并跳转到新会话', (tester) async {
    _suppressImageErrors();

    final container = _buildContainer(MockChatRepository());
    await _pumpStartGroupChatPage(tester, container: container);

    expect(find.byType(StartGroupChatPage), findsOneWidget);
    expect(find.text('发起群聊（1）'), findsNothing);

    await tester.tap(find.byIcon(CupertinoIcons.circle).first);
    await tester.pumpAndSettle();

    expect(find.text('发起群聊（1）'), findsOneWidget);

    await tester.tap(find.text('发起群聊（1）'));
    await tester.pumpAndSettle();

    expect(find.textContaining('chat:conv_new_'), findsOneWidget);
    await tester.pump(const Duration(seconds: 3));
  });

  testWidgets('添加成员向导只展示服务端过滤后的候选成员', (tester) async {
    _suppressImageErrors();

    final repository = MockChatRepository(
      seedConversations: <Map<String, dynamic>>[
        _groupConversation('conv_existing', '当前群'),
        _groupConversation('conv_source', '候选群'),
      ],
      seedMembers: <String, List<Map<String, dynamic>>>{
        'conv_existing': <Map<String, dynamic>>[
          _member(
            chatCurrentUserProfileId(),
            order: 0,
            role: 'owner',
            isCurrentUser: true,
          ),
          _member('user_002', order: 1),
        ],
        'conv_source': <Map<String, dynamic>>[
          _member(
            chatCurrentUserProfileId(),
            order: 0,
            role: 'owner',
            isCurrentUser: true,
          ),
          _member('user_002', order: 1),
          _member('user_003', order: 2),
        ],
      },
    );
    final container = _buildContainer(repository);
    await _pumpStartGroupChatPage(
      tester,
      container: container,
      conversationId: 'conv_existing',
    );

    expect(find.text('李明'), findsNothing);
    expect(find.text('张华'), findsOneWidget);
    expect(find.text('李青'), findsOneWidget);

    await tester.ensureVisible(find.text('张华').last);
    await tester.pumpAndSettle();
    await tester.tap(
      find
          .ancestor(
            of: find.text('张华').last,
            matching: find.byType(CupertinoButton),
          )
          .last,
    );
    await tester.pumpAndSettle();

    expect(find.text('${UITextConstants.addMember}（1）'), findsOneWidget);
  });

  testWidgets('建群成功后同时刷新消息列表与趣群列表', (tester) async {
    _suppressImageErrors();

    final container = _buildContainer(MockChatRepository());
    final keepAlive = container.listen(chatInboxListProvider, (_, _) {});
    addTearDown(keepAlive.close);
    await _pumpStartGroupChatPage(tester, container: container);

    await container.read(chatInboxListProvider.notifier).refresh();
    final beforeInboxIds = container
        .read(chatInboxListProvider)
        .items
        .map((item) => item.id)
        .toSet();
    final beforeFunGroups = await container.read(
      chatContactsRowsForSubTabProvider(
        UITextConstants.contactsTabFunGroup,
      ).future,
    );

    await tester.tap(find.byIcon(CupertinoIcons.circle).first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('发起群聊（1）'));
    await tester.pumpAndSettle();

    final inboxItems = container.read(chatInboxListProvider).items;
    expect(
      inboxItems.any(
        (item) =>
            item.id.startsWith('conv_new_') &&
            !beforeInboxIds.contains(item.id),
      ),
      isTrue,
    );
    final afterFunGroups = await container.read(
      chatContactsRowsForSubTabProvider(
        UITextConstants.contactsTabFunGroup,
      ).future,
    );
    expect(afterFunGroups.length, greaterThanOrEqualTo(beforeFunGroups.length));
    expect(
      afterFunGroups.any(
        (row) => (row.conversationId ?? '').startsWith('conv_new_'),
      ),
      isTrue,
    );
    await tester.pump(const Duration(seconds: 3));
    await tester.pumpAndSettle();
  });

}
