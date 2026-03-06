import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('local_context contract should be structured and explicit', () {
    final manifestFile = File('assets/personal_assistant/tools/manifest.json');
    expect(manifestFile.existsSync(), isTrue);
    final manifest = jsonDecode(manifestFile.readAsStringSync()) as Map;
    final catalogPath = (manifest['catalogPath'] ?? '').toString();
    expect(catalogPath.isNotEmpty, isTrue);

    final catalogFile = File(catalogPath);
    expect(catalogFile.existsSync(), isTrue);
    final catalog = jsonDecode(catalogFile.readAsStringSync()) as Map;
    final tools = (catalog['tools'] as List?)?.whereType<Map>().toList() ??
        const <Map>[];
    final localContext = tools.firstWhere(
      (item) => (item['toolName'] ?? '').toString() == 'local_context',
      orElse: () => <String, dynamic>{},
    );
    expect(localContext.isNotEmpty, isTrue);

    expect((localContext['purpose'] ?? '').toString(), contains('地理位置'));
    expect((localContext['purpose'] ?? '').toString(), contains('不包含相册'));

    final openAiFunction =
        (localContext['openAiFunction'] as Map?)?.cast<String, dynamic>() ??
            const <String, dynamic>{};
    final parameters =
        (openAiFunction['parameters'] as Map?)?.cast<String, dynamic>() ??
            const <String, dynamic>{};
    final properties =
        (parameters['properties'] as Map?)?.cast<String, dynamic>() ??
            const <String, dynamic>{};
    expect(properties.containsKey('requestedFields'), isTrue);
    expect(properties.containsKey('needPreciseLocation'), isTrue);
    expect(properties.containsKey('maxAgeSeconds'), isTrue);
  });
}
