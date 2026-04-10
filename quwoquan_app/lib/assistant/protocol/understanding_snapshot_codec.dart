import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';

RunArtifactsUnderstandingSnapshot parseRunArtifactsUnderstandingSnapshot(
  Object? raw,
) {
  if (raw is! Map) {
    return const RunArtifactsUnderstandingSnapshot();
  }
  return parseRunArtifactsUnderstandingSnapshotFromMap(
    raw.cast<String, dynamic>(),
  );
}

RunArtifactsUnderstandingSnapshot parseRunArtifactsUnderstandingSnapshotFromMap(
  Map<String, dynamic> raw,
) {
  if (raw.isEmpty) {
    return const RunArtifactsUnderstandingSnapshot();
  }
  return RunArtifactsUnderstandingSnapshot.fromJson(
    normalizeRunArtifactsUnderstandingSnapshotJson(raw),
  );
}

Map<String, dynamic> normalizeRunArtifactsUnderstandingSnapshotJson(
  Map<String, dynamic> raw,
) {
  if (raw.isEmpty) {
    return const <String, dynamic>{};
  }
  final normalized = Map<String, dynamic>.from(raw);
  if (raw.containsKey('resolutionItems')) {
    normalized['resolutionItems'] = _normalizeResolutionItems(
      raw['resolutionItems'],
    );
  }
  return normalized;
}

List<Map<String, dynamic>> _normalizeResolutionItems(Object? raw) {
  if (raw is! List) {
    return const <Map<String, dynamic>>[];
  }
  return raw
      .map(_normalizeResolutionItem)
      .whereType<Map<String, dynamic>>()
      .toList(growable: false);
}

Map<String, dynamic>? _normalizeResolutionItem(Object? raw) {
  if (raw is Map) {
    final item = raw.cast<String, dynamic>();
    final title = (item['title'] as String?)?.trim() ?? '';
    final detail = (item['detail'] as String?)?.trim() ?? '';
    final resolvedValue = (item['resolvedValue'] as String?)?.trim() ?? '';
    final normalizedDetail = detail.isNotEmpty ? detail : resolvedValue;
    final normalizedTitle = title.isNotEmpty
        ? title
        : _fallbackResolutionTitle(normalizedDetail);
    return <String, dynamic>{
      'kind': _firstNonEmpty(<String>[
        (item['kind'] as String?)?.trim() ?? '',
        _inferResolutionKind(title: normalizedTitle, detail: normalizedDetail),
      ]),
      'title': normalizedTitle,
      'detail': normalizedDetail,
      'source': (item['source'] as String?)?.trim() ?? '',
      'originalValue': (item['originalValue'] as String?)?.trim() ?? '',
      'resolvedValue': resolvedValue,
      'defaultApplied':
          item['defaultApplied'] == true || normalizedDetail.contains('默认'),
      'visibleInUnderstanding': item['visibleInUnderstanding'] != false,
    };
  }
  final text = raw?.toString().trim() ?? '';
  if (text.isEmpty) {
    return null;
  }
  final match = RegExp(r'^([^：:\n]{1,16})[：:]\s*(.+)$').firstMatch(text);
  final title = match?.group(1)?.trim() ?? _fallbackResolutionTitle(text);
  final detail = match?.group(2)?.trim() ?? text;
  return <String, dynamic>{
    'kind': _inferResolutionKind(title: title, detail: detail),
    'title': title,
    'detail': detail,
    'source': 'stream_progress',
    'originalValue': '',
    'resolvedValue': '',
    'defaultApplied': detail.contains('默认'),
    'visibleInUnderstanding': true,
  };
}

String _fallbackResolutionTitle(String detail) {
  final normalized = detail.trim();
  if (normalized.contains('时间')) {
    return '时间锚点';
  }
  if (normalized.contains('城市') ||
      normalized.contains('地点') ||
      normalized.contains('地理') ||
      normalized.contains('市场')) {
    return '地理锚点';
  }
  if (normalized.contains('补充') || normalized.contains('澄清')) {
    return '补充信息';
  }
  return '理解说明';
}

String _inferResolutionKind({required String title, required String detail}) {
  final normalized = '$title $detail';
  if (normalized.contains('时间')) {
    return 'temporal_anchor';
  }
  if (normalized.contains('城市') ||
      normalized.contains('地点') ||
      normalized.contains('地理') ||
      normalized.contains('市场')) {
    return 'geo_anchor';
  }
  if (normalized.contains('补充') || normalized.contains('澄清')) {
    return 'clarification';
  }
  return 'understanding_note';
}

String _firstNonEmpty(List<String> values) {
  for (final value in values) {
    final normalized = value.trim();
    if (normalized.isNotEmpty) {
      return normalized;
    }
  }
  return '';
}
