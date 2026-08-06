import 'dart:convert';

/// Allocates a deterministic, collision-free identity for every video episode
/// inside one Work Browser post.
///
/// Public delivery URLs are cache identities, not series-item identities: two
/// episode rows may intentionally reference the same asset. Canonical
/// mediaAssetId/version stays stable across reorder; the occurrence ordinal is
/// only used to disambiguate duplicate contract rows.
final class WorksVideoEpisodeIdentityAllocator {
  WorksVideoEpisodeIdentityAllocator(String postId)
    : _postId = _requireValue(postId, 'postId');

  final String _postId;
  final Map<String, int> _occurrencesByBase = <String, int>{};

  String allocate({
    required String deliveryCacheIdentity,
    String? mediaAssetId,
    int? mediaAssetVersion,
  }) {
    final normalizedAssetId = mediaAssetId?.trim() ?? '';
    final normalizedDelivery = _requireValue(
      deliveryCacheIdentity,
      'deliveryCacheIdentity',
    );
    final base = normalizedAssetId.isNotEmpty && (mediaAssetVersion ?? 0) > 0
        ? <Object>['asset', _postId, normalizedAssetId, mediaAssetVersion!]
        : <Object>['delivery', _postId, normalizedDelivery];
    final baseIdentity = jsonEncode(base);
    final occurrence = _occurrencesByBase.update(
      baseIdentity,
      (value) => value + 1,
      ifAbsent: () => 0,
    );
    return jsonEncode(<Object>[...base, occurrence]);
  }

  static String _requireValue(String value, String name) {
    final normalized = value.trim();
    if (normalized.isEmpty) {
      throw ArgumentError.value(value, name, 'must not be empty');
    }
    return normalized;
  }
}
