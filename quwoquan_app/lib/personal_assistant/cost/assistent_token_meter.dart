class AssistentTokenUsage {
  const AssistentTokenUsage({
    required this.promptTokens,
    required this.completionTokens,
  });

  final int promptTokens;
  final int completionTokens;

  int get totalTokens => promptTokens + completionTokens;
}

class AssistentTokenMeter {
  const AssistentTokenMeter();

  AssistentTokenUsage estimate({
    required String inputText,
    required String outputText,
  }) {
    final prompt = _estimateTextTokens(inputText);
    final completion = _estimateTextTokens(outputText);
    return AssistentTokenUsage(
      promptTokens: prompt,
      completionTokens: completion,
    );
  }

  int _estimateTextTokens(String text) {
    final cleaned = text.trim();
    if (cleaned.isEmpty) return 0;
    // Lightweight estimate for v1: ~4 chars per token.
    final estimated = (cleaned.length / 4).ceil();
    return estimated < 1 ? 1 : estimated;
  }
}

