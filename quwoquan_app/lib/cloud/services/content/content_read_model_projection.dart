import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/services/content/feed_item_discovery_wire_map.dart';

/// Projects the metadata-owned service read model into the App's public post
/// DTO. Field ownership stays in codegen; fixture consumers must not duplicate
/// service and client aliases in the same JSON row.
PostBaseDto contentPostDtoFromReadModelMap(Map<String, dynamic> source) {
  return postBaseDtoFromMap(contentPostWireFromReadModelMap(source));
}

/// Projects a service read-model row into the JSON-safe public post wire.
///
/// `FeedItemDto.toMap()` deliberately retains typed [DateTime] values. HTTP
/// fixtures and detail payloads require the canonical wire serializer so their
/// timestamps remain RFC3339 strings.
Map<String, dynamic> contentPostWireFromReadModelMap(
  Map<String, dynamic> source,
) {
  final wire = FeedItemDto.fromReadModelMap(source).toDiscoveryWireMap();
  for (final field in const ['createdAt', 'updatedAt', 'publishedAt']) {
    final sourceValue = source[field];
    if (sourceValue is String && sourceValue.trim().isNotEmpty) {
      wire[field] = sourceValue;
    }
  }
  return wire;
}
