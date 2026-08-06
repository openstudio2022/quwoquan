import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Adapter-owned deterministic idempotency key derivation for behavior facts.
///
/// The canonical payload is encoded with its insertion order, matching the
/// durable queue and request encoder's existing single-track representation.
String deriveContentBehaviorClientEventId(
  Map<String, dynamic> canonicalPayload,
) =>
    'evt_${sha256.convert(utf8.encode(jsonEncode(canonicalPayload))).toString()}';

extension ContentBehaviorEventAdapterCodec on BehaviorEvent {
  Map<String, dynamic> toDurableStorageJson() =>
      toStorageJson(deriveClientEventId: deriveContentBehaviorClientEventId);

  ContentBehaviorEventWire toRequestWire() =>
      toWire(deriveClientEventId: deriveContentBehaviorClientEventId);
}
