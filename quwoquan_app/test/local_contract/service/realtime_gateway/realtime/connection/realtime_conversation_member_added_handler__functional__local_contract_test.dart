import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart';
import 'package:quwoquan_app/runtime/di/realtime_message_handler.dart';
import 'package:quwoquan_app/runtime/di/chat_message_application_dependencies.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation_membership/application/public/chat_member_repository.dart';

import '../../../../../support/service/realtime_gateway/realtime/connection/connection_typed_double.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_repository_facet_overrides.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_repository_facets_typed_double.dart';

void main() {
  final memberAddedEvent = FixtureRealtimeEventCatalog.eventsForConversation(
    'fixture_conv_group',
  ).single;

  testWidgets('ConversationMemberAdded 不伪造未持久化 Message', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [...chatTestRepositoryOverrides()],
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
    final repo = _CountingMembersRepo(ChatTestFacets().member);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [...chatTestRepositoryOverrides(member: repo)],
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

class _CountingMembersRepo implements ChatMemberRepository {
  _CountingMembersRepo(this._delegate);

  final ChatMemberRepository _delegate;
  int listMembersCallCount = 0;

  @override
  Future<List<ConversationMemberListRow>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = ChatListConversationMembersQuery.defaultLimit,
    String? role,
    MemberListSort? sort,
  }) async {
    listMembersCallCount++;
    return _delegate.listMembers(
      conversationId: conversationId,
      cursor: cursor,
      limit: limit,
      role: role,
      sort: sort,
    );
  }

  @override
  Future<List<ConversationMemberListRow>> searchMembers({
    required String conversationId,
    required String query,
    required int limit,
  }) => _delegate.searchMembers(
    conversationId: conversationId,
    query: query,
    limit: limit,
  );

  @override
  Future<void> addMembers({
    required String conversationId,
    required List<String> userIds,
  }) => _delegate.addMembers(conversationId: conversationId, userIds: userIds);

  @override
  Future<void> removeMember({
    required String conversationId,
    required String userId,
  }) => _delegate.removeMember(conversationId: conversationId, userId: userId);

  @override
  Future<void> leaveConversation(String conversationId) =>
      _delegate.leaveConversation(conversationId);

  @override
  Future<List<String>> listMemberUserIds(String conversationId) =>
      _delegate.listMemberUserIds(conversationId);

  @override
  Future<void> inviteAssistant({required String conversationId}) =>
      _delegate.inviteAssistant(conversationId: conversationId);

  @override
  Future<void> removeAssistant({required String conversationId}) =>
      _delegate.removeAssistant(conversationId: conversationId);
}
