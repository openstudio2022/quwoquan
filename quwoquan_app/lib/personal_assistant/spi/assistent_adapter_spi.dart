class AssistentChannelEvent {
  const AssistentChannelEvent({
    required this.channel,
    required this.eventType,
    required this.payload,
  });

  final String channel;
  final String eventType;
  final Map<String, dynamic> payload;
}

class AssistentAdapterResponse {
  const AssistentAdapterResponse({
    required this.ok,
    required this.message,
    this.payload = const <String, dynamic>{},
  });

  final bool ok;
  final String message;
  final Map<String, dynamic> payload;
}

abstract class AssistentAdapterSpi {
  String get adapterId;

  Future<bool> verify(Map<String, String> headers, String rawBody);

  Future<AssistentChannelEvent> ingest({
    required Map<String, String> headers,
    required String rawBody,
  });

  Future<AssistentAdapterResponse> dispatch({
    required AssistentChannelEvent sourceEvent,
    required Map<String, dynamic> responseEnvelope,
  });
}

