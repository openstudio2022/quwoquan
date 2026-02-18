import 'package:quwoquan_app/personal_assistant/retrieval/retrieval_models.dart';

abstract class AssistentRetrievalProvider {
  String get providerId;
  List<String> get capabilityIds;

  Future<AssistentRetrievalResult> retrieve(AssistentRetrievalRequest request);
}

