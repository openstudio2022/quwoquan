import 'package:quwoquan_app/assistant/tool/runtime/tool_loop_detection.dart';
import 'package:quwoquan_app/assistant/tool/schema/tool_schema.dart';
import 'package:quwoquan_app/assistant/tool/runtime/tool_metadata_registry.dart';

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
      return const AssistantToolResult(
        success: false,
        message: 'Tool not found',
        errorCode: AssistantErrorCode.toolNotFound,
        degraded: true,
      );
    }
    await _metadataRegistry?.ensureLoaded();
    final argCheck = _validateArguments(name: name, arguments: arguments);
    if (argCheck != null) return argCheck;

    // before_tool_call hook: record call + loop detection
    final record = _callHistory.recordCall(name, arguments);
    final loopCheck = _callHistory.detectLoop();
    if (loopCheck.detected && loopCheck.severity == LoopSeverity.critical) {
      _callHistory.recordOutcome(record, false, loopCheck.message, null);
      return AssistantToolResult(
        success: false,
        message: loopCheck.message,
        errorCode: AssistantErrorCode.executionFailed,
        degraded: true,
        data: <String, dynamic>{
          'loopDetected': true,
          'loopPattern': loopCheck.pattern,
          'loopStreak': loopCheck.streak,
        },
      );
    }

    try {
      final result = await _executeWithResilience(
        tool: tool,
        name: name,
        arguments: arguments,
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
          data: augmentedData,
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
      );
    }
  }

  Future<AssistantToolResult> _executeWithResilience({
    required AssistantTool tool,
    required String name,
    required Map<String, dynamic> arguments,
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
        lastResult = AssistantToolResult(
          success: false,
          message: 'Tool execution failed: $error',
          errorCode: AssistantErrorCode.executionFailed,
          degraded: true,
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
      final retryable = _isRetryableFailure(name: name, result: lastResult);
      if (!retryable || attempt >= maxAttempts) {
        if (retryable) {
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
        const AssistantToolResult(
          success: false,
          message: 'Tool execution failed',
          errorCode: AssistantErrorCode.executionFailed,
          degraded: true,
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
      data: <String, dynamic>{
        ...?result.data,
        'retry': <String, dynamic>{
          'attempts': attempts,
          'recovered': recovered,
        },
      },
    );
  }

  bool _isRetryableFailure({
    required String name,
    required AssistantToolResult result,
  }) {
    final policy = _resilienceManager.policyFor(name);
    if (policy == null || result.success) {
      return false;
    }
    return result.degraded &&
        (result.errorCode == AssistantErrorCode.networkUnavailable ||
            result.errorCode == AssistantErrorCode.rateLimited);
  }

  AssistantToolResult? _validateArguments({
    required String name,
    required Map<String, dynamic> arguments,
  }) {
    final parameters = _metadataRegistry?.functionParametersByToolName(name);
    if (parameters == null || parameters.isEmpty) return null;
    final requiredKeys = (parameters['required'] as List?)
            ?.whereType<String>()
            .toList(growable: false) ??
        const <String>[];
    final properties = (parameters['properties'] as Map?)
            ?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final normalizedArgs = <String, dynamic>{};
    for (final entry in arguments.entries) {
      if (entry.key.startsWith('__')) continue;
      normalizedArgs[entry.key] = entry.value;
    }
    for (final key in requiredKeys) {
      final value = normalizedArgs[key];
      if (value == null) {
        return AssistantToolResult(
          success: false,
          message: 'Tool argument invalid: missing required "$key"',
          errorCode: AssistantErrorCode.invalidArguments,
          degraded: true,
        );
      }
      if (value is String && value.trim().isEmpty) {
        return AssistantToolResult(
          success: false,
          message: 'Tool argument invalid: empty required "$key"',
          errorCode: AssistantErrorCode.invalidArguments,
          degraded: true,
        );
      }
    }
    for (final entry in normalizedArgs.entries) {
      final schema = properties[entry.key];
      if (schema is! Map) continue;
      final expectedType = (schema['type'] as String?)?.trim() ?? '';
      if (expectedType.isEmpty) continue;
      if (!_matchesType(expectedType, entry.value)) {
        return AssistantToolResult(
          success: false,
          message:
              'Tool argument invalid: "${entry.key}" expects $expectedType',
          errorCode: AssistantErrorCode.invalidArguments,
          degraded: true,
        );
      }
    }
    return null;
  }

  AssistantToolResult? _validateOutput({
    required String name,
    required AssistantToolResult result,
  }) {
    if (!result.success) return null;
    final requiredPaths = _metadataRegistry?.requiredOutputPathsByToolName(name) ??
        const <String>[];
    if (requiredPaths.isEmpty) return null;
    final data = result.data ?? const <String, dynamic>{};
    for (final path in requiredPaths) {
      if (!_hasPath(data, path)) {
        return AssistantToolResult(
          success: false,
          message: 'Tool output invalid: missing "$path"',
          errorCode: AssistantErrorCode.executionFailed,
          degraded: true,
        );
      }
    }
    return null;
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
      final remainingSeconds =
          _breakerOpenUntil!.difference(now).inSeconds.clamp(1, 60);
      return AssistantToolResult(
        success: false,
        message: '$toolName 当前处于短暂保护期，请在 ${remainingSeconds}s 后重试。',
        errorCode: AssistantErrorCode.networkUnavailable,
        degraded: true,
        data: <String, dynamic>{
          'breakerOpen': true,
          'retryAfterSeconds': remainingSeconds,
        },
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
