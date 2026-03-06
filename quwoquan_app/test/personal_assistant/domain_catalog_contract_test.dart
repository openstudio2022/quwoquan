import 'dart:convert';
import 'dart:io';

import 'package:test/test.dart';

void main() {
  group('Domain catalog contract', () {
    test(
      'routing catalog keeps 19 domains and all domains use skill dialogue',
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
        expect(domains.length, equals(19));
        expect(domains.contains('social_companion_chat'), isTrue);
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
          for (final rel in const <String>[
            'dialogue/state_machine.md',
            'dialogue/state_prompts.md',
            'dialogue/state_transition_contract.json',
          ]) {
            final target = File('$skillRoot/$rel');
            expect(
              target.existsSync(),
              isTrue,
              reason: 'missing ${target.path}',
            );
          }
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
      expect(pageTypeFallbacks['chat'], equals('social_companion_chat'));
      final domains =
          (decoded['domains'] as List?)?.whereType<Map>().toList() ??
          const <Map>[];
      expect(domains, isNotEmpty);
      for (final item in domains) {
        expect((item['domainId'] as String?)?.isNotEmpty, isTrue);
        expect((item['dialoguePath'] as String?)?.isNotEmpty, isTrue);
        expect(item['priority'], isNotNull);
        expect(item['enabled'], isNotNull);
      }
      final weather = domains.firstWhere(
        (item) => (item['domainId'] as String?)?.trim() == 'weather',
        orElse: () => const <String, dynamic>{},
      );
      expect(weather.isNotEmpty, isTrue);
      final weatherKeywords =
          (weather['intentKeywords'] as List?)
              ?.whereType<String>()
              .map((item) => item.trim().toLowerCase())
              .where((item) => item.isNotEmpty)
              .toList(growable: false) ??
          const <String>[];
      expect(weatherKeywords.contains('tianqi'), isTrue);
      expect(weatherKeywords.contains('weather'), isTrue);
    });

    test('legacy prompt domain directory is removed', () {
      final legacyDomains = Directory(
        'assets/personal_assistant/prompts/domains',
      );
      expect(legacyDomains.existsSync(), isFalse);
    });
  });
}
