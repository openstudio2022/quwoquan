import 'package:test/test.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';

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
  });

  group('BehaviorAction — 端云枚举一致性', () {
    test('wireValue 与 Go supportedBehaviorActions 对齐', () {
      const expectedWireValues = <String>[
        'impression',
        'click',
        'dwell',
        'like',
        'share',
        'dislike',
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
        'content_depth',
        'join_circle',
        'add_contact',
        'assistant_interest',
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
      });
    });

    test('referralSourceForObjectType 按对象面精确映射（去 organicFeed 一刀切）', () {
      expect(
        referralSourceForObjectType('user'),
        ReferralSource.authorProfile,
      );
      expect(
        referralSourceForObjectType('circle'),
        ReferralSource.circlePost,
      );
      expect(
        referralSourceForObjectType('entity'),
        ReferralSource.entityPage,
      );
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

    test('channelId / rankingVersion / position 透传到 JSON（阶段五归因 common_fields）', () {
      final json = BehaviorEvent(
        contentId: 'post_1',
        action: BehaviorAction.click,
        feedRequestId: 'frq_01H',
        referralSource: ReferralSource.organicFeed,
        position: 7,
        channelId: 'following',
        rankingVersion: 'rank-v3',
      ).toJson();
      expect(json['feedRequestId'], 'frq_01H');
      expect(json['referralSource'], 'organic_feed');
      expect(json['position'], 7);
      expect(json['channelId'], 'following');
      expect(json['rankingVersion'], 'rank-v3');
    });

    test('空 channelId / rankingVersion 不写入 JSON（避免脏空串污染归因）', () {
      final json = BehaviorEvent(
        contentId: 'post_1',
        action: BehaviorAction.impression,
        channelId: '',
        rankingVersion: '',
      ).toJson();
      expect(json.containsKey('channelId'), isFalse);
      expect(json.containsKey('rankingVersion'), isFalse);
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
  });
}
