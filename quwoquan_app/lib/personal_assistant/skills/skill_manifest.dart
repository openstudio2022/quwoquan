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

  factory PersonalAssistantSkillManifest.fromMap(Map<String, dynamic> map) {
    return PersonalAssistantSkillManifest(
      id: (map['id'] as String?)?.trim() ?? '',
      name: (map['name'] as String?)?.trim() ?? '',
      description: (map['description'] as String?)?.trim() ?? '',
      version: (map['version'] as String?)?.trim() ?? '1.0.0',
      executionTarget: (map['executionTarget'] as String?)?.trim() ?? 'tool_chain',
      parametersSchema: Map<String, dynamic>.from(
        map['parametersSchema'] as Map? ?? const <String, dynamic>{},
      ),
      permissions: (map['permissions'] as List?)
              ?.map((e) => e.toString())
              .toList(growable: false) ??
          const <String>[],
      visibility: (map['visibility'] as String?)?.trim() ?? 'app_only',
      category: (map['category'] as String?)?.trim() ?? 'general',
      tier: (map['tier'] as String?)?.trim() ?? 'free',
      channelScopes: (map['channelScopes'] as List?)
              ?.map((e) => e.toString())
              .toList(growable: false) ??
          const <String>['app'],
      deviceScopes: (map['deviceScopes'] as List?)
              ?.map((e) => e.toString())
              .toList(growable: false) ??
          const <String>['mobile', 'tablet', 'pc'],
      versionPolicy: (map['versionPolicy'] as String?)?.trim() ?? 'semver',
      permissionScopes: (map['permissionScopes'] as List?)
              ?.map((e) => e.toString())
              .toList(growable: false) ??
          const <String>[],
      defaultEnabled: map['defaultEnabled'] == true,
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
