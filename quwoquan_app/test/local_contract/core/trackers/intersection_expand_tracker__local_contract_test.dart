import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';

/// W4 归因链补全（B6）：intersection_expand 端侧执行链契约。
/// behaviors.yaml 弱正信号 0.2 + 云侧 SignalWeights 已登记；本测试锁定端侧
/// tracker 产出的事件形状（action/state/归因字段），防止执行链再次断裂。
class _CaptureReporter implements BehaviorReporter {
  final List<BehaviorEvent> events = <BehaviorEvent>[];

  @override
  Future<void> reportEvents({required List<BehaviorEvent> events}) async {
    this.events.addAll(events);
  }
}

void main() {
  test('trackIntersectionExpand 产出 intersection_expand 弱正信号事件', () async {
    final reporter = _CaptureReporter();
    final tracker = ContentBehaviorTracker(
      reporter: reporter,
      enablePeriodicFlush: false,
    );

    tracker.trackIntersectionExpand(
      contentId: 'homepage_dali',
      intersectionId: 'ix_001',
      intersectionDimension: 'entity',
      intersectionClass: 'fact',
      intersectionSourceRef: 'coVisitedEntity',
      referralSource: ReferralSource.entityPage,
    );
    await tracker.flush();

    expect(reporter.events, hasLength(1));
    final event = reporter.events.single;
    expect(event.action, BehaviorEventType.intersectionExpand);
    expect(event.state, 'interaction');
    expect(event.contentId, 'homepage_dali');
    expect(event.intersectionId, 'ix_001');
    expect(event.intersectionDimension, 'entity');
    expect(event.intersectionClass, 'fact');
    expect(event.intersectionSourceRef, 'coVisitedEntity');
    expect(event.referralSource, ReferralSource.entityPage);
  });

  test('intersection_expand 的 wire action 与 behaviors.yaml 对齐', () {
    expect(
      BehaviorEventType.intersectionExpand.wireName,
      'intersection_expand',
      reason: '端云 action 单轨：与 behaviors.yaml type 及云侧 SignalWeights 键一致',
    );
  });
}
