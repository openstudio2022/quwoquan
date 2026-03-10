class SkillExecutionShell {
  const SkillExecutionShell({
    this.problemClass = 'general',
    this.maxIterations = 6,
    this.toolBudget = 12,
    this.variantBudget = 2,
    this.reflectionBudget = 2,
    this.providerPolicy = 'model_choice',
    this.preferredProviders = const <String>[],
    this.authorityDomains = const <String>[],
    this.freshnessHoursMax = 72,
  });

  final String problemClass;
  final int maxIterations;
  final int toolBudget;
  final int variantBudget;
  final int reflectionBudget;
  final String providerPolicy;
  final List<String> preferredProviders;
  final List<String> authorityDomains;
  final int freshnessHoursMax;

  SkillExecutionShell copyWith({
    String? problemClass,
    int? maxIterations,
    int? toolBudget,
    int? variantBudget,
    int? reflectionBudget,
    String? providerPolicy,
    List<String>? preferredProviders,
    List<String>? authorityDomains,
    int? freshnessHoursMax,
  }) {
    return SkillExecutionShell(
      problemClass: problemClass ?? this.problemClass,
      maxIterations: maxIterations ?? this.maxIterations,
      toolBudget: toolBudget ?? this.toolBudget,
      variantBudget: variantBudget ?? this.variantBudget,
      reflectionBudget: reflectionBudget ?? this.reflectionBudget,
      providerPolicy: providerPolicy ?? this.providerPolicy,
      preferredProviders: preferredProviders ?? this.preferredProviders,
      authorityDomains: authorityDomains ?? this.authorityDomains,
      freshnessHoursMax: freshnessHoursMax ?? this.freshnessHoursMax,
    );
  }

  factory SkillExecutionShell.fromMap(
    Map<String, dynamic> map, {
    required Map<String, dynamic> frontmatter,
    required String domainId,
  }) {
    final shellMap =
        (map['execution_shell'] as Map?)?.cast<String, dynamic>() ??
        (frontmatter['execution_shell'] as Map?)?.cast<String, dynamic>() ??
        (map['executionShell'] as Map?)?.cast<String, dynamic>() ??
        (frontmatter['executionShell'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final searchPolicy =
        (frontmatter['searchPolicy'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final mode = (frontmatter['mode'] as String?)?.trim() ?? '';
    final derivedProblemClass =
        (frontmatter['problem_class'] as String?)?.trim().isNotEmpty == true
        ? (frontmatter['problem_class'] as String).trim()
        : _deriveProblemClass(domainId: domainId, mode: mode);
    final defaultVariantBudget = derivedProblemClass == 'realtime_info'
        ? 0
        : (mode == 'task' ? 0 : 2);
    final defaultReflectionBudget = derivedProblemClass == 'realtime_info'
        ? 0
        : ((searchPolicy['maxReflection'] as num?)?.toInt() ?? 2);
    final defaultProviderPolicy = derivedProblemClass == 'realtime_info'
        ? 'authority_first'
        : 'model_choice';
    final defaultFreshnessHours = derivedProblemClass == 'realtime_info'
        ? 1
        : 72;
    final defaultAuthorityDomains = derivedProblemClass == 'realtime_info'
        ? const <String>['weather.com.cn', 'cma.cn']
        : const <String>[];
    final defaultPreferredProviders = derivedProblemClass == 'realtime_info'
        ? const <String>['web']
        : const <String>[];
    return SkillExecutionShell(
      problemClass:
          (shellMap['problemClass'] as String?)?.trim().isNotEmpty == true
          ? (shellMap['problemClass'] as String).trim()
          : derivedProblemClass,
      maxIterations: _positiveInt(
        shellMap['maxIterations'],
        fallback: derivedProblemClass == 'realtime_info' ? 2 : 6,
      ),
      toolBudget: _positiveInt(
        shellMap['toolBudget'],
        fallback: derivedProblemClass == 'realtime_info' ? 1 : 12,
      ),
      variantBudget: _nonNegativeInt(
        shellMap['variantBudget'],
        fallback: defaultVariantBudget,
      ),
      reflectionBudget: _nonNegativeInt(
        shellMap['reflectionBudget'],
        fallback: defaultReflectionBudget,
      ),
      providerPolicy:
          (shellMap['providerPolicy'] as String?)?.trim().isNotEmpty == true
          ? (shellMap['providerPolicy'] as String).trim()
          : defaultProviderPolicy,
      preferredProviders: _stringList(
        shellMap['preferredProviders'],
        fallback: defaultPreferredProviders,
      ),
      authorityDomains: _stringList(
        shellMap['authorityDomains'],
        fallback: defaultAuthorityDomains,
      ),
      freshnessHoursMax: _positiveInt(
        shellMap['freshnessHoursMax'],
        fallback: defaultFreshnessHours,
      ),
    );
  }

  Map<String, dynamic> toJson() => <String, dynamic>{
    'problemClass': problemClass,
    'maxIterations': maxIterations,
    'toolBudget': toolBudget,
    'variantBudget': variantBudget,
    'reflectionBudget': reflectionBudget,
    'providerPolicy': providerPolicy,
    'preferredProviders': preferredProviders,
    'authorityDomains': authorityDomains,
    'freshnessHoursMax': freshnessHoursMax,
  };

  static String _deriveProblemClass({
    required String domainId,
    required String mode,
  }) {
    if (domainId.trim() == 'weather') return 'realtime_info';
    if (mode.trim() == 'task') return 'task_execution';
    if (mode.trim() == 'hybrid') return 'complex_reasoning';
    return 'simple_qa';
  }

  static int _positiveInt(Object? value, {required int fallback}) {
    if (value is num && value.toInt() > 0) return value.toInt();
    final parsed = int.tryParse(value?.toString() ?? '');
    if (parsed != null && parsed > 0) return parsed;
    return fallback;
  }

  static int _nonNegativeInt(Object? value, {required int fallback}) {
    if (value is num && value.toInt() >= 0) return value.toInt();
    final parsed = int.tryParse(value?.toString() ?? '');
    if (parsed != null && parsed >= 0) return parsed;
    return fallback;
  }

  static List<String> _stringList(
    Object? value, {
    required List<String> fallback,
  }) {
    if (value is List) {
      return value
          .map((item) => item.toString().trim())
          .where((item) => item.isNotEmpty)
          .toList(growable: false);
    }
    if (value is String && value.trim().isNotEmpty) {
      return value
          .split(RegExp(r'[\s,]+'))
          .map((item) => item.trim())
          .where((item) => item.isNotEmpty)
          .toList(growable: false);
    }
    return fallback;
  }
}

class PersonalAssistantSkillManifest {
  const PersonalAssistantSkillManifest({
    required this.id,
    required this.name,
    required this.description,
    required this.version,
    required this.executionTarget,
    required this.parametersSchema,
    this.permissions = const <String>[],
    this.visibility = 'app_only',
    this.category = 'general',
    this.tier = 'free',
    this.channelScopes = const <String>['app'],
    this.deviceScopes = const <String>['mobile', 'tablet', 'pc'],
    this.versionPolicy = 'semver',
    this.permissionScopes = const <String>[],
    this.defaultEnabled = false,
    this.allowedTools = const <String>[],
    this.triggerKeywords = const <String>[],
    this.domainId = '',
    this.skillInstructionMarkdown = '',
    this.frontmatter = const <String, dynamic>{},
    this.executionShell = const SkillExecutionShell(),
  });

  final String id;
  final String name;
  final String description;
  final String version;
  final String executionTarget;
  final Map<String, dynamic> parametersSchema;
  final List<String> permissions;
  final String visibility;
  final String category;
  final String tier;
  final List<String> channelScopes;
  final List<String> deviceScopes;
  final String versionPolicy;
  final List<String> permissionScopes;
  final bool defaultEnabled;
  final List<String> allowedTools;
  final List<String> triggerKeywords;
  final String domainId;
  final String skillInstructionMarkdown;
  final Map<String, dynamic> frontmatter;
  final SkillExecutionShell executionShell;

  factory PersonalAssistantSkillManifest.fromMap(Map<String, dynamic> map) {
    final frontmatter = Map<String, dynamic>.from(
      map['frontmatter'] as Map? ?? const <String, dynamic>{},
    );
    final domainId =
        (map['domainId'] as String?)?.trim() ??
        (map['domain'] as String?)?.trim() ??
        '';
    return PersonalAssistantSkillManifest(
      id: (map['id'] as String?)?.trim() ?? '',
      name: (map['name'] as String?)?.trim() ?? '',
      description: (map['description'] as String?)?.trim() ?? '',
      version: (map['version'] as String?)?.trim() ?? '1.0.0',
      executionTarget:
          (map['executionTarget'] as String?)?.trim() ?? 'tool_chain',
      parametersSchema: Map<String, dynamic>.from(
        map['parametersSchema'] as Map? ?? const <String, dynamic>{},
      ),
      permissions:
          (map['permissions'] as List?)
              ?.map((e) => e.toString())
              .toList(growable: false) ??
          const <String>[],
      visibility: (map['visibility'] as String?)?.trim() ?? 'app_only',
      category: (map['category'] as String?)?.trim() ?? 'general',
      tier: (map['tier'] as String?)?.trim() ?? 'free',
      channelScopes:
          (map['channelScopes'] as List?)
              ?.map((e) => e.toString())
              .toList(growable: false) ??
          const <String>['app'],
      deviceScopes:
          (map['deviceScopes'] as List?)
              ?.map((e) => e.toString())
              .toList(growable: false) ??
          const <String>['mobile', 'tablet', 'pc'],
      versionPolicy: (map['versionPolicy'] as String?)?.trim() ?? 'semver',
      permissionScopes:
          (map['permissionScopes'] as List?)
              ?.map((e) => e.toString())
              .toList(growable: false) ??
          const <String>[],
      defaultEnabled: map['defaultEnabled'] == true,
      allowedTools:
          (map['allowedTools'] as List?)
              ?.map((e) => e.toString())
              .toList(growable: false) ??
          (map['allowed_tools'] as List?)
              ?.map((e) => e.toString())
              .toList(growable: false) ??
          const <String>[],
      triggerKeywords:
          (map['triggerKeywords'] as List?)
              ?.map((e) => e.toString())
              .toList(growable: false) ??
          (map['trigger_keywords'] as List?)
              ?.map((e) => e.toString())
              .toList(growable: false) ??
          const <String>[],
      domainId: domainId,
      skillInstructionMarkdown:
          (map['skillInstructionMarkdown'] as String?)?.trim() ??
          (map['skill_markdown'] as String?)?.trim() ??
          '',
      frontmatter: frontmatter,
      executionShell: SkillExecutionShell.fromMap(
        map,
        frontmatter: frontmatter,
        domainId: domainId,
      ),
    );
  }

  List<String> validate() {
    final errors = <String>[];
    if (id.trim().isEmpty) errors.add('id is required');
    if (name.trim().isEmpty) errors.add('name is required');
    if (description.trim().isEmpty) errors.add('description is required');
    if (version.trim().isEmpty) errors.add('version is required');
    const allowedTargets = <String>{
      'ios_intent',
      'android_intent',
      'native_api',
      'tool_chain',
    };
    if (!allowedTargets.contains(executionTarget)) {
      errors.add('executionTarget is invalid: $executionTarget');
    }
    final paramType = parametersSchema['type'];
    if (paramType != null && paramType != 'object') {
      errors.add('parametersSchema.type must be object');
    }
    if (tier != 'free' && tier != 'pro') {
      errors.add('tier must be free/pro');
    }
    return errors;
  }
}

class PersonalAssistantSkillInfo {
  const PersonalAssistantSkillInfo({
    required this.manifest,
    required this.enabled,
    required this.source,
    required this.version,
    required this.category,
    required this.tier,
    required this.isDefaultFree,
  });

  final PersonalAssistantSkillManifest manifest;
  final bool enabled;
  final String source;
  final String version;
  final String category;
  final String tier;
  final bool isDefaultFree;
}
