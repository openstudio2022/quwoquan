import 'package:quwoquan_app/personal_assistant/retrieval/retrieval_models.dart';

abstract class AssistantRetrievalProvider {
  String get providerId;
  List<String> get capabilityIds;

  Future<AssistantRetrievalResult> retrieve(AssistantRetrievalRequest request);
}

