import 'dart:convert';
import 'dart:math' as math;

import 'package:http/http.dart' as http;
import 'package:quwoquan_app/assistant/memory/domain/vector_store.dart';

class AssistantMemoryRepository {
  AssistantMemoryRepository(
    this._store, {
    this.embeddingBaseUrl = '',
    this.embeddingApiKey = '',
    this.embeddingModel = 'text-embedding-3-small',
  });

  final AssistantVectorStore _store;
  final String embeddingBaseUrl;
  final String embeddingApiKey;
  final String embeddingModel;

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

  /// Embeds text using the LLM embedding API (e.g. text-embedding-3-small).
  /// Falls back to TF-IDF inspired character-level embedding on error.
  Future<List<double>> embedText(String input) async {
    final normalized = input.trim();
    if (normalized.isEmpty) return List<double>.filled(1536, 0);
    if (embeddingBaseUrl.isNotEmpty && embeddingApiKey.isNotEmpty) {
      try {
        final endpoint = '${embeddingBaseUrl.trimRight().replaceAll(RegExp(r'/$'), '')}/embeddings';
        final response = await http
            .post(
              Uri.parse(endpoint),
              headers: <String, String>{
                'Content-Type': 'application/json',
                'Authorization': 'Bearer $embeddingApiKey',
              },
              body: jsonEncode(<String, dynamic>{
                'model': embeddingModel,
                'input': normalized,
              }),
            )
            .timeout(const Duration(seconds: 10));
        if (response.statusCode == 200) {
          final decoded = jsonDecode(response.body);
          final embeddingRaw = (decoded['data'] as List?)?.firstOrNull;
          if (embeddingRaw != null) {
            final vec = (embeddingRaw['embedding'] as List?)
                ?.whereType<num>()
                .map((n) => n.toDouble())
                .toList(growable: false);
            if (vec != null && vec.isNotEmpty) return vec;
          }
        }
      } catch (_) {
        // Fall through to TF-IDF fallback.
      }
    }
    return _tfidfFallbackEmbed(normalized);
  }

  /// 64-dimension character bigram TF vector as fallback.
  List<double> _tfidfFallbackEmbed(String text) {
    const dims = 64;
    final vector = List<double>.filled(dims, 0.0);
    if (text.length < 2) {
      vector[text.codeUnitAt(0) % dims] += 1.0;
    } else {
      for (var i = 0; i < text.length - 1; i++) {
        final bigram = text.codeUnitAt(i) * 31 + text.codeUnitAt(i + 1);
        vector[bigram % dims] += 1.0;
      }
    }
    final norm = math.sqrt(
      vector.fold(0.0, (sum, v) => sum + v * v),
    );
    if (norm > 0) {
      for (var i = 0; i < dims; i++) {
        vector[i] = vector[i] / norm;
      }
    }
    return vector;
  }

  /// Synchronous fallback for callers that cannot await.
  List<double> embedTextSync(String input) => _tfidfFallbackEmbed(input.trim());
}
