import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('tool catalog should define divination domain mapping', () {
    final manifestFile = File(
      'assets/assistant/tools/manifest.json',
    );
    expect(manifestFile.existsSync(), isTrue);

    final manifest = jsonDecode(manifestFile.readAsStringSync());
    expect(manifest, isA<Map>());
    final catalogPath = (manifest as Map)['catalogPath']?.toString() ?? '';
    expect(catalogPath, isNotEmpty);

    final catalogFile = File(catalogPath);
    expect(catalogFile.existsSync(), isTrue);
    final catalog = jsonDecode(catalogFile.readAsStringSync());
    expect(catalog, isA<Map>());

    final tools = ((catalog as Map)['tools'] as List?) ?? const <dynamic>[];
    final toolNames = tools
        .whereType<Map>()
        .map((item) => item['toolName']?.toString() ?? '')
        .where((name) => name.isNotEmpty)
        .toSet();
    expect(toolNames.contains('web_search'), isTrue);

    final domainMatrix =
        (catalog['domainToolMatrix'] as List?) ?? const <dynamic>[];
    final divination = domainMatrix
        .whereType<Map>()
        .firstWhere(
          (item) => item['domainId']?.toString() == 'divination_fortune',
          orElse: () => <String, dynamic>{},
        );
    expect(divination.isNotEmpty, isTrue);
    final allowed =
        (divination['allowedTools'] as List?)?.whereType<String>().toList() ??
        const <String>[];
    expect(allowed.contains('web_search'), isTrue);

    final weather = domainMatrix
        .whereType<Map>()
        .firstWhere(
          (item) => item['domainId']?.toString() == 'weather',
          orElse: () => <String, dynamic>{},
        );
    expect(weather.isNotEmpty, isTrue);
    final weatherAllowed =
        (weather['allowedTools'] as List?)?.whereType<String>().toList() ??
        const <String>[];
    expect(weatherAllowed.contains('local_context'), isTrue);
    expect(weatherAllowed.contains('web_search'), isTrue);
  });
}

