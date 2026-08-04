// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 93359367b8614f01bb5e1c51e37af383332b01f117cc1c6cf39e4fdf838e49d2

part of '../../../travel/travel_operation_contracts.g.dart';

Map<String, Object?> _generatedRequestObject(Object? value, String path) {
  if (value is Map<String, Object?>) return value;
  if (value is Map) return Map<String, Object?>.from(value);
  throw FormatException('$path must be an object');
}


void _generatedRequestRejectUnknownFields(
  Map<String, Object?> map,
  Set<String> allowed,
  String path,
) {
  for (final key in map.keys) {
    if (!allowed.contains(key)) {
      throw FormatException('$path contains unknown field $key');
    }
  }
}


String _generatedRequestString(Object? value, String path) {
  if (value is String) return value;
  throw FormatException('$path must be a string');
}


int _generatedRequestInt(Object? value, String path) {
  if (value is int) return value;
  throw FormatException('$path must be an integer');
}


DateTime _generatedRequestTimestamp(Object? value, String path) {
  if (value is! String) throw FormatException('$path must be a timestamp');
  final parsed = DateTime.tryParse(value);
  if (parsed == null) throw FormatException('$path must be a timestamp');
  return parsed.toUtc();
}


List<Object?> _generatedRequestList(Object? value, String path) {
  if (value is List) return List<Object?>.from(value);
  throw FormatException('$path must be a list');
}

final class AssignTripMomentRequest {
  AssignTripMomentRequest({
    required String tripId,
    required String momentId,
    required int expectedVersion,
    required int revisionNumber,
    required int dayIndex,
    String? itemId,
    required TripMomentVisibility visibility,
    required int sourceVersion,
  }) : tripId = tripId,
       momentId = momentId,
       expectedVersion = expectedVersion,
       revisionNumber = revisionNumber,
       dayIndex = dayIndex,
       itemId = itemId,
       visibility = visibility,
       sourceVersion = sourceVersion {
    if (this.tripId.isEmpty) {
      throw ArgumentError.value(this.tripId, "tripId", 'must not be blank');
    }
    if (this.momentId.isEmpty) {
      throw ArgumentError.value(this.momentId, "momentId", 'must not be blank');
    }
  }

  final String tripId;
  final String momentId;
  final int expectedVersion;
  final int revisionNumber;
  final int dayIndex;
  final String? itemId;
  final TripMomentVisibility visibility;
  final int sourceVersion;

  factory AssignTripMomentRequest.fromWire(Map<String, Object?> map, [String path = "AssignTripMomentRequest"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"tripId", "momentId", "expectedVersion", "revisionNumber", "dayIndex", "itemId", "visibility", "sourceVersion"}, path);
    return AssignTripMomentRequest(
      tripId: _generatedRequestString(map["tripId"], '$path.tripId'),
      momentId: _generatedRequestString(map["momentId"], '$path.momentId'),
      expectedVersion: _generatedRequestInt(map["expectedVersion"], '$path.expectedVersion'),
      revisionNumber: _generatedRequestInt(map["revisionNumber"], '$path.revisionNumber'),
      dayIndex: _generatedRequestInt(map["dayIndex"], '$path.dayIndex'),
      itemId: map["itemId"] == null ? null : _generatedRequestString(map["itemId"], '$path.itemId'),
      visibility: switch (map["visibility"]) { "personal" => TripMomentVisibility.personal, "trip_members" => TripMomentVisibility.tripMembers, "public" => TripMomentVisibility.public, _ => throw FormatException('$path.visibility' + ' has an invalid enum value'), },
      sourceVersion: _generatedRequestInt(map["sourceVersion"], '$path.sourceVersion'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "tripId": this.tripId,
    "momentId": this.momentId,
    "expectedVersion": this.expectedVersion,
    "revisionNumber": this.revisionNumber,
    "dayIndex": this.dayIndex,
    if (this.itemId != null) "itemId": this.itemId!,
    "visibility": this.visibility.wireName,
    "sourceVersion": this.sourceVersion,
  };
}

final class CreateTripMomentRequest {
  CreateTripMomentRequest({
    required String tripId,
    required int revisionNumber,
    int? dayIndex,
    String? itemId,
    required TripMomentKind kind,
    TripMomentObjectRef? contentRef,
    String? inlineText,
    required DateTime capturedAt,
    TripMomentObjectRef? coarsePlaceRef,
    required TripMomentVisibility visibility,
    required TripMomentAssignmentStatus assignmentStatus,
    required int sourceVersion,
  }) : tripId = tripId,
       revisionNumber = revisionNumber,
       dayIndex = dayIndex,
       itemId = itemId,
       kind = kind,
       contentRef = contentRef,
       inlineText = inlineText,
       capturedAt = capturedAt,
       coarsePlaceRef = coarsePlaceRef,
       visibility = visibility,
       assignmentStatus = assignmentStatus,
       sourceVersion = sourceVersion {
    if (this.tripId.isEmpty) {
      throw ArgumentError.value(this.tripId, "tripId", 'must not be blank');
    }
  }

  final String tripId;
  final int revisionNumber;
  final int? dayIndex;
  final String? itemId;
  final TripMomentKind kind;
  final TripMomentObjectRef? contentRef;
  final String? inlineText;
  final DateTime capturedAt;
  final TripMomentObjectRef? coarsePlaceRef;
  final TripMomentVisibility visibility;
  final TripMomentAssignmentStatus assignmentStatus;
  final int sourceVersion;

  factory CreateTripMomentRequest.fromWire(Map<String, Object?> map, [String path = "CreateTripMomentRequest"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"tripId", "revisionNumber", "dayIndex", "itemId", "kind", "contentRef", "inlineText", "capturedAt", "coarsePlaceRef", "visibility", "assignmentStatus", "sourceVersion"}, path);
    return CreateTripMomentRequest(
      tripId: _generatedRequestString(map["tripId"], '$path.tripId'),
      revisionNumber: _generatedRequestInt(map["revisionNumber"], '$path.revisionNumber'),
      dayIndex: map["dayIndex"] == null ? null : _generatedRequestInt(map["dayIndex"], '$path.dayIndex'),
      itemId: map["itemId"] == null ? null : _generatedRequestString(map["itemId"], '$path.itemId'),
      kind: switch (map["kind"]) { "photo" => TripMomentKind.photo, "video" => TripMomentKind.video, "voice" => TripMomentKind.voice, "text" => TripMomentKind.text, "check_in" => TripMomentKind.checkIn, "post_reference" => TripMomentKind.postReference, _ => throw FormatException('$path.kind' + ' has an invalid enum value'), },
      contentRef: map["contentRef"] == null ? null : TripMomentObjectRef.fromWire(_generatedRequestObject(map["contentRef"], '$path.contentRef'), '$path.contentRef'),
      inlineText: map["inlineText"] == null ? null : _generatedRequestString(map["inlineText"], '$path.inlineText'),
      capturedAt: _generatedRequestTimestamp(map["capturedAt"], '$path.capturedAt'),
      coarsePlaceRef: map["coarsePlaceRef"] == null ? null : TripMomentObjectRef.fromWire(_generatedRequestObject(map["coarsePlaceRef"], '$path.coarsePlaceRef'), '$path.coarsePlaceRef'),
      visibility: switch (map["visibility"]) { "personal" => TripMomentVisibility.personal, "trip_members" => TripMomentVisibility.tripMembers, "public" => TripMomentVisibility.public, _ => throw FormatException('$path.visibility' + ' has an invalid enum value'), },
      assignmentStatus: switch (map["assignmentStatus"]) { "unassigned" => TripMomentAssignmentStatus.unassigned, "suggested" => TripMomentAssignmentStatus.suggested, "confirmed" => TripMomentAssignmentStatus.confirmed, _ => throw FormatException('$path.assignmentStatus' + ' has an invalid enum value'), },
      sourceVersion: _generatedRequestInt(map["sourceVersion"], '$path.sourceVersion'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "tripId": this.tripId,
    "revisionNumber": this.revisionNumber,
    if (this.dayIndex != null) "dayIndex": this.dayIndex!,
    if (this.itemId != null) "itemId": this.itemId!,
    "kind": this.kind.wireName,
    if (this.contentRef != null) "contentRef": this.contentRef!.toWire(),
    if (this.inlineText != null) "inlineText": this.inlineText!,
    "capturedAt": this.capturedAt.toUtc().toIso8601String(),
    if (this.coarsePlaceRef != null) "coarsePlaceRef": this.coarsePlaceRef!.toWire(),
    "visibility": this.visibility.wireName,
    "assignmentStatus": this.assignmentStatus.wireName,
    "sourceVersion": this.sourceVersion,
  };
}

final class CreateTripPlanCommand {
  CreateTripPlanCommand({
    required String title,
    DateTime? startAt,
    DateTime? endAt,
    required List<TripPlanItemInput> items,
  }) : title = title,
       startAt = startAt,
       endAt = endAt,
       items = List.unmodifiable(items) {
    if (this.title.isEmpty) {
      throw ArgumentError.value(this.title, "title", 'must not be blank');
    }
  }

  final String title;
  final DateTime? startAt;
  final DateTime? endAt;
  final List<TripPlanItemInput> items;

  factory CreateTripPlanCommand.fromWire(Map<String, Object?> map, [String path = "CreateTripPlanCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"title", "startAt", "endAt", "items"}, path);
    return CreateTripPlanCommand(
      title: _generatedRequestString(map["title"], '$path.title'),
      startAt: map["startAt"] == null ? null : _generatedRequestTimestamp(map["startAt"], '$path.startAt'),
      endAt: map["endAt"] == null ? null : _generatedRequestTimestamp(map["endAt"], '$path.endAt'),
      items: List<TripPlanItemInput>.unmodifiable(_generatedRequestList(map["items"], '$path.items').asMap().entries.map((entry) => TripPlanItemInput.fromWire(_generatedRequestObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "title": this.title,
    if (this.startAt != null) "startAt": this.startAt!.toUtc().toIso8601String(),
    if (this.endAt != null) "endAt": this.endAt!.toUtc().toIso8601String(),
    "items": this.items.map((value) => value.toWire()).toList(growable: false),
  };
}

final class CreateTripPlanFromTemplateCommand {
  CreateTripPlanFromTemplateCommand({
    required String templateId,
    String? title,
    DateTime? startAt,
    DateTime? endAt,
  }) : templateId = templateId,
       title = title,
       startAt = startAt,
       endAt = endAt {
    if (this.templateId.isEmpty) {
      throw ArgumentError.value(this.templateId, "templateId", 'must not be blank');
    }
  }

  final String templateId;
  final String? title;
  final DateTime? startAt;
  final DateTime? endAt;

  factory CreateTripPlanFromTemplateCommand.fromWire(Map<String, Object?> map, [String path = "CreateTripPlanFromTemplateCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"templateId", "title", "startAt", "endAt"}, path);
    return CreateTripPlanFromTemplateCommand(
      templateId: _generatedRequestString(map["templateId"], '$path.templateId'),
      title: map["title"] == null ? null : _generatedRequestString(map["title"], '$path.title'),
      startAt: map["startAt"] == null ? null : _generatedRequestTimestamp(map["startAt"], '$path.startAt'),
      endAt: map["endAt"] == null ? null : _generatedRequestTimestamp(map["endAt"], '$path.endAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "templateId": this.templateId,
    if (this.title != null) "title": this.title!,
    if (this.startAt != null) "startAt": this.startAt!.toUtc().toIso8601String(),
    if (this.endAt != null) "endAt": this.endAt!.toUtc().toIso8601String(),
  };
}

final class CreateTripPlanTemplateRequest {
  CreateTripPlanTemplateRequest({
    required String title,
    String? summary,
    required int dayCount,
    required List<TripPlanTemplateItem> items,
    required List<TripPlanTemplateAttribution> attributions,
  }) : title = title,
       summary = summary,
       dayCount = dayCount,
       items = List.unmodifiable(items),
       attributions = List.unmodifiable(attributions) {
    if (this.title.isEmpty) {
      throw ArgumentError.value(this.title, "title", 'must not be blank');
    }
  }

  final String title;
  final String? summary;
  final int dayCount;
  final List<TripPlanTemplateItem> items;
  final List<TripPlanTemplateAttribution> attributions;

  factory CreateTripPlanTemplateRequest.fromWire(Map<String, Object?> map, [String path = "CreateTripPlanTemplateRequest"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"title", "summary", "dayCount", "items", "attributions"}, path);
    return CreateTripPlanTemplateRequest(
      title: _generatedRequestString(map["title"], '$path.title'),
      summary: map["summary"] == null ? null : _generatedRequestString(map["summary"], '$path.summary'),
      dayCount: _generatedRequestInt(map["dayCount"], '$path.dayCount'),
      items: List<TripPlanTemplateItem>.unmodifiable(_generatedRequestList(map["items"], '$path.items').asMap().entries.map((entry) => TripPlanTemplateItem.fromWire(_generatedRequestObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      attributions: List<TripPlanTemplateAttribution>.unmodifiable(_generatedRequestList(map["attributions"], '$path.attributions').asMap().entries.map((entry) => TripPlanTemplateAttribution.fromWire(_generatedRequestObject(entry.value, '$path.attributions' + '[${entry.key}]'), '$path.attributions' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "title": this.title,
    if (this.summary != null) "summary": this.summary!,
    "dayCount": this.dayCount,
    "items": this.items.map((value) => value.toWire()).toList(growable: false),
    "attributions": this.attributions.map((value) => value.toWire()).toList(growable: false),
  };
}

final class CreateTripShareSnapshotRequest {
  CreateTripShareSnapshotRequest({
    required String tripId,
    required String sourceRevisionId,
    required String sourceDigest,
    required TripShareSnapshotScope scope,
    int? dayIndex,
    String? itemId,
    required List<String> momentIds,
    required TripShareSnapshotVisibility visibility,
  }) : tripId = tripId,
       sourceRevisionId = sourceRevisionId,
       sourceDigest = sourceDigest,
       scope = scope,
       dayIndex = dayIndex,
       itemId = itemId,
       momentIds = List.unmodifiable(momentIds),
       visibility = visibility {
    if (this.tripId.isEmpty) {
      throw ArgumentError.value(this.tripId, "tripId", 'must not be blank');
    }
    if (this.sourceRevisionId.isEmpty) {
      throw ArgumentError.value(this.sourceRevisionId, "sourceRevisionId", 'must not be blank');
    }
    if (this.sourceDigest.isEmpty) {
      throw ArgumentError.value(this.sourceDigest, "sourceDigest", 'must not be blank');
    }
  }

  final String tripId;
  final String sourceRevisionId;
  final String sourceDigest;
  final TripShareSnapshotScope scope;
  final int? dayIndex;
  final String? itemId;
  final List<String> momentIds;
  final TripShareSnapshotVisibility visibility;

  factory CreateTripShareSnapshotRequest.fromWire(Map<String, Object?> map, [String path = "CreateTripShareSnapshotRequest"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"tripId", "sourceRevisionId", "sourceDigest", "scope", "dayIndex", "itemId", "momentIds", "visibility"}, path);
    return CreateTripShareSnapshotRequest(
      tripId: _generatedRequestString(map["tripId"], '$path.tripId'),
      sourceRevisionId: _generatedRequestString(map["sourceRevisionId"], '$path.sourceRevisionId'),
      sourceDigest: _generatedRequestString(map["sourceDigest"], '$path.sourceDigest'),
      scope: switch (map["scope"]) { "full" => TripShareSnapshotScope.full, "day" => TripShareSnapshotScope.day, "item" => TripShareSnapshotScope.item, "route" => TripShareSnapshotScope.route, "moment_collection" => TripShareSnapshotScope.momentCollection, _ => throw FormatException('$path.scope' + ' has an invalid enum value'), },
      dayIndex: map["dayIndex"] == null ? null : _generatedRequestInt(map["dayIndex"], '$path.dayIndex'),
      itemId: map["itemId"] == null ? null : _generatedRequestString(map["itemId"], '$path.itemId'),
      momentIds: List<String>.unmodifiable(_generatedRequestList(map["momentIds"], '$path.momentIds').asMap().entries.map((entry) => _generatedRequestString(entry.value, '$path.momentIds' + '[${entry.key}]'))),
      visibility: switch (map["visibility"]) { "trip_members" => TripShareSnapshotVisibility.tripMembers, "public" => TripShareSnapshotVisibility.public, _ => throw FormatException('$path.visibility' + ' has an invalid enum value'), },
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "tripId": this.tripId,
    "sourceRevisionId": this.sourceRevisionId,
    "sourceDigest": this.sourceDigest,
    "scope": this.scope.wireName,
    if (this.dayIndex != null) "dayIndex": this.dayIndex!,
    if (this.itemId != null) "itemId": this.itemId!,
    "momentIds": this.momentIds.map((value) => value).toList(growable: false),
    "visibility": this.visibility.wireName,
  };
}

final class DeleteTripMomentRequest {
  DeleteTripMomentRequest({
    required String tripId,
    required String momentId,
    required int expectedVersion,
    required String reason,
  }) : tripId = tripId,
       momentId = momentId,
       expectedVersion = expectedVersion,
       reason = reason {
    if (this.tripId.isEmpty) {
      throw ArgumentError.value(this.tripId, "tripId", 'must not be blank');
    }
    if (this.momentId.isEmpty) {
      throw ArgumentError.value(this.momentId, "momentId", 'must not be blank');
    }
    if (this.reason.isEmpty) {
      throw ArgumentError.value(this.reason, "reason", 'must not be blank');
    }
  }

  final String tripId;
  final String momentId;
  final int expectedVersion;
  final String reason;

  factory DeleteTripMomentRequest.fromWire(Map<String, Object?> map, [String path = "DeleteTripMomentRequest"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"tripId", "momentId", "expectedVersion", "reason"}, path);
    return DeleteTripMomentRequest(
      tripId: _generatedRequestString(map["tripId"], '$path.tripId'),
      momentId: _generatedRequestString(map["momentId"], '$path.momentId'),
      expectedVersion: _generatedRequestInt(map["expectedVersion"], '$path.expectedVersion'),
      reason: _generatedRequestString(map["reason"], '$path.reason'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "tripId": this.tripId,
    "momentId": this.momentId,
    "expectedVersion": this.expectedVersion,
    "reason": this.reason,
  };
}

final class DepartTripMembershipRequest {
  DepartTripMembershipRequest({
    required String tripId,
    required String personaId,
    required int expectedVersion,
    required String reason,
  }) : tripId = tripId,
       personaId = personaId,
       expectedVersion = expectedVersion,
       reason = reason {
    if (this.tripId.isEmpty) {
      throw ArgumentError.value(this.tripId, "tripId", 'must not be blank');
    }
    if (this.personaId.isEmpty) {
      throw ArgumentError.value(this.personaId, "personaId", 'must not be blank');
    }
    if (this.reason.isEmpty) {
      throw ArgumentError.value(this.reason, "reason", 'must not be blank');
    }
  }

  final String tripId;
  final String personaId;
  final int expectedVersion;
  final String reason;

  factory DepartTripMembershipRequest.fromWire(Map<String, Object?> map, [String path = "DepartTripMembershipRequest"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"tripId", "personaId", "expectedVersion", "reason"}, path);
    return DepartTripMembershipRequest(
      tripId: _generatedRequestString(map["tripId"], '$path.tripId'),
      personaId: _generatedRequestString(map["personaId"], '$path.personaId'),
      expectedVersion: _generatedRequestInt(map["expectedVersion"], '$path.expectedVersion'),
      reason: _generatedRequestString(map["reason"], '$path.reason'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "tripId": this.tripId,
    "personaId": this.personaId,
    "expectedVersion": this.expectedVersion,
    "reason": this.reason,
  };
}

final class GetTripMapQuery {
  GetTripMapQuery({
    required String tripId,
  }) : tripId = tripId {
    if (this.tripId.isEmpty) {
      throw ArgumentError.value(this.tripId, "tripId", 'must not be blank');
    }
  }

  final String tripId;

  factory GetTripMapQuery.fromWire(Map<String, Object?> map, [String path = "GetTripMapQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"tripId"}, path);
    return GetTripMapQuery(
      tripId: _generatedRequestString(map["tripId"], '$path.tripId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "tripId": this.tripId,
  };
}

final class GetTripPlanTemplateQuery {
  GetTripPlanTemplateQuery({
    required String templateId,
  }) : templateId = templateId {
    if (this.templateId.isEmpty) {
      throw ArgumentError.value(this.templateId, "templateId", 'must not be blank');
    }
  }

  final String templateId;

  factory GetTripPlanTemplateQuery.fromWire(Map<String, Object?> map, [String path = "GetTripPlanTemplateQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"templateId"}, path);
    return GetTripPlanTemplateQuery(
      templateId: _generatedRequestString(map["templateId"], '$path.templateId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "templateId": this.templateId,
  };
}

final class GetTripShareSnapshotQuery {
  GetTripShareSnapshotQuery({
    required String snapshotId,
  }) : snapshotId = snapshotId {
    if (this.snapshotId.isEmpty) {
      throw ArgumentError.value(this.snapshotId, "snapshotId", 'must not be blank');
    }
  }

  final String snapshotId;

  factory GetTripShareSnapshotQuery.fromWire(Map<String, Object?> map, [String path = "GetTripShareSnapshotQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"snapshotId"}, path);
    return GetTripShareSnapshotQuery(
      snapshotId: _generatedRequestString(map["snapshotId"], '$path.snapshotId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "snapshotId": this.snapshotId,
  };
}

final class GetTripTimelineQuery {
  GetTripTimelineQuery({
    required String tripId,
  }) : tripId = tripId {
    if (this.tripId.isEmpty) {
      throw ArgumentError.value(this.tripId, "tripId", 'must not be blank');
    }
  }

  final String tripId;

  factory GetTripTimelineQuery.fromWire(Map<String, Object?> map, [String path = "GetTripTimelineQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"tripId"}, path);
    return GetTripTimelineQuery(
      tripId: _generatedRequestString(map["tripId"], '$path.tripId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "tripId": this.tripId,
  };
}

final class ListSurfaceTripPlacementsQuery {
  ListSurfaceTripPlacementsQuery({
    required TripPlacementSurfaceKind surfaceKind,
    required String surfaceId,
  }) : surfaceKind = surfaceKind,
       surfaceId = surfaceId {
    if (this.surfaceId.isEmpty) {
      throw ArgumentError.value(this.surfaceId, "surfaceId", 'must not be blank');
    }
  }

  final TripPlacementSurfaceKind surfaceKind;
  final String surfaceId;

  factory ListSurfaceTripPlacementsQuery.fromWire(Map<String, Object?> map, [String path = "ListSurfaceTripPlacementsQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"surfaceKind", "surfaceId"}, path);
    return ListSurfaceTripPlacementsQuery(
      surfaceKind: switch (map["surfaceKind"]) { "conversation" => TripPlacementSurfaceKind.conversation, "circle" => TripPlacementSurfaceKind.circle, _ => throw FormatException('$path.surfaceKind' + ' has an invalid enum value'), },
      surfaceId: _generatedRequestString(map["surfaceId"], '$path.surfaceId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "surfaceKind": this.surfaceKind.wireName,
    "surfaceId": this.surfaceId,
  };
}

final class ListTripGuideAssignmentsQuery {
  ListTripGuideAssignmentsQuery({
    required String tripId,
  }) : tripId = tripId {
    if (this.tripId.isEmpty) {
      throw ArgumentError.value(this.tripId, "tripId", 'must not be blank');
    }
  }

  final String tripId;

  factory ListTripGuideAssignmentsQuery.fromWire(Map<String, Object?> map, [String path = "ListTripGuideAssignmentsQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"tripId"}, path);
    return ListTripGuideAssignmentsQuery(
      tripId: _generatedRequestString(map["tripId"], '$path.tripId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "tripId": this.tripId,
  };
}

final class ListTripMembershipsQuery {
  ListTripMembershipsQuery({
    required String tripId,
  }) : tripId = tripId {
    if (this.tripId.isEmpty) {
      throw ArgumentError.value(this.tripId, "tripId", 'must not be blank');
    }
  }

  final String tripId;

  factory ListTripMembershipsQuery.fromWire(Map<String, Object?> map, [String path = "ListTripMembershipsQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"tripId"}, path);
    return ListTripMembershipsQuery(
      tripId: _generatedRequestString(map["tripId"], '$path.tripId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "tripId": this.tripId,
  };
}

final class ListTripMomentsQuery {
  ListTripMomentsQuery({
    required String tripId,
  }) : tripId = tripId {
    if (this.tripId.isEmpty) {
      throw ArgumentError.value(this.tripId, "tripId", 'must not be blank');
    }
  }

  final String tripId;

  factory ListTripMomentsQuery.fromWire(Map<String, Object?> map, [String path = "ListTripMomentsQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"tripId"}, path);
    return ListTripMomentsQuery(
      tripId: _generatedRequestString(map["tripId"], '$path.tripId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "tripId": this.tripId,
  };
}

final class ListTripPlanContentLinksQuery {
  ListTripPlanContentLinksQuery({
    required String tripId,
  }) : tripId = tripId {
    if (this.tripId.isEmpty) {
      throw ArgumentError.value(this.tripId, "tripId", 'must not be blank');
    }
  }

  final String tripId;

  factory ListTripPlanContentLinksQuery.fromWire(Map<String, Object?> map, [String path = "ListTripPlanContentLinksQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"tripId"}, path);
    return ListTripPlanContentLinksQuery(
      tripId: _generatedRequestString(map["tripId"], '$path.tripId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "tripId": this.tripId,
  };
}

final class ListTripPlanPlacementsQuery {
  ListTripPlanPlacementsQuery({
    required String tripId,
  }) : tripId = tripId {
    if (this.tripId.isEmpty) {
      throw ArgumentError.value(this.tripId, "tripId", 'must not be blank');
    }
  }

  final String tripId;

  factory ListTripPlanPlacementsQuery.fromWire(Map<String, Object?> map, [String path = "ListTripPlanPlacementsQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"tripId"}, path);
    return ListTripPlanPlacementsQuery(
      tripId: _generatedRequestString(map["tripId"], '$path.tripId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "tripId": this.tripId,
  };
}

final class ListTripPlanTemplatesQuery {
  const ListTripPlanTemplatesQuery();
}

final class ListTripPlansQuery {
  const ListTripPlansQuery({
    TripPlanStatus? status,
    String? cursor,
    int? limit,
  }) : status = status,
       cursor = cursor,
       limit = limit;

  final TripPlanStatus? status;
  final String? cursor;
  final int? limit;

  factory ListTripPlansQuery.fromWire(Map<String, Object?> map, [String path = "ListTripPlansQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"status", "cursor", "limit"}, path);
    return ListTripPlansQuery(
      status: map["status"] == null ? null : switch (map["status"]) { "planning" => TripPlanStatus.planning, "active" => TripPlanStatus.active, "completed" => TripPlanStatus.completed, "archived" => TripPlanStatus.archived, _ => throw FormatException('$path.status' + ' has an invalid enum value'), },
      cursor: map["cursor"] == null ? null : _generatedRequestString(map["cursor"], '$path.cursor'),
      limit: map["limit"] == null ? null : _generatedRequestInt(map["limit"], '$path.limit'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (this.status != null) "status": this.status!.wireName,
    if (this.cursor != null) "cursor": this.cursor!,
    if (this.limit != null) "limit": this.limit!,
  };
}

final class PutTripGuideAssignmentRequest {
  PutTripGuideAssignmentRequest({
    required String tripId,
    required int expectedVersion,
    required String taskKey,
    required String assigneePersonaId,
    required TripGuideRole role,
    required TripGuideTaskKind taskKind,
    required String title,
    DateTime? dueAt,
    required int sourceRevisionNumber,
    required TripGuideAttributionKind attributionKind,
    required String attributionPersonaId,
    String? publicQualificationPersonaId,
  }) : tripId = tripId,
       expectedVersion = expectedVersion,
       taskKey = taskKey,
       assigneePersonaId = assigneePersonaId,
       role = role,
       taskKind = taskKind,
       title = title,
       dueAt = dueAt,
       sourceRevisionNumber = sourceRevisionNumber,
       attributionKind = attributionKind,
       attributionPersonaId = attributionPersonaId,
       publicQualificationPersonaId = publicQualificationPersonaId {
    if (this.tripId.isEmpty) {
      throw ArgumentError.value(this.tripId, "tripId", 'must not be blank');
    }
    if (this.taskKey.isEmpty) {
      throw ArgumentError.value(this.taskKey, "taskKey", 'must not be blank');
    }
    if (this.assigneePersonaId.isEmpty) {
      throw ArgumentError.value(this.assigneePersonaId, "assigneePersonaId", 'must not be blank');
    }
    if (this.title.isEmpty) {
      throw ArgumentError.value(this.title, "title", 'must not be blank');
    }
    if (this.attributionPersonaId.isEmpty) {
      throw ArgumentError.value(this.attributionPersonaId, "attributionPersonaId", 'must not be blank');
    }
  }

  final String tripId;
  final int expectedVersion;
  final String taskKey;
  final String assigneePersonaId;
  final TripGuideRole role;
  final TripGuideTaskKind taskKind;
  final String title;
  final DateTime? dueAt;
  final int sourceRevisionNumber;
  final TripGuideAttributionKind attributionKind;
  final String attributionPersonaId;
  final String? publicQualificationPersonaId;

  factory PutTripGuideAssignmentRequest.fromWire(Map<String, Object?> map, [String path = "PutTripGuideAssignmentRequest"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"tripId", "expectedVersion", "taskKey", "assigneePersonaId", "role", "taskKind", "title", "dueAt", "sourceRevisionNumber", "attributionKind", "attributionPersonaId", "publicQualificationPersonaId"}, path);
    return PutTripGuideAssignmentRequest(
      tripId: _generatedRequestString(map["tripId"], '$path.tripId'),
      expectedVersion: _generatedRequestInt(map["expectedVersion"], '$path.expectedVersion'),
      taskKey: _generatedRequestString(map["taskKey"], '$path.taskKey'),
      assigneePersonaId: _generatedRequestString(map["assigneePersonaId"], '$path.assigneePersonaId'),
      role: switch (map["role"]) { "leader" => TripGuideRole.leader, "assistant_guide" => TripGuideRole.assistantGuide, "licensed_guide" => TripGuideRole.licensedGuide, "local_expert" => TripGuideRole.localExpert, _ => throw FormatException('$path.role' + ' has an invalid enum value'), },
      taskKind: switch (map["taskKind"]) { "collection" => TripGuideTaskKind.collection, "briefing" => TripGuideTaskKind.briefing, "route_guidance" => TripGuideTaskKind.routeGuidance, "commentary" => TripGuideTaskKind.commentary, "general_support" => TripGuideTaskKind.generalSupport, _ => throw FormatException('$path.taskKind' + ' has an invalid enum value'), },
      title: _generatedRequestString(map["title"], '$path.title'),
      dueAt: map["dueAt"] == null ? null : _generatedRequestTimestamp(map["dueAt"], '$path.dueAt'),
      sourceRevisionNumber: _generatedRequestInt(map["sourceRevisionNumber"], '$path.sourceRevisionNumber'),
      attributionKind: switch (map["attributionKind"]) { "administrative" => TripGuideAttributionKind.administrative, "general_fact" => TripGuideAttributionKind.generalFact, "professional_commentary" => TripGuideAttributionKind.professionalCommentary, _ => throw FormatException('$path.attributionKind' + ' has an invalid enum value'), },
      attributionPersonaId: _generatedRequestString(map["attributionPersonaId"], '$path.attributionPersonaId'),
      publicQualificationPersonaId: map["publicQualificationPersonaId"] == null ? null : _generatedRequestString(map["publicQualificationPersonaId"], '$path.publicQualificationPersonaId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "tripId": this.tripId,
    "expectedVersion": this.expectedVersion,
    "taskKey": this.taskKey,
    "assigneePersonaId": this.assigneePersonaId,
    "role": this.role.wireName,
    "taskKind": this.taskKind.wireName,
    "title": this.title,
    if (this.dueAt != null) "dueAt": this.dueAt!.toUtc().toIso8601String(),
    "sourceRevisionNumber": this.sourceRevisionNumber,
    "attributionKind": this.attributionKind.wireName,
    "attributionPersonaId": this.attributionPersonaId,
    if (this.publicQualificationPersonaId != null) "publicQualificationPersonaId": this.publicQualificationPersonaId!,
  };
}

final class PutTripMembershipRequest {
  PutTripMembershipRequest({
    required String tripId,
    required String personaId,
    required TripMembershipRole role,
    required TripMembershipSourceKind sourceKind,
    TripMembershipSourceRef? sourceObjectRef,
    required int sourceVersion,
    required int expectedVersion,
  }) : tripId = tripId,
       personaId = personaId,
       role = role,
       sourceKind = sourceKind,
       sourceObjectRef = sourceObjectRef,
       sourceVersion = sourceVersion,
       expectedVersion = expectedVersion {
    if (this.tripId.isEmpty) {
      throw ArgumentError.value(this.tripId, "tripId", 'must not be blank');
    }
    if (this.personaId.isEmpty) {
      throw ArgumentError.value(this.personaId, "personaId", 'must not be blank');
    }
  }

  final String tripId;
  final String personaId;
  final TripMembershipRole role;
  final TripMembershipSourceKind sourceKind;
  final TripMembershipSourceRef? sourceObjectRef;
  final int sourceVersion;
  final int expectedVersion;

  factory PutTripMembershipRequest.fromWire(Map<String, Object?> map, [String path = "PutTripMembershipRequest"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"tripId", "personaId", "role", "sourceKind", "sourceObjectRef", "sourceVersion", "expectedVersion"}, path);
    return PutTripMembershipRequest(
      tripId: _generatedRequestString(map["tripId"], '$path.tripId'),
      personaId: _generatedRequestString(map["personaId"], '$path.personaId'),
      role: switch (map["role"]) { "organizer" => TripMembershipRole.organizer, "participant" => TripMembershipRole.participant, "leader" => TripMembershipRole.leader, "assistant_guide" => TripMembershipRole.assistantGuide, "guide" => TripMembershipRole.guide, "local_expert" => TripMembershipRole.localExpert, _ => throw FormatException('$path.role' + ' has an invalid enum value'), },
      sourceKind: switch (map["sourceKind"]) { "trip_invitation" => TripMembershipSourceKind.tripInvitation, "conversation" => TripMembershipSourceKind.conversation, "circle" => TripMembershipSourceKind.circle, "gathering" => TripMembershipSourceKind.gathering, _ => throw FormatException('$path.sourceKind' + ' has an invalid enum value'), },
      sourceObjectRef: map["sourceObjectRef"] == null ? null : TripMembershipSourceRef.fromWire(_generatedRequestObject(map["sourceObjectRef"], '$path.sourceObjectRef'), '$path.sourceObjectRef'),
      sourceVersion: _generatedRequestInt(map["sourceVersion"], '$path.sourceVersion'),
      expectedVersion: _generatedRequestInt(map["expectedVersion"], '$path.expectedVersion'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "tripId": this.tripId,
    "personaId": this.personaId,
    "role": this.role.wireName,
    "sourceKind": this.sourceKind.wireName,
    if (this.sourceObjectRef != null) "sourceObjectRef": this.sourceObjectRef!.toWire(),
    "sourceVersion": this.sourceVersion,
    "expectedVersion": this.expectedVersion,
  };
}

final class PutTripPlanContentLinkRequest {
  PutTripPlanContentLinkRequest({
    required String tripId,
    required String postId,
    required int expectedVersion,
    required int revisionNumber,
    required TripPlanContentLinkTargetKind targetKind,
    int? dayIndex,
    String? itemId,
    required TripPlanContentLinkVisibility visibility,
    required int sourceVersion,
  }) : tripId = tripId,
       postId = postId,
       expectedVersion = expectedVersion,
       revisionNumber = revisionNumber,
       targetKind = targetKind,
       dayIndex = dayIndex,
       itemId = itemId,
       visibility = visibility,
       sourceVersion = sourceVersion {
    if (this.tripId.isEmpty) {
      throw ArgumentError.value(this.tripId, "tripId", 'must not be blank');
    }
    if (this.postId.isEmpty) {
      throw ArgumentError.value(this.postId, "postId", 'must not be blank');
    }
  }

  final String tripId;
  final String postId;
  final int expectedVersion;
  final int revisionNumber;
  final TripPlanContentLinkTargetKind targetKind;
  final int? dayIndex;
  final String? itemId;
  final TripPlanContentLinkVisibility visibility;
  final int sourceVersion;

  factory PutTripPlanContentLinkRequest.fromWire(Map<String, Object?> map, [String path = "PutTripPlanContentLinkRequest"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"tripId", "postId", "expectedVersion", "revisionNumber", "targetKind", "dayIndex", "itemId", "visibility", "sourceVersion"}, path);
    return PutTripPlanContentLinkRequest(
      tripId: _generatedRequestString(map["tripId"], '$path.tripId'),
      postId: _generatedRequestString(map["postId"], '$path.postId'),
      expectedVersion: _generatedRequestInt(map["expectedVersion"], '$path.expectedVersion'),
      revisionNumber: _generatedRequestInt(map["revisionNumber"], '$path.revisionNumber'),
      targetKind: switch (map["targetKind"]) { "trip" => TripPlanContentLinkTargetKind.trip, "day" => TripPlanContentLinkTargetKind.day, "item" => TripPlanContentLinkTargetKind.item, _ => throw FormatException('$path.targetKind' + ' has an invalid enum value'), },
      dayIndex: map["dayIndex"] == null ? null : _generatedRequestInt(map["dayIndex"], '$path.dayIndex'),
      itemId: map["itemId"] == null ? null : _generatedRequestString(map["itemId"], '$path.itemId'),
      visibility: switch (map["visibility"]) { "trip_members" => TripPlanContentLinkVisibility.tripMembers, "public" => TripPlanContentLinkVisibility.public, _ => throw FormatException('$path.visibility' + ' has an invalid enum value'), },
      sourceVersion: _generatedRequestInt(map["sourceVersion"], '$path.sourceVersion'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "tripId": this.tripId,
    "postId": this.postId,
    "expectedVersion": this.expectedVersion,
    "revisionNumber": this.revisionNumber,
    "targetKind": this.targetKind.wireName,
    if (this.dayIndex != null) "dayIndex": this.dayIndex!,
    if (this.itemId != null) "itemId": this.itemId!,
    "visibility": this.visibility.wireName,
    "sourceVersion": this.sourceVersion,
  };
}

final class PutTripPlanPlacementRequest {
  PutTripPlanPlacementRequest({
    required String tripId,
    required TripPlacementSurfaceKind surfaceKind,
    required String surfaceId,
    required int sourceVersion,
    required int expectedVersion,
  }) : tripId = tripId,
       surfaceKind = surfaceKind,
       surfaceId = surfaceId,
       sourceVersion = sourceVersion,
       expectedVersion = expectedVersion {
    if (this.tripId.isEmpty) {
      throw ArgumentError.value(this.tripId, "tripId", 'must not be blank');
    }
    if (this.surfaceId.isEmpty) {
      throw ArgumentError.value(this.surfaceId, "surfaceId", 'must not be blank');
    }
  }

  final String tripId;
  final TripPlacementSurfaceKind surfaceKind;
  final String surfaceId;
  final int sourceVersion;
  final int expectedVersion;

  factory PutTripPlanPlacementRequest.fromWire(Map<String, Object?> map, [String path = "PutTripPlanPlacementRequest"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"tripId", "surfaceKind", "surfaceId", "sourceVersion", "expectedVersion"}, path);
    return PutTripPlanPlacementRequest(
      tripId: _generatedRequestString(map["tripId"], '$path.tripId'),
      surfaceKind: switch (map["surfaceKind"]) { "conversation" => TripPlacementSurfaceKind.conversation, "circle" => TripPlacementSurfaceKind.circle, _ => throw FormatException('$path.surfaceKind' + ' has an invalid enum value'), },
      surfaceId: _generatedRequestString(map["surfaceId"], '$path.surfaceId'),
      sourceVersion: _generatedRequestInt(map["sourceVersion"], '$path.sourceVersion'),
      expectedVersion: _generatedRequestInt(map["expectedVersion"], '$path.expectedVersion'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "tripId": this.tripId,
    "surfaceKind": this.surfaceKind.wireName,
    "surfaceId": this.surfaceId,
    "sourceVersion": this.sourceVersion,
    "expectedVersion": this.expectedVersion,
  };
}

final class PutTripPlanTemplateRequest {
  PutTripPlanTemplateRequest({
    required String templateId,
    required int expectedVersion,
    required String title,
    String? summary,
    required int dayCount,
    required List<TripPlanTemplateItem> items,
    required List<TripPlanTemplateAttribution> attributions,
  }) : templateId = templateId,
       expectedVersion = expectedVersion,
       title = title,
       summary = summary,
       dayCount = dayCount,
       items = List.unmodifiable(items),
       attributions = List.unmodifiable(attributions) {
    if (this.templateId.isEmpty) {
      throw ArgumentError.value(this.templateId, "templateId", 'must not be blank');
    }
    if (this.title.isEmpty) {
      throw ArgumentError.value(this.title, "title", 'must not be blank');
    }
  }

  final String templateId;
  final int expectedVersion;
  final String title;
  final String? summary;
  final int dayCount;
  final List<TripPlanTemplateItem> items;
  final List<TripPlanTemplateAttribution> attributions;

  factory PutTripPlanTemplateRequest.fromWire(Map<String, Object?> map, [String path = "PutTripPlanTemplateRequest"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"templateId", "expectedVersion", "title", "summary", "dayCount", "items", "attributions"}, path);
    return PutTripPlanTemplateRequest(
      templateId: _generatedRequestString(map["templateId"], '$path.templateId'),
      expectedVersion: _generatedRequestInt(map["expectedVersion"], '$path.expectedVersion'),
      title: _generatedRequestString(map["title"], '$path.title'),
      summary: map["summary"] == null ? null : _generatedRequestString(map["summary"], '$path.summary'),
      dayCount: _generatedRequestInt(map["dayCount"], '$path.dayCount'),
      items: List<TripPlanTemplateItem>.unmodifiable(_generatedRequestList(map["items"], '$path.items').asMap().entries.map((entry) => TripPlanTemplateItem.fromWire(_generatedRequestObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      attributions: List<TripPlanTemplateAttribution>.unmodifiable(_generatedRequestList(map["attributions"], '$path.attributions').asMap().entries.map((entry) => TripPlanTemplateAttribution.fromWire(_generatedRequestObject(entry.value, '$path.attributions' + '[${entry.key}]'), '$path.attributions' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "templateId": this.templateId,
    "expectedVersion": this.expectedVersion,
    "title": this.title,
    if (this.summary != null) "summary": this.summary!,
    "dayCount": this.dayCount,
    "items": this.items.map((value) => value.toWire()).toList(growable: false),
    "attributions": this.attributions.map((value) => value.toWire()).toList(growable: false),
  };
}

final class RemoveTripPlanContentLinkRequest {
  RemoveTripPlanContentLinkRequest({
    required String tripId,
    required String postId,
    required int expectedVersion,
    required String reason,
  }) : tripId = tripId,
       postId = postId,
       expectedVersion = expectedVersion,
       reason = reason {
    if (this.tripId.isEmpty) {
      throw ArgumentError.value(this.tripId, "tripId", 'must not be blank');
    }
    if (this.postId.isEmpty) {
      throw ArgumentError.value(this.postId, "postId", 'must not be blank');
    }
    if (this.reason.isEmpty) {
      throw ArgumentError.value(this.reason, "reason", 'must not be blank');
    }
  }

  final String tripId;
  final String postId;
  final int expectedVersion;
  final String reason;

  factory RemoveTripPlanContentLinkRequest.fromWire(Map<String, Object?> map, [String path = "RemoveTripPlanContentLinkRequest"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"tripId", "postId", "expectedVersion", "reason"}, path);
    return RemoveTripPlanContentLinkRequest(
      tripId: _generatedRequestString(map["tripId"], '$path.tripId'),
      postId: _generatedRequestString(map["postId"], '$path.postId'),
      expectedVersion: _generatedRequestInt(map["expectedVersion"], '$path.expectedVersion'),
      reason: _generatedRequestString(map["reason"], '$path.reason'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "tripId": this.tripId,
    "postId": this.postId,
    "expectedVersion": this.expectedVersion,
    "reason": this.reason,
  };
}

final class RemoveTripPlanPlacementRequest {
  RemoveTripPlanPlacementRequest({
    required String tripId,
    required TripPlacementSurfaceKind surfaceKind,
    required String surfaceId,
    required int sourceVersion,
    required int expectedVersion,
  }) : tripId = tripId,
       surfaceKind = surfaceKind,
       surfaceId = surfaceId,
       sourceVersion = sourceVersion,
       expectedVersion = expectedVersion {
    if (this.tripId.isEmpty) {
      throw ArgumentError.value(this.tripId, "tripId", 'must not be blank');
    }
    if (this.surfaceId.isEmpty) {
      throw ArgumentError.value(this.surfaceId, "surfaceId", 'must not be blank');
    }
  }

  final String tripId;
  final TripPlacementSurfaceKind surfaceKind;
  final String surfaceId;
  final int sourceVersion;
  final int expectedVersion;

  factory RemoveTripPlanPlacementRequest.fromWire(Map<String, Object?> map, [String path = "RemoveTripPlanPlacementRequest"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"tripId", "surfaceKind", "surfaceId", "sourceVersion", "expectedVersion"}, path);
    return RemoveTripPlanPlacementRequest(
      tripId: _generatedRequestString(map["tripId"], '$path.tripId'),
      surfaceKind: switch (map["surfaceKind"]) { "conversation" => TripPlacementSurfaceKind.conversation, "circle" => TripPlacementSurfaceKind.circle, _ => throw FormatException('$path.surfaceKind' + ' has an invalid enum value'), },
      surfaceId: _generatedRequestString(map["surfaceId"], '$path.surfaceId'),
      sourceVersion: _generatedRequestInt(map["sourceVersion"], '$path.sourceVersion'),
      expectedVersion: _generatedRequestInt(map["expectedVersion"], '$path.expectedVersion'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "tripId": this.tripId,
    "surfaceKind": this.surfaceKind.wireName,
    "surfaceId": this.surfaceId,
    "sourceVersion": this.sourceVersion,
    "expectedVersion": this.expectedVersion,
  };
}

final class ReviseTripPlanCommand {
  ReviseTripPlanCommand({
    required String tripId,
    required int expectedRevisionNumber,
    required String changeReason,
    required TripRevisionSeverity severity,
    required List<TripPlanItemInput> items,
  }) : tripId = tripId,
       expectedRevisionNumber = expectedRevisionNumber,
       changeReason = changeReason,
       severity = severity,
       items = List.unmodifiable(items) {
    if (this.tripId.isEmpty) {
      throw ArgumentError.value(this.tripId, "tripId", 'must not be blank');
    }
    if (this.changeReason.isEmpty) {
      throw ArgumentError.value(this.changeReason, "changeReason", 'must not be blank');
    }
  }

  final String tripId;
  final int expectedRevisionNumber;
  final String changeReason;
  final TripRevisionSeverity severity;
  final List<TripPlanItemInput> items;

  factory ReviseTripPlanCommand.fromWire(Map<String, Object?> map, [String path = "ReviseTripPlanCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"tripId", "expectedRevisionNumber", "changeReason", "severity", "items"}, path);
    return ReviseTripPlanCommand(
      tripId: _generatedRequestString(map["tripId"], '$path.tripId'),
      expectedRevisionNumber: _generatedRequestInt(map["expectedRevisionNumber"], '$path.expectedRevisionNumber'),
      changeReason: _generatedRequestString(map["changeReason"], '$path.changeReason'),
      severity: switch (map["severity"]) { "minor" => TripRevisionSeverity.minor, "important" => TripRevisionSeverity.important, "critical" => TripRevisionSeverity.critical, _ => throw FormatException('$path.severity' + ' has an invalid enum value'), },
      items: List<TripPlanItemInput>.unmodifiable(_generatedRequestList(map["items"], '$path.items').asMap().entries.map((entry) => TripPlanItemInput.fromWire(_generatedRequestObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "tripId": this.tripId,
    "expectedRevisionNumber": this.expectedRevisionNumber,
    "changeReason": this.changeReason,
    "severity": this.severity.wireName,
    "items": this.items.map((value) => value.toWire()).toList(growable: false),
  };
}

final class TransitionTripGuideAssignmentRequest {
  TransitionTripGuideAssignmentRequest({
    required String tripId,
    required String taskKey,
    required int expectedVersion,
    required TripGuideAssignmentStatus targetStatus,
  }) : tripId = tripId,
       taskKey = taskKey,
       expectedVersion = expectedVersion,
       targetStatus = targetStatus {
    if (this.tripId.isEmpty) {
      throw ArgumentError.value(this.tripId, "tripId", 'must not be blank');
    }
    if (this.taskKey.isEmpty) {
      throw ArgumentError.value(this.taskKey, "taskKey", 'must not be blank');
    }
  }

  final String tripId;
  final String taskKey;
  final int expectedVersion;
  final TripGuideAssignmentStatus targetStatus;

  factory TransitionTripGuideAssignmentRequest.fromWire(Map<String, Object?> map, [String path = "TransitionTripGuideAssignmentRequest"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"tripId", "taskKey", "expectedVersion", "targetStatus"}, path);
    return TransitionTripGuideAssignmentRequest(
      tripId: _generatedRequestString(map["tripId"], '$path.tripId'),
      taskKey: _generatedRequestString(map["taskKey"], '$path.taskKey'),
      expectedVersion: _generatedRequestInt(map["expectedVersion"], '$path.expectedVersion'),
      targetStatus: switch (map["targetStatus"]) { "assigned" => TripGuideAssignmentStatus.assigned, "accepted" => TripGuideAssignmentStatus.accepted, "in_progress" => TripGuideAssignmentStatus.inProgress, "completed" => TripGuideAssignmentStatus.completed, "cancelled" => TripGuideAssignmentStatus.cancelled, _ => throw FormatException('$path.targetStatus' + ' has an invalid enum value'), },
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "tripId": this.tripId,
    "taskKey": this.taskKey,
    "expectedVersion": this.expectedVersion,
    "targetStatus": this.targetStatus.wireName,
  };
}

final class TransitionTripPlanCommand {
  TransitionTripPlanCommand({
    required String tripId,
    required int expectedRevisionNumber,
    required TripPlanStatus targetStatus,
  }) : tripId = tripId,
       expectedRevisionNumber = expectedRevisionNumber,
       targetStatus = targetStatus {
    if (this.tripId.isEmpty) {
      throw ArgumentError.value(this.tripId, "tripId", 'must not be blank');
    }
  }

  final String tripId;
  final int expectedRevisionNumber;
  final TripPlanStatus targetStatus;

  factory TransitionTripPlanCommand.fromWire(Map<String, Object?> map, [String path = "TransitionTripPlanCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"tripId", "expectedRevisionNumber", "targetStatus"}, path);
    return TransitionTripPlanCommand(
      tripId: _generatedRequestString(map["tripId"], '$path.tripId'),
      expectedRevisionNumber: _generatedRequestInt(map["expectedRevisionNumber"], '$path.expectedRevisionNumber'),
      targetStatus: switch (map["targetStatus"]) { "planning" => TripPlanStatus.planning, "active" => TripPlanStatus.active, "completed" => TripPlanStatus.completed, "archived" => TripPlanStatus.archived, _ => throw FormatException('$path.targetStatus' + ' has an invalid enum value'), },
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "tripId": this.tripId,
    "expectedRevisionNumber": this.expectedRevisionNumber,
    "targetStatus": this.targetStatus.wireName,
  };
}

final class TripPlanIDQuery {
  TripPlanIDQuery({
    required String tripId,
  }) : tripId = tripId {
    if (this.tripId.isEmpty) {
      throw ArgumentError.value(this.tripId, "tripId", 'must not be blank');
    }
  }

  final String tripId;

  factory TripPlanIDQuery.fromWire(Map<String, Object?> map, [String path = "TripPlanIDQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"tripId"}, path);
    return TripPlanIDQuery(
      tripId: _generatedRequestString(map["tripId"], '$path.tripId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "tripId": this.tripId,
  };
}

final class TripPlanItemInput {
  TripPlanItemInput({
    required String itemId,
    required int dayIndex,
    required int orderInDay,
    required TripPlanItemKind kind,
    required String title,
    DateTime? startAt,
    DateTime? endAt,
    TripPlaceRef? placeRef,
    String? note,
  }) : itemId = itemId,
       dayIndex = dayIndex,
       orderInDay = orderInDay,
       kind = kind,
       title = title,
       startAt = startAt,
       endAt = endAt,
       placeRef = placeRef,
       note = note {
    if (this.itemId.isEmpty) {
      throw ArgumentError.value(this.itemId, "itemId", 'must not be blank');
    }
    if (this.title.isEmpty) {
      throw ArgumentError.value(this.title, "title", 'must not be blank');
    }
  }

  final String itemId;
  final int dayIndex;
  final int orderInDay;
  final TripPlanItemKind kind;
  final String title;
  final DateTime? startAt;
  final DateTime? endAt;
  final TripPlaceRef? placeRef;
  final String? note;

  factory TripPlanItemInput.fromWire(Map<String, Object?> map, [String path = "TripPlanItemInput"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"itemId", "dayIndex", "orderInDay", "kind", "title", "startAt", "endAt", "placeRef", "note"}, path);
    return TripPlanItemInput(
      itemId: _generatedRequestString(map["itemId"], '$path.itemId'),
      dayIndex: _generatedRequestInt(map["dayIndex"], '$path.dayIndex'),
      orderInDay: _generatedRequestInt(map["orderInDay"], '$path.orderInDay'),
      kind: switch (map["kind"]) { "stay" => TripPlanItemKind.stay, "food" => TripPlanItemKind.food, "sight" => TripPlanItemKind.sight, "activity" => TripPlanItemKind.activity, "transport" => TripPlanItemKind.transport, "rest" => TripPlanItemKind.rest, "free_time" => TripPlanItemKind.freeTime, _ => throw FormatException('$path.kind' + ' has an invalid enum value'), },
      title: _generatedRequestString(map["title"], '$path.title'),
      startAt: map["startAt"] == null ? null : _generatedRequestTimestamp(map["startAt"], '$path.startAt'),
      endAt: map["endAt"] == null ? null : _generatedRequestTimestamp(map["endAt"], '$path.endAt'),
      placeRef: map["placeRef"] == null ? null : TripPlaceRef.fromWire(_generatedRequestObject(map["placeRef"], '$path.placeRef'), '$path.placeRef'),
      note: map["note"] == null ? null : _generatedRequestString(map["note"], '$path.note'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "itemId": this.itemId,
    "dayIndex": this.dayIndex,
    "orderInDay": this.orderInDay,
    "kind": this.kind.wireName,
    "title": this.title,
    if (this.startAt != null) "startAt": this.startAt!.toUtc().toIso8601String(),
    if (this.endAt != null) "endAt": this.endAt!.toUtc().toIso8601String(),
    if (this.placeRef != null) "placeRef": this.placeRef!.toWire(),
    if (this.note != null) "note": this.note!,
  };
}

CloudOperationRequestPayload encodeTravelTripGuideAssignmentListTripGuideAssignmentsGeneratedRequest(ListTripGuideAssignmentsQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "tripId": request.tripId,
    },
  );
}

CloudOperationRequestPayload encodeTravelTripGuideAssignmentPutTripGuideAssignmentGeneratedRequest(PutTripGuideAssignmentRequest request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "tripId": request.tripId,
      "taskKey": request.taskKey,
    },
    body: <String, Object?>{
      "expectedVersion": request.expectedVersion,
      "assigneePersonaId": request.assigneePersonaId,
      "role": request.role.wireName,
      "taskKind": request.taskKind.wireName,
      "title": request.title,
      if (request.dueAt != null) "dueAt": request.dueAt!.toUtc().toIso8601String(),
      "sourceRevisionNumber": request.sourceRevisionNumber,
      "attributionKind": request.attributionKind.wireName,
      "attributionPersonaId": request.attributionPersonaId,
      if (request.publicQualificationPersonaId != null) "publicQualificationPersonaId": request.publicQualificationPersonaId!,
    },
  );
}

CloudOperationRequestPayload encodeTravelTripGuideAssignmentTransitionTripGuideAssignmentGeneratedRequest(TransitionTripGuideAssignmentRequest request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "tripId": request.tripId,
      "taskKey": request.taskKey,
    },
    body: <String, Object?>{
      "expectedVersion": request.expectedVersion,
      "targetStatus": request.targetStatus.wireName,
    },
  );
}

CloudOperationRequestPayload encodeTravelTripMapViewGetTripMapGeneratedRequest(GetTripMapQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "tripId": request.tripId,
    },
  );
}

CloudOperationRequestPayload encodeTravelTripMembershipDepartTripMembershipGeneratedRequest(DepartTripMembershipRequest request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "tripId": request.tripId,
      "personaId": request.personaId,
    },
    body: <String, Object?>{
      "expectedVersion": request.expectedVersion,
      "reason": request.reason,
    },
  );
}

CloudOperationRequestPayload encodeTravelTripMembershipListTripMembershipsGeneratedRequest(ListTripMembershipsQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "tripId": request.tripId,
    },
  );
}

CloudOperationRequestPayload encodeTravelTripMembershipPutTripMembershipGeneratedRequest(PutTripMembershipRequest request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "tripId": request.tripId,
      "personaId": request.personaId,
    },
    body: <String, Object?>{
      "role": request.role.wireName,
      "sourceKind": request.sourceKind.wireName,
      if (request.sourceObjectRef != null) "sourceObjectRef": request.sourceObjectRef!.toWire(),
      "sourceVersion": request.sourceVersion,
      "expectedVersion": request.expectedVersion,
    },
  );
}

CloudOperationRequestPayload encodeTravelTripMomentAssignTripMomentGeneratedRequest(AssignTripMomentRequest request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "tripId": request.tripId,
      "momentId": request.momentId,
    },
    body: <String, Object?>{
      "expectedVersion": request.expectedVersion,
      "revisionNumber": request.revisionNumber,
      "dayIndex": request.dayIndex,
      if (request.itemId != null) "itemId": request.itemId!,
      "visibility": request.visibility.wireName,
      "sourceVersion": request.sourceVersion,
    },
  );
}

CloudOperationRequestPayload encodeTravelTripMomentCreateTripMomentGeneratedRequest(CreateTripMomentRequest request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "tripId": request.tripId,
    },
    body: <String, Object?>{
      "revisionNumber": request.revisionNumber,
      if (request.dayIndex != null) "dayIndex": request.dayIndex!,
      if (request.itemId != null) "itemId": request.itemId!,
      "kind": request.kind.wireName,
      if (request.contentRef != null) "contentRef": request.contentRef!.toWire(),
      if (request.inlineText != null) "inlineText": request.inlineText!,
      "capturedAt": request.capturedAt.toUtc().toIso8601String(),
      if (request.coarsePlaceRef != null) "coarsePlaceRef": request.coarsePlaceRef!.toWire(),
      "visibility": request.visibility.wireName,
      "assignmentStatus": request.assignmentStatus.wireName,
      "sourceVersion": request.sourceVersion,
    },
  );
}

CloudOperationRequestPayload encodeTravelTripMomentDeleteTripMomentGeneratedRequest(DeleteTripMomentRequest request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "tripId": request.tripId,
      "momentId": request.momentId,
    },
    body: <String, Object?>{
      "expectedVersion": request.expectedVersion,
      "reason": request.reason,
    },
  );
}

CloudOperationRequestPayload encodeTravelTripMomentListTripMomentsGeneratedRequest(ListTripMomentsQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "tripId": request.tripId,
    },
  );
}

CloudOperationRequestPayload encodeTravelTripPlanCreateTripPlanGeneratedRequest(CreateTripPlanCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "title": request.title,
      if (request.startAt != null) "startAt": request.startAt!.toUtc().toIso8601String(),
      if (request.endAt != null) "endAt": request.endAt!.toUtc().toIso8601String(),
      "items": request.items.map((value) => value.toWire()).toList(growable: false),
    },
  );
}

CloudOperationRequestPayload encodeTravelTripPlanCreateTripPlanFromTemplateGeneratedRequest(CreateTripPlanFromTemplateCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "templateId": request.templateId,
    },
    body: <String, Object?>{
      if (request.title != null) "title": request.title!,
      if (request.startAt != null) "startAt": request.startAt!.toUtc().toIso8601String(),
      if (request.endAt != null) "endAt": request.endAt!.toUtc().toIso8601String(),
    },
  );
}

CloudOperationRequestPayload encodeTravelTripPlanGetTripPlanGeneratedRequest(TripPlanIDQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "tripId": request.tripId,
    },
  );
}

CloudOperationRequestPayload encodeTravelTripPlanListTripPlansGeneratedRequest(ListTripPlansQuery request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      if (request.status != null) "status": (request.status!.wireName).toString(),
      if (request.cursor != null) "cursor": request.cursor!,
      if (request.limit != null) "limit": (request.limit!).toString(),
    },
  );
}

CloudOperationRequestPayload encodeTravelTripPlanReviseTripPlanGeneratedRequest(ReviseTripPlanCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "tripId": request.tripId,
    },
    body: <String, Object?>{
      "expectedRevisionNumber": request.expectedRevisionNumber,
      "changeReason": request.changeReason,
      "severity": request.severity.wireName,
      "items": request.items.map((value) => value.toWire()).toList(growable: false),
    },
  );
}

CloudOperationRequestPayload encodeTravelTripPlanTransitionTripPlanGeneratedRequest(TransitionTripPlanCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "tripId": request.tripId,
    },
    body: <String, Object?>{
      "expectedRevisionNumber": request.expectedRevisionNumber,
      "targetStatus": request.targetStatus.wireName,
    },
  );
}

CloudOperationRequestPayload encodeTravelTripPlanContentLinkListTripPlanContentLinksGeneratedRequest(ListTripPlanContentLinksQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "tripId": request.tripId,
    },
  );
}

CloudOperationRequestPayload encodeTravelTripPlanContentLinkPutTripPlanContentLinkGeneratedRequest(PutTripPlanContentLinkRequest request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "tripId": request.tripId,
      "postId": request.postId,
    },
    body: <String, Object?>{
      "expectedVersion": request.expectedVersion,
      "revisionNumber": request.revisionNumber,
      "targetKind": request.targetKind.wireName,
      if (request.dayIndex != null) "dayIndex": request.dayIndex!,
      if (request.itemId != null) "itemId": request.itemId!,
      "visibility": request.visibility.wireName,
      "sourceVersion": request.sourceVersion,
    },
  );
}

CloudOperationRequestPayload encodeTravelTripPlanContentLinkRemoveTripPlanContentLinkGeneratedRequest(RemoveTripPlanContentLinkRequest request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "tripId": request.tripId,
      "postId": request.postId,
    },
    body: <String, Object?>{
      "expectedVersion": request.expectedVersion,
      "reason": request.reason,
    },
  );
}

CloudOperationRequestPayload encodeTravelTripPlanPlacementListSurfaceTripPlacementsGeneratedRequest(ListSurfaceTripPlacementsQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "surfaceKind": (request.surfaceKind.wireName).toString(),
      "surfaceId": request.surfaceId,
    },
  );
}

CloudOperationRequestPayload encodeTravelTripPlanPlacementListTripPlanPlacementsGeneratedRequest(ListTripPlanPlacementsQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "tripId": request.tripId,
    },
  );
}

CloudOperationRequestPayload encodeTravelTripPlanPlacementPutTripPlanPlacementGeneratedRequest(PutTripPlanPlacementRequest request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "tripId": request.tripId,
      "surfaceKind": (request.surfaceKind.wireName).toString(),
      "surfaceId": request.surfaceId,
    },
    body: <String, Object?>{
      "sourceVersion": request.sourceVersion,
      "expectedVersion": request.expectedVersion,
    },
  );
}

CloudOperationRequestPayload encodeTravelTripPlanPlacementRemoveTripPlanPlacementGeneratedRequest(RemoveTripPlanPlacementRequest request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "tripId": request.tripId,
      "surfaceKind": (request.surfaceKind.wireName).toString(),
      "surfaceId": request.surfaceId,
    },
    body: <String, Object?>{
      "sourceVersion": request.sourceVersion,
      "expectedVersion": request.expectedVersion,
    },
  );
}

CloudOperationRequestPayload encodeTravelTripPlanTemplateCreateTripPlanTemplateGeneratedRequest(CreateTripPlanTemplateRequest request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "title": request.title,
      if (request.summary != null) "summary": request.summary!,
      "dayCount": request.dayCount,
      "items": request.items.map((value) => value.toWire()).toList(growable: false),
      "attributions": request.attributions.map((value) => value.toWire()).toList(growable: false),
    },
  );
}

CloudOperationRequestPayload encodeTravelTripPlanTemplateGetTripPlanTemplateGeneratedRequest(GetTripPlanTemplateQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "templateId": request.templateId,
    },
  );
}

CloudOperationRequestPayload encodeTravelTripPlanTemplateListTripPlanTemplatesGeneratedRequest(ListTripPlanTemplatesQuery request) {
  return CloudOperationRequestPayload(
  );
}

CloudOperationRequestPayload encodeTravelTripPlanTemplateReviseTripPlanTemplateGeneratedRequest(PutTripPlanTemplateRequest request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "templateId": request.templateId,
    },
    body: <String, Object?>{
      "expectedVersion": request.expectedVersion,
      "title": request.title,
      if (request.summary != null) "summary": request.summary!,
      "dayCount": request.dayCount,
      "items": request.items.map((value) => value.toWire()).toList(growable: false),
      "attributions": request.attributions.map((value) => value.toWire()).toList(growable: false),
    },
  );
}

CloudOperationRequestPayload encodeTravelTripShareSnapshotCreateTripShareSnapshotGeneratedRequest(CreateTripShareSnapshotRequest request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "tripId": request.tripId,
    },
    body: <String, Object?>{
      "sourceRevisionId": request.sourceRevisionId,
      "sourceDigest": request.sourceDigest,
      "scope": request.scope.wireName,
      if (request.dayIndex != null) "dayIndex": request.dayIndex!,
      if (request.itemId != null) "itemId": request.itemId!,
      "momentIds": request.momentIds.map((value) => value).toList(growable: false),
      "visibility": request.visibility.wireName,
    },
  );
}

CloudOperationRequestPayload encodeTravelTripShareSnapshotGetTripShareSnapshotGeneratedRequest(GetTripShareSnapshotQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "snapshotId": request.snapshotId,
    },
  );
}

CloudOperationRequestPayload encodeTravelTripTimelineViewGetTripTimelineGeneratedRequest(GetTripTimelineQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "tripId": request.tripId,
    },
  );
}

