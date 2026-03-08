import 'package:quwoquan_app/personal_assistant/engine/tool_loop_detector.dart';

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
  ) =>
      GuardResult._(
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

  void reset() => _loopDetector.reset();

  GuardResult checkBeforeExecution(
    String toolName,
    Map<String, dynamic> args,
  ) {
    final loopResult = _loopDetector.check(toolName, args, null);
    if (loopResult.blocked) {
      return GuardResult.blocked(loopResult.reason);
    }

    final perm = _permissions[toolName];
    if (perm != null && perm.requireConfirmation) {
      return GuardResult.needsConfirmation(toolName, args);
    }

    return GuardResult.allowed();
  }

  /// Update the loop detector with actual result hash after execution.
  void recordResult(String toolName, Map<String, dynamic> args, String resultContent) {
    final resultHash = ToolLoopDetector.hashResult(resultContent);
    _loopDetector.check(toolName, args, resultHash);
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
