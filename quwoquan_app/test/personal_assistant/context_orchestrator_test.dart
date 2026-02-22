import 'package:quwoquan_app/personal_assistant/engine/context_orchestrator.dart';
import 'package:test/test.dart';

void main() {
  group('PersonalAssistantContextOrchestrator', () {
    const orchestrator = PersonalAssistantContextOrchestrator();

    test('blocks domain when realtime query has no location', () {
      final result = orchestrator.assemble(
        query: '深圳天气最近怎么样',
        historySummary: '',
        recalledTexts: const <String>[],
        deviceProfile: 'mobile',
        deviceModel: '',
        deviceOs: '',
        gpsLocation: const <String, dynamic>{},
        contextScopeHint: const <String, dynamic>{},
      );

      expect(result.canEnterDomain, isFalse);
      expect(result.fillTasks, isNotEmpty);
      expect(result.fillTasks.first.targetSlot, equals('gps_or_city_location'));
    });

    test('allows domain when coarse city location exists', () {
      final result = orchestrator.assemble(
        query: '深圳天气最近怎么样',
        historySummary: '',
        recalledTexts: const <String>[],
        deviceProfile: 'mobile',
        deviceModel: 'iphone',
        deviceOs: 'ios',
        gpsLocation: const <String, dynamic>{'city': '深圳'},
        contextScopeHint: const <String, dynamic>{},
      );

      expect(result.canEnterDomain, isTrue);
      expect(result.contextEnvelope['missingSlots'], isEmpty);
    });

    test('returns gap fill when realtime answer lacks tool evidence', () {
      final assembled = orchestrator.assemble(
        query: '杭州今天天气',
        historySummary: '',
        recalledTexts: const <String>[],
        deviceProfile: 'mobile',
        deviceModel: 'iphone',
        deviceOs: 'ios',
        gpsLocation: const <String, dynamic>{'city': '杭州'},
        contextScopeHint: const <String, dynamic>{},
      );
      final readiness = orchestrator.checkSynthesisReadiness(
        query: '杭州今天天气',
        finalText: '这是一个通用回答',
        hasToolResult: false,
        contextAssembly: assembled,
      );

      expect(readiness.ready, isFalse);
      expect(readiness.gapFillTask, isNotNull);
      expect(readiness.gapFillTask!.fillType, equals('gap_fill'));
    });
  });
}
