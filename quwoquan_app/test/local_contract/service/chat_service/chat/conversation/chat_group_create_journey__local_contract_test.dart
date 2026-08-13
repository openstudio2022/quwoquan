import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/start_group_chat_page.dart';

import '../../../../../support/service/chat_service/chat/conversation/chat_repository_facets_typed_double.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_repository_facet_overrides.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_seed_refs.dart';

void main() {
  testWidgets('从圈子来源选择互关成员后原子建群并进入新会话', (tester) async {
    final baseline = ChatTestFacets();
    final candidate = (await baseline.contact.listGroupCandidates(
      limit: 1,
    )).single;
    final currentUserId = chatCurrentUserProfileId();
    final circleConversationId = 'fixture_circle_source_conversation';

    List<Map<String, dynamic>> sourceMembers() => <Map<String, dynamic>>[
      <String, dynamic>{
        'id': '${circleConversationId}_owner',
        'conversationId': circleConversationId,
        'userId': currentUserId,
        'displayName': '当前用户',
        'role': 'owner',
        'memberType': 'user',
      },
      <String, dynamic>{
        'id': '${circleConversationId}_friend',
        'conversationId': circleConversationId,
        'userId': candidate.userId,
        'displayName': candidate.displayName,
        'avatarUrl': candidate.avatarUrl,
        'role': 'member',
        'memberType': 'user',
      },
    ];

    final facets = ChatTestFacets(
      seedConversations: <Map<String, dynamic>>[
        <String, dynamic>{
          'id': circleConversationId,
          'type': 'group',
          'title': '摄影圈交流群',
          'status': 'active',
          'circleId': 'fixture_circle_photo',
          'memberCount': 2,
          'maxSeq': 0,
          'avatarUrl': '',
          'lastMessagePreview': '欢迎加入摄影圈',
          'lastMessageTime': '2026-07-20T12:00:00Z',
        },
      ],
      seedMembers: <String, List<Map<String, dynamic>>>{
        circleConversationId: sourceMembers(),
      },
    );
    final router = GoRouter(
      initialLocation: AppRoutePaths.startGroupChat,
      routes: <RouteBase>[
        GoRoute(
          path: AppRoutePaths.startGroupChat,
          builder: (context, state) =>
              StartGroupChatPage(onBack: () => context.pop()),
        ),
        GoRoute(
          path: '/chat/:id',
          builder: (context, state) => CupertinoPageScaffold(
            child: Center(
              child: Text('conversation:${state.pathParameters['id'] ?? ''}'),
            ),
          ),
        ),
      ],
    );
    addTearDown(router.dispose);

    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          ...chatTestRepositoryOverrides(facets: facets),
          currentUserIdProvider.overrideWithValue(currentUserId),
        ],
        child: MaterialApp.router(routerConfig: router),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text(ChatText.startGroupChatPickFromCircle));
    await tester.pumpAndSettle();
    expect(find.text('摄影圈交流群'), findsOneWidget);

    await tester.tap(
      find.byKey(
        const ValueKey<String>(
          'start-group-picker-row-fixture_circle_source_conversation',
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(
      find.byKey(
        ValueKey<String>('start-group-candidate-row-${candidate.userId}'),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('${ChatText.selectAction}（1）'));
    await tester.pumpAndSettle();

    expect(find.text(ChatText.startGroupChatSelectedCount(1)), findsOneWidget);
    await tester.tap(find.text(ChatText.startGroupChatActionCount(1)));
    await tester.pumpAndSettle();

    expect(
      find.textContaining('conversation:fixture_conv_created_'),
      findsOneWidget,
    );
    final inbox = await facets.inbox.listInbox(limit: 100);
    expect(
      inbox.any((item) => item.id.startsWith('fixture_conv_created_')),
      isTrue,
    );
    await tester.pump(const Duration(seconds: 3));
    await tester.pumpAndSettle();
  });
}
