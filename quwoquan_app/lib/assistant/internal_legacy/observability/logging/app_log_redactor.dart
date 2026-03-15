class AppLogRedactor {
  const AppLogRedactor();

  static const String _masked = '***';
  static const List<String> _sensitiveKeyTokens = <String>[
    'authorization',
    'api_key',
    'apikey',
    'token',
    'secret',
    'password',
    'cookie',
    'phone',
    'mobile',
    'email',
  ];

  Map<String, dynamic> redactMap(Map<String, dynamic> input) {
    final out = <String, dynamic>{};
    input.forEach((key, value) {
      out[key] = _redactValue(key: key, value: value);
    });
    return out;
  }

  dynamic _redactValue({required String key, required dynamic value}) {
    if (_isSensitiveKey(key)) {
      return _masked;
    }
    if (value is Map) {
      final map = <String, dynamic>{};
      value.forEach((k, v) {
        map['$k'] = _redactValue(key: '$k', value: v);
      });
      return map;
    }
    if (value is Iterable) {
      return value
          .map((item) => _redactValue(key: key, value: item))
          .toList(growable: false);
    }
    if (value is String && _looksSensitiveText(value)) {
      return _masked;
    }
    return value;
  }

  bool _isSensitiveKey(String key) {
    final lowered = key.toLowerCase();
    for (final token in _sensitiveKeyTokens) {
      if (lowered.contains(token)) {
        return true;
      }
    }
    return false;
  }

  bool _looksSensitiveText(String text) {
    final lowered = text.toLowerCase();
    if (lowered.startsWith('bearer ')) {
      return true;
    }
    if (RegExp(r'^[A-Za-z0-9_\-]{24,}$').hasMatch(text)) {
      return true;
    }
    return false;
  }
}
