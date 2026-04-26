import 'package:quwoquan_app/assistant/tool/schema/tool_schema.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

class AssistantRuntimeFailureMapper {
  const AssistantRuntimeFailureMapper();

  RuntimeFailure fromAssistantErrorCode({
    required AssistantErrorCode errorCode,
    required String boundary,
    required String stage,
    required String functionModule,
    String businessObject = 'assistant_turn',
    List<RuntimeContextAttribute> attributes =
        const <RuntimeContextAttribute>[],
  }) {
    final runtimeCode = switch (errorCode) {
      AssistantErrorCode.none => 'ASSISTANT.SYSTEM.none',
      AssistantErrorCode.invalidArguments =>
        'ASSISTANT.VALIDATION.invalid_arguments',
      AssistantErrorCode.toolNotFound => 'ASSISTANT.NOT_FOUND.tool_not_found',
      AssistantErrorCode.skillNotFound => 'ASSISTANT.NOT_FOUND.skill_not_found',
      AssistantErrorCode.unsupportedTarget =>
        'ASSISTANT.UNSUPPORTED.unsupported_target',
      AssistantErrorCode.permissionDenied =>
        'ASSISTANT.PERMISSION.permission_denied',
      AssistantErrorCode.networkUnavailable =>
        'ASSISTANT.NETWORK.network_unavailable',
      AssistantErrorCode.executionFailed => 'ASSISTANT.SYSTEM.execution_failed',
      AssistantErrorCode.unauthorized => 'ASSISTANT.AUTH.unauthorized',
      AssistantErrorCode.rateLimited => 'ASSISTANT.RATE_LIMITED.rate_limited',
    };
    return fromRuntimeCode(
      runtimeCode,
      boundary: boundary,
      stage: stage,
      functionModule: functionModule,
      businessObject: businessObject,
      attributes: <RuntimeContextAttribute>[
        RuntimeContextAttribute(
          key: 'assistantErrorCode',
          value: errorCode.name,
        ),
        ...attributes,
      ],
    );
  }

  RuntimeFailure fromRuntimeCode(
    String code, {
    required String boundary,
    required String stage,
    required String functionModule,
    String businessObject = 'assistant_turn',
    List<RuntimeContextAttribute> attributes =
        const <RuntimeContextAttribute>[],
  }) {
    return RuntimeFailure(
      code: _normalizeRuntimeCode(code),
      origin: _originForCode(code),
      kind: _kindForCode(code),
      nature: _natureForCode(code),
      location: RuntimeFailureLocation(
        businessObject: businessObject,
        functionModule: functionModule,
      ),
      context: RuntimeFailureContext(
        attributes: <RuntimeContextAttribute>[
          RuntimeContextAttribute(key: 'boundary', value: boundary),
          RuntimeContextAttribute(key: 'stage', value: stage),
          ...attributes,
        ],
      ),
    );
  }

  RuntimeFailure fromToolResult({
    required String toolName,
    required AssistantToolResult result,
    required String stage,
  }) {
    final existing = result.runtimeFailure;
    if (existing is RuntimeFailure) return existing;
    if (existing != null) {
      return RuntimeFailure(
        code: existing.code,
        origin: existing.origin,
        kind: existing.kind,
        nature: existing.nature,
        location: existing.location,
        context: existing.context,
      );
    }
    return fromAssistantErrorCode(
      errorCode: result.errorCode,
      boundary: 'assistant_tool',
      stage: stage,
      functionModule: toolName,
      businessObject: 'assistant_tool',
      attributes: <RuntimeContextAttribute>[
        RuntimeContextAttribute(key: 'toolName', value: toolName),
      ],
    );
  }

  String _normalizeRuntimeCode(String code) {
    final trimmed = code.trim();
    if (trimmed.isEmpty) return 'ASSISTANT.SYSTEM.internal_error';
    if (trimmed.contains('.')) return trimmed;
    return 'ASSISTANT.SYSTEM.$trimmed';
  }

  RuntimeFailureOrigin _originForCode(String code) {
    if (code.contains('.USER.') ||
        code.contains('.VALIDATION.') ||
        code.contains('.PERMISSION.') ||
        code.contains('.AUTH.')) {
      return RuntimeFailureOrigin.user;
    }
    if (code.contains('.NETWORK.') ||
        code.contains('.TIMEOUT.') ||
        code.contains('.RATE_LIMITED.')) {
      return RuntimeFailureOrigin.remoteDependency;
    }
    return RuntimeFailureOrigin.system;
  }

  RuntimeFailureKind _kindForCode(String code) {
    if (code.contains('.VALIDATION.')) return RuntimeFailureKind.validation;
    if (code.contains('.CONTRACT.')) return RuntimeFailureKind.contract;
    if (code.contains('.PERMISSION.')) return RuntimeFailureKind.permission;
    if (code.contains('.AUTH.')) return RuntimeFailureKind.auth;
    if (code.contains('.NETWORK.')) return RuntimeFailureKind.network;
    if (code.contains('.RATE_LIMITED.')) return RuntimeFailureKind.rateLimited;
    if (code.contains('.UNAVAILABLE.')) return RuntimeFailureKind.unavailable;
    if (code.contains('.TIMEOUT.')) return RuntimeFailureKind.timeout;
    if (code.contains('.NOT_FOUND.')) return RuntimeFailureKind.notFound;
    if (code.contains('.UNSUPPORTED.')) return RuntimeFailureKind.unsupported;
    if (code.contains('.PARSING.')) return RuntimeFailureKind.parsing;
    if (code.contains('.MODEL.')) return RuntimeFailureKind.model;
    return RuntimeFailureKind.internal;
  }

  RuntimeFailureNature _natureForCode(String code) {
    if (code.contains('.NETWORK.') ||
        code.contains('.TIMEOUT.') ||
        code.contains('.RATE_LIMITED.') ||
        code.contains('.UNAVAILABLE.')) {
      return RuntimeFailureNature.transient;
    }
    if (code.contains('.PERMISSION.')) {
      return RuntimeFailureNature.requiresPermission;
    }
    if (code.contains('.AUTH.')) {
      return RuntimeFailureNature.requiresUserAction;
    }
    if (code.contains('.SYSTEM.') || code.contains('.CONTRACT.')) {
      return RuntimeFailureNature.bug;
    }
    return RuntimeFailureNature.permanent;
  }
}

Map<String, Object?> runtimeFailureBaseToJson(RuntimeFailureBase failure) {
  return <String, Object?>{
    'code': failure.code,
    'origin': failure.origin.name,
    'kind': failure.kind.name,
    'nature': failure.nature.name,
    'location': failure.location.toJson(),
    'context': failure.context.toJson(),
  };
}
