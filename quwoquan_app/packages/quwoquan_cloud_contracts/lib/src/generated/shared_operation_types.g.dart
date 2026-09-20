// Code generated from canonical domain contracts. DO NOT EDIT.
// ContractGraph SHA256: 66df23c48a0be75f74e187af317b72624e767b64ea9f478af12994620175c0c3

library;

import "../canonical_sha256_digest.dart";
import "../generated/shared_operation_enums.g.dart";

export "../generated/shared_operation_enums.g.dart";

final class ClientContentPresentationContract {
  const ClientContentPresentationContract({
    required this.contentTypes,
    required this.listObjectKinds,
    required this.presentationRecipes,
    required this.openSurfaces,
    required this.contractDigest,
  });

  final List<ContentType> contentTypes;
  final List<ListObjectKind> listObjectKinds;
  final List<FeedPresentationRecipe> presentationRecipes;
  final List<ContentUiSurface> openSurfaces;
  final String contractDigest;

  factory ClientContentPresentationContract.fromWire(
    Map<String, Object?> map, [
    String path = "ClientContentPresentationContract",
  ]) {
    _rejectUnknownFields(map, const <String>{
      "contentTypes",
      "listObjectKinds",
      "presentationRecipes",
      "openSurfaces",
      "contractDigest",
    }, path);
    return ClientContentPresentationContract(
      contentTypes: List<ContentType>.unmodifiable(
        _requiredBoundedList(
          map["contentTypes"],
          '$path.contentTypes',
          max: 32,
        ).asMap().entries.map(
          (entry) => ContentType.fromWire(
            entry.value,
            '$path.contentTypes' + '[${entry.key}]',
          ),
        ),
      ),
      listObjectKinds: List<ListObjectKind>.unmodifiable(
        _requiredBoundedList(
          map["listObjectKinds"],
          '$path.listObjectKinds',
          max: 32,
        ).asMap().entries.map(
          (entry) => ListObjectKind.fromWire(
            entry.value,
            '$path.listObjectKinds' + '[${entry.key}]',
          ),
        ),
      ),
      presentationRecipes: List<FeedPresentationRecipe>.unmodifiable(
        _requiredBoundedList(
          map["presentationRecipes"],
          '$path.presentationRecipes',
          max: 32,
        ).asMap().entries.map(
          (entry) => FeedPresentationRecipe.fromWire(
            entry.value,
            '$path.presentationRecipes' + '[${entry.key}]',
          ),
        ),
      ),
      openSurfaces: List<ContentUiSurface>.unmodifiable(
        _requiredBoundedList(
          map["openSurfaces"],
          '$path.openSurfaces',
          max: 32,
        ).asMap().entries.map(
          (entry) => ContentUiSurface.fromWire(
            entry.value,
            '$path.openSurfaces' + '[${entry.key}]',
          ),
        ),
      ),
      contractDigest: _requiredCanonicalSha256Digest(
        map["contractDigest"],
        '$path.contractDigest',
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "contentTypes": contentTypes
        .map((value) => value.wireName)
        .toList(growable: false),
    "listObjectKinds": listObjectKinds
        .map((value) => value.wireName)
        .toList(growable: false),
    "presentationRecipes": presentationRecipes
        .map((value) => value.wireName)
        .toList(growable: false),
    "openSurfaces": openSurfaces
        .map((value) => value.wireName)
        .toList(growable: false),
    "contractDigest": contractDigest,
  };
}

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

List<Object?> _requiredList(Object? value, String path) {
  if (value is! List<Object?>) {
    throw FormatException('$path must be a list');
  }
  return value;
}

List<Object?> _requiredBoundedList(
  Object? value,
  String path, {
  required int max,
}) {
  final result = _requiredList(value, path);
  if (result.length > max) {
    throw FormatException('$path must not contain more than $max items');
  }
  return result;
}

String _requiredCanonicalSha256Digest(Object? value, String path) {
  final result = _requiredNonBlankString(value, path);
  if (!isCanonicalSha256Digest(result)) {
    throw FormatException('$path must be a canonical sha256 digest');
  }
  return result;
}
