import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_text_resolver.dart';
import 'package:quwoquan_app/assistant/protocol/profile_update_proposal.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';

class AssistantRunResponse {
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

  RunArtifacts? get runArtifacts {
    final raw = (structuredResponse['runArtifacts'] as Map?)
        ?.cast<String, dynamic>();
    if (raw == null) return null;
    return parseRunArtifacts(raw);
  }

  String get machineEnvelope {
    return runArtifacts?.machineEnvelope.trim() ?? '';
  }

  String get displayMarkdown =>
      _suppressStructuredDisplayLeak(runArtifacts?.displayMarkdown ?? '');

  String get displayPlainText =>
      _suppressStructuredDisplayLeak(runArtifacts?.displayPlainText ?? '');

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

String _suppressStructuredDisplayLeak(String value) {
  final normalized = value.trim();
  if (normalized.isEmpty) return '';
  if (AssistantDisplayTextResolver.containsUnsafeDisplayProtocolLeak(
    normalized,
  )) {
    return '';
  }
  return normalized;
}
