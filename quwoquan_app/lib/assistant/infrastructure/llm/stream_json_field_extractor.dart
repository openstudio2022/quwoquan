import 'dart:convert';

// ASSISTANT_WEAK_TYPE: LLM_RAW — 流式片段上按路径抽取 JSON 字符串字段，产出增量 String。

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
    final segments = fieldName
        .split('.')
        .map((item) => item.trim())
        .where((item) => item.isNotEmpty)
        .toList(growable: false);
    if (segments.isEmpty) return null;
    return _extractFieldAtPath(
      raw,
      segments,
      segmentIndex: 0,
      searchStart: 0,
      searchEnd: raw.length,
    );
  }

  static _JsonFieldExtraction? _extractFieldAtPath(
    String raw,
    List<String> segments, {
    required int segmentIndex,
    required int searchStart,
    required int searchEnd,
  }) {
    final value = _extractValueForKey(
      raw,
      segments[segmentIndex],
      searchStart: searchStart,
      searchEnd: searchEnd,
    );
    if (value == null) return null;
    if (segmentIndex == segments.length - 1) {
      if (value.kind != _JsonValueKind.string) return null;
      return _JsonFieldExtraction(
        encodedValue: value.encodedValue,
        complete: value.complete,
      );
    }
    if (value.kind != _JsonValueKind.object) return null;
    return _extractFieldAtPath(
      raw,
      segments,
      segmentIndex: segmentIndex + 1,
      searchStart: value.objectSearchStart,
      searchEnd: value.objectSearchEnd,
    );
  }

  static _JsonValueExtraction? _extractValueForKey(
    String raw,
    String fieldName, {
    required int searchStart,
    required int searchEnd,
  }) {
    final key = '"$fieldName"';
    final fieldIndex = raw.indexOf(key, searchStart);
    if (fieldIndex < 0 || fieldIndex >= searchEnd) return null;
    var cursor = fieldIndex + key.length;
    while (cursor < raw.length &&
        cursor < searchEnd &&
        _isWhitespace(raw.codeUnitAt(cursor))) {
      cursor += 1;
    }
    if (cursor >= raw.length || cursor >= searchEnd || raw[cursor] != ':') {
      return null;
    }
    cursor += 1;
    while (cursor < raw.length &&
        cursor < searchEnd &&
        _isWhitespace(raw.codeUnitAt(cursor))) {
      cursor += 1;
    }
    if (cursor >= raw.length || cursor >= searchEnd) return null;
    final marker = raw[cursor];
    if (marker == '"') {
      cursor += 1;
      final valueStart = cursor;
      var escaped = false;
      while (cursor < raw.length && cursor < searchEnd) {
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
          return _JsonValueExtraction.string(
            encodedValue: raw.substring(valueStart, cursor),
            complete: true,
          );
        }
        cursor += 1;
      }
      return _JsonValueExtraction.string(
        encodedValue: raw.substring(valueStart),
        complete: false,
      );
    }
    if (marker == '{') {
      final objectStart = cursor + 1;
      cursor += 1;
      var depth = 1;
      var inString = false;
      var escaped = false;
      while (cursor < raw.length && cursor < searchEnd) {
        final ch = raw[cursor];
        if (inString) {
          if (escaped) {
            escaped = false;
          } else if (ch == r'\') {
            escaped = true;
          } else if (ch == '"') {
            inString = false;
          }
          cursor += 1;
          continue;
        }
        if (ch == '"') {
          inString = true;
          cursor += 1;
          continue;
        }
        if (ch == '{') {
          depth += 1;
        } else if (ch == '}') {
          depth -= 1;
          if (depth == 0) {
            return _JsonValueExtraction.object(
              objectSearchStart: objectStart,
              objectSearchEnd: cursor,
              complete: true,
            );
          }
        }
        cursor += 1;
      }
      return _JsonValueExtraction.object(
        objectSearchStart: objectStart,
        objectSearchEnd: searchEnd,
        complete: false,
      );
    }
    return _JsonValueExtraction.other();
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
      charCode == 0x20 ||
      charCode == 0x0A ||
      charCode == 0x0D ||
      charCode == 0x09;
}

class _JsonFieldExtraction {
  const _JsonFieldExtraction({
    required this.encodedValue,
    required this.complete,
  });

  final String encodedValue;
  final bool complete;
}

enum _JsonValueKind { string, object, other }

class _JsonValueExtraction {
  const _JsonValueExtraction._({
    required this.kind,
    this.encodedValue = '',
    this.objectSearchStart = 0,
    this.objectSearchEnd = 0,
    this.complete = false,
  });

  const _JsonValueExtraction.string({
    required String encodedValue,
    required bool complete,
  }) : this._(
         kind: _JsonValueKind.string,
         encodedValue: encodedValue,
         complete: complete,
       );

  const _JsonValueExtraction.object({
    required int objectSearchStart,
    required int objectSearchEnd,
    required bool complete,
  }) : this._(
         kind: _JsonValueKind.object,
         objectSearchStart: objectSearchStart,
         objectSearchEnd: objectSearchEnd,
         complete: complete,
       );

  const _JsonValueExtraction.other() : this._(kind: _JsonValueKind.other);

  final _JsonValueKind kind;
  final String encodedValue;
  final int objectSearchStart;
  final int objectSearchEnd;
  final bool complete;
}
