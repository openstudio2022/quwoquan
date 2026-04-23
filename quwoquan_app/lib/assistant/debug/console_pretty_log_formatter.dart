import 'dart:convert';

class ConsolePrettyLogFormatter {
  const ConsolePrettyLogFormatter._();

  static List<String> renderSection({
    required String prefix,
    required String title,
    Object? value,
  }) {
    final rendered = _renderValue(
      _normalizeValue(value),
      indent: 0,
      fieldName: title,
    );
    return rendered.map((line) => '$prefix$line').toList(growable: false);
  }

  static dynamic normalizeJsonLikeValue(
    dynamic value, {
    Set<String> secretKeys = const <String>{'authorization'},
  }) {
    if (value is Map) {
      final normalized = <String, dynamic>{};
      for (final entry in value.entries) {
        final key = entry.key.toString();
        if (secretKeys.contains(key.toLowerCase())) {
          normalized[key] = 'Bearer ***';
          continue;
        }
        normalized[key] = normalizeJsonLikeValue(
          entry.value,
          secretKeys: secretKeys,
        );
      }
      return normalized;
    }
    if (value is List) {
      return value
          .map((item) => normalizeJsonLikeValue(item, secretKeys: secretKeys))
          .toList(growable: false);
    }
    if (value is String) {
      final decoded = _tryDecodeJsonString(value.trim());
      if (decoded != null) {
        return normalizeJsonLikeValue(decoded, secretKeys: secretKeys);
      }
      return value;
    }
    return value;
  }

  static dynamic _normalizeValue(Object? value) {
    if (value == null) {
      return '<empty>';
    }
    if (value is String) {
      final trimmed = value.trim();
      if (trimmed.isEmpty) {
        return '<empty>';
      }
      return _tryDecodeJsonString(trimmed) ?? value;
    }
    return value;
  }

  static List<String> _renderValue(
    Object? value, {
    required int indent,
    String? fieldName,
  }) {
    final leading = '  ' * indent;
    final label = fieldName == null ? '' : '$fieldName: ';
    if (value is Map) {
      if (value.isEmpty) {
        return <String>['$leading$label{}'];
      }
      final lines = <String>['$leading$label{'];
      for (final entry in value.entries) {
        lines.addAll(
          _renderValue(
            entry.value,
            indent: indent + 1,
            fieldName: entry.key.toString(),
          ),
        );
      }
      lines.add('${leading}}');
      return lines;
    }
    if (value is List) {
      if (value.isEmpty) {
        return <String>['$leading$label[]'];
      }
      final lines = <String>['$leading$label['];
      for (final item in value) {
        if (item is Map || item is List) {
          lines.addAll(_renderListItem(item, indent + 1));
          continue;
        }
        final normalizedItem = _normalizeValue(item);
        if (_shouldUseBlockString(normalizedItem)) {
          lines.add('${'  ' * (indent + 1)}- |');
          for (final blockLine in _stringLines(normalizedItem)) {
            lines.add('${'  ' * (indent + 2)}$blockLine');
          }
          continue;
        }
        lines.add(
          "${'  ' * (indent + 1)}- ${_renderScalar(normalizedItem)}",
        );
      }
      lines.add('${leading}]');
      return lines;
    }
    if (_shouldUseBlockString(value)) {
      final lines = <String>['$leading$label|'];
      for (final blockLine in _stringLines(value)) {
        lines.add('${'  ' * (indent + 1)}$blockLine');
      }
      return lines;
    }
    return <String>['$leading$label${_renderScalar(value)}'];
  }

  static List<String> _renderListItem(Object? value, int indent) {
    final leading = '  ' * indent;
    if (value is Map) {
      if (value.isEmpty) return <String>['$leading- {}'];
      final lines = <String>['$leading- {'];
      for (final entry in value.entries) {
        lines.addAll(
          _renderValue(
            entry.value,
            indent: indent + 1,
            fieldName: entry.key.toString(),
          ),
        );
      }
      lines.add('${leading}}');
      return lines;
    }
    if (value is List) {
      if (value.isEmpty) return <String>['$leading- []'];
      final lines = <String>['$leading- ['];
      for (final item in value) {
        if (item is Map || item is List) {
          lines.addAll(_renderListItem(item, indent + 1));
        } else {
          lines.add(
            "${'  ' * (indent + 1)}- ${_renderScalar(_normalizeValue(item))}",
          );
        }
      }
      lines.add('${leading}]');
      return lines;
    }
    return <String>['$leading- ${_renderScalar(_normalizeValue(value))}'];
  }

  static bool _shouldUseBlockString(Object? value) {
    final text = value is String ? value : null;
    if (text == null) return false;
    return text.contains('\n') || text.length > 160;
  }

  static Iterable<String> _stringLines(Object? value) {
    final text = value is String ? value : value?.toString() ?? '';
    return const LineSplitter().convert(text);
  }

  static String _renderScalar(Object? value) {
    if (value == null) return 'null';
    if (value is String) {
      return value == '<empty>' ? value : jsonEncode(value);
    }
    if (value is bool || value is num) return value.toString();
    return jsonEncode(value.toString());
  }

  static Object? _tryDecodeJsonString(String text) {
    if (text.isEmpty) return null;
    final first = text.codeUnitAt(0);
    if (first != 0x7b && first != 0x5b) {
      return null;
    }
    try {
      return jsonDecode(text);
    } catch (_) {
      return null;
    }
  }
}
