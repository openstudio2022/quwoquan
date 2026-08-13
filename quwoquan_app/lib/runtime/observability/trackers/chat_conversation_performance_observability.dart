import 'dart:async';

import 'package:quwoquan_app/runtime/observability/generated/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_telemetry_reporter.dart';

/// 会话首屏性能 operationId；wire eventType 由 product-ops codegen 拥有。
class ChatConversationPerformanceMetricNames {
  static const String firstScreenTtiMs = 'chat_conversation_first_screen_tti_ms';

  const ChatConversationPerformanceMetricNames._();
}

/// 会话首屏可用的 typed 产品观测（复用首页 feed 的 requested→ready 模式）。
///
/// 调用方只能提交 codegen 生成的 payload；全局帧分母由
/// `AppRuntimeDiagnostics` 唯一生产，本类不建立第二条 jank 采样轨。
/// 同一会话一次打开只上报一次首屏采样。
class ChatConversationPerformanceObservability {
  ChatConversationPerformanceObservability({
    required AppTelemetryRecorder telemetry,
  }) : _telemetry = telemetry; // ignore: prefer_initializing_formals

  final AppTelemetryRecorder _telemetry;
  final Map<String, Stopwatch> _firstScreenTimers = <String, Stopwatch>{};
  final Set<String> _firstScreenReported = <String>{};

  void markConversationOpened(String conversationId) {
    final id = conversationId.trim();
    if (id.isEmpty || _firstScreenReported.contains(id)) return;
    _firstScreenTimers.putIfAbsent(id, () => Stopwatch()..start());
  }

  void markFirstTimelineReady(
    String conversationId, {
    required int messageCount,
  }) {
    final id = conversationId.trim();
    if (id.isEmpty || messageCount < 0 || _firstScreenReported.contains(id)) {
      return;
    }
    final timer = _firstScreenTimers.remove(id);
    if (timer == null) return;
    timer.stop();
    _firstScreenReported.add(id);
    unawaited(
      _telemetry.record(
        AppTelemetryPayload.performanceSample(
          operationId: ChatConversationPerformanceMetricNames.firstScreenTtiMs,
          durationMs: timer.elapsedMilliseconds,
          result: 'ok',
        ),
      ),
    );
  }

  /// 离开会话后允许下次打开重新计时上报。
  void resetConversation(String conversationId) {
    final id = conversationId.trim();
    if (id.isEmpty) return;
    _firstScreenTimers.remove(id);
    _firstScreenReported.remove(id);
  }
}
