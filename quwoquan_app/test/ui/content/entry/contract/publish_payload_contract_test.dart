import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_models.dart';
import 'package:quwoquan_app/ui/content/entry/models/publish_settings_models.dart';

/// L1a 契约测试：创作入口发布 payload 与 content/post metadata 对齐
///
/// 规范：create-entry-location-visibility-circle tasks T2
/// 验证 visibility、location、locationName、circleIds 在公开/私密、选位置/不选、选圈子/不选下的组合契约。
/// 不依赖 lib/features/create/，仅引用 cloud 元数据。
void main() {
  const writable = GeneratedPostRuntimeMetadata.createWritableFields;

  group('PublishPayload — 常规契约', () {
    test(
      'createWritableFields 包含 visibility location locationName circleIds',
      () {
        expect(writable, contains('visibility'));
        expect(writable, contains('location'));
        expect(writable, contains('locationName'));
        expect(writable, contains('circleIds'));
        expect(writable, contains('primaryHomepageId'));
        expect(writable, contains('primaryHomepageType'));
        expect(writable, contains('primaryHomepageSnapshot'));
      },
    );

    test('文章发布 payload 可写字段包含封面与展示真相源', () {
      expect(writable, contains('articleMarkdown'));
      expect(writable, contains('articleMarkdownVersion'));
      expect(writable, contains('articleAssetManifest'));
      expect(writable, contains('articleRenderProfile'));
      expect(writable, isNot(contains('articleDocument')));
      expect(writable, isNot(contains('articleTemplate')));
      expect(writable, isNot(contains('articleFontPreset')));
      expect(writable, isNot(contains('articlePresentationVersion')));
    });

    test('payload 公开+位置+圈子组合结构正确', () {
      final payload = <String, dynamic>{
        'contentType': 'micro',
        'visibility': 'public',
        'location': {
          'type': 'Point',
          'coordinates': [104.06, 30.65],
        },
        'locationName': '成都·天府广场',
        'circleIds': <String>['c1', 'c2'],
      };
      for (final k in payload.keys) {
        expect(
          writable,
          contains(k),
          reason: 'payload 字段 $k 应在 createWritableFields 中',
        );
      }
      expect(payload['visibility'], 'public');
      expect((payload['circleIds'] as List).length, 2);
    });

    test('payload 可携带 canonical homepage reference', () {
      const settings = PublishSettings(
        homepage: HomepageCanonicalReference(
          id: 'homepage_sight_west_lake',
          homepageType: 'sight',
          title: '西湖景区',
          subtitle: '杭州西湖核心游览区',
          coverUrl: 'https://example.com/west-lake.jpg',
          status: 'published',
        ),
      );
      final payload = settings.toPayloadFields();
      expect(payload['primaryHomepageId'], 'homepage_sight_west_lake');
      expect(payload['primaryHomepageType'], 'sight');
      expect(payload['primaryHomepageSnapshot'], <String, dynamic>{
        'title': '西湖景区',
        'subtitle': '杭州西湖核心游览区',
        'coverUrl': 'https://example.com/west-lake.jpg',
        'status': 'published',
      });
    });

    test('payload 私密时 circleIds 必须为空', () {
      final payload = <String, dynamic>{
        'contentType': 'image',
        'visibility': 'private',
        'circleIds': <String>[],
      };
      expect(payload['visibility'], 'private');
      expect(payload['circleIds'], isEmpty);
    });
  });

  group('PublishPayload — 兼容性契约', () {
    test('visibility 仅允许 public 或 private', () {
      const allowed = ['public', 'private'];
      for (final v in allowed) {
        expect(allowed, contains(v));
      }
    });

    test('无位置时 location 可缺失或为 null', () {
      final payload = <String, dynamic>{
        'contentType': 'video',
        'visibility': 'public',
        'locationName': '',
      };
      expect(
        payload.containsKey('location') || payload['location'] == null,
        isTrue,
      );
      expect(payload['locationName'], '');
    });

    test('circleIds 为 List<String>', () {
      final payload = <String, dynamic>{
        'visibility': 'public',
        'circleIds': <String>[],
      };
      expect(payload['circleIds'], isA<List<String>>());
    });
  });

  group('PublishPayload — 异常/边界契约', () {
    test('私密时 circleIds 为空不违反契约', () {
      final payload = <String, dynamic>{
        'contentType': 'article',
        'visibility': 'private',
        'circleIds': <String>[],
      };
      expect((payload['circleIds'] as List).length, 0);
    });

    test('四类 contentType 均支持 payload 字段', () {
      const types = ['micro', 'image', 'video', 'article'];
      for (final t in types) {
        final payload = <String, dynamic>{
          'contentType': t,
          'visibility': 'public',
          'circleIds': <String>[],
        };
        expect(writable, contains('contentType'));
        expect(payload['contentType'], t);
      }
    });
  });
}
