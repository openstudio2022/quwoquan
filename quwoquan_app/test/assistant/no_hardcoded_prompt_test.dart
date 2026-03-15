import 'dart:io';

import 'package:test/test.dart';

void main() {
  test('runtime and llm provider contain no hardcoded prompt bodies', () {
    final runtimeFile = File(
      'lib/assistant/runtime/assistant_runtime.dart',
    );
    final providerFile = File(
      'lib/assistant/internal_legacy/engine/llm_provider.dart',
    );
    expect(runtimeFile.existsSync(), isTrue);
    expect(providerFile.existsSync(), isTrue);

    final runtimeContent = runtimeFile.readAsStringSync();
    final providerContent = providerFile.readAsStringSync();

    expect(runtimeContent.contains('_seedPromptTemplates'), isFalse);
    expect(runtimeContent.contains('templateId: \'planner.global_plan\''), isFalse);
    expect(providerContent.contains('思考-查询-观察-再决策'), isFalse);
    expect(providerContent.contains('由你决定是否查询'), isFalse);
  });
}

