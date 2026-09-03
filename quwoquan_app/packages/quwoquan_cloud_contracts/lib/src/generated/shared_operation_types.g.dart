// Code generated from canonical domain contracts. DO NOT EDIT.
// ContractGraph SHA256: 569cc5db0ce32ce81f7493f8473fb1cb24a0da718c7e0adb37a6e14d4d9c5372

library;

final class GreetingIntersectionSnapshot {
  const GreetingIntersectionSnapshot({
    required this.intersectionId,
    required this.evidenceId,
    required this.sourceRef,
    required this.objectTypeRef,
    required this.objectId,
    required this.primaryText,
    this.dimension,
    required this.resolvedAt,
  });

  final String intersectionId;
  final String evidenceId;
  final String sourceRef;
  final String objectTypeRef;
  final String objectId;
  final String primaryText;
  final String? dimension;
  final DateTime resolvedAt;

  factory GreetingIntersectionSnapshot.fromWire(
    Map<String, Object?> map, [
    String path = "GreetingIntersectionSnapshot",
  ]) {
    _rejectUnknownFields(map, const <String>{
      "intersectionId",
      "evidenceId",
      "sourceRef",
      "objectTypeRef",
      "objectId",
      "primaryText",
      "dimension",
      "resolvedAt",
    }, path);
    return GreetingIntersectionSnapshot(
      intersectionId: _requiredNonBlankString(
        map["intersectionId"],
        '$path.intersectionId',
      ),
      evidenceId: _requiredNonBlankString(
        map["evidenceId"],
        '$path.evidenceId',
      ),
      sourceRef: _requiredNonBlankString(map["sourceRef"], '$path.sourceRef'),
      objectTypeRef: _requiredNonBlankString(
        map["objectTypeRef"],
        '$path.objectTypeRef',
      ),
      objectId: _requiredNonBlankString(map["objectId"], '$path.objectId'),
      primaryText: _requiredNonBlankString(
        map["primaryText"],
        '$path.primaryText',
      ),
      dimension: map["dimension"] == null
          ? null
          : _requiredString(map["dimension"], '$path.dimension'),
      resolvedAt: _requiredTimestamp(map["resolvedAt"], '$path.resolvedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "intersectionId": intersectionId,
    "evidenceId": evidenceId,
    "sourceRef": sourceRef,
    "objectTypeRef": objectTypeRef,
    "objectId": objectId,
    "primaryText": primaryText,
    if (dimension != null) "dimension": dimension!,
    "resolvedAt": resolvedAt.toUtc().toIso8601String(),
  };
}

void _rejectUnknownFields(
  Map<String, Object?> value,
  Set<String> allowed,
  String path,
) {
  final unknown = value.keys.where((key) => !allowed.contains(key)).toList()
    ..sort();
  if (unknown.isNotEmpty) {
    throw FormatException(
      '$path contains unknown fields: ${unknown.join(', ')}',
    );
  }
}

String _requiredString(Object? value, String path) {
  if (value is! String) throw FormatException('$path must be a string');
  return value;
}

String _requiredNonBlankString(Object? value, String path) {
  final result = _requiredString(value, path);
  if (result.trim().isEmpty) {
    throw FormatException('$path must not be blank');
  }
  return result;
}

DateTime _requiredTimestamp(Object? value, String path) {
  final result = _requiredString(value, path);
  final parsed = DateTime.tryParse(result);
  if (parsed == null) {
    throw FormatException('$path must be an ISO-8601 timestamp');
  }
  return parsed;
}
