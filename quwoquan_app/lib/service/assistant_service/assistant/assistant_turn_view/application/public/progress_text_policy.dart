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
            .map((value) => value.trim())
            .where((value) => value.isNotEmpty)
            .toList(growable: false) ??
        defaults.jsonEnvelopeSignatures;
    final lexicon = <String>[
      ...((json['progressLexicon'] as Map?)?['zh'] as List?)
              ?.whereType<String>()
              .map((value) => value.trim())
              .where((value) => value.isNotEmpty)
              .toList(growable: false) ??
          const <String>[],
      ...((json['progressLexicon'] as Map?)?['en'] as List?)
              ?.whereType<String>()
              .map((value) => value.trim())
              .where((value) => value.isNotEmpty)
              .toList(growable: false) ??
          const <String>[],
    ];
    final degradedPrefixes =
        (json['degradedPrefixes'] as List?)
            ?.whereType<String>()
            .map((value) => value.trim())
            .where((value) => value.isNotEmpty)
            .toList(growable: false) ??
        defaults.degradedPrefixes;
    final degradedSubstrings =
        (json['degradedSubstrings'] as List?)
            ?.whereType<String>()
            .map((value) => value.trim())
            .where((value) => value.isNotEmpty)
            .toList(growable: false) ??
        defaults.degradedSubstrings;
    return ProgressTextPolicy(
      jsonEnvelopeSignatures: signatures,
      progressLexicon: lexicon.isEmpty ? defaults.progressLexicon : lexicon,
      degradedPrefixes: degradedPrefixes,
      degradedSubstrings: degradedSubstrings,
    );
  }
}
