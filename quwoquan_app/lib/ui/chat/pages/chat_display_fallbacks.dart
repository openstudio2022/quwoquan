import 'package:quwoquan_app/personal_assistant/protocol/run_response.dart';

String resolveActionLikeCompletedFallback(AssistantRunResponse response) {
  final structured = response.structuredResponse;
  final answerPayload =
      (structured['answerPayload'] as Map?)?.cast<String, dynamic>() ??
      const <String, dynamic>{};
  final decision =
      (answerPayload['decision'] as Map?)?.cast<String, dynamic>() ??
      (structured['decision'] as Map?)?.cast<String, dynamic>() ??
      const <String, dynamic>{};
  final nextAction = (decision['nextAction'] as String?)?.trim() ?? '';
  final messageKind =
      (answerPayload['messageKind'] as String?)?.trim() ??
      (structured['messageKind'] as String?)?.trim() ??
      '';
  final rawSignals = <String>[
    response.finalText,
    response.displayMarkdown,
    response.displayPlainText,
    answerPayload.toString(),
    structured['uiAnswer'].toString(),
  ].join('\n');
  final looksActionLike =
      nextAction == 'tool_call' ||
      nextAction == 'retry' ||
      nextAction == 'clarify' ||
      nextAction == 'ask_user' ||
      messageKind == 'progress' ||
      messageKind == 'tool_call' ||
      rawSignals.contains('<tool_call>') ||
      rawSignals.contains('tool_call');
  if (!looksActionLike) {
    return '';
  }
  if (nextAction == 'ask_user' || nextAction == 'clarify') {
    return '我还需要你再补充一点信息，这样才能继续。';
  }
  if (nextAction == 'retry') {
    return '这次没有拿到可靠结果，请稍后再试一次。';
  }
  return '这个操作我暂时还没拿到可展示结果，请再试一次。';
}
