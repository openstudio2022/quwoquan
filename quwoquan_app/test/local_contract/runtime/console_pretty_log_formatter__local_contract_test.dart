import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/observability/console_pretty_log_formatter.dart';

void main() {
  test(
    'pretty formatter redacts nested authorization and decodes JSON text',
    () {
      final rendered = ConsolePrettyLogFormatter.prettyJsonLikeString(
        <String, Object?>{
          'authorization': 'Bearer secret',
          'nested': <Object>['{"authorization":"second","ok":true}'],
        },
      );

      expect(rendered, contains('Bearer ***'));
      expect(rendered, isNot(contains('secret')));
      expect(rendered, contains('"ok": true'));
      expect(ConsolePrettyLogFormatter.prettyJsonLikeString('plain'), 'plain');
      expect(ConsolePrettyLogFormatter.prettyJsonLikeString(null), '');
    },
  );

  test('section renderer handles empty, scalar and nested block values', () {
    expect(
      ConsolePrettyLogFormatter.renderSection(prefix: '> ', title: 'empty'),
      <String>['> empty: <empty>'],
    );
    final lines = ConsolePrettyLogFormatter.renderSection(
      prefix: '> ',
      title: 'payload',
      value: <String, Object?>{
        'emptyMap': <String, Object?>{},
        'emptyList': <Object>[],
        'nested': <Object>[
          <String, Object?>{'message': 'line one\nline two'},
          <Object>[true, 2],
        ],
      },
    );

    expect(lines, contains('>   emptyMap: {}'));
    expect(lines, contains('>   emptyList: []'));
    expect(lines.any((line) => line.contains('message: |')), isTrue);
    expect(lines.any((line) => line.contains('- true')), isTrue);
  });
}
