import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/content/content/post/domain/article_document_models.dart';
import 'package:quwoquan_app/content/content/post/domain/create_editor_models.dart';
import 'package:quwoquan_app/content/content/post/domain/publish_settings_models.dart';

void main() {
  group('CreateDraft', () {
    test('文字草稿缺少 canonical articleMarkdown 时不回退旧 body/imagePaths', () {
      final draft = CreateDraft.fromStorageMap({
        'id': 'draft_1',
        'updatedAt': 123,
        'type': 'text',
        'editorKind': 'text',
        'mediaKind': 'images',
        'imagePaths': ['a.png'],
        'title': '东京三日清单',
        'body': '第一天先去浅草寺',
        'titlePresentation': 'expanded',
        'settings': const <String, dynamic>{},
      });

      expect(draft.identity, CreateContentIdentity.moment);
      expect(draft.previewText, isEmpty);
      expect(draft.toStorageMap()['type'], 'text');
      expect(draft.state.imagePaths, isEmpty);
      expect(draft.state.articleDocument.body, isEmpty);
    });

    test('从 articleMarkdown 恢复正文与图片索引', () {
      final draft = CreateDraft.fromStorageMap({
        'id': 'draft_markdown',
        'updatedAt': 456,
        'type': 'text',
        'editorKind': 'text',
        'mediaKind': 'none',
        'title': '块编辑器',
        'body': '',
        'articleMarkdown':
            '---\n'
            'title: 块编辑器\n'
            '---\n\n'
            '# 块编辑器\n\n'
            '第一段\n\n'
            '1. 第二条\n\n'
            ':::figure id="i1" layout="fullWidth"\n'
            'inline.png\n'
            ':::\n',
        'articleAssetManifest': <String, dynamic>{
          'assets': <Map<String, dynamic>>[
            {'assetId': 'i1', 'localPath': 'inline.png', 'role': 'figure'},
          ],
        },
        'activeArticleBlockId': 'o1',
        'settings': const <String, dynamic>{},
      });

      expect(draft.state.body, contains('第一段'));
      expect(draft.state.imagePaths, <String>['asset://inline.png']);

      final storage = draft.toStorageMap();
      expect(storage['articleMarkdown'], contains('第一段'));
      expect(storage.containsKey('articleDocument'), isFalse);
      expect(storage.containsKey('articleBlocks'), isFalse);
      final restored = CreateDraft.fromStorageMap(storage);
      expect(restored.state.body, contains('第一段'));
    });

    test('图片 node 布局由 canonical document 直接承载', () {
      final document = ArticleDocumentData(
        nodes: const <ArticleDocumentNode>[
          ArticleDocumentNode(
            id: 'img_1',
            type: ArticleDocumentNodeType.figure,
            imageUrl: 'inline.png',
            imageLayout: 'wrapRight',
          ),
        ],
      );

      final imageNode = document.nodes.single;
      expect(imageNode.imageLayout, 'wrapRight');
      expect(imageNode.type, ArticleDocumentNodeType.figure);
    });

    test('扁平存储下图片类草稿解析为作品身份', () {
      final draft = CreateDraft.fromStorageMap({
        'id': 'photo_draft',
        'type': 'media',
        'updatedAt': 456,
        'editorKind': 'media',
        'mediaKind': 'images',
        'imagePaths': <String>['a.jpg'],
        'title': '',
        'body': '图片说明',
        'settings': const <String, dynamic>{},
      });

      expect(draft.identity, CreateContentIdentity.work);
      expect(draft.previewText, '图片说明');
      expect(draft.state.editorKind, CreateEditorKind.media);
    });
  });

  group('PublishSettings', () {
    test('toPayloadFields 输出发布设置基础字段', () {
      final payload = PublishSettings(
        isPublic: false,
        locationName: '成都',
        locationPoi: const CreateLocationOption(
          id: 't_poi',
          name: '',
          latitude: 30.6,
          longitude: 104.0,
        ),
      ).toPayloadFields();

      expect(payload['visibility'], 'private');
      expect(payload['locationName'], '成都');
      expect(payload['location'], isNotEmpty);
    });

    test('fromMap 在私密态下清空圈子', () {
      final settings = PublishSettings.fromMap({
        'visibility': 'private',
        'circleIds': ['circle_1'],
        'circleNames': ['摄影圈'],
      });

      expect(settings.isPublic, isFalse);
      expect(settings.circleIds, isEmpty);
      expect(settings.locationName, isEmpty);
    });

    test('toMap/fromMap 保留 WP6 富语义发布字段', () {
      const settings = PublishSettings(
        summary: '用户确认摘要',
        tagRefs: <String>['Topic/旅行/城市漫步'],
        tagLabels: <String>['城市漫步'],
        entityRefs: <String>['entity:sight:west_lake'],
        entityNames: <String>['西湖景区'],
        assistantUsePolicy: 'allow_summary',
      );

      final restored = PublishSettings.fromMap(settings.toMap());

      expect(restored.summary, '用户确认摘要');
      expect(restored.tagRefs, <String>['Topic/旅行/城市漫步']);
      expect(restored.tagLabels, <String>['城市漫步']);
      expect(restored.entityRefs, <String>['entity:sight:west_lake']);
      expect(restored.entityNames, <String>['西湖景区']);
      expect(restored.assistantUsePolicy, 'allow_summary');
    });
  });
}
