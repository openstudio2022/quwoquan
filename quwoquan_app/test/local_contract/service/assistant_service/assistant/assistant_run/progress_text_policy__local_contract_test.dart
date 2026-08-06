import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/application/public/progress_text_policy.dart';

void main() {
  test(
    'progress policy normalizes configured lists without transport code',
    () {
      final policy = ProgressTextPolicy.fromJson(<String, dynamic>{
        'jsonEnvelopeSignatures': <Object?>['  "custom"  ', '', 7],
        'progressLexicon': <String, Object?>{
          'zh': <Object?>['  正在处理  ', ''],
          'en': <Object?>['  working  ', 7],
        },
        'degradedPrefixes': <Object?>['  unavailable:  ', ''],
        'degradedSubstrings': <Object?>['  timeout  ', ''],
      });

      expect(policy.jsonEnvelopeSignatures, <String>['"custom"']);
      expect(policy.progressLexicon, <String>['正在处理', 'working']);
      expect(policy.degradedPrefixes, <String>['unavailable:']);
      expect(policy.degradedSubstrings, <String>['timeout']);
    },
  );

  test('progress policy keeps canonical defaults for absent fields', () {
    final policy = ProgressTextPolicy.fromJson(const <String, dynamic>{});

    expect(
      policy.jsonEnvelopeSignatures,
      ProgressTextPolicy.defaults.jsonEnvelopeSignatures,
    );
    expect(policy.progressLexicon, ProgressTextPolicy.defaults.progressLexicon);
    expect(
      policy.degradedPrefixes,
      ProgressTextPolicy.defaults.degradedPrefixes,
    );
    expect(
      policy.degradedSubstrings,
      ProgressTextPolicy.defaults.degradedSubstrings,
    );
  });
}
