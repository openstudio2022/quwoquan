import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test(
    'content-service media upload complete create bind contract stays green',
    () async {
      final result = await Process.run(
        'go',
        <String>[
          'test',
          '.',
          '-run',
          r'^TestBindMediaAssetsToPostContract$',
          '-count=1',
        ],
        workingDirectory: '../quwoquan_service/services/content-service/tests',
      );

      expect(result.exitCode, 0, reason: '${result.stdout}\n${result.stderr}');
    },
  );
}
