import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/di/ops_event_dependencies.dart';
import 'package:quwoquan_app/runtime/observability/trackers/feed_performance_observability.dart';

/// 首页性能观测的 production 组合；纯观测实现不依赖 App 依赖图。
final feedPerformanceObservabilityProvider =
    Provider<FeedPerformanceObservability>((ref) {
      return FeedPerformanceObservability(
        telemetry: ref.read(appTelemetryReporterProvider),
      );
    });
