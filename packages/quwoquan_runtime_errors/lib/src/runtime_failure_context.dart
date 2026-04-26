class RuntimeFailureContext {
  const RuntimeFailureContext({
    this.attributes = const <RuntimeContextAttribute>[],
  });

  factory RuntimeFailureContext.fromJson(Map<String, dynamic>? json) {
    final rawAttributes = json == null ? null : json['attributes'];
    final attributes = rawAttributes is List
        ? rawAttributes
              .whereType<Map>()
              .map(
                (item) => RuntimeContextAttribute.fromJson(
                  item.cast<String, dynamic>(),
                ),
              )
              .toList(growable: false)
        : const <RuntimeContextAttribute>[];
    return RuntimeFailureContext(attributes: attributes);
  }

  final List<RuntimeContextAttribute> attributes;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'attributes': attributes
          .map((item) => item.toJson())
          .toList(growable: false),
    };
  }

  RuntimeFailureContext normalized() {
    final filtered = <RuntimeContextAttribute>[];
    for (final attribute in attributes) {
      if (attribute.key.trim().isEmpty) continue;
      filtered.add(attribute.normalized());
    }
    return RuntimeFailureContext(attributes: filtered);
  }
}

class RuntimeContextAttribute {
  const RuntimeContextAttribute({required this.key, required this.value});

  factory RuntimeContextAttribute.fromJson(Map<String, dynamic> json) {
    return RuntimeContextAttribute(
      key: (json['key'] as String?) ?? '',
      value: _stringValue(json['value']),
    ).normalized();
  }

  final String key;
  final String value;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{'key': key, 'value': value};
  }

  RuntimeContextAttribute normalized() {
    return RuntimeContextAttribute(key: key.trim(), value: value.trim());
  }
}

String _stringValue(Object? raw) {
  if (raw == null) return '';
  if (raw is String) return raw;
  if (raw is num || raw is bool) return raw.toString();
  return raw.toString();
}
