class TemplateValidationResult {
  const TemplateValidationResult({required this.errors});

  final List<String> errors;

  bool get isValid => errors.isEmpty;
}

class TemplateValidator {
  const TemplateValidator();

  static const List<String> _requiredSections = <String>[
    '## 任务背景',
    '## 任务目标',
    '## 约束',
    '## 执行要求',
    '## 输出格式',
    '## 反思与自检',
    '=== CONTEXT_DATA_START ===',
    '=== CONTEXT_DATA_END ===',
  ];

  TemplateValidationResult validate({
    required String templateId,
    required String content,
  }) {
    final errors = <String>[];
    for (final section in _requiredSections) {
      if (!content.contains(section)) {
        errors.add('$templateId missing section: $section');
      }
    }
    final start = content.indexOf('=== CONTEXT_DATA_START ===');
    final end = content.indexOf('=== CONTEXT_DATA_END ===');
    if (start < 0 || end < 0 || end <= start) {
      errors.add('$templateId has invalid data boundary');
      return TemplateValidationResult(errors: errors);
    }
    final beforeData = content.substring(0, start);
    final dataBlock = content.substring(start, end);
    if (beforeData.contains('{{') && beforeData.contains('CONTEXT_DATA_START')) {
      errors.add('$templateId instruction area contains data marker misuse');
    }
    if (dataBlock.contains('## ')) {
      errors.add('$templateId data block contains instruction headings');
    }
    return TemplateValidationResult(errors: errors);
  }
}

