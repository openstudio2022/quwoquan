import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/application/content/media/content_media_upload_coordinator.dart';
import 'package:quwoquan_app/core/platform/file_storage_gateway.dart';
import 'package:quwoquan_app/ui/content/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/services/create_page_remote_helpers.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../support/recording_content_media_facet.dart';

void main() {
  group('video publish payload cover contract', () {
    test('视频发布上传视频与封面并只携带 MediaAsset ID', () async {
      final media = RecordingContentMediaFacet();
      final fileStorage = _MemoryFileStorageGateway(<String, List<int>>{
        '/tmp/clip.mp4': <int>[1, 2, 3, 4],
        '/tmp/cover.jpg': <int>[5, 6, 7],
      });
      final uploads = <_UploadCall>[];
      final state =
          CreateEditorState.initial(
            editorKind: CreateEditorKind.media,
          ).copyWith(
            mediaKind: CreateMediaKind.video,
            videoPath: '/tmp/clip.mp4',
            originalVideoPath: '/tmp/clip.mp4',
            videoThumbnail: '/tmp/cover.jpg',
            videoDurationMs: 12345,
            videoCoverTimeMs: 3200,
            videoCoverStrategy: 'manual',
            videoWidth: 1080,
            videoHeight: 1920,
            title: '视频作品',
          );

      final prepared = await buildPostPublicationPayloadWithRemoteMedia(
        media: media,
        state: state,
        mediaPreparationIdentity: 'video-cover-payload-draft',
        sourceReader: _MemoryContentMediaSourceReader(fileStorage.bytesByPath),
        uploadStream:
            (
              uri,
              bytes, {
              required contentLength,
              required mimeType,
              required expectedSha256,
              abortTrigger,
            }) async {
              final uploadedBytes = await bytes
                  .expand((chunk) => chunk)
                  .toList();
              expect(uploadedBytes.length, contentLength);
              uploads.add(_UploadCall(uri, uploadedBytes, mimeType));
            },
      );

      expect(
        media.initCommands.map((command) => command.mediaType),
        <MediaType>[MediaType.video, MediaType.image],
      );
      expect(uploads.map((call) => call.mimeType).toList(), <String>[
        'video/mp4',
        'image/jpeg',
      ]);
      expect(prepared.mediaAssetIds, <String>[
        'video_asset_1',
        'image_asset_2',
      ]);
      expect(prepared.payload, isNot(contains('videoUrl')));
      expect(prepared.payload, isNot(contains('thumbnailUrl')));
      expect(prepared.payload, isNot(contains('coverUrl')));
      expect(prepared.payload['coverStrategy'], 'manual');
      expect(prepared.payload['coverFrameTimeMs'], 3200);
      expect(prepared.payload['durationMs'], 12345);
      expect(prepared.payload['width'], 1080);
      expect(prepared.payload['height'], 1920);
      expect(prepared.payload.values.toString(), isNot(contains('/tmp/')));
      expect(prepared.payload, isNot(contains('mediaItems')));
      expect(media.selectedManualCovers, hasLength(1));
      expect(media.selectedManualCovers.single.mediaId, 'video_asset_1');
      expect(media.selectedManualCovers.single.coverAssetId, 'image_asset_2');
      expect(media.selectedAutoCoverMediaIds, isEmpty);
      expect(
        prepared.payload.values.toString(),
        isNot(contains('cdn.quwoquan.test')),
      );
    });

    test('首次发布媒体准备意图不持久化本地路径或未生成的媒体引用', () {
      final state =
          CreateEditorState.initial(
            editorKind: CreateEditorKind.media,
          ).copyWith(
            mediaKind: CreateMediaKind.video,
            videoPath: '/tmp/clip.mp4',
            videoThumbnail: '/tmp/cover.jpg',
            videoDurationMs: 12345,
            videoCoverTimeMs: 3200,
            videoCoverStrategy: 'manual',
            videoWidth: 1080,
            videoHeight: 1920,
            title: '视频作品',
          );

      final preparation = buildPostPublicationMediaPreparationPayload(state);

      expect(preparation.mediaAssetIds, isEmpty);
      expect(preparation.payload, isNot(contains('mediaUrls')));
      expect(preparation.payload, isNot(contains('videoUrl')));
      expect(preparation.payload, isNot(contains('thumbnailUrl')));
      expect(preparation.payload, isNot(contains('coverUrl')));
      expect(preparation.payload, isNot(contains('mediaItems')));
      expect(preparation.payload.values.toString(), isNot(contains('/tmp/')));
      expect(preparation.payload['coverStrategy'], 'manual');
      expect(preparation.payload['coverFrameTimeMs'], 3200);
      expect(preparation.payload['durationMs'], 12345);
      expect(preparation.payload['width'], 1080);
      expect(preparation.payload['height'], 1920);
    });

    test('封面上传失败会 abort 封面 session 且不返回半成品 payload', () async {
      final media = RecordingContentMediaFacet();
      final fileStorage = _MemoryFileStorageGateway(<String, List<int>>{
        '/tmp/clip.mp4': <int>[1, 2, 3, 4],
        '/tmp/cover.jpg': <int>[5, 6, 7],
      });
      final state =
          CreateEditorState.initial(
            editorKind: CreateEditorKind.media,
          ).copyWith(
            mediaKind: CreateMediaKind.video,
            videoPath: '/tmp/clip.mp4',
            videoThumbnail: '/tmp/cover.jpg',
            videoCoverStrategy: 'manual',
          );

      await expectLater(
        buildPostPublicationPayloadWithRemoteMedia(
          media: media,
          state: state,
          mediaPreparationIdentity: 'video-cover-failure-draft',
          sourceReader: _MemoryContentMediaSourceReader(
            fileStorage.bytesByPath,
          ),
          uploadStream:
              (
                uri,
                bytes, {
                required contentLength,
                required mimeType,
                required expectedSha256,
                abortTrigger,
              }) async {
                if (mimeType == 'image/jpeg') {
                  throw StateError('cover upload failed');
                }
                await bytes.drain<void>();
              },
        ),
        throwsStateError,
      );

      expect(media.abortedSessions, <String>['session_2']);
      expect(media.selectedManualCovers, isEmpty);
    });
  });
}

class _UploadCall {
  const _UploadCall(this.uri, this.bytes, this.mimeType);

  final Uri uri;
  final List<int> bytes;
  final String mimeType;
}

class _MemoryContentMediaSourceReader implements ContentMediaSourceReader {
  const _MemoryContentMediaSourceReader(this.bytesByPath);

  final Map<String, List<int>> bytesByPath;

  @override
  Future<PreparedContentMediaSource> prepare(String localPath) async {
    final bytes = bytesByPath[localPath]!;
    return PreparedContentMediaSource(
      fileSize: bytes.length,
      sha256Digest: sha256.convert(bytes).toString(),
      openRead: () => Stream<List<int>>.value(bytes),
    );
  }
}

class _MemoryFileStorageGateway implements FileStorageGateway {
  const _MemoryFileStorageGateway(this.bytesByPath);

  final Map<String, List<int>> bytesByPath;

  @override
  bool get isSupported => true;

  @override
  Future<String> applicationSupportPath() async => '/tmp/support';

  @override
  Future<String> temporaryPath() async => '/tmp';

  @override
  Future<bool> exists(String path) async => bytesByPath.containsKey(path);

  @override
  Future<void> writeAsString(String path, String contents) async {}

  @override
  Future<String> readAsString(String path) async => '';

  @override
  Future<List<int>> readAsBytes(String path) async => bytesByPath[path]!;

  @override
  Future<void> writeAsBytes(String path, List<int> bytes) async {}

  @override
  Future<void> delete(String path) async {}

  @override
  Future<void> ensureDirectory(String path) async {}

  @override
  Future<List<FileSystemEntry>> listDirectory(String path) async =>
      const <FileSystemEntry>[];
}
