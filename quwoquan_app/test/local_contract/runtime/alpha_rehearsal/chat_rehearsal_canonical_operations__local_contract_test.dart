// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-008
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/handlers/chat_handlers.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_ports.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_store.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  var sequence = 0;
  final now = DateTime.utc(2026, 9, 13);
  Future<Object?> call(
    AlphaRehearsalStore store,
    String actor,
    String operation, {
    Map<String, String> path = const {},
    Map<String, String> query = const {},
    Map<String, Object?> body = const {},
  }) {
    final contract = appCloudOperationContracts[operation]!;
    return const ChatRehearsalHandler().handle(
      RehearsalInvocation(
        operation: contract,
        payload: CloudOperationRequestPayload(
          pathParameters: path,
          queryParameters: query,
          body: body,
        ),
        context: CloudOperationInvocationContext(
          surfaceId: 'test',
          clientPageId: 'test',
          actor: CloudOperationActorContext(personaId: actor),
        ),
        store: store,
        now: () => now.add(Duration(seconds: sequence)),
        nextId: (prefix) => '$prefix${++sequence}',
      ),
    );
  }

  test('群成员治理、权限与重启读回', () async {
    final persistence = MemoryRehearsalPersistence();
    final store = AlphaRehearsalStore(persistence: persistence);
    final group = await call(
      store,
      'owner',
      'chat.conversation.CreateConversation',
      body: {
        'type': 'group',
        'initialMemberIds': ['admin', 'member'],
      },
    ) as Map;
    final id = group['conversationId'] as String;
    await call(
      store,
      'owner',
      'chat.conversation_membership.UpdateGroupAdmins',
      path: {'conversationId': id},
      body: {
        'adminIds': ['admin'],
      },
    );
    await call(
      store,
      'admin',
      'chat.conversation_membership.AddMembers',
      path: {'conversationId': id},
      body: {
        'userIds': ['new'],
      },
    );
    await expectLater(
      call(
        store,
        'member',
        'chat.conversation_membership.RemoveMember',
        path: {'conversationId': id, 'userId': 'new'},
      ),
      throwsA(isA<CloudException>()),
    );
    await call(
      store,
      'owner',
      'chat.conversation_membership.TransferOwnership',
      path: {'conversationId': id},
      body: {'newOwnerId': 'admin'},
    );
    await call(
      store,
      'owner',
      'chat.conversation_membership.LeaveConversation',
      path: {'conversationId': id},
    );
    final restored = AlphaRehearsalStore(persistence: persistence);
    await restored.ensureLoaded();
    final members = await call(
      restored,
      'admin',
      'chat.conversation_membership.ListMembers',
      path: {'conversationId': id},
      query: {'limit': '2'},
    ) as Map;
    expect((members['items'] as List), hasLength(2));
    expect(members['nextCursor'], isNotNull);
  });
  test('消息同步、撤回、回执与 inbox 状态一致', () async {
    final store = AlphaRehearsalStore();
    final conversation = await call(
      store,
      'a',
      'chat.conversation.CreateConversation',
      body: {
        'type': 'direct',
        'initialMemberIds': ['b'],
      },
    ) as Map;
    final id = conversation['conversationId'] as String;
    final first = await call(
      store,
      'a',
      'chat.message.SendMessage',
      path: {'conversationId': id},
      body: {'content': 'one'},
    ) as Map;
    await call(
      store,
      'a',
      'chat.message.SendMessage',
      path: {'conversationId': id},
      body: {'content': 'two'},
    );
    final sync = await call(
      store,
      'b',
      'chat.message.SyncMessages',
      path: {'conversationId': id},
      body: {'afterSeq': 0, 'limit': 1},
    ) as Map;
    expect(sync['hasMore'], isTrue);
    await call(
      store,
      'b',
      'chat.conversation_user_state.MarkAsRead',
      path: {'conversationId': id, 'messageId': first['messageId'] as String},
    );
    final receipts = await call(
      store,
      'a',
      'chat.message_receipt_fact.GetReceipts',
      path: {'conversationId': id, 'messageId': first['messageId'] as String},
    ) as Map;
    expect((receipts['items'] as List).single['userId'], 'b');
    await call(
      store,
      'a',
      'chat.message.RecallMessage',
      path: {'conversationId': id, 'messageId': first['messageId'] as String},
    );
    final inbox = await call(
      store,
      'b',
      'chat.chat_inbox_view.ListInbox',
      query: {'limit': '50'},
    ) as Map;
    expect((inbox['items'] as List).single['unreadCount'], 1);
  });
}
