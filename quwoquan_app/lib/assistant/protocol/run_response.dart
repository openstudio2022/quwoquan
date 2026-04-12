import 'package:quwoquan_app/assistant/contracts/assistant_run_structured_bundle.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_structured_response_wire.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_run_structured_interaction_view.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/retrieval_outcome.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_state_projection.dart';
import 'package:quwoquan_app/assistant/protocol/profile_update_proposal.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/answer_gate_resolver.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/retrieval_outcome_resolver.dart';

class AssistantRunResponse {
  static const RetrievalOutcomeResolver _retrievalOutcomeResolver =
      RetrievalOutcomeResolver();
  static const AnswerGateResolver _answerGateResolver = AnswerGateResolver();

  const AssistantRunResponse({
    required this.finalText,
    required this.traces,
    this.runId,
    this.traceId,
    this.degraded = false,
    this.errorCode,
    this.structuredResponse = const <String, dynamic>{},
    this.profileUpdateProposal,
  });

  final String finalText;
  final List<AssistantTraceEvent> traces;
  final String? runId;
  final String? traceId;
  final bool degraded;
  final String? errorCode;
  final Map<String, dynamic> structuredResponse;
  final ProfileUpdateProposal? profileUpdateProposal;

  /// metadata [`assistant_structured_response_wire`](quwoquan_service/contracts/metadata/assistant/assistant_structured_response_wire/schema.yaml) 子树视图。
  AssistantStructuredResponseWire get assistantStructuredWireView =>
      assistantStructuredWireFromStructuredRoot(structuredResponse);

  /// 模型交互子域：大图上的只读投影（具名 wire + artifacts），不替代 [structuredResponse] 持久化 Map。
  AssistantRunStructuredInteractionView get structuredInteractionView =>
      AssistantRunStructuredInteractionView(structuredResponse);

  /// 与 [structuredResponse] 同根的只读 bundle（runArtifacts + structured wire 子树）。
  AssistantRunStructuredBundle get structuredBundle =>
      AssistantRunStructuredBundle.fromStructuredResponseRoot(structuredResponse);

  RunArtifacts? get runArtifacts {
    final raw = (structuredResponse['runArtifacts'] as Map?)
        ?.cast<String, dynamic>();
    if (raw == null) return null;
    return parseRunArtifacts(raw);
  }

  RetrievalOutcome get retrievalOutcome {
    return _retrievalOutcomeResolver.resolveFromStructured(
      structured: structuredResponse,
      runArtifacts: runArtifacts,
      degraded: degraded,
    );
  }

  AnswerGateDecision get answerGateDecision {
    return _answerGateResolver.resolveFromStructured(
      structured: structuredResponse,
      runArtifacts: runArtifacts,
      degraded: degraded,
    );
  }

  String get machineEnvelope {
    return runArtifacts?.machineEnvelope.trim() ?? '';
  }

  String get displayMarkdown => runArtifacts?.displayMarkdown.trim() ?? '';

  String get displayPlainText =>
      runArtifacts?.displayPlainText.trim() ?? '';

  AssistantDisplayState get displayState {
    final raw = (structuredResponse['displayState'] as Map?)
        ?.cast<String, dynamic>();
    if (raw != null && raw.isNotEmpty) {
      return parseAssistantDisplayStateFromMap(raw);
    }
    final artifacts = runArtifacts;
    if (artifacts != null) {
      return resolveAssistantDisplayStateFromRunArtifacts(artifacts);
    }
    return const AssistantDisplayState();
  }

  String get followupPrompt =>
      (structuredResponse['followupPrompt'] as String?)?.trim() ?? '';

  List<String> get actionHints {
    final raw = structuredResponse['actionHints'];
    if (raw is! List) return const <String>[];
    return raw
        .whereType<String>()
        .map((item) => item.trim())
        .where((item) => item.isNotEmpty)
        .toList(growable: false);
  }

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'finalText': finalText,
      'traces': traces.map((t) => t.toJson()).toList(growable: false),
      'runId': runId,
      'traceId': traceId,
      'degraded': degraded,
      'errorCode': errorCode,
      'structuredResponse': structuredResponse,
      'profileUpdateProposal': profileUpdateProposal?.toJson(),
    };
  }

  factory AssistantRunResponse.fromJson(Map<String, dynamic> json) {
    final traceRaw = json['traces'];
    final traceList = traceRaw is List ? traceRaw : const <Never>[];
    final rawProposal = (json['profileUpdateProposal'] as Map?)
        ?.cast<String, dynamic>();
    return AssistantRunResponse(
      finalText: (json['finalText'] as String?) ?? '',
      traces: traceList
          .whereType<Map>()
          .map((e) => AssistantTraceEvent.fromJson(e.cast<String, dynamic>()))
          .toList(growable: false),
      runId: json['runId'] as String?,
      traceId: json['traceId'] as String?,
      degraded: json['degraded'] == true,
      errorCode: json['errorCode'] as String?,
      structuredResponse:
          (json['structuredResponse'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      profileUpdateProposal: rawProposal == null
          ? null
          : ProfileUpdateProposal.fromJson(rawProposal),
    );
  }
}
