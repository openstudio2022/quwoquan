import 'package:quwoquan_app/assistant/memory/long_term/assistant_memory_repository.dart';
import 'package:quwoquan_app/assistant/retrieval/contracts/retrieval_models.dart';

class AssistantMemoryRecallService {
  const AssistantMemoryRecallService(this._memoryRepository);

  final AssistantMemoryRepository _memoryRepository;

  Future<AssistantRetrievalResult> recallByText({
    required String query,
    int limit = 5,
  }) async {
    final recall = await _memoryRepository.recallByText(
      query: query,
      limit: limit,
    );
    if (recall.isEmpty) {
      return const AssistantRetrievalResult(
        success: false,
        message: '未命中长期记忆。',
        providersUsed: <String>['memory'],
      );
    }
    return AssistantRetrievalResult(
      success: true,
      message: '已命中长期记忆。',
      items: recall
          .map(
            (item) => AssistantRetrievalItem(
              content: item.text,
              sourceType: 'memory',
              sourceId: item.id,
              relevance: 0.7,
              metadata: item.metadata,
            ),
          )
          .toList(growable: false),
      providersUsed: const <String>['memory'],
      coverageScore: 0.7,
      conflictScore: 0.0,
    );
  }
}
