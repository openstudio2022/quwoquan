// GENERATED FILE — DO NOT EDIT BY HAND.
// Source: tools/codegen_app_metadata/content_app_config_client_codegen.go
// Metadata: contracts/metadata/content/post/projections/content_app_config_client.yaml
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
    return ContentCanaryStageWireDto(
      stage: (map['stage'] ?? '').toString().trim(),
      rolloutPercent: (map['rolloutPercent'] as num?)?.toInt() ?? 0,
    );
  }
}

/// content.gray_release 客户端消费子集（snake_case / camelCase 别名）。
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
    final rawList =
        (m['canary_matrix'] as List?) ?? (m['canaryMatrix'] as List?) ?? const [];
    final stages = rawList
        .whereType<Map>()
        .map((e) => ContentCanaryStageWireDto.fromMap(Map<String, dynamic>.from(e)))
        .where((s) => s.stage.isNotEmpty)
        .toList(growable: false);
    return ContentGrayReleaseClientDto(
      experimentBucket: (m['experiment_bucket'] ?? m['experimentBucket'] ?? '')
          .toString()
          .trim(),
      currentStage:
          (m['current_stage'] ?? m['currentStage'] ?? '').toString().trim(),
      canaryMatrix: stages,
    );
  }
}

/// 自根响应 Map 解析根键 content：feature_flags、gray_release、client_state_sync。
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
    final content = (root['content'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final rawFlags = (content['feature_flags'] as Map?)?.cast<String, dynamic>() ??
        (content['featureFlags'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final overrides = <String, bool>{};
    for (final e in rawFlags.entries) {
      if (e.value is bool) {
        overrides[e.key] = e.value as bool;
      }
    }
    final grayRaw = (content['gray_release'] as Map?)?.cast<String, dynamic>() ??
        (content['grayRelease'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final gray = ContentGrayReleaseClientDto.fromMap(grayRaw);
    final syncRaw =
        (content['client_state_sync'] as Map?)?.cast<String, dynamic>() ??
            (content['clientStateSync'] as Map?)?.cast<String, dynamic>() ??
            const <String, dynamic>{};
    return ContentAppConfigClientParsed._(
      featureFlagOverrides: overrides,
      grayRelease: gray,
      clientStateSyncMap: syncRaw,
    );
  }
}
