import 'package:quwoquan_app/cloud/runtime/generated/ops/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_context_provider.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_reporter.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

enum AppPageUsableTerminal { content, empty, error }

final class _PageExperienceVisit {
  _PageExperienceVisit({
    required this.pageName,
    required this.pageVisitId,
    required this.openedAt,
  });

  final String pageName;
  final String pageVisitId;
  final DateTime openedAt;
  bool firstUsableRecorded = false;
}

/// 页面首个可用终态、阻塞错误恢复和 ANR 产品事实的唯一 App 端投影器。
///
/// 路由层只负责开始/结束 visit；页面与统一错误面只提交明确终态。所有 wire
/// eventType 和扩展字段均来自 metadata codegen，不在 Widget 内复制事件目录。
final class AppPageExperienceTracker {
  AppPageExperienceTracker({
    AppPageContextStore? pageContextStore,
    DateTime Function()? now,
    this._anrDedupeWindow = const Duration(seconds: 10),
  }) : _pageContextStore = pageContextStore ?? AppPageContextStore.instance,
       _now = now ?? DateTime.now;

  static final AppPageExperienceTracker instance = AppPageExperienceTracker();

  final AppPageContextStore _pageContextStore;
  final DateTime Function() _now;
  final Duration _anrDedupeWindow;
  final List<_PageExperienceVisit> _visits = <_PageExperienceVisit>[];
  final Map<String, DateTime> _lastAnrBySource = <String, DateTime>{};
  AppTelemetryRecorder? _reporter;

  void attachReporter(AppTelemetryRecorder reporter) {
    _reporter = reporter;
  }

  void detachReporter(AppTelemetryRecorder reporter) {
    if (identical(_reporter, reporter)) {
      _reporter = null;
    }
  }

  void beginPageVisit({
    required String pageName,
    required String pageVisitId,
    required DateTime openedAt,
    AppTelemetryRecorder? reporter,
  }) {
    final normalizedPage = pageName.trim();
    final normalizedVisit = pageVisitId.trim();
    if (normalizedPage.isEmpty || normalizedVisit.isEmpty) {
      return;
    }
    if (reporter != null) {
      attachReporter(reporter);
    }
    _visits.removeWhere((visit) => visit.pageVisitId == normalizedVisit);
    _visits.add(
      _PageExperienceVisit(
        pageName: normalizedPage,
        pageVisitId: normalizedVisit,
        openedAt: openedAt,
      ),
    );
  }

  void endPageVisit(String pageVisitId) {
    final normalized = pageVisitId.trim();
    if (normalized.isEmpty) {
      return;
    }
    _visits.removeWhere((visit) => visit.pageVisitId == normalized);
  }

  Future<AppTelemetryRecordResult> recordFirstUsable({
    required AppPageUsableTerminal terminal,
    String? pageName,
    String? surfaceId,
    String? failReasonCode,
  }) async {
    final resolvedPage = (pageName ?? _pageContextStore.pageName).trim();
    final visit = _activeVisitFor(resolvedPage);
    final reporter = _reporter;
    if (visit == null || visit.firstUsableRecorded || reporter == null) {
      return AppTelemetryRecordResult.rejected;
    }
    visit.firstUsableRecorded = true;
    final durationMs = _nonNegativeDurationMs(visit.openedAt, _now());
    return _recordSafely(
      reporter,
      AppTelemetryPayload.pageFirstUsable(
        durationMs: durationMs,
        terminalState: terminal.name,
        surfaceId: _nonEmpty(surfaceId),
        failReasonCode: _nonEmpty(failReasonCode),
      ),
      pageName: visit.pageName,
    );
  }

  /// 只接受已冻结的页面生命周期终态；任意自定义 phase 不会被猜测为可用。
  Future<AppTelemetryRecordResult> recordLifecycleTerminal({
    required String pageName,
    required String phase,
    String? surfaceId,
    String? failReasonCode,
  }) {
    final terminal = switch (phase) {
      'onlineSuccess' ||
      'contentReady' ||
      'cacheFallback' ||
      'partial' => AppPageUsableTerminal.content,
      'emptyState' || 'emptySuccess' => AppPageUsableTerminal.empty,
      'blockingFailure' => AppPageUsableTerminal.error,
      _ => null,
    };
    if (terminal == null) {
      return Future<AppTelemetryRecordResult>.value(
        AppTelemetryRecordResult.rejected,
      );
    }
    return recordFirstUsable(
      terminal: terminal,
      pageName: pageName,
      surfaceId: surfaceId,
      failReasonCode: failReasonCode,
    );
  }

  /// [errorCode] 必须来自实际失败对象的 canonical errors 契约；缺失时拒绝记录，
  /// 观测层不得发明“未分类失败”替代领域事实。
  Future<AppTelemetryRecordResult> recordPageErrorOutcome({
    required String result,
    required String? errorCode,
    String? surfaceId,
    String? recoveryAction,
    String? action,
    int? durationMs,
  }) {
    final reporter = _reporter;
    final normalizedErrorCode = _nonEmpty(errorCode);
    if (reporter == null || normalizedErrorCode == null) {
      return Future<AppTelemetryRecordResult>.value(
        AppTelemetryRecordResult.rejected,
      );
    }
    final pageName = _pageContextStore.pageName;
    return _recordSafely(
      reporter,
      AppTelemetryPayload.pageErrorOutcome(
        surfaceId: _nonEmpty(surfaceId) ?? pageName,
        errorCode: normalizedErrorCode,
        recoveryAction:
            _nonEmpty(recoveryAction) ?? RuntimeRecoveryAction.absorb.name,
        result: result,
        action: _nonEmpty(action),
        durationMs: durationMs == null ? null : _nonNegative(durationMs),
      ),
      pageName: pageName,
    );
  }

  Future<AppTelemetryRecordResult> recordAnrOutcome({
    required String detectionSource,
    required String result,
    int? durationMs,
    DateTime? occurredAt,
  }) {
    final reporter = _reporter;
    if (reporter == null) {
      return Future<AppTelemetryRecordResult>.value(
        AppTelemetryRecordResult.rejected,
      );
    }
    final eventAt = occurredAt ?? _now();
    final previous = _lastAnrBySource[detectionSource];
    if (previous != null &&
        eventAt.difference(previous).abs() < _anrDedupeWindow) {
      return Future<AppTelemetryRecordResult>.value(
        AppTelemetryRecordResult.rejected,
      );
    }
    _lastAnrBySource[detectionSource] = eventAt;
    return _recordSafely(
      reporter,
      AppTelemetryPayload.appAnrOutcome(
        detectionSource: detectionSource,
        result: result,
        durationMs: durationMs == null ? null : _nonNegative(durationMs),
      ),
      pageName: _pageContextStore.pageName,
      occurredAt: eventAt,
    );
  }

  Future<AppTelemetryRecordResult> recordFrameJankOutcome({
    required int sampledFrames,
    required int jankyFrames,
    required int worstFrameMs,
    required int jankThresholdMs,
    required String result,
    DateTime? occurredAt,
  }) {
    final reporter = _reporter;
    if (reporter == null || sampledFrames <= 0 || jankyFrames < 0) {
      return Future<AppTelemetryRecordResult>.value(
        AppTelemetryRecordResult.rejected,
      );
    }
    return _recordSafely(
      reporter,
      AppTelemetryPayload.appFrameJankOutcome(
        sampledFrames: sampledFrames,
        jankyFrames: jankyFrames,
        worstFrameMs: _nonNegative(worstFrameMs),
        jankThresholdMs: jankThresholdMs <= 0 ? 1 : jankThresholdMs,
        result: result,
      ),
      pageName: _pageContextStore.pageName,
      occurredAt: occurredAt ?? _now(),
    );
  }

  Future<AppTelemetryRecordResult> _recordSafely(
    AppTelemetryRecorder reporter,
    AppTelemetryPayload payload, {
    required String pageName,
    DateTime? occurredAt,
  }) async {
    try {
      return await reporter.record(
        payload,
        pageName: pageName,
        occurredAt: occurredAt,
      );
    } on Object {
      // 观测持久化失败不能打断页面可用、错误恢复或平台诊断主流程。
      return AppTelemetryRecordResult.rejected;
    }
  }

  _PageExperienceVisit? _activeVisitFor(String pageName) {
    for (var index = _visits.length - 1; index >= 0; index -= 1) {
      final visit = _visits[index];
      if (visit.pageName == pageName) {
        return visit;
      }
    }
    return null;
  }

  int _nonNegativeDurationMs(DateTime startedAt, DateTime completedAt) {
    return _nonNegative(completedAt.difference(startedAt).inMilliseconds);
  }

  int _nonNegative(int value) => value < 0 ? 0 : value;

  String? _nonEmpty(String? value) {
    final normalized = value?.trim() ?? '';
    return normalized.isEmpty ? null : normalized;
  }
}
