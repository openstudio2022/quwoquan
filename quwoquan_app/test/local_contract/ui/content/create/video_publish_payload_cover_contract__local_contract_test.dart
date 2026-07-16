import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/platform/file_storage_gateway.dart';
import 'package:quwoquan_app/ui/content/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/services/create_page_remote_helpers.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../support/recording_content_media_facet.dart';

void main() {
  group('video publish payload cover contract', () {
    test('视频发布上传视频与封面并只携带远端引用', () async {
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

      final prepared = await buildCreatePostPayloadWithRemoteImageMedia(
        media: media,
        fileStorageGateway: fileStorage,
        state: state,
        uploadObject:
            (
              uri,
              bytes, {
              required contentType,
              required expectedSha256,
            }) async {
              uploads.add(_UploadCall(uri, bytes, contentType));
            },
      );

      expect(
        media.initCommands.map((command) => command.mediaType),
        <ContentMediaType>[ContentMediaType.video, ContentMediaType.image],
      );
      expect(uploads.map((call) => call.contentType).toList(), <String>[
        'video/mp4',
        'image/jpeg',
      ]);
      expect(prepared.mediaAssetIds, <String>[
        'video_asset_1',
        'image_asset_2',
      ]);
      expect(
        prepared.payload['videoUrl'],
        'https://cdn.quwoquan.test/video_asset_1.mp4',
      );
      expect(
        prepared.payload['thumbnailUrl'],
        'https://cdn.quwoquan.test/image_asset_2.jpg',
      );
      expect(
        prepared.payload['coverUrl'],
        'https://cdn.quwoquan.test/image_asset_2.jpg',
      );
      expect(prepared.payload['coverStrategy'], 'manual');
      expect(prepared.payload['coverFrameTimeMs'], 3200);
      expect(prepared.payload['durationMs'], 12345);
      expect(prepared.payload['width'], 1080);
      expect(prepared.payload['height'], 1920);
      expect(prepared.payload.values.toString(), isNot(contains('/tmp/')));
      final mediaItems =
          prepared.payload['mediaItems'] as List<Map<String, Object?>>;
      expect(
        mediaItems.single['thumbnailUrl'],
        prepared.payload['thumbnailUrl'],
      );
      expect(mediaItems.single['coverUrl'], prepared.payload['coverUrl']);
      expect(mediaItems.single['mediaId'], 'video_asset_1');
      expect(mediaItems.single['coverAssetId'], 'image_asset_2');
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
        buildCreatePostPayloadWithRemoteImageMedia(
          media: media,
          fileStorageGateway: fileStorage,
          state: state,
          uploadObject:
              (
                uri,
                bytes, {
                required contentType,
                required expectedSha256,
              }) async {
                if (contentType == 'image/jpeg') {
                  throw StateError('cover upload failed');
                }
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
  const _UploadCall(this.uri, this.bytes, this.contentType);

  final Uri uri;
  final List<int> bytes;
  final String contentType;
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
