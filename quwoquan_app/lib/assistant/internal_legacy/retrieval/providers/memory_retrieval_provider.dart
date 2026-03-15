import 'package:quwoquan_app/assistant/internal_legacy/retrieval/capability_catalog.dart';
import 'package:quwoquan_app/assistant/internal_legacy/retrieval/retrieval_models.dart';
import 'package:quwoquan_app/assistant/internal_legacy/retrieval/retrieval_provider.dart';
import 'package:quwoquan_app/assistant/internal_legacy/memory/memory_repository.dart';

class MemoryRetrievalProvider implements AssistantRetrievalProvider {
  const MemoryRetrievalProvider(this._memoryRepository);

  final AssistantMemoryRepository _memoryRepository;

  @override
  String get providerId => 'memory';

  @override
  List<String> get capabilityIds => const <String>[
        AssistantCapabilityCatalog.chatLongterm,
      ];

  @override
  Future<AssistantRetrievalResult> retrieve(AssistantRetrievalRequest request) async {
    final recall = await _memoryRepository.recallByText(
      query: request.query,
      limit: request.maxItems,
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

