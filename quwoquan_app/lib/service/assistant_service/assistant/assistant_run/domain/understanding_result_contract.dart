// 理解结果契约的 Dto/serde 由 assistant/understanding_result/schema.yaml 单轨
// 生成（strict：未知键拒绝、非法枚举抛异常）。本文件只保留 LLM 直出边界的
// 宽容归一化 wrapper：模型输出可能带未登记键、脏 intent 项与非法枚举值，
// 归一化在这里一次完成，之后全程走 strict typed。
export 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/domain/generated/understanding_result.g.dart';

import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/domain/generated/understanding_result.g.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/domain/runtime_enums.dart';

class UnderstandingResult extends UnderstandingResultDto {
  const UnderstandingResult({
    super.contractId = 'understanding_result',
    super.intents = const <IntentNodeDto>[],
    super.dialogueTransitionDecision = const DialogueTransitionDecisionDto(),
  });

  factory UnderstandingResult.fromJson(Map<String, dynamic> json) {
    final dto = UnderstandingResultDto.fromJson(<String, dynamic>{
      UnderstandingResultDtoFields.contractId:
          (json[UnderstandingResultDtoFields.contractId] as String?)?.trim(),
      UnderstandingResultDtoFields.intents: _normalizedIntents(
        json[UnderstandingResultDtoFields.intents],
      ),
      UnderstandingResultDtoFields.dialogueTransitionDecision:
          _normalizedDecision(
            json[UnderstandingResultDtoFields.dialogueTransitionDecision],
          ),
    });
    return UnderstandingResult(
      contractId: dto.contractId,
      intents: dto.intents,
      dialogueTransitionDecision: dto.dialogueTransitionDecision,
    );
  }

  static List<Map<String, dynamic>> _normalizedIntents(Object? raw) {
    if (raw is! List) {
      return const <Map<String, dynamic>>[];
    }
    final intents = <Map<String, dynamic>>[];
    for (final item in raw.whereType<Map>()) {
      final intentId = (item[IntentNodeDtoFields.intentId] as String?)?.trim();
      final intentType = (item[IntentNodeDtoFields.intentType] as String?)
          ?.trim();
      final goal = (item[IntentNodeDtoFields.goal] as String?)?.trim();
      if (intentId == null ||
          intentId.isEmpty ||
          intentType == null ||
          intentType.isEmpty ||
          goal == null ||
          goal.isEmpty) {
        continue;
      }
      intents.add(<String, dynamic>{
        IntentNodeDtoFields.intentId: intentId,
        IntentNodeDtoFields.intentType: intentType,
        IntentNodeDtoFields.goal: goal,
        IntentNodeDtoFields.entityRefs: _normalizedEntityRefs(
          item[IntentNodeDtoFields.entityRefs],
        ),
        IntentNodeDtoFields.constraints: _normalizedConstraints(
          item[IntentNodeDtoFields.constraints],
        ),
        IntentNodeDtoFields.requiresEvidence:
            item[IntentNodeDtoFields.requiresEvidence] == true,
      });
    }
    return intents;
  }

  static List<Map<String, dynamic>> _normalizedEntityRefs(Object? raw) {
    if (raw is! List) {
      return const <Map<String, dynamic>>[];
    }
    final refs = <Map<String, dynamic>>[];
    for (final item in raw.whereType<Map>()) {
      final entityType = (item[IntentEntityRefDtoFields.entityType] as String?)
          ?.trim();
      final canonicalKey =
          (item[IntentEntityRefDtoFields.canonicalKey] as String?)?.trim();
      if (entityType == null ||
          entityType.isEmpty ||
          canonicalKey == null ||
          canonicalKey.isEmpty) {
        continue;
      }
      refs.add(<String, dynamic>{
        IntentEntityRefDtoFields.entityType: entityType,
        IntentEntityRefDtoFields.canonicalKey: canonicalKey,
        IntentEntityRefDtoFields.displayText:
            (item[IntentEntityRefDtoFields.displayText] as String?)?.trim() ??
            '',
      });
    }
    return refs;
  }

  static List<Map<String, dynamic>> _normalizedConstraints(Object? raw) {
    if (raw is! List) {
      return const <Map<String, dynamic>>[];
    }
    final constraints = <Map<String, dynamic>>[];
    for (final item in raw.whereType<Map>()) {
      final key = (item[IntentConstraintDtoFields.key] as String?)?.trim();
      if (key == null || key.isEmpty) {
        continue;
      }
      constraints.add(<String, dynamic>{
        IntentConstraintDtoFields.key: key,
        IntentConstraintDtoFields.value:
            (item[IntentConstraintDtoFields.value] as String?)?.trim() ?? '',
      });
    }
    return constraints;
  }

  static Map<String, dynamic> _normalizedDecision(Object? raw) {
    if (raw is! Map) {
      return const <String, dynamic>{};
    }
    return <String, dynamic>{
      DialogueTransitionDecisionDtoFields.nextTurnMode: parseNextTurnMode(
        (raw[DialogueTransitionDecisionDtoFields.nextTurnMode] as String?)
                ?.trim() ??
            '',
      ).wireName,
      DialogueTransitionDecisionDtoFields.needsClarification:
          raw[DialogueTransitionDecisionDtoFields.needsClarification] == true,
      DialogueTransitionDecisionDtoFields.clarificationTargetIntentId:
          (raw[DialogueTransitionDecisionDtoFields.clarificationTargetIntentId]
                  as String?)
              ?.trim() ??
          '',
      DialogueTransitionDecisionDtoFields.canAnswerPartially:
          raw[DialogueTransitionDecisionDtoFields.canAnswerPartially] == true,
    };
  }
}
