import 'dart:convert';

import 'package:crypto/crypto.dart';

String canonicalFixtureSha256(Object? payload) {
  final canonical = _canonicalize(payload);
  return 'sha256:${sha256.convert(utf8.encode(jsonEncode(canonical)))}';
}

Object? _canonicalize(Object? value) {
  if (value is Map) {
    final entries =
        value.entries
            .map((entry) => MapEntry(entry.key.toString(), entry.value))
            .toList(growable: false)
          ..sort((left, right) => left.key.compareTo(right.key));
    return <String, Object?>{
      for (final entry in entries) entry.key: _canonicalize(entry.value),
    };
  }
  if (value is Iterable) {
    return value.map(_canonicalize).toList(growable: false);
  }
  return value;
}
