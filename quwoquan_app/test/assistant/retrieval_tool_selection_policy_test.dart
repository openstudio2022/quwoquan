import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/contracts/search_plan_contract.dart';
import 'package:quwoquan_app/assistant/orchestration/retrieval_tool_selection_policy.dart';
import 'package:quwoquan_app/assistant/tool/runtime/tool_metadata_registry.dart';

void main() {
  group('RetrievalToolSelectionPolicy', () {
    const policy = RetrievalToolSelectionPolicy();
    const availableTools = <String>[
      AssistantToolNames.appSearch,
      AssistantToolNames.search,
      AssistantToolNames.webSearch,
    ];

    test('routes app object plans to app_search', () {
      final selected = policy.select(
        availableToolNames: availableTools,
        searchPlans: const <SearchPlanItem>[
          SearchPlanItem(
            id: 'app_content',
            query: '我昨天发过的动态',
            dimension: SearchPlanDimension.coreObject,
          ),
        ],
      );

      expect(selected, AssistantToolNames.appSearch);
    });

    test('routes pure realtime external plans to web_search', () {
      final selected = policy.select(
        availableToolNames: availableTools,
        searchPlans: const <SearchPlanItem>[
          SearchPlanItem(
            id: 'weather',
            query: '深圳 今天 天气',
            dimension: SearchPlanDimension.latestSignal,
            authorityDomains: <String>['weather.cma.cn'],
            freshnessNeed: FreshnessNeed.realtime,
          ),
        ],
      );

      expect(selected, AssistantToolNames.webSearch);
    });

    test('routes mixed app and external plans to search bridge', () {
      final selected = policy.select(
        availableToolNames: availableTools,
        searchPlans: const <SearchPlanItem>[
          SearchPlanItem(
            id: 'chat',
            query: '我和张三的聊天',
            dimension: SearchPlanDimension.coreObject,
          ),
          SearchPlanItem(
            id: 'web',
            query: '深圳 今日天气',
            dimension: SearchPlanDimension.latestSignal,
            freshnessNeed: FreshnessNeed.realtime,
          ),
        ],
      );

      expect(selected, AssistantToolNames.search);
    });
  });
}
