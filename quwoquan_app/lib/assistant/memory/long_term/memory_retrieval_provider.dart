import 'package:quwoquan_app/assistant/memory/long_term/memory_recall_service.dart';
import 'package:quwoquan_app/assistant/retrieval/contracts/capability_catalog.dart';
import 'package:quwoquan_app/assistant/retrieval/contracts/retrieval_models.dart';
import 'package:quwoquan_app/assistant/retrieval/contracts/retrieval_provider.dart';

class MemoryRetrievalProvider implements AssistantRetrievalProvider {
  const MemoryRetrievalProvider(this._memoryRecallService);

  final AssistantMemoryRecallService _memoryRecallService;

  @override
  String get providerId => 'memory';

  @override
  List<String> get capabilityIds => const <String>[
    AssistantCapabilityCatalog.chatLongterm,
  ];

  @override
  Future<AssistantRetrievalResult> retrieve(
    AssistantRetrievalRequest request,
  ) async {
    return _memoryRecallService.recallByText(
      query: request.query,
      limit: request.maxItems,
    );
  }
}
