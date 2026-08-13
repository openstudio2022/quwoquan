import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/di/ops_event_dependencies.dart';
import 'package:quwoquan_app/runtime/observability/trackers/chat_conversation_performance_observability.dart';

/// 会话首屏性能观测的 production 组合；纯观测实现不依赖 App 依赖图。
final chatConversationPerformanceObservabilityProvider =
    Provider<ChatConversationPerformanceObservability>((ref) {
      return ChatConversationPerformanceObservability(
        telemetry: ref.read(appTelemetryReporterProvider),
      );
    });
