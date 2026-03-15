import 'package:quwoquan_app/assistant/internal_legacy/retrieval/retrieval_models.dart';

abstract class AssistantRetrievalProvider {
  String get providerId;
  List<String> get capabilityIds;

  Future<AssistantRetrievalResult> retrieve(AssistantRetrievalRequest request);
}

