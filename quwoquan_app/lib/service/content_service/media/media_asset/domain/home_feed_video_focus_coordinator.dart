import 'package:flutter/foundation.dart';

/// 单活跃视频粘滞阈值：当前活跃卡片的可见度只要不低于「最佳候选可见度 −
/// 该阈值」，就保持活跃，避免相近可见度时在两张卡片间来回抖动切换解码器。
const double kHomeFeedVideoFocusHysteresis = 0.08;

/// 首页瀑布流「单活跃视频」协调器。
///
/// 瀑布流可滚动浏览数百甚至上千条；若每张视频卡片各自独立初始化解码器，
/// 多列布局或快速滚动时会有多个 [VideoPlayerController]/AVPlayer 同时存活，
/// 触达 iOS 硬件解码器配额与内存上限，出现卡顿甚至无法播放。
///
/// 该协调器在整个 feed 范围内做单点仲裁：任意时刻至多授予**一张**卡片
/// 「活跃」资格去初始化/播放，其余卡片即使短暂可见也不初始化、并释放已有
/// 控制器。这样活跃解码器数恒定 ≤1，与 feed 长度无关，内存可被稳定回收。
///
/// 行为约定：
/// - 卡片可见且本地满足初始化条件时调用 [report]，附带当前可见比例；
/// - 卡片不再满足（滚出 / 释放 / dispose）时调用 [withdraw]；
/// - [activeId] 为当前唯一活跃卡片 id，可见度最高者胜出，并带粘滞避免抖动；
/// - [activeId] 变化时 [notifyListeners]，订阅卡片据此切换 initialize/autoPlay。
class HomeFeedVideoFocusCoordinator extends ChangeNotifier {
  HomeFeedVideoFocusCoordinator({
    this.hysteresis = kHomeFeedVideoFocusHysteresis,
  });

  final double hysteresis;
  final Map<String, double> _candidates = <String, double>{};
  String? _activeId;

  /// 当前唯一活跃视频 id；无候选时为 null。
  String? get activeId => _activeId;

  /// 当前存活候选数量（用于诊断/测试观测，非渲染消费）。
  @visibleForTesting
  int get candidateCount => _candidates.length;

  bool isActive(String id) => id.isNotEmpty && _activeId == id;

  /// 卡片申报「希望成为活跃视频」，附带当前可见比例 [visibleFraction]。
  void report(String id, double visibleFraction) {
    if (id.isEmpty) {
      return;
    }
    final previous = _candidates[id];
    if (previous != null && previous == visibleFraction) {
      return;
    }
    _candidates[id] = visibleFraction;
    _recompute();
  }

  /// 卡片让出资格（滚出可视区 / 不再初始化 / dispose）。
  void withdraw(String id) {
    if (_candidates.remove(id) != null) {
      _recompute();
    }
  }

  void _recompute() {
    String? best;
    var bestFraction = double.negativeInfinity;
    _candidates.forEach((id, fraction) {
      final wins =
          fraction > bestFraction ||
          // 可见度相等时用 id 字典序定序，保证仲裁确定、无抖动。
          (fraction == bestFraction &&
              (best == null || id.compareTo(best!) < 0));
      if (wins) {
        bestFraction = fraction;
        best = id;
      }
    });

    // 粘滞：当前活跃卡片仍在候选内且与最佳候选差距不超过阈值时保持活跃，
    // 避免两张可见度相近的卡片之间反复抢占、反复重建解码器。
    final current = _activeId;
    if (current != null &&
        best != current &&
        _candidates.containsKey(current)) {
      final currentFraction = _candidates[current] ?? double.negativeInfinity;
      if (currentFraction >= bestFraction - hysteresis) {
        best = current;
      }
    }

    if (best != _activeId) {
      _activeId = best;
      notifyListeners();
    }
  }
}
