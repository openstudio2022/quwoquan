import 'package:quwoquan_app/assistant/tool/runtime/tool_loop_detection.dart';
import 'package:quwoquan_app/assistant/orchestration/assistant_runtime_failure_mapper.dart';
import 'package:quwoquan_app/assistant/tool/schema/tool_schema.dart';
import 'package:quwoquan_app/assistant/tool/runtime/tool_metadata_registry.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

class AssistantToolRegistry {
  AssistantToolRegistry({ToolMetadataRegistry? metadataRegistry})
    : _metadataRegistry = metadataRegistry;

  final Map<String, AssistantTool> _tools = <String, AssistantTool>{};
  final ToolMetadataRegistry? _metadataRegistry;
  final ToolCallHistory _callHistory = ToolCallHistory();
  final _ToolResilienceManager _resilienceManager = _ToolResilienceManager();

  void register(AssistantTool tool) {
    _tools[tool.name] = tool;
  }

  AssistantTool? getTool(String name) => _tools[name];

  List<AssistantTool> listTools() => _tools.values.toList(growable: false);

  /// Access to call history for external inspection (e.g. assessment).
  ToolCallHistory get callHistory => _callHistory;

  /// Reset call history (e.g. at the start of each agent run).
  void resetCallHistory() => _callHistory.clear();

  Future<AssistantToolResult> execute(
    String name,
    Map<String, dynamic> arguments,
  ) async {
    final tool = _tools[name];
    if (tool == null) {
      return _failureResult(
        toolName: name,
        errorCode: AssistantErrorCode.toolNotFound,
        message: 'Tool not found',
        stage: 'tool_lookup',
      );
    }
    await _metadataRegistry?.ensureLoaded();
    final typedArguments = AssistantToolArguments.fromJson(arguments);
    final argCheck = _validateArguments(name: name, arguments: typedArguments);
    if (argCheck != null) return argCheck;

    // before_tool_call hook: record call + loop detection
    final record = _callHistory.recordCall(name, arguments);
    final loopCheck = _callHistory.detectLoop();
    if (loopCheck.detected && loopCheck.severity == LoopSeverity.critical) {
      _callHistory.recordOutcome(record, false, loopCheck.message, null);
      return _failureResult(
        toolName: name,
        errorCode: AssistantErrorCode.executionFailed,
        message: loopCheck.message,
        stage: 'tool_loop_guard',
        data: AssistantToolResultData(<String, Object?>{
          'loopDetected': true,
          'loopPattern': loopCheck.pattern,
          'loopStreak': loopCheck.streak,
        }),
      );
    }

    try {
      final result = await _executeWithResilience(
        tool: tool,
        name: name,
        arguments: typedArguments,
      );

      // after_tool_call hook: record outcome
      _callHistory.recordOutcome(
        record,
        result.success,
        result.message,
        result.data,
      );

      final outputCheck = _validateOutput(name: name, result: result);
      if (outputCheck != null) return outputCheck;

      // Attach loop warning to result data if detected
      if (loopCheck.detected && loopCheck.severity == LoopSeverity.warning) {
        final augmentedData = <String, dynamic>{
          ...?result.data,
          'loopWarning': loopCheck.message,
          'loopPattern': loopCheck.pattern,
          'loopStreak': loopCheck.streak,
        };
        return AssistantToolResult(
          success: result.success,
          message: result.message,
          errorCode: result.errorCode,
          degraded: result.degraded,
          runtimeFailure: result.effectiveRuntimeFailure,
          data: AssistantToolResultData.fromJson(augmentedData),
        );
      }

      return result;
    } catch (error) {
      _callHistory.recordOutcome(record, false, error.toString(), null);
      return AssistantToolResult(
        success: false,
        message: 'Tool execution failed: $error',
        errorCode: AssistantErrorCode.executionFailed,
        degraded: true,
        runtimeFailure: const AssistantRuntimeFailureMapper()
            .fromAssistantErrorCode(
              errorCode: AssistantErrorCode.executionFailed,
              boundary: 'assistant_tool',
              stage: 'tool_registry_execute',
              functionModule: name,
              businessObject: 'assistant_tool',
              attributes: <RuntimeContextAttribute>[
                RuntimeContextAttribute(key: 'errorType', value: 'exception'),
              ],
            ),
      );
    }
  }

  Future<AssistantToolResult> _executeWithResilience({
    required AssistantTool tool,
    required String name,
    required AssistantToolArguments arguments,
  }) async {
    final policy = _resilienceManager.policyFor(name);
    final breakerResult = policy?.checkBeforeExecute(name);
    if (breakerResult != null) {
      return breakerResult;
    }
    final maxAttempts = policy?.maxAttempts ?? 1;
    AssistantToolResult? lastResult;
    for (var attempt = 1; attempt <= maxAttempts; attempt++) {
      try {
        lastResult = await tool.execute(arguments);
      } catch (error) {
        lastResult = _failureResult(
          toolName: name,
          errorCode: AssistantErrorCode.executionFailed,
          message: 'Tool execution failed: $error',
          stage: 'tool_execution',
        );
      }
      if (lastResult.success) {
        policy?.recordSuccess();
        return _attachRetryMetadata(
          lastResult,
          attempts: attempt,
          recovered: attempt > 1,
        );
      }
      final shouldRetry = _shouldRetryFailure(name: name, result: lastResult);
      if (!shouldRetry || attempt >= maxAttempts) {
        if (shouldRetry) {
          policy?.recordTransientFailure();
        } else {
          policy?.recordNonTransientFailure();
        }
        return _attachRetryMetadata(
          lastResult,
          attempts: attempt,
          recovered: false,
        );
      }
      await Future<void>.delayed(policy?.retryDelay ?? Duration.zero);
    }
    return lastResult ??
        _failureResult(
          toolName: name,
          errorCode: AssistantErrorCode.executionFailed,
          message: 'Tool execution failed',
          stage: 'tool_execution',
        );
  }

  AssistantToolResult _attachRetryMetadata(
    AssistantToolResult result, {
    required int attempts,
    required bool recovered,
  }) {
    if (attempts <= 1) return result;
    return AssistantToolResult(
      success: result.success,
      message: result.message,
      errorCode: result.errorCode,
      degraded: result.degraded,
      runtimeFailure: result.effectiveRuntimeFailure,
      data: AssistantToolResultData(<String, Object?>{
        ...?result.data,
        'retry': <String, dynamic>{
          'attempts': attempts,
          'recovered': recovered,
        },
      }),
    );
  }

  bool _shouldRetryFailure({
    required String name,
    required AssistantToolResult result,
  }) {
    final policy = _resilienceManager.policyFor(name);
    if (policy == null || result.success) {
      return false;
    }
    final failure =
        result.effectiveRuntimeFailure ??
        const AssistantRuntimeFailureMapper().fromAssistantErrorCode(
          errorCode: result.errorCode,
          boundary: 'assistant_tool',
          stage: 'tool_retry_policy',
          functionModule: name,
          businessObject: 'assistant_tool',
        );
    final decision = const DefaultRuntimeRecoveryPolicy().decide(
      failure,
      const EntryContext(
        kind: 'assistant_tool',
        entryId: '',
        actorType: 'assistant',
        actorId: '',
        surfaceId: 'assistant',
      ),
      BoundaryContext(
        boundary: 'assistant_tool',
        stage: 'tool_retry_policy',
        remainingBudget: policy.maxAttempts - 1,
      ),
    );
    return decision.action == RuntimeRecoveryAction.retry;
  }

  AssistantToolResult? _validateArguments({
    required String name,
    required AssistantToolArguments arguments,
  }) {
    final parameters = _metadataRegistry?.functionParametersByToolName(name);
    if (parameters == null || parameters.isEmptyPayload) return null;
    final requiredKeys = parameters.requiredFields;
    final properties = parameters.properties;
    final normalizedArgs = <String, Object?>{};
    for (final entry in arguments.entries) {
      if (entry.key.startsWith('__')) continue;
      normalizedArgs[entry.key] = entry.value;
    }
    for (final key in requiredKeys) {
      final value = normalizedArgs[key];
      if (value == null) {
        return _failureResult(
          toolName: name,
          errorCode: AssistantErrorCode.invalidArguments,
          message: 'Tool argument invalid: missing required "$key"',
          stage: 'tool_argument_validation',
        );
      }
      if (value is String && value.trim().isEmpty) {
        return _failureResult(
          toolName: name,
          errorCode: AssistantErrorCode.invalidArguments,
          message: 'Tool argument invalid: empty required "$key"',
          stage: 'tool_argument_validation',
        );
      }
    }
    for (final entry in normalizedArgs.entries) {
      final typedSchema = properties[entry.key];
      if (typedSchema == null) continue;
      final expectedType = typedSchema.type;
      if (expectedType.isEmpty) continue;
      if (!_matchesType(expectedType, entry.value)) {
        return _failureResult(
          toolName: name,
          errorCode: AssistantErrorCode.invalidArguments,
          message:
              'Tool argument invalid: "${entry.key}" expects $expectedType',
          stage: 'tool_argument_validation',
        );
      }
      final enumError = _validateEnum(
        toolName: name,
        key: entry.key,
        schema: typedSchema,
        value: entry.value,
      );
      if (enumError != null) {
        return enumError;
      }
    }
    return null;
  }

  AssistantToolResult? _validateOutput({
    required String name,
    required AssistantToolResult result,
  }) {
    if (!result.success) return null;
    final requiredPaths =
        _metadataRegistry?.requiredOutputPathsByToolName(name) ??
        const <String>[];
    if (requiredPaths.isEmpty) return null;
    final data = result.data?.toDynamicJson() ?? const <String, dynamic>{};
    for (final path in requiredPaths) {
      if (!_hasPath(data, path)) {
        return _failureResult(
          toolName: name,
          errorCode: AssistantErrorCode.executionFailed,
          message: 'Tool output invalid: missing "$path"',
          stage: 'tool_output_validation',
        );
      }
    }
    return null;
  }

  AssistantToolResult _failureResult({
    required String toolName,
    required AssistantErrorCode errorCode,
    required String message,
    required String stage,
    AssistantToolResultData? data,
  }) {
    return AssistantToolResult(
      success: false,
      message: message,
      errorCode: errorCode,
      degraded: true,
      data: data,
      runtimeFailure: const AssistantRuntimeFailureMapper()
          .fromAssistantErrorCode(
            errorCode: errorCode,
            boundary: 'assistant_tool',
            stage: stage,
            functionModule: toolName,
            businessObject: 'assistant_tool',
            attributes: <RuntimeContextAttribute>[
              RuntimeContextAttribute(key: 'toolName', value: toolName),
            ],
          ),
    );
  }

  bool _matchesType(String expectedType, Object? value) {
    switch (expectedType) {
      case 'string':
        return value is String;
      case 'integer':
        return value is int;
      case 'number':
        return value is num;
      case 'boolean':
        return value is bool;
      case 'array':
        return value is List;
      case 'object':
        return value is Map;
      default:
        return true;
    }
  }

  AssistantToolResult? _validateEnum({
    required String toolName,
    required String key,
    required AssistantToolSchemaField schema,
    required Object? value,
  }) {
    final enumValues = schema.enumValues.toSet();
    if (enumValues.isNotEmpty) {
      if (value is! String || !enumValues.contains(value)) {
        return _failureResult(
          toolName: toolName,
          errorCode: AssistantErrorCode.invalidArguments,
          message:
              'Tool argument invalid: "$key" must be one of ${enumValues.join(", ")}',
          stage: 'tool_argument_validation',
        );
      }
    }
    final expectedType = schema.type;
    if (expectedType != 'array' || value is! List) {
      return null;
    }
    final itemSchema = schema.items;
    if (itemSchema == null) {
      return null;
    }
    final itemType = itemSchema.type;
    if (itemType.isNotEmpty &&
        value.any((item) => !_matchesType(itemType, item))) {
      return _failureResult(
        toolName: toolName,
        errorCode: AssistantErrorCode.invalidArguments,
        message:
            'Tool argument invalid: "$key" contains item that is not $itemType',
        stage: 'tool_argument_validation',
      );
    }
    final itemEnums = itemSchema.enumValues.toSet();
    if (itemEnums.isNotEmpty &&
        value.any((item) => item is! String || !itemEnums.contains(item))) {
      return _failureResult(
        toolName: toolName,
        errorCode: AssistantErrorCode.invalidArguments,
        message:
            'Tool argument invalid: "$key" contains unsupported enum value',
        stage: 'tool_argument_validation',
      );
    }
    return null;
  }

  bool _hasPath(Map<String, dynamic> data, String path) {
    final parts = path.split('.');
    Object? current = data;
    for (final part in parts) {
      if (current is! Map) return false;
      if (!current.containsKey(part)) return false;
      current = current[part];
    }
    return current != null;
  }
}

class _ToolResilienceManager {
  final Map<String, _ToolResiliencePolicy> _policies =
      <String, _ToolResiliencePolicy>{
        'search': _ToolResiliencePolicy(
          maxAttempts: 2,
          retryDelay: Duration.zero,
          breakerThreshold: 2,
          breakerWindow: const Duration(minutes: 1),
          breakerDuration: const Duration(seconds: 30),
        ),
        'web_search': _ToolResiliencePolicy(
          maxAttempts: 2,
          retryDelay: Duration.zero,
          breakerThreshold: 2,
          breakerWindow: const Duration(minutes: 1),
          breakerDuration: const Duration(seconds: 30),
        ),
        'web_fetch': _ToolResiliencePolicy(
          maxAttempts: 2,
          retryDelay: Duration.zero,
          breakerThreshold: 2,
          breakerWindow: const Duration(minutes: 1),
          breakerDuration: const Duration(seconds: 30),
        ),
      };

  _ToolResiliencePolicy? policyFor(String toolName) => _policies[toolName];
}

class _ToolResiliencePolicy {
  _ToolResiliencePolicy({
    required this.maxAttempts,
    required this.retryDelay,
    required this.breakerThreshold,
    required this.breakerWindow,
    required this.breakerDuration,
  });

  final int maxAttempts;
  final Duration retryDelay;
  final int breakerThreshold;
  final Duration breakerWindow;
  final Duration breakerDuration;
  final List<DateTime> _recentTransientFailures = <DateTime>[];
  DateTime? _breakerOpenUntil;

  AssistantToolResult? checkBeforeExecute(String toolName) {
    final now = DateTime.now();
    if (_breakerOpenUntil != null && now.isBefore(_breakerOpenUntil!)) {
      final remainingSeconds = _breakerOpenUntil!
          .difference(now)
          .inSeconds
          .clamp(1, 60);
      return AssistantToolResult(
        success: false,
        message: '$toolName 当前处于短暂保护期，请在 ${remainingSeconds}s 后重试。',
        errorCode: AssistantErrorCode.networkUnavailable,
        degraded: true,
        data: AssistantToolResultData(<String, Object?>{
          'breakerOpen': true,
          'recoveryAfterSeconds': remainingSeconds,
        }),
        runtimeFailure: const AssistantRuntimeFailureMapper()
            .fromAssistantErrorCode(
              errorCode: AssistantErrorCode.networkUnavailable,
              boundary: 'assistant_tool',
              stage: 'tool_breaker_open',
              functionModule: toolName,
              businessObject: 'assistant_tool',
              attributes: <RuntimeContextAttribute>[
                RuntimeContextAttribute(key: 'toolName', value: toolName),
              ],
            ),
      );
    }
    if (_breakerOpenUntil != null && !now.isBefore(_breakerOpenUntil!)) {
      _breakerOpenUntil = null;
      _recentTransientFailures.clear();
    }
    return null;
  }

  void recordSuccess() {
    _breakerOpenUntil = null;
    _recentTransientFailures.clear();
  }

  void recordTransientFailure() {
    final now = DateTime.now();
    _recentTransientFailures.removeWhere(
      (time) => now.difference(time) > breakerWindow,
    );
    _recentTransientFailures.add(now);
    if (_recentTransientFailures.length >= breakerThreshold) {
      _breakerOpenUntil = now.add(breakerDuration);
    }
  }

  void recordNonTransientFailure() {
    final now = DateTime.now();
    _recentTransientFailures.removeWhere(
      (time) => now.difference(time) > breakerWindow,
    );
  }
}
