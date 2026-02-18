import 'package:quwoquan_app/personal_assistant/memory/vector_store.dart';

class AssistantMemoryRepository {
  AssistantMemoryRepository(this._store);

  final AssistantVectorStore _store;

  Future<void> remember({
    required String id,
    required String text,
    required List<double> embedding,
    Map<String, dynamic> metadata = const <String, dynamic>{},
  }) {
    return _store.upsert(
      VectorMemoryItem(
        id: id,
        text: text,
        vector: embedding,
        metadata: metadata,
      ),
    );
  }

  Future<List<VectorMemoryItem>> recall({
    required List<double> queryEmbedding,
    int limit = 5,
  }) {
    return _store.search(queryEmbedding, limit: limit);
  }

  Future<void> rememberText({
    required String id,
    required String text,
    Map<String, dynamic> metadata = const <String, dynamic>{},
  }) {
    return remember(
      id: id,
      text: text,
      embedding: embedText(text),
      metadata: metadata,
    );
  }

  Future<List<VectorMemoryItem>> recallByText({
    required String query,
    int limit = 5,
  }) {
    return recall(
      queryEmbedding: embedText(query),
      limit: limit,
    );
  }

  List<double> embedText(String input) {
    final normalized = input.trim();
    if (normalized.isEmpty) return List<double>.filled(16, 0);
    final vector = List<double>.filled(16, 0);
    for (var i = 0; i < normalized.length; i++) {
      final slot = i % vector.length;
      vector[slot] += normalized.codeUnitAt(i) / 255.0;
    }
    return vector;
  }
}
