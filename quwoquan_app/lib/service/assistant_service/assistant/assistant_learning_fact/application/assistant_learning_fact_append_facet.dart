import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// AssistantLearningFact 的单轨 append command。
abstract class AssistantLearningFactAppendFacet {
  Future<AssistantLearningFactReceipt> appendUserFact({
    required AssistantLearningFactAppendCommand request,
  });
}
