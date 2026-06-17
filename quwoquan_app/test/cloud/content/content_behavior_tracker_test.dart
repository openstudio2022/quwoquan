/// L1a Unit Tests: ContentBehaviorTracker 批量缓冲 + flush + 去重
///
/// 守护：Tracker 使用 MockBehaviorRepository，不发 HTTP。
/// 覆盖以下行为：
///   - impression 去重（同一 contentId 只上报一次）
///   - dwell < 1s 不上报
///   - batch 满 maxBatchSize 时自动 flush
///   - dispose 时 flush 剩余事件
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';

void main() {
  group('ContentBehaviorTracker', () {
    late MockBehaviorRepository repo;
    late ContentBehaviorTracker tracker;

    setUp(() {
      repo = MockBehaviorRepository();
      tracker = ContentBehaviorTracker(
        repository: repo,
        // 设置很长的 flush 间隔，避免定时器干扰
        flushInterval: const Duration(hours: 1),
        maxBatchSize: 5,
      );
    });

    tearDown(() => tracker.dispose());

    test('impression 同一 contentId 只上报一次（去重）', () async {
      tracker.trackImpression('post_1');
      tracker.trackImpression('post_1');
      tracker.trackImpression('post_2');
      await tracker.flush();

      final impressions = repo.recorded
          .where((e) => e.action == BehaviorAction.impression)
          .map((e) => e.contentId)
          .toList();
      expect(impressions, equals(['post_1', 'post_2']));
      expect(repo.recorded.first.state, equals('impressed'));
      expect(repo.recorded.first.clientEventId, isNotEmpty);
    });

    test('未达可见阈值只上报 visible，不进入 impressed 去重集合', () async {
      tracker.trackQualifiedImpression(
        'post_1',
        visibleFraction: 0.2,
        visibleDuration: const Duration(milliseconds: 500),
      );
      await tracker.flush();

      final event = repo.recorded.single;
      expect(event.action, BehaviorAction.impression);
      expect(event.state, equals('visible'));
      expect(event.toJson()['state'], equals('visible'));
      expect(event.clientEventId, isNotEmpty);
    });

    test('dwell < 1s 不上报', () async {
      tracker.trackDwell('post_1', durationSeconds: 0.5);
      await tracker.flush();
      expect(repo.recorded, isEmpty);
    });

    test('dwell >= 1s 正常上报', () async {
      tracker.trackDwell('post_1', durationSeconds: 3.5);
      await tracker.flush();

      expect(repo.recorded.length, equals(1));
      expect(repo.recorded.first.action, BehaviorAction.dwell);
      expect(repo.recorded.first.state, equals('dwell'));
      expect(repo.recorded.first.duration, equals(3.5));
    });

    test('达到 maxBatchSize 时自动 flush', () async {
      for (var i = 0; i < 5; i++) {
        tracker.trackClick('post_$i');
      }
      // maxBatchSize=5，第 5 条触发自动 flush
      // 等待异步 flush 完成
      await Future<void>.delayed(Duration.zero);
      expect(repo.recorded.length, equals(5));
    });

    test('dispose 时 flush 剩余事件', () async {
      tracker.trackClick('post_a');
      tracker.trackShare('post_b');
      expect(repo.recorded, isEmpty); // 还未 flush
      await tracker.dispose();
      expect(repo.recorded.length, equals(2));
    });

    test('dislike 事件正确上报', () async {
      tracker.trackDislike(
        'post_1',
        contentType: 'photo',
        authorId: 'author_1',
      );
      await tracker.flush();
      expect(repo.recorded.first.action, BehaviorAction.dislike);
      expect(repo.recorded.first.state, equals('negative'));
      expect(repo.recorded.first.contentId, equals('post_1'));
      expect(repo.recorded.first.contentType, equals('photo'));
      expect(repo.recorded.first.authorId, equals('author_1'));
    });

    test('hide_author 事件上报 contentId + authorId + contentType', () async {
      tracker.trackHideAuthor(
        'post_1',
        authorId: 'author_1',
        contentType: 'photo',
      );
      await tracker.flush();

      final event = repo.recorded.single;
      expect(event.action, BehaviorAction.hideAuthor);
      expect(event.state, equals('negative'));
      expect(event.contentId, equals('post_1'));
      expect(event.authorId, equals('author_1'));
      expect(event.contentType, equals('photo'));
      expect(event.toJson()['action'], equals('hide_author'));
    });

    test('hide_content_type 事件上报 contentType，可带 authorId', () async {
      tracker.trackHideContentType(
        'post_2',
        contentType: 'video',
        authorId: 'author_2',
      );
      await tracker.flush();

      final event = repo.recorded.single;
      expect(event.action, BehaviorAction.hideContentType);
      expect(event.state, equals('negative'));
      expect(event.contentId, equals('post_2'));
      expect(event.contentType, equals('video'));
      expect(event.authorId, equals('author_2'));
      expect(event.toJson()['action'], equals('hide_content_type'));
    });

    test('share 事件正确上报', () async {
      tracker.trackShare('post_1');
      await tracker.flush();
      expect(repo.recorded.first.action, BehaviorAction.share);
    });

    // ── V1-F/V1-H T3：feed 归因字段回流（feedRequestId/position/referralSource）──
    test('impression 透传 feedRequestId/position/referralSource 回流', () async {
      tracker.trackImpression(
        'post_1',
        feedRequestId: 'req-abc',
        position: 7,
        referralSource: ReferralSource.organicFeed,
      );
      await tracker.flush();

      final event = repo.recorded.single;
      expect(event.feedRequestId, equals('req-abc'));
      expect(event.position, equals(7));
      expect(event.referralSource, equals(ReferralSource.organicFeed));
    });

    test('click 透传 position + referralSource 回流', () async {
      tracker.trackClick(
        'post_2',
        feedRequestId: 'req-xyz',
        position: 3,
        referralSource: ReferralSource.organicFeed,
      );
      await tracker.flush();

      final event = repo.recorded.single;
      expect(event.action, BehaviorAction.click);
      expect(event.position, equals(3));
      expect(event.referralSource, equals(ReferralSource.organicFeed));
    });

    test('follow 交集行动回流 dimension + tagRefs（B3 归因）', () async {
      tracker.trackFollow(
        'author_1',
        feedRequestId: 'req-follow',
        referralSource: ReferralSource.organicFeed,
        intersectionDimension: 'identity',
        intersectionTagRefs: const <String>['identity/campus/xdf'],
      );
      await tracker.flush();

      final event = repo.recorded.single;
      expect(event.action, BehaviorAction.follow);
      expect(event.authorId, equals('author_1'));
      expect(event.intersectionDimension, equals('identity'));
      expect(event.intersectionTagRefs, contains('identity/campus/xdf'));
    });

    // ── S6 交集转化三类行动可区分漏斗（follow / join_circle / add_contact）──
    test('join_circle 交集行动独立动作 + dimension/tagRefs 回流', () async {
      tracker.trackJoinCircle(
        'circle_1',
        intersectionDimension: 'interest',
        intersectionTagRefs: const <String>['Topic/旅行'],
      );
      await tracker.flush();

      final event = repo.recorded.single;
      expect(event.action, BehaviorAction.joinCircle);
      expect(event.contentId, equals('circle_1'));
      expect(event.intersectionDimension, equals('interest'));
      expect(event.intersectionTagRefs, contains('Topic/旅行'));
    });

    test('add_contact 交集行动独立动作 + dimension/tagRefs 回流', () async {
      tracker.trackAddContact(
        'author_2',
        intersectionDimension: 'location',
        intersectionTagRefs: const <String>['Entity/地点/北京'],
      );
      await tracker.flush();

      final event = repo.recorded.single;
      expect(event.action, BehaviorAction.addContact);
      expect(event.contentId, equals('author_2'));
      expect(event.authorId, equals('author_2'));
      expect(event.intersectionDimension, equals('location'));
      expect(event.intersectionTagRefs, contains('Entity/地点/北京'));
    });

    test('三类交集行动 wireValue 互不相同，漏斗可区分', () {
      expect(BehaviorAction.follow.wireValue, equals('follow'));
      expect(BehaviorAction.joinCircle.wireValue, equals('join_circle'));
      expect(BehaviorAction.addContact.wireValue, equals('add_contact'));
      expect(
        BehaviorAction.fromWireValue('join_circle'),
        equals(BehaviorAction.joinCircle),
      );
      expect(
        BehaviorAction.fromWireValue('add_contact'),
        equals(BehaviorAction.addContact),
      );
    });

    // ── S6 修复：BehaviorEvent JSON roundtrip 不得丢失交集归因（入队重试场景）──
    test('BehaviorEvent toJson 携带交集字段', () {
      const event = BehaviorEvent(
        contentId: 'circle_9',
        action: BehaviorAction.joinCircle,
        intersectionDimension: 'identity',
        intersectionTagRefs: <String>['Entity/机构/学校/西电'],
      );
      final json = event.toJson();
      expect(json['action'], equals('join_circle'));
      expect(json['intersectionDimension'], equals('identity'));
      expect(json['intersectionTagRefs'], contains('Entity/机构/学校/西电'));
    });

    // ── P3 飞轮：小艺对话浮现兴趣回流（assistant_interest，不绑定具体 post）──
    test('assistant_interest 回流 tagRefs，不绑 post，去重并过滤空值', () async {
      tracker.trackAssistantInterest(const <String>[
        'Topic/旅行',
        ' Topic/景区 ',
        'Topic/旅行',
        '',
        '   ',
      ]);
      await tracker.flush();

      final event = repo.recorded.single;
      expect(event.action, BehaviorAction.assistantInterest);
      expect(event.contentId, isEmpty);
      expect(event.tags, equals(<String>['Topic/旅行', 'Topic/景区']));

      final json = event.toJson();
      expect(json['action'], equals('assistant_interest'));
      expect(json['tagRefs'], equals(<String>['Topic/旅行', 'Topic/景区']));
    });

    test('assistant_interest 全空 tagRefs 不上报', () async {
      tracker.trackAssistantInterest(const <String>['', '  ']);
      await tracker.flush();
      expect(repo.recorded, isEmpty);
    });
  });
}
