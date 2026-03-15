import 'dart:collection';
import 'dart:convert';
import 'package:crypto/crypto.dart' show md5;

class LoopResult {
  const LoopResult._({required this.blocked, this.reason = ''});

  factory LoopResult.ok() => const LoopResult._(blocked: false);
  factory LoopResult.blocked(String reason) =>
      LoopResult._(blocked: true, reason: reason);

  final bool blocked;
  final String reason;
}

class _CallRecord {
  const _CallRecord(this.argsHash, this.resultHash);
  final String argsHash;
  final String? resultHash;
}

/// Detects tool call loops using three strategies:
/// 1. Duplicate call detection (same tool + same args)
/// 2. No-progress detection (same result hash)
/// 3. Global circuit breaker (total call count)
class ToolLoopDetector {
  static const int _historySize = 20;
  static const int _criticalRepeatCount = 4;
  static const int _sameResultThreshold = 3;

  final _history = Queue<_CallRecord>();

  void reset() => _history.clear();

  LoopResult check(
    String toolName,
    Map<String, dynamic> args,
    String? resultHash,
  ) {
    final argsHash = _hash(toolName, args);

    final repeats = _history.where((c) => c.argsHash == argsHash).length;
    if (repeats >= _criticalRepeatCount) {
      return LoopResult.blocked('$toolName 相同参数已调用 $repeats 次');
    }

    if (resultHash != null) {
      final sameResults = _history
          .where((c) => c.argsHash == argsHash && c.resultHash == resultHash)
          .length;
      if (sameResults >= _sameResultThreshold) {
        return LoopResult.blocked('$toolName 连续返回相同结果');
      }
    }

    if (_history.length >= _historySize) {
      return LoopResult.blocked('工具调用总数达上限 ($_historySize)');
    }

    _history.addLast(_CallRecord(argsHash, resultHash));
    return LoopResult.ok();
  }

  static String _hash(String toolName, Map<String, dynamic> args) {
    final canonical = '$toolName:${jsonEncode(args)}';
    return md5.convert(utf8.encode(canonical)).toString();
  }

  static String hashResult(String content) {
    return md5.convert(utf8.encode(content)).toString();
  }
}
