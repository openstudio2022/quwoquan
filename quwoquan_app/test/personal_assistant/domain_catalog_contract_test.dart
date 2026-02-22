import 'dart:convert';
import 'dart:io';

import 'package:test/test.dart';

void main() {
  group('Domain catalog contract', () {
    test('routing catalog domains match template assets', () {
      final routingCatalog = File(
        'assets/personal_assistant/prompts/domain_routing/domain_routing_catalog.json',
      );
      expect(routingCatalog.existsSync(), isTrue);
      final routingDecoded = jsonDecode(routingCatalog.readAsStringSync()) as Map;
      final domains = ((routingDecoded['domains'] as List?) ?? const <dynamic>[])
          .whereType<Map>()
          .map((item) => (item['domainId'] as String?)?.trim() ?? '')
          .where((id) => id.isNotEmpty)
          .toSet()
          .toList(growable: false);
      expect(domains.length, equals(19));
      expect(domains.contains('social_companion_chat'), isTrue);
      expect(domains.contains('fallback_general_search'), isTrue);

      for (final domainId in domains) {
        final domainDir = Directory(
          'assets/personal_assistant/prompts/domains/$domainId',
        );
        expect(domainDir.existsSync(), isTrue, reason: 'missing $domainId dir');
        for (final stage in const <String>['plan', 'answer']) {
          final md = File('${
              domainDir.path}/domain.$domainId.$stage.md');
          final meta = File('${
              domainDir.path}/domain.$domainId.$stage.meta.json');
          expect(md.existsSync(), isTrue, reason: 'missing ${md.path}');
          expect(meta.existsSync(), isTrue, reason: 'missing ${meta.path}');
          final content = md.readAsStringSync();
          expect(content.contains('## 任务背景'), isTrue);
          expect(content.contains('## 任务目标'), isTrue);
          expect(content.contains('## 约束'), isTrue);
          expect(content.contains('## 执行要求'), isTrue);
          expect(content.contains('=== CONTEXT_DATA_START ==='), isTrue);
          expect(content.contains('=== CONTEXT_DATA_END ==='), isTrue);

          final metaDecoded = jsonDecode(meta.readAsStringSync()) as Map;
          expect(metaDecoded['templateId'], equals('domain.$domainId.$stage'));
          expect(metaDecoded['version'], equals('2026.02.18'));
          expect(metaDecoded['domainId'], equals(domainId));
          expect((metaDecoded['requiredVariables'] as List?)?.isNotEmpty, isTrue);
          expect(
            metaDecoded['outputContract'],
            equals(
              stage == 'plan'
                  ? 'domain_plan_v2026_02_18'
                  : 'domain_answer_v2026_02_18',
            ),
          );
        }
      }
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
      final domains = (decoded['domains'] as List?)?.whereType<Map>().toList() ??
          const <Map>[];
      expect(domains, isNotEmpty);
      for (final item in domains) {
        expect((item['domainId'] as String?)?.isNotEmpty, isTrue);
        expect((item['dialoguePath'] as String?)?.isNotEmpty, isTrue);
        expect(item['priority'], isNotNull);
        expect(item['enabled'], isNotNull);
      }
    });

    test('fallback template enforces online/offline boundary rule', () {
      final fallbackMeta = File(
        'assets/personal_assistant/prompts/domains/fallback_general_search/domain.fallback_general_search.answer.meta.json',
      );
      expect(fallbackMeta.existsSync(), isTrue);
      final decoded = jsonDecode(fallbackMeta.readAsStringSync()) as Map;
      final rules =
          (decoded['selfCheckRules'] as List?)?.whereType<String>().toList() ??
          const <String>[];
      expect(rules.contains('online_offline_boundary_defined'), isTrue);
      expect(rules.contains('offline_boundary_explicit'), isTrue);
    });
  });
}
