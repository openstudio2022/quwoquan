import 'package:quwoquan_app/assistant/internal_legacy/template_runtime/prompt_template.dart';
import 'package:quwoquan_app/assistant/internal_legacy/template_runtime/template_registry.dart';
import 'package:quwoquan_app/assistant/internal_legacy/template_runtime/template_runtime.dart';
import 'package:test/test.dart';

void main() {
  group('PromptTemplateRuntime', () {
    test('renders template with variable bindings', () async {
      final template = PromptTemplate(
        templateId: 'planner.global_plan',
        templateVersion: '2026.02.18',
        requiredVariables: const <String>['userQuery'],
        content: 'Q={{userQuery}} Device={{deviceModel}}',
      );
      final runtime = PromptTemplateRuntime(
        registry: TemplateRegistry.withSeeded(
          seededTemplates: <String, PromptTemplate>{template.key(): template},
        ),
      );

      final output = await runtime.renderTemplate(
        templateId: 'planner.global_plan',
        defaultVersion: '2026.02.18',
        variables: const <String, dynamic>{
          'userQuery': '深圳天气',
          'deviceModel': 'iPhone 17',
        },
      );

      expect(output.rendered.content, contains('深圳天气'));
      expect(output.rendered.content, contains('iPhone 17'));
      expect(output.missingVariables, isEmpty);
      expect(output.bucket, equals('control'));
    });

    test('selector supports experiment bucket and rollback', () async {
      final templateV1 = PromptTemplate(
        templateId: 'planner.global_plan',
        templateVersion: '2026.02.18',
        content: 'A{{userQuery}}',
      );
      final templateV2 = PromptTemplate(
        templateId: 'planner.global_plan',
        templateVersion: '2026.03.01',
        content: 'B{{userQuery}}',
      );
      final runtime = PromptTemplateRuntime(
        registry: TemplateRegistry.withSeeded(
          seededTemplates: <String, PromptTemplate>{
            templateV1.key(): templateV1,
            templateV2.key(): templateV2,
          },
        ),
      );

      final expOutput = await runtime.renderTemplate(
        templateId: 'planner.global_plan',
        defaultVersion: '2026.02.18',
        variables: const <String, dynamic>{'userQuery': 'Q'},
        selectionContext: const <String, dynamic>{
          'templateExperiments': <String, dynamic>{
            'planner.global_plan': <String, dynamic>{
              'enabled': true,
              'targetVersion': '2026.03.01',
              'bucket': 'exp_a',
            },
          },
        },
      );
      expect(expOutput.rendered.templateVersion, equals('2026.03.01'));
      expect(expOutput.bucket, equals('exp_a'));

      final rollbackOutput = await runtime.renderTemplate(
        templateId: 'planner.global_plan',
        defaultVersion: '2026.02.18',
        variables: const <String, dynamic>{'userQuery': 'Q'},
        selectionContext: const <String, dynamic>{
          'templateExperiments': <String, dynamic>{
            'planner.global_plan': <String, dynamic>{
              'enabled': true,
              'targetVersion': '2026.03.01',
              'bucket': 'exp_a',
              'rollbackEnabled': true,
            },
          },
        },
      );
      expect(rollbackOutput.rendered.templateVersion, equals('2026.02.18'));
      expect(rollbackOutput.bucket, equals('control'));
    });

    test('missing required variables are reported', () async {
      final template = PromptTemplate(
        templateId: 'synthesizer.final_answer',
        templateVersion: '2026.02.18',
        requiredVariables: const <String>['userQuery', 'contextEnvelope'],
        content: 'Q={{userQuery}} C={{contextEnvelope}}',
      );
      final runtime = PromptTemplateRuntime(
        registry: TemplateRegistry.withSeeded(
          seededTemplates: <String, PromptTemplate>{template.key(): template},
        ),
      );

      final output = await runtime.renderTemplate(
        templateId: 'synthesizer.final_answer',
        defaultVersion: '2026.02.18',
        variables: const <String, dynamic>{'userQuery': 'hello'},
      );
      expect(output.missingVariables, contains('contextEnvelope'));
    });
  });
}
