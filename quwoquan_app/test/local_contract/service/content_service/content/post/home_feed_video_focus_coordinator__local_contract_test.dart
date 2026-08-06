import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/home_feed_video_focus_coordinator.dart';

void main() {
  group('HomeFeedVideoFocusCoordinator 单活跃视频不变量', () {
    test('初始无候选时无活跃视频', () {
      final coordinator = HomeFeedVideoFocusCoordinator();
      expect(coordinator.activeId, isNull);
      expect(coordinator.isActive('a'), isFalse);
      expect(coordinator.candidateCount, 0);
    });

    test('单候选申报后成为唯一活跃', () {
      final coordinator = HomeFeedVideoFocusCoordinator();
      coordinator.report('a', 0.9);
      expect(coordinator.activeId, 'a');
      expect(coordinator.isActive('a'), isTrue);
    });

    test('多候选同时可见时仅可见度最高者活跃（硬性 ≤1 解码器）', () {
      final coordinator = HomeFeedVideoFocusCoordinator();
      coordinator.report('a', 0.40);
      coordinator.report('b', 0.85);
      coordinator.report('c', 0.60);
      expect(coordinator.activeId, 'b');
      expect(coordinator.isActive('a'), isFalse);
      expect(coordinator.isActive('b'), isTrue);
      expect(coordinator.isActive('c'), isFalse);
      // 任意时刻活跃集合大小恒为 1。
      final activeCount = ['a', 'b', 'c'].where(coordinator.isActive).length;
      expect(activeCount, 1);
    });

    test('另一候选显著超过粘滞阈值时切换活跃（滚动焦点交接）', () {
      final coordinator = HomeFeedVideoFocusCoordinator(hysteresis: 0.08);
      coordinator.report('a', 0.80);
      expect(coordinator.activeId, 'a');
      // b 比 a 高出超过 hysteresis(0.08) → 交接。
      coordinator.report('b', 0.95);
      expect(coordinator.activeId, 'b');
    });

    test('可见度相近（粘滞阈值内）时不抖动切换', () {
      final coordinator = HomeFeedVideoFocusCoordinator(hysteresis: 0.08);
      coordinator.report('a', 0.80);
      expect(coordinator.activeId, 'a');
      // b 仅略高，差距 < hysteresis → 维持当前活跃 a，避免反复重建解码器。
      coordinator.report('b', 0.84);
      expect(coordinator.activeId, 'a');
    });

    test('活跃卡片让出资格后交接给次高候选', () {
      final coordinator = HomeFeedVideoFocusCoordinator();
      coordinator.report('a', 0.90);
      coordinator.report('b', 0.50);
      expect(coordinator.activeId, 'a');
      coordinator.withdraw('a');
      expect(coordinator.activeId, 'b');
      coordinator.withdraw('b');
      expect(coordinator.activeId, isNull);
    });

    test('activeId 未变化时不重复通知监听者', () {
      final coordinator = HomeFeedVideoFocusCoordinator(hysteresis: 0.08);
      var notifications = 0;
      coordinator.addListener(() => notifications++);
      coordinator.report('a', 0.80); // null -> a：通知 1 次
      coordinator.report('a', 0.82); // 活跃仍是 a：不通知
      coordinator.report('b', 0.83); // 差距 < hysteresis，活跃仍 a：不通知
      expect(coordinator.activeId, 'a');
      expect(notifications, 1);
      coordinator.report('b', 0.95); // 交接到 b：通知 1 次
      expect(coordinator.activeId, 'b');
      expect(notifications, 2);
    });

    test('空 id 申报被忽略', () {
      final coordinator = HomeFeedVideoFocusCoordinator();
      coordinator.report('', 0.99);
      expect(coordinator.activeId, isNull);
      expect(coordinator.candidateCount, 0);
      expect(coordinator.isActive(''), isFalse);
    });
  });
}
