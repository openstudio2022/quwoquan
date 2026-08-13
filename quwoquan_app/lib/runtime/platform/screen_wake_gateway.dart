import 'dart:async';

import 'package:quwoquan_app/runtime/observability/app_exception_telemetry_service.dart';
import 'package:wakelock_plus/wakelock_plus.dart';

/// 屏幕常亮防腐层：业务只表达「保持常亮 / 释放」，平台实现与失败降级在此收口。
///
/// 屏幕常亮是纯体验增强能力：任何平台失败都不得打断通话主流程（R-XP5
/// 缺失即一致降级），因此实现内部吞掉平台异常并只留观测日志。
abstract interface class ScreenWakeGateway {
  /// 保持屏幕常亮（幂等）。
  Future<void> acquire();

  /// 释放常亮（幂等；未曾 acquire 时调用也安全）。
  Future<void> release();
}

/// wakelock_plus 实现（Android/iOS/Web/desktop）。
final class WakelockScreenWakeGateway implements ScreenWakeGateway {
  const WakelockScreenWakeGateway();

  @override
  Future<void> acquire() async {
    try {
      await WakelockPlus.enable();
    } catch (error, stackTrace) {
      // 常亮失败不打断通话主流程，但降级事实必须结构化上报（自带去重）。
      unawaited(
        AppExceptionTelemetryService.instance.recordHandledException(
          source: 'platform.screen_wake.acquire',
          error: error,
          stackTrace: stackTrace,
        ),
      );
    }
  }

  @override
  Future<void> release() async {
    try {
      await WakelockPlus.disable();
    } catch (error, stackTrace) {
      unawaited(
        AppExceptionTelemetryService.instance.recordHandledException(
          source: 'platform.screen_wake.release',
          error: error,
          stackTrace: stackTrace,
        ),
      );
    }
  }
}

/// 能力缺失平台的一致降级实现：结构化 no-op，不 crash。
final class UnsupportedScreenWakeGateway implements ScreenWakeGateway {
  const UnsupportedScreenWakeGateway();

  @override
  Future<void> acquire() async {}

  @override
  Future<void> release() async {}
}
