import 'dart:async';

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

/// App 自有页面的唯一方向写入口；媒体局部旋转不参与此策略。
/// 请求完成不证明设备已锁定，平板多任务与大屏限制仍由平台决定。
final class MediaOrientationPolicy extends WidgetsBindingObserver {
  MediaOrientationPolicy({
    Future<void> Function(List<DeviceOrientation>)? apply,
  }) : _apply = apply ?? SystemChrome.setPreferredOrientations;

  static final instance = MediaOrientationPolicy();
  static const _portraitUp = [DeviceOrientation.portraitUp];
  static const _budget = Duration(seconds: 2);

  final Future<void> Function(List<DeviceOrientation>) _apply;

  /// 重入无需排队：每次及迟到完成都只能写同一不可变方向，不存在解锁补偿。
  Future<void> enforcePortraitUp() async {
    await _apply(_portraitUp).timeout(_budget);
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      unawaited(_enforceAfterResume());
    }
  }

  Future<void> _enforceAfterResume() async {
    try {
      await enforcePortraitUp();
    } catch (error, stack) {
      FlutterError.reportError(
        FlutterErrorDetails(
          exception: error,
          stack: stack,
          library: 'runtime_orientation',
          context: ErrorDescription('恢复 App 正向竖屏策略时'),
        ),
      );
    }
  }
}
