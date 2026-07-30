import '../operation_request_payload.dart';
part '../generated/requests/content/content_behavior_contracts.requests.g.dart';

/// Single wire event for `POST /content/behaviors`.
final class ContentBehaviorEventWire {
  ContentBehaviorEventWire({
    required String contentId,
    required String eventType,
    required String timestamp,
    this.durationMs,
    Map<String, Object?>? metadata,
  }) : contentId = _required(contentId, 'contentId'),
       eventType = _required(eventType, 'eventType'),
       timestamp = _required(timestamp, 'timestamp'),
       metadata = metadata == null
           ? const <String, Object?>{}
           : Map<String, Object?>.unmodifiable(metadata);

  final String contentId;
  final String eventType;
  final String timestamp;
  final int? durationMs;
  final Map<String, Object?> metadata;

  Map<String, Object?> toWireMap() {
    return <String, Object?>{
      'contentId': contentId,
      'eventType': eventType,
      'timestamp': timestamp,
      if (durationMs != null) 'durationMs': durationMs,
      if (metadata.isNotEmpty) 'metadata': metadata,
    };
  }
}





void decodeEmptyContentBehaviorsResponse(Object? value) {
  if (value != null) {
    throw const FormatException(
      'content.content_behavior_fact.ReportBehaviors response must be empty',
    );
  }
}

/// Content behavior batch report capability.
abstract interface class ContentBehaviorCommandWriter {
  Future<void> reportBehaviors(ReportContentBehaviorsCommand command);
}

String _required(String value, String name) {
  final normalized = value.trim();
  if (normalized.isEmpty) {
    throw ArgumentError.value(value, name, 'required');
  }
  return normalized;
}
