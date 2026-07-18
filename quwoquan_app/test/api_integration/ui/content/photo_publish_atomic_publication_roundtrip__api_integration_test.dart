import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test(
    'content-service media upload and atomic publication contract stays green',
    () async {
      final result = await Process.run(
        'go',
        <String>[
          'test',
          './services/content-service/tests/api_integration',
          '-run',
          r'^TestSubmitPostPublicationWithMediaContract$',
          '-count=1',
        ],
        workingDirectory: '../quwoquan_service',
      );

      expect(result.exitCode, 0, reason: '${result.stdout}\n${result.stderr}');
    },
  );
}
