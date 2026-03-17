import 'dart:convert';
import 'dart:math' show min, max;

/// Truncates tool results to prevent context window overflow.
/// Inspired by OpenClaw's tool-result-truncation.ts.
class ToolResultTruncator {
  const ToolResultTruncator({
    this.maxContextShareRatio = 0.3,
    this.hardMaxChars = 200000,
    this.minKeepChars = 1500,
    this.contextWindowChars = 60000,
  });

  final double maxContextShareRatio;
  final int hardMaxChars;
  final int minKeepChars;
  final int contextWindowChars;

  String truncate(String result) {
    final maxChars = min(
      (contextWindowChars * maxContextShareRatio).toInt(),
      hardMaxChars,
    );
    if (result.length <= maxChars) return result;

    final keepChars = max(maxChars - 80, minKeepChars);
    final cutPoint = result.lastIndexOf('\n', keepChars);
    final effectiveCut = (cutPoint > keepChars * 0.8) ? cutPoint : keepChars;
    return '${result.substring(0, effectiveCut)}\n\n[内容已截断，原始 ${result.length} 字符]';
  }

  String truncateJson(Object? value) {
    final maxChars = min(
      (contextWindowChars * maxContextShareRatio).toInt(),
      hardMaxChars,
    );
    final normalized = _shrinkValue(value, depth: 0);
    var encoded = jsonEncode(normalized);
    if (encoded.length <= maxChars) return encoded;
    final fallback = <String, dynamic>{
      'truncated': true,
      'originalLength': encoded.length,
      'preview': truncate(encoded),
    };
    encoded = jsonEncode(fallback);
    return encoded.length <= maxChars ? encoded : truncate(encoded);
  }

  Object? _shrinkValue(Object? value, {required int depth}) {
    if (value == null) return null;
    if (value is String) {
      final maxStringChars = depth <= 1 ? 1200 : 400;
      if (value.length <= maxStringChars) return value;
      return '${value.substring(0, maxStringChars)}...[截断 ${value.length - maxStringChars} 字符]';
    }
    if (value is List) {
      final limit = depth == 0 ? 8 : 4;
      final kept = value
          .take(limit)
          .map((item) => _shrinkValue(item, depth: depth + 1))
          .toList(growable: false);
      if (value.length <= limit) return kept;
      return <Object?>[
        ...kept,
        <String, dynamic>{
          'truncated': true,
          'remainingItems': value.length - limit,
        },
      ];
    }
    if (value is Map) {
      final out = <String, dynamic>{};
      for (final entry in value.entries) {
        final key = entry.key.toString();
        out[key] = _shrinkValue(entry.value, depth: depth + 1);
      }
      return out;
    }
    return value;
  }
}
