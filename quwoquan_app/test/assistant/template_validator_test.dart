import 'package:quwoquan_app/assistant/template_runtime/assistant_template_runtime.dart';
import 'package:test/test.dart';

void main() {
  group('TemplateValidator', () {
    const validator = TemplateValidator();

    test('accepts valid template with required sections and boundaries', () {
      const content = '''
## 任务背景
背景
## 任务目标
目标
## 约束
约束
## 执行要求
要求
## 输出格式
格式
## 反思与自检
检查
=== CONTEXT_DATA_START ===
{{userQuery}}
=== CONTEXT_DATA_END ===
''';
      final result = validator.validate(
        templateId: 'domain.weather.plan',
        content: content,
      );
      expect(result.isValid, isTrue);
    });

    test('rejects template missing section', () {
      const content = '''
## 任务背景
背景
=== CONTEXT_DATA_START ===
{{userQuery}}
=== CONTEXT_DATA_END ===
''';
      final result = validator.validate(
        templateId: 'domain.weather.plan',
        content: content,
      );
      expect(result.isValid, isFalse);
      expect(result.errors.join(','), contains('missing section'));
    });
  });
}
