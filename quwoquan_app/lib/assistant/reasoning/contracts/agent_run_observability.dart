class AgentRunObservabilityPayload {
  const AgentRunObservabilityPayload({
    required this.kind,
    required this.templateId,
    required this.templateVersion,
    required this.structuredResponse,
    required this.domainRouting,
    required this.retrievalRounds,
    required this.gapFillChain,
    required this.webPipeline,
    required this.profileProposalLifecycle,
    required this.userProfile,
    required this.learningTrack,
    required this.sensitiveBoundary,
    required this.resultSummary,
    required this.qualityMetrics,
  });

  final String kind;
  final String templateId;
  final String templateVersion;
  final Map<String, dynamic> structuredResponse;
  final Map<String, dynamic> domainRouting;
  final Map<String, dynamic> retrievalRounds;
  final Map<String, dynamic> gapFillChain;
  final Map<String, dynamic> webPipeline;
  final Map<String, dynamic> profileProposalLifecycle;
  final Map<String, dynamic> userProfile;
  final Map<String, dynamic> learningTrack;
  final Map<String, dynamic> sensitiveBoundary;
  final Map<String, dynamic> resultSummary;
  final Map<String, dynamic> qualityMetrics;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'kind': kind,
      'templateId': templateId,
      'templateVersion': templateVersion,
      'structuredResponse': structuredResponse,
      'domainRouting': domainRouting,
      'retrievalRounds': retrievalRounds,
      'gapFillChain': gapFillChain,
      'webPipeline': webPipeline,
      'profileProposalLifecycle': profileProposalLifecycle,
      'userProfile': userProfile,
      'learningTrack': learningTrack,
      'sensitiveBoundary': sensitiveBoundary,
      'resultSummary': resultSummary,
      'qualityMetrics': qualityMetrics,
    };
  }
}
