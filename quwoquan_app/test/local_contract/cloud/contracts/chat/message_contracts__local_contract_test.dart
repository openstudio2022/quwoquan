import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  group('Chat Message typed contract', () {
    test('media command 只编码稳定 MediaAsset identity', () {
      final payload = encodeChatMessageSendMessageGeneratedRequest(
        ChatSendMessageCommand(
          conversationId: 'conversation-1',
          type: 'audio',
          content: '',
          clientMsgId: 'client-message-1',
          mediaAssetId: 'asset-1',
          mentions: const <String>['assistant'],
          personaContextVersion: 7,
        ),
      );

      expect(payload.pathParameters, <String, String>{
        'conversationId': 'conversation-1',
      });
      final body = payload.body! as Map<String, Object?>;
      expect(body['clientMsgId'], 'client-message-1');
      expect(body['mentions'], const <String>['assistant']);
      expect(body['personaContextVersion'], 7);
      expect(body['mediaAssetId'], 'asset-1');
      expect(body.containsKey('media'), isFalse);
      expect(body.containsKey('mediaUrl'), isFalse);
    });

    test('rejects incomplete type-specific commands', () {
      expect(
        () => ChatSendMessageCommand(
          conversationId: 'conversation-1',
          type: 'audio',
          content: '',
          clientMsgId: 'client-message-1',
        ),
        throwsArgumentError,
      );
      expect(
        () => ChatSendMessageCommand(
          conversationId: 'conversation-1',
          type: 'text',
          content: 'hello',
          clientMsgId: 'client-message-2',
          mediaAssetId: 'asset-1',
        ),
        throwsArgumentError,
      );
      expect(
        () => ChatSendMessageCommand(
          conversationId: 'conversation-1',
          type: 'card',
          content: '',
          clientMsgId: 'client-message-1',
        ),
        throwsArgumentError,
      );
    });

    test('card command 只编码强类型 card，拒绝非 card 命令夹带', () {
      final payload = encodeChatMessageSendMessageGeneratedRequest(
        ChatSendMessageCommand(
          conversationId: 'conversation-card',
          type: 'card',
          content: '查看分享',
          clientMsgId: 'client-card-1',
          card: ChatMessageCardCommand(
            kind: 'content_post',
            title: '城市漫步',
            objectRef: ChatMessageCardObjectRef(
              objectTypeRef: 'post',
              objectId: 'post_001',
              routeId: 'contentDetail',
            ),
            attributes: <ChatMessageCardAttribute>[
              ChatMessageCardAttribute(name: 'postId', value: 'post_001'),
            ],
          ),
        ),
      );
      final body = payload.body! as Map<String, Object?>;
      expect(body.containsKey('cardPayload'), isFalse);
      expect(body['card'], <String, Object?>{
        'kind': 'content_post',
        'title': '城市漫步',
        'objectRef': <String, Object?>{
          'objectTypeRef': 'post',
          'objectId': 'post_001',
          'routeId': 'contentDetail',
        },
        'attributes': <Map<String, String>>[
          <String, String>{'name': 'postId', 'value': 'post_001'},
        ],
      });
      expect(
        () => ChatSendMessageCommand(
          conversationId: 'conversation-card',
          type: 'text',
          content: 'removed',
          clientMsgId: 'client-card-removed',
          card: ChatMessageCardCommand(kind: 'content_post', title: 'removed'),
        ),
        throwsArgumentError,
      );
      expect(
        () => ChatMessageCardCommand(
          kind: 'content_post',
          title: 'missing object ref',
        ),
        throwsArgumentError,
      );
    });

    test('strictly decodes SendMessage result', () {
      final result = decodeChatSendMessageResult(<String, Object?>{
        'messageId': 'message-1',
        'seq': 9,
        'timestamp': '2026-07-15T08:00:00Z',
      });
      expect(result.messageId, 'message-1');
      expect(result.seq, 9);
      expect(result.timestamp, DateTime.utc(2026, 7, 15, 8));

      expect(
        () => decodeChatSendMessageResult(<String, Object?>{
          'messageId': 'message-1',
          'seq': 1.5,
          'timestamp': '2026-07-15T08:00:00Z',
        }),
        throwsFormatException,
      );
      expect(
        () => decodeChatSendMessageResult(<String, Object?>{
          'messageId': 'message-1',
          'seq': 1,
          'timestamp': '2026-07-15T08:00:00Z',
          'removedField': true,
        }),
        throwsFormatException,
      );
    });

    test('decodes message keyset page and encodes sequence bounds', () {
      final request = encodeChatMessageListMessagesGeneratedRequest(
        ChatListMessagesQuery(
          conversationId: 'conversation-1',
          beforeSeq: 42,
          limit: 20,
        ),
      );
      final page = decodeChatMessagePageSlice(<String, Object?>{
        'items': <Object?>[
          <String, Object?>{
            'id': 'message-41',
            'conversationId': 'conversation-1',
            'seq': 41,
            'clientMsgId': 'client-message-41',
            'senderId': 'user-1',
            'senderName': '',
            'senderAvatar': '',
            'type': 'text',
            'content': '你好',
            'mediaAssetId': '',
            'card': null,
            'replyToMessageId': '',
            'mentions': <String>[],
            'status': 'sent',
            'timestamp': '2026-07-21T06:00:00Z',
          },
        ],
        'nextBeforeSeq': 41,
      });

      expect(request.queryParameters, <String, String>{
        'limit': '20',
        'beforeSeq': '42',
      });
      expect(page.items.single.content, '你好');
      expect(page.nextBeforeSeq, 41);
      expect(
        () => decodeChatMessagePageSlice(<String, Object?>{
          'items': <Object?>[],
          'cursor': 'retired',
        }),
        throwsFormatException,
      );
    });
  });
}
