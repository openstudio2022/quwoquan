import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_entry_view/adapters/assistant_entry_remote.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_entry_view/application/assistant_entry_query.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_entry_view/application/assistant_personalization_facade.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_learning_fact/adapters/assistant_learning_fact_remote.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_preference/adapters/assistant_preference_remote.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_preference/application/assistant_preference_facet.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/adapters/assistant_run_remote.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/application/public/assistant_run_ports.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/application/public/assistant_session_run_facade.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/domain/assistant_presentation_capability_catalog.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/domain/assistant_run_stream_event.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_session/adapters/assistant_session_remote.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_session/application/public/assistant_session_ports.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_task_view/adapters/assistant_task_remote.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_task_view/application/assistant_task_query.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/adapters/assistant_turn_query_remote.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/application/public/assistant_turn_query.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/page_context/adapters/page_context_remote.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/page_context/application/public/page_context_command_writer.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/page_context/application/public/assistant_open_context.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/skill_activity_view/adapters/skill_activity_remote.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/skill_catalog/adapters/skill_catalog_remote.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/skill_consent/adapters/skill_consent_remote.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/skill_consent/adapters/assistant_consent_store.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/skill_consent/application/skill_consent_facet.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/skill_data_control_request/adapters/skill_data_control_remote.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/skill_subscription/adapters/skill_subscription_remote.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/skill_user_setting/adapters/skill_user_setting_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// assistant domain 的 production Remote adapter 种类。
///
/// 只有本文件可以命名 `Remote*` 实现；Provider 侧只声明 typed port 泛型。
enum AssistantProductionAdapter {
  learningFactAppend,
  skillActivity,
  skillCatalog,
  skillConsent,
  skillDataControl,
  skillSubscription,
  skillUserSetting,
}

/// assistant domain 的唯一 production 装配入口。
final class AssistantProductionComposition {
  const AssistantProductionComposition._();

  static AssistantSessionRunComposition sessionRunFacade({
    required GeneratedCloudOperationClient client,
    required Object invocationContext,
    required AssistantPresentationCapabilitySnapshotFactory
    presentationCapabilities,
  }) {
    final dynamic context = invocationContext;
    final session = AssistantSessionGeneratedAdapter(
      client: client,
      invocationContext: context,
    );
    final turn = AssistantTurnQueryGeneratedAdapter(
      client: client,
      invocationContext: context,
    );
    final run = AssistantRunGeneratedAdapter(
      client: client,
      invocationContext: context,
      presentationCapabilities: presentationCapabilities,
    );
    final runControl = AssistantRunHandoffControlAdapter(generated: run);
    return _AssistantSessionRunComposition(
      sessionCommandWriter: session,
      sessionQuery: session,
      turnQuery: turn,
      answerRunCommandWriter: run,
      runQuery: run,
      runEventStream: run,
      runControl: runControl,
      creationRunCommandWriter: run,
    );
  }

  static AssistantSearchRunFacade searchRunFacade({
    required GeneratedCloudOperationClient client,
    required Object invocationContext,
    required AssistantPresentationCapabilitySnapshotFactory
    presentationCapabilities,
  }) {
    final dynamic context = invocationContext;
    final session = AssistantSessionGeneratedAdapter(
      client: client,
      invocationContext: context,
      networkSurface: true,
    );
    final run = AssistantRunGeneratedAdapter(
      client: client,
      invocationContext: context,
      presentationCapabilities: presentationCapabilities,
      networkSurface: true,
    );
    return _AssistantSearchRunComposition(
      sessionCommandWriter: session,
      runIntentCommandWriter: run,
      runQuery: run,
      runEventStream: run,
    );
  }

  static AssistantPersonalizationFacade personalizationFacade({
    required GeneratedCloudOperationClient client,
    required Object invocationContext,
  }) {
    final dynamic context = invocationContext;
    return _AssistantPersonalizationComposition(
      pageContextCommandWriter: PageContextGeneratedAdapter(
        client: client,
        invocationContext: context,
      ),
      entryQuery: AssistantEntryGeneratedAdapter(
        client: client,
        invocationContext: context,
      ),
    );
  }

  static AssistantTaskQuery taskQuery({
    required GeneratedCloudOperationClient client,
    required Object invocationContext,
  }) {
    final dynamic context = invocationContext;
    return AssistantTaskGeneratedAdapter(
      client: client,
      invocationContext: context,
    );
  }

  static AssistantPreferenceFacet preferenceFacet({
    required GeneratedCloudOperationClient client,
    required Object invocationContext,
  }) {
    final dynamic context = invocationContext;
    return AssistantPreferenceGeneratedAdapter(
      client: client,
      invocationContext: context,
    );
  }

  /// skill_consent 的 production 形态是「Remote + 成功态本地快照装饰器」。
  ///
  /// 快照只在写成功后落盘，用于离线只读回显；它不是 fallback，Remote 失败仍向上
  /// 抛结构化失败，不会用快照伪造成功。
  static AssistantSkillConsentFacet skillConsentFacet({
    required GeneratedCloudOperationClient client,
    required Object invocationContext,
    required String accountId,
  }) {
    return AssistantConsentStore.decorateRemoteSuccess(
      accountId: accountId,
      remote: generatedAdapter<AssistantSkillConsentFacet>(
        AssistantProductionAdapter.skillConsent,
        client: client,
        invocationContext: invocationContext,
      ),
    );
  }

  static T generatedAdapter<T>(
    AssistantProductionAdapter adapter, {
    required GeneratedCloudOperationClient client,
    required Object invocationContext,
  }) {
    final dynamic context = invocationContext;
    final Object result = switch (adapter) {
      AssistantProductionAdapter.learningFactAppend =>
        RemoteAssistantLearningFactAppendAdapter(
          client: client,
          invocationContext: context,
        ),
      AssistantProductionAdapter.skillActivity =>
        RemoteAssistantSkillActivityAdapter(
          client: client,
          invocationContext: context,
        ),
      AssistantProductionAdapter.skillCatalog =>
        RemoteAssistantSkillCatalogAdapter(
          client: client,
          invocationContext: context,
        ),
      AssistantProductionAdapter.skillConsent =>
        RemoteAssistantSkillConsentAdapter(
          client: client,
          invocationContext: context,
        ),
      AssistantProductionAdapter.skillDataControl =>
        RemoteAssistantSkillDataControlAdapter(
          client: client,
          invocationContext: context,
        ),
      AssistantProductionAdapter.skillSubscription =>
        RemoteAssistantSkillSubscriptionAdapter(
          client: client,
          invocationContext: context,
        ),
      AssistantProductionAdapter.skillUserSetting =>
        RemoteAssistantSkillUserSettingAdapter(
          client: client,
          invocationContext: context,
        ),
    };
    return result as T;
  }
}

final class _AssistantSessionRunComposition
    implements AssistantSessionRunComposition {
  const _AssistantSessionRunComposition({
    required this.sessionCommandWriter,
    required this.sessionQuery,
    required this.turnQuery,
    required this.answerRunCommandWriter,
    required this.runQuery,
    required this.runEventStream,
    required this.runControl,
    required this.creationRunCommandWriter,
  });

  final AssistantSessionCommandWriter sessionCommandWriter;
  final AssistantSessionQuery sessionQuery;
  final AssistantTurnQuery turnQuery;
  final AssistantAnswerRunCommandWriter answerRunCommandWriter;
  final AssistantRunQuery runQuery;
  final AssistantRunEventStream runEventStream;
  final AssistantRunControlFacet runControl;
  final AssistantCreationRunCommandWriter creationRunCommandWriter;

  @override
  Future<AssistantSessionWire> createAssistantSession({
    String summary = '',
    required String clientRequestId,
  }) {
    return sessionCommandWriter.createAssistantSession(
      summary: summary,
      clientRequestId: clientRequestId,
    );
  }

  @override
  Future<AssistantSessionWire> getAssistantSession({
    required String sessionId,
  }) {
    return sessionQuery.getAssistantSession(sessionId: sessionId);
  }

  @override
  Future<AssistantSessionListView> listAssistantSessions({
    int limit = kAssistantSessionListDefaultLimit,
    String cursor = '',
  }) {
    return sessionQuery.listAssistantSessions(limit: limit, cursor: cursor);
  }

  @override
  Future<AssistantTurnListView> listSessionTurns({
    required String sessionId,
    int limit = kAssistantTurnListDefaultLimit,
    String cursor = '',
  }) {
    return turnQuery.listSessionTurns(
      sessionId: sessionId,
      limit: limit,
      cursor: cursor,
    );
  }

  @override
  Future<AssistantRunEnvelopeWire> startAssistantRun({
    required String sessionId,
    required String text,
    required String clientRequestId,
    List<AssistantIntersectionEvidenceRef> intersectionEvidenceRefs =
        const <AssistantIntersectionEvidenceRef>[],
  }) {
    return answerRunCommandWriter.startAssistantRun(
      sessionId: sessionId,
      text: text,
      clientRequestId: clientRequestId,
      intersectionEvidenceRefs: intersectionEvidenceRefs,
    );
  }

  @override
  Future<AssistantRunEnvelopeWire> getAssistantRun({required String runId}) {
    return runQuery.getAssistantRun(runId: runId);
  }

  @override
  Future<AssistantRunEnvelopeWire> cancelAssistantRun({
    required String runId,
    required String commandRequestId,
  }) {
    return answerRunCommandWriter.cancelAssistantRun(
      runId: runId,
      commandRequestId: commandRequestId,
    );
  }

  @override
  Stream<AssistantStreamEventWire> watchAssistantRunEvents({
    required String runId,
    String lastEventId = '',
  }) {
    return runEventStream.watchAssistantRunEvents(
      runId: runId,
      lastEventId: lastEventId,
    );
  }

  @override
  Future<AssistantRunEnvelopeWire> pauseAssistantRun({
    required String runId,
    required String commandRequestId,
    String reason = '',
  }) {
    return runControl.pauseAssistantRun(
      runId: runId,
      commandRequestId: commandRequestId,
      reason: reason,
    );
  }

  @override
  Future<AssistantRunEnvelopeWire> resumeAssistantRun({
    required String runId,
    required String commandRequestId,
  }) {
    return runControl.resumeAssistantRun(
      runId: runId,
      commandRequestId: commandRequestId,
    );
  }

  @override
  Future<AssistantRunEnvelopeWire> steerAssistantRun({
    required String runId,
    required String commandRequestId,
    required String instruction,
  }) {
    return runControl.steerAssistantRun(
      runId: runId,
      commandRequestId: commandRequestId,
      instruction: instruction,
    );
  }

  @override
  Future<AssistantToolApprovalResult> approveAssistantToolUse({
    required String runId,
    required String toolInvocationId,
    required String commandRequestId,
    required String decision,
    required String approvalPermit,
    String? installationId,
    String? deviceId,
  }) {
    return runControl.approveAssistantToolUse(
      runId: runId,
      toolInvocationId: toolInvocationId,
      commandRequestId: commandRequestId,
      decision: decision,
      approvalPermit: approvalPermit,
      installationId: installationId,
      deviceId: deviceId,
    );
  }

  @override
  Future<AssistantRunEnvelopeWire> submitDeviceActionReceipt({
    required String runId,
    required String toolInvocationId,
    required String commandRequestId,
    required AssistantDeviceActionExecutionReceipt receipt,
  }) {
    return runControl.submitDeviceActionReceipt(
      runId: runId,
      toolInvocationId: toolInvocationId,
      commandRequestId: commandRequestId,
      receipt: receipt,
    );
  }

  @override
  Future<AssistantRunEnvelopeWire> startCreationRun({
    required String sessionId,
    required String clientRequestId,
    required AssistantCreationRunIntent intent,
    AssistantContextSnapshot? contextSnapshot,
  }) {
    return creationRunCommandWriter.startCreationRun(
      sessionId: sessionId,
      clientRequestId: clientRequestId,
      intent: intent,
      contextSnapshot: contextSnapshot,
    );
  }
}

final class _AssistantSearchRunComposition implements AssistantSearchRunFacade {
  const _AssistantSearchRunComposition({
    required this.sessionCommandWriter,
    required this.runIntentCommandWriter,
    required this.runQuery,
    required this.runEventStream,
  });

  final AssistantSessionCommandWriter sessionCommandWriter;
  final AssistantRunIntentCommandWriter runIntentCommandWriter;
  final AssistantRunQuery runQuery;
  final AssistantRunEventStream runEventStream;

  @override
  Future<AssistantRunTerminalSnapshotView> executeAssistantSearch({
    required String query,
    required String sessionClientRequestId,
    required String runClientRequestId,
    SearchIntensity searchIntensity = SearchIntensity.medium,
    AssistantContextSnapshot? contextSnapshot,
  }) async {
    final normalizedQuery = query.trim();
    if (normalizedQuery.isEmpty) {
      throw ArgumentError.value(query, 'query', 'must not be empty');
    }
    final session = await sessionCommandWriter.createAssistantSession(
      summary: normalizedQuery,
      clientRequestId: sessionClientRequestId,
    );
    final run = await runIntentCommandWriter.startAssistantRunIntent(
      sessionId: session.sessionId,
      clientRequestId: runClientRequestId,
      intent: AssistantRunIntent(
        kind: AssistantRunIntentKind.search,
        search: AssistantSearchRunIntent(
          query: normalizedQuery,
          searchIntensity: searchIntensity,
          sourceSurfaceId: AppUiSurfaces.globalSearchNetworkResults.id,
          fromGlobalSearch: true,
        ),
      ),
      contextSnapshot: contextSnapshot,
    );
    await for (final event in runEventStream.watchAssistantRunEvents(
      runId: run.runId,
    )) {
      if (parseAssistantRunStreamEventType(
        event.eventType.wireName,
      ).isTerminal) {
        break;
      }
    }
    final terminalRun = await runQuery.getAssistantRun(runId: run.runId);
    final snapshot = terminalRun.terminalSnapshot;
    if (snapshot == null) {
      throw const FormatException(
        'assistant search run completed without terminalSnapshot',
      );
    }
    if (snapshot.failure != null) {
      throw FormatException(
        'assistant search run failed: ${snapshot.failure!.code}',
      );
    }
    return snapshot;
  }
}

final class _AssistantPersonalizationComposition
    implements AssistantPersonalizationFacade {
  const _AssistantPersonalizationComposition({
    required this.pageContextCommandWriter,
    required this.entryQuery,
  });

  final PageContextCommandWriter pageContextCommandWriter;
  final AssistantEntryViewQuery entryQuery;

  @override
  Future<PageContextReceipt> reportPageContext({
    required AssistantOpenContext context,
    String? userAction,
  }) {
    return pageContextCommandWriter.reportPageContext(
      context: context,
      userAction: userAction,
    );
  }

  @override
  Future<AssistantEntryResponse> getAssistantEntry({
    required AssistantOpenContext context,
  }) {
    return entryQuery.getAssistantEntry(context: context);
  }
}
