import 'package:quwoquan_app/personal_assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/personal_assistant/protocol/profile_update_proposal.dart';

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
    final traceList = (json['traces'] as List?) ?? const <dynamic>[];
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
