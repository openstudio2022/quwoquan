import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/domain/run_artifacts.dart';

void main() {
  group('parseRunArtifacts', () {
    test('只接受 canonical diagnostics 字段类型', () {
      final artifacts = parseRunArtifacts(<String, dynamic>{
        'displayMarkdown': '答案',
        'diagnostics': <String, dynamic>{
          'renderFallback': 'plain_text',
          'renderMode': 'markdown',
        },
      });

      expect(artifacts.displayMarkdown, '答案');
      expect(artifacts.diagnostics.core.renderFallback, 'plain_text');
      expect(artifacts.diagnostics.core.renderMode, 'markdown');
    });

    test('拒绝非 canonical bool/string 漂移而不做读时升级', () {
      expect(
        () => parseRunArtifacts(<String, dynamic>{
          'diagnostics': <String, dynamic>{'renderFallback': true},
        }),
        throwsA(isA<FormatException>()),
      );
    });
  });
}
