// spec_ref: specs/feature-tree/runtime/runtime-media/media-upload-and-storage/spec.md#gwt-001

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/application/content/media/content_media_upload_coordinator.dart';
import 'package:quwoquan_app/ui/content/entry/services/create_page_remote_helpers.dart';
import 'package:quwoquan_app/ui/content/models/article_document_models.dart';
import 'package:quwoquan_app/ui/content/models/create_editor_models.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../support/recording_content_media_facet.dart';

void main() {
  test(
    'article cover and inline images bind only MediaAsset identities',
    () async {
      final media = RecordingContentMediaFacet();
      final sources = _MemorySourceReader(<String, List<int>>{
        '/local/cover.jpg': <int>[1, 2, 3],
        '/local/inline.png': <int>[4, 5, 6],
      });
      final state = CreateEditorState.initial(editorKind: CreateEditorKind.text)
          .copyWith(
            title: '有图文章',
            body: '正文',
            articleCoverImagePath: '/local/cover.jpg',
            articleDocument: ArticleDocumentData(
              nodes: const <ArticleDocumentNode>[
                ArticleDocumentNode(
                  id: 'title',
                  type: ArticleDocumentNodeType.documentTitle,
                  text: '有图文章',
                ),
                ArticleDocumentNode(
                  id: 'figure-local',
                  type: ArticleDocumentNodeType.figure,
                  assetId: 'figure-local',
                  imageUrl: '/local/inline.png',
                  imageLayout: 'wrapLeft',
                  caption: '配图',
                ),
                ArticleDocumentNode(
                  id: 'paragraph',
                  type: ArticleDocumentNodeType.paragraph,
                  text: '正文',
                ),
              ],
            ),
          );

      final prepared = await buildPostPublicationPayloadWithRemoteMedia(
        media: media,
        state: state,
        mediaPreparationIdentity: 'article-media-draft',
        sourceReader: sources,
        uploadStream: _drainUpload,
      );

      expect(prepared.payload['contentType'], 'article');
      expect(prepared.mediaAssetIds, <String>[
        'image_asset_1',
        'image_asset_2',
      ]);
      expect(
        prepared.payload['articleMarkdown'],
        contains('asset://image_asset_1'),
      );
      expect(
        prepared.payload['articleMarkdown'],
        contains('asset://image_asset_2'),
      );
      final manifest =
          prepared.payload['articleAssetManifest'] as Map<String, dynamic>;
      final serialized = manifest.toString();
      expect(serialized, contains('image_asset_1'));
      expect(serialized, contains('image_asset_2'));
      for (final forbidden in <String>[
        '/local/',
        'localPath',
        'objectKey',
        'cdnUrl',
        'uploadUrl',
      ]) {
        expect(
          '${prepared.payload}',
          isNot(contains(forbidden)),
          reason: 'Post command exposed $forbidden',
        );
      }
      expect(
        media.completeCommands.map((command) => command.accessPolicy),
        everyElement(ContentMediaAccessPolicy.referencedPost),
      );
    },
  );

  test(
    'short text with an image remains micro and uploads the image',
    () async {
      final media = RecordingContentMediaFacet();
      final state = CreateEditorState.initial(
        editorKind: CreateEditorKind.text,
      ).copyWith(body: '随手记录', imagePaths: const <String>['/local/micro.jpg']);

      final prepared = await buildPostPublicationPayloadWithRemoteMedia(
        media: media,
        state: state,
        mediaPreparationIdentity: 'micro-media-draft',
        sourceReader: _MemorySourceReader(<String, List<int>>{
          '/local/micro.jpg': <int>[7, 8, 9],
        }),
        uploadStream: _drainUpload,
      );

      expect(prepared.payload['contentType'], 'micro');
      expect(prepared.mediaAssetIds, <String>['image_asset_1']);
      expect('${prepared.payload}', isNot(contains('/local/')));
      expect(prepared.payload, isNot(contains('mediaUrls')));
    },
  );
}

Future<void> _drainUpload(
  Uri _,
  Stream<List<int>> body, {
  required int contentLength,
  required String mimeType,
  required String expectedSha256,
  Future<void>? abortTrigger,
}) async {
  final bytes = await body.expand((chunk) => chunk).toList();
  expect(bytes, hasLength(contentLength));
}

final class _MemorySourceReader implements ContentMediaSourceReader {
  const _MemorySourceReader(this.bytesByPath);

  final Map<String, List<int>> bytesByPath;

  @override
  Future<PreparedContentMediaSource> prepare(String localPath) async {
    final bytes = bytesByPath[localPath];
    if (bytes == null) throw StateError('missing source $localPath');
    return PreparedContentMediaSource(
      fileSize: bytes.length,
      sha256Digest: sha256.convert(bytes).toString(),
      openRead: () => Stream<List<int>>.value(bytes),
    );
  }
}
