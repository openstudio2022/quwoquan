class PromptTemplate {
  const PromptTemplate({
    required this.templateId,
    required this.templateVersion,
    required this.content,
    this.requiredVariables = const <String>[],
    this.metadata = const <String, dynamic>{},
  });

  final String templateId;
  final String templateVersion;
  final String content;
  final List<String> requiredVariables;
  final Map<String, dynamic> metadata;

  String key() => '$templateId@$templateVersion';

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'templateId': templateId,
      'templateVersion': templateVersion,
      'content': content,
      'requiredVariables': requiredVariables,
      'metadata': metadata,
    };
  }

  factory PromptTemplate.fromJson(Map<String, dynamic> json) {
    return PromptTemplate(
      templateId: (json['templateId'] as String?)?.trim() ?? '',
      templateVersion: (json['templateVersion'] as String?)?.trim() ?? 'v1',
      content: (json['content'] as String?) ?? '',
      requiredVariables:
          (json['requiredVariables'] as List?)
              ?.whereType<String>()
              .map((item) => item.trim())
              .where((item) => item.isNotEmpty)
              .toList(growable: false) ??
          const <String>[],
      metadata:
          (json['metadata'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
    );
  }
}

class RenderedPrompt {
  const RenderedPrompt({
    required this.templateId,
    required this.templateVersion,
    required this.content,
    required this.variableBindings,
  });

  final String templateId;
  final String templateVersion;
  final String content;
  final Map<String, dynamic> variableBindings;
}
