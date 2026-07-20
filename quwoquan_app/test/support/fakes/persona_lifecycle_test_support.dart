import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_errors.g.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

/// 将 canonical 生命周期守卫原因投影为端侧结构化错误。
CloudException personaLifecycleGuardExceptionForReason(String reason) {
  final errorCode = switch (reason) {
    'blocked_primary_persona' => UserErrorCode.primarySubAccountGuard,
    'blocked_last_persona' => UserErrorCode.lastSubAccount,
    'blocked_active_persona' => UserErrorCode.activeSubAccountGuard,
    'blocked_retired_persona' => UserErrorCode.retiredSubAccountGuard,
    _ => UserErrorCode.invalidArgument,
  };
  return CloudException(
    type: CloudErrorType.unknown,
    message: errorCode.code,
    statusCode: errorCode.httpStatus,
    code: errorCode.code,
    runtimeFailure: RuntimeFailure(
      code: errorCode.code,
      semanticReason: reason,
      transportStatus: errorCode.httpStatus,
      origin: RuntimeFailureOrigin.remoteDependency,
      kind: RuntimeFailureKind.validation,
      nature: RuntimeFailureNature.requiresUserAction,
      location: const RuntimeFailureLocation(
        businessObject: 'user.persona',
        functionModule: 'persona_lifecycle_test_fake',
      ),
      context: RuntimeFailureContext(
        attributes: <RuntimeContextAttribute>[
          RuntimeContextAttribute(key: 'guardReason', value: reason),
        ],
      ),
      recovery: RuntimeRecoveryDirective(
        action: errorCode.recoveryAction,
        afterSeconds: errorCode.recoveryAfterSeconds,
        disruptionLevel: errorCode.disruptionLevel,
      ),
    ),
    userMessage: errorCode.defaultMessage,
  );
}
