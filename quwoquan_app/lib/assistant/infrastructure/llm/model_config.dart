import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:path_provider/path_provider.dart';

class AssistantModelRuntimeConfig {
  const AssistantModelRuntimeConfig({
    required this.modelRef,
    required this.providerId,
    required this.modelId,
    required this.baseUrl,
    required this.apiKey,
  });

  final String modelRef;
  final String providerId;
  final String modelId;
  final String baseUrl;
  final String apiKey;
}

enum ModelReasoningMode {
  none,
  nativeField,
  thinkTag,
  jsonThinkingText,
}

enum ModelToolCallMode { nativeFunction, xmlTagged, jsonEnvelope }

/// Declares per-model capability differences so the streaming parser,
/// tool-call extraction, and prompt construction can adapt automatically.
class ModelCapabilityProfile {
  const ModelCapabilityProfile({
    this.supportsNativeFunctionCalling = true,
    this.supportsReasoningField = false,
    this.supportsThinkTags = false,
    this.reasoningFieldName = '',
    this.reasoningRequestObject = const <String, dynamic>{},
    this.supportsJsonMode = true,
    this.reasoningMode = ModelReasoningMode.jsonThinkingText,
    this.toolCallMode = ModelToolCallMode.nativeFunction,
    this.supportsStreamingAnswer = true,
    this.defaultMaxTokens = 4096,
    this.defaultTemperature = 0.3,
  });

  final bool supportsNativeFunctionCalling;
  final bool supportsReasoningField;
  final bool supportsThinkTags;
  final String reasoningFieldName;
  final Map<String, dynamic> reasoningRequestObject;
  final bool supportsJsonMode;
  final ModelReasoningMode reasoningMode;
  final ModelToolCallMode toolCallMode;
  final bool supportsStreamingAnswer;
  final int defaultMaxTokens;
  final double defaultTemperature;

  static const ModelCapabilityProfile openAiDefault =
      ModelCapabilityProfile();

  static const ModelCapabilityProfile mimo = ModelCapabilityProfile(
    supportsNativeFunctionCalling: false,
    supportsReasoningField: true,
    reasoningFieldName: 'reasoning_content',
    reasoningRequestObject: <String, dynamic>{'enabled': true},
    supportsJsonMode: false,
    reasoningMode: ModelReasoningMode.nativeField,
    toolCallMode: ModelToolCallMode.jsonEnvelope,
    defaultTemperature: 0.6,
  );

  static const ModelCapabilityProfile deepseek = ModelCapabilityProfile(
    supportsThinkTags: true,
    supportsReasoningField: true,
    reasoningFieldName: 'reasoning_content',
    reasoningMode: ModelReasoningMode.nativeField,
    toolCallMode: ModelToolCallMode.nativeFunction,
  );

  static const ModelCapabilityProfile qwen = ModelCapabilityProfile(
    supportsThinkTags: true,
    reasoningMode: ModelReasoningMode.thinkTag,
    toolCallMode: ModelToolCallMode.xmlTagged,
  );

  /// Resolves the best-matching profile for a given modelRef (e.g. "mimo/mimo-v2-flash").
  static ModelCapabilityProfile forModelRef(String modelRef) {
    final lower = modelRef.toLowerCase();
    if (lower.startsWith('mimo/') || lower.contains('mimo')) return mimo;
    if (lower.contains('deepseek')) return deepseek;
    if (lower.contains('qwen')) return qwen;
    return openAiDefault;
  }
}

class AssistantModelConfigLoader {
  const AssistantModelConfigLoader();

  List<AssistantModelRuntimeConfig> loadDefaultSync() {
    final project = loadFromProjectSync();
    if (project.isNotEmpty) return project;
    final independent = loadFromPersonalAssistantSync();
    if (independent.isNotEmpty) return independent;
    final envBased = loadFromEnvironmentSync();
    if (envBased.isNotEmpty) return envBased;
    final mimoFallback = _loadMimoDefaultFallbackSync();
    if (mimoFallback.isNotEmpty) return mimoFallback;
    return const <AssistantModelRuntimeConfig>[];
  }

  /// 异步加载：优先使用打包进应用的 config + .env，保证 App/移动端无需工程目录即可获得模型与搜索配置。
  Future<List<AssistantModelRuntimeConfig>> loadDefault() async {
    final bundled = await loadFromBundledAsset();
    if (bundled.isNotEmpty) return bundled;
    final project = await loadFromProject();
    if (project.isNotEmpty) return project;
    final independent = await loadFromPersonalAssistant();
    if (independent.isNotEmpty) return independent;
    final envBased = loadFromEnvironmentSync();
    if (envBased.isNotEmpty) return envBased;
    final mimoFallback = _loadMimoDefaultFallbackSync();
    if (mimoFallback.isNotEmpty) return mimoFallback;
    return const <AssistantModelRuntimeConfig>[];
  }

  Future<List<AssistantModelRuntimeConfig>> loadFromBundledAsset() async {
    try {
      final configText = await rootBundle.loadString(
        'assistant/config.json',
      );
      final decoded = jsonDecode(configText);
      if (decoded is! Map<String, dynamic>) {
        return const <AssistantModelRuntimeConfig>[];
      }

      Map<String, String> envMap = const <String, String>{};
      try {
        final envText = await rootBundle.loadString('assistant/.env');
        envMap = _parseDotEnvContent(envText);
      } catch (_) {
        envMap = const <String, String>{};
      }

      return _extractConfigs(
        decoded,
        envFileMap: envMap,
        defaultProviderId: 'project_asset',
      );
    } catch (_) {
      return const <AssistantModelRuntimeConfig>[];
    }
  }

  /// 工程内模型配置（优先），不依赖 Moltbot 目录
  /// 约定位置：
  /// - assistant/config.json
  /// - assistant/.env（可选）
  List<AssistantModelRuntimeConfig> loadFromProjectSync() {
    for (final candidate in _projectConfigCandidatesSync()) {
      final configFile = File(candidate.configPath);
      if (!configFile.existsSync()) continue;
      final configs = _loadFromFileSync(
        configFile,
        candidate.envPath,
        defaultProviderId: 'project',
      );
      if (configs.isNotEmpty) return configs;
    }
    return const <AssistantModelRuntimeConfig>[];
  }

  Future<List<AssistantModelRuntimeConfig>> loadFromProject() async {
    for (final candidate in _projectConfigCandidatesSync()) {
      final configFile = File(candidate.configPath);
      if (!await configFile.exists()) continue;
      final configs = await _loadFromFile(
        configFile,
        candidate.envPath,
        defaultProviderId: 'project',
      );
      if (configs.isNotEmpty) return configs;
    }
    return const <AssistantModelRuntimeConfig>[];
  }

  List<AssistantModelRuntimeConfig> loadFromPersonalAssistantSync() {
    final home = Platform.environment['HOME'] ?? '';
    if (home.isEmpty) return const <AssistantModelRuntimeConfig>[];
    for (final candidate in _homeConfigCandidates(home)) {
      final configFile = File(candidate.configPath);
      if (!configFile.existsSync()) continue;
      final configs = _loadFromFileSync(
        configFile,
        candidate.envPath,
        defaultProviderId: 'assistant_home',
      );
      if (configs.isNotEmpty) return configs;
    }
    return const <AssistantModelRuntimeConfig>[];
  }

  Future<List<AssistantModelRuntimeConfig>> loadFromPersonalAssistant() async {
    final home = Platform.environment['HOME'] ?? '';
    if (home.isEmpty) return const <AssistantModelRuntimeConfig>[];
    for (final candidate in _homeConfigCandidates(home)) {
      final configFile = File(candidate.configPath);
      if (!await configFile.exists()) {
        continue;
      }
      final configs = await _loadFromFile(
        configFile,
        candidate.envPath,
        defaultProviderId: 'assistant_home',
      );
      if (configs.isNotEmpty) return configs;
    }
    return const <AssistantModelRuntimeConfig>[];
  }

  List<AssistantModelRuntimeConfig> loadFromEnvironmentSync() {
    final env = Platform.environment;
    final modelId = (env['PERSONAL_ASSISTANT_MODEL_ID'] ?? '').trim();
    final baseUrl = (env['PERSONAL_ASSISTANT_MODEL_BASE_URL'] ?? '').trim();
    final apiKey = (env['PERSONAL_ASSISTANT_MODEL_API_KEY'] ?? '').trim();
    final providerId =
        (env['PERSONAL_ASSISTANT_MODEL_PROVIDER'] ?? 'openai_compatible')
            .trim();
    if (modelId.isEmpty || baseUrl.isEmpty || apiKey.isEmpty) {
      return const <AssistantModelRuntimeConfig>[];
    }
    final ref = '$providerId/$modelId';
    return <AssistantModelRuntimeConfig>[
      AssistantModelRuntimeConfig(
        modelRef: ref,
        providerId: providerId,
        modelId: modelId,
        baseUrl: baseUrl,
        apiKey: apiKey,
      ),
    ];
  }

  /// 从应用存储目录加载配置（适用于移动端，HOME 可能为空）
  Future<List<AssistantModelRuntimeConfig>> loadFromAppStorage() async {
    try {
      final dir = await getApplicationDocumentsDirectory();
      var basePath = dir.path;
      if (basePath.endsWith('app_flutter')) {
        basePath = Directory(basePath).parent.path;
      }
      final assistantHomeConfig = File('$basePath/.assistant/config.json');
      if (await assistantHomeConfig.exists()) {
        final configs = await _loadFromFile(
          assistantHomeConfig,
          '$basePath/.assistant/.env',
          defaultProviderId: 'assistant_home',
        );
        if (configs.isNotEmpty) return configs;
      }
      final legacyHomeConfig = File('$basePath/.personal_assistant/config.json');
      if (await legacyHomeConfig.exists()) {
        final configs = await _loadFromFile(
          legacyHomeConfig,
          '$basePath/.personal_assistant/.env',
          defaultProviderId: 'assistant_home_legacy',
        );
        if (configs.isNotEmpty) return configs;
      }
      final projectConfig = File('$basePath/assistant/config.json');
      if (await projectConfig.exists()) {
        final configs = await _loadFromFile(
          projectConfig,
          '$basePath/assistant/.env',
          defaultProviderId: 'project_storage',
        );
        if (configs.isNotEmpty) return configs;
      }
    } catch (_) {
      // 忽略异常，回退到其他来源
    }
    return const <AssistantModelRuntimeConfig>[];
  }

  Future<List<AssistantModelRuntimeConfig>> _loadFromFile(
    File configFile,
    String envPath, {
    required String defaultProviderId,
  }) async {
    final text = await configFile.readAsString();
    final decoded = jsonDecode(text);
    if (decoded is! Map<String, dynamic>) {
      return const <AssistantModelRuntimeConfig>[];
    }
    final envFileMap = await _readDotEnv(envPath);
    return _extractConfigs(
      decoded,
      envFileMap: envFileMap,
      defaultProviderId: defaultProviderId,
    );
  }

  List<AssistantModelRuntimeConfig> _loadFromFileSync(
    File configFile,
    String envPath, {
    required String defaultProviderId,
  }) {
    final text = configFile.readAsStringSync();
    final decoded = jsonDecode(text);
    if (decoded is! Map<String, dynamic>) {
      return const <AssistantModelRuntimeConfig>[];
    }
    final envFileMap = _readDotEnvSync(envPath);
    return _extractConfigs(
      decoded,
      envFileMap: envFileMap,
      defaultProviderId: defaultProviderId,
    );
  }

  List<AssistantModelRuntimeConfig> _extractConfigs(
    Map<String, dynamic> root, {
    required Map<String, String> envFileMap,
    required String defaultProviderId,
  }) {
    final mergedEnv = _mergeNonEmptyEnvMaps(<Map<String, String>>[
      _readSharedDotEnvsSync(),
      envFileMap,
    ]);
    final providers =
        ((root['models'] as Map?)?['providers'] as Map?)
            ?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    if (providers.isNotEmpty) {
      final preference = _readModelPreference(root);
      final configs = _extractFromProviderMap(providers, mergedEnv);
      return _sortByPreference(configs, preference);
    }

    final modelId = (root['modelId'] as String?)?.trim() ?? '';
    final baseUrl = (root['baseUrl'] as String?)?.trim() ?? '';
    final apiKeyRaw = (root['apiKey'] as String?)?.trim() ?? '';
    if (modelId.isEmpty || baseUrl.isEmpty || apiKeyRaw.isEmpty) {
      return const <AssistantModelRuntimeConfig>[];
    }
    final apiKey = _resolveApiKey(apiKeyRaw, mergedEnv);
    if (apiKey.isEmpty) return const <AssistantModelRuntimeConfig>[];
    final providerId =
        (root['providerId'] as String?)?.trim() ?? defaultProviderId;
    return <AssistantModelRuntimeConfig>[
      AssistantModelRuntimeConfig(
        modelRef: '$providerId/$modelId',
        providerId: providerId,
        modelId: modelId,
        baseUrl: baseUrl,
        apiKey: apiKey,
      ),
    ];
  }

  List<AssistantModelRuntimeConfig> _extractFromProviderMap(
    Map<String, dynamic> providers,
    Map<String, String> envFileMap,
  ) {
    final configs = <AssistantModelRuntimeConfig>[];
    for (final providerEntry in providers.entries) {
      final providerId = providerEntry.key;
      final providerMap = providerEntry.value;
      if (providerMap is! Map) continue;
      final typed = providerMap.cast<String, dynamic>();
      final baseUrl = (typed['baseUrl'] as String?)?.trim() ?? '';
      final apiKeyRaw = (typed['apiKey'] as String?)?.trim() ?? '';
      final models = (typed['models'] as List?) ?? const <dynamic>[];
      if (baseUrl.isEmpty || models.isEmpty) continue;
      final resolvedApiKey = _resolveApiKey(apiKeyRaw, envFileMap);
      if (resolvedApiKey.isEmpty) continue;

      for (final model in models) {
        if (model is! Map) continue;
        final modelId = (model['id'] as String?)?.trim() ?? '';
        if (modelId.isEmpty) continue;
        final modelRef = '$providerId/$modelId';
        configs.add(
          AssistantModelRuntimeConfig(
            modelRef: modelRef,
            providerId: providerId,
            modelId: modelId,
            baseUrl: baseUrl,
            apiKey: resolvedApiKey,
          ),
        );
      }
    }
    return configs;
  }

  List<AssistantModelRuntimeConfig> _sortByPreference(
    List<AssistantModelRuntimeConfig> configs,
    _ModelPreference preference,
  ) {
    if (configs.isEmpty) return configs;
    final orderedRefs = <String>[
      if (preference.primaryRef.isNotEmpty) preference.primaryRef,
      ...preference.fallbackRefs,
    ];
    if (orderedRefs.isEmpty) return configs;
    final rank = <String, int>{};
    for (var i = 0; i < orderedRefs.length; i++) {
      rank[orderedRefs[i]] = i;
    }
    configs.sort((a, b) {
      final ra = rank[a.modelRef];
      final rb = rank[b.modelRef];
      if (ra != null && rb != null) return ra.compareTo(rb);
      if (ra != null) return -1;
      if (rb != null) return 1;
      return a.modelRef.compareTo(b.modelRef);
    });
    return configs;
  }

  _ModelPreference _readModelPreference(Map<String, dynamic> map) {
    final agents = map['agents'];
    if (agents is! Map) return const _ModelPreference();
    final defaults = agents['defaults'];
    if (defaults is! Map) return const _ModelPreference();
    final model = defaults['model'];
    if (model is! Map) return const _ModelPreference();
    final primaryRef = (model['primary'] as String?)?.trim() ?? '';
    final fallbackRefs =
        (model['fallbacks'] as List?)
            ?.whereType<String>()
            .map((item) => item.trim())
            .where((item) => item.isNotEmpty)
            .toList(growable: false) ??
        const <String>[];
    return _ModelPreference(primaryRef: primaryRef, fallbackRefs: fallbackRefs);
  }

  List<_ProjectConfigCandidate> _projectConfigCandidatesSync() {
    final cwd = Directory.current.path;
    return <_ProjectConfigCandidate>[
      _ProjectConfigCandidate(
        configPath: '$cwd/assistant/config.json',
        envPath: '$cwd/assistant/.env',
      ),
      _ProjectConfigCandidate(
        configPath: '$cwd/quwoquan_app/assistant/config.json',
        envPath: '$cwd/quwoquan_app/assistant/.env',
      ),
    ];
  }

  List<_ProjectConfigCandidate> _homeConfigCandidates(String home) {
    return <_ProjectConfigCandidate>[
      _ProjectConfigCandidate(
        configPath: '$home/.assistant/config.json',
        envPath: '$home/.assistant/.env',
      ),
      _ProjectConfigCandidate(
        configPath: '$home/.personal_assistant/config.json',
        envPath: '$home/.personal_assistant/.env',
      ),
    ];
  }

  String _resolveApiKey(String raw, Map<String, String> dotenv) {
    if (raw.isEmpty) return '';
    final envMatch = RegExp(r'^\$\{([A-Z0-9_]+)\}$').firstMatch(raw);
    if (envMatch == null) return raw;
    final envName = envMatch.group(1)!;
    final aliases = _envAliasesFor(envName);
    String fromDefines = '';
    for (final name in aliases) {
      fromDefines = _resolveFromDartDefines(name);
      if (fromDefines.isNotEmpty) break;
    }
    if (fromDefines.isNotEmpty) return fromDefines;
    for (final name in aliases) {
      final fromProcessEnv = (Platform.environment[name] ?? '').trim();
      if (fromProcessEnv.isNotEmpty) return fromProcessEnv;
    }
    for (final name in aliases) {
      final fromDotEnv = (dotenv[name] ?? '').trim();
      if (fromDotEnv.isNotEmpty) return fromDotEnv;
    }
    final fromMoltbotConfig = _resolveFromMoltbotConfig(envName);
    if (fromMoltbotConfig.isNotEmpty) return fromMoltbotConfig;
    return '';
  }

  List<String> _envAliasesFor(String envName) {
    if (envName == 'MIMO_API_KEY') {
      return const <String>['MIMO_API_KEY', 'PERSONAL_ASSISTANT_MIMO_API_KEY'];
    }
    if (envName == 'PERSONAL_ASSISTANT_MIMO_API_KEY') {
      return const <String>['PERSONAL_ASSISTANT_MIMO_API_KEY', 'MIMO_API_KEY'];
    }
    return <String>[envName];
  }

  Map<String, String> _readSharedDotEnvsSync() {
    final home = Platform.environment['HOME'] ?? '';
    if (home.trim().isEmpty) return const <String, String>{};
    return _mergeNonEmptyEnvMaps(<Map<String, String>>[
      _readDotEnvSync('$home/.moltbot/.env'),
      _readDotEnvSync('$home/.clawdbot/.env'),
    ]);
  }

  Map<String, String> _mergeNonEmptyEnvMaps(List<Map<String, String>> maps) {
    final merged = <String, String>{};
    for (final map in maps) {
      for (final entry in map.entries) {
        final key = entry.key.trim();
        final value = entry.value.trim();
        if (key.isEmpty || value.isEmpty) continue;
        merged[key] = value;
      }
    }
    return merged;
  }

  String _resolveFromMoltbotConfig(String envName) {
    if (envName != 'MIMO_API_KEY') return '';
    final home = Platform.environment['HOME'] ?? '';
    if (home.trim().isEmpty) return '';
    final candidates = <String>[
      '$home/.moltbot/moltbot.json',
      '$home/.moltbot/clawdbot.json',
      '$home/.moltbot/agents/main/agent/models.json',
      '$home/.clawdbot/moltbot.json',
      '$home/.clawdbot/clawdbot.json',
      '$home/.clawdbot/agents/main/agent/models.json',
    ];
    for (final path in candidates) {
      final file = File(path);
      if (!file.existsSync()) continue;
      try {
        final decoded = jsonDecode(file.readAsStringSync());
        if (decoded is! Map<String, dynamic>) continue;
        final fromSkills =
            ((decoded['skills'] as Map?)?['mimo'] as Map?)?['apiKey'];
        if (fromSkills is String) {
          final value = fromSkills.trim();
          if (value.isNotEmpty && !value.startsWith(r'${')) return value;
        }
        final fromProviders =
            (((decoded['models'] as Map?)?['providers'] as Map?)?['mimo']
                as Map?)?['apiKey'];
        if (fromProviders is String) {
          final value = fromProviders.trim();
          if (value.isNotEmpty && !value.startsWith(r'${')) return value;
        }
      } catch (_) {
        // ignore invalid config file
      }
    }
    return '';
  }

  List<AssistantModelRuntimeConfig> _loadMimoDefaultFallbackSync() {
    final sharedEnv = _readSharedDotEnvsSync();
    final mimoApiKey =
        (Platform.environment['MIMO_API_KEY'] ??
                Platform.environment['PERSONAL_ASSISTANT_MIMO_API_KEY'] ??
                sharedEnv['MIMO_API_KEY'] ??
                sharedEnv['PERSONAL_ASSISTANT_MIMO_API_KEY'] ??
                '')
            .trim();
    final resolvedApiKey = mimoApiKey.isNotEmpty
        ? mimoApiKey
        : _resolveFromMoltbotConfig('MIMO_API_KEY');
    if (resolvedApiKey.isEmpty) return const <AssistantModelRuntimeConfig>[];

    final baseUrl =
        (Platform.environment['PERSONAL_ASSISTANT_MIMO_BASE_URL'] ??
                Platform.environment['MIMO_BASE_URL'] ??
                sharedEnv['PERSONAL_ASSISTANT_MIMO_BASE_URL'] ??
                sharedEnv['MIMO_BASE_URL'] ??
                'https://api.xiaomimimo.com/v1')
            .trim();
    final modelId =
        (Platform.environment['PERSONAL_ASSISTANT_MIMO_MODEL_ID'] ??
                Platform.environment['MIMO_MODEL_ID'] ??
                sharedEnv['PERSONAL_ASSISTANT_MIMO_MODEL_ID'] ??
                sharedEnv['MIMO_MODEL_ID'] ??
                'mimo-v2-flash')
            .trim();
    if (baseUrl.isEmpty || modelId.isEmpty) {
      return const <AssistantModelRuntimeConfig>[];
    }
    return <AssistantModelRuntimeConfig>[
      AssistantModelRuntimeConfig(
        modelRef: 'mimo/$modelId',
        providerId: 'mimo',
        modelId: modelId,
        baseUrl: baseUrl,
        apiKey: resolvedApiKey,
      ),
    ];
  }

  Future<Map<String, String>> _readDotEnv(String path) async {
    final file = File(path);
    if (!await file.exists()) return const <String, String>{};
    final text = await file.readAsString();
    return _parseDotEnvContent(text);
  }

  Map<String, String> _readDotEnvSync(String path) {
    final file = File(path);
    if (!file.existsSync()) return const <String, String>{};
    final text = file.readAsStringSync();
    return _parseDotEnvContent(text);
  }

  Map<String, String> _parseDotEnvContent(String text) {
    final map = <String, String>{};
    for (final line in LineSplitter.split(text)) {
      final trimmed = line.trim();
      if (trimmed.isEmpty || trimmed.startsWith('#')) continue;
      final idx = trimmed.indexOf('=');
      if (idx <= 0) continue;
      final key = trimmed.substring(0, idx).trim();
      final value = trimmed.substring(idx + 1).trim();
      map[key] = value;
    }
    return map;
  }

  String _resolveFromDartDefines(String envName) {
    switch (envName) {
      case 'MIMO_API_KEY':
        return const String.fromEnvironment('MIMO_API_KEY');
      case 'PERSONAL_ASSISTANT_MIMO_API_KEY':
        return const String.fromEnvironment('PERSONAL_ASSISTANT_MIMO_API_KEY');
      case 'OPENAI_API_KEY':
        return const String.fromEnvironment('OPENAI_API_KEY');
      case 'PERSONAL_ASSISTANT_MODEL_API_KEY':
        return const String.fromEnvironment('PERSONAL_ASSISTANT_MODEL_API_KEY');
      default:
        return '';
    }
  }
}

class _ProjectConfigCandidate {
  const _ProjectConfigCandidate({
    required this.configPath,
    required this.envPath,
  });

  final String configPath;
  final String envPath;
}

class _ModelPreference {
  const _ModelPreference({
    this.primaryRef = '',
    this.fallbackRefs = const <String>[],
  });

  final String primaryRef;
  final List<String> fallbackRefs;
}
