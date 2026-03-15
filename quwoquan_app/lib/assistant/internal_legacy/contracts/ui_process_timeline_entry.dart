class UiProcessTimelineEntry {
  const UiProcessTimelineEntry({
    required this.scope,
    required this.type,
    required this.summary,
    this.nodeId = '',
    this.runId = '',
    this.eventId = '',
    this.payload = const <String, dynamic>{},
    this.references = const <Map<String, dynamic>>[],
  });

  final String scope;
  final String type;
  final String summary;
  final String nodeId;
  final String runId;
  final String eventId;
  final Map<String, dynamic> payload;
  final List<Map<String, dynamic>> references;

  Map<String, dynamic> toJson() => <String, dynamic>{
    'scope': scope,
    'type': type,
    'nodeId': nodeId,
    'runId': runId,
    'eventId': eventId,
    'summary': summary,
    'payload': payload,
    'references': references,
  };

  factory UiProcessTimelineEntry.fromJson(Map<String, dynamic> json) {
    return UiProcessTimelineEntry(
      scope: (json['scope'] as String?)?.trim() ?? '',
      type: (json['type'] as String?)?.trim() ?? '',
      nodeId: (json['nodeId'] as String?)?.trim() ?? '',
      runId: (json['runId'] as String?)?.trim() ?? '',
      eventId: (json['eventId'] as String?)?.trim() ?? '',
      summary: (json['summary'] as String?)?.trim() ?? '',
      payload:
          (json['payload'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      references:
          (json['references'] as List?)
              ?.whereType<Map>()
              .map((item) => item.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[],
    );
  }
}
