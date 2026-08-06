// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-003

import 'dart:async';
import 'dart:io';
import 'dart:math';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/content_media_upload_coordinator.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/media_upload_queue.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/adapters/media_upload_manager.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/adapters/local_media_upload_source.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

import '../../../../../support/runtime/transport/recording_content_media_facet.dart';

void main() {
  test('retry 只使用有界全抖动，不存在确定性指数延迟', () {
    expect(
      mediaUploadFullJitterDelay(
        retryCount: 1,
        random: _BoundaryRandom(useUpperBound: false),
      ),
      Duration.zero,
    );
    expect(
      mediaUploadFullJitterDelay(
        retryCount: 1,
        random: _BoundaryRandom(useUpperBound: true),
      ),
      const Duration(seconds: 1),
    );
    expect(
      mediaUploadFullJitterDelay(
        retryCount: 99,
        random: _BoundaryRandom(useUpperBound: true),
      ),
      const Duration(seconds: 32),
    );
  });

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
              required mimeType,
              required expectedSha256,
              Future<void>? abortTrigger,
            }) async {
              uploadedUri = uri;
              uploadedContentType = mimeType;
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
        mimeType: 'video/mp4',
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
      expect(init.mediaType, MediaType.video);
      expect(init.mimeType, 'video/mp4');
      expect(init.fileSize, bytes.length);
      expect(init.expectedSha256, '${sha256.convert(bytes)}');
      expect(media.completedSessions, <String>['session_1']);
      expect(media.abortedSessions, isEmpty);
      expect(uploadedUri, Uri.parse('https://upload.quwoquan.test/session_1'));
      expect(uploadedBytes, bytes);
      expect(uploadedContentType, 'video/mp4');
      expect(result.assetId, 'video_asset_1');
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
              required mimeType,
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
          mimeType: 'video/mp4',
          fileSize: 4,
        ),
      );
      final result = await completed.future.timeout(const Duration(seconds: 2));

      expect(media.completedSessions, isEmpty);
      expect(media.abortedSessions, <String>['session_1']);
      expect(result.status, UploadStatus.failed);
      expect(result.error, RuntimeFailureCodes.cloudSystemUnavailable);
    });

    test('账号 closed 后 disposed manager 清空队列并拒绝旧实例继续上传', () async {
      final manager = MediaUploadManager(
        coordinator: ContentMediaUploadCoordinator(
          media: RecordingContentMediaFacet(),
        ),
        sourceReader: const LocalContentMediaSourceReader(),
        uploadStream:
            (
              _,
              _, {
              required contentLength,
              required mimeType,
              required expectedSha256,
              Future<void>? abortTrigger,
            }) async {},
      );

      manager.dispose();

      await expectLater(
        manager.enqueue(
          UploadTask(
            localPath: '/tmp/closed.jpg',
            category: MediaCategory.chatImage,
            mimeType: 'image/jpeg',
            fileSize: 4,
          ),
        ),
        throwsStateError,
      );
      expect(manager.pendingCount, 0);
      expect(manager.activeCount, 0);
    });
  });
}

final class _BoundaryRandom implements Random {
  const _BoundaryRandom({required this.useUpperBound});

  final bool useUpperBound;

  @override
  bool nextBool() => useUpperBound;

  @override
  double nextDouble() => useUpperBound ? 0.999999 : 0;

  @override
  int nextInt(int max) => useUpperBound ? max - 1 : 0;
}
