import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

final class RuntimeFailureTelemetryDimensions {
  const RuntimeFailureTelemetryDimensions({
    this.sourceCode = '',
    this.failureKind = '',
    this.recoveryAction = '',
    this.disruptionLevel = '',
    this.requestId = '',
    this.traceId = '',
  });

  factory RuntimeFailureTelemetryDimensions.from(Object? error) {
    if (error == null) {
      return const RuntimeFailureTelemetryDimensions();
    }
    final failure = switch (error) {
      CloudException value => value.runtimeFailure,
      RuntimeFailureBase value => value,
      _ => null,
    };
    final attributes = <String, String>{
      for (final attribute
          in failure?.context.attributes ?? const <RuntimeContextAttribute>[])
        attribute.key.trim(): attribute.value.trim(),
    };
    final cloudRequestId = error is CloudException
        ? (error.requestId ?? '').trim()
        : '';
    final cloudTraceId = error is CloudException
        ? (error.traceId ?? '').trim()
        : '';
    final uiRecoveryAction = error is UiErrorSemantic
        ? error.recoveryAction?.name ?? ''
        : '';

    return RuntimeFailureTelemetryDimensions(
      sourceCode: switch (error) {
        CloudException value when (value.code ?? '').trim().isNotEmpty =>
          value.code!.trim(),
        UiErrorSemantic value when (value.sourceCode ?? '').trim().isNotEmpty =>
          value.sourceCode!.trim(),
        _ => failure?.code.trim() ?? '',
      },
      failureKind: switch (error) {
        UiErrorSemantic value => value.failureKind?.name ?? '',
        _ => failure?.kind.name ?? '',
      },
      recoveryAction: uiRecoveryAction.isNotEmpty
          ? uiRecoveryAction
          : failure?.recovery.action.trim() ?? '',
      disruptionLevel: failure?.recovery.disruptionLevel.trim() ?? '',
      requestId: cloudRequestId.isNotEmpty
          ? cloudRequestId
          : attributes['requestId'] ?? '',
      traceId: cloudTraceId.isNotEmpty
          ? cloudTraceId
          : attributes['traceId'] ?? '',
    );
  }

  final String sourceCode;
  final String failureKind;
  final String recoveryAction;
  final String disruptionLevel;
  final String requestId;
  final String traceId;
}
