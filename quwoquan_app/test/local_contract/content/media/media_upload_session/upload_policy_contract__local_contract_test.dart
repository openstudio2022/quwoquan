import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/application/content/media/generated/content_media_upload_policy.g.dart';
import 'package:quwoquan_app/cloud/content/generated/content_errors.g.dart';
import 'package:quwoquan_app/content/media/media_upload_session/domain/upload_policy.dart';

void main() {
  group('UploadPolicy — 常规契约', () {
    test('chatVoice 允许 audio/mp4', () {
      final error = validateUpload(
        category: MediaCategory.chatVoice,
        fileSize: 48000,
        mimeType: 'audio/mp4',
      );
      expect(error, isNull);
    });

    test('chatVoice 允许 audio/aac', () {
      final error = validateUpload(
        category: MediaCategory.chatVoice,
        fileSize: 48000,
        mimeType: 'audio/aac',
      );
      expect(error, isNull);
    });

    test('chatImage 允许 image/jpeg', () {
      final error = validateUpload(
        category: MediaCategory.chatImage,
        fileSize: 1024 * 1024,
        mimeType: 'image/jpeg',
      );
      expect(error, isNull);
    });

    test('所有 Category 都映射到 metadata 生成策略', () {
      for (final category in MediaCategory.values) {
        expect(
          ContentMediaUploadPolicy.mediaTypes[contentMediaTypeForCategory(
            category,
          ).name],
          isNotNull,
          reason: 'Missing generated policy for $category',
        );
      }
    });
  });

  group('UploadPolicy — 单轨契约', () {
    test('chatFile 允许任意 mimeType（空 allowedTypes）', () {
      final error = validateUpload(
        category: MediaCategory.chatFile,
        fileSize: 1024 * 1024,
        mimeType: 'application/pdf',
      );
      expect(error, isNull);
    });
  });

  group('UploadPolicy — 异常/边界契约', () {
    test('chatVoice 超过 10MB 被拒绝', () {
      final error = validateUpload(
        category: MediaCategory.chatVoice,
        fileSize: 20 * 1024 * 1024,
        mimeType: 'audio/mp4',
      );
      expect(
        error,
        ContentErrorMessages.zh[ContentErrorCode.mediaFileTooLarge],
      );
    });

    test('chatVoice 不允许 video/mp4', () {
      final error = validateUpload(
        category: MediaCategory.chatVoice,
        fileSize: 48000,
        mimeType: 'video/mp4',
      );
      expect(
        error,
        ContentErrorMessages.zh[ContentErrorCode.mediaTypeUnsupported],
      );
    });

    test('chatImage 遵循 canonical 50MiB 上限', () {
      expect(
        validateUpload(
          category: MediaCategory.chatImage,
          fileSize: 30 * 1024 * 1024,
          mimeType: 'image/jpeg',
        ),
        isNull,
      );
      final error = validateUpload(
        category: MediaCategory.chatImage,
        fileSize: 50 * 1024 * 1024 + 1,
        mimeType: 'image/jpeg',
      );
      expect(
        error,
        ContentErrorMessages.zh[ContentErrorCode.mediaFileTooLarge],
      );
    });
  });
}
