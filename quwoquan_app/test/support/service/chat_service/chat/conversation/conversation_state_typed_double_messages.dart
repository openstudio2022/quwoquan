part of 'conversation_state_typed_double.dart';

extension AlphaChatMessageCommandState on InMemoryChatStateEngine {
  ChatSendMessageResult sendMessage(ChatSendMessageCommand command) {
    final conversation = _conversation(command.conversationId);
    if (conversation == null) {
      throw StateError('CHAT.USER.conversation_not_found');
    }

    final canonicalMentions = _canonicalMessageMentions(
      conversation: conversation,
      mentions: command.mentions,
    );
    final payload = encodeChatMessageSendMessageGeneratedRequest(command);
    final Map<String, Object?> body = payload.body is Map
        ? Map<String, Object?>.from(
            (payload.body as Map).cast<String, Object?>(),
          )
        : <String, Object?>{};
    body['mentions'] = canonicalMentions;
    final digest = sha256.convert(utf8.encode(jsonEncode(body))).toString();
    final existing = _sendReceipts[command.clientMsgId];
    if (existing != null) {
      if (existing.commandDigest != digest) {
        throw StateError('CHAT.USER.message_idempotency_conflict');
      }
      return existing.result;
    }

    final messages = _messagesFor(command.conversationId);
    final nextSeq =
        <int>[
          _int(conversation['maxSeq']),
          for (final message in messages) _int(message['seq']),
        ].reduce((left, right) => left > right ? left : right) +
        1;
    final timestamp = _now();
    final messageId = 'alpha-message-${command.clientMsgId}';
    messages.add(<String, Object?>{
      'id': messageId,
      'conversationId': command.conversationId,
      'seq': nextSeq,
      'clientMsgId': command.clientMsgId,
      'senderId': currentUserId,
      'senderName': command.senderDisplayNameSnapshot?.trim().isNotEmpty == true
          ? command.senderDisplayNameSnapshot!.trim()
          : displayNameFor(currentUserId),
      'senderAvatar': command.senderAvatarUrlSnapshot?.trim().isNotEmpty == true
          ? command.senderAvatarUrlSnapshot!.trim()
          : avatarFor(currentUserId),
      'type': command.type,
      'content': command.content,
      'mediaAssetId': command.mediaAssetId,
      'card': body['card'],
      'replyToMessageId': command.replyToMessageId,
      'mentions': canonicalMentions,
      'status': 'sent',
      'timestamp': timestamp.toIso8601String(),
    });

    conversation['maxSeq'] = nextSeq;
    conversation['lastSeq'] = nextSeq;
    conversation['lastMessageId'] = messageId;
    conversation['lastMessagePreview'] = command.content;
    conversation['lastMessageType'] = command.type;
    conversation['lastMessageTime'] = timestamp.toIso8601String();
    conversation['messageCount'] = messages.length;
    conversation['updatedAt'] = timestamp.toIso8601String();

    final result = ChatSendMessageResult(
      messageId: messageId,
      seq: nextSeq,
      timestamp: timestamp,
    );
    _sendReceipts[command.clientMsgId] = _InMemoryChatSendReceipt(
      commandDigest: digest,
      result: result,
    );
    return result;
  }

  List<String> _canonicalMessageMentions({
    required ChatFixtureObject conversation,
    required List<String> mentions,
  }) {
    if (mentions.isEmpty) {
      return const <String>[];
    }
    if (mentions.length > 50 || _text(conversation['type']) != 'group') {
      throw StateError('CHAT.USER.message_invalid');
    }
    final members = _ensureMembers(_text(conversation['id']));
    ChatFixtureObject? sender;
    for (final member in members) {
      if (_text(member['userId']) == currentUserId) {
        sender = member;
        break;
      }
    }
    if (sender == null) {
      throw StateError('CHAT.USER.message_invalid');
    }
    final canonical = <String>[];
    final seen = <String>{};
    for (final raw in mentions) {
      var targetId = raw.trim();
      if (targetId.isEmpty) {
        continue;
      }
      if (targetId == '__all__') {
        final role = _text(sender['role']);
        if (role != 'owner' && role != 'admin') {
          throw StateError('CHAT.USER.message_invalid');
        }
      } else if (targetId == 'assistant') {
        ChatFixtureObject? assistantMember;
        for (final member in members) {
          if (_text(member['memberType']) == 'assistant' ||
              _text(member['userId']) == 'assistant') {
            assistantMember = member;
            break;
          }
        }
        if (assistantMember == null ||
            _text(assistantMember['userId']).isEmpty) {
          throw StateError('CHAT.USER.message_invalid');
        }
        targetId = _text(assistantMember['userId']);
      } else {
        final exists = members.any(
          (member) => _text(member['userId']) == targetId,
        );
        if (!exists) {
          throw StateError('CHAT.USER.message_invalid');
        }
      }
      if (seen.add(targetId)) {
        canonical.add(targetId);
      }
    }
    return List<String>.unmodifiable(canonical);
  }
}

final class _InMemoryChatSendReceipt {
  const _InMemoryChatSendReceipt({
    required this.commandDigest,
    required this.result,
  });

  final String commandDigest;
  final ChatSendMessageResult result;
}
