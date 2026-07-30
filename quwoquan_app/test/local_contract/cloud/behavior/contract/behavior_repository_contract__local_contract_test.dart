import 'dart:convert';

import 'package:fake_async/fake_async.dart';
import 'package:http/http.dart' as http;
import 'package:test/test.dart';
import 'package:quwoquan_app/cloud/runtime/context/actor_queue_partition.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';

import '../../../../support/cloud_services/behavior_repository_double.dart';

final class _UnavailableCloudHttpClient extends CloudHttpClient {
  _UnavailableCloudHttpClient() : super(client: http.Client());

  @override
  Future<http.Response> postBytes(
    Uri uri, {
    required Map<String, String> headers,
    required List<int> body,
  }) async => http.Response('', 503);
}

final class _CapturingCloudHttpClient extends CloudHttpClient {
  _CapturingCloudHttpClient() : super(client: http.Client());

  Map<String, String>? lastHeaders;
  List<int>? lastBody;
  final headersHistory = <Map<String, String>>[];

  @override
  Future<http.Response> postBytes(
    Uri uri, {
    required Map<String, String> headers,
    required List<int> body,
  }) async {
    lastHeaders = Map<String, String>.from(headers);
    lastBody = List<int>.from(body);
    headersHistory.add(lastHeaders!);
    return http.Response('', 204);
  }
}

void main() {
  group('BehaviorRepository — 常规契约', () {
    late MockBehaviorRepository repo;

    setUp(() {
      repo = MockBehaviorRepository();
    });

    test('reportEvents 记录行为事件', () async {
      await repo.reportEvents(
        events: [
          BehaviorEvent(contentId: 'post_1', action: BehaviorAction.impression),
          BehaviorEvent(contentId: 'post_2', action: BehaviorAction.click),
        ],
      );
      expect(repo.recorded.length, 2);
    });

    test('reportSingle 记录单个事件', () async {
      await repo.reportSingle(
        contentId: 'post_3',
        action: BehaviorAction.share,
      );
      expect(repo.recorded.length, 1);
      expect(repo.recorded.first.action, BehaviorAction.share);
      expect(repo.recorded.first.contentId, 'post_3');
    });

    test('BehaviorEvent 支持 tags 和 duration', () {
      final event = BehaviorEvent(
        contentId: 'post_4',
        action: BehaviorAction.dwell,
        tags: ['photo'],
        duration: 3.5,
      );
      expect(event.contentId, 'post_4');
      expect(event.action, BehaviorAction.dwell);
      expect(event.tags, ['photo']);
      expect(event.duration, 3.5);
    });

    test('toJson 使用 tagRefs wire key（对齐云侧 BehaviorEventInput，无旧 tags 键残留）', () {
      final json = BehaviorEvent(
        contentId: 'post_5',
        action: BehaviorAction.dwell,
        tags: ['Topic/旅行', 'Entity/地点/景区'],
      ).toJson();
      expect(json['tagRefs'], ['Topic/旅行', 'Entity/地点/景区']);
      expect(json.containsKey('tags'), isFalse);
    });

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
          event.toJson()['taxonomyReleaseId'],
          'tag-taxonomy-20260723-001',
        );
      },
    );

    test(
      'remote batch binds the queue owner actor to request headers',
      () async {
        final httpClient = _CapturingCloudHttpClient();
        final remote = RemoteBehaviorRepository(
          httpClient: httpClient,
          baseUrl: 'https://api.example.com',
          queuePartition: ActorQueuePartition(
            environment: 'gamma',
            accountId: 'account-1',
            personaId: 'persona-1',
            deviceId: 'device-1',
          ),
        );
        addTearDown(() {
          remote.dispose();
          httpClient.close();
        });

        await remote.submitOnboardingInterest(
          clientEventId: 'onboarding:actor-bound',
          taxonomyReleaseId: ' tag-taxonomy-20260723-001 ',
          tagRefs: const <String>['Topic/兴趣/旅行'],
        );

        expect(httpClient.lastHeaders, isNotNull);
        expect(httpClient.lastHeaders!['X-Client-User-Id'], 'account-1');
        expect(httpClient.lastHeaders!['X-Client-Persona-Id'], 'persona-1');
        expect(httpClient.lastHeaders!['X-Client-Device-Actor-Id'], 'device-1');
        expect(
          httpClient.lastHeaders!['Idempotency-Key'],
          matches(RegExp(r'^behavior-batch-[0-9a-f]{64}$')),
        );
        final payload = jsonDecode(utf8.decode(httpClient.lastBody!)) as Map;
        final event = (payload['events'] as List).single as Map;
        expect(event['taxonomyReleaseId'], 'tag-taxonomy-20260723-001');
        // Retired catalogVersion must not be emitted on the canonical wire.
        expect(event.keys, isNot(contains('catalogVersion')));

        await remote.submitOnboardingInterest(
          clientEventId: 'onboarding:actor-bound',
          taxonomyReleaseId: 'tag-taxonomy-20260723-001',
          tagRefs: const <String>['Topic/兴趣/旅行'],
        );

        expect(
          httpClient.headersHistory.last['Idempotency-Key'],
          httpClient.headersHistory.first['Idempotency-Key'],
        );
      },
    );

    test('toJson 固化 occurredAt 并生成稳定 clientEventId', () {
      final occurredAt = DateTime.utc(2026, 7, 19, 6, 0, 0);
      final event = BehaviorEvent(
        contentId: 'post_stable_id',
        action: BehaviorAction.click,
        occurredAt: occurredAt,
      );
      final first = event.toJson();
      final second = event.toJson();
      expect(first['occurredAt'], occurredAt.toIso8601String());
      expect(first['clientEventId'], startsWith('evt_'));
      expect(second['clientEventId'], first['clientEventId']);
    });
  });

  group('BehaviorRepository — 异常/边界契约', () {
    late MockBehaviorRepository repo;

    setUp(() {
      repo = MockBehaviorRepository();
    });

    test('reportEvents 空事件列表不崩溃', () async {
      await repo.reportEvents(events: []);
      expect(repo.recorded, isEmpty);
    });

    test('Remote dispose 会取消退避计时器并结束在途重试', () {
      fakeAsync((clock) {
        final remote = RemoteBehaviorRepository(
          httpClient: _UnavailableCloudHttpClient(),
          baseUrl: 'https://api.example.com',
          queuePartition: ActorQueuePartition(environment: ''),
        );
        var completed = false;
        remote
            .reportEvents(
              events: <BehaviorEvent>[
                BehaviorEvent(
                  contentId: 'post_retry',
                  action: BehaviorAction.impression,
                ),
              ],
            )
            .then((_) => completed = true);

        clock.flushMicrotasks();
        expect(clock.pendingTimers, hasLength(1));

        remote.dispose();
        clock.flushMicrotasks();

        expect(clock.pendingTimers, isEmpty);
        expect(completed, isTrue);
      });
    });
  });

  group('BehaviorAction — 端云枚举一致性', () {
    test('wireValue 与 Go supportedBehaviorActions 对齐', () {
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
        'add_contact',
        'assistant_interest',
        'onboarding_interest',
        'intersection_feedback',
        'wishlist_add',
        'wishlist_remove',
      ];
      final actualWireValues = BehaviorAction.values
          .map((a) => a.wireValue)
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

    test('toJson 使用 wireValue 而非 enum name', () {
      final event = BehaviorEvent(
        contentId: 'post_1',
        action: BehaviorAction.authorView,
      );
      final json = event.toJson();
      expect(json['action'], 'author_view');
    });

    test('深度行为事件包含 engagementDepth 和 consumedRatio', () {
      final event = BehaviorEvent(
        contentId: 'post_1',
        action: BehaviorAction.contentDepth,
        engagementDepth: 3,
        consumedRatio: 0.85,
        totalUnits: 12,
      );
      final json = event.toJson();
      expect(json['engagementDepth'], 3);
      expect(json['consumedRatio'], 0.85);
      expect(json['totalUnits'], 12);
    });

    test('feedRequestId 透传到 JSON', () {
      final event = BehaviorEvent(
        contentId: 'post_1',
        action: BehaviorAction.impression,
        clientEventId: 'evt-1',
        state: 'impressed',
        feedRequestId: 'req-uuid-123',
      );
      final json = event.toJson();
      expect(json['clientEventId'], 'evt-1');
      expect(json['state'], 'impressed');
      expect(json['feedRequestId'], 'req-uuid-123');
    });

    test('推荐归因字段透传到 JSON（阶段五 common_fields + P0+ attribution）', () {
      final json = BehaviorEvent(
        contentId: 'post_1',
        action: BehaviorAction.click,
        feedRequestId: 'frq_01H',
        referralSource: ReferralSource.organicFeed,
        position: 7,
        channelId: 'following',
        policyDigest:
            'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
        recallPath: 'collab_i2i',
        contentVertical: 'travel_photography',
        supplySource: 'data_engineering',
      ).toJson();
      expect(json['feedRequestId'], 'frq_01H');
      expect(json['referralSource'], 'organic_feed');
      expect(json['position'], 7);
      expect(json['channelId'], 'following');
      expect(
        json['policyDigest'],
        'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      );
      expect(json['recallPath'], 'collab_i2i');
      expect(json['contentVertical'], 'travel_photography');
      expect(json['supplySource'], 'data_engineering');
    });

    test('来源未提供推荐归因时不写入 JSON', () {
      final json = BehaviorEvent(
        contentId: 'post_1',
        action: BehaviorAction.impression,
        channelId: '',
        recallPath: '',
        contentVertical: '',
        supplySource: '',
      ).toJson();
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
        'sha256:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA',
        'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      ]) {
        expect(
          () => BehaviorEvent(
            contentId: 'post_1',
            action: BehaviorAction.impression,
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
        action: BehaviorAction.hideAuthor,
        authorId: 'author_1',
        contentType: 'photo',
      ).toJson();
      expect(hideAuthorJson['action'], 'hide_author');
      expect(hideAuthorJson['authorId'], 'author_1');
      expect(hideAuthorJson['contentType'], 'photo');

      final hideTypeJson = BehaviorEvent(
        contentId: 'post_2',
        action: BehaviorAction.hideContentType,
        contentType: 'video',
      ).toJson();
      expect(hideTypeJson['action'], 'hide_content_type');
      expect(hideTypeJson['contentType'], 'video');
    });

    test('wishlist_add 透传 objectId/objectKind/displayName/sourceSurface', () {
      final json = BehaviorEvent(
        contentId: 'homepage_west_lake',
        action: BehaviorAction.wishlistAdd,
        objectId: 'homepage_west_lake',
        objectKind: 'homepage',
        displayName: '西湖日落机位',
        sourceSurface: 'object_homepage',
        entityRefs: const <String>['homepage_west_lake'],
        feedRequestId: 'frq_wish_1',
        referralSource: ReferralSource.entityPage,
      ).toJson();

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
