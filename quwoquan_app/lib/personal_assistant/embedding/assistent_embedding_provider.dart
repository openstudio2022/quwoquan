abstract class AssistentEmbeddingProvider {
  String get providerId;

  Future<List<double>> embedText(String text);
}

class AssistentHeuristicEmbeddingProvider implements AssistentEmbeddingProvider {
  const AssistentHeuristicEmbeddingProvider();

  @override
  String get providerId => 'heuristic_v1';

  @override
  Future<List<double>> embedText(String text) async {
    final normalized = text.trim();
    final vector = List<double>.filled(24, 0);
    if (normalized.isEmpty) return vector;
    for (var i = 0; i < normalized.length; i++) {
      vector[i % vector.length] += normalized.codeUnitAt(i) / 255.0;
    }
    return vector;
  }
}

