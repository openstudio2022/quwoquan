part of 'persisted_assistant_turn.dart';

String _sanitizeUserFacingTimelineText(String raw) {
  final normalized =
      AssistantDisplayTextResolver.normalizeUserFacingProcessNarration(raw);
  if (normalized.isEmpty) {
    return '';
  }
  if (AssistantDisplayTextResolver.containsInternalProcessFragment(
    normalized,
  )) {
    return '';
  }
  return normalized;
}

List<ProcessTimelineFrame> _parseProcessTimelineList(Object? raw) {
  if (raw is! List) {
    return const <ProcessTimelineFrame>[];
  }
  final frames = raw
      .whereType<Map>()
      .map(
        (item) => ProcessTimelineFrame.fromJson(item.cast<String, dynamic>()),
      )
      .toList(growable: false);
  return normalizeProcessTimeline(frames);
}

Map<String, dynamic> _resolvePersistedStructuredMap(
  Map<String, dynamic> message,
  String key,
) {
  final direct = (message[key] as Map?)?.cast<String, dynamic>();
  if (direct != null && _hasStructuredContent(direct)) {
    return _copyStructuredMap(direct);
  }
  return const <String, dynamic>{};
}

Map<String, dynamic> _copyStructuredMap(Map<String, dynamic> value) {
  return Map<String, dynamic>.from(value);
}

bool _hasStructuredContent(Map<String, dynamic> value) {
  for (final item in value.values) {
    if (item is String && item.trim().isNotEmpty) return true;
    if (item is num && item != 0) return true;
    if (item is bool && item) return true;
    if (item is List && item.isNotEmpty) return true;
    if (item is Map && item.isNotEmpty) return true;
  }
  return false;
}
