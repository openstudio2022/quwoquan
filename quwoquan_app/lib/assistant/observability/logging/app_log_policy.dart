import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_log_models.dart';

/// 商用策略：成功摘要、失败全量，并支持按 session/run 动态提级。
class AppLogPolicy {
  AppLogPolicy({bool? isRelease, this.successSampleRate = 0.2})
    : _isRelease = isRelease ?? kReleaseMode;

  final bool _isRelease;
  final double successSampleRate;
  final Set<String> _boostedSessionIds = <String>{};
  final Set<String> _boostedRunIds = <String>{};

  bool get isRelease => _isRelease;
  bool get isDebug => !_isRelease;

  void boostSession(String sessionId) {
    final id = sessionId.trim();
    if (id.isNotEmpty) {
      _boostedSessionIds.add(id);
    }
  }

  void boostRun(String runId) {
    final id = runId.trim();
    if (id.isNotEmpty) {
      _boostedRunIds.add(id);
    }
  }

  void clearBoosts() {
    _boostedSessionIds.clear();
    _boostedRunIds.clear();
  }

  bool shouldIncludeFullPayload({
    required String sessionId,
    required String runId,
    required bool hasError,
    required AppLogType type,
  }) {
    if (isDebug) {
      return true;
    }
    if (hasError || type == AppLogType.error) {
      return true;
    }
    if (_boostedSessionIds.contains(sessionId) ||
        _boostedRunIds.contains(runId)) {
      return true;
    }
    return false;
  }

  bool shouldEmitSuccessLog({
    required String sessionId,
    required String runId,
    required AppLogType type,
  }) {
    if (isDebug) {
      return true;
    }
    if (_boostedSessionIds.contains(sessionId) ||
        _boostedRunIds.contains(runId)) {
      return true;
    }
    if (type == AppLogType.error) {
      return true;
    }
    final clamped = successSampleRate.clamp(0.0, 1.0);
    if (clamped >= 1.0) {
      return true;
    }
    final seed = Object.hash(sessionId, runId, type.value).abs() % 1000;
    return seed / 1000.0 < clamped;
  }
}
