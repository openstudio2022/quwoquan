import 'dart:convert';
import 'dart:math' as math;

import 'package:http/http.dart' as http;

class AssistantMemoryEmbeddingService {
  const AssistantMemoryEmbeddingService({
    this.embeddingBaseUrl = '',
    this.embeddingApiKey = '',
    this.embeddingModel = 'text-embedding-3-small',
  });

  final String embeddingBaseUrl;
  final String embeddingApiKey;
  final String embeddingModel;

  /// Embeds text using the LLM embedding API (e.g. text-embedding-3-small).
  /// Falls back to TF-IDF inspired character-level embedding on error.
  Future<List<double>> embedText(String input) async {
    final normalized = input.trim();
    if (normalized.isEmpty) return List<double>.filled(1536, 0);
    if (embeddingBaseUrl.isNotEmpty && embeddingApiKey.isNotEmpty) {
      try {
        final endpoint =
            '${embeddingBaseUrl.trimRight().replaceAll(RegExp(r'/$'), '')}/embeddings';
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
  List<double> embedTextSync(String input) => _tfidfFallbackEmbed(input.trim());

  List<double> _tfidfFallbackEmbed(String text) {
    const dims = 64;
    final vector = List<double>.filled(dims, 0.0);
    if (text.isEmpty) {
      return vector;
    }
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
}
