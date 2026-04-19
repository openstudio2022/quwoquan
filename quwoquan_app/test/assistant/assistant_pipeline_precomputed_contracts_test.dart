import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_precomputed_contracts.dart';

void main() {
  test('recoverPrecomputedBootstrap parses core fields', () {
    final bootstrap = recoverPrecomputedBootstrap(
      <String, dynamic>{
        'precomputedBootstrap': <String, dynamic>{
          'sessionId': ' session-42 ',
          'latestUserQuery': ' 你好 ',
          'historySummary': ' 已有历史 ',
          'recalledTexts': <String>[' 甲 ', '', '乙'],
          'previousAnswerSummary': ' 上次回答 ',
          'forceRefreshCatalog': true,
          'domainCatalog': <String>[' content ', ' chat '],
          'domainCatalogVersion': ' v1 ',
          'fullSkillCatalog': 'full',
          'skillCatalog': 'skill',
        },
      },
    );

    expect(bootstrap, isNotNull);
    expect(bootstrap!.sessionId, 'session-42');
    expect(bootstrap.latestUserQuery, '你好');
    expect(bootstrap.historySummary, ' 已有历史 ');
    expect(bootstrap.recalledTexts, ['甲', '乙']);
    expect(bootstrap.previousAnswerSummary, '上次回答');
    expect(bootstrap.forceRefreshCatalog, isTrue);
    expect(bootstrap.domainCatalog, ['content', 'chat']);
    expect(bootstrap.domainCatalogVersion, 'v1');
    expect(bootstrap.fullSkillCatalog, 'full');
    expect(bootstrap.skillCatalog, 'skill');
  });

  test('recoverPrecomputedUnderstand parses mode decision', () {
    final understand = recoverPrecomputedUnderstand(
      <String, dynamic>{
        'precomputedUnderstand': <String, dynamic>{
          'domainId': 'content',
          'modeDecision': <String, dynamic>{
            'mode': 'multi_agent',
            'reason': 'model_requested_multi_agent',
            'subagentCount': 3,
            'budgetMultiplier': 0.8,
          },
        },
      },
    );

    expect(understand, isNotNull);
    expect(understand!.domainId, 'content');
    expect(understand.modeDecision.mode.name, 'multiAgent');
    expect(understand.modeDecision.subagentCount, 3);
    expect(understand.modeDecision.budgetMultiplier, 0.8);
  });
}
