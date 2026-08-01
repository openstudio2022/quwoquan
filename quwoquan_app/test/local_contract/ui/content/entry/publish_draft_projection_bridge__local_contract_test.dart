import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/ui/content/models/article_document_models.dart';
import 'package:quwoquan_app/ui/content/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/models/publish_settings_models.dart';
import 'package:quwoquan_app/ui/content/entry/publish_draft_projection_bridge.dart';
import 'package:quwoquan_app/ui/content/entry/services/create_page_remote_helpers.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

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
        videoThumbnailUrl: '/tmp/cover.jpg',
      );
      expect(wire['contentType'], 'video');
      expect(wire['contentIdentity'], 'moment');
      expect(wire['thumbnailUrl'], '/tmp/cover.jpg');
      expect(wire['coverUrl'], '/tmp/cover.jpg');
    });

    test(
      'buildPostPublicationPayloadMap video writes cover contract fields',
      () {
        final state =
            CreateEditorState.initial(
              editorKind: CreateEditorKind.media,
            ).copyWith(
              mediaKind: CreateMediaKind.video,
              videoPath: '/tmp/video.mp4',
              videoThumbnail: '/tmp/cover.jpg',
              videoDurationMs: 12000,
              videoCoverTimeMs: 420,
              videoMuted: true,
              title: '视频作品',
              body: '视频简介',
            );

        final payload = buildPostPublicationPayloadMap(state);
        expect(payload['contentType'], 'video');
        expect(payload['videoUrl'], '/tmp/video.mp4');
        expect(payload['thumbnailUrl'], '/tmp/cover.jpg');
        expect(payload['coverUrl'], '/tmp/cover.jpg');
        expect(payload['coverStrategy'], 'manual');
        expect(payload['coverFrameTimeMs'], 420);
        expect(payload['durationMs'], 12000);
        expect(payload, isNot(contains('mediaItems')));
        expect(payload, isNot(contains('deviceInfo')));

        final command = submitContentPostPublicationCommandFromPreparedPayload(
          payload,
          localDraftId: 'draft-video-contract',
          mediaAssetIds: const <String>['video-asset-contract'],
        );
        final wire = Map<String, Object?>.from(
          encodeContentPostSubmitPostPublicationGeneratedRequest(command).body!
              as Map,
        );
        expect(wire, isNot(contains('thumbnailUrl')));
        expect(wire, isNot(contains('coverUrl')));
        expect(wire['coverStrategy'], 'manual');
        expect(wire['coverFrameTimeMs'], 420);
        expect(wire['mediaAssetIds'], const <String>['video-asset-contract']);
        expect(wire, isNot(contains('mediaItems')));
      },
    );

    test(
      'buildPostPublicationPayloadMap article branch uses Markdown truth source',
      () {
        final state = CreateEditorState.initial().copyWith(
          title: 'T',
          body: 'x' * 200,
        );
        expect(shouldPublishAsArticleForPayload(state), isTrue);
        final payload = buildPostPublicationPayloadMap(state);
        expect(payload['contentType'], 'article');
        expect(payload['articleMarkdown'], isA<String>());
        expect(payload['markdownDialect'], 'qwq-rich-md');
        expect(
          payload['articleAssetManifest'],
          isA<PostArticleAssetManifestInput>(),
        );
        expect(
          payload['articleRenderProfile'],
          isA<PostArticleRenderProfile>(),
        );
        expect(payload.containsKey('articleDocument'), isFalse);
      },
    );

    test(
      'buildPostPublicationPayloadMap writes confirmed summary refs and assistant policy',
      () {
        final state = CreateEditorState.initial().copyWith(
          title: 'T',
          body: 'x' * 200,
          settings: const PublishSettings(
            summary: '用户确认摘要',
            tagRefs: <String>['Topic/旅行/城市漫步'],
            entityRefs: <String>['entity:sight:west_lake'],
            assistantUsePolicy: 'allow_summary',
          ),
        );

        final payload = buildPostPublicationPayloadMap(state);

        expect(payload['summary'], '用户确认摘要');
        expect(payload['tagRefs'], <String>['Topic/旅行/城市漫步']);
        expect(payload['entityRefs'], <String>['entity:sight:west_lake']);
        expect(payload['assistantUsePolicy'], 'allow_summary');
        expect(payload['articleMarkdown'], contains('summary: "用户确认摘要"'));
        expect(payload['articleMarkdown'], contains('tag_refs:'));
        expect(payload['articleMarkdown'], contains('entity_refs:'));
      },
    );

    test(
      'buildPostPublicationPayloadMap derives entityRefs from inline mentions',
      () {
        final document = ArticleDocumentData(
          nodes: <ArticleDocumentNode>[
            ArticleDocumentNode(
              id: 'p1',
              type: ArticleDocumentNodeType.paragraph,
              text: '灵隐寺值得一去',
              spans: <ArticleInlineSpan>[
                ArticleInlineSpan(
                  start: 0,
                  end: 3,
                  kind: 'entity',
                  targetType: 'entity',
                  targetId: 'entity:sight:lingyin',
                  displayText: '灵隐寺',
                ),
              ],
            ),
          ],
        );
        final state = CreateEditorState.initial().copyWith(
          title: 'T',
          body: 'x' * 200,
          articleDocument: document,
        );

        final payload = buildPostPublicationPayloadMap(state);

        expect(payload['entityRefs'], contains('entity:sight:lingyin'));
        expect(
          payload['articleMarkdown'],
          contains('@[灵隐寺](entity:sight:lingyin)'),
        );
      },
    );

    test(
      'buildPostPublicationPayloadMap derives tagRefs from inline mentions and keeps entity',
      () {
        final document = ArticleDocumentData(
          nodes: <ArticleDocumentNode>[
            ArticleDocumentNode(
              id: 'p1',
              type: ArticleDocumentNodeType.paragraph,
              text: '城市漫步路线途经灵隐寺',
              spans: <ArticleInlineSpan>[
                ArticleInlineSpan(
                  start: 0,
                  end: 4,
                  kind: 'tag',
                  targetType: 'tag',
                  targetId: 'tag:topic:city_walk',
                  displayText: '城市漫步',
                ),
                ArticleInlineSpan(
                  start: 8,
                  end: 11,
                  kind: 'entity',
                  targetType: 'entity',
                  targetId: 'entity:sight:lingyin',
                  displayText: '灵隐寺',
                ),
              ],
            ),
          ],
        );
        final state = CreateEditorState.initial().copyWith(
          title: 'T',
          body: 'x' * 200,
          articleDocument: document,
          settings: const PublishSettings(
            tagRefs: <String>['Topic/旅行/城市漫步', 'topic:city_walk'],
            entityRefs: <String>['entity:sight:west_lake'],
          ),
        );

        final payload = buildPostPublicationPayloadMap(state);

        final tagRefs = (payload['tagRefs'] as List).cast<String>();
        // 正文 tag span 剥离 tag: 前缀后注入，并与 settings 已有 ref 去重。
        expect(tagRefs, contains('topic:city_walk'));
        expect(tagRefs, contains('Topic/旅行/城市漫步'));
        expect(tagRefs, isNot(contains('tag:topic:city_walk')));
        expect(
          tagRefs.where((ref) => ref == 'topic:city_walk').length,
          1,
          reason: 'tagRefs 必须去重，正文与 settings 同值只投影一次',
        );

        // entity 投影不回归：settings + 正文 entity span 同时保留（仍带 entity: 前缀）。
        final entityRefs = (payload['entityRefs'] as List).cast<String>();
        expect(entityRefs, contains('entity:sight:west_lake'));
        expect(entityRefs, contains('entity:sight:lingyin'));

        final markdown = payload['articleMarkdown'] as String;
        expect(markdown, contains('@[城市漫步](tag:topic:city_walk)'));
        expect(markdown, contains('@[灵隐寺](entity:sight:lingyin)'));
        expect(markdown, contains('tag_refs:'));
        expect(markdown, contains('entity_refs:'));
      },
    );

    test('article asset manifest carries identity and presentation only', () {
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
      final cover = manifest.assets.firstWhere(
        (asset) => asset.assetId == 'cover',
      );
      expect(cover.role, 'cover');
      expect(
        cover.toJson().keys,
        unorderedEquals(<Object?>['assetId', 'role']),
      );
      expect('${manifest.toJson()['assets']}', isNot(contains('/tmp/')));
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
      );

      final markdown = buildArticleMarkdownForPayload(state);

      expect(markdown, contains('# 节点标题'));
      expect(markdown, contains('## 节点章节'));
      expect(
        markdown,
        contains(':::figure id="fig1" layout="wrapLeft" caption="节点图注"'),
      );
      expect(markdown, contains('节点正文第一段。'));
      expect(markdown, isNot(contains('旧标题不应覆盖 nodes')));
      expect(markdown, isNot(contains('旧正文不应覆盖 nodes')));
    });

    test(
      'semanticMentionsForPayload projects inline entity + tag to published rows',
      () {
        final document = ArticleDocumentData(
          nodes: <ArticleDocumentNode>[
            ArticleDocumentNode(
              id: 'p1',
              type: ArticleDocumentNodeType.paragraph,
              text: '城市漫步路线途经灵隐寺',
              spans: <ArticleInlineSpan>[
                ArticleInlineSpan(
                  start: 0,
                  end: 4,
                  kind: 'tag',
                  targetType: 'tag',
                  targetId: 'tag:Topic/旅行/城市漫步',
                  displayText: '城市漫步',
                ),
                ArticleInlineSpan(
                  start: 8,
                  end: 11,
                  kind: 'entity',
                  targetType: 'entity',
                  targetId: 'entity:sight:lingyin',
                  displayText: '灵隐寺',
                ),
              ],
            ),
          ],
        );
        final state = CreateEditorState.initial().copyWith(
          title: 'T',
          body: 'x' * 200,
          articleDocument: document,
        );

        final mentions = semanticMentionsForPayload(state);
        final tagRefs = mentions
            .where((mention) => mention.kind == 'tag')
            .map((mention) => mention.targetRef)
            .toList();
        final entityRefs = mentions
            .where((mention) => mention.kind == 'entity')
            .map((mention) => mention.targetRef)
            .toList();

        expect(tagRefs, contains('Topic/旅行/城市漫步'));
        expect(entityRefs, contains('entity:sight:lingyin'));
        for (final mention in mentions) {
          expect(mention.status, 'published');
          expect(mention.mentionId, isNotEmpty);
          expect(mention.surface, isNotEmpty);
          expect(mention.location, isNotEmpty);
        }
      },
    );

    test(
      'semanticMentionsForPayload dedups and filters invalid / candidate refs',
      () {
        final state = CreateEditorState.initial().copyWith(
          title: 'T',
          body: 'x' * 200,
          settings: const PublishSettings(
            tagRefs: <String>['Topic/旅行/城市漫步', 'Topic/旅行/城市漫步', '单段非法标签'],
            entityRefs: <String>[
              'entity:sight:west_lake',
              'entity:candidate_pending',
              'entity:bad',
            ],
          ),
        );

        final mentions = semanticMentionsForPayload(state);
        final tagRefs = mentions
            .where((mention) => mention.kind == 'tag')
            .map((mention) => mention.targetRef ?? '')
            .toList();
        final entityRefs = mentions
            .where((mention) => mention.kind == 'entity')
            .map((mention) => mention.targetRef ?? '')
            .toList();

        expect(
          tagRefs.where((r) => r == 'Topic/旅行/城市漫步').length,
          1,
          reason: 'semanticMentions 必须按 (kind,targetRef) 去重',
        );
        expect(
          tagRefs,
          isNot(contains('单段非法标签')),
          reason: '单段 bare tag（无 / 分段）非法，需过滤',
        );
        expect(entityRefs, contains('entity:sight:west_lake'));
        expect(
          entityRefs,
          isNot(contains('entity:candidate_pending')),
          reason: 'candidate ref 不得作为 published mention',
        );
        expect(
          entityRefs,
          isNot(contains('entity:bad')),
          reason: 'entity: 少于 3 段非法，需过滤',
        );
      },
    );

    test(
      'buildPostPublicationPayloadMap injects semanticMentions and wire keeps structured array',
      () {
        final document = ArticleDocumentData(
          nodes: <ArticleDocumentNode>[
            ArticleDocumentNode(
              id: 'p1',
              type: ArticleDocumentNodeType.paragraph,
              text: '灵隐寺',
              spans: <ArticleInlineSpan>[
                ArticleInlineSpan(
                  start: 0,
                  end: 3,
                  kind: 'entity',
                  targetType: 'entity',
                  targetId: 'entity:sight:lingyin',
                  displayText: '灵隐寺',
                ),
              ],
            ),
          ],
        );
        final state = CreateEditorState.initial().copyWith(
          title: 'T',
          body: 'x' * 200,
          articleDocument: document,
          settings: const PublishSettings(tagRefs: <String>['Topic/旅行/城市漫步']),
        );

        final payload = buildPostPublicationPayloadMap(state);
        expect(payload['semanticMentions'], isA<List>());

        final command = submitContentPostPublicationCommandFromPreparedPayload(
          payload,
          localDraftId: 'draft-semantic-contract',
          mediaAssetIds: const <String>[],
        );
        final body = Map<String, Object?>.from(
          encodeContentPostSubmitPostPublicationGeneratedRequest(command).body!
              as Map,
        );
        expect(
          body['semanticMentions'],
          isA<List>(),
          reason: 'wire 不得把 semanticMentions 数组 stringify',
        );
        final rows = (body['semanticMentions'] as List)
            .cast<Map<String, dynamic>>();
        expect(
          rows.any(
            (r) =>
                r['kind'] == 'entity' &&
                r['targetRef'] == 'entity:sight:lingyin',
          ),
          isTrue,
        );
        expect(
          rows.any(
            (r) => r['kind'] == 'tag' && r['targetRef'] == 'Topic/旅行/城市漫步',
          ),
          isTrue,
        );
        // canonical 发布请求实体不拥有顶层只读投影字段。
        expect(body.containsKey('tagRefs'), isFalse);
        expect(body.containsKey('entityRefs'), isFalse);
      },
    );

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
          settings: const PublishSettings(
            summary: '草稿摘要',
            tagRefs: <String>['Topic/旅行/城市漫步'],
            entityRefs: <String>['entity:sight:west_lake'],
            assistantUsePolicy: 'allow_summary',
          ),
        ),
      );

      final map = draft.toStorageMap();
      expect(map['articleMarkdown'], isA<String>());
      expect(map['markdownDialect'], 'qwq-rich-md');
      expect(map['articleAssetManifest'], isA<Map>());
      expect(map['articleRenderProfile'], isA<Map>());
      expect(map.containsKey('articleDocument'), isFalse);
      expect(map.containsKey('articlePages'), isFalse);
      expect(map.containsKey('articleBlocks'), isFalse);

      final restored = CreateDraft.fromStorageMap(map);
      expect(restored.state.articleDocument.title, '草稿标题');
      expect(restored.state.articleDocument.body, contains('草稿正文'));
      expect(restored.state.articleCoverImagePath, '/tmp/cover.jpg');
      expect(restored.state.settings.summary, '草稿摘要');
      expect(restored.state.settings.tagRefs, <String>['Topic/旅行/城市漫步']);
      expect(restored.state.settings.entityRefs, <String>[
        'entity:sight:west_lake',
      ]);
      expect(restored.state.settings.assistantUsePolicy, 'allow_summary');
    });
  });
}
