import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_conversation_member_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import '../../../support/cloud_services/chat_repository_mock.dart';
import 'package:quwoquan_app/cloud/services/realtime/realtime_message_handler.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/chat/providers/group_home_provider.dart';

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

void main() {
  testWidgets('ConversationRosterUpdated 触发成员列表 load', (tester) async {
    final repo = _CountingMembersRepo();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [chatRepositoryCompositionProvider.overrideWithValue(repo)],
        child: Consumer(
          builder: (context, ref, _) {
            WidgetsBinding.instance.addPostFrameCallback((_) {
              RealtimeMessageHandler(ref.read).handle({
                'type': 'ConversationRosterUpdated',
                'conversationId': 'fixture_conv_group',
              });
            });
            return const MaterialApp(home: SizedBox());
          },
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    expect(repo.listMembersCallCount, greaterThanOrEqualTo(1));
    await tester.pump(const Duration(milliseconds: 200));
  });

  testWidgets('ConversationRosterUpdated invalidate groupHomeProvider', (
    tester,
  ) async {
    final repo = _CountingMembersRepo();
    late ProviderContainer container;
    await tester.pumpWidget(
      ProviderScope(
        overrides: [chatRepositoryCompositionProvider.overrideWithValue(repo)],
        child: Consumer(
          builder: (context, ref, _) {
            container = ProviderScope.containerOf(context);
            return const MaterialApp(home: SizedBox());
          },
        ),
      ),
    );
    await tester.pump();
    await container.read(groupHomeProvider('fixture_conv_group').future);
    RealtimeMessageHandler(
      container.read,
      invalidate: container.invalidate,
    ).handle({
      'type': 'ConversationRosterUpdated',
      'conversationId': 'fixture_conv_group',
    });
    await tester.pump();
    final state = container.read(groupHomeProvider('fixture_conv_group'));
    expect(state.isLoading, isTrue);
    await tester.pump(const Duration(milliseconds: 200));
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(milliseconds: 200));
  });
}
