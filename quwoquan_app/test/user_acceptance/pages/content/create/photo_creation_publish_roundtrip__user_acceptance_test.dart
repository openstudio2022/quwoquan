import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/application/content/media/content_media_upload_coordinator.dart';
import 'package:quwoquan_app/core/platform/file_storage_gateway.dart';
import 'package:quwoquan_app/ui/content/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/services/create_page_remote_helpers.dart';

import '../../../../support/recording_content_media_facet.dart';
import '../../../../support/recording_content_post_publication_writer.dart';

void main() {
  test('图片创作发布旅程保持选图顺序并原子提交 MediaAsset ID', () async {
    final media = RecordingContentMediaFacet();
    final publication = RecordingContentPostPublicationWriter();
    final fileStorage = _JourneyFileStorageGateway(<String, List<int>>{
      '/tmp/first.jpg': <int>[1],
      '/tmp/second.jpg': <int>[2],
      '/tmp/third.jpg': <int>[3],
    });
    final state = CreateEditorState.initial(editorKind: CreateEditorKind.media)
        .copyWith(
          mediaKind: CreateMediaKind.images,
          imagePaths: <String>[
            '/tmp/second.jpg',
            '/tmp/first.jpg',
            '/tmp/third.jpg',
          ],
          body: '按用户拖动后的顺序发布。',
        );

    final prepared = await buildPostPublicationPayloadWithRemoteMedia(
      media: media,
      state: state,
      sourceReader: _JourneyContentMediaSourceReader(fileStorage.bytesByPath),
      uploadStream:
          (
            uri,
            bytes, {
            required contentLength,
            required contentType,
            required expectedSha256,
            abortTrigger,
          }) async {
            final uploadedBytes = await bytes.expand((chunk) => chunk).toList();
            expect(uploadedBytes.length, contentLength);
          },
    );
    final command = submitContentPostPublicationCommandFromPreparedPayload(
      prepared.payload,
      localDraftId: 'draft-photo-roundtrip',
      mediaAssetIds: prepared.mediaAssetIds,
    );
    await publication.submitPostPublication(command);

    expect(prepared.payload['contentType'], 'image');
    expect(prepared.payload, isNot(contains('mediaUrls')));
    expect(prepared.payload, isNot(contains('coverUrl')));
    expect(prepared.payload['mediaItems'], <Map<String, Object?>>[
      <String, Object?>{'kind': 'image', 'mediaId': 'image_asset_1'},
      <String, Object?>{'kind': 'image', 'mediaId': 'image_asset_2'},
      <String, Object?>{'kind': 'image', 'mediaId': 'image_asset_3'},
    ]);
    expect(publication.submitCommands.single.mediaAssetIds, <String>[
      'image_asset_1',
      'image_asset_2',
      'image_asset_3',
    ]);
  });
}

class _JourneyContentMediaSourceReader implements ContentMediaSourceReader {
  const _JourneyContentMediaSourceReader(this.bytesByPath);

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

class _JourneyFileStorageGateway implements FileStorageGateway {
  const _JourneyFileStorageGateway(this.bytesByPath);

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
  Future<String> readAsString(String path) async => '';

  @override
  Future<void> writeAsString(String path, String contents) async {}

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
