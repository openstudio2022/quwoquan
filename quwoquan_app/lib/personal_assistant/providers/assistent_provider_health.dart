import 'dart:async';

import 'package:quwoquan_app/personal_assistant/providers/assistent_provider_registry.dart';

class AssistentProviderHealthSnapshot {
  const AssistentProviderHealthSnapshot({
    required this.providerId,
    required this.ok,
    required this.timestamp,
    this.message = '',
  });

  final String providerId;
  final bool ok;
  final DateTime timestamp;
  final String message;
}

class AssistentProviderHealthService {
  final Map<String, AssistentProviderHealthSnapshot> _latest =
      <String, AssistentProviderHealthSnapshot>{};

  Future<void> probe(AssistentProviderDescriptor descriptor) async {
    _latest[descriptor.id] = AssistentProviderHealthSnapshot(
      providerId: descriptor.id,
      ok: descriptor.enabled,
      timestamp: DateTime.now(),
      message: descriptor.enabled ? 'healthy' : 'disabled',
    );
  }

  List<AssistentProviderHealthSnapshot> snapshots() {
    return _latest.values.toList(growable: false);
  }

  Map<String, bool> healthMap() {
    final map = <String, bool>{};
    for (final snapshot in _latest.values) {
      map[snapshot.providerId] = snapshot.ok;
    }
    return map;
  }
}

