class VectorMemoryItem {
  const VectorMemoryItem({
    required this.id,
    required this.text,
    required this.vector,
    this.metadata = const <String, dynamic>{},
  });

  final String id;
  final String text;
  final List<double> vector;
  final Map<String, dynamic> metadata;
}

abstract class AssistantVectorStore {
  Future<void> upsert(VectorMemoryItem item);
  Future<List<VectorMemoryItem>> search(List<double> queryVector, {int limit = 5});
}
