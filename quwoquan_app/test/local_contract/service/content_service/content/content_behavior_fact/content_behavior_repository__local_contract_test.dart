import 'package:test/test.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/adapters/content_behavior_event_codec.dart';
import 'package:quwoquan_app/runtime/context/actor_queue_partition.dart';
import 'package:quwoquan_app/runtime/transport/actor_queue/actor_queue_storage.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/adapters/content_behavior_outbox_adapter.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/content_service/content/content_behavior_fact/recording_content_behavior_repository.dart';

final class _RecordingBehaviorWriter implements ContentBehaviorCommandWriter {
  final commands = <ReportContentBehaviorsCommand>[];

  @override
  Future<void> reportBehaviors(ReportContentBehaviorsCommand command) async {
    commands.add(command);
  }
}

void main() {
  group('BehaviorRepository — 常规契约', () {
    late RecordingContentBehaviorRepository repo;

    setUp(() {
      repo = RecordingContentBehaviorRepository();
    });

    test('reportEvents 记录行为事件', () async {
      await repo.reportEvents(
        events: [
          BehaviorEvent(
            contentId: 'post_1',
            action: BehaviorEventType.impression,
          ),
          BehaviorEvent(contentId: 'post_2', action: BehaviorEventType.click),
        ],
      );
      expect(repo.recorded.length, 2);
    });

    test('reportSingle 记录单个事件', () async {
      await repo.reportSingle(
        contentId: 'post_3',
        action: BehaviorEventType.share,
      );
      expect(repo.recorded.length, 1);
      expect(repo.recorded.first.action, BehaviorEventType.share);
      expect(repo.recorded.first.contentId, 'post_3');
    });

    test('BehaviorEvent 支持 tags 和 duration', () {
      final event = BehaviorEvent(
        contentId: 'post_4',
        action: BehaviorEventType.dwell,
        tags: ['photo'],
        duration: 3.5,
      );
      expect(event.contentId, 'post_4');
      expect(event.action, BehaviorEventType.dwell);
      expect(event.tags, ['photo']);
      expect(event.duration, 3.5);
    });

    test(
      'storage codec 使用 canonical tagRefs，generated wire 由 typed constructor 构造',
      () {
        final event = BehaviorEvent(
          contentId: 'post_5',
          action: BehaviorEventType.dwell,
          contentType: 'image',
          tags: ['Topic/旅行', 'Entity/地点/景区'],
        );
        final storage = event.toDurableStorageJson();
        final wire = event.toRequestWire();
        expect(storage['tagRefs'], ['Topic/旅行', 'Entity/地点/景区']);
        expect(storage.containsKey('tags'), isFalse);
        expect(wire.contentType, ContentType.image);
        expect(wire.tagRefs, ['Topic/旅行', 'Entity/地点/景区']);
        expect(wire.toWire(), isNot(contains('contentVertical')));
      },
    );

    test(
      'onboarding event binds catalog selection to taxonomy release',
      () async {
        await repo.submitOnboardingInterest(
          clientEventId: 'onboarding:release-bound',
          taxonomyReleaseId: 'tag-taxonomy-20260723-001',
          tagRefs: const <String>['Topic/兴趣/旅行'],
        );

        final event = repo.recorded.single;
        expect(event.taxonomyReleaseId, 'tag-taxonomy-20260723-001');
        expect(
          event.toDurableStorageJson()['taxonomyReleaseId'],
          'tag-taxonomy-20260723-001',
        );
      },
    );

    test(
      'remote queue delegates one typed command and binds feed session per event',
      () async {
        final writer = _RecordingBehaviorWriter();
        final remote = DurableContentBehaviorRepository(
          writer: writer,
          feedSessionIdProvider: () => 'feed-session-1',
          queuePartition: ActorQueuePartition(
            environment: 'gamma',
            accountId: 'account-1',
            personaId: 'persona-1',
            deviceId: 'device-1',
          ),
          queueStorage: ActorQueueStorage(),
        );
        addTearDown(remote.dispose);

        await remote.submitOnboardingInterest(
          clientEventId: 'onboarding:actor-bound',
          taxonomyReleaseId: ' tag-taxonomy-20260723-001 ',
          tagRefs: const <String>['Topic/兴趣/旅行'],
        );

        final event = writer.commands.single.events.single;
        expect(event.taxonomyReleaseId, 'tag-taxonomy-20260723-001');
        expect(event.feedSessionId, 'feed-session-1');
        expect(event.toWire(), isNot(contains('sessionId')));
      },
    );

    test('storage codec 固化 occurredAt 并生成稳定 clientEventId', () {
      final occurredAt = DateTime.utc(2026, 7, 19, 6, 0, 0);
      final event = BehaviorEvent(
        contentId: 'post_stable_id',
        action: BehaviorEventType.click,
        occurredAt: occurredAt,
      );
      final first = event.toDurableStorageJson();
      final second = event.toDurableStorageJson();
      expect(first['occurredAt'], occurredAt.toIso8601String());
      expect(first['clientEventId'], startsWith('evt_'));
      expect(second['clientEventId'], first['clientEventId']);
    });
  });

  group('BehaviorRepository — 异常/边界契约', () {
    late RecordingContentBehaviorRepository repo;

    setUp(() {
      repo = RecordingContentBehaviorRepository();
    });

    test('reportEvents 空事件列表不崩溃', () async {
      await repo.reportEvents(events: []);
      expect(repo.recorded, isEmpty);
    });

    test('Remote dispose 后不再调用 generated writer', () async {
      final writer = _RecordingBehaviorWriter();
      final remote = DurableContentBehaviorRepository(
        writer: writer,
        queuePartition: ActorQueuePartition(environment: ''),
        queueStorage: ActorQueueStorage(),
      );
      remote.dispose();

      await remote.reportEvents(
        events: <BehaviorEvent>[
          BehaviorEvent(
            contentId: 'post_disposed',
            action: BehaviorEventType.impression,
          ),
        ],
      );

      expect(writer.commands, isEmpty);
    });
  });

  group('BehaviorEventType — 端云枚举一致性', () {
    test('wireName 与 canonical BehaviorEventType 对齐', () {
      const expectedWireValues = <String>[
        'impression',
        'click',
        'intersection_expand',
        'dwell',
        'like',
        'share',
        'dislike',
        'undo_dislike',
        'hide_author',
        'hide_content_type',
        'report',
        'skip',
        'comment',
        'follow',
        'author_view',
        'entity_page_view',
        'tag_click',
        'play_progress',
        'effective_play',
        'content_depth',
        'join_circle',
        'leave_circle',
        'add_contact',
        'assistant_interest',
        'onboarding_interest',
        'intersection_feedback',
        'wishlist_add',
        'wishlist_remove',
      ];
      final actualWireValues = BehaviorEventType.values
          .map((a) => a.wireName)
          .toList();
      expect(actualWireValues, containsAll(expectedWireValues));
      expect(actualWireValues.length, expectedWireValues.length);
    });

    // ── N10：ReferralSource 闭集与云侧 behaviors.yaml enum / ReferralSourceMultiplier 键对齐 ──
    test('ReferralSource.value 闭集与 metadata enum 一一对应（含 my_intersections）', () {
      final values = ReferralSource.values.map((s) => s.value).toSet();
      expect(values, <String>{
        'organic_feed',
        'friend_share',
        'chat_link',
        'circle_post',
        'author_profile',
        'entity_page',
        'search',
        'push_notification',
        'deep_link',
        'my_intersections',
        'publish_result',
      });
    });

    test('referralSourceForObjectType 按对象面精确映射（去 organicFeed 一刀切）', () {
      expect(referralSourceForObjectType('user'), ReferralSource.authorProfile);
      expect(referralSourceForObjectType('circle'), ReferralSource.circlePost);
      expect(referralSourceForObjectType('entity'), ReferralSource.entityPage);
      expect(
        referralSourceForObjectType('homepage'),
        ReferralSource.entityPage,
      );
      // 未知 / 缺省对象面回退作者主页（最近邻，非推荐流）。
      expect(referralSourceForObjectType(''), ReferralSource.authorProfile);
      expect(
        referralSourceForObjectType('  circle  '),
        ReferralSource.circlePost,
      );
    });

    test('storage codec 使用 generated wireName 而非 enum name', () {
      final event = BehaviorEvent(
        contentId: 'post_1',
        action: BehaviorEventType.authorView,
      );
      final json = event.toDurableStorageJson();
      expect(json['action'], 'author_view');
    });

    test('深度行为事件包含 engagementDepth 和 consumedRatio', () {
      final event = BehaviorEvent(
        contentId: 'post_1',
        action: BehaviorEventType.contentDepth,
        engagementDepth: 3,
        consumedRatio: 0.85,
        totalUnits: 12,
      );
      final json = event.toDurableStorageJson();
      expect(json['engagementDepth'], 3);
      expect(json['consumedRatio'], 0.85);
      expect(json['totalUnits'], 12);
    });

    test('feedRequestId 透传到 JSON', () {
      final event = BehaviorEvent(
        contentId: 'post_1',
        action: BehaviorEventType.impression,
        clientEventId: 'evt-1',
        state: 'impressed',
        feedRequestId: 'req-uuid-123',
      );
      final json = event.toDurableStorageJson();
      expect(json['clientEventId'], 'evt-1');
      expect(json['state'], 'impressed');
      expect(json['feedRequestId'], 'req-uuid-123');
    });

    test('推荐归因字段透传到 JSON（阶段五 common_fields + P0+ attribution）', () {
      final json = BehaviorEvent(
        contentId: 'post_1',
        action: BehaviorEventType.click,
        feedRequestId: 'frq_01H',
        referralSource: ReferralSource.organicFeed,
        position: 7,
        channelId: 'following',
        policyDigest:
            'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
        recallPath: 'collab_i2i',
        supplySource: 'data_engineering',
      ).toDurableStorageJson();
      expect(json['feedRequestId'], 'frq_01H');
      expect(json['referralSource'], 'organic_feed');
      expect(json['position'], 7);
      expect(json['channelId'], 'following');
      expect(
        json['policyDigest'],
        'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      );
      expect(json['recallPath'], 'collab_i2i');
      expect(json['supplySource'], 'data_engineering');
      expect(json.containsKey('contentVertical'), isFalse);
    });

    test('来源未提供推荐归因时不写入 JSON', () {
      final json = BehaviorEvent(
        contentId: 'post_1',
        action: BehaviorEventType.impression,
        channelId: '',
        recallPath: '',
        supplySource: '',
      ).toDurableStorageJson();
      expect(json.containsKey('channelId'), isFalse);
      expect(json.containsKey('policyDigest'), isFalse);
      expect(json.containsKey('recallPath'), isFalse);
      expect(json.containsKey('contentVertical'), isFalse);
      expect(json.containsKey('supplySource'), isFalse);
    });

    test('非空 policyDigest 必须精确匹配唯一 canonical 形态', () {
      const canonical =
          'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
      for (final invalid in <String>[
        '',
        'rank-v3',
        ' $canonical',
        '$canonical ',
        invalidSha256Fixture(List<String>.filled(64, 'A').join()),
        invalidSha256Fixture(List<String>.filled(63, 'a').join()),
      ]) {
        expect(
          () => BehaviorEvent(
            contentId: 'post_1',
            action: BehaviorEventType.impression,
            policyDigest: invalid,
          ),
          throwsFormatException,
          reason: 'must reject <$invalid> without trimming or fallback',
        );
      }
    });

    test('hide_author / hide_content_type 透传 authorId 与 contentType', () {
      final hideAuthorJson = BehaviorEvent(
        contentId: 'post_1',
        action: BehaviorEventType.hideAuthor,
        authorId: 'author_1',
        contentType: 'photo',
      ).toDurableStorageJson();
      expect(hideAuthorJson['action'], 'hide_author');
      expect(hideAuthorJson['authorId'], 'author_1');
      expect(hideAuthorJson['contentType'], 'photo');

      final hideTypeJson = BehaviorEvent(
        contentId: 'post_2',
        action: BehaviorEventType.hideContentType,
        contentType: 'video',
      ).toDurableStorageJson();
      expect(hideTypeJson['action'], 'hide_content_type');
      expect(hideTypeJson['contentType'], 'video');
    });

    test('wishlist_add 透传 objectId/objectKind/displayName/sourceSurface', () {
      final json = BehaviorEvent(
        contentId: 'homepage_west_lake',
        action: BehaviorEventType.wishlistAdd,
        objectId: 'homepage_west_lake',
        objectKind: 'homepage',
        displayName: '西湖日落机位',
        sourceSurface: 'object_homepage',
        entityRefs: const <String>['homepage_west_lake'],
        feedRequestId: 'frq_wish_1',
        referralSource: ReferralSource.entityPage,
      ).toDurableStorageJson();

      expect(json['action'], 'wishlist_add');
      expect(json['contentId'], 'homepage_west_lake');
      expect(json['objectId'], 'homepage_west_lake');
      expect(json['objectKind'], 'homepage');
      expect(json['displayName'], '西湖日落机位');
      expect(json['sourceSurface'], 'object_homepage');
      expect(json['entityRefs'], <String>['homepage_west_lake']);
      expect(json['feedRequestId'], 'frq_wish_1');
      expect(json['referralSource'], 'entity_page');
    });
  });
}

String invalidSha256Fixture(String payload) => 'sha256:$payload';
