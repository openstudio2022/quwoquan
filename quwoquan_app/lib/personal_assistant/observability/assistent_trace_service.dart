class AssistentTraceSpan {
  const AssistentTraceSpan({
    required this.runId,
    required this.traceId,
    required this.spanId,
    required this.name,
    required this.startedAt,
    this.endedAt,
    this.attributes = const <String, dynamic>{},
  });

  final String runId;
  final String traceId;
  final String spanId;
  final String name;
  final DateTime startedAt;
  final DateTime? endedAt;
  final Map<String, dynamic> attributes;

  AssistentTraceSpan end() {
    return AssistentTraceSpan(
      runId: runId,
      traceId: traceId,
      spanId: spanId,
      name: name,
      startedAt: startedAt,
      endedAt: DateTime.now(),
      attributes: attributes,
    );
  }
}

class AssistentTraceService {
  final Map<String, List<AssistentTraceSpan>> _byRun = <String, List<AssistentTraceSpan>>{};

  void append(AssistentTraceSpan span) {
    final list = _byRun.putIfAbsent(span.runId, () => <AssistentTraceSpan>[]);
    list.add(span);
  }

  List<AssistentTraceSpan> tracesForRun(String runId) {
    return List<AssistentTraceSpan>.from(_byRun[runId] ?? const <AssistentTraceSpan>[]);
  }
}

