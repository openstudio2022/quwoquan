import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/media/upload_policy.dart';

void main() {
  group('UploadPolicy — 常规契约', () {
    test('chatVoice 允许 audio/mp4', () {
      final error = validateUpload(
        category: MediaCategory.chatVoice,
        fileSize: 48000,
        contentType: 'audio/mp4',
      );
      expect(error, isNull);
    });

    test('chatVoice 允许 audio/aac', () {
      final error = validateUpload(
        category: MediaCategory.chatVoice,
        fileSize: 48000,
        contentType: 'audio/aac',
      );
      expect(error, isNull);
    });

    test('chatImage 允许 image/jpeg', () {
      final error = validateUpload(
        category: MediaCategory.chatImage,
        fileSize: 1024 * 1024,
        contentType: 'image/jpeg',
      );
      expect(error, isNull);
    });

    test('所有 Category 都有默认策略', () {
      for (final category in MediaCategory.values) {
        expect(defaultPolicies[category], isNotNull,
            reason: 'Missing policy for $category');
      }
    });
  });

  group('UploadPolicy — 兼容性契约', () {
    test('chatFile 允许任意 contentType（空 allowedTypes）', () {
      final error = validateUpload(
        category: MediaCategory.chatFile,
        fileSize: 1024 * 1024,
        contentType: 'application/pdf',
      );
      expect(error, isNull);
    });
  });

  group('UploadPolicy — 异常/边界契约', () {
    test('chatVoice 超过 10MB 被拒绝', () {
      final error = validateUpload(
        category: MediaCategory.chatVoice,
        fileSize: 20 * 1024 * 1024,
        contentType: 'audio/mp4',
      );
      expect(error, isNotNull);
      expect(error, contains('文件大小超过限制'));
    });

    test('chatVoice 不允许 video/mp4', () {
      final error = validateUpload(
        category: MediaCategory.chatVoice,
        fileSize: 48000,
        contentType: 'video/mp4',
      );
      expect(error, isNotNull);
      expect(error, contains('不支持的文件类型'));
    });

    test('chatImage 超过 20MB 被拒绝', () {
      final error = validateUpload(
        category: MediaCategory.chatImage,
        fileSize: 30 * 1024 * 1024,
        contentType: 'image/jpeg',
      );
      expect(error, isNotNull);
    });
  });
}
