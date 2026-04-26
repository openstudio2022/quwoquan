import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/debug/console_pretty_log_formatter.dart';

void main() {
  group('ConsolePrettyLogFormatter.prettyJsonLikeString', () {
    test('formats maps into indented multi-line json', () {
      final formatted = ConsolePrettyLogFormatter.prettyJsonLikeString(
        <String, dynamic>{
          'dialogueState': <String, dynamic>{
            'suggestedNextStateId': 'S1_城市补全',
            'nextStateCandidates': <String>['S1_城市补全'],
          },
        },
      );

      expect(formatted, contains('\n'));
      expect(formatted, contains('  "dialogueState": {'));
      expect(formatted, contains('    "suggestedNextStateId": "S1_城市补全"'));
    });

    test('formats json strings into indented multi-line json', () {
      const raw = '{"sharedContext":{"cityLabel":"深圳","timezone":"Asia/Shanghai"}}';

      final formatted = ConsolePrettyLogFormatter.prettyJsonLikeString(raw);

      expect(formatted, contains('\n'));
      expect(formatted, contains('  "sharedContext": {'));
      expect(formatted, contains('    "cityLabel": "深圳"'));
    });
  });
}
