import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/application/content/media/content_media_upload_coordinator.dart';
import 'package:quwoquan_app/core/platform/file_storage_gateway.dart';
import 'package:quwoquan_app/ui/content/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/services/create_page_remote_helpers.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../support/recording_content_media_facet.dart';

void main() {
  group('photo publish payload media refs', () {
    test('图片发布只把 MediaAsset ID 交给后续服务端绑定', () async {
      final media = RecordingContentMediaFacet();
      final fileStorage = _MemoryFileStorageGateway(<String, List<int>>{
        '/tmp/a.jpg': <int>[1, 2, 3],
        '/tmp/b.png': <int>[4, 5, 6],
      });
      final uploads = <_UploadCall>[];
      final state =
          CreateEditorState.initial(
            editorKind: CreateEditorKind.media,
          ).copyWith(
            mediaKind: CreateMediaKind.images,
            imagePaths: <String>['/tmp/a.jpg', '/tmp/b.png'],
            title: '图片作品',
          );

      final prepared = await buildPostPublicationPayloadWithRemoteMedia(
        media: media,
        state: state,
        mediaPreparationIdentity: 'photo-payload-draft',
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
        <ContentMediaType>[ContentMediaType.image, ContentMediaType.image],
      );
      expect(media.initCommands.map((command) => command.fileSize), <int>[
        3,
        3,
      ]);
      expect(
        media.initCommands.map((command) => command.expectedSha256),
        everyElement(matches(RegExp(r'^[0-9a-f]{64}$'))),
      );
      expect(uploads.map((call) => call.uri.toString()).toList(), <String>[
        'https://upload.quwoquan.test/session_1',
        'https://upload.quwoquan.test/session_2',
      ]);
      expect(uploads.map((call) => call.mimeType).toList(), <String>[
        'image/jpeg',
        'image/png',
      ]);
      expect(prepared.mediaAssetIds, <String>[
        'image_asset_1',
        'image_asset_2',
      ]);
      expect(
        media.completeCommands.map((command) => command.accessPolicy),
        everyElement(ContentMediaAccessPolicy.referencedPost),
      );
      expect(prepared.payload, isNot(contains('mediaUrls')));
      expect(prepared.payload, isNot(contains('coverUrl')));
      expect(prepared.payload, isNot(contains('mediaItems')));
      expect(prepared.payload.values.toString(), isNot(contains('/tmp/')));
      expect(
        prepared.payload.values.toString(),
        isNot(contains('cdn.quwoquan.test')),
      );
    });

    test('本地图片上传失败会 abort 当前 upload session 且不产出半成品 payload', () async {
      final media = RecordingContentMediaFacet();
      final fileStorage = _MemoryFileStorageGateway(<String, List<int>>{
        '/tmp/a.jpg': <int>[1, 2, 3],
      });
      final state =
          CreateEditorState.initial(
            editorKind: CreateEditorKind.media,
          ).copyWith(
            mediaKind: CreateMediaKind.images,
            imagePaths: <String>['/tmp/a.jpg'],
          );

      await expectLater(
        buildPostPublicationPayloadWithRemoteMedia(
          media: media,
          state: state,
          mediaPreparationIdentity: 'photo-failure-draft',
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
                throw StateError('upload failed');
              },
        ),
        throwsStateError,
      );

      expect(media.abortedSessions, <String>['session_1']);
      expect(media.completedSessions, isEmpty);
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
