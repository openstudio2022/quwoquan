/// Skill setup 只接受 active package 中声明的安全 JSON Schema 子集。
///
/// 未支持的类型、可追加任意字段的 schema 或不完整的 enum 都会 fail-closed，
/// App 不猜测字段含义；服务端仍对提交值执行完整 canonical schema 校验。
final class AssistantSkillSetupSchema {
  const AssistantSkillSetupSchema({
    required this.title,
    required this.description,
    required this.fields,
  });

  final String title;
  final String description;
  final List<AssistantSkillSetupField> fields;

  static AssistantSkillSetupSchema? tryParse(
    dynamic document, {
    Iterable<String> requiredFields = const <String>[],
  }) {
    if (document is! Map || document['type'] != 'object') {
      return null;
    }
    if (document['additionalProperties'] != false) {
      return null;
    }
    final rawProperties = document['properties'];
    if (rawProperties is! Map) {
      return null;
    }
    final required = <String>{
      ...requiredFields
          .map((item) => item.trim())
          .where((item) => item.isNotEmpty),
    };
    final schemaRequired = document['required'];
    if (schemaRequired != null) {
      if (schemaRequired is! List ||
          schemaRequired.any((item) => item is! String)) {
        return null;
      }
      required.addAll(schemaRequired.cast<String>().map((item) => item.trim()));
    }
    final fields = <AssistantSkillSetupField>[];
    for (final entry in rawProperties.entries) {
      final id = entry.key.toString().trim();
      final raw = entry.value;
      if (id.isEmpty || raw is! Map) {
        return null;
      }
      final field = AssistantSkillSetupField.tryParse(
        id,
        raw,
        required: required.contains(id),
      );
      if (field == null) {
        return null;
      }
      fields.add(field);
    }
    if (required.any((field) => fields.every((item) => item.id != field))) {
      return null;
    }
    return AssistantSkillSetupSchema(
      title: _schemaText(document['title']),
      description: _schemaText(document['description']),
      fields: List<AssistantSkillSetupField>.unmodifiable(fields),
    );
  }
}

enum AssistantSkillSetupFieldKind { text, choice, integer, stringList }

final class AssistantSkillSetupField {
  const AssistantSkillSetupField({
    required this.id,
    required this.title,
    required this.description,
    required this.kind,
    required this.required,
    required this.options,
    required this.optionLabels,
    this.minimum,
    this.maximum,
    this.minLength,
    this.maxLength,
    this.maxItems,
  });

  final String id;
  final String title;
  final String description;
  final AssistantSkillSetupFieldKind kind;
  final bool required;
  final List<String> options;
  final Map<String, String> optionLabels;
  final int? minimum;
  final int? maximum;
  final int? minLength;
  final int? maxLength;
  final int? maxItems;

  static AssistantSkillSetupField? tryParse(
    String id,
    Map<dynamic, dynamic> raw, {
    required bool required,
  }) {
    final type = raw['type'];
    final rawOptions = raw['enum'];
    final kind = switch ((type, rawOptions)) {
      ('string', List _) => AssistantSkillSetupFieldKind.choice,
      ('string', null) => AssistantSkillSetupFieldKind.text,
      ('integer', null) => AssistantSkillSetupFieldKind.integer,
      ('array', null) => AssistantSkillSetupFieldKind.stringList,
      _ => null,
    };
    if (kind == null) {
      return null;
    }
    if (kind == AssistantSkillSetupFieldKind.stringList) {
      final items = raw['items'];
      if (items is! Map || items['type'] != 'string') {
        return null;
      }
    }
    final options = <String>[];
    if (rawOptions != null) {
      if (rawOptions is! List ||
          rawOptions.isEmpty ||
          rawOptions.any((item) => item is! String)) {
        return null;
      }
      options.addAll(rawOptions.cast<String>());
    }
    final labels = <String, String>{};
    final rawLabels = raw['x-enum-labels'];
    if (rawLabels != null) {
      if (rawLabels is! Map) {
        return null;
      }
      for (final entry in rawLabels.entries) {
        final key = entry.key.toString();
        final value = entry.value;
        if (!options.contains(key) ||
            value is! String ||
            value.trim().isEmpty) {
          return null;
        }
        labels[key] = value.trim();
      }
    }
    return AssistantSkillSetupField(
      id: id,
      title: _schemaText(raw['title'], fallback: id),
      description: _schemaText(raw['description']),
      kind: kind,
      required: required,
      options: List<String>.unmodifiable(options),
      optionLabels: Map<String, String>.unmodifiable(labels),
      minimum: _schemaInt(raw['minimum']),
      maximum: _schemaInt(raw['maximum']),
      minLength: _schemaInt(raw['minLength']),
      maxLength: _schemaInt(raw['maxLength']),
      maxItems: _schemaInt(raw['maxItems']),
    );
  }

  String labelFor(String value) => optionLabels[value] ?? value;

  String? validate(Object? value) {
    if (value == null || value == '' || (value is List && value.isEmpty)) {
      return required ? '$title不能为空' : null;
    }
    switch (kind) {
      case AssistantSkillSetupFieldKind.text:
        if (value is! String) return '$title格式不正确';
        if (minLength != null && value.length < minLength!) {
          return '$title至少需要 $minLength 个字';
        }
        if (maxLength != null && value.length > maxLength!) {
          return '$title不能超过 $maxLength 个字';
        }
      case AssistantSkillSetupFieldKind.choice:
        if (value is! String || !options.contains(value)) {
          return '请选择有效的$title';
        }
      case AssistantSkillSetupFieldKind.integer:
        if (value is! int) return '$title必须是整数';
        if (minimum != null && value < minimum!) {
          return '$title不能小于 $minimum';
        }
        if (maximum != null && value > maximum!) {
          return '$title不能大于 $maximum';
        }
      case AssistantSkillSetupFieldKind.stringList:
        if (value is! List<String>) return '$title格式不正确';
        if (maxItems != null && value.length > maxItems!) {
          return '$title最多填写 $maxItems 项';
        }
    }
    return null;
  }
}

String _schemaText(dynamic value, {String fallback = ''}) {
  if (value is! String || value.trim().isEmpty) {
    return fallback;
  }
  return value.trim();
}

int? _schemaInt(dynamic value) => value is num ? value.toInt() : null;
