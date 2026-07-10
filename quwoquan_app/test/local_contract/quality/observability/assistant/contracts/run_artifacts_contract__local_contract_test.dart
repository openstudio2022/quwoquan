import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';

void main() {
  group('parseRunArtifacts', () {
    test('兼容 diagnostics 中既往 bool/string 漂移字段', () {
      final artifacts = parseRunArtifacts(<String, dynamic>{
        'displayMarkdown': '答案',
        'diagnostics': <String, dynamic>{
          'renderFallback': true,
          'renderMode': 'markdown',
        },
      });

      expect(artifacts.displayMarkdown, '答案');
      expect(artifacts.diagnostics.core.renderFallback, 'true');
      expect(artifacts.diagnostics.core.renderMode, 'markdown');
    });
  });
}
