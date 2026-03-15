class KnowledgeQaEvidence {
  const KnowledgeQaEvidence({
    required this.provider,
    required this.title,
    required this.snippet,
    required this.url,
  });

  final String provider;
  final String title;
  final String snippet;
  final String url;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'provider': provider,
      'title': title,
      'snippet': snippet,
      'url': url,
    };
  }
}

class KnowledgeQaPlan {
  const KnowledgeQaPlan({
    required this.query,
    required this.domainId,
    required this.primaryProvider,
    required this.backupProviders,
    required this.maxEvidence,
  });

  final String query;
  final String domainId;
  final String primaryProvider;
  final List<String> backupProviders;
  final int maxEvidence;
}

class KnowledgeQaReport {
  const KnowledgeQaReport({
    required this.answer,
    required this.conclusion,
    required this.evidences,
    required this.uncertainty,
    required this.providersTried,
    required this.degraded,
  });

  final String answer;
  final String conclusion;
  final List<KnowledgeQaEvidence> evidences;
  final String uncertainty;
  final List<String> providersTried;
  final bool degraded;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'answer': answer,
      'conclusion': conclusion,
      'evidences': evidences.map((e) => e.toJson()).toList(growable: false),
      'uncertainty': uncertainty,
      'providersTried': providersTried,
      'degraded': degraded,
    };
  }
}
