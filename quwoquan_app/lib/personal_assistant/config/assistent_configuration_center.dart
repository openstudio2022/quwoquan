class AssistentConfigSnapshot {
  const AssistentConfigSnapshot({
    required this.version,
    required this.updatedAt,
    required this.values,
  });

  final String version;
  final DateTime updatedAt;
  final Map<String, dynamic> values;
}

class AssistentConfigurationCenter {
  AssistentConfigSnapshot _snapshot = AssistentConfigSnapshot(
    version: 'v1',
    updatedAt: DateTime.now(),
    values: const <String, dynamic>{},
  );

  AssistentConfigSnapshot current() => _snapshot;

  void update({
    required String version,
    required Map<String, dynamic> values,
  }) {
    _snapshot = AssistentConfigSnapshot(
      version: version,
      updatedAt: DateTime.now(),
      values: values,
    );
  }

  T read<T>(String key, T fallback) {
    final value = _snapshot.values[key];
    if (value is T) return value;
    return fallback;
  }

  String readString(String key, String fallback) {
    final value = _snapshot.values[key];
    if (value is String && value.trim().isNotEmpty) return value;
    return fallback;
  }

  int readInt(String key, int fallback) {
    final value = _snapshot.values[key];
    if (value is int) return value;
    if (value is num) return value.toInt();
    return fallback;
  }

  double readDouble(String key, double fallback) {
    final value = _snapshot.values[key];
    if (value is double) return value;
    if (value is num) return value.toDouble();
    return fallback;
  }

  bool readBool(String key, bool fallback) {
    final value = _snapshot.values[key];
    if (value is bool) return value;
    return fallback;
  }
}

