import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_cloud_mock/src/generated/alpha_fixture_bundle.g.dart';

/// Alpha-only Message command adapter backed by the packaged fixture bundle.
/// It preserves command idempotency without exposing a Repository or wire map.
final class AlphaChatMessageCommandWriter implements ChatMessageCommandWriter {
  AlphaChatMessageCommandWriter({
    AlphaFixtureBundle bundle = alphaFixtureBundle,
  }) : _nextSeqByConversation = _readConversationSequences(bundle);

  final Map<String, int> _nextSeqByConversation;
  final Map<String, _AlphaMessageReceipt> _receipts =
      <String, _AlphaMessageReceipt>{};

  @override
  Future<ChatSendMessageResult> sendMessage(
    ChatSendMessageCommand command,
  ) async {
    final currentSeq = _nextSeqByConversation[command.conversationId];
    if (currentSeq == null) {
      throw StateError('CHAT.USER.conversation_not_found');
    }
    final digest = _commandDigest(command);
    final existing = _receipts[command.clientMsgId];
    if (existing != null) {
      if (existing.commandDigest != digest) {
        throw StateError('CHAT.USER.message_idempotency_conflict');
      }
      return existing.result;
    }

    final nextSeq = currentSeq + 1;
    final result = ChatSendMessageResult(
      messageId: 'alpha-message-${command.clientMsgId}',
      seq: nextSeq,
      timestamp: DateTime.now().toUtc(),
    );
    _nextSeqByConversation[command.conversationId] = nextSeq;
    _receipts[command.clientMsgId] = _AlphaMessageReceipt(
      commandDigest: digest,
      result: result,
    );
    return result;
  }

  static String _commandDigest(ChatSendMessageCommand command) {
    final payload = encodeChatSendMessageCommand(command);
    return sha256.convert(utf8.encode(jsonEncode(payload.body))).toString();
  }

  static Map<String, int> _readConversationSequences(
    AlphaFixtureBundle bundle,
  ) {
    final asset = bundle.assets['chat'];
    if (asset == null) {
      throw StateError('Chat alpha fixture asset is missing');
    }
    final decoded = jsonDecode(asset.sourceJson);
    if (decoded is! Map) {
      throw FormatException('Chat alpha fixture root must be an object');
    }
    final seedSets = decoded['seedSets'];
    final chatCore = seedSets is Map ? seedSets['chat_core'] : null;
    final conversations = chatCore is Map ? chatCore['conversations'] : null;
    if (conversations is! List) {
      throw FormatException('Chat alpha fixture conversations are missing');
    }
    return <String, int>{
      for (final raw in conversations)
        if (raw is Map &&
            (raw['conversationId'] ?? raw['id']) is String &&
            (raw['conversationId'] ?? raw['id']).toString().trim().isNotEmpty)
          (raw['conversationId'] ?? raw['id']).toString().trim():
              raw['maxSeq'] is num ? (raw['maxSeq'] as num).toInt() : 0,
    };
  }
}

final class _AlphaMessageReceipt {
  const _AlphaMessageReceipt({
    required this.commandDigest,
    required this.result,
  });

  final String commandDigest;
  final ChatSendMessageResult result;
}
