import 'dart:convert';

class JsonFieldStreamExtractor {
  JsonFieldStreamExtractor(this.fieldName);

  final String fieldName;
  String _rawBuffer = '';
  String _emittedDecoded = '';
  bool _completed = false;
  bool _matchedField = false;

  bool get hasMatchedField => _matchedField;
  bool get isComplete => _completed;
  String get decodedValue => _emittedDecoded;

  void reset() {
    _rawBuffer = '';
    _emittedDecoded = '';
    _completed = false;
    _matchedField = false;
  }

  String consume(String chunk) {
    if (chunk.isEmpty || _completed) return '';
    _rawBuffer += chunk;
    final extraction = _extractField(_rawBuffer, fieldName);
    if (extraction == null) return '';
    _matchedField = true;
    final decoded = _decodeLenientJsonString(extraction.encodedValue);
    if (decoded.length <= _emittedDecoded.length) {
      if (extraction.complete) _completed = true;
      return '';
    }
    final delta = decoded.substring(_emittedDecoded.length);
    _emittedDecoded = decoded;
    if (extraction.complete) _completed = true;
    return delta;
  }

  static _JsonFieldExtraction? _extractField(String raw, String fieldName) {
    final key = '"$fieldName"';
    final fieldIndex = raw.indexOf(key);
    if (fieldIndex < 0) return null;
    var cursor = fieldIndex + key.length;
    while (cursor < raw.length && _isWhitespace(raw.codeUnitAt(cursor))) {
      cursor += 1;
    }
    if (cursor >= raw.length || raw[cursor] != ':') return null;
    cursor += 1;
    while (cursor < raw.length && _isWhitespace(raw.codeUnitAt(cursor))) {
      cursor += 1;
    }
    if (cursor >= raw.length || raw[cursor] != '"') return null;
    cursor += 1;
    final valueStart = cursor;
    var escaped = false;
    while (cursor < raw.length) {
      final ch = raw[cursor];
      if (escaped) {
        escaped = false;
        cursor += 1;
        continue;
      }
      if (ch == r'\') {
        escaped = true;
        cursor += 1;
        continue;
      }
      if (ch == '"') {
        return _JsonFieldExtraction(
          encodedValue: raw.substring(valueStart, cursor),
          complete: true,
        );
      }
      cursor += 1;
    }
    return _JsonFieldExtraction(
      encodedValue: raw.substring(valueStart),
      complete: false,
    );
  }

  static String _decodeLenientJsonString(String encoded) {
    var candidate = encoded;
    while (candidate.isNotEmpty) {
      try {
        return jsonDecode('"$candidate"') as String;
      } catch (_) {
        candidate = candidate.substring(0, candidate.length - 1);
      }
    }
    return '';
  }

  static bool _isWhitespace(int charCode) =>
      charCode == 0x20 || charCode == 0x0A || charCode == 0x0D || charCode == 0x09;
}

class _JsonFieldExtraction {
  const _JsonFieldExtraction({
    required this.encodedValue,
    required this.complete,
  });

  final String encodedValue;
  final bool complete;
}
