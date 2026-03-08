import 'dart:convert';
import 'dart:io';

import 'package:test/test.dart';

void main() {
  group('Domain catalog contract', () {
    test(
      'routing catalog has at least 15 domains and all domains use skill dialogue',
      () {
        final routingCatalog = File(
          'assets/personal_assistant/prompts/domain_routing/domain_routing_catalog.json',
        );
        expect(routingCatalog.existsSync(), isTrue);
        final routingDecoded =
            jsonDecode(routingCatalog.readAsStringSync()) as Map;
        final domainItems =
            ((routingDecoded['domains'] as List?) ?? const <dynamic>[])
                .whereType<Map>()
                .toList(growable: false);
        final domains = domainItems
            .map((item) => (item['domainId'] as String?)?.trim() ?? '')
            .where((id) => id.isNotEmpty)
            .toSet()
            .toList(growable: false);
        expect(domains.length, greaterThanOrEqualTo(15));
        expect(domains.contains('emotion_companion'), isTrue);
        expect(domains.contains('fortune_astrology'), isTrue);
        expect(domains.contains('fallback_general_search'), isTrue);

        for (final item in domainItems) {
          final domainId = (item['domainId'] as String?)?.trim() ?? '';
          if (domainId.isEmpty) continue;
          final dialoguePath = (item['dialoguePath'] as String?)?.trim() ?? '';
          expect(
            dialoguePath.isNotEmpty,
            isTrue,
            reason: '$domainId missing dialoguePath',
          );
          expect(
            dialoguePath.startsWith('assets/personal_assistant/skills/'),
            isTrue,
            reason: '$domainId must use skills dialogue path',
          );
          final suffix = '/dialogue';
          expect(
            dialoguePath.endsWith(suffix),
            isTrue,
            reason: '$domainId dialoguePath must end with /dialogue',
          );
          final skillRoot = dialoguePath.substring(
            0,
            dialoguePath.length - suffix.length,
          );
          final skillFile = File('$skillRoot/SKILL.md');
          expect(
            skillFile.existsSync(),
            isTrue,
            reason: 'missing ${skillFile.path}',
          );
        }
      },
    );

    test('all domain prompt templates are removed from manifest', () {
      final manifest = File('assets/personal_assistant/prompts/manifest.json');
      expect(manifest.existsSync(), isTrue);
      final decoded = jsonDecode(manifest.readAsStringSync()) as Map;
      final templates =
          (decoded['templates'] as List?)?.whereType<Map>().toList() ??
          const <Map>[];
      final allMetaPaths = templates
          .map((item) => (item['metaPath'] as String?)?.trim() ?? '')
          .where((path) => path.isNotEmpty)
          .toList(growable: false);
      expect(
        allMetaPaths.any(
          (path) =>
              path.startsWith('assets/personal_assistant/prompts/domains/'),
        ),
        isFalse,
        reason: 'manifest should not keep legacy domain prompt templates',
      );
    });

    test('routing catalog contains dynamic routing policies', () {
      final routingCatalog = File(
        'assets/personal_assistant/prompts/domain_routing/domain_routing_catalog.json',
      );
      expect(routingCatalog.existsSync(), isTrue);
      final decoded = jsonDecode(routingCatalog.readAsStringSync()) as Map;
      expect((decoded['version'] as String?)?.isNotEmpty, isTrue);
      expect(decoded['fallbackDomainId'], equals('fallback_general_search'));
      final pageTypeFallbacks =
          (decoded['pageTypeFallbacks'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      expect(pageTypeFallbacks['chat'], equals('emotion_companion'));
      final domains =
          (decoded['domains'] as List?)?.whereType<Map>().toList() ??
          const <Map>[];
      expect(domains, isNotEmpty);
      for (final item in domains) {
        expect((item['domainId'] as String?)?.isNotEmpty, isTrue);
        expect((item['dialoguePath'] as String?)?.isNotEmpty, isTrue);
        expect(item['priority'], isNotNull);
        expect(item['enabled'], isNotNull);
        expect(
          (item['description'] as String?)?.isNotEmpty,
          isTrue,
          reason: '${item['domainId']} must have a description for LLM routing',
        );
        expect(
          (item['mode'] as String?)?.isNotEmpty,
          isTrue,
          reason: '${item['domainId']} must declare a mode (qa/task/hybrid)',
        );
      }
    });

    test('legacy prompt domain directory is removed', () {
      final legacyDomains = Directory(
        'assets/personal_assistant/prompts/domains',
      );
      expect(legacyDomains.existsSync(), isFalse);
    });
  });
}
