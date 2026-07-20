import 'dart:async';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/application/content/media/content_media_upload_coordinator.dart';
import 'package:quwoquan_app/cloud/media/media_upload_manager.dart';
import 'package:quwoquan_app/cloud/media/upload_policy.dart';
import 'package:quwoquan_app/cloud/remote/content/media/local_media_upload_source.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

import '../../../support/recording_content_media_facet.dart';

void main() {
  group('MediaUploadManager typed Media Facet', () {
    test('Chat 复用 MediaUploadSession 聚合与统一数据面', () async {
      final tempDir = Directory.systemTemp.createTempSync('qwq-chat-upload-');
      addTearDown(() => tempDir.deleteSync(recursive: true));
      final filePath = '${tempDir.path}/clip.mp4';
      const bytes = <int>[1, 2, 3, 4];
      File(filePath).writeAsBytesSync(bytes);

      final media = RecordingContentMediaFacet();
      Uri? uploadedUri;
      List<int>? uploadedBytes;
      String? uploadedContentType;
      final manager = MediaUploadManager(
        coordinator: ContentMediaUploadCoordinator(media: media),
        sourceReader: const LocalContentMediaSourceReader(),
        uploadStream:
            (
              uri,
              body, {
              required contentLength,
              required contentType,
              required expectedSha256,
              Future<void>? abortTrigger,
            }) async {
              uploadedUri = uri;
              uploadedContentType = contentType;
              final collected = <int>[];
              await for (final chunk in body) {
                collected.addAll(chunk);
              }
              expect(collected.length, contentLength);
              uploadedBytes = collected;
            },
        maxConcurrent: 1,
      );
      addTearDown(manager.dispose);
      final task = UploadTask(
        localPath: filePath,
        category: MediaCategory.chatVideo,
        contentType: 'video/mp4',
        fileSize: bytes.length,
      );
      final completed = Completer<UploadTask>();
      final sub = manager.onTaskUpdate.listen((update) {
        if (update.localPath == filePath &&
            update.status == UploadStatus.completed &&
            !completed.isCompleted) {
          completed.complete(update);
        }
      });
      addTearDown(sub.cancel);

      await manager.enqueue(task);
      final result = await completed.future.timeout(const Duration(seconds: 5));

      final init = media.initCommands.single;
      expect(init.mediaType, ContentMediaType.video);
      expect(init.contentType, 'video/mp4');
      expect(init.fileSize, bytes.length);
      expect(init.expectedSha256, 'sha256:${sha256.convert(bytes)}');
      expect(media.completedSessions, <String>['session_1']);
      expect(media.abortedSessions, isEmpty);
      expect(uploadedUri, Uri.parse('https://upload.quwoquan.test/session_1'));
      expect(uploadedBytes, bytes);
      expect(uploadedContentType, 'video/mp4');
      expect(result.assetId, 'video_asset_1');
      expect(result.cdnUrl, 'https://cdn.quwoquan.test/video_asset_1.mp4');
    });

    test('数据面失败会中止权威 session 且不伪造成功', () async {
      final tempDir = Directory.systemTemp.createTempSync('qwq-chat-upload-');
      addTearDown(() => tempDir.deleteSync(recursive: true));
      final filePath = '${tempDir.path}/clip.mp4';
      File(filePath).writeAsBytesSync(<int>[1, 2, 3, 4]);

      final media = RecordingContentMediaFacet();
      final manager = MediaUploadManager(
        coordinator: ContentMediaUploadCoordinator(media: media),
        sourceReader: const LocalContentMediaSourceReader(),
        uploadStream:
            (
              _,
              _, {
              required contentLength,
              required contentType,
              required expectedSha256,
              Future<void>? abortTrigger,
            }) async {
              throw StateError('object storage rejected upload');
            },
        maxConcurrent: 1,
        maxRetries: 0,
      );
      addTearDown(manager.dispose);
      final completed = Completer<UploadTask>();
      final sub = manager.onTaskUpdate.listen((update) {
        if (update.status == UploadStatus.failed && !completed.isCompleted) {
          completed.complete(update);
        }
      });
      addTearDown(sub.cancel);

      await manager.enqueue(
        UploadTask(
          localPath: filePath,
          category: MediaCategory.chatVideo,
          contentType: 'video/mp4',
          fileSize: 4,
        ),
      );
      final result = await completed.future.timeout(const Duration(seconds: 2));

      expect(media.completedSessions, isEmpty);
      expect(media.abortedSessions, <String>['session_1']);
      expect(result.status, UploadStatus.failed);
      expect(result.error, RuntimeFailureCodes.cloudSystemUnavailable);
    });
  });
}
