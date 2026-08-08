import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart'
    show
        activePersonaContextProvider,
        chatContactRepositoryProvider,
        chatConversationRepositoryProvider,
        chatMessageCommandWriterProvider;
import 'package:quwoquan_app/runtime/shell/share/forward_share_dependencies.dart';
import 'package:quwoquan_app/runtime/shell/share/forward_share_models.dart';
import 'package:quwoquan_app/runtime/transport/media/avatar_image_url.dart';
import 'package:quwoquan_app/service/chat_service/chat/chat_inbox_view/application/public/chat_inbox_view_data.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/chat_conversation_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Binds the runtime share shell to Chat-owned production ports. The shell sees
/// only neutral recipient/card values and never imports Chat implementation.
final forwardShareDependenciesProvider = Provider<ForwardShareDependencies>(
  (ref) => ForwardShareDependencies(
    loadRecentRecipients: ({required limit}) async {
      final rows = await ref
          .read(chatConversationRepositoryProvider)
          .listConversations(limit: limit);
      return rows.map(_recipientFromConversation).toList(growable: false);
    },
    loadContactRecipients: ({required limit, required groupsOnly}) async {
      final rows = await ref
          .read(chatContactRepositoryProvider)
          .listContactHome(filter: groupsOnly ? 'group' : 'all', limit: limit);
      return rows
          .where((row) => row.kind.trim().toLowerCase() != 'circle')
          .map(_recipientFromContactHome)
          .toList(growable: false);
    },
    sendCard:
        ({
          required payload,
          required recipient,
          required note,
          required clientMsgId,
        }) async {
          final conversationId = await _resolveConversationId(
            ref.read(chatConversationRepositoryProvider),
            recipient,
          );
          final activeContext = await ref.read(
            activePersonaContextProvider.future,
          );
          final content = note.isNotEmpty ? note : payload.messagePreview;
          await ref
              .read(chatMessageCommandWriterProvider)
              .sendMessage(
                ChatSendMessageCommand(
                  conversationId: conversationId,
                  type: 'card',
                  content: content,
                  card: payload.toMessageCardCommand(message: note),
                  senderDisplayNameSnapshot: activeContext.displayName,
                  senderAvatarUrlSnapshot: activeContext.avatarUrl,
                  personaContextVersion: activeContext.contextVersion > 0
                      ? activeContext.contextVersion
                      : null,
                  clientMsgId: clientMsgId,
                ),
              );
        },
  ),
);

AppForwardRecipient _recipientFromConversation(ChatInboxViewData row) {
  final normalizedType = row.type.trim().toLowerCase();
  final isGroup = normalizedType == 'group' || normalizedType == 'circle_group';
  final title = row.title.trim().isNotEmpty ? row.title.trim() : row.id;
  return AppForwardRecipient(
    id: row.id,
    kind: isGroup
        ? AppForwardRecipientKind.group
        : AppForwardRecipientKind.conversation,
    title: title,
    subtitle: row.lastMessagePreview.trim(),
    avatarUrl: resolveAvatarImageUrl(row.avatarUrl),
    conversationId: row.id,
    lastActiveAt: row.lastMessageTime,
  );
}

AppForwardRecipient _recipientFromContactHome(ContactHomeRow row) {
  final normalizedKind = row.kind.trim().toLowerCase();
  final isGroup = normalizedKind == 'group';
  final title = row.title.trim().isNotEmpty
      ? row.title.trim()
      : ((row.userId?.trim().isNotEmpty ?? false)
            ? row.userId!.trim()
            : row.id);
  return AppForwardRecipient(
    id: row.id.isNotEmpty ? row.id : row.objectId,
    kind: isGroup
        ? AppForwardRecipientKind.group
        : AppForwardRecipientKind.user,
    title: title,
    subtitle: row.subtitle.trim().isNotEmpty
        ? row.subtitle.trim()
        : row.summaryIntersections.take(2).join(' · '),
    avatarUrl: resolveAvatarImageUrl(row.avatarUrl),
    conversationId: row.conversationId?.trim() ?? '',
    userId: (row.userId?.trim().isNotEmpty ?? false)
        ? row.userId!.trim()
        : row.objectId.trim(),
    memberCount: row.memberCount ?? 0,
    lastActiveAt: row.lastActiveAt,
  );
}

Future<String> _resolveConversationId(
  ChatConversationRepository repository,
  AppForwardRecipient recipient,
) async {
  final conversationId = recipient.conversationId.trim();
  if (conversationId.isNotEmpty) {
    return conversationId;
  }
  final userId = recipient.userId.trim();
  if (userId.isEmpty || recipient.kind == AppForwardRecipientKind.group) {
    throw StateError('forward target unavailable');
  }
  final created = await repository.createConversation(
    type: 'direct',
    initialMemberIds: <String>[userId],
  );
  final createdId = created.conversationId.trim();
  if (createdId.isEmpty) {
    throw StateError('forward target unavailable');
  }
  return createdId;
}
