import 'package:quwoquan_app/personal_assistant/engine/default_processing/problem_framer.dart';
import 'package:quwoquan_app/personal_assistant/tools/tool_schema.dart';

class BaselineRetrievalPlan {
  const BaselineRetrievalPlan({
    required this.reasoning,
    required this.calls,
    this.queryTasks = const <Map<String, dynamic>>[],
    this.blockingDimensions = const <String>[],
  });

  final String reasoning;
  final List<AssistantToolCall> calls;
  final List<Map<String, dynamic>> queryTasks;
  final List<String> blockingDimensions;
}

class DefaultRetrievalPlanner {
  const DefaultRetrievalPlanner();

  BaselineRetrievalPlan? plan({
    required ProblemFrame frame,
    required List<String> availableTools,
  }) {
    if (frame.normalizedQuery.isEmpty) return null;
    if (!availableTools.contains('web_search')) return null;

    if (frame.queryIntent == 'weather_now' ||
        frame.primaryDomainId == 'weather') {
      final city = frame.city;
      final reasoning = city.isNotEmpty
          ? '你现在更想知道$city能不能放心出门，我先替你查实时天气和出门直接相关的提醒。'
          : '你更需要的是能直接拿来判断的最新信息，我先替你查实时天气和出门提醒。';
      final queryTasks = <Map<String, dynamic>>[
        <String, dynamic>{
          'id': 'weather_now',
          'label': '实时天气',
          'dimension': '实时天气',
          'query': city.isNotEmpty
              ? '$city 天气 实时 温度 降雨 风力 体感'
              : '${frame.normalizedQuery} 实时 温度 降雨 风力',
        },
      ];
      return BaselineRetrievalPlan(
        reasoning: reasoning,
        queryTasks: queryTasks,
        blockingDimensions: const <String>['实时天气'],
        calls: <AssistantToolCall>[
          AssistantToolCall(
            name: 'web_search',
            arguments: <String, dynamic>{
              'query': (queryTasks.first['query'] as String?)?.trim() ?? '',
              'queryTasks': queryTasks,
              'freshnessHoursMax': 6,
            },
          ),
        ],
      );
    }

    if (frame.queryIntent == 'travelAlternativeOptions') {
      final focus = frame.city.isNotEmpty ? frame.city : '九寨沟方向';
      final queryTasks = <Map<String, dynamic>>[
        <String, dynamic>{
          'id': 'travel_alternative_candidates',
          'label': '候选路线',
          'dimension': '候选路线',
          'query': '$focus 备选 方案 路线 川主寺 松潘 黄龙 若尔盖',
        },
        <String, dynamic>{
          'id': 'travel_alternative_fit',
          'label': '适用条件',
          'dimension': '适用条件',
          'query': '$focus 适合 什么人 行程 节奏 海拔 路况',
        },
        <String, dynamic>{
          'id': 'travel_alternative_tradeoff',
          'label': '关键取舍',
          'dimension': '关键取舍',
          'query': '$focus 黄龙 川主寺 松潘 若尔盖 区别 取舍',
        },
      ];
      return BaselineRetrievalPlan(
        reasoning: '我把九寨沟方向拆成候选路线、适用条件和关键取舍三块并行核对，这样更容易直接收敛成几个可选方案。',
        queryTasks: queryTasks,
        blockingDimensions: const <String>['候选路线', '适用条件'],
        calls: <AssistantToolCall>[
          AssistantToolCall(
            name: 'web_search',
            arguments: <String, dynamic>{
              'query': (queryTasks.first['query'] as String?)?.trim() ?? '',
              'queryTasks': queryTasks,
              'freshnessHoursMax': 72,
            },
          ),
        ],
      );
    }

    if (frame.queryIntent == 'wildlifeBestTime') {
      final subject = frame.normalizedQuery;
      final queryTasks = <Map<String, dynamic>>[
        <String, dynamic>{
          'id': 'wildlife_season',
          'label': '季节窗口',
          'dimension': '季节窗口',
          'query': '$subject 季节 5月 6月 7月 8月 9月',
        },
        <String, dynamic>{
          'id': 'wildlife_daytime',
          'label': '日内时段',
          'dimension': '日内时段',
          'query': '$subject 早上 上午 傍晚 下午 活动时间',
        },
        <String, dynamic>{
          'id': 'wildlife_weather',
          'label': '天气条件',
          'dimension': '天气条件',
          'query': '$subject 晴天 多云 风小 雨后 天气 条件',
        },
      ];
      return BaselineRetrievalPlan(
        reasoning: '我把观赏时间拆成季节窗口、一天中的活跃时段和天气条件三块并行核对，这样结论会更直接也更稳。',
        queryTasks: queryTasks,
        blockingDimensions: const <String>['季节窗口', '日内时段', '天气条件'],
        calls: <AssistantToolCall>[
          AssistantToolCall(
            name: 'web_search',
            arguments: <String, dynamic>{
              'query': (queryTasks.first['query'] as String?)?.trim() ?? '',
              'queryTasks': queryTasks,
              'freshnessHoursMax': 720,
            },
          ),
        ],
      );
    }

    if (frame.queryIntent == 'stayPlanning' ||
        frame.problemClass == 'complex_reasoning') {
      final city = frame.city;
      final areaQuery = city.isNotEmpty
          ? '$city 住宿 区域 交通 方便'
          : '${frame.normalizedQuery} 区域 交通 方便';
      final priceQuery = city.isNotEmpty
          ? '$city 酒店 价格 档位 性价比'
          : '${frame.normalizedQuery} 价格 性价比';
      final reviewQuery = city.isNotEmpty
          ? '$city 住宿 评价 避坑'
          : '${frame.normalizedQuery} 评价 避坑';
      final queryTasks = <Map<String, dynamic>>[
        <String, dynamic>{
          'id': 'stay_location',
          'label': '位置与通勤',
          'dimension': '位置与通勤',
          'query': areaQuery,
        },
        <String, dynamic>{
          'id': 'stay_price',
          'label': '价格与档位',
          'dimension': '价格与档位',
          'query': priceQuery,
        },
        <String, dynamic>{
          'id': 'stay_review',
          'label': '近期评价',
          'dimension': '近期评价',
          'query': reviewQuery,
        },
      ];
      return BaselineRetrievalPlan(
        reasoning: '这个问题不能把位置、价格和评价一次混在一起查，我先拆成几路分别核对，这样更容易收敛。',
        queryTasks: queryTasks,
        blockingDimensions: const <String>['位置与通勤', '价格与档位'],
        calls: <AssistantToolCall>[
          AssistantToolCall(
            name: 'web_search',
            arguments: <String, dynamic>{
              'query': areaQuery,
              'queryTasks': queryTasks,
              'freshnessHoursMax': 72,
            },
          ),
        ],
      );
    }

    return BaselineRetrievalPlan(
      reasoning: '我先替你查最影响结论的资料，尽量少带回无关信息。',
      calls: <AssistantToolCall>[
        AssistantToolCall(
          name: 'web_search',
          arguments: <String, dynamic>{'query': frame.normalizedQuery},
        ),
      ],
    );
  }
}
