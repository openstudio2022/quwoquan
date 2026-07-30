// GENERATED FILE — DO NOT EDIT BY HAND.
// Source: tools/codegen_app_metadata/content_app_config_client_codegen.go
// Metadata: services/content-service/contracts/content/post/projections/content_app_config_client.yaml
// Regenerate: make codegen-app (from quwoquan_service)

/// 灰度阶段矩阵中的单行（wire 与 [ContentCanaryStage] 字段对齐）。
class ContentCanaryStageWireDto {
  const ContentCanaryStageWireDto({
    required this.stage,
    required this.rolloutPercent,
  });

  final String stage;
  final int rolloutPercent;

  factory ContentCanaryStageWireDto.fromMap(Map<String, dynamic> map) {
    final stage = map['stage'];
    final rolloutPercent = map['rolloutPercent'];
    if (stage is! String || stage.isEmpty || stage != stage.trim()) {
      throw const FormatException('invalid gray_release stage');
    }
    if (rolloutPercent is! int ||
        rolloutPercent < 0 ||
        rolloutPercent > 100) {
      throw const FormatException('invalid gray_release rolloutPercent');
    }
    return ContentCanaryStageWireDto(
      stage: stage,
      rolloutPercent: rolloutPercent,
    );
  }
}

/// content.gray_release 客户端消费子集（snake_case only）。
class ContentGrayReleaseClientDto {
  const ContentGrayReleaseClientDto({
    required this.experimentBucket,
    required this.currentStage,
    required this.canaryMatrix,
  });

  final String experimentBucket;
  final String currentStage;
  final List<ContentCanaryStageWireDto> canaryMatrix;

  factory ContentGrayReleaseClientDto.fromMap(Map<String, dynamic> m) {
    final rawList = m['canary_matrix'];
    if (rawList != null && rawList is! List) {
      throw const FormatException('invalid gray_release canary_matrix');
    }
    final stages = <ContentCanaryStageWireDto>[];
    for (final row in (rawList as List?) ?? const <Object?>[]) {
      stages.add(
        ContentCanaryStageWireDto.fromMap(
          _exactStringKeyMap(row, 'gray_release canary row'),
        ),
      );
    }
    return ContentGrayReleaseClientDto(
      experimentBucket: _optionalExactString(m, 'experiment_bucket'),
      currentStage: _optionalExactString(m, 'current_stage'),
      canaryMatrix: stages,
    );
  }
}

/// 自根响应 Map 解析根键 content：feature_flags、gray_release、client_state_sync（snake_case only）。
class ContentAppConfigClientParsed {
  ContentAppConfigClientParsed._({
    required this.featureFlagOverrides,
    required this.grayRelease,
    required this.clientStateSyncMap,
  });

  /// 远端为 bool 的 feature flag 条目，用于与本地 fallback 合并。
  final Map<String, bool> featureFlagOverrides;
  final ContentGrayReleaseClientDto grayRelease;
  final Map<String, dynamic> clientStateSyncMap;

  factory ContentAppConfigClientParsed.fromRootMap(Map<String, dynamic> root) {
    final content = _optionalExactMap(root, 'content');
    final rawFlags = _optionalExactMap(content, 'feature_flags');
    final overrides = <String, bool>{};
    for (final e in rawFlags.entries) {
      if (e.value is! bool) {
        throw const FormatException('invalid feature_flags value');
      }
      overrides[e.key] = e.value as bool;
    }
    final grayRaw = _optionalExactMap(content, 'gray_release');
    final gray = ContentGrayReleaseClientDto.fromMap(grayRaw);
    final syncRaw = _optionalExactMap(content, 'client_state_sync');
    return ContentAppConfigClientParsed._(
      featureFlagOverrides: overrides,
      grayRelease: gray,
      clientStateSyncMap: syncRaw,
    );
  }
}

Map<String, dynamic> _optionalExactMap(
  Map<String, dynamic> parent,
  String key,
) {
  final value = parent[key];
  if (value == null) return const <String, dynamic>{};
  return _exactStringKeyMap(value, key);
}

Map<String, dynamic> _exactStringKeyMap(Object? value, String label) {
  if (value is! Map || value.keys.any((key) => key is! String)) {
    throw FormatException('invalid $label');
  }
  return <String, dynamic>{
    for (final entry in value.entries) entry.key as String: entry.value,
  };
}

String _optionalExactString(Map<String, dynamic> parent, String key) {
  final value = parent[key];
  if (value == null) return '';
  if (value is! String || value != value.trim()) {
    throw FormatException('invalid $key');
  }
  return value;
}
