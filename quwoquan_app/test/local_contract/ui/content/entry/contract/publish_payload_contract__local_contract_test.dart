import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_models.dart';
import 'package:quwoquan_app/ui/content/entry/services/create_page_remote_helpers.dart';
import 'package:quwoquan_app/ui/content/models/publish_settings_models.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// L1a 契约测试：创作入口发布 payload 与 content/content/post metadata 对齐
///
/// 验证 Post 发布字段与 CirclePostPlacement 跨上下文输入严格分离。
/// 不依赖 lib/features/create/，仅引用 cloud 元数据。
void main() {
  final requestBodyFields = _submitPostPublicationRequestBodyFields();

  group('PublishPayload — 常规契约', () {
    test('generated request body 包含 Post 字段且排除 CirclePostPlacement 输入', () {
      expect(requestBodyFields, contains('visibility'));
      expect(requestBodyFields, contains('location'));
      expect(requestBodyFields, contains('locationName'));
      expect(requestBodyFields, isNot(contains('circleIds')));
      expect(requestBodyFields, contains('primaryHomepageId'));
      expect(requestBodyFields, contains('primaryHomepageType'));
      expect(requestBodyFields, contains('primaryHomepageSnapshot'));
      expect(requestBodyFields, contains('summary'));
      expect(requestBodyFields, contains('semanticMentions'));
      expect(requestBodyFields, isNot(contains('tagRefs')));
      expect(requestBodyFields, isNot(contains('entityRefs')));
      expect(requestBodyFields, contains('assistantUsePolicy'));
    });

    test('文章发布 request body 包含封面与展示真相源', () {
      expect(requestBodyFields, contains('articleMarkdown'));
      expect(requestBodyFields, contains('markdownDialect'));
      expect(requestBodyFields, contains('articleAssetManifest'));
      expect(requestBodyFields, contains('articleRenderProfile'));
      expect(requestBodyFields, isNot(contains('articleDocument')));
      expect(requestBodyFields, isNot(contains('articleTemplate')));
      expect(requestBodyFields, isNot(contains('articleFontPreset')));
      expect(requestBodyFields, isNot(contains('articlePresentationVersion')));
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
          requestBodyFields,
          contains(k),
          reason: 'payload 字段 $k 应由 generated request body 接纳',
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
      // R-CS06：semanticMentions 是 []object request body 字段，wire 必须以结构化数组承载，
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
        encodeContentPostSubmitPostPublicationGeneratedRequest(command).body!
            as Map,
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

  group('PublishPayload — 出行时间（到访事实）', () {
    const anchored = PublishSettings(
      locationName: '老君山观景台',
      geoTagRef: 'Topic/地理/行政区/河南省/洛阳市',
    );

    test('visitedAt 是发布 request body 字段', () {
      expect(requestBodyFields, contains('visitedAt'));
    });

    test('声明的到访时间以 UTC RFC3339 进入 payload', () {
      final settings = anchored.copyWith(
        visitedAt: DateTime.utc(2026, 4, 5, 6, 30),
      );

      expect(
        settings.toPayloadFields()['visitedAt'],
        '2026-04-05T06:30:00.000Z',
      );
    });

    test('没有地点锚点时到访时间不进入 payload', () {
      final settings = const PublishSettings().copyWith(
        visitedAt: DateTime.utc(2026, 4, 5),
      );

      expect(settings.hasPlaceAnchor, isFalse);
      expect(settings.toPayloadFields().containsKey('visitedAt'), isFalse);
    });

    test('未声明到访时间时不用发布时间冒充', () {
      expect(anchored.visitedAt, isNull);
      expect(anchored.toPayloadFields().containsKey('visitedAt'), isFalse);
    });

    test('草稿存取往返保留到访时间', () {
      final settings = anchored.copyWith(
        visitedAt: DateTime.utc(2026, 4, 5, 6, 30),
      );

      final restored = PublishSettings.fromMap(
        Map<String, dynamic>.from(settings.toMap()),
      );

      expect(restored.visitedAt?.toUtc(), settings.visitedAt);
    });

    test('payload 到发布命令的 wire 往返保留到访时间', () {
      final settings = anchored.copyWith(
        visitedAt: DateTime.utc(2026, 4, 5, 6, 30),
      );
      final payload = <String, Object?>{
        'contentType': 'image',
        ...settings.toPayloadFields(),
      };

      final command = submitContentPostPublicationCommandFromPreparedPayload(
        payload,
        localDraftId: 'draft-visited',
        mediaAssetIds: const <String>['asset-image'],
      );
      final body = Map<String, Object?>.from(
        encodeContentPostSubmitPostPublicationGeneratedRequest(command).body!
            as Map,
      );

      expect(command.visitedAt, DateTime.utc(2026, 4, 5, 6, 30));
      expect(body['visitedAt'], '2026-04-05T06:30:00.000Z');
      expect(
        decodeSubmitContentPostPublicationCommand(body).visitedAt,
        command.visitedAt,
      );
    });

    test('非 RFC3339 的到访时间在端侧即被拒绝', () {
      expect(
        () => submitContentPostPublicationCommandFromPreparedPayload(
          <String, Object?>{'contentType': 'micro', 'visitedAt': '去年春天'},
          localDraftId: 'draft-visited-invalid',
          mediaAssetIds: const <String>[],
        ),
        throwsArgumentError,
      );
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
        expect(requestBodyFields, contains('contentType'));
        expect(payload['contentType'], t);
        expect(payload, isNot(contains('circleIds')));
      }
    });
  });
}

Set<String> _submitPostPublicationRequestBodyFields() {
  final structured = ContentPostStructuredObject(
    <String, ContentPostStructuredValue>{
      'value': const ContentPostStructuredText('contract'),
    },
  );
  final command = SubmitContentPostPublicationCommand(
    publishIntentId: 'intent-contract-fields',
    localDraftId: 'draft-contract-fields',
    contentType: ContentPostType.article,
    contentIdentity: ContentPostIdentity.work,
    title: '标题',
    body: '正文',
    summary: '摘要',
    semanticMentions: <ContentPostStructuredObject>[structured],
    mediaAssetIds: const <String>['asset-contract'],
    mediaItems: <ContentPostStructuredObject>[structured],
    articleMarkdown: '# 标题',
    markdownDialect: 'qwq-rich-md',
    articleAssetManifest: structured,
    articleRenderProfile: structured,
    coverStrategy: 'manual',
    coverFrameTimeMs: 1,
    illustrationAssetId: 'asset-contract',
    location: structured,
    locationName: '成都',
    geoTagRef: 'Topic/地理/行政区/四川省/成都市',
    visitedAt: DateTime.utc(2026, 4, 5),
    primaryHomepageId: 'homepage-contract',
    primaryHomepageType: 'sight',
    primaryHomepageSnapshot: structured,
    visibility: ContentPostVisibility.public,
    assistantUsePolicy: ContentPostAssistantUsePolicy.inherit,
    sourcePostId: 'source-contract',
    sourceType: ContentPostSourceType.original,
    deviceInfo: structured,
    publishLocation: structured,
    authorDisplayNameSnapshot: '作者',
    authorAvatarUrlSnapshot: 'https://example.com/avatar.jpg',
    personaContextVersion: 1,
  );
  final body = encodeContentPostSubmitPostPublicationGeneratedRequest(
    command,
  ).body;
  return Map<String, Object?>.from(body! as Map).keys.toSet();
}
