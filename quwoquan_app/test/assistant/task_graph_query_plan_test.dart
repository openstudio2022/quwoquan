import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/contracts/search_plan_contract.dart';
import 'package:quwoquan_app/assistant/contracts/task_graph_contract.dart';
import 'package:quwoquan_app/assistant/orchestration/task_graph_query_plan.dart';

void main() {
  group('task graph query plan', () {
    test('extracts query tasks from retrieval task arguments', () {
      const graph = TaskGraph(
        tasks: <TaskNode>[
          TaskNode(
            taskId: 'task_weather',
            intentId: 'intent_weather',
            toolName: 'web_search',
            toolArgs: TaskToolArgs(<String, Object?>{
              'searchPlans': <Map<String, Object?>>[
                <String, Object?>{
                  'id': 'task_weather',
                  'query': '深圳今天天气',
                },
              ],
            }),
          ),
        ],
      );

      final searchPlans = searchPlansFromTaskGraph(graph);

      expect(searchPlans, hasLength(1));
      expect(searchPlans.single.query, '深圳今天天气');
    });

    test('writes query tasks back into first retrieval task', () {
      const graph = TaskGraph(
        tasks: <TaskNode>[
          TaskNode(
            taskId: 'task_weather',
            intentId: 'intent_weather',
            toolName: 'web_search',
            toolArgs: TaskToolArgs(<String, Object?>{'query': '天气'}),
          ),
        ],
      );

      final updated = taskGraphWithSearchPlans(
        taskGraph: graph,
        searchPlans: const <SearchPlanItem>[
          SearchPlanItem(id: 'task_weather', query: '深圳今天天气'),
        ],
        fallbackQuery: '天气',
      );

      expect(updated.tasks, hasLength(1));
      expect(updated.tasks.single.toolArgs.fields['query'], '深圳今天天气');
      expect(
        SearchPlanItem.normalizeList(updated.tasks.single.toolArgs.fields['searchPlans'])
            .single
            .query,
        '深圳今天天气',
      );
    });
  });
}
