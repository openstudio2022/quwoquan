import 'package:quwoquan_app/assistant/generated/enums/assistant_runtime_enums.g.dart';

String assistantPipelineInternalErrorMessage() {
  return '这次处理遇到了内部异常，我没有把答案组织完整。可以重新生成一次，我会基于已理解的需求继续处理。';
}

String assistantPipelineDefaultFailureMessageForStep(ProcessStepId stepId) {
  switch (stepId) {
    case ProcessStepId.understanding:
      return '我这次没有稳定理解你的需求，请重新发一次或补充关键信息。';
    case ProcessStepId.retrievalDesign:
    case ProcessStepId.retrievalProcessing:
      return '我这次没有稳定完成资料检索和筛选，请重新生成一次，我会继续围绕当前问题整理资料。';
    case ProcessStepId.answerOrganization:
      return '我已经完成前面的理解和资料整理，但这次最终答案没有组织成功。请重新生成一次，我会基于当前资料重新成答。';
    case ProcessStepId.unknown:
      return assistantPipelineInternalErrorMessage();
  }
}

String assistantPipelineDefaultReasonShort() {
  return '处理未完整完成';
}
