import 'package:quwoquan_app/runtime/observability/startup/startup_telemetry.dart';
import 'package:quwoquan_cloud_contracts/generated/ops_contracts.dart'
    as ops_contracts;
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef StartupTelemetryInvocationContextFactory =
    CloudOperationInvocationContext Function({required bool recoveryBatch});

/// 匿名启动遥测的 generated-client Remote adapter。
///
/// proof 的 header 位置、body、path、重试和 response decoder 全部由
/// ReportStartupEventBatch canonical operation 生成；此处只映射 App 本地 journal
/// 模型与业务 ACK。
final class RemoteStartupTelemetryTransport
    implements StartupTelemetryTransport {
  const RemoteStartupTelemetryTransport({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final StartupTelemetryInvocationContextFactory invocationContext;

  @override
  Future<StartupTelemetryBatchAck> report(
    List<StartupTelemetryEvent> events, {
    required String proof,
  }) async {
    if (events.isEmpty) {
      return const StartupTelemetryBatchAck(
        acceptedCount: 0,
        duplicateCount: 0,
      );
    }
    final recoveryBatch = events.first.isRecoveryTelemetry;
    if (events.any((event) => event.isRecoveryTelemetry != recoveryBatch)) {
      throw StateError('startup and recovery telemetry cannot share a batch');
    }
    final receipt = await client.opsEventRecordReportStartupEventBatch(
      ops_contracts.ReportStartupEventBatchCommand(
        proof: proof.trim(),
        events: events.map(_eventWire).toList(growable: false),
      ),
      context: invocationContext(recoveryBatch: recoveryBatch),
    );
    return StartupTelemetryBatchAck(
      acceptedCount: receipt.duplicateBatch ? 0 : receipt.acceptedCount,
      duplicateCount: receipt.duplicateBatch ? receipt.acceptedCount : 0,
    );
  }
}

ops_contracts.StartupTelemetryEventWire _eventWire(
  StartupTelemetryEvent event,
) {
  return ops_contracts.StartupTelemetryEventWire(
    eventId: event.eventId,
    attemptId: event.attemptId,
    sequence: event.sequence,
    phase: event.phase.wireName,
    phaseDurationMs: event.phaseDurationMs,
    elapsedMs: event.elapsedMs,
    outcome: event.outcome,
    occurredAt: event.occurredAt,
    platform: event.platform,
    runtimeEnv: event.runtimeEnv,
    appVersion: event.appVersion.isEmpty ? null : event.appVersion,
    networkClass: event.networkClass.isEmpty ? null : event.networkClass,
    recoverySurface: event.recoverySurface,
    recoveryLifecycle: event.recoveryLifecycle,
    recoveryMount: event.recoveryMount,
    recoveryPhase: event.recoveryPhase,
    recoveryAction: event.recoveryAction,
    failureCode: event.failureCode.isEmpty ? null : event.failureCode,
    failureSource: event.failureSource.isEmpty ? null : event.failureSource,
    deadlineOrigin: event.deadlineOrigin.isEmpty ? null : event.deadlineOrigin,
  );
}
