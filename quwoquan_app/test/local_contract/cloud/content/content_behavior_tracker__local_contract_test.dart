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

import '../../../support/cloud_services/behavior_repository_double.dart';

/// 任务 B 测试用：可控失败的行为仓储，验证 flush 失败路径的结构化兜底。
class _FlakyBehaviorRepository extends BehaviorRepository {
  final List<BehaviorEvent> recorded = <BehaviorEvent>[];

  @override
  Future<void> clearPendingForLogout() async {
    recorded.clear();
  }

  bool shouldThrow = false;

  @override
  Future<void> reportEvents({required List<BehaviorEvent> events}) async {
    if (shouldThrow) {
      throw StateError('simulated behavior upload failure');
    }
    recorded.addAll(events);
  }

  @override
  Future<void> submitOnboardingInterest({
    required String clientEventId,
    required String catalogVersion,
    required String taxonomyReleaseId,
    required List<String> tagRefs,
  }) async {
    recorded.add(
      BehaviorEvent(
        contentId: '',
        action: BehaviorAction.onboardingInterest,
        clientEventId: clientEventId,
        catalogVersion: catalogVersion,
        taxonomyReleaseId: taxonomyReleaseId,
        tags: tagRefs,
      ),
    );
  }
}

void main() {
  group('ContentBehaviorTracker flush 失败兜底', () {
    test('上报失败时不抛异常、事件回灌缓冲，恢复后可重发不丢失', () async {
      final repo = _FlakyBehaviorRepository();
      final tracker = ContentBehaviorTracker(
        reporter: repo,
        flushInterval: const Duration(hours: 1),
        maxBatchSize: 5,
        enablePeriodicFlush: false,
      );
      addTearDown(tracker.dispose);

      tracker.trackClick('post_a');
      tracker.trackShare('post_b');

      // 上报失败：flush 不得向调用方抛出异常，事件不得被静默丢弃。
      repo.shouldThrow = true;
      await expectLater(tracker.flush(), completes);
      expect(repo.recorded, isEmpty);

      // 恢复后再次 flush：先前失败的事件被回灌并重新上报。
      repo.shouldThrow = false;
      await tracker.flush();
      expect(
        repo.recorded.map((e) => e.contentId).toList(),
        containsAll(<String>['post_a', 'post_b']),
      );
    });
  });

  group('ContentBehaviorTracker', () {
    late MockBehaviorRepository repo;
    late ContentBehaviorTracker tracker;

    setUp(() {
      repo = MockBehaviorRepository();
      tracker = ContentBehaviorTracker(
        reporter: repo,
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

    test('onboarding_interest 回流去重后的路径制 tagRefs（N2-4/W11）', () async {
      tracker.trackOnboardingInterest(<String>[
        'Topic/旅行',
        ' Topic/旅行 ',
        'Topic/摄影',
        '',
      ]);
      await tracker.flush();

      final event = repo.recorded.single;
      expect(event.action, BehaviorAction.onboardingInterest);
      expect(event.state, 'interaction');
      expect(event.contentId, isEmpty, reason: '兴趣先验不绑定具体 post');
      expect(event.tags, equals(<String>['Topic/旅行', 'Topic/摄影']));
    });

    test('onboarding_interest 空标签不产生事件', () async {
      tracker.trackOnboardingInterest(<String>['', '  ']);
      await tracker.flush();
      expect(repo.recorded, isEmpty);
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

    test('effective_play 仅上报实际播放证据并携带播放会话', () async {
      tracker.trackEffectivePlayback(
        'post_video_1',
        playbackSessionId: 'video-session-1',
        effectivePlayMs: 8000,
        consumedRatio: 0.064,
        totalUnits: 125,
        contentType: 'video',
      );
      await tracker.flush();

      final event = repo.recorded.single;
      expect(event.action, BehaviorAction.effectivePlay);
      expect(event.state, 'foreground_visible_playing');
      expect(event.sessionId, 'video-session-1');
      expect(event.effectivePlayMs, 8000);
      expect(event.toJson()['effectivePlayMs'], 8000);
      expect(event.toJson()['sessionId'], 'video-session-1');
    });

    test('works_image_pageflip_motion 上报舒适度 motion 字段', () async {
      tracker.trackWorksImagePageflipMotion(
        'post_image_1',
        direction: 'forward',
        motionProfile: 'comfort_curl',
        settleMs: 384,
        reducedMotion: false,
        committed: true,
        contentType: 'photo',
        feedRequestId: 'feed_req_1',
      );
      await tracker.flush();

      final event = repo.recorded.single;
      expect(event.action, BehaviorAction.contentDepth);
      expect(event.state, 'works_image_pageflip_motion');
      expect(event.motionDirection, 'forward');
      expect(event.motionProfile, 'comfort_curl');
      expect(event.settleMs, 384);
      expect(event.reducedMotion, isFalse);
      expect(event.committed, isTrue);
      expect(event.duration, 0.384);
      final json = event.toJson();
      expect(json['state'], 'works_image_pageflip_motion');
      expect(json['direction'], 'forward');
      expect(json['motionProfile'], 'comfort_curl');
      expect(json['settleMs'], 384);
      expect(json['reducedMotion'], isFalse);
      expect(json['committed'], isTrue);
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

    test('undo_dislike 作为中性补偿事件上报', () async {
      tracker.trackUndoDislike(
        'post_1',
        contentType: 'photo',
        authorId: 'author_1',
      );
      await tracker.flush();
      expect(repo.recorded.first.action, BehaviorAction.undoDislike);
      expect(repo.recorded.first.state, 'interaction');
      expect(repo.recorded.first.contentId, 'post_1');
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

    // ── 阶段五 + P0+：推荐归因字段全事件透传（common_fields + attribution）──
    test('impression 透传推荐归因字段回流', () async {
      tracker.trackImpression(
        'post_ch',
        feedRequestId: 'frq_01H',
        position: 2,
        referralSource: ReferralSource.organicFeed,
        channelId: 'following',
        rankingVersion: 'rank-v3',
        reasonVersion: 'reason-v2',
        recallPath: 'collab_i2i',
        contentVertical: 'travel_photography',
        supplySource: 'data_engineering',
      );
      await tracker.flush();

      final event = repo.recorded.single;
      expect(event.state, equals('impressed'));
      expect(event.channelId, equals('following'));
      expect(event.rankingVersion, equals('rank-v3'));
      expect(event.reasonVersion, equals('reason-v2'));
      expect(event.recallPath, equals('collab_i2i'));
      expect(event.contentVertical, equals('travel_photography'));
      expect(event.supplySource, equals('data_engineering'));
      expect(event.feedRequestId, equals('frq_01H'));
    });

    test('click 独立七态并透传推荐归因字段回流', () async {
      tracker.trackClick(
        'post_ch2',
        feedRequestId: 'frq_02H',
        position: 5,
        referralSource: ReferralSource.organicFeed,
        channelId: 'video',
        rankingVersion: 'rank-v9',
        reasonVersion: 'reason-v9',
        recallPath: 'collab_u2i',
        contentVertical: 'general',
        supplySource: 'ugc',
      );
      await tracker.flush();

      final event = repo.recorded.single;
      expect(event.action, BehaviorAction.click);
      expect(event.state, equals('click'));
      expect(event.channelId, equals('video'));
      expect(event.rankingVersion, equals('rank-v9'));
      expect(event.reasonVersion, equals('reason-v9'));
      expect(event.recallPath, equals('collab_u2i'));
      expect(event.contentVertical, equals('general'));
      expect(event.supplySource, equals('ugc'));
    });

    // ── N7：交集证据组点击统一通道，保 tag_click 语义（推荐 HotPath 1.8 权重）──
    test('tag_click 交集证据组点击：独立动作（禁降级为 click）+ 完整交集归因回流', () async {
      tracker.trackTagClick(
        'u_lin',
        contentType: 'user',
        authorId: 'u_lin',
        referralSource: ReferralSource.authorProfile,
        tags: const <String>['relationship/sharedFollowees'],
        feedRequestId: 'feed_req_video_book',
        channelId: 'premium_stream',
        rankingVersion: 'rank-v-video-book',
        reasonVersion: 'reason-v-video-book',
        intersectionId: 'ix_1',
        intersectionDimension: 'relationship',
        intersectionSourceRef: 'sharedFollowees',
        intersectionTagRefs: const <String>['relationship/sharedFollowees'],
        intersectionClass: 'fact',
        intersectionEvidenceId: 'ev_1',
      );
      await tracker.flush();

      final event = repo.recorded.single;
      // 关键不变量：保留 tag_click 语义，未降级为 click（否则丢推荐 1.8 权重）。
      expect(event.action, BehaviorAction.tagClick);
      expect(event.toJson()['action'], equals('tag_click'));
      expect(event.state, equals('interaction'));
      expect(event.contentId, equals('u_lin'));
      expect(event.authorId, equals('u_lin'));
      expect(event.referralSource, equals(ReferralSource.authorProfile));
      expect(event.feedRequestId, equals('feed_req_video_book'));
      expect(event.channelId, equals('premium_stream'));
      expect(event.rankingVersion, equals('rank-v-video-book'));
      expect(event.reasonVersion, equals('reason-v-video-book'));
      expect(event.intersectionId, equals('ix_1'));
      expect(event.intersectionDimension, equals('relationship'));
      expect(event.intersectionSourceRef, equals('sharedFollowees'));
      expect(event.intersectionClass, equals('fact'));
      expect(
        event.intersectionTagRefs,
        contains('relationship/sharedFollowees'),
      );
      expect(event.intersectionEvidenceId, equals('ev_1'));
    });

    // ── 七态漏斗：visible（弱可见）与 impressed（达阈值）状态严格区分，归因字段全透传 ──
    test(
      '七态漏斗：visible 未达阈值 vs impressed 达阈值，状态区分且 channelId/rankingVersion 透传',
      () async {
        tracker.trackQualifiedImpression(
          'post_visible',
          visibleFraction: 0.3,
          visibleDuration: const Duration(milliseconds: 400),
          feedRequestId: 'frq_07',
          channelId: 'recommend',
          rankingVersion: 'rank-v7',
        );
        tracker.trackQualifiedImpression(
          'post_impressed',
          visibleFraction: 0.8,
          visibleDuration: const Duration(milliseconds: 1500),
          feedRequestId: 'frq_07',
          channelId: 'recommend',
          rankingVersion: 'rank-v7',
        );
        await tracker.flush();

        final visible = repo.recorded.firstWhere(
          (e) => e.contentId == 'post_visible',
        );
        final impressed = repo.recorded.firstWhere(
          (e) => e.contentId == 'post_impressed',
        );
        expect(visible.state, equals('visible'));
        expect(impressed.state, equals('impressed'));
        for (final event in <BehaviorEvent>[visible, impressed]) {
          expect(event.feedRequestId, equals('frq_07'));
          expect(event.channelId, equals('recommend'));
          expect(event.rankingVersion, equals('rank-v7'));
        }
      },
    );

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
      final event = BehaviorEvent(
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

    test('wishlist_add 写入对象上下文与归因，支撑 coWishlistedEntity 事实源', () async {
      tracker.trackWishlistAdd(
        'homepage_west_lake',
        objectKind: 'homepage',
        displayName: '西湖日落机位',
        sourceSurface: 'object_homepage',
        feedRequestId: 'frq_wish_1',
        position: 2,
        referralSource: ReferralSource.entityPage,
        channelId: 'recommend',
        rankingVersion: 'rank-v-wishlist',
      );
      await tracker.flush();

      final event = repo.recorded.single;
      expect(event.action, BehaviorAction.wishlistAdd);
      expect(event.state, 'interaction');
      expect(event.contentId, 'homepage_west_lake');
      expect(event.objectId, 'homepage_west_lake');
      expect(event.objectKind, 'homepage');
      expect(event.displayName, '西湖日落机位');
      expect(event.sourceSurface, 'object_homepage');
      expect(event.entityRefs, <String>['homepage_west_lake']);
      final json = event.toJson();
      expect(json['action'], 'wishlist_add');
      expect(json['objectId'], 'homepage_west_lake');
      expect(json['objectKind'], 'homepage');
      expect(json['displayName'], '西湖日落机位');
      expect(json['sourceSurface'], 'object_homepage');
      expect(json['feedRequestId'], 'frq_wish_1');
      expect(json['referralSource'], 'entity_page');
    });

    test('wishlist_remove 写 removed 语义，空对象不上报', () async {
      tracker.trackWishlistAdd('', objectKind: 'homepage');
      tracker.trackWishlistRemove('homepage_west_lake', objectKind: 'homepage');
      await tracker.flush();

      final event = repo.recorded.single;
      expect(event.action, BehaviorAction.wishlistRemove);
      expect(event.state, 'negative');
      expect(event.contentId, 'homepage_west_lake');
      expect(event.objectId, 'homepage_west_lake');
      expect(event.objectKind, 'homepage');
      expect(event.toJson()['action'], 'wishlist_remove');
    });
  });
}
