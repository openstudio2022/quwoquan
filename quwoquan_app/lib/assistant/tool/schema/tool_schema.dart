import 'dart:collection';

import 'package:quwoquan_runtime_errors/runtime_errors.dart';

/// Typed payload wrapper used across tool schema / tool call / tool result.
///
/// We still serialize to JSON maps at provider/tool boundaries, but runtime
/// surfaces no longer expose raw `Map<String, dynamic>` as their public shape.
class AssistantToolPayload extends MapBase<String, Object?> {
  AssistantToolPayload([
    Map<String, Object?> fields = const <String, Object?>{},
  ]) : _fields = Map.unmodifiable(_normalizeObjectMap(fields));

  factory AssistantToolPayload.fromJson(Object? raw) {
    return AssistantToolPayload(_normalizeObjectMap(raw));
  }

  final Map<String, Object?> _fields;

  @override
  Object? operator [](Object? key) => _fields[key];

  @override
  void operator []=(String key, Object? value) {
    throw UnsupportedError('AssistantToolPayload is immutable');
  }

  @override
  void clear() {
    throw UnsupportedError('AssistantToolPayload is immutable');
  }

  @override
  Iterable<String> get keys => _fields.keys;

  @override
  Object? remove(Object? key) {
    throw UnsupportedError('AssistantToolPayload is immutable');
  }

  bool get isEmptyPayload => _fields.isEmpty;

  String? stringField(String key) => (_fields[key] as String?)?.trim();

  int? intField(String key) {
    final value = _fields[key];
    if (value is int) return value;
    if (value is num) return value.toInt();
    return int.tryParse(value?.toString() ?? '');
  }

  double? doubleField(String key) {
    final value = _fields[key];
    if (value is double) return value;
    if (value is num) return value.toDouble();
    return double.tryParse(value?.toString() ?? '');
  }

  bool? boolField(String key) {
    final value = _fields[key];
    if (value is bool) return value;
    final text = value?.toString().trim().toLowerCase() ?? '';
    if (text == 'true') return true;
    if (text == 'false') return false;
    return null;
  }

  List<Object?> listField(String key) {
    final value = _fields[key];
    if (value is List) {
      return List<Object?>.from(value, growable: false);
    }
    return const <Object?>[];
  }

  List<String> stringListField(String key) {
    return listField(key)
        .map((item) => item?.toString().trim() ?? '')
        .where((item) => item.isNotEmpty)
        .toList(growable: false);
  }

  AssistantToolPayload payloadField(String key) {
    return AssistantToolPayload.fromJson(_fields[key]);
  }

  Map<String, Object?> toJson() => Map<String, Object?>.from(_fields);

  Map<String, dynamic> toDynamicJson() =>
      _toDynamicMap(Map<String, Object?>.from(_fields));

  static Map<String, Object?> _normalizeObjectMap(Object? raw) {
    if (raw is AssistantToolPayload) {
      return raw.toJson();
    }
    if (raw is Map) {
      final normalized = <String, Object?>{};
      for (final entry in raw.entries) {
        final key = entry.key?.toString().trim() ?? '';
        if (key.isEmpty) continue;
        normalized[key] = _normalizeValue(entry.value);
      }
      return normalized;
    }
    return const <String, Object?>{};
  }

  static Object? _normalizeValue(Object? value) {
    if (value is AssistantToolPayload) {
      return value.toJson();
    }
    if (value is List) {
      return value.map(_normalizeValue).toList(growable: false);
    }
    if (value is Map) {
      return _normalizeObjectMap(value);
    }
    return value;
  }

  static Map<String, dynamic> _toDynamicMap(Map<String, Object?> raw) {
    return raw.map<String, dynamic>(
      (key, value) => MapEntry<String, dynamic>(key, _toDynamicValue(value)),
    );
  }

  static dynamic _toDynamicValue(Object? value) {
    if (value is AssistantToolPayload) {
      return _toDynamicMap(value.toJson());
    }
    if (value is Map) {
      return value.map<String, dynamic>(
        (key, nested) =>
            MapEntry<String, dynamic>(key.toString(), _toDynamicValue(nested)),
      );
    }
    if (value is List) {
      return value.map<dynamic>(_toDynamicValue).toList(growable: false);
    }
    return value;
  }
}

class AssistantToolArguments extends AssistantToolPayload {
  AssistantToolArguments([super.fields = const <String, Object?>{}]);

  factory AssistantToolArguments.fromJson(Object? raw) {
    return AssistantToolArguments(AssistantToolPayload.fromJson(raw).toJson());
  }

  AssistantToolArguments withoutInternalFields() {
    return AssistantToolArguments(
      Map<String, Object?>.fromEntries(
        entries.where((entry) => !entry.key.startsWith('__')),
      ),
    );
  }
}

class AssistantToolResultData extends AssistantToolPayload {
  AssistantToolResultData([super.fields = const <String, Object?>{}]);

  factory AssistantToolResultData.fromJson(Object? raw) {
    return AssistantToolResultData(AssistantToolPayload.fromJson(raw).toJson());
  }
}

class AssistantToolSchemaField extends AssistantToolPayload {
  AssistantToolSchemaField([super.fields = const <String, Object?>{}]);

  factory AssistantToolSchemaField.fromJson(Object? raw) {
    return AssistantToolSchemaField(
      AssistantToolPayload.fromJson(raw).toJson(),
    );
  }

  String get type => stringField('type') ?? '';

  String get description => stringField('description') ?? '';

  List<String> get enumValues => stringListField('enum');

  AssistantToolSchemaField? get items {
    final value = this['items'];
    if (value is! Map && value is! AssistantToolPayload) return null;
    final nested = AssistantToolSchemaField.fromJson(value);
    return nested.isEmptyPayload ? null : nested;
  }

  Map<String, AssistantToolSchemaField> get properties {
    final value = this['properties'];
    if (value is! Map && value is! AssistantToolPayload) {
      return const <String, AssistantToolSchemaField>{};
    }
    final raw = AssistantToolPayload.fromJson(value);
    final out = <String, AssistantToolSchemaField>{};
    for (final entry in raw.entries) {
      out[entry.key] = AssistantToolSchemaField.fromJson(entry.value);
    }
    return out;
  }
}

class AssistantToolInputSchema extends AssistantToolPayload {
  AssistantToolInputSchema([super.fields = const <String, Object?>{}]);

  factory AssistantToolInputSchema.fromJson(Object? raw) {
    return AssistantToolInputSchema(
      AssistantToolPayload.fromJson(raw).toJson(),
    );
  }

  List<String> get requiredFields => stringListField('required');

  Map<String, AssistantToolSchemaField> get properties {
    final value = this['properties'];
    if (value is! Map && value is! AssistantToolPayload) {
      return const <String, AssistantToolSchemaField>{};
    }
    final raw = AssistantToolPayload.fromJson(value);
    final out = <String, AssistantToolSchemaField>{};
    for (final entry in raw.entries) {
      out[entry.key] = AssistantToolSchemaField.fromJson(entry.value);
    }
    return out;
  }
}

class AssistantToolSpec {
  AssistantToolSpec({
    required this.name,
    required this.description,
    required this.inputSchema,
  });

  final String name;
  final String description;
  final AssistantToolInputSchema inputSchema;

  Map<String, Object?> toJson() {
    return <String, Object?>{
      'name': name,
      'description': description,
      'inputSchema': inputSchema.toJson(),
    };
  }

  Map<String, dynamic> toOpenAiToolWire() {
    return <String, dynamic>{
      'type': 'function',
      'function': <String, dynamic>{
        'name': name,
        'description': description,
        'parameters': inputSchema.toDynamicJson(),
      },
    };
  }

  Map<String, dynamic> toAnthropicToolWire() {
    return <String, dynamic>{
      'name': name,
      'description': description,
      'input_schema': inputSchema.toDynamicJson(),
    };
  }
}

class AssistantToolCall {
  AssistantToolCall({
    required this.name,
    required Object? arguments,
    this.id = '',
  }) : arguments = arguments is AssistantToolArguments
           ? arguments
           : AssistantToolArguments.fromJson(arguments);

  final String name;
  final AssistantToolArguments arguments;

  /// OpenAI function calling 协议中的 tool_call id，用于构建 tool message。
  final String id;

  Map<String, Object?> toJson() {
    return <String, Object?>{
      if (id.isNotEmpty) 'id': id,
      'name': name,
      'arguments': arguments.toJson(),
    };
  }

  factory AssistantToolCall.fromJson(Map<String, dynamic> json) {
    final normalizedName =
        (json['name'] as String?)?.trim() ??
        (json['toolName'] as String?)?.trim() ??
        '';
    final rawArgs = json['arguments'];
    return AssistantToolCall(
      name: normalizedName,
      arguments: AssistantToolArguments.fromJson(rawArgs),
      id:
          (json['id'] as String?)?.trim() ??
          (json['toolCallId'] as String?)?.trim() ??
          '',
    );
  }
}

enum AssistantErrorCode {
  none,
  invalidArguments,
  toolNotFound,
  skillNotFound,
  unsupportedTarget,
  permissionDenied,
  networkUnavailable,
  executionFailed,
  unauthorized,
  rateLimited,
}

class AssistantErrorCatalog {
  const AssistantErrorCatalog._();

  static String fallbackMessage(AssistantErrorCode code) {
    switch (code) {
      case AssistantErrorCode.invalidArguments:
        return '请求参数不完整，已自动降级为安全回复。';
      case AssistantErrorCode.toolNotFound:
        return '未找到所需能力，已降级为本地说明。';
      case AssistantErrorCode.skillNotFound:
        return '未找到对应技能，请检查技能是否已启用。';
      case AssistantErrorCode.unsupportedTarget:
        return '当前设备不支持该能力目标，已尝试可用路径。';
      case AssistantErrorCode.permissionDenied:
        return '系统权限不足，暂无法执行该操作。';
      case AssistantErrorCode.networkUnavailable:
        return '当前网络不可用，已切换为离线策略。';
      case AssistantErrorCode.executionFailed:
        return '能力执行失败，已返回可恢复结果。';
      case AssistantErrorCode.unauthorized:
        return '鉴权失败，请检查令牌配置。';
      case AssistantErrorCode.rateLimited:
        return '请求过于频繁，请稍后再试。';
      case AssistantErrorCode.none:
        return '执行成功。';
    }
  }
}

class AssistantToolResult {
  const AssistantToolResult({
    required this.success,
    required this.message,
    this.data,
    this.errorCode = AssistantErrorCode.none,
    this.degraded = false,
    this.runtimeFailure,
    this.searchPlan,
  });

  final bool success;
  final String message;
  final AssistantToolResultData? data;
  final AssistantErrorCode errorCode;
  final bool degraded;
  final RuntimeFailureBase? runtimeFailure;
  final Map<String, Object?>? searchPlan;

  RuntimeFailureBase? get effectiveRuntimeFailure =>
      runtimeFailure ??
      (success ? null : _fallbackRuntimeFailureForToolResult(this));

  Map<String, Object?> toJson() {
    final failure = effectiveRuntimeFailure;
    return <String, Object?>{
      'success': success,
      'message': message,
      'data': data?.toJson(),
      'errorCode': errorCode.name,
      'degraded': degraded,
      if (failure != null) 'runtimeFailure': _runtimeFailureToJson(failure),
      if (searchPlan != null) 'searchPlan': searchPlan,
    };
  }

  factory AssistantToolResult.fromJson(Map<String, dynamic> json) {
    final codeName = (json['errorCode'] as String?)?.trim() ?? 'none';
    final code = AssistantErrorCode.values.firstWhere(
      (e) => e.name == codeName,
      orElse: () => AssistantErrorCode.none,
    );
    final parsedFailure = json['runtimeFailure'] is Map
        ? RuntimeFailure.fromJson(
            (json['runtimeFailure'] as Map).cast<String, dynamic>(),
          )
        : null;
    final result = AssistantToolResult(
      success: json['success'] == true,
      message: (json['message'] as String?) ?? '',
      data: json['data'] is Map
          ? AssistantToolResultData.fromJson(json['data'])
          : null,
      errorCode: code,
      degraded: json['degraded'] == true,
      runtimeFailure: parsedFailure,
      searchPlan: json['searchPlan'] is Map
          ? (json['searchPlan'] as Map).cast<String, Object?>()
          : null,
    );
    if (result.success || result.runtimeFailure != null) return result;
    return AssistantToolResult(
      success: result.success,
      message: result.message,
      data: result.data,
      errorCode: result.errorCode,
      degraded: result.degraded,
      runtimeFailure: _fallbackRuntimeFailureForToolResult(result),
      searchPlan: result.searchPlan,
    );
  }
}

Map<String, Object?> _runtimeFailureToJson(RuntimeFailureBase failure) {
  return <String, Object?>{
    'code': failure.code,
    'origin': failure.origin.name,
    'kind': failure.kind.name,
    'nature': failure.nature.name,
    'location': failure.location.toJson(),
    'context': failure.context.toJson(),
  };
}

RuntimeFailure _fallbackRuntimeFailureForToolResult(
  AssistantToolResult result,
) {
  final code = switch (result.errorCode) {
    AssistantErrorCode.none => 'ASSISTANT.SYSTEM.execution_failed',
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
  return RuntimeFailure(
    code: code,
    origin: _originForAssistantToolCode(code),
    kind: _kindForAssistantToolCode(code),
    nature: _natureForAssistantToolCode(code),
    location: const RuntimeFailureLocation(
      businessObject: 'assistant_tool',
      functionModule: 'assistant_tool_result',
    ),
    context: RuntimeFailureContext(
      attributes: <RuntimeContextAttribute>[
        RuntimeContextAttribute(
          key: 'assistantErrorCode',
          value: result.errorCode.name,
        ),
        if (result.message.trim().isNotEmpty)
          RuntimeContextAttribute(key: 'message', value: result.message.trim()),
      ],
    ),
  );
}

RuntimeFailure assistantToolRuntimeFailure({
  required AssistantErrorCode errorCode,
  required String message,
  required String functionModule,
  String stage = 'tool_impl',
}) {
  final code = switch (errorCode) {
    AssistantErrorCode.none => 'ASSISTANT.SYSTEM.execution_failed',
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
  return RuntimeFailure(
    code: code,
    origin: _originForAssistantToolCode(code),
    kind: _kindForAssistantToolCode(code),
    nature: _natureForAssistantToolCode(code),
    location: RuntimeFailureLocation(
      businessObject: 'assistant_tool',
      functionModule: functionModule,
    ),
    context: RuntimeFailureContext(
      attributes: <RuntimeContextAttribute>[
        RuntimeContextAttribute(key: 'stage', value: stage),
        RuntimeContextAttribute(
          key: 'assistantErrorCode',
          value: errorCode.name,
        ),
        if (message.trim().isNotEmpty)
          RuntimeContextAttribute(key: 'message', value: message.trim()),
      ],
    ),
  );
}

RuntimeFailureOrigin _originForAssistantToolCode(String code) {
  if (code.contains('.VALIDATION.') ||
      code.contains('.PERMISSION.') ||
      code.contains('.AUTH.')) {
    return RuntimeFailureOrigin.user;
  }
  if (code.contains('.NETWORK.') || code.contains('.RATE_LIMITED.')) {
    return RuntimeFailureOrigin.remoteDependency;
  }
  return RuntimeFailureOrigin.system;
}

RuntimeFailureKind _kindForAssistantToolCode(String code) {
  if (code.contains('.VALIDATION.')) return RuntimeFailureKind.validation;
  if (code.contains('.PERMISSION.')) return RuntimeFailureKind.permission;
  if (code.contains('.AUTH.')) return RuntimeFailureKind.auth;
  if (code.contains('.NETWORK.')) return RuntimeFailureKind.network;
  if (code.contains('.RATE_LIMITED.')) return RuntimeFailureKind.rateLimited;
  if (code.contains('.NOT_FOUND.')) return RuntimeFailureKind.notFound;
  if (code.contains('.UNSUPPORTED.')) return RuntimeFailureKind.unsupported;
  return RuntimeFailureKind.internal;
}

RuntimeFailureNature _natureForAssistantToolCode(String code) {
  if (code.contains('.NETWORK.') || code.contains('.RATE_LIMITED.')) {
    return RuntimeFailureNature.transient;
  }
  if (code.contains('.PERMISSION.')) {
    return RuntimeFailureNature.requiresPermission;
  }
  if (code.contains('.AUTH.')) {
    return RuntimeFailureNature.requiresUserAction;
  }
  if (code.contains('.SYSTEM.')) return RuntimeFailureNature.bug;
  return RuntimeFailureNature.permanent;
}

abstract class AssistantTool {
  String get name;
  String get description;

  Future<AssistantToolResult> execute(AssistantToolArguments arguments);
}
