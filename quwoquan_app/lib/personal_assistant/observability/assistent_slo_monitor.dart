class AssistentSloTarget {
  const AssistentSloTarget({
    required this.maxP95LatencyMs,
    required this.minAvailability,
    required this.maxErrorRate,
  });

  final int maxP95LatencyMs;
  final double minAvailability;
  final double maxErrorRate;
}

class AssistentSloEvent {
  const AssistentSloEvent({
    required this.providerId,
    required this.latencyMs,
    required this.success,
    required this.timestamp,
  });

  final String providerId;
  final int latencyMs;
  final bool success;
  final DateTime timestamp;
}

class AssistentSloSnapshot {
  const AssistentSloSnapshot({
    required this.windowMinutes,
    required this.p95LatencyMs,
    required this.availability,
    required this.errorRate,
  });

  final int windowMinutes;
  final int p95LatencyMs;
  final double availability;
  final double errorRate;

  bool isHealthy(AssistentSloTarget target) {
    return p95LatencyMs <= target.maxP95LatencyMs &&
        availability >= target.minAvailability &&
        errorRate <= target.maxErrorRate;
  }

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'windowMinutes': windowMinutes,
      'p95LatencyMs': p95LatencyMs,
      'availability': availability,
      'errorRate': errorRate,
    };
  }
}

enum AssistentSloAlertSeverity {
  warning,
  critical,
}

class AssistentSloAlert {
  const AssistentSloAlert({
    required this.providerId,
    required this.severity,
    required this.message,
    required this.snapshot,
    required this.timestamp,
  });

  final String providerId;
  final AssistentSloAlertSeverity severity;
  final String message;
  final AssistentSloSnapshot snapshot;
  final DateTime timestamp;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'providerId': providerId,
      'severity': severity.name,
      'message': message,
      'snapshot': snapshot.toJson(),
      'timestamp': timestamp.toIso8601String(),
    };
  }
}

class AssistentSloMonitor {
  AssistentSloMonitor({
    AssistentSloTarget defaultTarget = const AssistentSloTarget(
      maxP95LatencyMs: 2800,
      minAvailability: 0.985,
      maxErrorRate: 0.015,
    ),
  }) : _defaultTarget = defaultTarget;

  final AssistentSloTarget _defaultTarget;
  final Map<String, List<AssistentSloEvent>> _eventsByProvider =
      <String, List<AssistentSloEvent>>{};
  final Map<String, AssistentSloTarget> _targetByProvider = <String, AssistentSloTarget>{};

  AssistentSloSnapshot evaluate({
    required int windowMinutes,
    required List<int> latenciesMs,
    required int totalRequests,
    required int failedRequests,
  }) {
    final sorted = List<int>.from(latenciesMs)..sort();
    final p95Index = sorted.isEmpty ? 0 : ((sorted.length - 1) * 0.95).floor();
    final p95 = sorted.isEmpty ? 0 : sorted[p95Index];
    final availability = totalRequests == 0
        ? 1.0
        : (totalRequests - failedRequests) / totalRequests;
    final errorRate = totalRequests == 0 ? 0.0 : failedRequests / totalRequests;
    return AssistentSloSnapshot(
      windowMinutes: windowMinutes,
      p95LatencyMs: p95,
      availability: availability,
      errorRate: errorRate,
    );
  }

  void setTarget(String providerId, AssistentSloTarget target) {
    _targetByProvider[providerId] = target;
  }

  void record({
    required String providerId,
    required int latencyMs,
    required bool success,
  }) {
    final list = _eventsByProvider.putIfAbsent(providerId, () => <AssistentSloEvent>[]);
    list.add(
      AssistentSloEvent(
        providerId: providerId,
        latencyMs: latencyMs,
        success: success,
        timestamp: DateTime.now(),
      ),
    );
    if (list.length > 4000) {
      list.removeRange(0, list.length - 4000);
    }
  }

  AssistentSloSnapshot snapshotForProvider({
    required String providerId,
    int windowMinutes = 5,
  }) {
    final now = DateTime.now();
    final cutoff = now.subtract(Duration(minutes: windowMinutes));
    final events = (_eventsByProvider[providerId] ?? const <AssistentSloEvent>[])
        .where((event) => event.timestamp.isAfter(cutoff))
        .toList(growable: false);
    final latencies = events.map((event) => event.latencyMs).toList(growable: false);
    final failed = events.where((event) => !event.success).length;
    return evaluate(
      windowMinutes: windowMinutes,
      latenciesMs: latencies,
      totalRequests: events.length,
      failedRequests: failed,
    );
  }

  AssistentSloAlert? evaluateAlert({
    required String providerId,
    int windowMinutes = 5,
  }) {
    final snapshot = snapshotForProvider(
      providerId: providerId,
      windowMinutes: windowMinutes,
    );
    final target = _targetByProvider[providerId] ?? _defaultTarget;
    if (snapshot.isHealthy(target)) return null;
    final isCritical = snapshot.errorRate > (target.maxErrorRate * 2) ||
        snapshot.availability < (target.minAvailability - 0.02);
    final severity =
        isCritical ? AssistentSloAlertSeverity.critical : AssistentSloAlertSeverity.warning;
    return AssistentSloAlert(
      providerId: providerId,
      severity: severity,
      message:
          'SLO violation provider=$providerId p95=${snapshot.p95LatencyMs} availability=${snapshot.availability.toStringAsFixed(4)} errorRate=${snapshot.errorRate.toStringAsFixed(4)}',
      snapshot: snapshot,
      timestamp: DateTime.now(),
    );
  }
}

