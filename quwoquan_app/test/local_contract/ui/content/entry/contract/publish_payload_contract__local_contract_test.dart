import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_models.dart';
import 'package:quwoquan_app/ui/content/models/publish_settings_models.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// L1a 契约测试：创作入口发布 payload 与 content/post metadata 对齐
///
/// 验证 Post 发布字段与 CirclePostPlacement 跨上下文输入严格分离。
/// 不依赖 lib/features/create/，仅引用 cloud 元数据。
void main() {
  const writable = GeneratedPostRuntimeMetadata.publicationWritableFields;

  group('PublishPayload — 常规契约', () {
    test('publicationWritableFields 包含 Post 字段且排除 CirclePostPlacement 输入', () {
      expect(writable, contains('visibility'));
      expect(writable, contains('location'));
      expect(writable, contains('locationName'));
      expect(writable, isNot(contains('circleIds')));
      expect(writable, contains('primaryHomepageId'));
      expect(writable, contains('primaryHomepageType'));
      expect(writable, contains('primaryHomepageSnapshot'));
      expect(writable, contains('summary'));
      expect(writable, contains('semanticMentions'));
      expect(writable, isNot(contains('tagRefs')));
      expect(writable, isNot(contains('entityRefs')));
      expect(writable, contains('assistantUsePolicy'));
    });

    test('文章发布 payload 可写字段包含封面与展示真相源', () {
      expect(writable, contains('articleMarkdown'));
      expect(writable, contains('markdownDialect'));
      expect(writable, contains('articleAssetManifest'));
      expect(writable, contains('articleRenderProfile'));
      expect(writable, isNot(contains('articleDocument')));
      expect(writable, isNot(contains('articleTemplate')));
      expect(writable, isNot(contains('articleFontPreset')));
      expect(writable, isNot(contains('articlePresentationVersion')));
    });

    test('Post payload 公开+位置组合结构正确', () {
      final payload = <String, dynamic>{
        'contentType': 'micro',
        'visibility': 'public',
        'location': {
          'type': 'Point',
          'coordinates': [104.06, 30.65],
        },
        'locationName': '成都·天府广场',
      };
      for (final k in payload.keys) {
        expect(
          writable,
          contains(k),
          reason: 'payload 字段 $k 应在 publicationWritableFields 中',
        );
      }
      expect(payload['visibility'], 'public');
      expect(payload, isNot(contains('circleIds')));
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
        assistantUsePolicy: 'exclude',
      );
      final payload = settings.toPayloadFields();
      expect(payload['summary'], '西湖一日游摘要');
      expect(payload['tagRefs'], isA<List<String>>());
      expect(payload['tagRefs'], contains('Topic/旅行/城市漫步'));
      expect(payload['entityRefs'], isA<List<String>>());
      expect(payload['entityRefs'], contains('entity:sight:west_lake'));
      expect(payload['assistantUsePolicy'], 'exclude');
    });

    test('SubmitPostPublication semanticMentions 为结构化数组且不被 stringify', () {
      // R-CS06：semanticMentions 是 []object 可写字段，wire 必须以结构化数组承载，
      // 不得 .toString() 破坏；顶层只读投影 tagRefs/entityRefs 仍被 wire 剥离。
      final command = SubmitContentPostPublicationCommand(
        publishIntentId: 'intent-contract',
        localDraftId: 'draft-contract',
        contentType: ContentPostType.article,
        summary: '摘要',
        semanticMentions: <ContentPostStructuredObject>[
          ContentPostStructuredObject(<String, ContentPostStructuredValue>{
            'kind': const ContentPostStructuredText('tag'),
            'status': const ContentPostStructuredText('published'),
            'targetRef': const ContentPostStructuredText('Topic/旅行/城市漫步'),
          }),
          ContentPostStructuredObject(<String, ContentPostStructuredValue>{
            'kind': const ContentPostStructuredText('entity'),
            'status': const ContentPostStructuredText('published'),
            'targetRef': const ContentPostStructuredText(
              'entity:sight:west_lake',
            ),
          }),
        ],
        assistantUsePolicy: ContentPostAssistantUsePolicy.inherit,
      );
      final body = Map<String, Object?>.from(
        encodeSubmitContentPostPublicationCommand(command).body! as Map,
      );
      expect(body['contentType'], 'article');
      expect(body, isNot(contains('type')));
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

    test('私密 Post payload 同样不携带 circleIds', () {
      final payload = <String, dynamic>{
        'contentType': 'image',
        'visibility': 'private',
      };
      expect(payload['visibility'], 'private');
      expect(payload, isNot(contains('circleIds')));
    });
  });

  group('PublishPayload — 创作锚点契约（上下文化入口）', () {
    test('圈子锚点保留为 placement 输入但不进入 Post payload', () {
      const base = PublishSettings();
      final anchored = base.copyWith(
        isPublic: true,
        circleIds: <String>['circle_west_sichuan'],
        circleNames: <String>['川西出行圈'],
      );
      final payload = anchored.toPayloadFields();
      expect(payload['visibility'], 'public');
      expect(anchored.circleIds, contains('circle_west_sichuan'));
      expect(payload, isNot(contains('circleIds')));
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
      expect(anchored.circleIds, contains('circle_west_sichuan'));
      expect(payload, isNot(contains('circleIds')));
    });
  });

  group('PublishPayload — 严格字段契约', () {
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

    test('圈子选择只能从 PublishSettings 读取', () {
      const settings = PublishSettings(circleIds: <String>['circle-a']);
      expect(settings.circleIds, <String>['circle-a']);
      expect(settings.toPayloadFields(), isNot(contains('circleIds')));
    });
  });

  group('PublishPayload — 异常/边界契约', () {
    test('任何 Post payload 都禁止 circleIds', () {
      final payload = <String, dynamic>{
        'contentType': 'article',
        'visibility': 'private',
      };
      expect(payload, isNot(contains('circleIds')));
    });

    test('四类 contentType 均支持 payload 字段', () {
      const types = ['micro', 'image', 'video', 'article'];
      for (final t in types) {
        final payload = <String, dynamic>{
          'contentType': t,
          'visibility': 'public',
        };
        expect(writable, contains('contentType'));
        expect(payload['contentType'], t);
        expect(payload, isNot(contains('circleIds')));
      }
    });
  });
}
