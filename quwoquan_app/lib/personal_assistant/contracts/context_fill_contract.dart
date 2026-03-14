export 'package:quwoquan_app/personal_assistant/contracts/runtime_enums.dart';
export 'package:quwoquan_app/assistant/generated/contracts/context_fill_task.g.dart';

import 'package:quwoquan_app/personal_assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/generated/contracts/context_fill_task.g.dart';

class ContextFillTask extends ContextFillTaskDto {
  const ContextFillTask({
    required super.fillType,
    required super.targetSlot,
    required super.reason,
    super.generatedQueryConditions = const <String>[],
    super.scopeExpansionPolicy = ContextScopeExpansionPolicy.none,
    super.retryPolicy = ContextRetryPolicy.singleRetry,
  });

  factory ContextFillTask.fromJson(Map<String, dynamic> json) {
    final dto = ContextFillTaskDto.fromJson(json);
    return ContextFillTask(
      fillType: dto.fillType,
      targetSlot: dto.targetSlot,
      reason: dto.reason,
      generatedQueryConditions: dto.generatedQueryConditions,
      scopeExpansionPolicy: dto.scopeExpansionPolicy,
      retryPolicy: dto.retryPolicy,
    );
  }
}
