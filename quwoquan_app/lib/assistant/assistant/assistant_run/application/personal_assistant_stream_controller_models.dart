part of 'personal_assistant_stream_controller.dart';

enum _PersonalAssistantRetryKind { send, openRun, history, switchSession }

const Object _unsetAssistantFailure = Object();

const String _assistantTurnActionSubmit = 'submit';
const String _assistantTurnActionFirstAnswer = 'first_answer';
const String _assistantTurnActionCompleted = 'completed';
const String _assistantTurnActionFailed = 'failed';
const String _assistantTurnActionCancelled = 'cancelled';
const String _assistantTurnActionStreamFailure = 'stream_failure';

const String _assistantTurnResultSuccess = 'success';
const String _assistantTurnResultFailure = 'failure';
const String _assistantTurnResultCancelled = 'cancelled';

class PersonalAssistantStreamState {
  const PersonalAssistantStreamState({
    this.sessionId = '',
    this.runId = '',
    this.runStatus = '',
    this.answer = '',
    this.transcript = const <AssistantTranscriptTimelineRow>[],
    this.processSummary = const PersonalAssistantProcessSummary(),
    this.events = const <AssistantStreamEventWire>[],
    this.answerGateOpen = false,
    this.running = false,
    this.errorMessage = '',
    this.errorFailure,
    this.retryAvailable = false,
    this.appMessageUnreadCount = 0,
    this.managementSummaryLoading = false,
    this.feedbackMessage = '',
    this.feedbackType = '',
    this.historyInitialized = false,
    this.historyLoading = false,
  });

  final String sessionId;
  final String runId;
  final String runStatus;
  final String answer;
  final List<AssistantTranscriptTimelineRow> transcript;
  final PersonalAssistantProcessSummary processSummary;
  final List<AssistantStreamEventWire> events;
  final bool answerGateOpen;
  final bool running;
  final String errorMessage;
  final RuntimeFailureBase? errorFailure;
  final bool retryAvailable;
  final int appMessageUnreadCount;
  final bool managementSummaryLoading;
  final String feedbackMessage;
  final String feedbackType;
  final bool historyInitialized;
  final bool historyLoading;

  PersonalAssistantStreamState copyWith({
    String? sessionId,
    String? runId,
    String? runStatus,
    String? answer,
    List<AssistantTranscriptTimelineRow>? transcript,
    PersonalAssistantProcessSummary? processSummary,
    List<AssistantStreamEventWire>? events,
    bool? answerGateOpen,
    bool? running,
    String? errorMessage,
    Object? errorFailure = _unsetAssistantFailure,
    bool? retryAvailable,
    int? appMessageUnreadCount,
    bool? managementSummaryLoading,
    String? feedbackMessage,
    String? feedbackType,
    bool? historyInitialized,
    bool? historyLoading,
  }) {
    return PersonalAssistantStreamState(
      sessionId: sessionId ?? this.sessionId,
      runId: runId ?? this.runId,
      runStatus: runStatus ?? this.runStatus,
      answer: answer ?? this.answer,
      transcript: transcript ?? this.transcript,
      processSummary: processSummary ?? this.processSummary,
      events: events ?? this.events,
      answerGateOpen: answerGateOpen ?? this.answerGateOpen,
      running: running ?? this.running,
      errorMessage: errorMessage ?? this.errorMessage,
      errorFailure: identical(errorFailure, _unsetAssistantFailure)
          ? this.errorFailure
          : errorFailure as RuntimeFailureBase?,
      retryAvailable: retryAvailable ?? this.retryAvailable,
      appMessageUnreadCount:
          appMessageUnreadCount ?? this.appMessageUnreadCount,
      managementSummaryLoading:
          managementSummaryLoading ?? this.managementSummaryLoading,
      feedbackMessage: feedbackMessage ?? this.feedbackMessage,
      feedbackType: feedbackType ?? this.feedbackType,
      historyInitialized: historyInitialized ?? this.historyInitialized,
      historyLoading: historyLoading ?? this.historyLoading,
    );
  }
}

class PersonalAssistantProcessSummary {
  const PersonalAssistantProcessSummary({
    this.processedCount = 0,
    this.searchCount = 0,
    this.acceptedCount = 0,
    this.elapsedMs = 0,
    this.lines = const <String>[],
    this.understandingSummary = '',
    this.retrievalDesignNarrative = '',
    this.processingSummary = '',
    this.expansionReason = '',
    this.finalAnswerSummary = '',
    this.finalAnswerReady = false,
    this.processes = const <AssistantRunVisibleProcess>[],
    this.selectedKeyPoints = const <String>[],
    this.acceptedReferences = const <RetrievalProcessingReference>[],
  });

  final int processedCount;
  final int searchCount;
  final int acceptedCount;
  final int elapsedMs;
  final List<String> lines;
  final String understandingSummary;
  final String retrievalDesignNarrative;
  final String processingSummary;
  final String expansionReason;
  final String finalAnswerSummary;
  final bool finalAnswerReady;
  final List<AssistantRunVisibleProcess> processes;
  final List<String> selectedKeyPoints;
  final List<RetrievalProcessingReference> acceptedReferences;

  PersonalAssistantProcessSummary copyWith({
    int? processedCount,
    int? searchCount,
    int? acceptedCount,
    int? elapsedMs,
    List<String>? lines,
    String? understandingSummary,
    String? retrievalDesignNarrative,
    String? processingSummary,
    String? expansionReason,
    String? finalAnswerSummary,
    bool? finalAnswerReady,
    List<AssistantRunVisibleProcess>? processes,
    List<String>? selectedKeyPoints,
    List<RetrievalProcessingReference>? acceptedReferences,
  }) {
    return PersonalAssistantProcessSummary(
      processedCount: processedCount ?? this.processedCount,
      searchCount: searchCount ?? this.searchCount,
      acceptedCount: acceptedCount ?? this.acceptedCount,
      elapsedMs: elapsedMs ?? this.elapsedMs,
      lines: lines ?? this.lines,
      understandingSummary: understandingSummary ?? this.understandingSummary,
      retrievalDesignNarrative:
          retrievalDesignNarrative ?? this.retrievalDesignNarrative,
      processingSummary: processingSummary ?? this.processingSummary,
      expansionReason: expansionReason ?? this.expansionReason,
      finalAnswerSummary: finalAnswerSummary ?? this.finalAnswerSummary,
      finalAnswerReady: finalAnswerReady ?? this.finalAnswerReady,
      processes: processes ?? this.processes,
      selectedKeyPoints: selectedKeyPoints ?? this.selectedKeyPoints,
      acceptedReferences: acceptedReferences ?? this.acceptedReferences,
    );
  }

  bool get hasContent =>
      processedCount > 0 ||
      searchCount > 0 ||
      acceptedCount > 0 ||
      lines.isNotEmpty ||
      processes.isNotEmpty ||
      understandingSummary.trim().isNotEmpty ||
      retrievalDesignNarrative.trim().isNotEmpty ||
      processingSummary.trim().isNotEmpty ||
      finalAnswerSummary.trim().isNotEmpty ||
      acceptedReferences.isNotEmpty;
}
