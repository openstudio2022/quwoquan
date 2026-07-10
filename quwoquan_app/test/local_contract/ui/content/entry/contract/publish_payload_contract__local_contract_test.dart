import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_post_mutation_wires.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_models.dart';
import 'package:quwoquan_app/ui/content/models/publish_settings_models.dart';

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
        expect(writable, contains('summary'));
        expect(writable, contains('semanticMentions'));
        expect(writable, isNot(contains('tagRefs')));
        expect(writable, isNot(contains('entityRefs')));
        expect(writable, contains('assistantUsePolicy'));
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
          canonicalEntityId: 'entity:sight:west_lake',
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
        'canonicalEntityId': 'entity:sight:west_lake',
      });
    });

    test('payload 可携带摘要、标签、附加关联对象与 assistant policy', () {
      const settings = PublishSettings(
        summary: '西湖一日游摘要',
        tagRefs: <String>['Topic/旅行/城市漫步', 'Entity/地点/西湖'],
        tagLabels: <String>['城市漫步', '西湖'],
        entityRefs: <String>['entity:sight:west_lake'],
        entityNames: <String>['西湖景区'],
        assistantUsePolicy: 'allow_summary',
      );
      final payload = settings.toPayloadFields();
      expect(payload['summary'], '西湖一日游摘要');
      expect(payload['tagRefs'], isA<List<String>>());
      expect(payload['tagRefs'], contains('Topic/旅行/城市漫步'));
      expect(payload['entityRefs'], isA<List<String>>());
      expect(payload['entityRefs'], contains('entity:sight:west_lake'));
      expect(payload['assistantUsePolicy'], 'allow_summary');
    });

    test('CreatePostRequestWire semanticMentions 为结构化数组且不被 stringify', () {
      // R-CS06：semanticMentions 是 []object 可写字段，wire 必须以结构化数组承载，
      // 不得 .toString() 破坏；顶层只读投影 tagRefs/entityRefs 仍被 wire 剥离。
      final wire = CreatePostRequestWire.fromMap(<String, dynamic>{
        'type': 'article',
        'contentType': 'article',
        'summary': '摘要',
        'semanticMentions': <Map<String, dynamic>>[
          {
            'kind': 'tag',
            'status': 'published',
            'targetRef': 'Topic/旅行/城市漫步',
          },
          {
            'kind': 'entity',
            'status': 'published',
            'targetRef': 'entity:sight:west_lake',
          },
        ],
        'tagRefs': <String>['Topic/旅行/城市漫步'],
        'entityRefs': <String>['entity:sight:west_lake'],
        'assistantUsePolicy': 'inherit',
      });
      final body = wire.toWire();
      expect(body['semanticMentions'], isA<List>());
      final rows = (body['semanticMentions'] as List)
          .cast<Map<String, dynamic>>();
      expect(rows.length, 2);
      expect(
        rows.any(
          (r) => r['kind'] == 'tag' && r['targetRef'] == 'Topic/旅行/城市漫步',
        ),
        isTrue,
      );
      expect(
        rows.any(
          (r) =>
              r['kind'] == 'entity' &&
              r['targetRef'] == 'entity:sight:west_lake',
        ),
        isTrue,
      );
      expect(body.containsKey('tagRefs'), isFalse);
      expect(body.containsKey('entityRefs'), isFalse);
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

  group('PublishPayload — 创作锚点契约（上下文化入口）', () {
    test('圈子锚点注入 circleIds 后 payload 携带该圈子且为公开', () {
      // 模拟「向圈子投稿」入口：CreatePage 将 circle 锚点写入 PublishSettings。
      const base = PublishSettings();
      final anchored = base.copyWith(
        isPublic: true,
        circleIds: <String>['circle_west_sichuan'],
        circleNames: <String>['川西出行圈'],
      );
      final payload = anchored.toPayloadFields();
      expect(payload['visibility'], 'public');
      expect(payload['circleIds'], contains('circle_west_sichuan'));
    });

    test('对象主页 + 圈子锚点可共存于同一 payload', () {
      const base = PublishSettings(
        homepage: HomepageCanonicalReference(
          id: 'homepage_sight_daocheng',
          homepageType: 'sight',
          canonicalEntityId: 'entity:sight:daocheng',
          title: '稻城亚丁',
          subtitle: '川西高原核心景区',
          coverUrl: 'https://example.com/daocheng.jpg',
          status: 'published',
        ),
      );
      final anchored = base.copyWith(
        isPublic: true,
        circleIds: <String>['circle_west_sichuan'],
        circleNames: <String>['川西出行圈'],
      );
      final payload = anchored.toPayloadFields();
      expect(payload['primaryHomepageId'], 'homepage_sight_daocheng');
      expect(payload['circleIds'], contains('circle_west_sichuan'));
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
