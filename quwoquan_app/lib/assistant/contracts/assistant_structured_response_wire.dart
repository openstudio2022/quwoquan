export 'package:quwoquan_app/assistant/generated/contracts/assistant_structured_response_wire.g.dart';

import 'package:quwoquan_app/assistant/generated/contracts/assistant_structured_response_wire.g.dart';

/// 从 Run `structuredResponse` 根 Map 解析 wire，并对 `qualityMetrics` 内嵌键与顶层标量做双读合并。
AssistantStructuredResponseWire assistantStructuredWireFromStructuredRoot(
  Map<String, dynamic> json,
) {
  final base = AssistantStructuredResponseWire.fromJson(json);
  final qm = base.qualityMetrics;
  return AssistantStructuredResponseWire(
    qualityMetrics: qm,
    dialogueRuntime: base.dialogueRuntime,
    uiReferences: base.uiReferences,
    decisionParseSuccess: _mergeBoolTrueDefault(
      json['decisionParseSuccess'],
      qm['decisionParseSuccess'],
    ),
    hardCutSource: _mergeTrimmedStringTopOrNested(
      (json['hardCutSource'] as String?)?.trim() ?? '',
      qm['hardCutSource'],
    ),
    answerGateReady: _mergeBoolFalseDefault(
      json['answerGateReady'],
      qm['answerGateReady'],
    ),
    answerGateReasonCode: _mergeTrimmedStringTopOrNested(
      (json['answerGateReasonCode'] as String?)?.trim() ?? '',
      qm['answerGateReasonCode'],
    ),
    dialogueDomainId: _mergeTrimmedStringTopOrNested(
      (json['dialogueDomainId'] as String?)?.trim() ?? '',
      base.dialogueRuntime['domainId'],
    ),
  );
}

bool _mergeBoolTrueDefault(Object? top, Object? nested) {
  if (top != null) return top != false;
  if (nested != null) return nested == true;
  return true;
}

bool _mergeBoolFalseDefault(Object? top, Object? nested) {
  if (top != null) return top == true;
  if (nested != null) return nested == true;
  return false;
}

String _mergeTrimmedStringTopOrNested(String top, Object? nested) {
  if (top.trim().isNotEmpty) return top.trim();
  return nested?.toString().trim() ?? '';
}

extension AssistantStructuredResponseWireMergeX on AssistantStructuredResponseWire {
  /// 合并 `qualityMetrics` 扩展键，并在 patch 含对应键时同步更新具名标量字段。
  AssistantStructuredResponseWire mergeQualityMetrics(
    Map<String, dynamic> patch,
  ) {
    final mergedQm = <String, dynamic>{...qualityMetrics, ...patch};
    return AssistantStructuredResponseWire(
      qualityMetrics: mergedQm,
      dialogueRuntime: dialogueRuntime,
      uiReferences: uiReferences,
      decisionParseSuccess: patch.containsKey('decisionParseSuccess')
          ? (patch['decisionParseSuccess'] != false)
          : decisionParseSuccess,
      hardCutSource: patch.containsKey('hardCutSource')
          ? (patch['hardCutSource']?.toString().trim() ?? '')
          : hardCutSource,
      answerGateReady: patch.containsKey('answerGateReady')
          ? (patch['answerGateReady'] == true)
          : answerGateReady,
      answerGateReasonCode: patch.containsKey('answerGateReasonCode')
          ? (patch['answerGateReasonCode']?.toString().trim() ?? '')
          : answerGateReasonCode,
      dialogueDomainId: patch.containsKey('dialogueDomainId')
          ? (patch['dialogueDomainId']?.toString().trim() ?? '')
          : dialogueDomainId,
    );
  }
}
