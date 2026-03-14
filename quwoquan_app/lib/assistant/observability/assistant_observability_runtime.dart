import 'dart:developer' as developer;
import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:quwoquan_app/assistant/providers/assistant_provider_runtime.dart';

class AssistantSloTarget {
  const AssistantSloTarget({
    required this.maxP95LatencyMs,
    required this.minAvailability,
    required this.maxErrorRate,
  });

  final int maxP95LatencyMs;
  final double minAvailability;
  final double maxErrorRate;
}

class AssistantSloEvent {
  const AssistantSloEvent({
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

class AssistantSloSnapshot {
  const AssistantSloSnapshot({
    required this.windowMinutes,
    required this.p95LatencyMs,
    required this.availability,
    required this.errorRate,
  });

  final int windowMinutes;
  final int p95LatencyMs;
  final double availability;
  final double errorRate;

  bool isHealthy(AssistantSloTarget target) {
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

enum AssistantSloAlertSeverity {
  warning,
  critical,
}

class AssistantSloAlert {
  const AssistantSloAlert({
    required this.providerId,
    required this.severity,
    required this.message,
    required this.snapshot,
    required this.timestamp,
  });

  final String providerId;
  final AssistantSloAlertSeverity severity;
  final String message;
  final AssistantSloSnapshot snapshot;
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

class AssistantSloMonitor {
  AssistantSloMonitor({
    AssistantSloTarget defaultTarget = const AssistantSloTarget(
      maxP95LatencyMs: 2800,
      minAvailability: 0.985,
      maxErrorRate: 0.015,
    ),
  }) : _defaultTarget = defaultTarget;

  final AssistantSloTarget _defaultTarget;
  final Map<String, List<AssistantSloEvent>> _eventsByProvider =
      <String, List<AssistantSloEvent>>{};
  final Map<String, AssistantSloTarget> _targetByProvider =
      <String, AssistantSloTarget>{};

  AssistantSloSnapshot evaluate({
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
    return AssistantSloSnapshot(
      windowMinutes: windowMinutes,
      p95LatencyMs: p95,
      availability: availability,
      errorRate: errorRate,
    );
  }

  void setTarget(String providerId, AssistantSloTarget target) {
    _targetByProvider[providerId] = target;
  }

  void record({
    required String providerId,
    required int latencyMs,
    required bool success,
  }) {
    final list = _eventsByProvider.putIfAbsent(
      providerId,
      () => <AssistantSloEvent>[],
    );
    list.add(
      AssistantSloEvent(
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

  AssistantSloSnapshot snapshotForProvider({
    required String providerId,
    int windowMinutes = 5,
  }) {
    final now = DateTime.now();
    final cutoff = now.subtract(Duration(minutes: windowMinutes));
    final events = (_eventsByProvider[providerId] ?? const <AssistantSloEvent>[])
        .where((event) => event.timestamp.isAfter(cutoff))
        .toList(growable: false);
    final latencies = events
        .map((event) => event.latencyMs)
        .toList(growable: false);
    final failed = events.where((event) => !event.success).length;
    return evaluate(
      windowMinutes: windowMinutes,
      latenciesMs: latencies,
      totalRequests: events.length,
      failedRequests: failed,
    );
  }

  AssistantSloAlert? evaluateAlert({
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
    final severity = isCritical
        ? AssistantSloAlertSeverity.critical
        : AssistantSloAlertSeverity.warning;
    return AssistantSloAlert(
      providerId: providerId,
      severity: severity,
      message:
          'SLO violation provider=$providerId p95=${snapshot.p95LatencyMs} availability=${snapshot.availability.toStringAsFixed(4)} errorRate=${snapshot.errorRate.toStringAsFixed(4)}',
      snapshot: snapshot,
      timestamp: DateTime.now(),
    );
  }
}

class AssistantProviderRoutingContext {
  const AssistantProviderRoutingContext({
    required this.capability,
    required this.channel,
    required this.deviceProfile,
    required this.latencySensitive,
    required this.costSensitive,
    this.availabilityThreshold = 0.0,
    this.region = '',
  });

  final String capability;
  final String channel;
  final String deviceProfile;
  final bool latencySensitive;
  final bool costSensitive;
  final double availabilityThreshold;
  final String region;
}

class AssistantProviderPolicy {
  const AssistantProviderPolicy();

  AssistantProviderDescriptor? pickProvider({
    required AssistantProviderRoutingContext context,
    required List<AssistantProviderDescriptor> candidates,
    required Map<String, bool> healthMap,
    required Map<String, AssistantSloSnapshot> sloMap,
  }) {
    if (candidates.isEmpty) return null;
    final enabled = candidates.where((c) => c.enabled).toList(growable: false);
    if (enabled.isEmpty) return null;
    final alive = enabled.where((candidate) {
      final healthy = healthMap[candidate.id] ?? true;
      return healthy;
    }).toList(growable: false);
    if (alive.isEmpty) return enabled.first;
    final scored = alive.map((candidate) {
      final costWeight =
          (candidate.metadata['costWeight'] as num?)?.toDouble() ?? 1.0;
      final latencyWeight =
          (candidate.metadata['latencyWeight'] as num?)?.toDouble() ?? 1.0;
      final availabilityWeight =
          (candidate.metadata['availabilityWeight'] as num?)?.toDouble() ?? 1.0;
      final slo = sloMap[candidate.id];
      final errorRate = slo?.errorRate ?? 0.0;
      final availability = slo?.availability ?? 1.0;
      final p95Latency = (slo?.p95LatencyMs ?? 0).toDouble();
      var score = 0.0;
      if (context.costSensitive) score += costWeight * 1.5;
      if (context.latencySensitive) score += latencyWeight * 1.4;
      score += errorRate * 5.0;
      score += (1.0 - availability) * availabilityWeight * 4.0;
      score += p95Latency / 5000.0;
      if (context.availabilityThreshold > 0 &&
          availability < context.availabilityThreshold) {
        score += 1000;
      }
      return (candidate: candidate, score: score);
    }).toList(growable: false)
      ..sort((a, b) => a.score.compareTo(b.score));
    if (scored.isNotEmpty) {
      return scored.first.candidate;
    }
    return alive.first;
  }
}

class AssistantAlertDispatcher {
  AssistantAlertDispatcher({
    String? webhookUrl,
    String? feishuBotWebhook,
    int? suppressWindowSeconds,
    bool? logChannelEnabled,
  }) : _webhookUrl = webhookUrl ?? '',
       _feishuBotWebhook = feishuBotWebhook ?? '',
       _suppressWindowSeconds = suppressWindowSeconds ?? 180,
       _logChannelEnabled = logChannelEnabled ?? true;

  final List<AssistantSloAlert> _alerts = <AssistantSloAlert>[];
  final Map<String, DateTime> _lastDispatchAt = <String, DateTime>{};
  final String _webhookUrl;
  final String _feishuBotWebhook;
  final int _suppressWindowSeconds;
  final bool _logChannelEnabled;

  Map<String, dynamic> routingConfig() {
    return <String, dynamic>{
      'logEnabled': _logChannelEnabled,
      'webhookEnabled': _webhookUrl.trim().isNotEmpty,
      'feishuWebhookEnabled': _feishuBotWebhook.trim().isNotEmpty,
      'suppressWindowSeconds': _suppressWindowSeconds,
    };
  }

  Future<void> dispatch(AssistantSloAlert alert) async {
    final key = '${alert.providerId}:${alert.severity.name}';
    final now = DateTime.now();
    final last = _lastDispatchAt[key];
    if (last != null &&
        now.difference(last).inSeconds < _suppressWindowSeconds) {
      return;
    }
    _lastDispatchAt[key] = now;
    _alerts.add(alert);
    if (_alerts.length > 2000) {
      _alerts.removeRange(0, _alerts.length - 2000);
    }
    if (_logChannelEnabled) {
      developer.log(
        jsonEncode(alert.toJson()),
        name: 'assistant.alert',
      );
    }
    await _dispatchWebhook(alert);
    await _dispatchFeishu(alert);
  }

  List<AssistantSloAlert> listRecent({int limit = 50}) {
    if (_alerts.length <= limit) {
      return List<AssistantSloAlert>.from(_alerts.reversed);
    }
    final start = _alerts.length - limit;
    return _alerts.sublist(start).reversed.toList(growable: false);
  }

  Future<AssistantSloAlert> dispatchSynthetic({
    required String providerId,
    required AssistantSloAlertSeverity severity,
    required String message,
  }) async {
    final alert = AssistantSloAlert(
      providerId: providerId,
      severity: severity,
      message: message,
      snapshot: const AssistantSloSnapshot(
        windowMinutes: 5,
        p95LatencyMs: 9999,
        availability: 0.7,
        errorRate: 0.3,
      ),
      timestamp: DateTime.now(),
    );
    await dispatch(alert);
    return alert;
  }

  Future<void> _dispatchWebhook(AssistantSloAlert alert) async {
    if (_webhookUrl.trim().isEmpty) return;
    try {
      await http.post(
        Uri.parse(_webhookUrl),
        headers: const <String, String>{'Content-Type': 'application/json'},
        body: jsonEncode(<String, dynamic>{
          'source': 'assistant_v1',
          'alert': alert.toJson(),
        }),
      );
    } catch (_) {
      // noop
    }
  }

  Future<void> _dispatchFeishu(AssistantSloAlert alert) async {
    if (_feishuBotWebhook.trim().isEmpty) return;
    final text =
        'Assistant SLO Alert\nprovider=${alert.providerId}\nseverity=${alert.severity.name}\nmessage=${alert.message}';
    try {
      await http.post(
        Uri.parse(_feishuBotWebhook),
        headers: const <String, String>{'Content-Type': 'application/json'},
        body: jsonEncode(<String, dynamic>{
          'msg_type': 'text',
          'content': <String, dynamic>{'text': text},
        }),
      );
    } catch (_) {
      // noop
    }
  }
}
