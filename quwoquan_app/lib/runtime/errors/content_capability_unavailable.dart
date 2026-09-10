import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

/// 本地内容读取不授予云端写入或后台同步能力；不伪造 HTTP 响应或待投递任务。
CloudException contentCapabilityUnavailable(String capability) {
  return CloudException(
    type: CloudErrorType.unknown,
    message: 'Content capability is unavailable for the selected source',
    code: RuntimeFailureCodes.clientPlatformCapabilityUnavailable,
    runtimeFailure: RuntimeFailure(
      code: RuntimeFailureCodes.clientPlatformCapabilityUnavailable,
      semanticReason: 'content_source_capability_unavailable',
      origin: RuntimeFailureOrigin.localClient,
      kind: RuntimeFailureKind.unsupported,
      nature: RuntimeFailureNature.permanent,
      location: const RuntimeFailureLocation(
        businessObject: 'app_runtime',
        functionModule: 'platform_capability_gateway',
      ),
      context: RuntimeFailureContext(
        attributes: <RuntimeContextAttribute>[
          RuntimeContextAttribute(key: 'capability', value: capability),
        ],
      ),
      recovery: const RuntimeRecoveryDirective(
        action: 'surface',
        disruptionLevel: 'snackbar',
      ),
    ),
  );
}
