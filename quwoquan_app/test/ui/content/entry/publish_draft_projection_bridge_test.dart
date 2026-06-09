import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/ui/content/article_document_models.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/publish_draft_projection_bridge.dart';
import 'package:quwoquan_app/ui/content/entry/services/create_page_remote_helpers.dart';

void main() {
  group('publish_draft_projection_bridge', () {
    test(
      'createEditorStateToArticlePreviewWire carries Markdown + template keys',
      () {
        final state = CreateEditorState.initial();
        final wire = createEditorStateToArticlePreviewWire(
          state,
          previewPostId: 'p_preview',
        );
        expect(wire['postId'], 'p_preview');
        expect(wire['contentType'], 'article');
        expect(wire['articleMarkdown'], isA<String>());
        expect(wire['articleAssetManifest'], isA<Map>());
        expect(wire['articleRenderProfile'], isA<Map>());
        expect(wire.containsKey('articleDocument'), isFalse);
        expect(wire['articleTemplate'], isNotNull);
        expect(wire['articleFontPreset'], isNotNull);
      },
    );

    test(
      'postReadPreviewBundleFromCreateEditorState uses draftPreview surface',
      () {
        final state = CreateEditorState.initial().copyWith(title: 'NavTitle');
        final bundle = postReadPreviewBundleFromCreateEditorState(state);
        expect(bundle.surface, PostReadSurfaceId.draftPreview);
        expect(bundle.presentation.postId, 'draft_preview');
        expect(bundle.presentation.title, 'NavTitle');
      },
    );

    test(
      'postReadPreviewBundleFromPublishConfirmSummary work article branch',
      () {
        final bundle = postReadPreviewBundleFromPublishConfirmSummary(
          contentIdentity: CreateContentIdentity.work,
          title: 'T',
          body: 'B',
          hasVideo: false,
          imageCount: 0,
        );
        expect(bundle.surface, PostReadSurfaceId.draftPreview);
        expect(bundle.presentation.title, 'T');
        expect(bundle.presentation.body, 'B');
      },
    );

    test('createPublishConfirmPreviewWire video uses contentType video', () {
      final wire = createPublishConfirmPreviewWire(
        contentIdentity: CreateContentIdentity.moment,
        title: '',
        body: 'caption',
        hasVideo: true,
        imageCount: 0,
      );
      expect(wire['contentType'], 'video');
      expect(wire['contentIdentity'], 'moment');
    });

    test(
      'buildCreatePostPayloadMap article branch uses Markdown truth source',
      () {
        final state = CreateEditorState.initial().copyWith(
          title: 'T',
          body: 'x' * 200,
        );
        expect(shouldPublishAsArticleForPayload(state), isTrue);
        final payload = buildCreatePostPayloadMap(state);
        expect(payload['contentType'], 'article');
        expect(payload['articleMarkdown'], isA<String>());
        expect(payload['articleMarkdownVersion'], 'qwq-rich-md/1');
        expect(payload['articleAssetManifest'], isA<Map>());
        expect(payload['articleRenderProfile'], isA<Map>());
        expect(payload.containsKey('articleDocument'), isFalse);
      },
    );

    test('article asset manifest requests server-side variant generation', () {
      final document = ArticleDocumentData(
        nodes: const <ArticleDocumentNode>[
          ArticleDocumentNode(
            id: 'fig1',
            type: ArticleDocumentNodeType.figure,
            assetId: 'fig1',
            imageUrl: '/tmp/fig1.jpg',
          ),
        ],
      );
      final state = CreateEditorState.initial().copyWith(
        title: 'T',
        body: 'x' * 200,
        articleDocument: document,
        articleCoverImagePath: '/tmp/cover.jpg',
      );

      final manifest = buildArticleAssetManifestForPayload(state);
      final assets = manifest['assets'] as List<Object?>;
      final cover = assets.cast<Map<Object?, Object?>>().firstWhere(
        (asset) => asset['assetId'] == 'cover',
      );
      final variantGeneration =
          cover['variantGeneration'] as Map<Object?, Object?>;

      expect(variantGeneration['required'], isTrue);
      expect(variantGeneration['source'], 'server');
      expect(variantGeneration['profiles'], contains('display'));
      expect(variantGeneration['profiles'], contains('original'));
    });

    test('article markdown is serialized directly from document nodes', () {
      final document = ArticleDocumentData(
        nodes: const <ArticleDocumentNode>[
          ArticleDocumentNode(
            id: 'document_title',
            type: ArticleDocumentNodeType.documentTitle,
            text: '节点标题',
          ),
          ArticleDocumentNode(
            id: 'h2',
            type: ArticleDocumentNodeType.headingMajor,
            text: '节点章节',
          ),
          ArticleDocumentNode(
            id: 'fig1',
            type: ArticleDocumentNodeType.figure,
            assetId: 'fig1',
            imageUrl: '/tmp/fig1.jpg',
            imageLayout: 'wrapLeft',
            caption: '节点图注',
          ),
          ArticleDocumentNode(
            id: 'p1',
            type: ArticleDocumentNodeType.paragraph,
            text: '节点正文第一段。',
          ),
        ],
      );
      final state = CreateEditorState.initial().copyWith(
        title: '旧标题不应覆盖 nodes',
        body: '旧正文不应覆盖 nodes',
        articleDocument: document,
        articleBlocks: const <CreateTextBlock>[
          CreateTextBlock(
            id: 'block_1',
            type: CreateTextBlockType.paragraph,
            text: 'blocks 不应进入 Markdown',
          ),
        ],
      );

      final markdown = buildArticleMarkdownForPayload(state);

      expect(markdown, contains('# 节点标题'));
      expect(markdown, contains('## 节点章节'));
      expect(
        markdown,
        contains(':::figure id="fig1" layout="wrapLeft" caption="节点图注"'),
      );
      expect(markdown, contains('节点正文第一段。'));
      expect(markdown, isNot(contains('blocks 不应进入 Markdown')));
    });

    test('draft storage persists Markdown triple and can restore document', () {
      final document = ArticleDocumentData(
        nodes: const <ArticleDocumentNode>[
          ArticleDocumentNode(
            id: 'document_title',
            type: ArticleDocumentNodeType.documentTitle,
            text: '草稿标题',
          ),
          ArticleDocumentNode(
            id: 'p1',
            type: ArticleDocumentNodeType.paragraph,
            text: '草稿正文。',
          ),
        ],
      );
      final draft = CreateDraft(
        id: 'draft_1',
        updatedAtMs: 1,
        state: CreateEditorState.initial().copyWith(
          articleDocument: document,
          title: '草稿标题',
          body: '草稿正文。',
          articleCoverImagePath: '/tmp/cover.jpg',
        ),
      );

      final map = draft.toStorageMap();
      expect(map['articleMarkdown'], isA<String>());
      expect(map['articleMarkdownVersion'], 'qwq-rich-md/1');
      expect(map['articleAssetManifest'], isA<Map>());
      expect(map['articleRenderProfile'], isA<Map>());
      expect(map.containsKey('articleDocument'), isFalse);
      expect(map.containsKey('articlePages'), isFalse);
      expect(map.containsKey('articleBlocks'), isFalse);

      final restored = CreateDraft.fromStorageMap(map);
      expect(restored.state.articleDocument.title, '草稿标题');
      expect(restored.state.articleDocument.body, contains('草稿正文'));
      expect(restored.state.articleCoverImagePath, '/tmp/cover.jpg');
    });
  });
}
