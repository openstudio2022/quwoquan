class ClientStateSyncConfig {
  const ClientStateSyncConfig({
    required this.flushDelay,
    required this.retryDelay,
    required this.maxBatchSize,
    required this.maxPendingAge,
    required this.flushOnForegroundResume,
    required this.flushOnNetworkRecovered,
  });

  final Duration flushDelay;
  final Duration retryDelay;
  final int maxBatchSize;
  final Duration maxPendingAge;
  final bool flushOnForegroundResume;
  final bool flushOnNetworkRecovered;

  factory ClientStateSyncConfig.defaults() {
    return const ClientStateSyncConfig(
      flushDelay: Duration(seconds: 10),
      retryDelay: Duration(minutes: 5),
      maxBatchSize: 20,
      maxPendingAge: Duration(hours: 72),
      flushOnForegroundResume: true,
      flushOnNetworkRecovered: true,
    );
  }

  factory ClientStateSyncConfig.fromMap(
    Map<String, dynamic> map, {
    required ClientStateSyncConfig fallback,
  }) {
    return ClientStateSyncConfig(
      flushDelay: Duration(
        seconds: _int(map['flush_delay_sec'], fallback.flushDelay.inSeconds),
      ),
      retryDelay: Duration(
        seconds: _int(map['retry_delay_sec'], fallback.retryDelay.inSeconds),
      ),
      maxBatchSize: _int(map['max_batch_size'], fallback.maxBatchSize),
      maxPendingAge: Duration(
        seconds: _int(
          map['max_pending_age_sec'],
          fallback.maxPendingAge.inSeconds,
        ),
      ),
      flushOnForegroundResume: _bool(
        map['flush_on_foreground_resume'],
        fallback.flushOnForegroundResume,
      ),
      flushOnNetworkRecovered: _bool(
        map['flush_on_network_recovered'],
        fallback.flushOnNetworkRecovered,
      ),
    );
  }
}

class ClientStateSyncOutboxEntry {
  const ClientStateSyncOutboxEntry({
    required this.coalesceKey,
    required this.objectType,
    required this.objectId,
    required this.intentType,
    required this.desiredBoolValue,
    required this.nextFlushAt,
    this.retryCount = 0,
  });

  final String coalesceKey;
  final String objectType;
  final String objectId;
  final String intentType;
  final bool desiredBoolValue;
  final DateTime nextFlushAt;
  final int retryCount;

  factory ClientStateSyncOutboxEntry.fromMap(Map<String, dynamic> map) {
    return ClientStateSyncOutboxEntry(
      coalesceKey: (map['coalesceKey'] ?? '').toString(),
      objectType: (map['objectType'] ?? '').toString(),
      objectId: (map['objectId'] ?? '').toString(),
      intentType: (map['intentType'] ?? '').toString(),
      desiredBoolValue: map['desiredBoolValue'] == true,
      nextFlushAt:
          DateTime.tryParse(map['nextFlushAt']?.toString() ?? '')?.toUtc() ??
          DateTime.now().toUtc(),
      retryCount: _int(map['retryCount'], 0),
    );
  }

  ClientStateSyncOutboxEntry copyWith({
    String? coalesceKey,
    String? objectType,
    String? objectId,
    String? intentType,
    bool? desiredBoolValue,
    DateTime? nextFlushAt,
    int? retryCount,
  }) {
    return ClientStateSyncOutboxEntry(
      coalesceKey: coalesceKey ?? this.coalesceKey,
      objectType: objectType ?? this.objectType,
      objectId: objectId ?? this.objectId,
      intentType: intentType ?? this.intentType,
      desiredBoolValue: desiredBoolValue ?? this.desiredBoolValue,
      nextFlushAt: nextFlushAt ?? this.nextFlushAt,
      retryCount: retryCount ?? this.retryCount,
    );
  }

  Map<String, dynamic> toMap() {
    return <String, dynamic>{
      'coalesceKey': coalesceKey,
      'objectType': objectType,
      'objectId': objectId,
      'intentType': intentType,
      'desiredBoolValue': desiredBoolValue,
      'nextFlushAt': nextFlushAt.toUtc().toIso8601String(),
      'retryCount': retryCount,
    };
  }
}

class ClientStateSyncOutboxState {
  const ClientStateSyncOutboxState({
    this.entries = const <ClientStateSyncOutboxEntry>[],
  });

  final List<ClientStateSyncOutboxEntry> entries;

  factory ClientStateSyncOutboxState.fromMap(Map<String, dynamic> map) {
    final rawEntries = map['entries'];
    return ClientStateSyncOutboxState(
      entries: rawEntries is List
          ? rawEntries
                .whereType<Map>()
                .map(
                  (entry) => ClientStateSyncOutboxEntry.fromMap(
                    entry.cast<String, dynamic>(),
                  ),
                )
                .toList(growable: false)
          : const <ClientStateSyncOutboxEntry>[],
    );
  }

  ClientStateSyncOutboxState copyWith({
    List<ClientStateSyncOutboxEntry>? entries,
  }) {
    return ClientStateSyncOutboxState(entries: entries ?? this.entries);
  }

  Map<String, dynamic> toMap() {
    return <String, dynamic>{
      'entries': entries.map((entry) => entry.toMap()).toList(growable: false),
    };
  }
}

int _int(Object? value, int fallback) {
  if (value is int) return value;
  if (value is num) return value.toInt();
  return int.tryParse(value?.toString() ?? '') ?? fallback;
}

bool _bool(Object? value, bool fallback) {
  if (value is bool) return value;
  if (value is String) {
    final lower = value.toLowerCase().trim();
    if (lower == 'true') return true;
    if (lower == 'false') return false;
  }
  return fallback;
}
