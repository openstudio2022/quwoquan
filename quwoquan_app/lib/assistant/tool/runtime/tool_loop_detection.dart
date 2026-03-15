import 'dart:convert';
import 'package:crypto/crypto.dart';

/// Result of running loop detection against the current call history.
class LoopDetectionResult {
  const LoopDetectionResult({
    required this.detected,
    this.pattern = '',
    this.severity = LoopSeverity.none,
    this.message = '',
    this.streak = 0,
  });

  static const LoopDetectionResult clear = LoopDetectionResult(detected: false);

  final bool detected;
  final String pattern;
  final LoopSeverity severity;
  final String message;
  final int streak;
}

enum LoopSeverity { none, warning, critical }

/// A single recorded tool call with input/output hashes.
class ToolCallRecord {
  ToolCallRecord({
    required this.toolName,
    required this.argsHash,
    required this.timestamp,
    this.resultHash,
    this.success = true,
  });

  final String toolName;
  final String argsHash;
  final DateTime timestamp;
  String? resultHash;
  bool success;
}

/// Tracks tool call history and detects 3 types of loops, inspired by
/// OpenClaw's `tool-loop-detection.ts`.
class ToolCallHistory {
  ToolCallHistory({
    this.genericRepeatWarning = 3,
    this.genericRepeatCritical = 5,
    this.pingPongWarning = 4,
    this.pingPongCritical = 6,
    this.globalCircuitBreaker = 10,
  });

  final int genericRepeatWarning;
  final int genericRepeatCritical;
  final int pingPongWarning;
  final int pingPongCritical;
  final int globalCircuitBreaker;

  final List<ToolCallRecord> _records = <ToolCallRecord>[];

  List<ToolCallRecord> get records => List<ToolCallRecord>.unmodifiable(_records);

  /// Hash tool name + sorted arguments for deduplication.
  static String hashToolCall(String toolName, Map<String, dynamic> args) {
    final sortedKeys = args.keys.toList()..sort();
    final normalized = <String, dynamic>{};
    for (final key in sortedKeys) {
      if (key.startsWith('__')) continue;
      normalized[key] = args[key];
    }
    final payload = '$toolName:${jsonEncode(normalized)}';
    return sha256.convert(utf8.encode(payload)).toString().substring(0, 16);
  }

  /// Hash tool result for outcome comparison.
  static String hashToolOutcome(bool success, String message, Map<String, dynamic>? data) {
    final keys = data?.keys.toList()?..sort();
    final payload = '$success:$message:${keys?.join(",")}';
    return sha256.convert(utf8.encode(payload)).toString().substring(0, 16);
  }

  /// Record a tool call (before execution).
  ToolCallRecord recordCall(String toolName, Map<String, dynamic> args) {
    final record = ToolCallRecord(
      toolName: toolName,
      argsHash: hashToolCall(toolName, args),
      timestamp: DateTime.now(),
    );
    _records.add(record);
    return record;
  }

  /// Record the outcome (after execution).
  void recordOutcome(ToolCallRecord record, bool success, String message, Map<String, dynamic>? data) {
    record.resultHash = hashToolOutcome(success, message, data);
    record.success = success;
  }

  /// Run all 3 detectors and return the most severe result.
  LoopDetectionResult detectLoop() {
    if (_records.length < 2) return LoopDetectionResult.clear;

    final results = <LoopDetectionResult>[
      _detectGenericRepeat(),
      _detectPingPong(),
      _detectGlobalCircuitBreaker(),
    ];

    LoopDetectionResult worst = LoopDetectionResult.clear;
    for (final r in results) {
      if (r.detected && r.severity.index > worst.severity.index) {
        worst = r;
      }
    }
    return worst;
  }

  /// Detector 1: Same tool + same args hash repeated N times.
  LoopDetectionResult _detectGenericRepeat() {
    if (_records.length < genericRepeatWarning) return LoopDetectionResult.clear;

    final last = _records.last;
    int streak = 0;
    for (int i = _records.length - 1; i >= 0; i--) {
      final r = _records[i];
      if (r.toolName == last.toolName && r.argsHash == last.argsHash) {
        streak++;
      } else {
        break;
      }
    }

    if (streak >= genericRepeatCritical) {
      return LoopDetectionResult(
        detected: true,
        pattern: 'generic_repeat',
        severity: LoopSeverity.critical,
        message: '检测到重复操作：${last.toolName} 已连续相同调用 $streak 次',
        streak: streak,
      );
    }
    if (streak >= genericRepeatWarning) {
      return LoopDetectionResult(
        detected: true,
        pattern: 'generic_repeat',
        severity: LoopSeverity.warning,
        message: '${last.toolName} 连续相同调用 $streak 次，尝试其他方式',
        streak: streak,
      );
    }
    return LoopDetectionResult.clear;
  }

  /// Detector 2: A→B→A→B alternating pattern with no progress.
  LoopDetectionResult _detectPingPong() {
    if (_records.length < 4) return LoopDetectionResult.clear;

    int alternations = 0;
    for (int i = _records.length - 1; i >= 2; i -= 2) {
      final a = _records[i];
      final b = _records[i - 1];
      final prevA = _records[i - 2];

      if (a.toolName == prevA.toolName &&
          a.argsHash == prevA.argsHash &&
          a.toolName != b.toolName) {
        final aNoProgress = a.resultHash != null &&
            prevA.resultHash != null &&
            a.resultHash == prevA.resultHash;
        if (aNoProgress) {
          alternations++;
        } else {
          break;
        }
      } else {
        break;
      }
    }

    final totalSteps = alternations * 2 + 2;
    if (totalSteps >= pingPongCritical) {
      return LoopDetectionResult(
        detected: true,
        pattern: 'ping_pong',
        severity: LoopSeverity.critical,
        message: '检测到反复尝试，已切换策略',
        streak: totalSteps,
      );
    }
    if (totalSteps >= pingPongWarning) {
      return LoopDetectionResult(
        detected: true,
        pattern: 'ping_pong',
        severity: LoopSeverity.warning,
        message: '检测到交替调用模式，尝试其他方式',
        streak: totalSteps,
      );
    }
    return LoopDetectionResult.clear;
  }

  /// Detector 3: Global circuit breaker - too many calls with no new results.
  LoopDetectionResult _detectGlobalCircuitBreaker() {
    if (_records.length < globalCircuitBreaker) return LoopDetectionResult.clear;

    final recentRecords = _records.length > globalCircuitBreaker
        ? _records.sublist(_records.length - globalCircuitBreaker)
        : _records;

    final uniqueResults = <String>{};
    for (final r in recentRecords) {
      if (r.resultHash != null) uniqueResults.add(r.resultHash!);
    }

    if (uniqueResults.length <= 2) {
      return LoopDetectionResult(
        detected: true,
        pattern: 'global_circuit_breaker',
        severity: LoopSeverity.critical,
        message: '多次尝试未获得新信息，基于已有信息回答',
        streak: recentRecords.length,
      );
    }
    return LoopDetectionResult.clear;
  }

  void clear() => _records.clear();
}
