import 'package:quwoquan_app/assistant/memory/long_term/vector_store.dart';
import 'package:quwoquan_app/assistant/memory/long_term/memory_embedding_service.dart';

class AssistantMemoryRepository {
  AssistantMemoryRepository(
    this._store, {
    AssistantMemoryEmbeddingService? embeddingService,
    String embeddingBaseUrl = '',
    String embeddingApiKey = '',
    String embeddingModel = 'text-embedding-3-small',
  }) : _embeddingService = embeddingService ??
            AssistantMemoryEmbeddingService(
              embeddingBaseUrl: embeddingBaseUrl,
              embeddingApiKey: embeddingApiKey,
              embeddingModel: embeddingModel,
            );

  final AssistantVectorStore _store;
  final AssistantMemoryEmbeddingService _embeddingService;

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
  }) async {
    return remember(
      id: id,
      text: text,
      embedding: await embedText(text),
      metadata: metadata,
    );
  }

  Future<List<VectorMemoryItem>> recallByText({
    required String query,
    int limit = 5,
  }) async {
    return recall(
      queryEmbedding: await embedText(query),
      limit: limit,
    );
  }

  Future<List<double>> embedText(String input) async {
    return _embeddingService.embedText(input);
  }

  List<double> embedTextSync(String input) => _embeddingService.embedTextSync(input);
}
