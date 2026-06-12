import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/integration/location_poi_dto.g.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/models/publish_settings_models.dart';

void main() {
  group('CreateDraft', () {
    test('从存储 map 恢复文字草稿与预览文案', () {
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
      expect(draft.previewText, '东京三日清单');
      expect(draft.toStorageMap()['type'], 'text');
      expect(draft.state.imagePaths, hasLength(1));
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
            {
              'assetId': 'i1',
              'localPath': 'inline.png',
              'role': 'figure',
            },
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

    test('图片块布局样式可序列化恢复', () {
      final block = CreateTextBlock.image(
        id: 'img_1',
        imagePath: 'inline.png',
        imageLayout: CreateTextImageLayout.wrapRight,
      );

      final restored = CreateTextBlock.fromMap(block.toMap());
      expect(restored.imageLayout, CreateTextImageLayout.wrapRight);
      expect(restored.usesWrappedLayout, isTrue);
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
        locationPoi: LocationPoiDto(
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
  });
}
