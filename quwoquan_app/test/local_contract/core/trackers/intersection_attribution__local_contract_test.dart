import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_kind_metadata.g.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';

import '../../../support/cloud_services/behavior_repository_double.dart';

/// SIT4 · 交集曝光 → 点击 → 转化漏斗归因（T2 模块交互 + T1 契约对齐）。
///
/// 校验 ContentBehaviorTracker 上报的 BehaviorEvent 携带 behaviors.yaml 声明的
/// 交集归因字段（intersectionId/dimension/class/sourceRef/evidenceId/tagRefs +
/// referralSource/feedRequestId/position），且转化行动（follow/join_circle/
/// add_contact）回流 dimension + sourceRef + tagRefs。
void main() {
  late MockBehaviorRepository repo;
  late ContentBehaviorTracker tracker;

  setUp(() {
    repo = MockBehaviorRepository();
    tracker = ContentBehaviorTracker(
      reporter: repo,
      maxBatchSize: 100,
      enablePeriodicFlush: false,
    );
  });

  tearDown(() => tracker.dispose());

  // behaviors.yaml impression/click payload_fields 中的交集归因键。
  const exposureAttributionKeys = <String>{
    'intersectionId',
    'intersectionDimension',
    'intersectionClass',
    'intersectionSourceRef',
    'intersectionEvidenceId',
  };
  // follow/join_circle/add_contact 转化归因键。
  const conversionAttributionKeys = <String>{
    'intersectionDimension',
    'intersectionSourceRef',
    'intersectionTagRefs',
  };

  test('曝光归因：impression 携带全套交集漏斗字段', () async {
    tracker.trackImpression(
      'object_a',
      contentType: 'person',
      feedRequestId: 'feed_req_1',
      position: 2,
      referralSource: ReferralSource.organicFeed,
      intersectionId: 'ix_rel_a',
      intersectionDimension: 'relationship',
      intersectionClass: 'fact',
      intersectionSourceRef: 'sharedFollowees',
      intersectionTagRefs: const <String>['tag/relationship/shared_follow'],
      intersectionEvidenceId: 'ev_rel_a',
    );
    await tracker.flush();

    expect(repo.recorded, hasLength(1));
    final event = repo.recorded.single;
    expect(event.action, BehaviorAction.impression);
    final json = event.toJson();
    for (final key in exposureAttributionKeys) {
      expect(json.containsKey(key), isTrue, reason: 'impression 缺少 $key');
    }
    expect(json['intersectionId'], 'ix_rel_a');
    expect(json['intersectionDimension'], 'relationship');
    expect(json['intersectionClass'], 'fact');
    expect(json['intersectionSourceRef'], 'sharedFollowees');
    expect(json['intersectionEvidenceId'], 'ev_rel_a');
    expect(json['referralSource'], 'organic_feed');
    expect(json['feedRequestId'], 'feed_req_1');
    expect(json['position'], 2);
  });

  test('曝光去重：同一 contentId 仅上报一次 impression', () async {
    tracker.trackImpression('object_a', intersectionId: 'ix_a');
    tracker.trackImpression('object_a', intersectionId: 'ix_a');
    await tracker.flush();

    final impressions = repo.recorded
        .where((e) => e.action == BehaviorAction.impression)
        .toList(growable: false);
    expect(impressions, hasLength(1));
  });

  test('点击归因：click 携带全套交集漏斗字段并可与曝光按同一 kind 下钻', () async {
    tracker.trackClick(
      'object_a',
      feedRequestId: 'feed_req_1',
      position: 2,
      referralSource: ReferralSource.organicFeed,
      intersectionId: 'ix_rel_a',
      intersectionDimension: 'relationship',
      intersectionClass: 'fact',
      intersectionSourceRef: 'sharedFollowees',
      intersectionTagRefs: const <String>['tag/relationship/shared_follow'],
      intersectionEvidenceId: 'ev_rel_a',
    );
    await tracker.flush();

    final event = repo.recorded.single;
    expect(event.action, BehaviorAction.click);
    final json = event.toJson();
    for (final key in exposureAttributionKeys) {
      expect(json.containsKey(key), isTrue, reason: 'click 缺少 $key');
    }
    // 曝光与点击共用 intersectionSourceRef（§5.4 kind），支持同 kind 漏斗下钻。
    expect(json['intersectionSourceRef'], 'sharedFollowees');
    expect(json['intersectionId'], 'ix_rel_a');
  });

  test(
    '转化归因：follow/join_circle/add_contact 回流 dimension + sourceRef + tagRefs',
    () async {
      tracker.trackFollow(
        'u_lin',
        feedRequestId: 'feed_req_1',
        referralSource: ReferralSource.organicFeed,
        intersectionDimension: 'relationship',
        intersectionSourceRef: 'sharedFollowees',
        intersectionTagRefs: const <String>['tag/relationship/shared_follow'],
      );
      tracker.trackJoinCircle(
        'circle_photo',
        intersectionDimension: 'interest',
        intersectionSourceRef: 'sharedInterest',
        intersectionTagRefs: const <String>['tag/interest/photography'],
      );
      tracker.trackAddContact(
        'u_zhou',
        intersectionDimension: 'location',
        intersectionSourceRef: 'sameCity',
        intersectionTagRefs: const <String>['tag/location/chengdu'],
      );
      await tracker.flush();

      final byAction = {for (final e in repo.recorded) e.action: e};
      for (final action in <BehaviorAction>[
        BehaviorAction.follow,
        BehaviorAction.joinCircle,
        BehaviorAction.addContact,
      ]) {
        final event = byAction[action];
        expect(event, isNotNull, reason: '缺少 $action 转化事件');
        final json = event!.toJson();
        for (final key in conversionAttributionKeys) {
          expect(json.containsKey(key), isTrue, reason: '$action 缺少 $key');
        }
      }
      expect(
        byAction[BehaviorAction.follow]!.toJson()['intersectionDimension'],
        'relationship',
      );
      expect(
        byAction[BehaviorAction.joinCircle]!.toJson()['intersectionSourceRef'],
        'sharedInterest',
      );
      expect(
        byAction[BehaviorAction.addContact]!.toJson()['intersectionTagRefs'],
        <String>['tag/location/chengdu'],
      );
    },
  );

  group('交集负反馈归因（F 推荐差异化 · UAT-7）', () {
    test(
      '合法 feedbackKind：上报 intersection_feedback 携带 subjectId + feedbackKind + 漏斗归因',
      () async {
        tracker.trackIntersectionFeedback(
          'u_lin',
          feedbackKind: 'notInterested',
          intersectionId: 'ix_rel_a',
          intersectionDimension: 'relationship',
          intersectionClass: 'affinity',
          intersectionSourceRef: 'sharedFollowees',
        );
        await tracker.flush();

        expect(repo.recorded, hasLength(1));
        final event = repo.recorded.single;
        expect(event.action, BehaviorAction.intersectionFeedback);
        expect(event.action.wireValue, 'intersection_feedback');
        final json = event.toJson();
        // 不绑定 post：subjectId 承载对象。
        expect(json['subjectId'], 'u_lin');
        expect(json['feedbackKind'], 'notInterested');
        expect(json['state'], 'negative');
        // 与曝光/点击同一漏斗归因键，负反馈可按维度 / kind / 类别下钻。
        expect(json['intersectionId'], 'ix_rel_a');
        expect(json['intersectionDimension'], 'relationship');
        expect(json['intersectionClass'], 'affinity');
        expect(json['intersectionSourceRef'], 'sharedFollowees');
      },
    );

    test('端云同源闭集：registry.feedbackKinds 全部可上报', () async {
      for (final kind in intersectionFeedbackKinds) {
        tracker.trackIntersectionFeedback('subj_$kind', feedbackKind: kind);
      }
      await tracker.flush();

      final reported = repo.recorded
          .where((e) => e.action == BehaviorAction.intersectionFeedback)
          .map((e) => e.feedbackKind)
          .toSet();
      expect(reported, intersectionFeedbackKinds.toSet());
    });

    test('非法 feedbackKind（闭集外）直接丢弃，不上报脏信号', () async {
      tracker.trackIntersectionFeedback('u_lin', feedbackKind: 'bogus_kind');
      tracker.trackIntersectionFeedback('u_lin', feedbackKind: '');
      await tracker.flush();

      expect(
        repo.recorded.where(
          (e) => e.action == BehaviorAction.intersectionFeedback,
        ),
        isEmpty,
      );
    });

    test('空 subjectId 丢弃（subject 是负反馈冷却主键，缺失即无效）', () async {
      tracker.trackIntersectionFeedback('  ', feedbackKind: 'dismiss');
      await tracker.flush();

      expect(
        repo.recorded.where(
          (e) => e.action == BehaviorAction.intersectionFeedback,
        ),
        isEmpty,
      );
    });
  });
}
