import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/service/chat_service/chat/chat_inbox_view/adapters/chat_inbox_remote.dart';
import 'package:quwoquan_app/service/chat_service/chat/chat_inbox_view/adapters/chat_inbox_repository_remote.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/adapters/chat_conversation_repository_remote.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/adapters/contact_remote.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/adapters/conversation_remote.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/adapters/gathering_board_chat_remote.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/gathering_board_ports.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation_user_state/adapters/conversation_user_state_remote.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/adapters/message_home_remote.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation_membership/adapters/chat_member_repository_remote.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation_membership/adapters/conversation_membership_remote.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/adapters/chat_message_repository_remote.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/adapters/message_remote.dart';
import 'package:quwoquan_app/service/chat_service/chat/message_receipt_fact/application/public/message_receipt_fact_query.dart';
import 'package:quwoquan_app/service/chat_service/chat/message_receipt_fact/adapters/message_receipt_fact_remote.dart';
import 'package:quwoquan_app/runtime/di/chat_repository_facade.dart';
import 'package:quwoquan_app/runtime/transport/generated/chat/chat_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef ChatSurfaceInvocationContextFactory =
    CloudOperationInvocationContext Function(
      AppUiSurface surface,
      String clientPageId, {
      String? idempotencyKey,
    });

/// chat domain 的唯一 production Remote 装配入口。
///
/// Provider 只负责提供 generated client 与 actor context；对象 adapter 的实例化、
/// operation 对应 surface，以及聚合 Facet 的共享关系全部固定在这里。
final class ChatProductionComposition {
  const ChatProductionComposition._();

  static MessageReceiptFactQuery messageReceiptFactQuery({
    required GeneratedCloudOperationClient client,
    required ChatSurfaceInvocationContextFactory invocationContext,
  }) {
    return RemoteMessageReceiptFactQuery(
      client: client,
      invocationContext: (clientPageId) =>
          invocationContext(AppUiSurfaces.chatDetail, clientPageId),
    );
  }

  static ChatRepository repository({
    required GeneratedCloudOperationClient client,
    required ChatSurfaceInvocationContextFactory invocationContext,
  }) {
    final conversationQuery = RemoteChatConversationQuery(
      client: client,
      invocationContext: (clientPageId) {
        final surface = switch (clientPageId) {
          ChatRequestPageIds.getConversation => AppUiSurfaces.chatDetail,
          ChatRequestPageIds.getGroupHome => AppUiSurfaces.chatAnnouncement,
          _ => AppUiSurfaces.chatList,
        };
        return invocationContext(surface, clientPageId);
      },
    );
    final settingsConversationQuery = RemoteChatConversationQuery(
      client: client,
      invocationContext: (clientPageId) =>
          invocationContext(AppUiSurfaces.chatSettings, clientPageId),
    );
    final conversationCommandWriter = RemoteChatConversationCommandWriter(
      client: client,
      invocationContext: (clientPageId, idempotencyKey) {
        final surface = switch (clientPageId) {
          ChatRequestPageIds.createConversation => AppUiSurfaces.startGroupChat,
          ChatRequestPageIds.updateConversationTitle =>
            AppUiSurfaces.chatSettings,
          ChatRequestPageIds.updateAnnouncement =>
            AppUiSurfaces.chatAnnouncement,
          _ => AppUiSurfaces.chatManage,
        };
        return invocationContext(
          surface,
          clientPageId,
          idempotencyKey: idempotencyKey,
        );
      },
    );
    final contactQuery = RemoteChatContactQuery(
      client: client,
      invocationContext: (clientPageId) {
        final surface = switch (clientPageId) {
          ChatRequestPageIds.listGroupCandidates ||
          ChatRequestPageIds.listSelectableGroupConversations ||
          ChatRequestPageIds.listSelectableGroupContactMembers =>
            AppUiSurfaces.startGroupChat,
          _ => AppUiSurfaces.chatList,
        };
        return invocationContext(surface, clientPageId);
      },
    );
    final inboxQuery = RemoteChatInboxQuery(
      client: client,
      invocationContext: (clientPageId) =>
          invocationContext(AppUiSurfaces.chatList, clientPageId),
    );
    final messageHomeQuery = RemoteChatMessageHomeQuery(
      client: client,
      invocationContext: (clientPageId) =>
          invocationContext(AppUiSurfaces.chatList, clientPageId),
    );
    final membershipQuery = RemoteChatConversationMembershipQuery(
      client: client,
      invocationContext: (clientPageId) =>
          invocationContext(AppUiSurfaces.chatManage, clientPageId),
    );
    final memberSearchQuery = RemoteChatConversationMembershipQuery(
      client: client,
      invocationContext: (clientPageId) =>
          invocationContext(AppUiSurfaces.chatDetail, clientPageId),
    );
    final membershipCommandWriter =
        RemoteChatConversationMembershipCommandWriter(
          client: client,
          invocationContext: (clientPageId, idempotencyKey) {
            final surface = switch (clientPageId) {
              ChatRequestPageIds.addMembers => AppUiSurfaces.chatAddMembers,
              ChatRequestPageIds.inviteAssistant ||
              ChatRequestPageIds.removeAssistant => AppUiSurfaces.chatDetail,
              ChatRequestPageIds.transferOwnership =>
                AppUiSurfaces.chatTransferOwnership,
              ChatRequestPageIds.updateGroupAdmins => AppUiSurfaces.chatAdmins,
              _ => AppUiSurfaces.chatSettings,
            };
            return invocationContext(
              surface,
              clientPageId,
              idempotencyKey: idempotencyKey,
            );
          },
        );
    final userStateCommandWriter = RemoteChatConversationUserStateCommandWriter(
      client: client,
      invocationContext: (clientPageId, idempotencyKey) {
        final surface = clientPageId == ChatRequestPageIds.markAsRead
            ? AppUiSurfaces.chatDetail
            : AppUiSurfaces.chatSettings;
        return invocationContext(
          surface,
          clientPageId,
          idempotencyKey: idempotencyKey,
        );
      },
    );
    final messageQuery = RemoteChatMessageQuery(
      client: client,
      invocationContext: (clientPageId) =>
          invocationContext(AppUiSurfaces.chatDetail, clientPageId),
    );
    final messageMutationWriter = RemoteChatMessageMutationWriter(
      client: client,
      invocationContext: (clientPageId, idempotencyKey) => invocationContext(
        AppUiSurfaces.chatDetail,
        clientPageId,
        idempotencyKey: idempotencyKey,
      ),
    );
    final receiptQuery = messageReceiptFactQuery(
      client: client,
      invocationContext: invocationContext,
    );

    final inboxRepository = RemoteChatInboxRepository(query: inboxQuery);
    final conversationRepository = RemoteChatConversationRepository(
      conversationQuery: conversationQuery,
      settingsConversationQuery: settingsConversationQuery,
      conversationCommandWriter: conversationCommandWriter,
      contactQuery: contactQuery,
      messageHomeQuery: messageHomeQuery,
      membershipCommandWriter: membershipCommandWriter,
      userStateCommandWriter: userStateCommandWriter,
    );
    final memberRepository = RemoteChatMemberRepository(
      membershipQuery: membershipQuery,
      memberSearchQuery: memberSearchQuery,
      membershipCommandWriter: membershipCommandWriter,
    );
    final messageRepository = RemoteChatMessageRepository(
      messageQuery: messageQuery,
      messageMutationWriter: messageMutationWriter,
      userStateCommandWriter: userStateCommandWriter,
      receiptQuery: receiptQuery,
    );

    return ComposedChatRepository(
      inbox: inboxRepository,
      conversation: conversationRepository,
      message: messageRepository,
      member: memberRepository,
      contact: conversationRepository,
      groupSelection: conversationRepository,
      groupAdmin: conversationRepository,
    );
  }

  static ChatMessageCommandWriter messageCommandWriter({
    required GeneratedCloudOperationClient client,
    required ChatSurfaceInvocationContextFactory invocationContext,
  }) {
    return RemoteChatMessageCommandWriter(
      client: client,
      invocationContext: (clientPageId, idempotencyKey) => invocationContext(
        AppUiSurfaces.chatDetail,
        clientPageId,
        idempotencyKey: idempotencyKey,
      ),
    );
  }

  static GatheringBoardChatReader gatheringBoardChatReader({
    required GeneratedCloudOperationClient client,
    required ChatSurfaceInvocationContextFactory invocationContext,
  }) {
    return RemoteGatheringBoardChatReader(
      client: client,
      invocationContext: (clientPageId) =>
          invocationContext(AppUiSurfaces.gatheringBoard, clientPageId),
    );
  }
}
