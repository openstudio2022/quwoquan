import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart' show rootBundle;

class ProgressTextPolicy {
  const ProgressTextPolicy({
    required this.jsonEnvelopeSignatures,
    required this.progressLexicon,
    required this.degradedPrefixes,
    required this.degradedSubstrings,
  });

  final List<String> jsonEnvelopeSignatures;
  final List<String> progressLexicon;
  final List<String> degradedPrefixes;
  final List<String> degradedSubstrings;

  static const ProgressTextPolicy defaults = ProgressTextPolicy(
    jsonEnvelopeSignatures: <String>[
      '"contractId"',
      '"decision"',
      '"userMarkdown"',
    ],
    progressLexicon: <String>[
      '正在查询',
      '正在获取',
      '正在执行',
      '正在检索',
      '正在搜索',
      '正在为您',
      '正在规划',
      '稍等一下',
      '请稍等',
      '请稍候',
      '执行进度',
      'searching for',
      'retrieving',
      'processing your',
      'please wait',
      'working on it',
      'in progress',
    ],
    degradedPrefixes: <String>[
      '模型调用失败',
      '模型调用异常',
      '助手暂时不可用',
      '当前模型服务不可用',
      '模板渲染失败',
    ],
    degradedSubstrings: <String>[
      '服务暂时不可用',
      '暂时不可用，已尝试自动恢复',
      'HTTP 400',
      'HTTP 500',
      'HTTP 503',
    ],
  );

  factory ProgressTextPolicy.fromJson(Map<String, dynamic> json) {
    final signatures =
        (json['jsonEnvelopeSignatures'] as List?)
            ?.whereType<String>()
            .map((e) => e.trim())
            .where((e) => e.isNotEmpty)
            .toList(growable: false) ??
        defaults.jsonEnvelopeSignatures;
    final lexicon = <String>[
      ...((json['progressLexicon'] as Map?)?['zh'] as List?)
              ?.whereType<String>()
              .map((e) => e.trim())
              .where((e) => e.isNotEmpty)
              .toList(growable: false) ??
          const <String>[],
      ...((json['progressLexicon'] as Map?)?['en'] as List?)
              ?.whereType<String>()
              .map((e) => e.trim())
              .where((e) => e.isNotEmpty)
              .toList(growable: false) ??
          const <String>[],
    ];
    final degradedPrefixes =
        (json['degradedPrefixes'] as List?)
            ?.whereType<String>()
            .map((e) => e.trim())
            .where((e) => e.isNotEmpty)
            .toList(growable: false) ??
        defaults.degradedPrefixes;
    final degradedSubstrings =
        (json['degradedSubstrings'] as List?)
            ?.whereType<String>()
            .map((e) => e.trim())
            .where((e) => e.isNotEmpty)
            .toList(growable: false) ??
        defaults.degradedSubstrings;
    return ProgressTextPolicy(
      jsonEnvelopeSignatures: signatures,
      progressLexicon: lexicon.isEmpty ? defaults.progressLexicon : lexicon,
      degradedPrefixes: degradedPrefixes,
      degradedSubstrings: degradedSubstrings,
    );
  }

  static Future<ProgressTextPolicy> loadFromAsset(String path) async {
    try {
      final raw = await _loadPolicyText(path);
      final decoded = jsonDecode(raw);
      if (decoded is Map) {
        return ProgressTextPolicy.fromJson(decoded.cast<String, dynamic>());
      }
    } catch (_) {}
    return defaults;
  }
}

class ReactSuppressRule {
  const ReactSuppressRule({
    required this.toolName,
    required this.errorCodes,
    required this.messageKeywords,
  });

  final String toolName;
  final List<String> errorCodes;
  final List<String> messageKeywords;
}

class ReactToolStatusRule {
  const ReactToolStatusRule({
    required this.toolName,
    required this.successWithSummary,
    required this.successWithoutSummary,
    required this.invalidArgumentsStatus,
    required this.permissionDeniedStatus,
    required this.errorStatus,
  });

  final String toolName;
  final String successWithSummary;
  final String successWithoutSummary;
  final String invalidArgumentsStatus;
  final String permissionDeniedStatus;
  final String errorStatus;
}

class ReactPolicy {
  const ReactPolicy({
    required this.replanCoverageMin,
    required this.replanConfidenceMin,
    required this.replanFreshnessHoursMax,
    required this.reflectionQualityScoreMin,
    required this.reflectionMaxRounds,
    required this.replanStatuses,
    required this.replanRetryableErrorClasses,
    required this.errorClassMap,
    required this.retryableErrorCodes,
    required this.suppressUserErrorRules,
    required this.toolStatusRules,
    required this.llmRetryWithoutToolsStatusCodes,
    required this.llmRetryWithoutToolsKeywords,
    required this.llmRetryWithoutJsonModeStatusCodes,
    required this.llmRetryWithoutJsonModeKeywords,
  });

  final double replanCoverageMin;
  final double replanConfidenceMin;
  final double replanFreshnessHoursMax;
  final double reflectionQualityScoreMin;
  final int reflectionMaxRounds;
  final List<String> replanStatuses;
  final List<String> replanRetryableErrorClasses;
  final Map<String, String> errorClassMap;
  final List<String> retryableErrorCodes;
  final List<ReactSuppressRule> suppressUserErrorRules;
  final List<ReactToolStatusRule> toolStatusRules;
  final List<int> llmRetryWithoutToolsStatusCodes;
  final List<String> llmRetryWithoutToolsKeywords;
  final List<int> llmRetryWithoutJsonModeStatusCodes;
  final List<String> llmRetryWithoutJsonModeKeywords;

  static const ReactPolicy defaults = ReactPolicy(
    replanCoverageMin: 0.7,
    replanConfidenceMin: 0.65,
    replanFreshnessHoursMax: 72,
    reflectionQualityScoreMin: 0.4,
    reflectionMaxRounds: 2,
    replanStatuses: <String>[
      'retrieval_no_summary',
      'retrieval_no_data',
      'retrieval_error',
    ],
    replanRetryableErrorClasses: <String>['timeout', 'network', 'rate_limited'],
    errorClassMap: <String, String>{
      'none': 'none',
      'invalidArguments': 'invalid_args',
      'permissionDenied': 'permission',
      'networkUnavailable': 'network',
      'rateLimited': 'rate_limited',
      'unauthorized': 'unauthorized',
      'toolNotFound': 'tool_not_found',
    },
    retryableErrorCodes: <String>['rateLimited', 'networkUnavailable'],
    suppressUserErrorRules: <ReactSuppressRule>[
      ReactSuppressRule(
        toolName: 'search',
        errorCodes: <String>[
          'invalidArguments',
          'networkUnavailable',
          'rateLimited',
          'executionFailed',
        ],
        messageKeywords: <String>[
          'api key',
          '未发现可用搜索 provider',
          '检索未找到足够信息',
          '检索完成但信息不足',
          'proxy',
        ],
      ),
      ReactSuppressRule(
        toolName: 'web_search',
        errorCodes: <String>[
          'invalidArguments',
          'networkUnavailable',
          'rateLimited',
          'executionFailed',
        ],
        messageKeywords: <String>[
          'api key',
          '未发现可用搜索 provider',
          '检索未找到足够信息',
          '检索完成但信息不足',
          'proxy',
        ],
      ),
      ReactSuppressRule(
        toolName: 'web_fetch',
        errorCodes: <String>[
          'unsupportedTarget',
          'networkUnavailable',
          'rateLimited',
          'executionFailed',
        ],
        messageKeywords: <String>[
          'unsupported content type',
          'application/pdf',
          'timeout',
          '403',
          '429',
        ],
      ),
    ],
    toolStatusRules: <ReactToolStatusRule>[
      ReactToolStatusRule(
        toolName: 'search',
        successWithSummary: 'retrieval_summary',
        successWithoutSummary: 'retrieval_no_summary',
        invalidArgumentsStatus: 'retrieval_invalid_args',
        permissionDeniedStatus: 'retrieval_permission_denied',
        errorStatus: 'retrieval_error',
      ),
      ReactToolStatusRule(
        toolName: 'web_search',
        successWithSummary: 'retrieval_summary',
        successWithoutSummary: 'retrieval_no_summary',
        invalidArgumentsStatus: 'retrieval_invalid_args',
        permissionDeniedStatus: 'retrieval_permission_denied',
        errorStatus: 'retrieval_error',
      ),
      ReactToolStatusRule(
        toolName: 'local_context',
        successWithSummary: 'context_fetched',
        successWithoutSummary: 'context_fetched',
        invalidArgumentsStatus: 'context_invalid_args',
        permissionDeniedStatus: 'context_permission_denied',
        errorStatus: 'context_error',
      ),
    ],
    llmRetryWithoutToolsStatusCodes: <int>[400, 422, 500],
    llmRetryWithoutToolsKeywords: <String>[
      'tool_choice',
      'function calling',
      'unsupported',
      'schema',
    ],
    llmRetryWithoutJsonModeStatusCodes: <int>[400, 422],
    llmRetryWithoutJsonModeKeywords: <String>[
      'response_format',
      'json_object',
      'structured output',
      'json mode',
    ],
  );

  factory ReactPolicy.fromJson(Map<String, dynamic> json) {
    final thresholds =
        (json['replanThresholds'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final reflectionThresholds =
        (json['reflectionThresholds'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final errorClassRaw =
        (json['errorClassMap'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final errorClassMap = <String, String>{
      for (final entry in errorClassRaw.entries)
        entry.key: entry.value.toString().trim(),
    };
    final suppressRules =
        ((json['suppressUserErrorRules'] as List?)
                    ?.whereType<Map>()
                    .map((item) => item.cast<String, dynamic>())
                    .toList(growable: false) ??
                const <Map<String, dynamic>>[])
            .map(
              (item) => ReactSuppressRule(
                toolName: (item['toolName'] as String?)?.trim() ?? '',
                errorCodes:
                    (item['errorCodes'] as List?)
                        ?.whereType<String>()
                        .map((e) => e.trim())
                        .where((e) => e.isNotEmpty)
                        .toList(growable: false) ??
                    const <String>[],
                messageKeywords:
                    (item['messageKeywords'] as List?)
                        ?.whereType<String>()
                        .map((e) => e.trim())
                        .where((e) => e.isNotEmpty)
                        .toList(growable: false) ??
                    const <String>[],
              ),
            )
            .where((rule) => rule.toolName.isNotEmpty)
            .toList(growable: false);
    final toolStatusRules =
        ((json['toolStatusRules'] as List?)
                    ?.whereType<Map>()
                    .map((item) => item.cast<String, dynamic>())
                    .toList(growable: false) ??
                const <Map<String, dynamic>>[])
            .map(
              (item) => ReactToolStatusRule(
                toolName: (item['toolName'] as String?)?.trim() ?? '',
                successWithSummary:
                    (item['successWithSummary'] as String?)?.trim() ?? '',
                successWithoutSummary:
                    (item['successWithoutSummary'] as String?)?.trim() ?? '',
                invalidArgumentsStatus:
                    (item['invalidArgumentsStatus'] as String?)?.trim() ?? '',
                permissionDeniedStatus:
                    (item['permissionDeniedStatus'] as String?)?.trim() ?? '',
                errorStatus: (item['errorStatus'] as String?)?.trim() ?? '',
              ),
            )
            .where((rule) => rule.toolName.isNotEmpty)
            .toList(growable: false);
    return ReactPolicy(
      replanCoverageMin:
          (thresholds['coverageMin'] as num?)?.toDouble() ??
          defaults.replanCoverageMin,
      replanConfidenceMin:
          (thresholds['confidenceMin'] as num?)?.toDouble() ??
          defaults.replanConfidenceMin,
      replanFreshnessHoursMax:
          (thresholds['freshnessHoursMax'] as num?)?.toDouble() ??
          defaults.replanFreshnessHoursMax,
      reflectionQualityScoreMin:
          (reflectionThresholds['qualityScoreMin'] as num?)?.toDouble() ??
          defaults.reflectionQualityScoreMin,
      reflectionMaxRounds:
          (reflectionThresholds['maxRounds'] as num?)?.toInt() ??
          defaults.reflectionMaxRounds,
      replanStatuses:
          (json['replanStatuses'] as List?)
              ?.whereType<String>()
              .map((e) => e.trim())
              .where((e) => e.isNotEmpty)
              .toList(growable: false) ??
          defaults.replanStatuses,
      replanRetryableErrorClasses:
          (json['replanRetryableErrorClasses'] as List?)
              ?.whereType<String>()
              .map((e) => e.trim())
              .where((e) => e.isNotEmpty)
              .toList(growable: false) ??
          defaults.replanRetryableErrorClasses,
      errorClassMap: errorClassMap.isEmpty
          ? defaults.errorClassMap
          : errorClassMap,
      retryableErrorCodes:
          (json['retryableErrorCodes'] as List?)
              ?.whereType<String>()
              .map((e) => e.trim())
              .where((e) => e.isNotEmpty)
              .toList(growable: false) ??
          defaults.retryableErrorCodes,
      suppressUserErrorRules: suppressRules.isEmpty
          ? defaults.suppressUserErrorRules
          : suppressRules,
      toolStatusRules: toolStatusRules.isEmpty
          ? defaults.toolStatusRules
          : toolStatusRules,
      llmRetryWithoutToolsStatusCodes:
          (json['llmRetryWithoutToolsStatusCodes'] as List?)
              ?.whereType<num>()
              .map((e) => e.toInt())
              .toList(growable: false) ??
          defaults.llmRetryWithoutToolsStatusCodes,
      llmRetryWithoutToolsKeywords:
          (json['llmRetryWithoutToolsKeywords'] as List?)
              ?.whereType<String>()
              .map((e) => e.trim())
              .where((e) => e.isNotEmpty)
              .toList(growable: false) ??
          defaults.llmRetryWithoutToolsKeywords,
      llmRetryWithoutJsonModeStatusCodes:
          (json['llmRetryWithoutJsonModeStatusCodes'] as List?)
              ?.whereType<num>()
              .map((e) => e.toInt())
              .toList(growable: false) ??
          defaults.llmRetryWithoutJsonModeStatusCodes,
      llmRetryWithoutJsonModeKeywords:
          (json['llmRetryWithoutJsonModeKeywords'] as List?)
              ?.whereType<String>()
              .map((e) => e.trim())
              .where((e) => e.isNotEmpty)
              .toList(growable: false) ??
          defaults.llmRetryWithoutJsonModeKeywords,
    );
  }

  ReactSuppressRule? suppressRuleFor(String toolName) {
    for (final rule in suppressUserErrorRules) {
      if (rule.toolName == toolName) return rule;
    }
    return null;
  }

  ReactToolStatusRule? statusRuleFor(String toolName) {
    for (final rule in toolStatusRules) {
      if (rule.toolName == toolName) return rule;
    }
    return null;
  }

  static Future<ReactPolicy> loadFromAsset(String path) async {
    try {
      final raw = await _loadPolicyText(path);
      final decoded = jsonDecode(raw);
      if (decoded is Map) {
        return ReactPolicy.fromJson(decoded.cast<String, dynamic>());
      }
    } catch (_) {}
    return defaults;
  }
}

Future<String> _loadPolicyText(String path) async {
  try {
    return await rootBundle.loadString(path);
  } catch (_) {
    final file = File(path);
    if (!await file.exists()) rethrow;
    return file.readAsString();
  }
}
