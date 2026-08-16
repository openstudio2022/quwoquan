// Code generated from canonical content MediaAsset preview-track schema. DO NOT EDIT.
// ContractGraph SHA256: 134a2a79a9c728aba04fd6623968f89f6227d1b011e10ef29e7e3b43159e283d

library;

enum PreviewTrackAccessPolicy {
  ownerOnly("owner_only"),
  referencedPost("referenced_post"),
  public("public");

  const PreviewTrackAccessPolicy(this.wireName);

  final String wireName;

  static PreviewTrackAccessPolicy fromWire(Object? value, String path) {
    return switch (value) {
      "owner_only" => PreviewTrackAccessPolicy.ownerOnly,
      "referenced_post" => PreviewTrackAccessPolicy.referencedPost,
      "public" => PreviewTrackAccessPolicy.public,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum PreviewTrackSpriteMimeType {
  imageWebp("image/webp"),
  imageJpeg("image/jpeg");

  const PreviewTrackSpriteMimeType(this.wireName);

  final String wireName;

  static PreviewTrackSpriteMimeType fromWire(Object? value, String path) {
    return switch (value) {
      "image/webp" => PreviewTrackSpriteMimeType.imageWebp,
      "image/jpeg" => PreviewTrackSpriteMimeType.imageJpeg,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

final class PreviewTrackManifestWire {
  const PreviewTrackManifestWire({
    required this.schema,
    required this.assetId,
    required this.assetVersion,
    required this.trackVersion,
    required this.processorProfile,
    required this.accessPolicy,
    required this.frameIntervalMs,
    required this.sprites,
    required this.frames,
  });

  final String schema;
  final String assetId;
  final int assetVersion;
  final int trackVersion;
  final String processorProfile;
  final PreviewTrackAccessPolicy accessPolicy;
  final int frameIntervalMs;
  final List<PreviewTrackSpriteWire> sprites;
  final List<PreviewTrackFrameWire> frames;

  factory PreviewTrackManifestWire.fromWire(Object? value, [String path = "PreviewTrackManifestWire"]) {
    final map = _previewRequiredObject(value, path);
    _previewRejectUnknownFields(map, const <String>{"schema", "assetId", "assetVersion", "trackVersion", "processorProfile", "accessPolicy", "frameIntervalMs", "sprites", "frames"}, path);
    return PreviewTrackManifestWire(
      schema: _previewRequiredConstString(map["schema"], '$path.schema', "quwoquan.content.preview_track_manifest"),
      assetId: _previewRequiredString(map["assetId"], '$path.assetId', minLength: 1),
      assetVersion: _previewRequiredInt(map["assetVersion"], '$path.assetVersion', min: 1),
      trackVersion: _previewRequiredInt(map["trackVersion"], '$path.trackVersion', min: 1),
      processorProfile: _previewRequiredString(map["processorProfile"], '$path.processorProfile', minLength: 1),
      accessPolicy: PreviewTrackAccessPolicy.fromWire(map["accessPolicy"], '$path.accessPolicy'),
      frameIntervalMs: _previewRequiredInt(map["frameIntervalMs"], '$path.frameIntervalMs', min: 1000, max: 30000),
      sprites: List<PreviewTrackSpriteWire>.unmodifiable(_previewRequiredList(map["sprites"], '$path.sprites', minItems: 1, maxItems: 64).asMap().entries.map((entry) => PreviewTrackSpriteWire.fromWire(entry.value, '$path.sprites' + '[${entry.key}]'))),
      frames: List<PreviewTrackFrameWire>.unmodifiable(_previewRequiredList(map["frames"], '$path.frames', minItems: 1, maxItems: 1000).asMap().entries.map((entry) => PreviewTrackFrameWire.fromWire(entry.value, '$path.frames' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "schema": schema,
    "assetId": assetId,
    "assetVersion": assetVersion,
    "trackVersion": trackVersion,
    "processorProfile": processorProfile,
    "accessPolicy": accessPolicy.wireName,
    "frameIntervalMs": frameIntervalMs,
    "sprites": sprites.map((entry) => entry.toWire()).toList(growable: false),
    "frames": frames.map((entry) => entry.toWire()).toList(growable: false),
  };
}

final class PreviewTrackFrameWire {
  const PreviewTrackFrameWire({
    required this.timeMs,
    required this.spriteId,
    required this.x,
    required this.y,
    required this.width,
    required this.height,
  });

  final int timeMs;
  final String spriteId;
  final int x;
  final int y;
  final int width;
  final int height;

  factory PreviewTrackFrameWire.fromWire(Object? value, [String path = "PreviewTrackFrameWire"]) {
    final map = _previewRequiredObject(value, path);
    _previewRejectUnknownFields(map, const <String>{"timeMs", "spriteId", "x", "y", "width", "height"}, path);
    return PreviewTrackFrameWire(
      timeMs: _previewRequiredInt(map["timeMs"], '$path.timeMs', min: 0, max: 3600000),
      spriteId: _previewRequiredString(map["spriteId"], '$path.spriteId', minLength: 1),
      x: _previewRequiredInt(map["x"], '$path.x', min: 0),
      y: _previewRequiredInt(map["y"], '$path.y', min: 0),
      width: _previewRequiredInt(map["width"], '$path.width', min: 1, max: 1920),
      height: _previewRequiredInt(map["height"], '$path.height', min: 1, max: 1080),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "timeMs": timeMs,
    "spriteId": spriteId,
    "x": x,
    "y": y,
    "width": width,
    "height": height,
  };
}

final class PreviewTrackSpriteWire {
  const PreviewTrackSpriteWire({
    required this.spriteId,
    required this.publicSliceKey,
    required this.mimeType,
    required this.sha256,
    required this.width,
    required this.height,
  });

  final String spriteId;
  final String publicSliceKey;
  final PreviewTrackSpriteMimeType mimeType;
  final String sha256;
  final int width;
  final int height;

  factory PreviewTrackSpriteWire.fromWire(Object? value, [String path = "PreviewTrackSpriteWire"]) {
    final map = _previewRequiredObject(value, path);
    _previewRejectUnknownFields(map, const <String>{"spriteId", "publicSliceKey", "mimeType", "sha256", "width", "height"}, path);
    return PreviewTrackSpriteWire(
      spriteId: _previewRequiredString(map["spriteId"], '$path.spriteId', minLength: 1),
      publicSliceKey: _previewRequiredString(map["publicSliceKey"], '$path.publicSliceKey', pattern: "^media/video/s/"),
      mimeType: PreviewTrackSpriteMimeType.fromWire(map["mimeType"], '$path.mimeType'),
      sha256: _previewRequiredString(map["sha256"], '$path.sha256', pattern: "^sha256:[0-9a-f]{64}\$"),
      width: _previewRequiredInt(map["width"], '$path.width', min: 1, max: 8192),
      height: _previewRequiredInt(map["height"], '$path.height', min: 1, max: 8192),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "spriteId": spriteId,
    "publicSliceKey": publicSliceKey,
    "mimeType": mimeType.wireName,
    "sha256": sha256,
    "width": width,
    "height": height,
  };
}


Map<String, Object?> _previewRequiredObject(Object? value, String path) {
  if (value is! Map) {
    throw FormatException('$path must be an object');
  }
  return value.map((key, child) {
    if (key is! String) {
      throw FormatException('$path contains a non-string key');
    }
    return MapEntry(key, child);
  });
}

List<Object?> _previewRequiredList(
  Object? value,
  String path, {
  int? minItems,
  int? maxItems,
}) {
  if (value is! List) {
    throw FormatException('$path must be an array');
  }
  if (minItems != null && value.length < minItems) {
    throw FormatException('$path has fewer than $minItems items');
  }
  if (maxItems != null && value.length > maxItems) {
    throw FormatException('$path has more than $maxItems items');
  }
  return List<Object?>.unmodifiable(value);
}

String _previewRequiredString(
  Object? value,
  String path, {
  int? minLength,
  String? pattern,
}) {
  if (value is! String ||
      (minLength != null && value.length < minLength) ||
      (pattern != null && !RegExp(pattern).hasMatch(value))) {
    throw FormatException('$path has an invalid string value');
  }
  return value;
}

String _previewRequiredConstString(
  Object? value,
  String path,
  String expected,
) {
  final decoded = _previewRequiredString(value, path);
  if (decoded != expected) {
    throw FormatException('$path does not match the canonical schema identity');
  }
  return decoded;
}

int _previewRequiredInt(
  Object? value,
  String path, {
  int? min,
  int? max,
}) {
  if (value is! num || value.isNaN || value.isInfinite) {
    throw FormatException('$path must be an integer');
  }
  final decoded = value.toInt();
  if (decoded.toDouble() != value.toDouble() ||
      (min != null && decoded < min) ||
      (max != null && decoded > max)) {
    throw FormatException('$path has an invalid integer value');
  }
  return decoded;
}

void _previewRejectUnknownFields(
  Map<String, Object?> map,
  Set<String> allowed,
  String path,
) {
  final unknown = map.keys.where((key) => !allowed.contains(key)).toList();
  if (unknown.isNotEmpty) {
    throw FormatException('$path contains unknown fields: ${unknown.join(', ')}');
  }
}
