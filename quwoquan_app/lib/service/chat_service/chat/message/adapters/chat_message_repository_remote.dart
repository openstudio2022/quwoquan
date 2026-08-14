// ignore_for_file: prefer_initializing_formals

import 'package:quwoquan_app/service/chat_service/chat/message/application/chat_message_repository.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation_user_state/application/public/conversation_user_state_command_writer.dart';
import 'package:quwoquan_app/service/chat_service/chat/message_receipt_fact/application/public/message_receipt_fact_query.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_view_data.dart';
import 'package:quwoquan_app/runtime/transport/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:uuid/uuid.dart';

final class RemoteChatMessageRepository implements ChatMessageRepository {
  RemoteChatMessageRepository({
    required ChatMessageQuery messageQuery,
    required ChatMessageMutationWriter messageMutationWriter,
    required ConversationUserStateCommandWriter userStateCommandWriter,
    required MessageReceiptFactQuery receiptQuery,
    String Function()? idempotencyKeyFactory,
  }) : _messageQuery = messageQuery,
       _messageMutationWriter = messageMutationWriter,
       _userStateCommandWriter = userStateCommandWriter,
       _receiptQuery = receiptQuery,
       _idempotencyKeyFactory = idempotencyKeyFactory ?? const Uuid().v4;

  final ChatMessageQuery _messageQuery;
  final ChatMessageMutationWriter _messageMutationWriter;
  final ConversationUserStateCommandWriter _userStateCommandWriter;
  final MessageReceiptFactQuery _receiptQuery;
  final String Function() _idempotencyKeyFactory;

  String _idempotencyKey() {
    final value = _idempotencyKeyFactory().trim();
    if (value.isEmpty) {
      throw ArgumentError.value(value, 'idempotencyKey', 'must not be blank');
    }
    return value;
  }

  @override
  Future<List<ChatMessageViewData>> listMessages({
    required String conversationId,
    String? before,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final normalizedBefore = before?.trim() ?? '';
    final beforeSeq = normalizedBefore.isEmpty
        ? null
        : int.tryParse(normalizedBefore);
    if (normalizedBefore.isNotEmpty && beforeSeq == null) {
      throw ArgumentError.value(before, 'before', 'must be a message sequence');
    }
    final page = await _messageQuery.listMessages(
      ChatListMessagesQuery(
        conversationId: conversationId,
        beforeSeq: beforeSeq,
        limit: limit,
      ),
    );
    return page.items.map(ChatMessageViewData.fromWire).toList(growable: false);
  }

  @override
  Future<void> recallMessage({
    required String conversationId,
    required String messageId,
  }) async {
    await _messageMutationWriter.recallMessage(
      ChatRecallMessageCommand(
        conversationId: conversationId,
        messageId: messageId,
      ),
      idempotencyKey: _idempotencyKey(),
    );
  }

  @override
  Future<ChatMessageSyncViewData> syncMessages({
    required String conversationId,
    required int lastSeq,
    int limit = ChatSyncMessagesQuery.defaultLimit,
  }) async {
    final slice = await _messageQuery.syncMessages(
      ChatSyncMessagesQuery(
        conversationId: conversationId,
        lastSeq: lastSeq,
        limit: limit,
      ),
    );
    return ChatMessageSyncViewData(
      messages: slice.messages
          .map(ChatMessageViewData.fromWire)
          .toList(growable: false),
      hasMore: slice.hasMore,
    );
  }

  @override
  Future<void> markAsRead({
    required String conversationId,
    required String messageId,
  }) async {
    await _userStateCommandWriter.markMessageRead(
      ChatMarkConversationMessageReadCommand(
        conversationId: conversationId,
        messageId: messageId,
      ),
      idempotencyKey: _idempotencyKey(),
    );
  }

  @override
  Future<List<ChatMessageReceipt>> getReceipts({
    required String conversationId,
    required String messageId,
  }) async {
    final page = await _receiptQuery.getReceipts(
      ChatGetMessageReceiptsQuery(
        conversationId: conversationId,
        messageId: messageId,
      ),
    );
    return page.items;
  }

  @override
  Future<ConversationAssetPage> listConversationAssets({
    required String conversationId,
    required String kind,
    int? beforeSeq,
    int limit = 60,
  }) {
    return _messageQuery.listConversationAssets(
      ChatListConversationAssetsQuery(
        conversationId: conversationId,
        kind: kind,
        beforeSeq: beforeSeq,
        limit: limit,
      ),
    );
  }
}
