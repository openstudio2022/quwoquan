import 'package:quwoquan_app/assistant/generated/enums/assistant_runtime_enums.g.dart';

String assistantPipelineInternalErrorMessage() {
  return '助手内部出现意外错误，请重试。';
}

String assistantPipelineDefaultFailureMessageForStep(ProcessStepId stepId) {
  switch (stepId) {
    case ProcessStepId.understanding:
      return '理解阶段还没收敛，我先不继续往下生成答案。';
    case ProcessStepId.retrievalDesign:
      return '检索设计还没收敛，我先不继续往下生成答案。';
    case ProcessStepId.retrievalProcessing:
      return '这次拿到的结果还不够稳定，我先不继续往下生成答案。';
    case ProcessStepId.answerOrganization:
      return '这次生成答案失败，我先不强行给你结论，请稍后再试。';
    case ProcessStepId.unknown:
      return '这次处理失败了，我先不强行给你结论，请稍后再试。';
  }
}

String assistantPipelineDefaultReasonShort() {
  return '关键信息已经齐了，我先把结果整理成你能直接使用的答案。';
}
