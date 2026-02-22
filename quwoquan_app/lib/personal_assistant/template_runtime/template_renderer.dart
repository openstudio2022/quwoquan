import 'package:quwoquan_app/personal_assistant/template_runtime/prompt_template.dart';

class TemplateRenderResult {
  const TemplateRenderResult({
    required this.rendered,
    required this.missingVariables,
  });

  final RenderedPrompt rendered;
  final List<String> missingVariables;

  bool get isValid => missingVariables.isEmpty;
}

class TemplateRenderer {
  const TemplateRenderer();

  TemplateRenderResult render({
    required PromptTemplate template,
    required Map<String, dynamic> variables,
  }) {
    final missing = <String>[];
    for (final key in template.requiredVariables) {
      final value = variables[key];
      if (value == null) {
        missing.add(key);
        continue;
      }
      if (value is String && value.trim().isEmpty) {
        missing.add(key);
      }
    }
    var content = template.content;
    final bindings = <String, dynamic>{};
    for (final entry in variables.entries) {
      final value = _stringify(entry.value);
      bindings[entry.key] = value;
      content = content.replaceAll('{{${entry.key}}}', value);
    }
    final rendered = RenderedPrompt(
      templateId: template.templateId,
      templateVersion: template.templateVersion,
      content: content,
      variableBindings: bindings,
    );
    return TemplateRenderResult(rendered: rendered, missingVariables: missing);
  }

  String _stringify(dynamic value) {
    if (value == null) return '';
    if (value is String) return value;
    if (value is num || value is bool) return '$value';
    if (value is Iterable) return value.map(_stringify).join(', ');
    if (value is Map) return value.toString();
    return value.toString();
  }
}
