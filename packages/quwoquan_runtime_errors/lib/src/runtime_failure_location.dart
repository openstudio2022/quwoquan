class RuntimeFailureLocation {
  const RuntimeFailureLocation({
    required this.businessObject,
    required this.functionModule,
    this.sourceFilePath,
    this.sourceLineNumber,
    this.sourceLineText,
  });

  const RuntimeFailureLocation.unknown()
    : businessObject = 'unknown',
      functionModule = 'unknown',
      sourceFilePath = null,
      sourceLineNumber = null,
      sourceLineText = null;

  factory RuntimeFailureLocation.fromJson(Map<String, dynamic>? json) {
    if (json == null) return const RuntimeFailureLocation.unknown();
    return RuntimeFailureLocation(
      businessObject: ((json['businessObject'] as String?) ?? 'unknown').trim(),
      functionModule: ((json['functionModule'] as String?) ?? 'unknown').trim(),
      sourceFilePath: _optionalString(json['sourceFilePath']),
      sourceLineNumber: json['sourceLineNumber'] is int
          ? json['sourceLineNumber'] as int
          : int.tryParse((json['sourceLineNumber'] as String?) ?? ''),
      sourceLineText: _optionalString(json['sourceLineText']),
    ).normalized();
  }

  final String businessObject;
  final String functionModule;
  final String? sourceFilePath;
  final int? sourceLineNumber;
  final String? sourceLineText;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'businessObject': businessObject,
      'functionModule': functionModule,
      if (sourceFilePath != null) 'sourceFilePath': sourceFilePath,
      if (sourceLineNumber != null) 'sourceLineNumber': sourceLineNumber,
      if (sourceLineText != null) 'sourceLineText': sourceLineText,
    };
  }

  RuntimeFailureLocation normalized() {
    final normalizedBusinessObject = businessObject.trim();
    final normalizedFunctionModule = functionModule.trim();
    return RuntimeFailureLocation(
      businessObject: normalizedBusinessObject.isEmpty
          ? 'unknown'
          : normalizedBusinessObject,
      functionModule: normalizedFunctionModule.isEmpty
          ? 'unknown'
          : normalizedFunctionModule,
      sourceFilePath: sourceFilePath?.trim(),
      sourceLineNumber: sourceLineNumber,
      sourceLineText: sourceLineText?.trim(),
    );
  }
}

String? _optionalString(Object? raw) {
  if (raw is! String) return null;
  final trimmed = raw.trim();
  return trimmed.isEmpty ? null : trimmed;
}
