import 'dart:async';
import 'dart:collection';

import 'package:flutter/foundation.dart';

/// 首页曝光门控的共享采样时钟。
///
/// 所有已挂载卡片共用一个周期 Timer，避免长列表为每张卡分别创建定时器。
class HomeFeedImpressionSamplingClock {
  HomeFeedImpressionSamplingClock({
    this.interval = const Duration(milliseconds: 250),
  }) : assert(interval > Duration.zero);

  static final HomeFeedImpressionSamplingClock shared =
      HomeFeedImpressionSamplingClock();

  final Duration interval;
  final LinkedHashSet<VoidCallback> _listeners =
      LinkedHashSet<VoidCallback>.identity();
  Timer? _timer;

  @visibleForTesting
  int get listenerCount => _listeners.length;

  @visibleForTesting
  bool get isRunning => _timer?.isActive ?? false;

  void addListener(VoidCallback listener) {
    if (!_listeners.add(listener)) {
      return;
    }
    _timer ??= Timer.periodic(interval, (_) => _notifyListeners());
  }

  void removeListener(VoidCallback listener) {
    _listeners.remove(listener);
    if (_listeners.isNotEmpty) {
      return;
    }
    _timer?.cancel();
    _timer = null;
  }

  void _notifyListeners() {
    for (final listener in List<VoidCallback>.of(_listeners)) {
      if (_listeners.contains(listener)) {
        listener();
      }
    }
  }
}
