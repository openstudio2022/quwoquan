import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/media/media_asset_dto.dart';

void main() {
  group('MediaAssetDto — 常规契约', () {
    test('fromMap 全字段解析', () {
      final dto = MediaAssetDto.fromMap({
        'assetId': 'ma_001',
        'sessionId': 'us_001',
        'category': 'chat_voice',
        'ownerId': 'user_001',
        'fileName': 'voice.m4a',
        'contentType': 'audio/mp4',
        'fileSize': 48000,
        'ossKey': 'media/chat_voice/2026/03/08/user_001/us_001_voice.m4a',
        'cdnUrl': 'https://cdn.example.com/media/chat_voice/voice.m4a',
        'durationMs': 5200,
        'createdAt': '2026-03-08T12:00:00Z',
      });

      expect(dto.assetId, 'ma_001');
      expect(dto.category, 'chat_voice');
      expect(dto.durationMs, 5200);
      expect(dto.cdnUrl, contains('cdn.example.com'));
    });

    test('toMap round-trip 正确', () {
      final original = MediaAssetDto(
        assetId: 'ma_002',
        sessionId: 'us_002',
        category: 'chat_image',
        ownerId: 'user_002',
        fileName: 'photo.jpg',
        contentType: 'image/jpeg',
        fileSize: 1024000,
        ossKey: 'media/chat_image/photo.jpg',
        cdnUrl: 'https://cdn.example.com/photo.jpg',
        width: 1920,
        height: 1080,
        createdAt: DateTime.parse('2026-03-08T12:00:00Z'),
      );

      final map = original.toMap();
      final roundTripped = MediaAssetDto.fromMap(map);
      expect(roundTripped.width, 1920);
      expect(roundTripped.height, 1080);
    });
  });

  group('MediaAssetDto — 兼容性契约', () {
    test('可选字段缺失正确解析', () {
      final dto = MediaAssetDto.fromMap({
        'assetId': 'ma_003',
        'sessionId': 'us_003',
        'category': 'chat_voice',
        'ownerId': 'user_001',
        'fileName': 'voice.m4a',
        'contentType': 'audio/mp4',
        'fileSize': 48000,
        'ossKey': 'key',
        'cdnUrl': 'https://cdn.example.com/voice.m4a',
        'createdAt': '2026-03-08T12:00:00Z',
      });

      expect(dto.durationMs, isNull);
      expect(dto.width, isNull);
      expect(dto.height, isNull);
      expect(dto.metadata, isNull);
    });
  });

  group('MediaAssetDto — 异常/边界契约', () {
    test('全字段缺失不崩溃', () {
      expect(() => MediaAssetDto.fromMap({}), returnsNormally);
    });

    test('toMap 不包含 null 可选字段', () {
      final dto = MediaAssetDto(
        assetId: 'ma_004',
        sessionId: 'us_004',
        category: 'post',
        ownerId: 'user_003',
        fileName: 'file.txt',
        contentType: 'text/plain',
        fileSize: 100,
        ossKey: 'key',
        cdnUrl: 'url',
        createdAt: DateTime.now(),
      );

      final map = dto.toMap();
      expect(map.containsKey('durationMs'), isFalse);
      expect(map.containsKey('width'), isFalse);
      expect(map.containsKey('metadata'), isFalse);
    });
  });
}
