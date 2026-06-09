import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/chat/models/message_dto.dart';

void main() {
  group('MessageDto — 常规契约', () {
    test('audio 类型消息全字段解析', () {
      final dto = MessageDto.fromMap({
        '_id': 'msg_001',
        'conversationId': 'conv_001',
        'seq': 42,
        'clientMsgId': 'client_001',
        'senderId': 'user_001',
        'type': 'audio',
        'content': '',
        'mediaUrl': 'https://cdn.example.com/voice.m4a',
        'media': {
          'url': 'https://cdn.example.com/voice.m4a',
          'mimeType': 'audio/mp4',
          'fileSizeBytes': 48000,
          'durationMs': 5200,
          'waveform': [0.1, 0.3, 0.7, 0.5, 0.2],
          'codec': 'aac',
        },
        'status': 'sent',
        'timestamp': '2026-03-08T12:00:00Z',
      });

      expect(dto.type, 'audio');
      expect(dto.mediaUrl, 'https://cdn.example.com/voice.m4a');
      expect(dto.media, isNotNull);
      expect(dto.media!['durationMs'], 5200);
      expect(dto.media!['mimeType'], 'audio/mp4');
      expect(dto.media!['waveform'], isA<List>());
      expect(dto.media!['codec'], 'aac');
    });

    test('image 类型消息解析 mediaUrl 与缩略图', () {
      final dto = MessageDto.fromMap({
        '_id': 'msg_img_001',
        'conversationId': 'conv_001',
        'seq': 43,
        'clientMsgId': 'client_img_001',
        'senderId': 'user_001',
        'type': 'image',
        'content': '契约图片消息',
        'mediaUrl': 'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        'media': {
          'url': 'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
          'thumbnailUrl':
              'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
          'mimeType': 'image/png',
          'fileName': 'fixture_photo_001_cover.png',
          'fileSizeBytes': 128000,
          'width': 960,
          'height': 720,
        },
        'status': 'sent',
        'timestamp': '2026-03-08T12:01:00Z',
      });

      expect(dto.type, 'image');
      expect(dto.mediaUrl, 'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png');
      expect(dto.media!['thumbnailUrl'], isNotNull);
      expect(dto.media!['mimeType'], 'image/png');
    });

    test('file 类型消息保留 fileName 与 mimeType', () {
      final dto = MessageDto.fromMap({
        '_id': 'msg_file_001',
        'conversationId': 'conv_001',
        'seq': 44,
        'clientMsgId': 'client_file_001',
        'senderId': 'user_001',
        'type': 'file',
        'content': '契约说明.pdf',
        'mediaUrl': 'media/file/s/archived-file/post/fixture_chat_file_001/v1/spec.pdf',
        'media': {
          'url': 'media/file/s/archived-file/post/fixture_chat_file_001/v1/spec.pdf',
          'mimeType': 'application/pdf',
          'fileName': 'spec.pdf',
          'fileSizeBytes': 2048,
        },
        'status': 'sent',
        'timestamp': '2026-03-08T12:02:00Z',
      });

      expect(dto.type, 'file');
      expect(dto.mediaUrl, 'media/file/s/archived-file/post/fixture_chat_file_001/v1/spec.pdf');
      expect(dto.media!['fileName'], 'spec.pdf');
      expect(dto.media!['mimeType'], 'application/pdf');
    });

    test('video 类型消息解析缩略图和时长', () {
      final dto = MessageDto.fromMap({
        '_id': 'msg_video_001',
        'conversationId': 'conv_001',
        'seq': 45,
        'clientMsgId': 'client_video_001',
        'senderId': 'user_001',
        'type': 'video',
        'content': '契约视频消息',
        'mediaUrl': 'media/video/s/archived-video/post/fixture_video_001/v1/video.mp4',
        'media': {
          'url': 'media/video/s/archived-video/post/fixture_video_001/v1/video.mp4',
          'thumbnailUrl':
              'media/image/s/archived-image/post/fixture_video_001/v1/cover.png',
          'mimeType': 'video/mp4',
          'fileName': 'fixture_video_001.mp4',
          'fileSizeBytes': 1048576,
          'durationMs': 93000,
        },
        'status': 'sent',
        'timestamp': '2026-03-08T12:03:00Z',
      });

      expect(dto.type, 'video');
      expect(dto.mediaUrl, 'media/video/s/archived-video/post/fixture_video_001/v1/video.mp4');
      expect(dto.media!['thumbnailUrl'], isNotNull);
      expect(dto.media!['durationMs'], 93000);
    });

    test('text 类型消息 media 字段为 null', () {
      final dto = MessageDto.fromMap({
        '_id': 'msg_002',
        'conversationId': 'conv_001',
        'seq': 43,
        'clientMsgId': 'client_002',
        'senderId': 'user_001',
        'type': 'text',
        'content': 'hello',
        'status': 'sent',
        'timestamp': '2026-03-08T12:01:00Z',
      });

      expect(dto.type, 'text');
      expect(dto.media, isNull);
    });

    test('toMap round-trip 包含 media 字段', () {
      final original = MessageDto(
        id: 'msg_003',
        conversationId: 'conv_001',
        seq: 44,
        clientMsgId: 'client_003',
        senderId: 'user_001',
        type: 'audio',
        content: '',
        mediaUrl: 'https://cdn.example.com/voice2.m4a',
        media: {
          'url': 'https://cdn.example.com/voice2.m4a',
          'durationMs': 3000,
        },
        status: 'sent',
        timestamp: DateTime.parse('2026-03-08T12:02:00Z'),
      );

      final map = original.toMap();
      expect(map['media'], isNotNull);
      expect(map['media']['durationMs'], 3000);

      final roundTripped = MessageDto.fromMap(map);
      expect(roundTripped.media!['durationMs'], 3000);
    });
  });

  group('MessageDto — 兼容性契约', () {
    test('旧消息无 media 字段仍正确解析', () {
      final dto = MessageDto.fromMap({
        '_id': 'msg_old',
        'conversationId': 'conv_001',
        'seq': 10,
        'clientMsgId': 'old_001',
        'senderId': 'user_001',
        'type': 'audio',
        'content': '',
        'mediaUrl': 'https://cdn.example.com/old_voice.m4a',
        'status': 'sent',
        'timestamp': '2026-01-01T00:00:00Z',
      });

      expect(dto.mediaUrl, 'https://cdn.example.com/old_voice.m4a');
      expect(dto.media, isNull);
    });

    test('copyWith 更新 media 字段', () {
      final original = MessageDto(
        id: 'msg_copy',
        conversationId: 'conv_001',
        seq: 50,
        clientMsgId: 'copy_001',
        senderId: 'user_001',
        type: 'audio',
        status: 'sending',
        timestamp: DateTime.now(),
      );

      final updated = original.copyWith(
        media: {'url': 'https://cdn.example.com/new.m4a', 'durationMs': 7000},
        status: 'sent',
      );

      expect(updated.media!['durationMs'], 7000);
      expect(updated.status, 'sent');
      expect(updated.id, original.id);
    });
  });

  group('MessageDto — 异常/边界契约', () {
    test('全字段缺失不崩溃', () {
      expect(() => MessageDto.fromMap({}), returnsNormally);
    });

    test('media 字段为非 Map 类型不崩溃', () {
      final dto = MessageDto.fromMap({
        '_id': 'msg_bad',
        'conversationId': 'conv_001',
        'seq': 1,
        'clientMsgId': 'bad_001',
        'senderId': 'user_001',
        'type': 'audio',
        'media': 'not_a_map',
        'status': 'sent',
        'timestamp': '2026-03-08T12:00:00Z',
      });
      expect(dto.media, isNull);
    });

    test('media 内 waveform 为空数组', () {
      final dto = MessageDto.fromMap({
        '_id': 'msg_empty_wave',
        'conversationId': 'conv_001',
        'seq': 2,
        'clientMsgId': 'wave_001',
        'senderId': 'user_001',
        'type': 'audio',
        'media': {'url': 'https://cdn.example.com/v.m4a', 'waveform': []},
        'status': 'sent',
        'timestamp': '2026-03-08T12:00:00Z',
      });
      expect(dto.media!['waveform'], isEmpty);
    });
  });
}
