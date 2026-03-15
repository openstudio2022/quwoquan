import 'package:quwoquan_app/assistant/internal_legacy/template_runtime/prompt_template.dart';
import 'package:quwoquan_app/assistant/internal_legacy/template_runtime/template_registry.dart';
import 'package:quwoquan_app/assistant/internal_legacy/template_runtime/template_renderer.dart';

class PromptTemplateRuntime {
  PromptTemplateRuntime({
    required TemplateRegistry registry,
    TemplateSelector? selector,
    TemplateRenderer? renderer,
  }) : _registry = registry,
       _selector = selector ?? const TemplateSelector(),
       _renderer = renderer ?? const TemplateRenderer();

  final TemplateRegistry _registry;
  final TemplateSelector _selector;
  final TemplateRenderer _renderer;

  Future<TemplateRuntimeOutput> renderTemplate({
    required String templateId,
    required String defaultVersion,
    required Map<String, dynamic> variables,
    Map<String, dynamic> selectionContext = const <String, dynamic>{},
  }) async {
    await _registry.ensureLoaded();
    final selection = _selector.select(
      templateId: templateId,
      defaultVersion: defaultVersion,
      context: selectionContext,
    );
    final selectedTemplate =
        _registry.getTemplate(templateId, selection.templateVersion) ??
        _registry.getTemplate(templateId, defaultVersion) ??
        _registry.getLatestById(templateId);
    if (selectedTemplate == null) {
      return TemplateRuntimeOutput(
        rendered: RenderedPrompt(
          templateId: templateId,
          templateVersion: defaultVersion,
          content: '',
          variableBindings: const <String, dynamic>{},
        ),
        bucket: selection.bucket,
        missingVariables: const <String>['__template_not_found__'],
      );
    }
    final renderResult = _renderer.render(
      template: selectedTemplate,
      variables: variables,
    );
    return TemplateRuntimeOutput(
      rendered: renderResult.rendered,
      bucket: selection.bucket,
      missingVariables: renderResult.missingVariables,
    );
  }
}

class TemplateRuntimeOutput {
  const TemplateRuntimeOutput({
    required this.rendered,
    required this.bucket,
    required this.missingVariables,
  });

  TemplateRuntimeOutput.empty({
    required String templateId,
    required String templateVersion,
  }) : rendered = RenderedPrompt(
         templateId: templateId,
         templateVersion: templateVersion,
         content: '',
         variableBindings: const <String, dynamic>{},
       ),
       bucket = 'control',
       missingVariables = const <String>['__template_not_found__'];

  final RenderedPrompt rendered;
  final String bucket;
  final List<String> missingVariables;
}
