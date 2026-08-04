// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/commercial-remote-only-message-system/spec.md#gwt-001
// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/spec.md#sit-006
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/remote/chat/conversation/contact_remote.dart';
import 'package:quwoquan_app/cloud/remote/chat/conversation/conversation_membership_remote.dart';
import 'package:quwoquan_app/cloud/remote/chat/conversation/conversation_remote.dart';
import 'package:quwoquan_app/cloud/remote/chat/conversation/conversation_user_state_remote.dart';
import 'package:quwoquan_app/cloud/remote/chat/conversation/message_home_remote.dart';
import 'package:quwoquan_app/cloud/remote/chat/message/message_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  late _RoutingExecutor executor;
  late GeneratedCloudOperationClient client;

  setUp(() {
    executor = _RoutingExecutor();
    client = GeneratedCloudOperationClient(executor);
  });

  test('会话批量、收件箱与联系人七个查询只经 generated typed client', () async {
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
    final inbox = await contact.listInbox(ChatListInboxQuery(limit: 60));
    final groups = await contact.listSelectableGroupConversations(
      ChatListSelectableGroupConversationsQuery(
        query: '旅行',
        source: 'group',
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
    expect(candidates.items.single.source, 'mutual');
    expect(inbox.items.single.unreadCount, 2);
    expect(groups.items.single.friendMemberCount, 3);
    expect(members.items.single.userId, 'persona-2');
    expect(members.items.single.userHandle, 'xiaoq_public');
    expect(executor.operationIds, <String>[
      AppCloudOperationIds.chatConversationBatchGetConversations,
      AppCloudOperationIds.chatConversationListContactHome,
      AppCloudOperationIds.chatConversationListContacts,
      AppCloudOperationIds.chatConversationListGroupCandidates,
      AppCloudOperationIds.chatChatInboxViewListInbox,
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
    expect(executor.payloads[5].queryParameters, <String, String>{
      'limit': '20',
      'query': '旅行',
      'source': 'group',
      'cursor': 'group-cursor',
    });
  });

  test('消息首页、会话标题与助手参与只经 generated typed client', () async {
    final messageHome = RemoteChatMessageHomeQuery(
      client: client,
      invocationContext: _queryContext,
    );
    final conversationWriter = RemoteChatConversationCommandWriter(
      client: client,
      invocationContext: _commandContext,
    );
    final membershipWriter = RemoteChatConversationMembershipCommandWriter(
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
    await membershipWriter.inviteAssistant(
      ChatInviteConversationAssistantCommand(conversationId: 'conversation-1'),
      idempotencyKey: 'assistant-invite-1',
    );
    await membershipWriter.removeAssistant(
      ChatRemoveConversationAssistantCommand(conversationId: 'conversation-1'),
      idempotencyKey: 'assistant-remove-1',
    );

    expect(home.items.single.notificationId, 'notification-1');
    expect(conversation.id, 'conversation-1');
    expect(executor.operationIds, <String>[
      AppCloudOperationIds.chatConversationListMessageHome,
      AppCloudOperationIds.chatConversationUpdateConversationTitle,
      AppCloudOperationIds.chatConversationMembershipInviteAssistant,
      AppCloudOperationIds.chatConversationMembershipRemoveAssistant,
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
    expect(executor.payloads[2].body, isNull);
    expect(executor.payloads[3].body, isNull);
    expect(
      executor.contexts.skip(1).map((context) => context.idempotencyKey),
      <String>['title-1', 'assistant-invite-1', 'assistant-remove-1'],
    );
  });

  test('成员名册查询与五个治理命令保持 typed payload 和幂等键', () async {
    final query = RemoteChatConversationMembershipQuery(
      client: client,
      invocationContext: _queryContext,
    );
    final writer = RemoteChatConversationMembershipCommandWriter(
      client: client,
      invocationContext: _commandContext,
    );

    final page = await query.listMembers(
      ChatListConversationMembersQuery(
        conversationId: 'conversation-1',
        query: '小趣',
        sort: 'display_name_asc',
      ),
    );
    await writer.addMembers(
      ChatAddConversationMembersCommand(
        conversationId: 'conversation-1',
        userIds: const <String>['persona-2'],
      ),
      idempotencyKey: 'add-1',
    );
    await writer.removeMember(
      ChatRemoveConversationMemberCommand(
        conversationId: 'conversation-1',
        userId: 'persona-2',
      ),
      idempotencyKey: 'remove-1',
    );
    await writer.leaveConversation(
      ChatLeaveConversationCommand(conversationId: 'conversation-1'),
      idempotencyKey: 'leave-1',
    );
    await writer.transferOwnership(
      ChatTransferConversationOwnershipCommand(
        conversationId: 'conversation-1',
        newOwnerId: 'persona-2',
      ),
      idempotencyKey: 'transfer-1',
    );
    await writer.updateAdmins(
      ChatUpdateConversationAdminsCommand(
        conversationId: 'conversation-1',
        adminIds: const <String>['persona-2'],
      ),
      idempotencyKey: 'admins-1',
    );

    expect(page.items.single.displayName, '小趣');
    expect(executor.operationIds, <String>[
      AppCloudOperationIds.chatConversationMembershipListMembers,
      AppCloudOperationIds.chatConversationMembershipAddMembers,
      AppCloudOperationIds.chatConversationMembershipRemoveMember,
      AppCloudOperationIds.chatConversationMembershipLeaveConversation,
      AppCloudOperationIds.chatConversationMembershipTransferOwnership,
      AppCloudOperationIds.chatConversationMembershipUpdateGroupAdmins,
    ]);
    expect(
      executor.contexts.skip(1).map((context) => context.idempotencyKey),
      <String>['add-1', 'remove-1', 'leave-1', 'transfer-1', 'admins-1'],
    );
  });

  test('消息列表同步撤回与会话用户态四个操作保持 typed 单路径', () async {
    final query = RemoteChatMessageQuery(
      client: client,
      invocationContext: _queryContext,
    );
    final mutation = RemoteChatMessageMutationWriter(
      client: client,
      invocationContext: _commandContext,
    );
    final userState = RemoteChatConversationUserStateCommandWriter(
      client: client,
      invocationContext: _commandContext,
    );

    final messages = await query.listMessages(
      ChatListMessagesQuery(
        conversationId: 'conversation-1',
        beforeSeq: 20,
        limit: 10,
      ),
    );
    final sync = await query.syncMessages(
      ChatSyncMessagesQuery(
        conversationId: 'conversation-1',
        lastSeq: 8,
        limit: 100,
      ),
    );
    await mutation.recallMessage(
      ChatRecallMessageCommand(
        conversationId: 'conversation-1',
        messageId: 'message-1',
      ),
      idempotencyKey: 'recall-1',
    );
    await userState.markMessageRead(
      ChatMarkConversationMessageReadCommand(
        conversationId: 'conversation-1',
        messageId: 'message-1',
      ),
      idempotencyKey: 'read-1',
    );
    await userState.updateConversationSettings(
      ChatUpdateConversationSettingsCommand(
        conversationId: 'conversation-1',
        muted: true,
      ),
      idempotencyKey: 'settings-1',
    );

    expect(messages.items.single.content, '你好');
    expect(sync.messages.single.seq, 9);
    expect(sync.hasMore, isFalse);
    expect(executor.operationIds, <String>[
      AppCloudOperationIds.chatMessageListMessages,
      AppCloudOperationIds.chatMessageSyncMessages,
      AppCloudOperationIds.chatMessageRecallMessage,
      AppCloudOperationIds.chatConversationUserStateMarkAsRead,
      AppCloudOperationIds.chatConversationUserStateUpdateConversationSettings,
    ]);
    expect(executor.payloads.first.queryParameters, <String, String>{
      'limit': '10',
      'beforeSeq': '20',
    });
    expect(executor.payloads[1].body, <String, Object?>{
      'lastSeq': 8,
      'limit': 100,
    });
    expect(
      executor.contexts.skip(2).map((context) => context.idempotencyKey),
      <String>['recall-1', 'read-1', 'settings-1'],
    );
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
    AppCloudOperationIds.chatChatInboxViewListInbox => <String, Object?>{
      'items': <Object?>[_inbox],
      'nextCursor': null,
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
    AppCloudOperationIds.chatConversationMembershipListMembers =>
      <String, Object?>{
        'items': <Object?>[_member],
        'nextCursor': null,
      },
    AppCloudOperationIds.chatMessageListMessages => <String, Object?>{
      'items': <Object?>[_message],
      'nextBeforeSeq': null,
    },
    AppCloudOperationIds.chatMessageSyncMessages => <String, Object?>{
      'messages': <Object?>[
        <String, Object?>{..._message, 'seq': 9},
      ],
      'hasMore': false,
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

const Map<String, Object?> _inbox = <String, Object?>{
  'id': 'conversation-1',
  'type': 'direct',
  'title': '小趣',
  'avatarUrl': '',
  'groupAvatarVersion': 0,
  'lastMessagePreview': '你好',
  'lastMessageType': 'text',
  'lastMessageTime': '2026-07-21T08:00:00Z',
  'lastSeq': 9,
  'unreadCount': 2,
  'mentionUnreadCount': 0,
  'muted': false,
  'pinned': false,
  'circleId': null,
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

const Map<String, Object?> _member = <String, Object?>{
  'userId': 'persona-2',
  'userHandle': 'xiaoq_public',
  'displayName': '小趣',
  'avatarUrl': '',
  'role': 'member',
  'memberType': 'user',
  'joinedAt': '2026-07-20T08:00:00Z',
  'isCurrentUser': false,
};

const Map<String, Object?> _message = <String, Object?>{
  'id': 'message-1',
  'conversationId': 'conversation-1',
  'seq': 8,
  'clientMsgId': 'client-message-1',
  'senderId': 'persona-2',
  'senderName': '小趣',
  'senderAvatar': '',
  'type': 'text',
  'content': '你好',
  'mediaAssetId': null,
  'card': null,
  'replyToMessageId': null,
  'mentions': <String>[],
  'status': 'sent',
  'timestamp': '2026-07-21T08:00:00Z',
  'recalledAt': null,
  'mediaDeliveryUrl': null,
  'mediaType': null,
  'mediaContentType': null,
  'mediaFileSizeBytes': null,
};
