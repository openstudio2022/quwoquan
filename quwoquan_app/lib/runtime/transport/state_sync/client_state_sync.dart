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
        seconds: _positiveIntOrFallback(
          map,
          'flush_delay_sec',
          fallback.flushDelay.inSeconds,
        ),
      ),
      retryDelay: Duration(
        seconds: _positiveIntOrFallback(
          map,
          'retry_delay_sec',
          fallback.retryDelay.inSeconds,
        ),
      ),
      maxBatchSize: _positiveIntOrFallback(
        map,
        'max_batch_size',
        fallback.maxBatchSize,
      ),
      maxPendingAge: Duration(
        seconds: _positiveIntOrFallback(
          map,
          'max_pending_age_sec',
          fallback.maxPendingAge.inSeconds,
        ),
      ),
      flushOnForegroundResume: _boolOrFallback(
        map,
        'flush_on_foreground_resume',
        fallback.flushOnForegroundResume,
      ),
      flushOnNetworkRecovered: _boolOrFallback(
        map,
        'flush_on_network_recovered',
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
    required this.firstQueuedAt,
    this.sourceSurfaceId = '',
    this.confirmedBoolValue,
    this.retryCount = 0,
  });

  final String coalesceKey;
  final String objectType;
  final String objectId;
  final String intentType;
  final bool desiredBoolValue;
  final DateTime nextFlushAt;

  /// 首次入队时间：coalesce 更新不重置，是 `maxPendingAge` 终态判定的唯一依据。
  final DateTime firstQueuedAt;

  final String sourceSurfaceId;
  final bool? confirmedBoolValue;
  final int retryCount;

  bool get hasPendingDelta =>
      confirmedBoolValue == null || confirmedBoolValue != desiredBoolValue;

  factory ClientStateSyncOutboxEntry.fromMap(Map<String, dynamic> map) {
    const allowedKeys = <String>{
      'coalesceKey',
      'objectType',
      'objectId',
      'intentType',
      'desiredBoolValue',
      'sourceSurfaceId',
      'nextFlushAt',
      'firstQueuedAt',
      'confirmedBoolValue',
      'retryCount',
    };
    if (!allowedKeys.containsAll(map.keys)) {
      throw const FormatException('unknown client state sync outbox field');
    }
    final coalesceKey = _requiredText(map, 'coalesceKey');
    final objectType = _requiredText(map, 'objectType');
    final objectId = _requiredText(map, 'objectId');
    final intentType = _requiredText(map, 'intentType');
    if (coalesceKey != '$objectType:$intentType:$objectId') {
      throw const FormatException('invalid client state sync coalesceKey');
    }
    final desiredBoolValue = map['desiredBoolValue'];
    if (desiredBoolValue is! bool) {
      throw const FormatException('invalid desiredBoolValue');
    }
    final sourceSurfaceId = map['sourceSurfaceId'];
    if (sourceSurfaceId != null && sourceSurfaceId is! String) {
      throw const FormatException('invalid sourceSurfaceId');
    }
    final rawNextFlushAt = map['nextFlushAt'];
    final nextFlushAt = rawNextFlushAt is String
        ? DateTime.tryParse(rawNextFlushAt)?.toUtc()
        : null;
    if (nextFlushAt == null) {
      throw const FormatException('invalid nextFlushAt');
    }
    final rawFirstQueuedAt = map['firstQueuedAt'];
    DateTime? firstQueuedAt;
    if (rawFirstQueuedAt == null) {
      // 一次性 schema 演进：旧记录缺首次入队时间时以 nextFlushAt 初始化，
      // 写回后即带新字段；不保留长期双读。
      firstQueuedAt = nextFlushAt;
    } else if (rawFirstQueuedAt is String) {
      firstQueuedAt = DateTime.tryParse(rawFirstQueuedAt)?.toUtc();
    }
    if (firstQueuedAt == null) {
      throw const FormatException('invalid firstQueuedAt');
    }
    final confirmedBoolValue = map['confirmedBoolValue'];
    if (confirmedBoolValue != null && confirmedBoolValue is! bool) {
      throw const FormatException('invalid confirmedBoolValue');
    }
    final retryCount = map['retryCount'];
    if (retryCount is! int || retryCount < 0) {
      throw const FormatException('invalid retryCount');
    }
    return ClientStateSyncOutboxEntry(
      coalesceKey: coalesceKey,
      objectType: objectType,
      objectId: objectId,
      intentType: intentType,
      desiredBoolValue: desiredBoolValue,
      sourceSurfaceId: sourceSurfaceId as String? ?? '',
      nextFlushAt: nextFlushAt,
      firstQueuedAt: firstQueuedAt,
      confirmedBoolValue: confirmedBoolValue as bool?,
      retryCount: retryCount,
    );
  }

  ClientStateSyncOutboxEntry copyWith({
    String? coalesceKey,
    String? objectType,
    String? objectId,
    String? intentType,
    bool? desiredBoolValue,
    DateTime? nextFlushAt,
    DateTime? firstQueuedAt,
    String? sourceSurfaceId,
    bool? confirmedBoolValue,
    int? retryCount,
  }) {
    return ClientStateSyncOutboxEntry(
      coalesceKey: coalesceKey ?? this.coalesceKey,
      objectType: objectType ?? this.objectType,
      objectId: objectId ?? this.objectId,
      intentType: intentType ?? this.intentType,
      desiredBoolValue: desiredBoolValue ?? this.desiredBoolValue,
      nextFlushAt: nextFlushAt ?? this.nextFlushAt,
      firstQueuedAt: firstQueuedAt ?? this.firstQueuedAt,
      sourceSurfaceId: sourceSurfaceId ?? this.sourceSurfaceId,
      confirmedBoolValue: confirmedBoolValue ?? this.confirmedBoolValue,
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
      'firstQueuedAt': firstQueuedAt.toUtc().toIso8601String(),
      if (sourceSurfaceId.isNotEmpty) 'sourceSurfaceId': sourceSurfaceId,
      'confirmedBoolValue': confirmedBoolValue,
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
    if (map.length != 1 || map['entries'] is! List) {
      throw const FormatException('invalid client state sync outbox');
    }
    final rawEntries = map['entries'];
    return ClientStateSyncOutboxState(
      entries: (rawEntries! as List<Object?>)
          .map((entry) {
            if (entry is! Map<String, dynamic>) {
              throw const FormatException('invalid client state sync entry');
            }
            return ClientStateSyncOutboxEntry.fromMap(entry);
          })
          .toList(growable: false),
    );
  }

  ClientStateSyncOutboxState copyWith({
    List<ClientStateSyncOutboxEntry>? entries,
  }) {
    return ClientStateSyncOutboxState(entries: entries ?? this.entries);
  }

  ClientStateSyncOutboxEntry? entryFor({
    required String objectType,
    required String objectId,
    required String intentType,
  }) {
    final coalesceKey = '$objectType:$intentType:$objectId';
    for (final entry in entries.reversed) {
      if (entry.coalesceKey == coalesceKey) {
        return entry;
      }
    }
    return null;
  }

  Map<String, dynamic> toMap() {
    return <String, dynamic>{
      'entries': entries.map((entry) => entry.toMap()).toList(growable: false),
    };
  }
}

int _positiveIntOrFallback(Map<String, dynamic> map, String key, int fallback) {
  final value = map[key];
  if (value == null) return fallback;
  if (value is! int || value <= 0) {
    throw FormatException('invalid $key');
  }
  return value;
}

bool _boolOrFallback(Map<String, dynamic> map, String key, bool fallback) {
  final value = map[key];
  if (value == null) return fallback;
  if (value is! bool) {
    throw FormatException('invalid $key');
  }
  return value;
}

String _requiredText(Map<String, dynamic> map, String key) {
  final value = map[key];
  if (value is! String || value.isEmpty || value != value.trim()) {
    throw FormatException('invalid $key');
  }
  return value;
}
