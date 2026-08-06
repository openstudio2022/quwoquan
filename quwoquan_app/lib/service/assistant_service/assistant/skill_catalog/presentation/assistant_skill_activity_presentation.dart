import 'package:quwoquan_app/l10n/copy/assistant_text_constants.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

String assistantSkillActivityLabel(SkillActivityDisplayKey key) {
  return switch (key) {
    SkillActivityDisplayKey.runAccepted =>
      AssistantText.assistantSkillActivityRunAccepted,
    SkillActivityDisplayKey.runOrienting =>
      AssistantText.assistantSkillActivityRunOrienting,
    SkillActivityDisplayKey.runPlanning =>
      AssistantText.assistantSkillActivityRunPlanning,
    SkillActivityDisplayKey.runExecuting =>
      AssistantText.assistantSkillActivityRunExecuting,
    SkillActivityDisplayKey.runObserving =>
      AssistantText.assistantSkillActivityRunObserving,
    SkillActivityDisplayKey.runReflecting =>
      AssistantText.assistantSkillActivityRunReflecting,
    SkillActivityDisplayKey.runCheckpointing =>
      AssistantText.assistantSkillActivityRunCheckpointing,
    SkillActivityDisplayKey.runWaitingUser =>
      AssistantText.assistantSkillActivityRunWaitingUser,
    SkillActivityDisplayKey.runWaitingApproval =>
      AssistantText.assistantSkillActivityRunWaitingApproval,
    SkillActivityDisplayKey.runWaitingExternal =>
      AssistantText.assistantSkillActivityRunWaitingExternal,
    SkillActivityDisplayKey.runPaused =>
      AssistantText.assistantSkillActivityRunPaused,
    SkillActivityDisplayKey.runSynthesizing =>
      AssistantText.assistantSkillActivityRunSynthesizing,
    SkillActivityDisplayKey.runVerifying =>
      AssistantText.assistantSkillActivityRunVerifying,
    SkillActivityDisplayKey.runCompleted =>
      AssistantText.assistantSkillActivityRunCompleted,
    SkillActivityDisplayKey.runFailed =>
      AssistantText.assistantSkillActivityRunFailed,
    SkillActivityDisplayKey.runCancelled =>
      AssistantText.assistantSkillActivityRunCancelled,
    SkillActivityDisplayKey.consentGranted =>
      AssistantText.assistantSkillActivityConsentGranted,
    SkillActivityDisplayKey.consentRevoked =>
      AssistantText.assistantSkillActivityConsentRevoked,
    SkillActivityDisplayKey.subscriptionActive =>
      AssistantText.assistantSkillActivitySubscriptionActive,
    SkillActivityDisplayKey.subscriptionPaused =>
      AssistantText.assistantSkillActivitySubscriptionPaused,
    SkillActivityDisplayKey.subscriptionArchived =>
      AssistantText.assistantSkillActivitySubscriptionArchived,
    SkillActivityDisplayKey.dataControlPendingConfirmation =>
      AssistantText.assistantSkillDataControlPending,
    SkillActivityDisplayKey.dataControlExecuting =>
      AssistantText.assistantSkillDataControlExecuting,
    SkillActivityDisplayKey.dataControlCompleted =>
      AssistantText.assistantSkillDataControlCompleted,
    SkillActivityDisplayKey.dataControlCancelled =>
      AssistantText.assistantSkillDataControlCancelled,
    SkillActivityDisplayKey.dataControlFailed =>
      AssistantText.assistantSkillDataControlFailed,
  };
}

String assistantSkillDataControlActionLabel(SkillDataControlAction action) {
  return switch (action) {
    SkillDataControlAction.hideActivityHistory =>
      AssistantText.assistantSkillDataControlHideActivity,
    SkillDataControlAction.revokeConsent =>
      AssistantText.assistantSkillDataControlRevokeConsent,
    SkillDataControlAction.archiveSubscriptions =>
      AssistantText.assistantSkillDataControlArchiveSubscriptions,
  };
}

String assistantSkillDataControlStatusLabel(
  SkillDataControlRequestStatus status,
) {
  return switch (status) {
    SkillDataControlRequestStatus.pendingConfirmation =>
      AssistantText.assistantSkillDataControlPending,
    SkillDataControlRequestStatus.executing =>
      AssistantText.assistantSkillDataControlExecuting,
    SkillDataControlRequestStatus.completed =>
      AssistantText.assistantSkillDataControlCompleted,
    SkillDataControlRequestStatus.cancelled =>
      AssistantText.assistantSkillDataControlCancelled,
    SkillDataControlRequestStatus.failed =>
      AssistantText.assistantSkillDataControlFailed,
  };
}
