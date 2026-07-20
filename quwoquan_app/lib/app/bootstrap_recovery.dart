import 'dart:async';

import 'package:flutter/material.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/ops_event_record_errors.g.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/error_states/app_error_states.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

/// `runApp` 前失败的最小、无远端依赖恢复边界。
///
/// 该边界只能消费已由 metadata 生成的稳定错误码，不能显示原始异常或堆栈。
final class BootstrapFailure {
  const BootstrapFailure._({
    required this.errorCode,
    required this.runtimeFailure,
  });

  final OpsEventRecordErrorCode errorCode;
  final RuntimeFailureBase runtimeFailure;

  factory BootstrapFailure.fromError(Object error) {
    final errorCode = error is CloudRuntimeConfigurationException
        ? OpsEventRecordErrorCode.startupConfigurationInvalid
        : OpsEventRecordErrorCode.startupInitializationFailed;
    return BootstrapFailure._fromCode(
      errorCode,
      error,
      invalidKeys: error is CloudRuntimeConfigurationException
          ? error.invalidKeys
          : const <String>[],
      failureSource: error is CloudRuntimeConfigurationException
          ? error.source
          : 'bootstrap',
    );
  }

  factory BootstrapFailure.router(Object error) {
    return BootstrapFailure._fromCode(
      OpsEventRecordErrorCode.startupRouterUnavailable,
      error,
    );
  }

  factory BootstrapFailure.deadline() {
    return BootstrapFailure._fromCode(
      OpsEventRecordErrorCode.startupRouterUnavailable,
      TimeoutException('startup deadline elapsed'),
    );
  }

  factory BootstrapFailure.fromRuntimeFailure(RuntimeFailureBase failure) {
    final errorCode =
        failure.code == OpsEventRecordErrorCode.startupConfigurationInvalid.code
        ? OpsEventRecordErrorCode.startupConfigurationInvalid
        : failure.code ==
              OpsEventRecordErrorCode.startupInitializationFailed.code
        ? OpsEventRecordErrorCode.startupInitializationFailed
        : OpsEventRecordErrorCode.startupRouterUnavailable;
    return BootstrapFailure._(errorCode: errorCode, runtimeFailure: failure);
  }

  factory BootstrapFailure._fromCode(
    OpsEventRecordErrorCode errorCode,
    Object error, {
    Iterable<String> invalidKeys = const <String>[],
    String failureSource = 'bootstrap',
  }) {
    final attributes = <RuntimeContextAttribute>[
      RuntimeContextAttribute(
        key: 'failureType',
        value: error.runtimeType.toString(),
      ),
      RuntimeContextAttribute(key: 'failureSource', value: failureSource),
      if (invalidKeys.isNotEmpty)
        RuntimeContextAttribute(
          key: 'invalidDefineKeys',
          value: invalidKeys.join(','),
        ),
    ];
    return BootstrapFailure._(
      errorCode: errorCode,
      runtimeFailure: RuntimeFailure(
        code: errorCode.code,
        semanticReason: errorCode.name,
        transportStatus: errorCode.httpStatus,
        origin: RuntimeFailureOrigin.localClient,
        kind: RuntimeFailureKind.unavailable,
        nature: RuntimeFailureNature.transient,
        location: const RuntimeFailureLocation(
          businessObject: 'runtime.startup',
          functionModule: 'bootstrap',
        ),
        context: RuntimeFailureContext(attributes: attributes),
        recovery: const RuntimeRecoveryDirective(
          action: 'retry',
          disruptionLevel: 'fullPage',
        ),
      ),
    );
  }
}

/// 故障根只使用 Material、结构化语义与本地文案，故可在未装配 Cloud/Router 时显示。
class BootstrapRecoveryApp extends StatelessWidget {
  const BootstrapRecoveryApp({
    super.key,
    required this.failure,
    required this.onRetry,
  });

  final BootstrapFailure failure;
  final Future<void> Function() onRetry;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: UITextConstants.welcomeTitle,
      home: AppScaffold(
        body: AppPageErrorState(
          semantic: UiErrorSemantic(
            category: UiErrorCategory.pageLoad,
            scope: UiErrorScope.global,
            title: UITextConstants.startupRecoveryTitle,
            message: failure.errorCode.defaultMessage,
            secondaryMessage: UITextConstants.startupRecoverySupportHint,
            sourceCode: failure.errorCode.code,
            failureKind: failure.runtimeFailure.kind,
            recoveryAction: RuntimeRecoveryAction.retry,
            copyKey: 'startupRecovery',
            presentation: UiErrorPresentation.emptyPage,
            tone: UiErrorTone.critical,
            primaryAction: UiErrorAction(
              type: UiErrorActionType.retry,
              label: UITextConstants.startupRecoveryRetry,
            ),
          ),
          onAction: (action) async {
            if (action.type == UiErrorActionType.retry) {
              await onRetry();
            }
          },
        ),
      ),
    );
  }
}
