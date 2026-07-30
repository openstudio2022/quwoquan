import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/chat/models/message_dto.dart';

Map<String, dynamic> validMessageWire({
  String type = 'text',
  String? mediaAssetId,
  String? mediaDeliveryUrl,
  String? mediaType,
  String? mediaContentType,
  int? mediaFileSizeBytes,
}) {
  return <String, dynamic>{
    'id': 'msg_001',
    'conversationId': 'conv_001',
    'seq': 42,
    'clientMsgId': 'client_001',
    'senderId': 'persona_001',
    'senderName': '契约发送者',
    'senderAvatar': 'https://cdn.example.com/avatar.png',
    'type': type,
    'content': type == 'text' ? 'hello' : '',
    'mediaAssetId': mediaAssetId,
    'mediaDeliveryUrl': mediaDeliveryUrl,
    'mediaType': mediaType,
    'mediaContentType': mediaContentType,
    'mediaFileSizeBytes': mediaFileSizeBytes,
    'replyToMessageId': null,
    'mentions': <String>['assistant'],
    'status': 'sent',
    'recalledAt': null,
    'timestamp': '2026-07-15T08:00:00.000Z',
  };
}

void main() {
  group('ChatMessageDto strict projection', () {
    test('解析服务端返回的强类型 MediaAsset delivery projection', () {
      final dto = MessageDto.fromMap(
        validMessageWire(
          type: 'audio',
          mediaAssetId: 'asset_audio_001',
          mediaDeliveryUrl: 'https://cdn.example.com/voice.m4a',
          mediaType: 'audio',
          mediaContentType: 'audio/mp4',
          mediaFileSizeBytes: 48000,
        ),
      );

      expect(dto.id, 'msg_001');
      expect(dto.senderId, 'persona_001');
      expect(dto.senderName, '契约发送者');
      expect(dto.type, 'audio');
      expect(dto.mediaAssetId, 'asset_audio_001');
      expect(dto.mediaDeliveryUrl, 'https://cdn.example.com/voice.m4a');
      expect(dto.mediaType, 'audio');
      expect(dto.mediaContentType, 'audio/mp4');
      expect(dto.mediaFileSizeBytes, 48000);
    });

    test('toMap 使用 canonical wire key 并可严格 round-trip', () {
      final original = MessageDto.fromMap(validMessageWire());
      final wire = original.toMap();

      expect(wire['id'], 'msg_001');
      expect(wire['senderName'], '契约发送者');
      expect(wire['timestamp'], '2026-07-15T08:00:00.000Z');
      expect(wire.containsKey('_id'), isFalse);
      expect(wire.containsKey('senderDisplayNameSnapshot'), isFalse);

      final decoded = MessageDto.fromMap(wire);
      expect(decoded.id, original.id);
      expect(decoded.timestamp, original.timestamp);
    });

    test('解析并 round-trip Message 拥有的强类型 card 值对象', () {
      final wire = validMessageWire(type: 'card')
        ..['card'] = <String, dynamic>{
          'kind': 'content_post',
          'title': '城市漫步',
          'subtitle': '周末路线',
          'attributes': <Map<String, String>>[
            <String, String>{'name': 'postId', 'value': 'post_001'},
          ],
        };
      final dto = MessageDto.fromMap(wire);
      expect(dto.card?.kind, 'content_post');
      expect(dto.card?.attributes.single.name, 'postId');
      final roundTripCard = dto.toMap()['card']! as Map<String, dynamic>;
      expect(roundTripCard['kind'], 'content_post');
      expect(roundTripCard['title'], '城市漫步');
      expect(roundTripCard['attributes'], wire['card']['attributes']);
      expect(MessageDto.fromMap(dto.toMap()).card?.title, '城市漫步');
    });

    test('拒绝已移除的 mediaUrl/media 与 alias key', () {
      for (final removedField in <String>[
        '_id',
        'messageId',
        'senderDisplayNameSnapshot',
        'senderAvatarUrlSnapshot',
        'mediaUrl',
        'media',
        'cardPayload',
        'senderPersonaId',
        'messageStatus',
        'createdAt',
        'sentAt',
      ]) {
        final wire = validMessageWire()..[removedField] = 'removed';
        expect(
          () => MessageDto.fromMap(wire),
          throwsFormatException,
          reason: 'removed field $removedField must not be accepted',
        );
      }
    });

    test('拒绝缺失必填字段、错误类型和非法时间', () {
      expect(
        () => MessageDto.fromMap(validMessageWire()..remove('id')),
        throwsFormatException,
      );
      expect(
        () => MessageDto.fromMap(validMessageWire()..['seq'] = 1.5),
        throwsFormatException,
      );
      expect(
        () =>
            MessageDto.fromMap(validMessageWire()..['mentions'] = <Object>[1]),
        throwsFormatException,
      );
      expect(
        () => MessageDto.fromMap(validMessageWire()..['timestamp'] = 'invalid'),
        throwsFormatException,
      );
    });
  });
}
