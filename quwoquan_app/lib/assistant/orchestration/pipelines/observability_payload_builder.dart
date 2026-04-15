import 'package:quwoquan_app/assistant/reasoning/contracts/agent_run_observability.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/run_response.dart';

/// Builds the observability payload for agent run logging.
///
/// All methods are stateless pure functions — no instance field dependencies.
class ObservabilityPayloadBuilder {
  const ObservabilityPayloadBuilder();

  // ASSISTANT_WEAK_TYPE: observability JSON payload boundary
  Map<String, dynamic> call({
    required AssistantRunResponse response,
    required AssistantRunRequest request,
  }) {
    return buildObservabilityPayload(response: response, request: request);
  }

  // ASSISTANT_WEAK_TYPE: observability JSON payload boundary
  static Map<String, dynamic> buildObservabilityPayload({
    required AssistantRunResponse response,
    required AssistantRunRequest request,
  }) {
    final structured = response.structuredResponse;
    final domainResults =
        (structured['domainResults'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final payload = AgentRunObservabilityPayload(
      kind: 'agent_run',
      templateId: 'synthesizer.final_answer',
      templateVersion:
          (structured['templateVersionUsed'] as String?)?.trim().isNotEmpty ==
              true
          ? (structured['templateVersionUsed'] as String).trim()
          : 'latest',
      structuredResponse: <String, dynamic>{
        'contextAssembly':
            structured['contextAssembly'] ?? const <String, dynamic>{},
        'domainPrecheck':
            structured['domainPrecheck'] ?? const <String, dynamic>{},
        'synthesisReadiness':
            structured['synthesisReadiness'] ?? const <String, dynamic>{},
        'contextSlots':
            structured['contextSlots'] ?? const <Map<String, dynamic>>[],
        'dialogueRuntime':
            structured['dialogueRuntime'] ?? const <String, dynamic>{},
        'roundTrace': structured['roundTrace'] ?? const <String, dynamic>{},
        'fillActions':
            structured['fillActions'] ?? const <Map<String, dynamic>>[],
        'missingCriticalSlots':
            structured['missingCriticalSlots'] ?? const <String>[],
        'answerEligibility': structured['answerEligibility'] ?? 'unknown',
        'selfCheck': structured['selfCheck'] ?? const <String, dynamic>{},
        'diagnostics': structured['diagnostics'] ?? const <String, dynamic>{},
        'webEvidencePacks':
            structured['webEvidencePacks'] ?? const <Map<String, dynamic>>[],
        'webEvidenceGate':
            structured['webEvidenceGate'] ?? const <String, dynamic>{},
      },
      domainRouting: <String, dynamic>{
        'catalogVersion':
            (structured['domainCatalogVersion'] as String?) ?? '',
        'candidateDomains':
            (structured['candidateDomains'] as List?)
                ?.whereType<String>()
                .toList(growable: false) ??
            const <String>[],
        'domainScores': const <String, double>{},
        'selectedDomains': <String>[
          ((structured['dialogueRuntime'] as Map?)?['domainId'] as String?) ??
              'fallback_general_search',
        ],
        'fallbackTriggered':
            (((structured['dialogueRuntime'] as Map?)?['domainId']
                    as String?) ??
                '') ==
            'fallback_general_search',
        'fallbackReason': '',
      },
      retrievalRounds: <String, dynamic>{
        'retrievalRound': 1,
        'queryId': response.runId ?? '',
        'topicId': request.messages.isNotEmpty
            ? request.messages.last.content
            : '',
        'singleTopic': true,
        'providerHint': '',
        'scopeExpansionPolicy': '',
        'usedHistoricalStrategy': false,
      },
      gapFillChain: <String, dynamic>{
        'triggerReason':
            ((structured['synthesisReadiness'] as Map?)?['reason'] ?? '')
                .toString(),
        'contextFillTaskCount':
            ((structured['fillTasks'] as Map?)?['contextFillTasks'] as List?)
                ?.length ??
            0,
        'hasReplanTask':
            ((structured['fillTasks'] as Map?)?['replanTask']) != null,
      },
      webPipeline: <String, dynamic>{
        'evidencePackCount':
            ((structured['webEvidencePacks'] as List?)?.length ?? 0),
        'gatePassed':
            ((structured['webEvidenceGate'] as Map?)?['passed']) == true,
      },
      profileProposalLifecycle: <String, dynamic>{
        'proposalId': response.profileUpdateProposal?.proposalId ?? '',
        'proposalStatus': response.profileUpdateProposal == null
            ? 'none'
            : 'created',
        'statusChangedAt': DateTime.now().toIso8601String(),
        'changedBy': 'assistant',
        'idempotencyKey': response.profileUpdateProposal?.proposalId ?? '',
      },
      userProfile: <String, dynamic>{
        'profileVersion': (structured['profileVersion'] ?? '').toString(),
        'profileReadAt': DateTime.now().toIso8601String(),
        'profileUpdateProposalId':
            response.profileUpdateProposal?.proposalId ?? '',
        'profileUpdateConfirmedByUser': false,
      },
      learningTrack: <String, dynamic>{
        'profileTagDelta':
            ((structured['learningSignals'] as Map?)?['profileTagDelta']) ??
            const <Map<String, dynamic>>[],
        'satisfactionProxy':
            ((structured['learningSignals'] as Map?)?['satisfactionProxy'] ??
                    'unknown')
                .toString(),
        'strategySelectionReason':
            ((structured['learningSignals']
                        as Map?)?['strategySelectionReason'] ??
                    '')
                .toString(),
      },
      sensitiveBoundary: redactSensitiveProfile(structured: structured),
      resultSummary: <String, dynamic>{
        'toolResultCount':
            ((domainResults['toolResults'] as List?)?.length ?? 0),
        'toolErrorCount':
            ((domainResults['toolErrors'] as List?)?.length ?? 0),
        'degraded': response.degraded,
      },
      qualityMetrics:
          structured['qualityMetrics'] ?? const <String, dynamic>{},
    );
    return payload.toJson();
  }

  static Map<String, dynamic> redactSensitiveProfile({
    required Map<String, dynamic> structured,
  }) {
    final basicIdentity =
        (structured['basicIdentity'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final ipResidence =
        (structured['ipResidenceProfile'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    return <String, dynamic>{
      'birthDateSolar': _maskDate(
        (basicIdentity['birthDateSolar'] ?? '').toString(),
      ),
      'birthDateLunar': _maskDate(
        (basicIdentity['birthDateLunar'] ?? '').toString(),
      ),
      'ageRange': _ageRangeLabel((basicIdentity['age'] as num?)?.toInt()),
      'ipResidenceProfile': <String, dynamic>{
        'home': _maskResidence(ipResidence['home']),
        'office': _maskResidence(ipResidence['office']),
        'study': _maskResidence(ipResidence['study']),
      },
      'retentionPolicy': 'sensitive_fields_30d_masked',
      'deleteMark': false,
    };
  }

  static String _ageRangeLabel(int? age) {
    if (age == null || age <= 0) return '';
    if (age < 18) return '<18';
    if (age <= 24) return '18-24';
    if (age <= 34) return '25-34';
    if (age <= 44) return '35-44';
    if (age <= 54) return '45-54';
    return '55+';
  }

  static String _maskDate(String raw) {
    if (raw.isEmpty) return '';
    if (raw.length <= 4) return '****';
    return '${raw.substring(0, 4)}-**-**';
  }

  static String _maskResidence(dynamic value) {
    final text = (value ?? '').toString().trim();
    if (text.isEmpty) return '';
    if (text.length <= 2) return '${text.substring(0, 1)}*';
    return '${text.substring(0, 2)}**';
  }
}
