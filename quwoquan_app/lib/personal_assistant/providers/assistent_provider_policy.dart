import 'package:quwoquan_app/personal_assistant/providers/assistent_provider_registry.dart';
import 'package:quwoquan_app/personal_assistant/observability/assistent_slo_monitor.dart';

class AssistentProviderRoutingContext {
  const AssistentProviderRoutingContext({
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

class AssistentProviderPolicy {
  const AssistentProviderPolicy();

  AssistentProviderDescriptor? pickProvider({
    required AssistentProviderRoutingContext context,
    required List<AssistentProviderDescriptor> candidates,
    required Map<String, bool> healthMap,
    required Map<String, AssistentSloSnapshot> sloMap,
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
      final costWeight = (candidate.metadata['costWeight'] as num?)?.toDouble() ?? 1.0;
      final latencyWeight = (candidate.metadata['latencyWeight'] as num?)?.toDouble() ?? 1.0;
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
      if (context.availabilityThreshold > 0 && availability < context.availabilityThreshold) {
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

