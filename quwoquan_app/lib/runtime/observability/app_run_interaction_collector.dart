class AppRunInteractionCollector {
  AppRunInteractionCollector._();

  static final AppRunInteractionCollector instance =
      AppRunInteractionCollector._();

  final Map<String, List<Map<String, dynamic>>> _buffer =
      <String, List<Map<String, dynamic>>>{};

  void add({required String runId, required Map<String, dynamic> interaction}) {
    final id = runId.trim();
    if (id.isEmpty) return;
    final list = _buffer.putIfAbsent(id, () => <Map<String, dynamic>>[]);
    list.add(interaction);
  }

  List<Map<String, dynamic>> peek(String runId) {
    final id = runId.trim();
    if (id.isEmpty) return const <Map<String, dynamic>>[];
    final list = _buffer[id];
    if (list == null) return const <Map<String, dynamic>>[];
    return List<Map<String, dynamic>>.from(list);
  }

  List<Map<String, dynamic>> take(String runId) {
    final id = runId.trim();
    if (id.isEmpty) return const <Map<String, dynamic>>[];
    final list = _buffer.remove(id);
    if (list == null) return const <Map<String, dynamic>>[];
    return list;
  }
}
