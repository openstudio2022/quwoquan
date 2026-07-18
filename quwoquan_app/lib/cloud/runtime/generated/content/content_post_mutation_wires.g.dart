// GENERATED FILE — DO NOT EDIT BY HAND.
// Source: contracts/metadata/content/post/service.yaml (writable_fields per operation).
// Regenerate: make codegen-app

import 'package:quwoquan_app/cloud/runtime/codec/cloud_wire_json_types.dart';

CloudJsonMap _mutationPutOpt(CloudJsonMap m, String k, Object? v) {
  if (v == null) return m;
  m[k] = v;
  return m;
}

CloudJsonMap? _mutationStringKeyedMap(Object? v) {
  if (v is! Map) return null;
  return Map<String, dynamic>.from(v);
}

List<CloudJsonMap>? _mutationMapList(Object? v) {
  if (v is! List) return null;
  return v
      .whereType<Map>()
      .map((e) => Map<String, dynamic>.from(e))
      .toList(growable: false);
}

/// HTTP body for UpdatePostSettings (metadata writable_fields).
class UpdatePostSettingsRequestWire {
  UpdatePostSettingsRequestWire({
    this.visibility,
    this.primaryHomepageId,
    this.primaryHomepageType,
    this.primaryHomepageSnapshot,
    this.assistantUsePolicy,
  });

  final String? visibility;
  final String? primaryHomepageId;
  final String? primaryHomepageType;
  final CloudJsonMap? primaryHomepageSnapshot;
  final String? assistantUsePolicy;

  CloudJsonMap toWire() {
    final m = <String, dynamic>{};
    _mutationPutOpt(m, 'visibility', visibility);
    _mutationPutOpt(m, 'primaryHomepageId', primaryHomepageId);
    _mutationPutOpt(m, 'primaryHomepageType', primaryHomepageType);
    if (primaryHomepageSnapshot != null) m['primaryHomepageSnapshot'] = primaryHomepageSnapshot!;
    _mutationPutOpt(m, 'assistantUsePolicy', assistantUsePolicy);
    return m;
  }

  factory UpdatePostSettingsRequestWire.fromMap(CloudJsonMap m) {
    return UpdatePostSettingsRequestWire(
      visibility: m['visibility']?.toString(),
      primaryHomepageId: m['primaryHomepageId']?.toString(),
      primaryHomepageType: m['primaryHomepageType']?.toString(),
      primaryHomepageSnapshot: _mutationStringKeyedMap(m['primaryHomepageSnapshot']),
      assistantUsePolicy: m['assistantUsePolicy']?.toString(),
    );
  }
}

/// HTTP body for PromotePostToWork (metadata writable_fields).
class PromotePostToWorkRequestWire {
  PromotePostToWorkRequestWire({
    this.contentType,
    this.title,
    this.summary,
    this.semanticMentions,
    this.coverUrl,
    this.articleMarkdown,
    this.markdownDialect,
    this.articleAssetManifest,
    this.articleRenderProfile,
    this.primaryHomepageId,
    this.primaryHomepageType,
    this.primaryHomepageSnapshot,
    this.visibility,
    this.assistantUsePolicy,
  });

  final String? contentType;
  final String? title;
  final String? summary;
  final List<CloudJsonMap>? semanticMentions;
  final String? coverUrl;
  final String? articleMarkdown;
  final String? markdownDialect;
  final CloudJsonMap? articleAssetManifest;
  final CloudJsonMap? articleRenderProfile;
  final String? primaryHomepageId;
  final String? primaryHomepageType;
  final CloudJsonMap? primaryHomepageSnapshot;
  final String? visibility;
  final String? assistantUsePolicy;

  CloudJsonMap toWire() {
    final m = <String, dynamic>{};
    _mutationPutOpt(m, 'contentType', contentType);
    _mutationPutOpt(m, 'title', title);
    _mutationPutOpt(m, 'summary', summary);
    if (semanticMentions != null) m['semanticMentions'] = semanticMentions!;
    _mutationPutOpt(m, 'coverUrl', coverUrl);
    _mutationPutOpt(m, 'articleMarkdown', articleMarkdown);
    _mutationPutOpt(m, 'markdownDialect', markdownDialect);
    if (articleAssetManifest != null) m['articleAssetManifest'] = articleAssetManifest!;
    if (articleRenderProfile != null) m['articleRenderProfile'] = articleRenderProfile!;
    _mutationPutOpt(m, 'primaryHomepageId', primaryHomepageId);
    _mutationPutOpt(m, 'primaryHomepageType', primaryHomepageType);
    if (primaryHomepageSnapshot != null) m['primaryHomepageSnapshot'] = primaryHomepageSnapshot!;
    _mutationPutOpt(m, 'visibility', visibility);
    _mutationPutOpt(m, 'assistantUsePolicy', assistantUsePolicy);
    return m;
  }

  factory PromotePostToWorkRequestWire.fromMap(CloudJsonMap m) {
    return PromotePostToWorkRequestWire(
      contentType: m['contentType']?.toString(),
      title: m['title']?.toString(),
      summary: m['summary']?.toString(),
      semanticMentions: _mutationMapList(m['semanticMentions']),
      coverUrl: m['coverUrl']?.toString(),
      articleMarkdown: m['articleMarkdown']?.toString(),
      markdownDialect: m['markdownDialect']?.toString(),
      articleAssetManifest: _mutationStringKeyedMap(m['articleAssetManifest']),
      articleRenderProfile: _mutationStringKeyedMap(m['articleRenderProfile']),
      primaryHomepageId: m['primaryHomepageId']?.toString(),
      primaryHomepageType: m['primaryHomepageType']?.toString(),
      primaryHomepageSnapshot: _mutationStringKeyedMap(m['primaryHomepageSnapshot']),
      visibility: m['visibility']?.toString(),
      assistantUsePolicy: m['assistantUsePolicy']?.toString(),
    );
  }
}

