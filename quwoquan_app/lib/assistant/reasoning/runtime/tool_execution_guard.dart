import 'package:quwoquan_app/assistant/reasoning/runtime/tool_loop_detector.dart';

enum GuardVerdict { allowed, blocked, needsConfirmation }

class GuardResult {
  const GuardResult._({
    required this.verdict,
    this.reason = '',
    this.toolName = '',
    this.args = const <String, dynamic>{},
  });

  factory GuardResult.allowed() =>
      const GuardResult._(verdict: GuardVerdict.allowed);

  factory GuardResult.blocked(String reason) =>
      GuardResult._(verdict: GuardVerdict.blocked, reason: reason);

  factory GuardResult.needsConfirmation(
    String toolName,
    Map<String, dynamic> args,
  ) => GuardResult._(
    verdict: GuardVerdict.needsConfirmation,
    toolName: toolName,
    args: args,
  );

  final GuardVerdict verdict;
  final String reason;
  final String toolName;
  final Map<String, dynamic> args;

  bool get isAllowed => verdict == GuardVerdict.allowed;
  bool get isBlocked => verdict == GuardVerdict.blocked;
}

/// Pre-execution guard that checks loop detection and tool permissions.
class ToolExecutionGuard {
  ToolExecutionGuard({
    ToolLoopDetector? loopDetector,
    Map<String, ToolPermission>? permissions,
  }) : _loopDetector = loopDetector ?? ToolLoopDetector(),
       _permissions = permissions ?? const <String, ToolPermission>{};

  final ToolLoopDetector _loopDetector;
  final Map<String, ToolPermission> _permissions;
  final Map<String, _RecentToolFailure> _recentFailures =
      <String, _RecentToolFailure>{};
  static const Duration _repeatFailureCooldown = Duration(seconds: 20);

  void reset() {
    _loopDetector.reset();
    _recentFailures.clear();
  }

  GuardResult checkBeforeExecution(String toolName, Map<String, dynamic> args) {
    final loopResult = _loopDetector.check(toolName, args, null);
    if (loopResult.blocked) {
      return GuardResult.blocked(loopResult.reason);
    }

    final signature = _toolSignature(toolName, args);
    final recentFailure = _recentFailures[signature];
    if (recentFailure != null &&
        recentFailure.failureCount >= 2 &&
        DateTime.now().difference(recentFailure.lastFailureAt) <
            _repeatFailureCooldown) {
      return GuardResult.blocked(
        recentFailure.message.trim().isNotEmpty
            ? '同一工具刚刚连续失败，已暂停重复尝试：${recentFailure.message}'
            : '同一工具刚刚连续失败，已暂停重复尝试，请稍后再试或调整条件。',
      );
    }

    final perm = _permissions[toolName];
    if (perm != null && perm.requireConfirmation) {
      return GuardResult.needsConfirmation(toolName, args);
    }

    return GuardResult.allowed();
  }

  /// Update the loop detector with actual result hash after execution.
  void recordResult(
    String toolName,
    Map<String, dynamic> args,
    String resultContent,
  ) {
    final resultHash = ToolLoopDetector.hashResult(resultContent);
    _loopDetector.check(toolName, args, resultHash);
  }

  void recordExecutionResult(
    String toolName,
    Map<String, dynamic> args, {
    required bool success,
    required String message,
    required String errorCode,
  }) {
    final signature = _toolSignature(toolName, args);
    if (success) {
      _recentFailures.remove(signature);
      if (message.trim().isNotEmpty) {
        recordResult(toolName, args, message);
      }
      return;
    }
    final now = DateTime.now();
    final existing = _recentFailures[signature];
    final withinCooldown =
        existing != null &&
        now.difference(existing.lastFailureAt) < _repeatFailureCooldown;
    _recentFailures[signature] = _RecentToolFailure(
      failureCount: withinCooldown ? existing.failureCount + 1 : 1,
      lastFailureAt: now,
      message: message,
      errorCode: errorCode,
    );
  }

  String _toolSignature(String toolName, Map<String, dynamic> args) {
    final normalized = Map<String, dynamic>.from(args)
      ..removeWhere((key, _) => key.startsWith('__'));
    return '$toolName::${ToolLoopDetector.hashResult(normalized.toString())}';
  }
}

class ToolPermission {
  const ToolPermission({
    this.requireConfirmation = false,
    this.allowedSchemes = const <String>[],
  });

  final bool requireConfirmation;
  final List<String> allowedSchemes;
}

class _RecentToolFailure {
  const _RecentToolFailure({
    required this.failureCount,
    required this.lastFailureAt,
    required this.message,
    required this.errorCode,
  });

  final int failureCount;
  final DateTime lastFailureAt;
  final String message;
  final String errorCode;
}
