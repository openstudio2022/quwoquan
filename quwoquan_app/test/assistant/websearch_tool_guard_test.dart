import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/assistant/tool/impl/web/websearch_tool.dart';
import 'package:quwoquan_app/assistant/tool/runtime/search_cache.dart';
import 'package:quwoquan_app/assistant/tool/schema/tool_schema.dart';

void main() {
  test('已配置代理时优先使用可配置 provider 而不是直接回退 duckduckgo', () async {
    late String capturedQuery;
    final tool = WebSearchTool(
      openclawBaseUrl: 'http://mock.openclaw',
      enableInteractionLogging: false,
      resolveRuntimeConfigFromDisk: false,
      textLoader: _testTextLoader,
      httpClient: MockClient((request) async {
        capturedQuery = _extractProxyQuery(
          jsonDecode(request.body) as Map<String, dynamic>,
        );
        return http.Response(
          jsonEncode(<String, dynamic>{
            'message': '代理检索命中',
            'references': <Map<String, dynamic>>[
              <String, dynamic>{
                'title': '深圳天气',
                'url': 'https://example.com/weather',
                'snippet': '深圳天气晴朗。',
              },
            ],
          }),
          200,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );

    final result = await tool.execute(
      AssistantToolArguments.fromJson(<String, dynamic>{'query': '深圳天气'}),
    );

    expect(result.success, isTrue);
    expect(
      result.data?['provider'],
      AssistantSearchProvider.openclawProxy.name,
    );
    expect(capturedQuery, contains('深圳天气'));
  });

  test('长句 contextConstraints 不会被直接拼进检索 query 造成噪声', () async {
    late String capturedQuery;
    final tool = WebSearchTool(
      openclawBaseUrl: 'http://mock.openclaw',
      enableInteractionLogging: false,
      resolveRuntimeConfigFromDisk: false,
      textLoader: _testTextLoader,
      httpClient: MockClient((request) async {
        capturedQuery = _extractProxyQuery(
          jsonDecode(request.body) as Map<String, dynamic>,
        );
        return http.Response(
          jsonEncode(<String, dynamic>{
            'message': '已命中天气线索',
            'references': <Map<String, dynamic>>[
              <String, dynamic>{
                'title': '深圳天气',
                'url': 'https://weather.example.com/shenzhen',
                'snippet': '深圳今日多云，体感较温和。',
              },
            ],
          }),
          200,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );

    final result = await tool.execute(
      AssistantToolArguments.fromJson(<String, dynamic>{
        'query': '深圳今天天气怎么样',
        'domainId': 'weather',
        'referenceNowIso': '2026-04-09T10:30:00.000',
        'timezone': 'Asia/Shanghai',
      }),
    );

    expect(result.success, isTrue);
    expect(capturedQuery, contains('深圳'));
    expect(capturedQuery, isNot(contains('上下文限定')));
    expect(capturedQuery, isNot(contains('必须覆盖温度湿度风速和体感温度')));
    expect(capturedQuery, isNot(contains('优先返回实时天气关键指标')));
  });

  test('weather 域 negativeKeywords 会过滤长周期预报结果', () async {
    final tool = WebSearchTool(
      openclawBaseUrl: 'http://mock.openclaw',
      enableInteractionLogging: false,
      resolveRuntimeConfigFromDisk: false,
      textLoader: _testTextLoader,
      httpClient: MockClient((request) async {
        return http.Response(
          jsonEncode(<String, dynamic>{
            'message': '已命中天气候选',
            'references': <Map<String, dynamic>>[
              <String, dynamic>{
                'title': '深圳40天天气预报',
                'url': 'https://www.weather.com.cn/weather40d/101280601.shtml',
                'snippet': '未来40天天气趋势。',
              },
              <String, dynamic>{
                'title': '深圳天气预报',
                'url': 'https://www.weather.com.cn/weather/101280601.shtml',
                'snippet': '2026-04-09 深圳多云，气温28℃。',
              },
            ],
          }),
          200,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );

    final result = await tool.execute(
      AssistantToolArguments.fromJson(<String, dynamic>{
        'query': '深圳今天天气怎么样',
        'domainId': 'weather',
        'referenceNowIso': '2026-04-09T10:30:00.000',
        'timezone': 'Asia/Shanghai',
      }),
    );

    expect(result.success, isTrue);
    final refs =
        (result.data?['references'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
    expect(
      refs.any(
        (item) =>
            (item['url'] as String?)?.contains('weather40d/101280601.shtml') ==
            true,
      ),
      isFalse,
    );
    expect(
      refs.any(
        (item) =>
            (item['url'] as String?)?.contains('weather/101280601.shtml') ==
            true,
      ),
      isTrue,
    );
  });

  test(
    '冲突日期 token 会被 deterministic temporal guard 清洗并补入 canonical 日期锚点',
    () async {
      late String capturedQuery;
      final tool = WebSearchTool(
        openclawBaseUrl: 'http://mock.openclaw',
        enableInteractionLogging: false,
        resolveRuntimeConfigFromDisk: false,
        textLoader: _testTextLoader,
        httpClient: MockClient((request) async {
          capturedQuery = _extractProxyQuery(
            jsonDecode(request.body) as Map<String, dynamic>,
          );
          return http.Response(
            jsonEncode(<String, dynamic>{
              'message': '已返回网页候选',
              'references': <Map<String, dynamic>>[
                <String, dynamic>{
                  'title': '午间快讯',
                  'url': 'https://news.example.com/market',
                  'snippet': '盘中成交活跃，但页面没有明确发布时间。',
                },
              ],
            }),
            200,
            headers: <String, String>{'content-type': 'application/json'},
          );
        }),
      );

      final result = await tool.execute(
        AssistantToolArguments.fromJson(<String, dynamic>{
          'query': '今天A股为什么大涨 2024年10月28日',
          'referenceNowIso': '2026-04-09T10:30:00+08:00',
          'timezone': 'Asia/Shanghai',
        }),
      );

      expect(result.success, isTrue);
      expect(capturedQuery, contains('2026-04-09'));
      expect(capturedQuery, isNot(contains('2024年10月28日')));
      final temporalGuard = (result.data?['temporalGuard'] as Map?)
          ?.cast<String, dynamic>();
      expect(temporalGuard, isNotNull);
      expect(temporalGuard!['applied'], isTrue);
      expect(
        (temporalGuard['conflictingDateTokens'] as List?) ?? const <dynamic>[],
        contains('2024年10月28日'),
      );
      expect(result.data?['freshnessKnown'], isFalse);
      expect(result.data?['freshnessSatisfied'], isFalse);
      expect(result.data?['retrievalInsufficient'], isTrue);
      final timeConstraint = (result.data?['timeConstraint'] as Map?)
          ?.cast<String, dynamic>();
      expect(timeConstraint, isNotNull);
      expect(timeConstraint!['scope'], equals('today'));
      expect(timeConstraint['temporalMode'], equals('realtime'));
    },
  );

  test('historical anchor 会命中目标时间窗而不是走 now-based freshness', () async {
    late String capturedQuery;
    final tool = WebSearchTool(
      openclawBaseUrl: 'http://mock.openclaw',
      enableInteractionLogging: false,
      resolveRuntimeConfigFromDisk: false,
      textLoader: _testTextLoader,
      httpClient: MockClient((request) async {
        capturedQuery = _extractProxyQuery(
          jsonDecode(request.body) as Map<String, dynamic>,
        );
        return http.Response(
          jsonEncode(<String, dynamic>{
            'message': '已命中候选线索',
            'references': <Map<String, dynamic>>[
              <String, dynamic>{
                'title': 'A股盘后解读',
                'url': 'https://news.example.com/2026/04/08/market-recap',
                'snippet': '2026-04-07 A股大涨，主要由风险偏好修复和权重板块共振驱动。',
              },
            ],
          }),
          200,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );

    final result = await tool.execute(
      AssistantToolArguments.fromJson(<String, dynamic>{
        'query': 'A股为什么大涨 2024年10月',
        'timeScope': 'year_month_day',
        'timePoint': '2026-04-07',
        'referenceNowIso': '2026-04-08T10:30:00.000',
        'timezone': 'Asia/Shanghai',
      }),
    );

    expect(result.success, isTrue);
    expect(capturedQuery, contains('2026-04-07'));
    expect(capturedQuery, isNot(contains('2024年10月')));
    expect(result.data?['freshnessKnown'], isTrue);
    expect(result.data?['freshnessSatisfied'], isTrue);
    final timeConstraint = (result.data?['timeConstraint'] as Map?)
        ?.cast<String, dynamic>();
    expect(timeConstraint, isNotNull);
    expect(timeConstraint!['temporalMode'], equals('historical'));
  });

  test('cache key 会区分 canonical 时间参数，cache hit 保留原始 timeConstraint', () async {
    var requestCount = 0;
    final tool = WebSearchTool(
      openclawBaseUrl: 'http://mock.openclaw',
      enableInteractionLogging: false,
      resolveRuntimeConfigFromDisk: false,
      textLoader: _testTextLoader,
      searchCache: SearchResultCache(),
      httpClient: MockClient((request) async {
        requestCount += 1;
        return http.Response(
          jsonEncode(<String, dynamic>{
            'message': '已命中候选线索',
            'references': <Map<String, dynamic>>[
              <String, dynamic>{
                'title': 'A股盘后解读',
                'url': 'https://news.example.com/analysis/market-recap',
                'snippet': '2026-04-07 A股大涨，主要由风险偏好修复驱动。',
              },
            ],
          }),
          200,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );

    final first = await tool.execute(
      AssistantToolArguments.fromJson(<String, dynamic>{
        'query': 'A股为什么大涨',
        'timeScope': 'year_month_day',
        'timePoint': '2026-04-07',
        'referenceNowIso': '2026-04-08T10:30:00+08:00',
        'timezone': 'Asia/Shanghai',
      }),
    );
    final second = await tool.execute(
      AssistantToolArguments.fromJson(<String, dynamic>{
        'query': 'A股为什么大涨',
        'timeScope': 'year_month_day',
        'timePoint': '2026-04-07',
        'referenceNowIso': '2026-04-08T10:30:00+08:00',
        'timezone': 'Asia/Shanghai',
      }),
    );
    final third = await tool.execute(
      AssistantToolArguments.fromJson(<String, dynamic>{
        'query': 'A股为什么大涨',
        'timeScope': 'year_month_day',
        'timePoint': '2026-04-07',
        'referenceNowIso': '2026-04-09T10:30:00+08:00',
        'timezone': 'Asia/Shanghai',
      }),
    );

    expect(first.success, isTrue);
    expect(second.success, isTrue);
    expect(third.success, isTrue);
    expect(requestCount, equals(2));
    expect(second.data?['cacheHit'], isTrue);
    final firstTimeConstraint = (first.data?['timeConstraint'] as Map?)
        ?.cast<String, dynamic>();
    final secondTimeConstraint = (second.data?['timeConstraint'] as Map?)
        ?.cast<String, dynamic>();
    expect(firstTimeConstraint, isNotNull);
    expect(secondTimeConstraint, isNotNull);
    expect(secondTimeConstraint, equals(firstTimeConstraint));
    expect(secondTimeConstraint!['temporalMode'], 'historical');
    final secondRefs =
        (second.data?['references'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
    expect(secondRefs, isNotEmpty);
    expect(secondRefs.first['freshnessSatisfied'], isTrue);
    expect(third.data?['cacheHit'], isNot(true));
  });

  test('provider date 会补齐 publishedAt 与 observedAt', () async {
    final tool = WebSearchTool(
      openclawBaseUrl: 'http://mock.openclaw',
      enableInteractionLogging: false,
      resolveRuntimeConfigFromDisk: false,
      textLoader: _testTextLoader,
      httpClient: MockClient((request) async {
        return http.Response(
          jsonEncode(<String, dynamic>{
            'message': '已命中新结果',
            'references': <Map<String, dynamic>>[
              <String, dynamic>{
                'title': '深圳天气快讯',
                'url': 'https://weather.example.com/shenzhen/today',
                'snippet': '深圳今天晴，体感偏暖。',
                'date': '2026-04-09T08:20:00.000Z',
              },
            ],
          }),
          200,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );

    final result = await tool.execute(
      AssistantToolArguments.fromJson(<String, dynamic>{
        'query': '深圳今天天气怎么样',
        'referenceNowIso': '2026-04-09T10:30:00.000',
        'timezone': 'Asia/Shanghai',
      }),
    );

    expect(result.success, isTrue);
    final refs =
        (result.data?['references'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
    expect(refs, isNotEmpty);
    expect(refs.first['publishedAt'], isNotEmpty);
    expect(refs.first['observedAt'], isNotEmpty);
    expect(result.data?['freshnessKnown'], isTrue);
  });

  test(
    'generic source rerank 会优先 news/analysis 而不是 pdf/announcement',
    () async {
      final tool = WebSearchTool(
        openclawBaseUrl: 'http://mock.openclaw',
        enableInteractionLogging: false,
        resolveRuntimeConfigFromDisk: false,
        textLoader: _testTextLoader,
        httpClient: MockClient((request) async {
          return http.Response(
            jsonEncode(<String, dynamic>{
              'message': '已命中多个候选',
              'references': <Map<String, dynamic>>[
                <String, dynamic>{
                  'title': '公司公告',
                  'url': 'https://example.com/announcement/prospectus.pdf',
                  'snippet': 'prospectus appendix pdf',
                },
                <String, dynamic>{
                  'title': '市场解读：A股为何大涨',
                  'url': 'https://news.example.com/analysis/market-recap',
                  'snippet': 'analysis recap summary of today market move',
                },
              ],
            }),
            200,
            headers: <String, String>{'content-type': 'application/json'},
          );
        }),
      );

      final result = await tool.execute(
        AssistantToolArguments.fromJson(<String, dynamic>{'query': 'A股为什么大涨'}),
      );

      expect(result.success, isTrue);
      final refs =
          (result.data?['references'] as List?)
              ?.whereType<Map>()
              .map((item) => item.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[];
      expect(refs, hasLength(2));
      expect(refs.first['url'], contains('market-recap'));
      expect(refs.last['url'], contains('.pdf'));
    },
  );

  test('authority 满足只依赖 source tier 与 authorityDomains 的通用字段', () async {
    final tool = WebSearchTool(
      openclawBaseUrl: 'http://mock.openclaw',
      enableInteractionLogging: false,
      resolveRuntimeConfigFromDisk: false,
      textLoader: _testTextLoader,
      httpClient: MockClient((request) async {
        return http.Response(
          jsonEncode(<String, dynamic>{
            'message': '已命中高权威来源',
            'references': <Map<String, dynamic>>[
              <String, dynamic>{
                'title': '通告',
                'url': 'https://news.example.com/notice',
                'snippet': '这里是通告正文。',
                'sourceTier': 'authority',
              },
            ],
          }),
          200,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );

    final result = await tool.execute(
      AssistantToolArguments.fromJson(<String, dynamic>{
        'query': '政策通告',
        'authorityDomains': <String>['gov.cn'],
      }),
    );

    expect(result.success, isTrue);
    expect(result.data?['authoritySatisfied'], isTrue);
    expect(result.data?['authoritativeCount'], 1);
  });

  test(
    'finance_consumer 会限制多路 query 数量且不再默认拼接高噪声 contextConstraints',
    () async {
      final capturedQueries = <String>[];
      final tool = WebSearchTool(
        openclawBaseUrl: 'http://mock.openclaw',
        enableInteractionLogging: false,
        resolveRuntimeConfigFromDisk: false,
        textLoader: _testTextLoader,
        httpClient: MockClient((request) async {
          capturedQueries.add(
            _extractProxyQuery(
              jsonDecode(request.body) as Map<String, dynamic>,
            ),
          );
          return http.Response(
            jsonEncode(<String, dynamic>{
              'message': '已命中候选',
              'references': <Map<String, dynamic>>[
                <String, dynamic>{
                  'title': 'A股盘后解读',
                  'url': 'https://news.example.com/analysis/market-recap',
                  'snippet': '2026-04-09 A股上涨，风险偏好修复与权重板块共振。',
                },
              ],
            }),
            200,
            headers: <String, String>{'content-type': 'application/json'},
          );
        }),
      );

      final result = await tool.execute(
        AssistantToolArguments.fromJson(<String, dynamic>{
          'query': '昨天A股为什么大涨',
          'domainId': 'finance_consumer',
          'queryTasks': <Map<String, dynamic>>[
            <String, dynamic>{'id': 'q1', 'query': '2026-04-09 A股 大涨 原因'},
            <String, dynamic>{'id': 'q2', 'query': '2026-04-09 中国股市 表现'},
            <String, dynamic>{'id': 'q3', 'query': '2026-04-09 A股 领涨板块'},
          ],
          'referenceNowIso': '2026-04-10T10:30:00.000',
          'timezone': 'Asia/Shanghai',
        }),
      );

      expect(result.success, isTrue);
      expect(capturedQueries, hasLength(2));
      expect(
        capturedQueries.any(
          (query) => query.contains('财务口径') || query.contains('风险提示'),
        ),
        isFalse,
      );
    },
  );

  test('finance_consumer 会过滤低相关 accepted refs', () async {
    final tool = WebSearchTool(
      openclawBaseUrl: 'http://mock.openclaw',
      enableInteractionLogging: false,
      resolveRuntimeConfigFromDisk: false,
      textLoader: _testTextLoader,
      httpClient: MockClient((request) async {
        return http.Response(
          jsonEncode(<String, dynamic>{
            'message': '已命中多个候选',
            'references': <Map<String, dynamic>>[
              <String, dynamic>{
                'title': '市场解读：A股为何大涨',
                'url': 'https://news.example.com/analysis/market-recap',
                'snippet': '2026-04-09 A股上涨与风险偏好修复有关。',
                'relevanceScore': 0.82,
              },
              <String, dynamic>{
                'title': '公司公告',
                'url': 'https://example.com/notice.pdf',
                'snippet': '与本轮盘面原因无直接关系。',
                'relevanceScore': 0.21,
              },
            ],
          }),
          200,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );

    final result = await tool.execute(
      AssistantToolArguments.fromJson(<String, dynamic>{
        'query': '昨天A股为什么大涨',
        'domainId': 'finance_consumer',
        'queryTaskId': 'stock_reason',
        'queryTaskLabel': '上涨原因',
        'entityAnchors': <String>['A股'],
        'referenceNowIso': '2026-04-10T10:30:00.000',
        'timezone': 'Asia/Shanghai',
      }),
    );

    expect(result.success, isTrue);
    final refs =
        (result.data?['references'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
    expect(refs, hasLength(1));
    expect(refs.single['url'], contains('market-recap'));
  });
}

String _extractProxyQuery(Map<String, dynamic> payload) {
  final arguments =
      (payload['arguments'] as Map?)?.cast<String, dynamic>() ??
      const <String, dynamic>{};
  final toolArgs =
      (arguments['toolArgs'] as Map?)?.cast<String, dynamic>() ??
      const <String, dynamic>{};
  return (toolArgs['query'] as String?)?.trim() ?? '';
}

Future<String> _testTextLoader(String path) async {
  if (path.endsWith('retrieval_time_contract.json')) {
    return jsonEncode(<String, dynamic>{
      'defaultScope': 'last_30d',
      'defaultFreshnessHoursMax': 72,
      'supportedScopes': <String>[
        'latest',
        'today',
        'last_7d',
        'last_30d',
        'last_1y',
        'year_to_date',
        'year',
        'year_month',
        'year_month_day',
        'custom',
        'unspecified',
      ],
      'windowHoursByScope': <String, int>{
        'latest': 24,
        'today': 24,
        'last_7d': 24 * 7,
        'last_30d': 24 * 30,
        'last_1y': 24 * 365,
      },
      'freshnessHoursMaxByScope': <String, int>{
        'latest': 12,
        'today': 24,
        'last_7d': 24 * 7,
        'last_30d': 24 * 30,
        'last_1y': 24 * 365,
      },
    });
  }
  if (path.endsWith('skills/weather/config/retrieval_policy.json')) {
    return jsonEncode(<String, dynamic>{
      'defaultTimeScope': 'latest',
      'defaultFreshnessHoursMax': 1,
      'authorityRequired': true,
      'allowedTimeScopes': <String>[
        'latest',
        'today',
        'last_7d',
        'custom',
        'unspecified',
      ],
      'authorityDomains': <String>['weather.com.cn', 'nmc.cn', 'cma.gov.cn'],
      'contextConstraints': <String>[
        '优先返回实时天气关键指标',
        '必须覆盖温度湿度风速和体感温度',
        '若无法获取实时指标需明确说明并给出重试策略',
      ],
      'negativeKeywords': <String>[
        '40天',
        '40d',
        '15天',
        '15日',
        '未来40天',
        '未来15天',
        'weather40d',
      ],
    });
  }
  if (path.endsWith('skills/finance_consumer/config/retrieval_policy.json')) {
    return jsonEncode(<String, dynamic>{
      'defaultTimeScope': 'latest',
      'defaultFreshnessHoursMax': 6,
      'maxQueryTasks': 2,
      'minAcceptedRelevanceScore': 0.45,
      'authorityDomains': <String>['eastmoney.com', 'sina.com.cn'],
    });
  }
  throw ArgumentError('Unexpected test asset path: $path');
}
