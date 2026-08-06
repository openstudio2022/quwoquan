// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/commercial-remote-only-message-system/spec.md#gwt-001
// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/spec.md#sit-006
// readiness_case: conversation_batch_get_conversations_app_local
// readiness_case: conversation_list_contact_home_app_local
// readiness_case: conversation_list_contacts_app_local
// readiness_case: conversation_list_group_candidates_app_local
// readiness_case: conversation_list_message_home_app_local
// readiness_case: conversation_list_selectable_group_conversations_app_local
// readiness_case: conversation_list_selectable_group_contact_members_app_local
// readiness_case: conversation_update_conversation_title_app_local
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/adapters/contact_remote.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/adapters/conversation_remote.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/adapters/message_home_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  late _RoutingExecutor executor;
  late GeneratedCloudOperationClient client;

  setUp(() {
    executor = _RoutingExecutor();
    client = GeneratedCloudOperationClient(executor);
  });

  test('会话批量与联系人六个查询只经 generated typed client', () async {
    final conversation = RemoteChatConversationQuery(
      client: client,
      invocationContext: _queryContext,
    );
    final contact = RemoteChatContactQuery(
      client: client,
      invocationContext: _queryContext,
    );

    final batch = await conversation.batchGetConversations(
      ChatBatchGetConversationsQuery(
        conversationIds: const <String>['conversation-1'],
      ),
    );
    final home = await contact.listContactHome(
      ChatListContactHomeQuery(filter: 'mutual', limit: 30),
    );
    final contacts = await contact.listContacts(
      ChatListContactsQuery(cursor: 'contacts-cursor', limit: 40),
    );
    final candidates = await contact.listGroupCandidates(
      ChatListGroupCandidatesQuery(conversationId: 'conversation-1', limit: 50),
    );
    final groups = await contact.listSelectableGroupConversations(
      ChatListSelectableGroupConversationsQuery(
        query: '旅行',
        source: SelectableGroupConversationSource.group,
        cursor: 'group-cursor',
        limit: 20,
      ),
    );
    final members = await contact.listSelectableGroupContactMembers(
      ChatListSelectableGroupContactMembersQuery(
        conversationId: 'conversation-1',
        query: '小趣',
        cursor: 'member-cursor',
        limit: 30,
      ),
    );

    expect(batch.items.single.id, 'conversation-1');
    expect(home.items.single.summaryIntersections, <String>['共同关注摄影']);
    expect(contacts.items.single.userId, 'persona-2');
    expect(contacts.items.single.userHandle, 'xiaoq_public');
    expect(candidates.items.single.source, ChatContactSource.mutual);
    expect(groups.items.single.friendMemberCount, 3);
    expect(members.items.single.userId, 'persona-2');
    expect(members.items.single.userHandle, 'xiaoq_public');
    expect(executor.operationIds, <String>[
      AppCloudOperationIds.chatConversationBatchGetConversations,
      AppCloudOperationIds.chatConversationListContactHome,
      AppCloudOperationIds.chatConversationListContacts,
      AppCloudOperationIds.chatConversationListGroupCandidates,
      AppCloudOperationIds.chatConversationListSelectableGroupConversations,
      AppCloudOperationIds.chatConversationListSelectableGroupContactMembers,
    ]);
    expect(executor.payloads.first.body, <String, Object?>{
      'ids': <String>['conversation-1'],
    });
    expect(executor.payloads[1].queryParameters, <String, String>{
      'filter': 'mutual',
      'limit': '30',
    });
    expect(executor.payloads[2].queryParameters, <String, String>{
      'limit': '40',
      'cursor': 'contacts-cursor',
    });
    expect(executor.payloads[4].queryParameters, <String, String>{
      'limit': '20',
      'query': '旅行',
      'source': 'group',
      'cursor': 'group-cursor',
    });
  });

  test('消息首页与会话标题只经 generated typed client', () async {
    final messageHome = RemoteChatMessageHomeQuery(
      client: client,
      invocationContext: _queryContext,
    );
    final conversationWriter = RemoteChatConversationCommandWriter(
      client: client,
      invocationContext: _commandContext,
    );
    final home = await messageHome.listMessageHome(
      ChatListMessageHomeQuery(
        filter: 'unread',
        cursor: 'message-home-cursor',
        limit: 40,
      ),
    );
    final conversation = await conversationWriter.updateConversationTitle(
      ChatUpdateConversationTitleCommand(
        conversationId: 'conversation-1',
        title: '新的讨论名',
      ),
      idempotencyKey: 'title-1',
    );
    expect(home.items.single.notificationId, 'notification-1');
    expect(conversation.id, 'conversation-1');
    expect(executor.operationIds, <String>[
      AppCloudOperationIds.chatConversationListMessageHome,
      AppCloudOperationIds.chatConversationUpdateConversationTitle,
    ]);
    expect(executor.payloads[0].queryParameters, <String, String>{
      'filter': 'unread',
      'limit': '40',
      'cursor': 'message-home-cursor',
    });
    expect(executor.payloads[1].pathParameters, <String, String>{
      'conversationId': 'conversation-1',
    });
    expect(executor.payloads[1].body, <String, Object?>{'title': '新的讨论名'});
  });
}

CloudOperationInvocationContext _queryContext(String clientPageId) {
  return CloudOperationInvocationContext(
    surfaceId: 'chat-contract',
    clientPageId: clientPageId,
    actor: const CloudOperationActorContext(
      accountId: 'account-1',
      personaId: 'persona-1',
    ),
  );
}

CloudOperationInvocationContext _commandContext(
  String clientPageId,
  String idempotencyKey,
) {
  return CloudOperationInvocationContext(
    surfaceId: 'chat-contract',
    clientPageId: clientPageId,
    actor: const CloudOperationActorContext(
      accountId: 'account-1',
      personaId: 'persona-1',
    ),
    idempotencyKey: idempotencyKey,
  );
}

final class _RoutingExecutor implements CloudOperationExecutor {
  final List<String> operationIds = <String>[];
  final List<CloudOperationInvocationContext> contexts =
      <CloudOperationInvocationContext>[];
  final List<CloudOperationRequestPayload> payloads =
      <CloudOperationRequestPayload>[];

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    operationIds.add(operation.canonicalOperationId);
    contexts.add(context);
    payloads.add(requestEncoder());
    return responseDecoder(_responseFor(operation.canonicalOperationId));
  }
}

Object? _responseFor(String operationId) {
  return switch (operationId) {
    AppCloudOperationIds.chatConversationBatchGetConversations =>
      <String, Object?>{
        'items': <Object?>[_conversation],
      },
    AppCloudOperationIds.chatConversationListContactHome => <String, Object?>{
      'items': <Object?>[_contactHome],
    },
    AppCloudOperationIds.chatConversationListContacts => <String, Object?>{
      'items': <Object?>[_contact],
      'nextCursor': null,
    },
    AppCloudOperationIds.chatConversationListGroupCandidates =>
      <String, Object?>{
        'items': <Object?>[_groupCandidate],
      },
    AppCloudOperationIds.chatConversationListMessageHome => <String, Object?>{
      'items': <Object?>[_messageHome],
      'nextCursor': null,
    },
    AppCloudOperationIds.chatConversationUpdateConversationTitle =>
      _conversation,
    AppCloudOperationIds.chatConversationListSelectableGroupConversations =>
      <String, Object?>{
        'items': <Object?>[_selectableGroup],
        'nextCursor': null,
      },
    AppCloudOperationIds.chatConversationListSelectableGroupContactMembers =>
      <String, Object?>{
        'items': <Object?>[_selectableMember],
        'nextCursor': null,
      },
    _ => const <String, Object?>{'status': 'ok'},
  };
}

const Map<String, Object?> _conversation = <String, Object?>{
  'id': 'conversation-1',
  'conversationId': 'conversation-1',
  'type': 'group',
  'title': '旅行讨论',
  'avatarUrl': '',
  'groupAvatarVersion': 1,
  'creatorId': 'persona-1',
  'circleId': '',
  'circleGroupId': '',
  'entityId': '',
  'originType': 'ad_hoc_group',
  'maxSeq': 9,
  'memberCount': 2,
  'membersRosterRevision': 1,
  'maxGroupSize': 500,
  'receiptEnabled': true,
  'announcement': '',
  'announcementUpdatedBy': '',
  'announcementUpdatedAt': '2026-07-21T08:00:00Z',
  'nameEditableByAdminOnly': false,
  'lastMessageId': 'message-1',
  'lastMessagePreview': '你好',
  'lastMessageType': 'text',
  'lastMessageTime': '2026-07-21T08:00:00Z',
  'messageCount': 9,
  'status': 'active',
  'createdAt': '2026-07-20T08:00:00Z',
  'updatedAt': '2026-07-21T08:00:00Z',
};

const Map<String, Object?> _contactHome = <String, Object?>{
  'id': 'persona-2',
  'kind': 'user',
  'objectId': 'persona-2',
  'userHandle': 'xiaoq_public',
  'title': '小趣',
  'subtitle': '摄影作者',
  'avatarUrl': '',
  'summaryIntersections': <String>['共同关注摄影'],
  'sortKey': 'xiaoq',
  'contactCount': 0,
};

const Map<String, Object?> _contact = <String, Object?>{
  'userId': 'persona-2',
  'userHandle': 'xiaoq_public',
  'displayName': '小趣',
  'avatarUrl': '',
  'bio': '摄影作者',
  'metFrom': '摄影圈',
  'lastInteraction': '刚刚',
  'relationState': 'mutual',
  'conversationId': 'conversation-1',
  'conversationType': 'direct',
  'subtitle': '摄影作者',
  'highlightText': '',
  'matchedField': '',
  'source': 'mutual',
  'isStarred': false,
};

const Map<String, Object?> _groupCandidate = <String, Object?>{
  'userId': 'persona-2',
  'userHandle': 'xiaoq_public',
  'displayName': '小趣',
  'avatarUrl': '',
  'bio': '摄影作者',
  'metFrom': '摄影圈',
  'lastInteraction': '刚刚',
  'relationState': 'mutual',
  'source': 'mutual',
  'isStarred': false,
};

const Map<String, Object?> _messageHome = <String, Object?>{
  'id': 'notification-1',
  'kind': 'notification',
  'conversationId': '',
  'notificationId': 'notification-1',
  'conversationType': '',
  'title': '新的互动',
  'summary': '小趣关注了你',
  'avatarUrl': '',
  'groupAvatarVersion': 0,
  'lastActiveAt': '2026-07-21T08:00:00Z',
  'unreadCount': 1,
  'mentionUnreadCount': 0,
  'muted': false,
  'pinned': false,
  'notificationType': 'follow',
  'read': false,
};

const Map<String, Object?> _selectableGroup = <String, Object?>{
  'conversationId': 'conversation-1',
  'title': '旅行讨论',
  'avatarUrl': '',
  'circleId': '',
  'friendMemberCount': 3,
  'memberCount': 6,
};

const Map<String, Object?> _selectableMember = <String, Object?>{
  'userId': 'persona-2',
  'userHandle': 'xiaoq_public',
  'displayName': '小趣',
  'avatarUrl': '',
  'relationState': 'mutual',
  'source': 'mutual',
};
