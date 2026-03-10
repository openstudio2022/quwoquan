class PreferenceFact {
  const PreferenceFact({
    required this.factId,
    required this.scope,
    required this.key,
    required this.value,
    this.source = '',
    this.createdAt = '',
    this.revoked = false,
  });

  final String factId;
  final String scope;
  final String key;
  final String value;
  final String source;
  final String createdAt;
  final bool revoked;

  Map<String, dynamic> toJson() => <String, dynamic>{
    'factId': factId,
    'scope': scope,
    'key': key,
    'value': value,
    'source': source,
    'createdAt': createdAt,
    'revoked': revoked,
  };

  factory PreferenceFact.fromJson(Map<String, dynamic> json) {
    return PreferenceFact(
      factId: (json['factId'] as String?)?.trim() ?? '',
      scope: (json['scope'] as String?)?.trim() ?? '',
      key: (json['key'] as String?)?.trim() ?? '',
      value: (json['value'] as String?)?.trim() ?? '',
      source: (json['source'] as String?)?.trim() ?? '',
      createdAt: (json['createdAt'] as String?)?.trim() ?? '',
      revoked: json['revoked'] == true,
    );
  }
}
