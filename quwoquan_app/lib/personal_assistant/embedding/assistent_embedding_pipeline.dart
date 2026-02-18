import 'package:quwoquan_app/personal_assistant/embedding/assistent_embedding_provider.dart';

class AssistentEmbeddingChunk {
  const AssistentEmbeddingChunk({
    required this.id,
    required this.text,
    required this.vector,
  });

  final String id;
  final String text;
  final List<double> vector;
}

class AssistentEmbeddingPipeline {
  const AssistentEmbeddingPipeline({
    required AssistentEmbeddingProvider provider,
  }) : _provider = provider;

  final AssistentEmbeddingProvider _provider;

  Future<List<AssistentEmbeddingChunk>> process({
    required String documentId,
    required String text,
    int chunkSize = 280,
  }) async {
    final chunks = _splitText(text, chunkSize: chunkSize);
    final result = <AssistentEmbeddingChunk>[];
    for (var i = 0; i < chunks.length; i++) {
      final vector = await _provider.embedText(chunks[i]);
      result.add(
        AssistentEmbeddingChunk(
          id: '${documentId}_$i',
          text: chunks[i],
          vector: vector,
        ),
      );
    }
    return result;
  }

  List<String> _splitText(String text, {required int chunkSize}) {
    final normalized = text.trim();
    if (normalized.isEmpty) return const <String>[];
    final parts = <String>[];
    for (var i = 0; i < normalized.length; i += chunkSize) {
      final end = (i + chunkSize) > normalized.length ? normalized.length : (i + chunkSize);
      parts.add(normalized.substring(i, end));
    }
    return parts;
  }
}

