// Code generated from canonical domain contracts. DO NOT EDIT.
// ContractGraph SHA256: 9816b2b7d9fedea34ad78dd719fc16fdf3e982073304d7f50f7a8ea4064f6b7f

library;

import '../operation_request_payload.dart';

part '../generated/requests/travel/travel_operation_contracts.g.requests.g.dart';

enum TripGuideAssignmentStatus {
  assigned("assigned"),
  accepted("accepted"),
  inProgress("in_progress"),
  completed("completed"),
  cancelled("cancelled");

  const TripGuideAssignmentStatus(this.wireName);

  final String wireName;

  static TripGuideAssignmentStatus fromWire(Object? value, String path) {
    return switch (value) {
      "assigned" => TripGuideAssignmentStatus.assigned,
      "accepted" => TripGuideAssignmentStatus.accepted,
      "in_progress" => TripGuideAssignmentStatus.inProgress,
      "completed" => TripGuideAssignmentStatus.completed,
      "cancelled" => TripGuideAssignmentStatus.cancelled,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum TripGuideAttributionKind {
  administrative("administrative"),
  generalFact("general_fact"),
  professionalCommentary("professional_commentary");

  const TripGuideAttributionKind(this.wireName);

  final String wireName;

  static TripGuideAttributionKind fromWire(Object? value, String path) {
    return switch (value) {
      "administrative" => TripGuideAttributionKind.administrative,
      "general_fact" => TripGuideAttributionKind.generalFact,
      "professional_commentary" => TripGuideAttributionKind.professionalCommentary,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum TripGuideRole {
  leader("leader"),
  assistantGuide("assistant_guide"),
  licensedGuide("licensed_guide"),
  localExpert("local_expert");

  const TripGuideRole(this.wireName);

  final String wireName;

  static TripGuideRole fromWire(Object? value, String path) {
    return switch (value) {
      "leader" => TripGuideRole.leader,
      "assistant_guide" => TripGuideRole.assistantGuide,
      "licensed_guide" => TripGuideRole.licensedGuide,
      "local_expert" => TripGuideRole.localExpert,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum TripGuideTaskKind {
  collection("collection"),
  briefing("briefing"),
  routeGuidance("route_guidance"),
  commentary("commentary"),
  generalSupport("general_support");

  const TripGuideTaskKind(this.wireName);

  final String wireName;

  static TripGuideTaskKind fromWire(Object? value, String path) {
    return switch (value) {
      "collection" => TripGuideTaskKind.collection,
      "briefing" => TripGuideTaskKind.briefing,
      "route_guidance" => TripGuideTaskKind.routeGuidance,
      "commentary" => TripGuideTaskKind.commentary,
      "general_support" => TripGuideTaskKind.generalSupport,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum TripMembershipRole {
  organizer("organizer"),
  participant("participant"),
  leader("leader"),
  assistantGuide("assistant_guide"),
  guide("guide"),
  localExpert("local_expert");

  const TripMembershipRole(this.wireName);

  final String wireName;

  static TripMembershipRole fromWire(Object? value, String path) {
    return switch (value) {
      "organizer" => TripMembershipRole.organizer,
      "participant" => TripMembershipRole.participant,
      "leader" => TripMembershipRole.leader,
      "assistant_guide" => TripMembershipRole.assistantGuide,
      "guide" => TripMembershipRole.guide,
      "local_expert" => TripMembershipRole.localExpert,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum TripMembershipSourceKind {
  tripInvitation("trip_invitation"),
  conversation("conversation"),
  circle("circle"),
  gathering("gathering");

  const TripMembershipSourceKind(this.wireName);

  final String wireName;

  static TripMembershipSourceKind fromWire(Object? value, String path) {
    return switch (value) {
      "trip_invitation" => TripMembershipSourceKind.tripInvitation,
      "conversation" => TripMembershipSourceKind.conversation,
      "circle" => TripMembershipSourceKind.circle,
      "gathering" => TripMembershipSourceKind.gathering,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum TripMembershipState {
  active("active"),
  left("left"),
  revoked("revoked");

  const TripMembershipState(this.wireName);

  final String wireName;

  static TripMembershipState fromWire(Object? value, String path) {
    return switch (value) {
      "active" => TripMembershipState.active,
      "left" => TripMembershipState.left,
      "revoked" => TripMembershipState.revoked,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum TripMomentAssignmentStatus {
  unassigned("unassigned"),
  suggested("suggested"),
  confirmed("confirmed");

  const TripMomentAssignmentStatus(this.wireName);

  final String wireName;

  static TripMomentAssignmentStatus fromWire(Object? value, String path) {
    return switch (value) {
      "unassigned" => TripMomentAssignmentStatus.unassigned,
      "suggested" => TripMomentAssignmentStatus.suggested,
      "confirmed" => TripMomentAssignmentStatus.confirmed,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum TripMomentKind {
  photo("photo"),
  video("video"),
  voice("voice"),
  text("text"),
  checkIn("check_in"),
  postReference("post_reference");

  const TripMomentKind(this.wireName);

  final String wireName;

  static TripMomentKind fromWire(Object? value, String path) {
    return switch (value) {
      "photo" => TripMomentKind.photo,
      "video" => TripMomentKind.video,
      "voice" => TripMomentKind.voice,
      "text" => TripMomentKind.text,
      "check_in" => TripMomentKind.checkIn,
      "post_reference" => TripMomentKind.postReference,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum TripMomentStatus {
  active("active"),
  deleted("deleted");

  const TripMomentStatus(this.wireName);

  final String wireName;

  static TripMomentStatus fromWire(Object? value, String path) {
    return switch (value) {
      "active" => TripMomentStatus.active,
      "deleted" => TripMomentStatus.deleted,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum TripMomentVisibility {
  personal("personal"),
  tripMembers("trip_members"),
  public("public");

  const TripMomentVisibility(this.wireName);

  final String wireName;

  static TripMomentVisibility fromWire(Object? value, String path) {
    return switch (value) {
      "personal" => TripMomentVisibility.personal,
      "trip_members" => TripMomentVisibility.tripMembers,
      "public" => TripMomentVisibility.public,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum TripPlacementSurfaceKind {
  conversation("conversation"),
  circle("circle");

  const TripPlacementSurfaceKind(this.wireName);

  final String wireName;

  static TripPlacementSurfaceKind fromWire(Object? value, String path) {
    return switch (value) {
      "conversation" => TripPlacementSurfaceKind.conversation,
      "circle" => TripPlacementSurfaceKind.circle,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum TripPlanContentLinkStatus {
  active("active"),
  removed("removed");

  const TripPlanContentLinkStatus(this.wireName);

  final String wireName;

  static TripPlanContentLinkStatus fromWire(Object? value, String path) {
    return switch (value) {
      "active" => TripPlanContentLinkStatus.active,
      "removed" => TripPlanContentLinkStatus.removed,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum TripPlanContentLinkTargetKind {
  trip("trip"),
  day("day"),
  item("item");

  const TripPlanContentLinkTargetKind(this.wireName);

  final String wireName;

  static TripPlanContentLinkTargetKind fromWire(Object? value, String path) {
    return switch (value) {
      "trip" => TripPlanContentLinkTargetKind.trip,
      "day" => TripPlanContentLinkTargetKind.day,
      "item" => TripPlanContentLinkTargetKind.item,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum TripPlanContentLinkVisibility {
  tripMembers("trip_members"),
  public("public");

  const TripPlanContentLinkVisibility(this.wireName);

  final String wireName;

  static TripPlanContentLinkVisibility fromWire(Object? value, String path) {
    return switch (value) {
      "trip_members" => TripPlanContentLinkVisibility.tripMembers,
      "public" => TripPlanContentLinkVisibility.public,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum TripPlanItemKind {
  stay("stay"),
  food("food"),
  sight("sight"),
  activity("activity"),
  transport("transport"),
  rest("rest"),
  freeTime("free_time");

  const TripPlanItemKind(this.wireName);

  final String wireName;

  static TripPlanItemKind fromWire(Object? value, String path) {
    return switch (value) {
      "stay" => TripPlanItemKind.stay,
      "food" => TripPlanItemKind.food,
      "sight" => TripPlanItemKind.sight,
      "activity" => TripPlanItemKind.activity,
      "transport" => TripPlanItemKind.transport,
      "rest" => TripPlanItemKind.rest,
      "free_time" => TripPlanItemKind.freeTime,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum TripPlanPlacementStatus {
  active("active"),
  removed("removed");

  const TripPlanPlacementStatus(this.wireName);

  final String wireName;

  static TripPlanPlacementStatus fromWire(Object? value, String path) {
    return switch (value) {
      "active" => TripPlanPlacementStatus.active,
      "removed" => TripPlanPlacementStatus.removed,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum TripPlanSourceAttributionKind {
  publicSource("public_source"),
  professionalCommentary("professional_commentary");

  const TripPlanSourceAttributionKind(this.wireName);

  final String wireName;

  static TripPlanSourceAttributionKind fromWire(Object? value, String path) {
    return switch (value) {
      "public_source" => TripPlanSourceAttributionKind.publicSource,
      "professional_commentary" => TripPlanSourceAttributionKind.professionalCommentary,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum TripPlanStatus {
  planning("planning"),
  active("active"),
  completed("completed"),
  archived("archived");

  const TripPlanStatus(this.wireName);

  final String wireName;

  static TripPlanStatus fromWire(Object? value, String path) {
    return switch (value) {
      "planning" => TripPlanStatus.planning,
      "active" => TripPlanStatus.active,
      "completed" => TripPlanStatus.completed,
      "archived" => TripPlanStatus.archived,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum TripPlanTemplateAttributionKind {
  publicSource("public_source"),
  professionalCommentary("professional_commentary");

  const TripPlanTemplateAttributionKind(this.wireName);

  final String wireName;

  static TripPlanTemplateAttributionKind fromWire(Object? value, String path) {
    return switch (value) {
      "public_source" => TripPlanTemplateAttributionKind.publicSource,
      "professional_commentary" => TripPlanTemplateAttributionKind.professionalCommentary,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum TripPlanTemplateStatus {
  active("active"),
  archived("archived");

  const TripPlanTemplateStatus(this.wireName);

  final String wireName;

  static TripPlanTemplateStatus fromWire(Object? value, String path) {
    return switch (value) {
      "active" => TripPlanTemplateStatus.active,
      "archived" => TripPlanTemplateStatus.archived,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum TripRevisionSeverity {
  minor("minor"),
  important("important"),
  critical("critical");

  const TripRevisionSeverity(this.wireName);

  final String wireName;

  static TripRevisionSeverity fromWire(Object? value, String path) {
    return switch (value) {
      "minor" => TripRevisionSeverity.minor,
      "important" => TripRevisionSeverity.important,
      "critical" => TripRevisionSeverity.critical,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum TripShareSnapshotScope {
  full("full"),
  day("day"),
  item("item"),
  route("route"),
  momentCollection("moment_collection");

  const TripShareSnapshotScope(this.wireName);

  final String wireName;

  static TripShareSnapshotScope fromWire(Object? value, String path) {
    return switch (value) {
      "full" => TripShareSnapshotScope.full,
      "day" => TripShareSnapshotScope.day,
      "item" => TripShareSnapshotScope.item,
      "route" => TripShareSnapshotScope.route,
      "moment_collection" => TripShareSnapshotScope.momentCollection,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum TripShareSnapshotStatus {
  active("active");

  const TripShareSnapshotStatus(this.wireName);

  final String wireName;

  static TripShareSnapshotStatus fromWire(Object? value, String path) {
    return switch (value) {
      "active" => TripShareSnapshotStatus.active,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum TripShareSnapshotVisibility {
  tripMembers("trip_members"),
  public("public");

  const TripShareSnapshotVisibility(this.wireName);

  final String wireName;

  static TripShareSnapshotVisibility fromWire(Object? value, String path) {
    return switch (value) {
      "trip_members" => TripShareSnapshotVisibility.tripMembers,
      "public" => TripShareSnapshotVisibility.public,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

final class TripGuideAssignment {
  const TripGuideAssignment({
    required this.id,
    required this.version,
    required this.tripId,
    required this.taskKey,
    required this.assigneePersonaId,
    required this.role,
    required this.taskKind,
    required this.title,
    this.dueAt,
    required this.sourceRevisionNumber,
    required this.attributionKind,
    required this.attributionPersonaId,
    this.publicQualificationPersonaId,
    required this.status,
    required this.createdByPersonaId,
    required this.createdAt,
    required this.updatedAt,
  });

  final String id;
  final int version;
  final String tripId;
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
  final TripGuideAssignmentStatus status;
  final String createdByPersonaId;
  final DateTime createdAt;
  final DateTime updatedAt;

  factory TripGuideAssignment.fromWire(Map<String, Object?> map, [String path = "TripGuideAssignment"]) {
    _rejectUnknownFields(map, const <String>{"id", "version", "tripId", "taskKey", "assigneePersonaId", "role", "taskKind", "title", "dueAt", "sourceRevisionNumber", "attributionKind", "attributionPersonaId", "publicQualificationPersonaId", "status", "createdByPersonaId", "createdAt", "updatedAt"}, path);
    return TripGuideAssignment(
      id: _requiredString(map["id"], '$path.id'),
      version: _requiredInt(map["version"], '$path.version'),
      tripId: _requiredString(map["tripId"], '$path.tripId'),
      taskKey: _requiredString(map["taskKey"], '$path.taskKey'),
      assigneePersonaId: _requiredString(map["assigneePersonaId"], '$path.assigneePersonaId'),
      role: TripGuideRole.fromWire(map["role"], '$path.role'),
      taskKind: TripGuideTaskKind.fromWire(map["taskKind"], '$path.taskKind'),
      title: _requiredString(map["title"], '$path.title'),
      dueAt: map["dueAt"] == null ? null : _requiredTimestamp(map["dueAt"], '$path.dueAt'),
      sourceRevisionNumber: _requiredInt(map["sourceRevisionNumber"], '$path.sourceRevisionNumber'),
      attributionKind: TripGuideAttributionKind.fromWire(map["attributionKind"], '$path.attributionKind'),
      attributionPersonaId: _requiredString(map["attributionPersonaId"], '$path.attributionPersonaId'),
      publicQualificationPersonaId: map["publicQualificationPersonaId"] == null ? null : _requiredString(map["publicQualificationPersonaId"], '$path.publicQualificationPersonaId'),
      status: TripGuideAssignmentStatus.fromWire(map["status"], '$path.status'),
      createdByPersonaId: _requiredString(map["createdByPersonaId"], '$path.createdByPersonaId'),
      createdAt: _requiredTimestamp(map["createdAt"], '$path.createdAt'),
      updatedAt: _requiredTimestamp(map["updatedAt"], '$path.updatedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "id": id,
    "version": version,
    "tripId": tripId,
    "taskKey": taskKey,
    "assigneePersonaId": assigneePersonaId,
    "role": role.wireName,
    "taskKind": taskKind.wireName,
    "title": title,
    if (dueAt != null) "dueAt": dueAt!.toUtc().toIso8601String(),
    "sourceRevisionNumber": sourceRevisionNumber,
    "attributionKind": attributionKind.wireName,
    "attributionPersonaId": attributionPersonaId,
    if (publicQualificationPersonaId != null) "publicQualificationPersonaId": publicQualificationPersonaId!,
    "status": status.wireName,
    "createdByPersonaId": createdByPersonaId,
    "createdAt": createdAt.toUtc().toIso8601String(),
    "updatedAt": updatedAt.toUtc().toIso8601String(),
  };
}

final class TripGuideAssignmentListSlice {
  const TripGuideAssignmentListSlice({
    required this.tripId,
    required this.assignments,
  });

  final String tripId;
  final List<TripGuideAssignment> assignments;

  factory TripGuideAssignmentListSlice.fromWire(Map<String, Object?> map, [String path = "TripGuideAssignmentListSlice"]) {
    _rejectUnknownFields(map, const <String>{"tripId", "assignments"}, path);
    return TripGuideAssignmentListSlice(
      tripId: _requiredNonBlankString(map["tripId"], '$path.tripId'),
      assignments: List<TripGuideAssignment>.unmodifiable(_requiredList(map["assignments"], '$path.assignments').asMap().entries.map((entry) => TripGuideAssignment.fromWire(_requiredObject(entry.value, '$path.assignments' + '[${entry.key}]'), '$path.assignments' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "tripId": tripId,
    "assignments": assignments.map((value) => value.toWire()).toList(growable: false),
  };
}

final class TripMapMomentMarkerSlice {
  const TripMapMomentMarkerSlice({
    required this.momentId,
    required this.dayIndex,
    this.itemId,
    required this.placeRef,
  });

  final String momentId;
  final int dayIndex;
  final String? itemId;
  final TripMapPlaceRef placeRef;

  factory TripMapMomentMarkerSlice.fromWire(Map<String, Object?> map, [String path = "TripMapMomentMarkerSlice"]) {
    _rejectUnknownFields(map, const <String>{"momentId", "dayIndex", "itemId", "placeRef"}, path);
    return TripMapMomentMarkerSlice(
      momentId: _requiredString(map["momentId"], '$path.momentId'),
      dayIndex: _requiredInt(map["dayIndex"], '$path.dayIndex'),
      itemId: map["itemId"] == null ? null : _requiredString(map["itemId"], '$path.itemId'),
      placeRef: TripMapPlaceRef.fromWire(_requiredObject(map["placeRef"], '$path.placeRef'), '$path.placeRef'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "momentId": momentId,
    "dayIndex": dayIndex,
    if (itemId != null) "itemId": itemId!,
    "placeRef": placeRef.toWire(),
  };
}

final class TripMapPlaceRef {
  const TripMapPlaceRef({
    required this.objectTypeRef,
    required this.objectId,
  });

  final String objectTypeRef;
  final String objectId;

  factory TripMapPlaceRef.fromWire(Map<String, Object?> map, [String path = "TripMapPlaceRef"]) {
    _rejectUnknownFields(map, const <String>{"objectTypeRef", "objectId"}, path);
    return TripMapPlaceRef(
      objectTypeRef: _requiredNonBlankString(map["objectTypeRef"], '$path.objectTypeRef'),
      objectId: _requiredNonBlankString(map["objectId"], '$path.objectId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "objectTypeRef": objectTypeRef,
    "objectId": objectId,
  };
}

final class TripMapRouteSegmentSlice {
  const TripMapRouteSegmentSlice({
    required this.segmentId,
    required this.sequence,
    required this.fromStopId,
    required this.toStopId,
  });

  final String segmentId;
  final int sequence;
  final String fromStopId;
  final String toStopId;

  factory TripMapRouteSegmentSlice.fromWire(Map<String, Object?> map, [String path = "TripMapRouteSegmentSlice"]) {
    _rejectUnknownFields(map, const <String>{"segmentId", "sequence", "fromStopId", "toStopId"}, path);
    return TripMapRouteSegmentSlice(
      segmentId: _requiredString(map["segmentId"], '$path.segmentId'),
      sequence: _requiredInt(map["sequence"], '$path.sequence'),
      fromStopId: _requiredString(map["fromStopId"], '$path.fromStopId'),
      toStopId: _requiredString(map["toStopId"], '$path.toStopId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "segmentId": segmentId,
    "sequence": sequence,
    "fromStopId": fromStopId,
    "toStopId": toStopId,
  };
}

final class TripMapStopSlice {
  const TripMapStopSlice({
    required this.stopId,
    required this.sequence,
    required this.dayIndex,
    required this.itemId,
    required this.title,
    required this.placeRef,
    required this.momentIds,
    required this.contentLinkIds,
  });

  final String stopId;
  final int sequence;
  final int dayIndex;
  final String itemId;
  final String title;
  final TripMapPlaceRef placeRef;
  final List<String> momentIds;
  final List<String> contentLinkIds;

  factory TripMapStopSlice.fromWire(Map<String, Object?> map, [String path = "TripMapStopSlice"]) {
    _rejectUnknownFields(map, const <String>{"stopId", "sequence", "dayIndex", "itemId", "title", "placeRef", "momentIds", "contentLinkIds"}, path);
    return TripMapStopSlice(
      stopId: _requiredString(map["stopId"], '$path.stopId'),
      sequence: _requiredInt(map["sequence"], '$path.sequence'),
      dayIndex: _requiredInt(map["dayIndex"], '$path.dayIndex'),
      itemId: _requiredString(map["itemId"], '$path.itemId'),
      title: _requiredString(map["title"], '$path.title'),
      placeRef: TripMapPlaceRef.fromWire(_requiredObject(map["placeRef"], '$path.placeRef'), '$path.placeRef'),
      momentIds: List<String>.unmodifiable(_requiredList(map["momentIds"], '$path.momentIds').asMap().entries.map((entry) => _requiredString(entry.value, '$path.momentIds' + '[${entry.key}]'))),
      contentLinkIds: List<String>.unmodifiable(_requiredList(map["contentLinkIds"], '$path.contentLinkIds').asMap().entries.map((entry) => _requiredString(entry.value, '$path.contentLinkIds' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "stopId": stopId,
    "sequence": sequence,
    "dayIndex": dayIndex,
    "itemId": itemId,
    "title": title,
    "placeRef": placeRef.toWire(),
    "momentIds": momentIds.map((value) => value).toList(growable: false),
    "contentLinkIds": contentLinkIds.map((value) => value).toList(growable: false),
  };
}

final class TripMapView {
  const TripMapView({
    required this.tripId,
    required this.currentRevisionId,
    required this.currentRevisionNumber,
    required this.stops,
    required this.routeSegments,
    required this.momentMarkers,
    required this.sourceMomentIds,
    required this.sourceContentLinkIds,
    required this.sourceDigest,
    required this.sourceEventId,
    required this.projectedAt,
  });

  final String tripId;
  final String currentRevisionId;
  final int currentRevisionNumber;
  final List<TripMapStopSlice> stops;
  final List<TripMapRouteSegmentSlice> routeSegments;
  final List<TripMapMomentMarkerSlice> momentMarkers;
  final List<String> sourceMomentIds;
  final List<String> sourceContentLinkIds;
  final String sourceDigest;
  final String sourceEventId;
  final DateTime projectedAt;

  factory TripMapView.fromWire(Map<String, Object?> map, [String path = "TripMapView"]) {
    _rejectUnknownFields(map, const <String>{"tripId", "currentRevisionId", "currentRevisionNumber", "stops", "routeSegments", "momentMarkers", "sourceMomentIds", "sourceContentLinkIds", "sourceDigest", "sourceEventId", "projectedAt"}, path);
    return TripMapView(
      tripId: _requiredString(map["tripId"], '$path.tripId'),
      currentRevisionId: _requiredString(map["currentRevisionId"], '$path.currentRevisionId'),
      currentRevisionNumber: _requiredInt(map["currentRevisionNumber"], '$path.currentRevisionNumber'),
      stops: List<TripMapStopSlice>.unmodifiable(_requiredList(map["stops"], '$path.stops').asMap().entries.map((entry) => TripMapStopSlice.fromWire(_requiredObject(entry.value, '$path.stops' + '[${entry.key}]'), '$path.stops' + '[${entry.key}]'))),
      routeSegments: List<TripMapRouteSegmentSlice>.unmodifiable(_requiredList(map["routeSegments"], '$path.routeSegments').asMap().entries.map((entry) => TripMapRouteSegmentSlice.fromWire(_requiredObject(entry.value, '$path.routeSegments' + '[${entry.key}]'), '$path.routeSegments' + '[${entry.key}]'))),
      momentMarkers: List<TripMapMomentMarkerSlice>.unmodifiable(_requiredList(map["momentMarkers"], '$path.momentMarkers').asMap().entries.map((entry) => TripMapMomentMarkerSlice.fromWire(_requiredObject(entry.value, '$path.momentMarkers' + '[${entry.key}]'), '$path.momentMarkers' + '[${entry.key}]'))),
      sourceMomentIds: List<String>.unmodifiable(_requiredList(map["sourceMomentIds"], '$path.sourceMomentIds').asMap().entries.map((entry) => _requiredString(entry.value, '$path.sourceMomentIds' + '[${entry.key}]'))),
      sourceContentLinkIds: List<String>.unmodifiable(_requiredList(map["sourceContentLinkIds"], '$path.sourceContentLinkIds').asMap().entries.map((entry) => _requiredString(entry.value, '$path.sourceContentLinkIds' + '[${entry.key}]'))),
      sourceDigest: _requiredString(map["sourceDigest"], '$path.sourceDigest'),
      sourceEventId: _requiredString(map["sourceEventId"], '$path.sourceEventId'),
      projectedAt: _requiredTimestamp(map["projectedAt"], '$path.projectedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "tripId": tripId,
    "currentRevisionId": currentRevisionId,
    "currentRevisionNumber": currentRevisionNumber,
    "stops": stops.map((value) => value.toWire()).toList(growable: false),
    "routeSegments": routeSegments.map((value) => value.toWire()).toList(growable: false),
    "momentMarkers": momentMarkers.map((value) => value.toWire()).toList(growable: false),
    "sourceMomentIds": sourceMomentIds.map((value) => value).toList(growable: false),
    "sourceContentLinkIds": sourceContentLinkIds.map((value) => value).toList(growable: false),
    "sourceDigest": sourceDigest,
    "sourceEventId": sourceEventId,
    "projectedAt": projectedAt.toUtc().toIso8601String(),
  };
}

final class TripMembershipListSlice {
  const TripMembershipListSlice({
    required this.tripId,
    required this.memberships,
  });

  final String tripId;
  final List<TripMembershipSlice> memberships;

  factory TripMembershipListSlice.fromWire(Map<String, Object?> map, [String path = "TripMembershipListSlice"]) {
    _rejectUnknownFields(map, const <String>{"tripId", "memberships"}, path);
    return TripMembershipListSlice(
      tripId: _requiredString(map["tripId"], '$path.tripId'),
      memberships: List<TripMembershipSlice>.unmodifiable(_requiredList(map["memberships"], '$path.memberships').asMap().entries.map((entry) => TripMembershipSlice.fromWire(_requiredObject(entry.value, '$path.memberships' + '[${entry.key}]'), '$path.memberships' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "tripId": tripId,
    "memberships": memberships.map((value) => value.toWire()).toList(growable: false),
  };
}

final class TripMembershipSlice {
  const TripMembershipSlice({
    required this.membershipId,
    required this.version,
    required this.tripId,
    required this.personaId,
    required this.role,
    required this.state,
    required this.sourceKind,
    this.sourceObjectRef,
    required this.sourceVersion,
    required this.joinedAt,
    required this.updatedAt,
  });

  final String membershipId;
  final int version;
  final String tripId;
  final String personaId;
  final TripMembershipRole role;
  final TripMembershipState state;
  final TripMembershipSourceKind sourceKind;
  final TripMembershipSourceRef? sourceObjectRef;
  final int sourceVersion;
  final DateTime joinedAt;
  final DateTime updatedAt;

  factory TripMembershipSlice.fromWire(Map<String, Object?> map, [String path = "TripMembershipSlice"]) {
    _rejectUnknownFields(map, const <String>{"membershipId", "version", "tripId", "personaId", "role", "state", "sourceKind", "sourceObjectRef", "sourceVersion", "joinedAt", "updatedAt"}, path);
    return TripMembershipSlice(
      membershipId: _requiredString(map["membershipId"], '$path.membershipId'),
      version: _requiredInt(map["version"], '$path.version'),
      tripId: _requiredString(map["tripId"], '$path.tripId'),
      personaId: _requiredString(map["personaId"], '$path.personaId'),
      role: TripMembershipRole.fromWire(map["role"], '$path.role'),
      state: TripMembershipState.fromWire(map["state"], '$path.state'),
      sourceKind: TripMembershipSourceKind.fromWire(map["sourceKind"], '$path.sourceKind'),
      sourceObjectRef: map["sourceObjectRef"] == null ? null : TripMembershipSourceRef.fromWire(_requiredObject(map["sourceObjectRef"], '$path.sourceObjectRef'), '$path.sourceObjectRef'),
      sourceVersion: _requiredInt(map["sourceVersion"], '$path.sourceVersion'),
      joinedAt: _requiredTimestamp(map["joinedAt"], '$path.joinedAt'),
      updatedAt: _requiredTimestamp(map["updatedAt"], '$path.updatedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "membershipId": membershipId,
    "version": version,
    "tripId": tripId,
    "personaId": personaId,
    "role": role.wireName,
    "state": state.wireName,
    "sourceKind": sourceKind.wireName,
    if (sourceObjectRef != null) "sourceObjectRef": sourceObjectRef!.toWire(),
    "sourceVersion": sourceVersion,
    "joinedAt": joinedAt.toUtc().toIso8601String(),
    "updatedAt": updatedAt.toUtc().toIso8601String(),
  };
}

final class TripMembershipSourceRef {
  const TripMembershipSourceRef({
    required this.objectTypeRef,
    required this.objectId,
  });

  final String objectTypeRef;
  final String objectId;

  factory TripMembershipSourceRef.fromWire(Map<String, Object?> map, [String path = "TripMembershipSourceRef"]) {
    _rejectUnknownFields(map, const <String>{"objectTypeRef", "objectId"}, path);
    return TripMembershipSourceRef(
      objectTypeRef: _requiredNonBlankString(map["objectTypeRef"], '$path.objectTypeRef'),
      objectId: _requiredNonBlankString(map["objectId"], '$path.objectId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "objectTypeRef": objectTypeRef,
    "objectId": objectId,
  };
}

final class TripMomentListSlice {
  const TripMomentListSlice({
    required this.tripId,
    required this.moments,
  });

  final String tripId;
  final List<TripMomentSlice> moments;

  factory TripMomentListSlice.fromWire(Map<String, Object?> map, [String path = "TripMomentListSlice"]) {
    _rejectUnknownFields(map, const <String>{"tripId", "moments"}, path);
    return TripMomentListSlice(
      tripId: _requiredString(map["tripId"], '$path.tripId'),
      moments: List<TripMomentSlice>.unmodifiable(_requiredList(map["moments"], '$path.moments').asMap().entries.map((entry) => TripMomentSlice.fromWire(_requiredObject(entry.value, '$path.moments' + '[${entry.key}]'), '$path.moments' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "tripId": tripId,
    "moments": moments.map((value) => value.toWire()).toList(growable: false),
  };
}

final class TripMomentObjectRef {
  const TripMomentObjectRef({
    required this.objectTypeRef,
    required this.objectId,
  });

  final String objectTypeRef;
  final String objectId;

  factory TripMomentObjectRef.fromWire(Map<String, Object?> map, [String path = "TripMomentObjectRef"]) {
    _rejectUnknownFields(map, const <String>{"objectTypeRef", "objectId"}, path);
    return TripMomentObjectRef(
      objectTypeRef: _requiredNonBlankString(map["objectTypeRef"], '$path.objectTypeRef'),
      objectId: _requiredNonBlankString(map["objectId"], '$path.objectId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "objectTypeRef": objectTypeRef,
    "objectId": objectId,
  };
}

final class TripMomentSlice {
  const TripMomentSlice({
    required this.momentId,
    required this.version,
    required this.tripId,
    required this.revisionNumber,
    this.dayIndex,
    this.itemId,
    required this.kind,
    this.contentRef,
    this.inlineText,
    required this.capturedAt,
    this.coarsePlaceRef,
    required this.visibility,
    required this.assignmentStatus,
    required this.attributionPersonaId,
    required this.sourceVersion,
    required this.status,
    required this.createdAt,
    required this.updatedAt,
  });

  final String momentId;
  final int version;
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
  final String attributionPersonaId;
  final int sourceVersion;
  final TripMomentStatus status;
  final DateTime createdAt;
  final DateTime updatedAt;

  factory TripMomentSlice.fromWire(Map<String, Object?> map, [String path = "TripMomentSlice"]) {
    _rejectUnknownFields(map, const <String>{"momentId", "version", "tripId", "revisionNumber", "dayIndex", "itemId", "kind", "contentRef", "inlineText", "capturedAt", "coarsePlaceRef", "visibility", "assignmentStatus", "attributionPersonaId", "sourceVersion", "status", "createdAt", "updatedAt"}, path);
    return TripMomentSlice(
      momentId: _requiredString(map["momentId"], '$path.momentId'),
      version: _requiredInt(map["version"], '$path.version'),
      tripId: _requiredString(map["tripId"], '$path.tripId'),
      revisionNumber: _requiredInt(map["revisionNumber"], '$path.revisionNumber'),
      dayIndex: map["dayIndex"] == null ? null : _requiredInt(map["dayIndex"], '$path.dayIndex'),
      itemId: map["itemId"] == null ? null : _requiredString(map["itemId"], '$path.itemId'),
      kind: TripMomentKind.fromWire(map["kind"], '$path.kind'),
      contentRef: map["contentRef"] == null ? null : TripMomentObjectRef.fromWire(_requiredObject(map["contentRef"], '$path.contentRef'), '$path.contentRef'),
      inlineText: map["inlineText"] == null ? null : _requiredString(map["inlineText"], '$path.inlineText'),
      capturedAt: _requiredTimestamp(map["capturedAt"], '$path.capturedAt'),
      coarsePlaceRef: map["coarsePlaceRef"] == null ? null : TripMomentObjectRef.fromWire(_requiredObject(map["coarsePlaceRef"], '$path.coarsePlaceRef'), '$path.coarsePlaceRef'),
      visibility: TripMomentVisibility.fromWire(map["visibility"], '$path.visibility'),
      assignmentStatus: TripMomentAssignmentStatus.fromWire(map["assignmentStatus"], '$path.assignmentStatus'),
      attributionPersonaId: _requiredString(map["attributionPersonaId"], '$path.attributionPersonaId'),
      sourceVersion: _requiredInt(map["sourceVersion"], '$path.sourceVersion'),
      status: TripMomentStatus.fromWire(map["status"], '$path.status'),
      createdAt: _requiredTimestamp(map["createdAt"], '$path.createdAt'),
      updatedAt: _requiredTimestamp(map["updatedAt"], '$path.updatedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "momentId": momentId,
    "version": version,
    "tripId": tripId,
    "revisionNumber": revisionNumber,
    if (dayIndex != null) "dayIndex": dayIndex!,
    if (itemId != null) "itemId": itemId!,
    "kind": kind.wireName,
    if (contentRef != null) "contentRef": contentRef!.toWire(),
    if (inlineText != null) "inlineText": inlineText!,
    "capturedAt": capturedAt.toUtc().toIso8601String(),
    if (coarsePlaceRef != null) "coarsePlaceRef": coarsePlaceRef!.toWire(),
    "visibility": visibility.wireName,
    "assignmentStatus": assignmentStatus.wireName,
    "attributionPersonaId": attributionPersonaId,
    "sourceVersion": sourceVersion,
    "status": status.wireName,
    "createdAt": createdAt.toUtc().toIso8601String(),
    "updatedAt": updatedAt.toUtc().toIso8601String(),
  };
}

final class TripPlaceRef {
  const TripPlaceRef({
    required this.objectTypeRef,
    required this.objectId,
  });

  final String objectTypeRef;
  final String objectId;

  factory TripPlaceRef.fromWire(Map<String, Object?> map, [String path = "TripPlaceRef"]) {
    _rejectUnknownFields(map, const <String>{"objectTypeRef", "objectId"}, path);
    return TripPlaceRef(
      objectTypeRef: _requiredNonBlankString(map["objectTypeRef"], '$path.objectTypeRef'),
      objectId: _requiredNonBlankString(map["objectId"], '$path.objectId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "objectTypeRef": objectTypeRef,
    "objectId": objectId,
  };
}

final class TripPlanCommandResult {
  const TripPlanCommandResult({
    required this.tripId,
    required this.version,
    required this.currentRevisionId,
    required this.currentRevisionNumber,
    required this.status,
    required this.idempotentReplay,
  });

  final String tripId;
  final int version;
  final String currentRevisionId;
  final int currentRevisionNumber;
  final TripPlanStatus status;
  final bool idempotentReplay;

  factory TripPlanCommandResult.fromWire(Map<String, Object?> map, [String path = "TripPlanCommandResult"]) {
    _rejectUnknownFields(map, const <String>{"tripId", "version", "currentRevisionId", "currentRevisionNumber", "status", "idempotentReplay"}, path);
    return TripPlanCommandResult(
      tripId: _requiredString(map["tripId"], '$path.tripId'),
      version: _requiredInt(map["version"], '$path.version'),
      currentRevisionId: _requiredString(map["currentRevisionId"], '$path.currentRevisionId'),
      currentRevisionNumber: _requiredInt(map["currentRevisionNumber"], '$path.currentRevisionNumber'),
      status: TripPlanStatus.fromWire(map["status"], '$path.status'),
      idempotentReplay: _requiredBool(map["idempotentReplay"], '$path.idempotentReplay'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "tripId": tripId,
    "version": version,
    "currentRevisionId": currentRevisionId,
    "currentRevisionNumber": currentRevisionNumber,
    "status": status.wireName,
    "idempotentReplay": idempotentReplay,
  };
}

final class TripPlanContentLinkListSlice {
  const TripPlanContentLinkListSlice({
    required this.tripId,
    required this.links,
  });

  final String tripId;
  final List<TripPlanContentLinkSlice> links;

  factory TripPlanContentLinkListSlice.fromWire(Map<String, Object?> map, [String path = "TripPlanContentLinkListSlice"]) {
    _rejectUnknownFields(map, const <String>{"tripId", "links"}, path);
    return TripPlanContentLinkListSlice(
      tripId: _requiredString(map["tripId"], '$path.tripId'),
      links: List<TripPlanContentLinkSlice>.unmodifiable(_requiredList(map["links"], '$path.links').asMap().entries.map((entry) => TripPlanContentLinkSlice.fromWire(_requiredObject(entry.value, '$path.links' + '[${entry.key}]'), '$path.links' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "tripId": tripId,
    "links": links.map((value) => value.toWire()).toList(growable: false),
  };
}

final class TripPlanContentLinkSlice {
  const TripPlanContentLinkSlice({
    required this.linkId,
    required this.version,
    required this.tripId,
    required this.postId,
    required this.revisionNumber,
    required this.targetKind,
    this.dayIndex,
    this.itemId,
    required this.visibility,
    required this.linkedByPersonaId,
    required this.sourceVersion,
    required this.status,
    required this.createdAt,
    required this.updatedAt,
  });

  final String linkId;
  final int version;
  final String tripId;
  final String postId;
  final int revisionNumber;
  final TripPlanContentLinkTargetKind targetKind;
  final int? dayIndex;
  final String? itemId;
  final TripPlanContentLinkVisibility visibility;
  final String linkedByPersonaId;
  final int sourceVersion;
  final TripPlanContentLinkStatus status;
  final DateTime createdAt;
  final DateTime updatedAt;

  factory TripPlanContentLinkSlice.fromWire(Map<String, Object?> map, [String path = "TripPlanContentLinkSlice"]) {
    _rejectUnknownFields(map, const <String>{"linkId", "version", "tripId", "postId", "revisionNumber", "targetKind", "dayIndex", "itemId", "visibility", "linkedByPersonaId", "sourceVersion", "status", "createdAt", "updatedAt"}, path);
    return TripPlanContentLinkSlice(
      linkId: _requiredString(map["linkId"], '$path.linkId'),
      version: _requiredInt(map["version"], '$path.version'),
      tripId: _requiredString(map["tripId"], '$path.tripId'),
      postId: _requiredString(map["postId"], '$path.postId'),
      revisionNumber: _requiredInt(map["revisionNumber"], '$path.revisionNumber'),
      targetKind: TripPlanContentLinkTargetKind.fromWire(map["targetKind"], '$path.targetKind'),
      dayIndex: map["dayIndex"] == null ? null : _requiredInt(map["dayIndex"], '$path.dayIndex'),
      itemId: map["itemId"] == null ? null : _requiredString(map["itemId"], '$path.itemId'),
      visibility: TripPlanContentLinkVisibility.fromWire(map["visibility"], '$path.visibility'),
      linkedByPersonaId: _requiredString(map["linkedByPersonaId"], '$path.linkedByPersonaId'),
      sourceVersion: _requiredInt(map["sourceVersion"], '$path.sourceVersion'),
      status: TripPlanContentLinkStatus.fromWire(map["status"], '$path.status'),
      createdAt: _requiredTimestamp(map["createdAt"], '$path.createdAt'),
      updatedAt: _requiredTimestamp(map["updatedAt"], '$path.updatedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "linkId": linkId,
    "version": version,
    "tripId": tripId,
    "postId": postId,
    "revisionNumber": revisionNumber,
    "targetKind": targetKind.wireName,
    if (dayIndex != null) "dayIndex": dayIndex!,
    if (itemId != null) "itemId": itemId!,
    "visibility": visibility.wireName,
    "linkedByPersonaId": linkedByPersonaId,
    "sourceVersion": sourceVersion,
    "status": status.wireName,
    "createdAt": createdAt.toUtc().toIso8601String(),
    "updatedAt": updatedAt.toUtc().toIso8601String(),
  };
}

final class TripPlanItemSlice {
  const TripPlanItemSlice({
    required this.itemId,
    required this.dayIndex,
    required this.orderInDay,
    required this.kind,
    required this.title,
    this.startAt,
    this.endAt,
    this.placeRef,
    this.note,
  });

  final String itemId;
  final int dayIndex;
  final int orderInDay;
  final TripPlanItemKind kind;
  final String title;
  final DateTime? startAt;
  final DateTime? endAt;
  final TripPlaceRef? placeRef;
  final String? note;

  factory TripPlanItemSlice.fromWire(Map<String, Object?> map, [String path = "TripPlanItemSlice"]) {
    _rejectUnknownFields(map, const <String>{"itemId", "dayIndex", "orderInDay", "kind", "title", "startAt", "endAt", "placeRef", "note"}, path);
    return TripPlanItemSlice(
      itemId: _requiredString(map["itemId"], '$path.itemId'),
      dayIndex: _requiredInt(map["dayIndex"], '$path.dayIndex'),
      orderInDay: _requiredInt(map["orderInDay"], '$path.orderInDay'),
      kind: TripPlanItemKind.fromWire(map["kind"], '$path.kind'),
      title: _requiredString(map["title"], '$path.title'),
      startAt: map["startAt"] == null ? null : _requiredTimestamp(map["startAt"], '$path.startAt'),
      endAt: map["endAt"] == null ? null : _requiredTimestamp(map["endAt"], '$path.endAt'),
      placeRef: map["placeRef"] == null ? null : TripPlaceRef.fromWire(_requiredObject(map["placeRef"], '$path.placeRef'), '$path.placeRef'),
      note: map["note"] == null ? null : _requiredString(map["note"], '$path.note'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "itemId": itemId,
    "dayIndex": dayIndex,
    "orderInDay": orderInDay,
    "kind": kind.wireName,
    "title": title,
    if (startAt != null) "startAt": startAt!.toUtc().toIso8601String(),
    if (endAt != null) "endAt": endAt!.toUtc().toIso8601String(),
    if (placeRef != null) "placeRef": placeRef!.toWire(),
    if (note != null) "note": note!,
  };
}

final class TripPlanListSlice {
  const TripPlanListSlice({
    required this.plans,
    this.nextCursor,
  });

  final List<TripPlanSummarySlice> plans;
  final String? nextCursor;

  factory TripPlanListSlice.fromWire(Map<String, Object?> map, [String path = "TripPlanListSlice"]) {
    _rejectUnknownFields(map, const <String>{"plans", "nextCursor"}, path);
    return TripPlanListSlice(
      plans: List<TripPlanSummarySlice>.unmodifiable(_requiredList(map["plans"], '$path.plans').asMap().entries.map((entry) => TripPlanSummarySlice.fromWire(_requiredObject(entry.value, '$path.plans' + '[${entry.key}]'), '$path.plans' + '[${entry.key}]'))),
      nextCursor: map["nextCursor"] == null ? null : _requiredString(map["nextCursor"], '$path.nextCursor'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "plans": plans.map((value) => value.toWire()).toList(growable: false),
    if (nextCursor != null) "nextCursor": nextCursor!,
  };
}

final class TripPlanPlacementListSlice {
  const TripPlanPlacementListSlice({
    this.tripId,
    this.surfaceKind,
    this.surfaceId,
    required this.placements,
  });

  final String? tripId;
  final TripPlacementSurfaceKind? surfaceKind;
  final String? surfaceId;
  final List<TripPlanPlacementSlice> placements;

  factory TripPlanPlacementListSlice.fromWire(Map<String, Object?> map, [String path = "TripPlanPlacementListSlice"]) {
    _rejectUnknownFields(map, const <String>{"tripId", "surfaceKind", "surfaceId", "placements"}, path);
    return TripPlanPlacementListSlice(
      tripId: map["tripId"] == null ? null : _requiredString(map["tripId"], '$path.tripId'),
      surfaceKind: map["surfaceKind"] == null ? null : TripPlacementSurfaceKind.fromWire(map["surfaceKind"], '$path.surfaceKind'),
      surfaceId: map["surfaceId"] == null ? null : _requiredString(map["surfaceId"], '$path.surfaceId'),
      placements: List<TripPlanPlacementSlice>.unmodifiable(_requiredList(map["placements"], '$path.placements').asMap().entries.map((entry) => TripPlanPlacementSlice.fromWire(_requiredObject(entry.value, '$path.placements' + '[${entry.key}]'), '$path.placements' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (tripId != null) "tripId": tripId!,
    if (surfaceKind != null) "surfaceKind": surfaceKind!.wireName,
    if (surfaceId != null) "surfaceId": surfaceId!,
    "placements": placements.map((value) => value.toWire()).toList(growable: false),
  };
}

final class TripPlanPlacementSlice {
  const TripPlanPlacementSlice({
    required this.placementId,
    required this.version,
    required this.tripId,
    required this.surfaceKind,
    required this.surfaceId,
    required this.sourceVersion,
    required this.status,
    required this.createdByPersonaId,
    required this.createdAt,
    required this.updatedAt,
  });

  final String placementId;
  final int version;
  final String tripId;
  final TripPlacementSurfaceKind surfaceKind;
  final String surfaceId;
  final int sourceVersion;
  final TripPlanPlacementStatus status;
  final String createdByPersonaId;
  final DateTime createdAt;
  final DateTime updatedAt;

  factory TripPlanPlacementSlice.fromWire(Map<String, Object?> map, [String path = "TripPlanPlacementSlice"]) {
    _rejectUnknownFields(map, const <String>{"placementId", "version", "tripId", "surfaceKind", "surfaceId", "sourceVersion", "status", "createdByPersonaId", "createdAt", "updatedAt"}, path);
    return TripPlanPlacementSlice(
      placementId: _requiredString(map["placementId"], '$path.placementId'),
      version: _requiredInt(map["version"], '$path.version'),
      tripId: _requiredString(map["tripId"], '$path.tripId'),
      surfaceKind: TripPlacementSurfaceKind.fromWire(map["surfaceKind"], '$path.surfaceKind'),
      surfaceId: _requiredString(map["surfaceId"], '$path.surfaceId'),
      sourceVersion: _requiredInt(map["sourceVersion"], '$path.sourceVersion'),
      status: TripPlanPlacementStatus.fromWire(map["status"], '$path.status'),
      createdByPersonaId: _requiredString(map["createdByPersonaId"], '$path.createdByPersonaId'),
      createdAt: _requiredTimestamp(map["createdAt"], '$path.createdAt'),
      updatedAt: _requiredTimestamp(map["updatedAt"], '$path.updatedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "placementId": placementId,
    "version": version,
    "tripId": tripId,
    "surfaceKind": surfaceKind.wireName,
    "surfaceId": surfaceId,
    "sourceVersion": sourceVersion,
    "status": status.wireName,
    "createdByPersonaId": createdByPersonaId,
    "createdAt": createdAt.toUtc().toIso8601String(),
    "updatedAt": updatedAt.toUtc().toIso8601String(),
  };
}

final class TripPlanSlice {
  const TripPlanSlice({
    required this.tripId,
    required this.version,
    required this.organizerPersonaId,
    required this.title,
    required this.status,
    this.startAt,
    this.endAt,
    this.sourceTemplateId,
    this.sourceTemplateVersion,
    required this.sourceAttributions,
    required this.currentRevisionId,
    required this.currentRevisionNumber,
    required this.items,
    required this.createdAt,
    required this.updatedAt,
  });

  final String tripId;
  final int version;
  final String organizerPersonaId;
  final String title;
  final TripPlanStatus status;
  final DateTime? startAt;
  final DateTime? endAt;
  final String? sourceTemplateId;
  final int? sourceTemplateVersion;
  final List<TripPlanSourceAttribution> sourceAttributions;
  final String currentRevisionId;
  final int currentRevisionNumber;
  final List<TripPlanItemSlice> items;
  final DateTime createdAt;
  final DateTime updatedAt;

  factory TripPlanSlice.fromWire(Map<String, Object?> map, [String path = "TripPlanSlice"]) {
    _rejectUnknownFields(map, const <String>{"tripId", "version", "organizerPersonaId", "title", "status", "startAt", "endAt", "sourceTemplateId", "sourceTemplateVersion", "sourceAttributions", "currentRevisionId", "currentRevisionNumber", "items", "createdAt", "updatedAt"}, path);
    return TripPlanSlice(
      tripId: _requiredString(map["tripId"], '$path.tripId'),
      version: _requiredInt(map["version"], '$path.version'),
      organizerPersonaId: _requiredString(map["organizerPersonaId"], '$path.organizerPersonaId'),
      title: _requiredString(map["title"], '$path.title'),
      status: TripPlanStatus.fromWire(map["status"], '$path.status'),
      startAt: map["startAt"] == null ? null : _requiredTimestamp(map["startAt"], '$path.startAt'),
      endAt: map["endAt"] == null ? null : _requiredTimestamp(map["endAt"], '$path.endAt'),
      sourceTemplateId: map["sourceTemplateId"] == null ? null : _requiredString(map["sourceTemplateId"], '$path.sourceTemplateId'),
      sourceTemplateVersion: map["sourceTemplateVersion"] == null ? null : _requiredInt(map["sourceTemplateVersion"], '$path.sourceTemplateVersion'),
      sourceAttributions: List<TripPlanSourceAttribution>.unmodifiable(_requiredList(map["sourceAttributions"], '$path.sourceAttributions').asMap().entries.map((entry) => TripPlanSourceAttribution.fromWire(_requiredObject(entry.value, '$path.sourceAttributions' + '[${entry.key}]'), '$path.sourceAttributions' + '[${entry.key}]'))),
      currentRevisionId: _requiredString(map["currentRevisionId"], '$path.currentRevisionId'),
      currentRevisionNumber: _requiredInt(map["currentRevisionNumber"], '$path.currentRevisionNumber'),
      items: List<TripPlanItemSlice>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => TripPlanItemSlice.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      createdAt: _requiredTimestamp(map["createdAt"], '$path.createdAt'),
      updatedAt: _requiredTimestamp(map["updatedAt"], '$path.updatedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "tripId": tripId,
    "version": version,
    "organizerPersonaId": organizerPersonaId,
    "title": title,
    "status": status.wireName,
    if (startAt != null) "startAt": startAt!.toUtc().toIso8601String(),
    if (endAt != null) "endAt": endAt!.toUtc().toIso8601String(),
    if (sourceTemplateId != null) "sourceTemplateId": sourceTemplateId!,
    if (sourceTemplateVersion != null) "sourceTemplateVersion": sourceTemplateVersion!,
    "sourceAttributions": sourceAttributions.map((value) => value.toWire()).toList(growable: false),
    "currentRevisionId": currentRevisionId,
    "currentRevisionNumber": currentRevisionNumber,
    "items": items.map((value) => value.toWire()).toList(growable: false),
    "createdAt": createdAt.toUtc().toIso8601String(),
    "updatedAt": updatedAt.toUtc().toIso8601String(),
  };
}

final class TripPlanSourceAttribution {
  const TripPlanSourceAttribution({
    required this.attributionId,
    required this.kind,
    required this.postId,
    this.authorPersonaId,
    required this.title,
  });

  final String attributionId;
  final TripPlanSourceAttributionKind kind;
  final String postId;
  final String? authorPersonaId;
  final String title;

  factory TripPlanSourceAttribution.fromWire(Map<String, Object?> map, [String path = "TripPlanSourceAttribution"]) {
    _rejectUnknownFields(map, const <String>{"attributionId", "kind", "postId", "authorPersonaId", "title"}, path);
    return TripPlanSourceAttribution(
      attributionId: _requiredNonBlankString(map["attributionId"], '$path.attributionId'),
      kind: TripPlanSourceAttributionKind.fromWire(map["kind"], '$path.kind'),
      postId: _requiredNonBlankString(map["postId"], '$path.postId'),
      authorPersonaId: map["authorPersonaId"] == null ? null : _requiredString(map["authorPersonaId"], '$path.authorPersonaId'),
      title: _requiredNonBlankString(map["title"], '$path.title'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "attributionId": attributionId,
    "kind": kind.wireName,
    "postId": postId,
    if (authorPersonaId != null) "authorPersonaId": authorPersonaId!,
    "title": title,
  };
}

final class TripPlanSummarySlice {
  const TripPlanSummarySlice({
    required this.tripId,
    required this.title,
    required this.status,
    this.startAt,
    this.endAt,
    required this.currentRevisionId,
    required this.currentRevisionNumber,
    required this.itemCount,
    required this.updatedAt,
  });

  final String tripId;
  final String title;
  final TripPlanStatus status;
  final DateTime? startAt;
  final DateTime? endAt;
  final String currentRevisionId;
  final int currentRevisionNumber;
  final int itemCount;
  final DateTime updatedAt;

  factory TripPlanSummarySlice.fromWire(Map<String, Object?> map, [String path = "TripPlanSummarySlice"]) {
    _rejectUnknownFields(map, const <String>{"tripId", "title", "status", "startAt", "endAt", "currentRevisionId", "currentRevisionNumber", "itemCount", "updatedAt"}, path);
    return TripPlanSummarySlice(
      tripId: _requiredString(map["tripId"], '$path.tripId'),
      title: _requiredString(map["title"], '$path.title'),
      status: TripPlanStatus.fromWire(map["status"], '$path.status'),
      startAt: map["startAt"] == null ? null : _requiredTimestamp(map["startAt"], '$path.startAt'),
      endAt: map["endAt"] == null ? null : _requiredTimestamp(map["endAt"], '$path.endAt'),
      currentRevisionId: _requiredString(map["currentRevisionId"], '$path.currentRevisionId'),
      currentRevisionNumber: _requiredInt(map["currentRevisionNumber"], '$path.currentRevisionNumber'),
      itemCount: _requiredInt(map["itemCount"], '$path.itemCount'),
      updatedAt: _requiredTimestamp(map["updatedAt"], '$path.updatedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "tripId": tripId,
    "title": title,
    "status": status.wireName,
    if (startAt != null) "startAt": startAt!.toUtc().toIso8601String(),
    if (endAt != null) "endAt": endAt!.toUtc().toIso8601String(),
    "currentRevisionId": currentRevisionId,
    "currentRevisionNumber": currentRevisionNumber,
    "itemCount": itemCount,
    "updatedAt": updatedAt.toUtc().toIso8601String(),
  };
}

final class TripPlanTemplate {
  const TripPlanTemplate({
    required this.id,
    required this.version,
    required this.ownerPersonaId,
    required this.title,
    this.summary,
    required this.dayCount,
    required this.templateItemIds,
    required this.items,
    required this.attributionIds,
    required this.attributionPersonaIds,
    required this.attributions,
    required this.status,
    required this.createdAt,
    required this.updatedAt,
  });

  final String id;
  final int version;
  final String ownerPersonaId;
  final String title;
  final String? summary;
  final int dayCount;
  final List<String> templateItemIds;
  final List<TripPlanTemplateItem> items;
  final List<String> attributionIds;
  final List<String> attributionPersonaIds;
  final List<TripPlanTemplateAttribution> attributions;
  final TripPlanTemplateStatus status;
  final DateTime createdAt;
  final DateTime updatedAt;

  factory TripPlanTemplate.fromWire(Map<String, Object?> map, [String path = "TripPlanTemplate"]) {
    _rejectUnknownFields(map, const <String>{"id", "version", "ownerPersonaId", "title", "summary", "dayCount", "templateItemIds", "items", "attributionIds", "attributionPersonaIds", "attributions", "status", "createdAt", "updatedAt"}, path);
    return TripPlanTemplate(
      id: _requiredString(map["id"], '$path.id'),
      version: _requiredInt(map["version"], '$path.version'),
      ownerPersonaId: _requiredString(map["ownerPersonaId"], '$path.ownerPersonaId'),
      title: _requiredString(map["title"], '$path.title'),
      summary: map["summary"] == null ? null : _requiredString(map["summary"], '$path.summary'),
      dayCount: _requiredInt(map["dayCount"], '$path.dayCount'),
      templateItemIds: List<String>.unmodifiable(_requiredList(map["templateItemIds"], '$path.templateItemIds').asMap().entries.map((entry) => _requiredString(entry.value, '$path.templateItemIds' + '[${entry.key}]'))),
      items: List<TripPlanTemplateItem>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => TripPlanTemplateItem.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      attributionIds: List<String>.unmodifiable(_requiredList(map["attributionIds"], '$path.attributionIds').asMap().entries.map((entry) => _requiredString(entry.value, '$path.attributionIds' + '[${entry.key}]'))),
      attributionPersonaIds: List<String>.unmodifiable(_requiredList(map["attributionPersonaIds"], '$path.attributionPersonaIds').asMap().entries.map((entry) => _requiredString(entry.value, '$path.attributionPersonaIds' + '[${entry.key}]'))),
      attributions: List<TripPlanTemplateAttribution>.unmodifiable(_requiredList(map["attributions"], '$path.attributions').asMap().entries.map((entry) => TripPlanTemplateAttribution.fromWire(_requiredObject(entry.value, '$path.attributions' + '[${entry.key}]'), '$path.attributions' + '[${entry.key}]'))),
      status: TripPlanTemplateStatus.fromWire(map["status"], '$path.status'),
      createdAt: _requiredTimestamp(map["createdAt"], '$path.createdAt'),
      updatedAt: _requiredTimestamp(map["updatedAt"], '$path.updatedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "id": id,
    "version": version,
    "ownerPersonaId": ownerPersonaId,
    "title": title,
    if (summary != null) "summary": summary!,
    "dayCount": dayCount,
    "templateItemIds": templateItemIds.map((value) => value).toList(growable: false),
    "items": items.map((value) => value.toWire()).toList(growable: false),
    "attributionIds": attributionIds.map((value) => value).toList(growable: false),
    "attributionPersonaIds": attributionPersonaIds.map((value) => value).toList(growable: false),
    "attributions": attributions.map((value) => value.toWire()).toList(growable: false),
    "status": status.wireName,
    "createdAt": createdAt.toUtc().toIso8601String(),
    "updatedAt": updatedAt.toUtc().toIso8601String(),
  };
}

final class TripPlanTemplateAttribution {
  const TripPlanTemplateAttribution({
    required this.attributionId,
    required this.kind,
    required this.referenceObjectTypeRef,
    required this.referenceObjectId,
    this.authorPersonaId,
    required this.title,
  });

  final String attributionId;
  final TripPlanTemplateAttributionKind kind;
  final String referenceObjectTypeRef;
  final String referenceObjectId;
  final String? authorPersonaId;
  final String title;

  factory TripPlanTemplateAttribution.fromWire(Map<String, Object?> map, [String path = "TripPlanTemplateAttribution"]) {
    _rejectUnknownFields(map, const <String>{"attributionId", "kind", "referenceObjectTypeRef", "referenceObjectId", "authorPersonaId", "title"}, path);
    return TripPlanTemplateAttribution(
      attributionId: _requiredNonBlankString(map["attributionId"], '$path.attributionId'),
      kind: TripPlanTemplateAttributionKind.fromWire(map["kind"], '$path.kind'),
      referenceObjectTypeRef: _requiredNonBlankString(map["referenceObjectTypeRef"], '$path.referenceObjectTypeRef'),
      referenceObjectId: _requiredNonBlankString(map["referenceObjectId"], '$path.referenceObjectId'),
      authorPersonaId: map["authorPersonaId"] == null ? null : _requiredString(map["authorPersonaId"], '$path.authorPersonaId'),
      title: _requiredNonBlankString(map["title"], '$path.title'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "attributionId": attributionId,
    "kind": kind.wireName,
    "referenceObjectTypeRef": referenceObjectTypeRef,
    "referenceObjectId": referenceObjectId,
    if (authorPersonaId != null) "authorPersonaId": authorPersonaId!,
    "title": title,
  };
}

final class TripPlanTemplateItem {
  const TripPlanTemplateItem({
    required this.templateItemId,
    required this.dayOffset,
    required this.orderInDay,
    required this.kind,
    this.title,
    this.publicPlaceRef,
    this.note,
    required this.attributionIds,
  });

  final String templateItemId;
  final int dayOffset;
  final int orderInDay;
  final String kind;
  final String? title;
  final TripPlanTemplatePlaceRef? publicPlaceRef;
  final String? note;
  final List<String> attributionIds;

  factory TripPlanTemplateItem.fromWire(Map<String, Object?> map, [String path = "TripPlanTemplateItem"]) {
    _rejectUnknownFields(map, const <String>{"templateItemId", "dayOffset", "orderInDay", "kind", "title", "publicPlaceRef", "note", "attributionIds"}, path);
    return TripPlanTemplateItem(
      templateItemId: _requiredNonBlankString(map["templateItemId"], '$path.templateItemId'),
      dayOffset: _requiredInt(map["dayOffset"], '$path.dayOffset'),
      orderInDay: _requiredInt(map["orderInDay"], '$path.orderInDay'),
      kind: _requiredNonBlankString(map["kind"], '$path.kind'),
      title: map["title"] == null ? null : _requiredString(map["title"], '$path.title'),
      publicPlaceRef: map["publicPlaceRef"] == null ? null : TripPlanTemplatePlaceRef.fromWire(_requiredObject(map["publicPlaceRef"], '$path.publicPlaceRef'), '$path.publicPlaceRef'),
      note: map["note"] == null ? null : _requiredString(map["note"], '$path.note'),
      attributionIds: List<String>.unmodifiable(_requiredList(map["attributionIds"], '$path.attributionIds').asMap().entries.map((entry) => _requiredString(entry.value, '$path.attributionIds' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "templateItemId": templateItemId,
    "dayOffset": dayOffset,
    "orderInDay": orderInDay,
    "kind": kind,
    if (title != null) "title": title!,
    if (publicPlaceRef != null) "publicPlaceRef": publicPlaceRef!.toWire(),
    if (note != null) "note": note!,
    "attributionIds": attributionIds.map((value) => value).toList(growable: false),
  };
}

final class TripPlanTemplateListSlice {
  const TripPlanTemplateListSlice({
    required this.templates,
  });

  final List<TripPlanTemplate> templates;

  factory TripPlanTemplateListSlice.fromWire(Map<String, Object?> map, [String path = "TripPlanTemplateListSlice"]) {
    _rejectUnknownFields(map, const <String>{"templates"}, path);
    return TripPlanTemplateListSlice(
      templates: List<TripPlanTemplate>.unmodifiable(_requiredList(map["templates"], '$path.templates').asMap().entries.map((entry) => TripPlanTemplate.fromWire(_requiredObject(entry.value, '$path.templates' + '[${entry.key}]'), '$path.templates' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "templates": templates.map((value) => value.toWire()).toList(growable: false),
  };
}

final class TripPlanTemplatePlaceRef {
  const TripPlanTemplatePlaceRef({
    required this.objectTypeRef,
    required this.objectId,
  });

  final String objectTypeRef;
  final String objectId;

  factory TripPlanTemplatePlaceRef.fromWire(Map<String, Object?> map, [String path = "TripPlanTemplatePlaceRef"]) {
    _rejectUnknownFields(map, const <String>{"objectTypeRef", "objectId"}, path);
    return TripPlanTemplatePlaceRef(
      objectTypeRef: _requiredNonBlankString(map["objectTypeRef"], '$path.objectTypeRef'),
      objectId: _requiredNonBlankString(map["objectId"], '$path.objectId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "objectTypeRef": objectTypeRef,
    "objectId": objectId,
  };
}

final class TripShareContentLinkSlice {
  const TripShareContentLinkSlice({
    required this.linkId,
    required this.postId,
    this.dayIndex,
    this.itemId,
  });

  final String linkId;
  final String postId;
  final int? dayIndex;
  final String? itemId;

  factory TripShareContentLinkSlice.fromWire(Map<String, Object?> map, [String path = "TripShareContentLinkSlice"]) {
    _rejectUnknownFields(map, const <String>{"linkId", "postId", "dayIndex", "itemId"}, path);
    return TripShareContentLinkSlice(
      linkId: _requiredString(map["linkId"], '$path.linkId'),
      postId: _requiredString(map["postId"], '$path.postId'),
      dayIndex: map["dayIndex"] == null ? null : _requiredInt(map["dayIndex"], '$path.dayIndex'),
      itemId: map["itemId"] == null ? null : _requiredString(map["itemId"], '$path.itemId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "linkId": linkId,
    "postId": postId,
    if (dayIndex != null) "dayIndex": dayIndex!,
    if (itemId != null) "itemId": itemId!,
  };
}

final class TripShareItemSlice {
  const TripShareItemSlice({
    required this.dayIndex,
    required this.itemId,
    required this.orderInDay,
    required this.kind,
    this.title,
    this.placeRef,
  });

  final int dayIndex;
  final String itemId;
  final int orderInDay;
  final String kind;
  final String? title;
  final TripSharePlaceRef? placeRef;

  factory TripShareItemSlice.fromWire(Map<String, Object?> map, [String path = "TripShareItemSlice"]) {
    _rejectUnknownFields(map, const <String>{"dayIndex", "itemId", "orderInDay", "kind", "title", "placeRef"}, path);
    return TripShareItemSlice(
      dayIndex: _requiredInt(map["dayIndex"], '$path.dayIndex'),
      itemId: _requiredString(map["itemId"], '$path.itemId'),
      orderInDay: _requiredInt(map["orderInDay"], '$path.orderInDay'),
      kind: _requiredNonBlankString(map["kind"], '$path.kind'),
      title: map["title"] == null ? null : _requiredString(map["title"], '$path.title'),
      placeRef: map["placeRef"] == null ? null : TripSharePlaceRef.fromWire(_requiredObject(map["placeRef"], '$path.placeRef'), '$path.placeRef'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "dayIndex": dayIndex,
    "itemId": itemId,
    "orderInDay": orderInDay,
    "kind": kind,
    if (title != null) "title": title!,
    if (placeRef != null) "placeRef": placeRef!.toWire(),
  };
}

final class TripShareMomentSlice {
  const TripShareMomentSlice({
    required this.momentId,
    required this.dayIndex,
    this.itemId,
    required this.kind,
    this.contentObjectTypeRef,
    this.contentObjectId,
  });

  final String momentId;
  final int dayIndex;
  final String? itemId;
  final String kind;
  final String? contentObjectTypeRef;
  final String? contentObjectId;

  factory TripShareMomentSlice.fromWire(Map<String, Object?> map, [String path = "TripShareMomentSlice"]) {
    _rejectUnknownFields(map, const <String>{"momentId", "dayIndex", "itemId", "kind", "contentObjectTypeRef", "contentObjectId"}, path);
    return TripShareMomentSlice(
      momentId: _requiredString(map["momentId"], '$path.momentId'),
      dayIndex: _requiredInt(map["dayIndex"], '$path.dayIndex'),
      itemId: map["itemId"] == null ? null : _requiredString(map["itemId"], '$path.itemId'),
      kind: _requiredNonBlankString(map["kind"], '$path.kind'),
      contentObjectTypeRef: map["contentObjectTypeRef"] == null ? null : _requiredString(map["contentObjectTypeRef"], '$path.contentObjectTypeRef'),
      contentObjectId: map["contentObjectId"] == null ? null : _requiredString(map["contentObjectId"], '$path.contentObjectId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "momentId": momentId,
    "dayIndex": dayIndex,
    if (itemId != null) "itemId": itemId!,
    "kind": kind,
    if (contentObjectTypeRef != null) "contentObjectTypeRef": contentObjectTypeRef!,
    if (contentObjectId != null) "contentObjectId": contentObjectId!,
  };
}

final class TripSharePlaceRef {
  const TripSharePlaceRef({
    required this.objectTypeRef,
    required this.objectId,
  });

  final String objectTypeRef;
  final String objectId;

  factory TripSharePlaceRef.fromWire(Map<String, Object?> map, [String path = "TripSharePlaceRef"]) {
    _rejectUnknownFields(map, const <String>{"objectTypeRef", "objectId"}, path);
    return TripSharePlaceRef(
      objectTypeRef: _requiredNonBlankString(map["objectTypeRef"], '$path.objectTypeRef'),
      objectId: _requiredNonBlankString(map["objectId"], '$path.objectId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "objectTypeRef": objectTypeRef,
    "objectId": objectId,
  };
}

final class TripShareRouteStopSlice {
  const TripShareRouteStopSlice({
    required this.dayIndex,
    required this.itemId,
    required this.sequence,
    this.title,
    required this.placeRef,
  });

  final int dayIndex;
  final String itemId;
  final int sequence;
  final String? title;
  final TripSharePlaceRef placeRef;

  factory TripShareRouteStopSlice.fromWire(Map<String, Object?> map, [String path = "TripShareRouteStopSlice"]) {
    _rejectUnknownFields(map, const <String>{"dayIndex", "itemId", "sequence", "title", "placeRef"}, path);
    return TripShareRouteStopSlice(
      dayIndex: _requiredInt(map["dayIndex"], '$path.dayIndex'),
      itemId: _requiredString(map["itemId"], '$path.itemId'),
      sequence: _requiredInt(map["sequence"], '$path.sequence'),
      title: map["title"] == null ? null : _requiredString(map["title"], '$path.title'),
      placeRef: TripSharePlaceRef.fromWire(_requiredObject(map["placeRef"], '$path.placeRef'), '$path.placeRef'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "dayIndex": dayIndex,
    "itemId": itemId,
    "sequence": sequence,
    if (title != null) "title": title!,
    "placeRef": placeRef.toWire(),
  };
}

final class TripShareSnapshot {
  const TripShareSnapshot({
    required this.id,
    required this.version,
    required this.tripId,
    required this.sourceRevisionId,
    required this.sourceRevisionNumber,
    required this.sourceDigest,
    required this.scope,
    this.dayIndex,
    this.itemId,
    required this.momentIds,
    required this.visibility,
    required this.privacyPolicyDigest,
    required this.items,
    required this.moments,
    required this.contentLinks,
    required this.routeStops,
    required this.createdByPersonaId,
    required this.status,
    required this.createdAt,
  });

  final String id;
  final int version;
  final String tripId;
  final String sourceRevisionId;
  final int sourceRevisionNumber;
  final String sourceDigest;
  final TripShareSnapshotScope scope;
  final int? dayIndex;
  final String? itemId;
  final List<String> momentIds;
  final TripShareSnapshotVisibility visibility;
  final String privacyPolicyDigest;
  final List<TripShareItemSlice> items;
  final List<TripShareMomentSlice> moments;
  final List<TripShareContentLinkSlice> contentLinks;
  final List<TripShareRouteStopSlice> routeStops;
  final String createdByPersonaId;
  final TripShareSnapshotStatus status;
  final DateTime createdAt;

  factory TripShareSnapshot.fromWire(Map<String, Object?> map, [String path = "TripShareSnapshot"]) {
    _rejectUnknownFields(map, const <String>{"id", "version", "tripId", "sourceRevisionId", "sourceRevisionNumber", "sourceDigest", "scope", "dayIndex", "itemId", "momentIds", "visibility", "privacyPolicyDigest", "items", "moments", "contentLinks", "routeStops", "createdByPersonaId", "status", "createdAt"}, path);
    return TripShareSnapshot(
      id: _requiredString(map["id"], '$path.id'),
      version: _requiredInt(map["version"], '$path.version'),
      tripId: _requiredString(map["tripId"], '$path.tripId'),
      sourceRevisionId: _requiredString(map["sourceRevisionId"], '$path.sourceRevisionId'),
      sourceRevisionNumber: _requiredInt(map["sourceRevisionNumber"], '$path.sourceRevisionNumber'),
      sourceDigest: _requiredString(map["sourceDigest"], '$path.sourceDigest'),
      scope: TripShareSnapshotScope.fromWire(map["scope"], '$path.scope'),
      dayIndex: map["dayIndex"] == null ? null : _requiredInt(map["dayIndex"], '$path.dayIndex'),
      itemId: map["itemId"] == null ? null : _requiredString(map["itemId"], '$path.itemId'),
      momentIds: List<String>.unmodifiable(_requiredList(map["momentIds"], '$path.momentIds').asMap().entries.map((entry) => _requiredString(entry.value, '$path.momentIds' + '[${entry.key}]'))),
      visibility: TripShareSnapshotVisibility.fromWire(map["visibility"], '$path.visibility'),
      privacyPolicyDigest: _requiredString(map["privacyPolicyDigest"], '$path.privacyPolicyDigest'),
      items: List<TripShareItemSlice>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => TripShareItemSlice.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      moments: List<TripShareMomentSlice>.unmodifiable(_requiredList(map["moments"], '$path.moments').asMap().entries.map((entry) => TripShareMomentSlice.fromWire(_requiredObject(entry.value, '$path.moments' + '[${entry.key}]'), '$path.moments' + '[${entry.key}]'))),
      contentLinks: List<TripShareContentLinkSlice>.unmodifiable(_requiredList(map["contentLinks"], '$path.contentLinks').asMap().entries.map((entry) => TripShareContentLinkSlice.fromWire(_requiredObject(entry.value, '$path.contentLinks' + '[${entry.key}]'), '$path.contentLinks' + '[${entry.key}]'))),
      routeStops: List<TripShareRouteStopSlice>.unmodifiable(_requiredList(map["routeStops"], '$path.routeStops').asMap().entries.map((entry) => TripShareRouteStopSlice.fromWire(_requiredObject(entry.value, '$path.routeStops' + '[${entry.key}]'), '$path.routeStops' + '[${entry.key}]'))),
      createdByPersonaId: _requiredString(map["createdByPersonaId"], '$path.createdByPersonaId'),
      status: TripShareSnapshotStatus.fromWire(map["status"], '$path.status'),
      createdAt: _requiredTimestamp(map["createdAt"], '$path.createdAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "id": id,
    "version": version,
    "tripId": tripId,
    "sourceRevisionId": sourceRevisionId,
    "sourceRevisionNumber": sourceRevisionNumber,
    "sourceDigest": sourceDigest,
    "scope": scope.wireName,
    if (dayIndex != null) "dayIndex": dayIndex!,
    if (itemId != null) "itemId": itemId!,
    "momentIds": momentIds.map((value) => value).toList(growable: false),
    "visibility": visibility.wireName,
    "privacyPolicyDigest": privacyPolicyDigest,
    "items": items.map((value) => value.toWire()).toList(growable: false),
    "moments": moments.map((value) => value.toWire()).toList(growable: false),
    "contentLinks": contentLinks.map((value) => value.toWire()).toList(growable: false),
    "routeStops": routeStops.map((value) => value.toWire()).toList(growable: false),
    "createdByPersonaId": createdByPersonaId,
    "status": status.wireName,
    "createdAt": createdAt.toUtc().toIso8601String(),
  };
}

final class TripTimelineContentLinkSlice {
  const TripTimelineContentLinkSlice({
    required this.linkId,
    required this.postId,
    required this.visibility,
    required this.linkedByPersonaId,
  });

  final String linkId;
  final String postId;
  final TripPlanContentLinkVisibility visibility;
  final String linkedByPersonaId;

  factory TripTimelineContentLinkSlice.fromWire(Map<String, Object?> map, [String path = "TripTimelineContentLinkSlice"]) {
    _rejectUnknownFields(map, const <String>{"linkId", "postId", "visibility", "linkedByPersonaId"}, path);
    return TripTimelineContentLinkSlice(
      linkId: _requiredString(map["linkId"], '$path.linkId'),
      postId: _requiredString(map["postId"], '$path.postId'),
      visibility: TripPlanContentLinkVisibility.fromWire(map["visibility"], '$path.visibility'),
      linkedByPersonaId: _requiredString(map["linkedByPersonaId"], '$path.linkedByPersonaId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "linkId": linkId,
    "postId": postId,
    "visibility": visibility.wireName,
    "linkedByPersonaId": linkedByPersonaId,
  };
}

final class TripTimelineContentRef {
  const TripTimelineContentRef({
    required this.objectTypeRef,
    required this.objectId,
  });

  final String objectTypeRef;
  final String objectId;

  factory TripTimelineContentRef.fromWire(Map<String, Object?> map, [String path = "TripTimelineContentRef"]) {
    _rejectUnknownFields(map, const <String>{"objectTypeRef", "objectId"}, path);
    return TripTimelineContentRef(
      objectTypeRef: _requiredNonBlankString(map["objectTypeRef"], '$path.objectTypeRef'),
      objectId: _requiredNonBlankString(map["objectId"], '$path.objectId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "objectTypeRef": objectTypeRef,
    "objectId": objectId,
  };
}

final class TripTimelineDaySlice {
  const TripTimelineDaySlice({
    required this.dayIndex,
    required this.unassignedMoments,
    required this.unassignedContentLinks,
    required this.items,
  });

  final int dayIndex;
  final List<TripTimelineMomentSlice> unassignedMoments;
  final List<TripTimelineContentLinkSlice> unassignedContentLinks;
  final List<TripTimelineItemSlice> items;

  factory TripTimelineDaySlice.fromWire(Map<String, Object?> map, [String path = "TripTimelineDaySlice"]) {
    _rejectUnknownFields(map, const <String>{"dayIndex", "unassignedMoments", "unassignedContentLinks", "items"}, path);
    return TripTimelineDaySlice(
      dayIndex: _requiredInt(map["dayIndex"], '$path.dayIndex'),
      unassignedMoments: List<TripTimelineMomentSlice>.unmodifiable(_requiredList(map["unassignedMoments"], '$path.unassignedMoments').asMap().entries.map((entry) => TripTimelineMomentSlice.fromWire(_requiredObject(entry.value, '$path.unassignedMoments' + '[${entry.key}]'), '$path.unassignedMoments' + '[${entry.key}]'))),
      unassignedContentLinks: List<TripTimelineContentLinkSlice>.unmodifiable(_requiredList(map["unassignedContentLinks"], '$path.unassignedContentLinks').asMap().entries.map((entry) => TripTimelineContentLinkSlice.fromWire(_requiredObject(entry.value, '$path.unassignedContentLinks' + '[${entry.key}]'), '$path.unassignedContentLinks' + '[${entry.key}]'))),
      items: List<TripTimelineItemSlice>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => TripTimelineItemSlice.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "dayIndex": dayIndex,
    "unassignedMoments": unassignedMoments.map((value) => value.toWire()).toList(growable: false),
    "unassignedContentLinks": unassignedContentLinks.map((value) => value.toWire()).toList(growable: false),
    "items": items.map((value) => value.toWire()).toList(growable: false),
  };
}

final class TripTimelineItemSlice {
  const TripTimelineItemSlice({
    required this.itemId,
    required this.orderInDay,
    required this.kind,
    required this.title,
    this.startAt,
    this.endAt,
    this.placeRef,
    this.note,
    required this.moments,
    required this.contentLinks,
  });

  final String itemId;
  final int orderInDay;
  final TripPlanItemKind kind;
  final String title;
  final DateTime? startAt;
  final DateTime? endAt;
  final TripTimelinePlaceRef? placeRef;
  final String? note;
  final List<TripTimelineMomentSlice> moments;
  final List<TripTimelineContentLinkSlice> contentLinks;

  factory TripTimelineItemSlice.fromWire(Map<String, Object?> map, [String path = "TripTimelineItemSlice"]) {
    _rejectUnknownFields(map, const <String>{"itemId", "orderInDay", "kind", "title", "startAt", "endAt", "placeRef", "note", "moments", "contentLinks"}, path);
    return TripTimelineItemSlice(
      itemId: _requiredString(map["itemId"], '$path.itemId'),
      orderInDay: _requiredInt(map["orderInDay"], '$path.orderInDay'),
      kind: TripPlanItemKind.fromWire(map["kind"], '$path.kind'),
      title: _requiredString(map["title"], '$path.title'),
      startAt: map["startAt"] == null ? null : _requiredTimestamp(map["startAt"], '$path.startAt'),
      endAt: map["endAt"] == null ? null : _requiredTimestamp(map["endAt"], '$path.endAt'),
      placeRef: map["placeRef"] == null ? null : TripTimelinePlaceRef.fromWire(_requiredObject(map["placeRef"], '$path.placeRef'), '$path.placeRef'),
      note: map["note"] == null ? null : _requiredString(map["note"], '$path.note'),
      moments: List<TripTimelineMomentSlice>.unmodifiable(_requiredList(map["moments"], '$path.moments').asMap().entries.map((entry) => TripTimelineMomentSlice.fromWire(_requiredObject(entry.value, '$path.moments' + '[${entry.key}]'), '$path.moments' + '[${entry.key}]'))),
      contentLinks: List<TripTimelineContentLinkSlice>.unmodifiable(_requiredList(map["contentLinks"], '$path.contentLinks').asMap().entries.map((entry) => TripTimelineContentLinkSlice.fromWire(_requiredObject(entry.value, '$path.contentLinks' + '[${entry.key}]'), '$path.contentLinks' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "itemId": itemId,
    "orderInDay": orderInDay,
    "kind": kind.wireName,
    "title": title,
    if (startAt != null) "startAt": startAt!.toUtc().toIso8601String(),
    if (endAt != null) "endAt": endAt!.toUtc().toIso8601String(),
    if (placeRef != null) "placeRef": placeRef!.toWire(),
    if (note != null) "note": note!,
    "moments": moments.map((value) => value.toWire()).toList(growable: false),
    "contentLinks": contentLinks.map((value) => value.toWire()).toList(growable: false),
  };
}

final class TripTimelineMomentSlice {
  const TripTimelineMomentSlice({
    required this.momentId,
    required this.kind,
    this.contentRef,
    this.inlineText,
    required this.capturedAt,
    this.coarsePlaceRef,
    required this.visibility,
    required this.attributionPersonaId,
  });

  final String momentId;
  final TripMomentKind kind;
  final TripTimelineContentRef? contentRef;
  final String? inlineText;
  final DateTime capturedAt;
  final TripTimelinePlaceRef? coarsePlaceRef;
  final TripMomentVisibility visibility;
  final String attributionPersonaId;

  factory TripTimelineMomentSlice.fromWire(Map<String, Object?> map, [String path = "TripTimelineMomentSlice"]) {
    _rejectUnknownFields(map, const <String>{"momentId", "kind", "contentRef", "inlineText", "capturedAt", "coarsePlaceRef", "visibility", "attributionPersonaId"}, path);
    return TripTimelineMomentSlice(
      momentId: _requiredString(map["momentId"], '$path.momentId'),
      kind: TripMomentKind.fromWire(map["kind"], '$path.kind'),
      contentRef: map["contentRef"] == null ? null : TripTimelineContentRef.fromWire(_requiredObject(map["contentRef"], '$path.contentRef'), '$path.contentRef'),
      inlineText: map["inlineText"] == null ? null : _requiredString(map["inlineText"], '$path.inlineText'),
      capturedAt: _requiredTimestamp(map["capturedAt"], '$path.capturedAt'),
      coarsePlaceRef: map["coarsePlaceRef"] == null ? null : TripTimelinePlaceRef.fromWire(_requiredObject(map["coarsePlaceRef"], '$path.coarsePlaceRef'), '$path.coarsePlaceRef'),
      visibility: TripMomentVisibility.fromWire(map["visibility"], '$path.visibility'),
      attributionPersonaId: _requiredString(map["attributionPersonaId"], '$path.attributionPersonaId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "momentId": momentId,
    "kind": kind.wireName,
    if (contentRef != null) "contentRef": contentRef!.toWire(),
    if (inlineText != null) "inlineText": inlineText!,
    "capturedAt": capturedAt.toUtc().toIso8601String(),
    if (coarsePlaceRef != null) "coarsePlaceRef": coarsePlaceRef!.toWire(),
    "visibility": visibility.wireName,
    "attributionPersonaId": attributionPersonaId,
  };
}

final class TripTimelinePlaceRef {
  const TripTimelinePlaceRef({
    required this.objectTypeRef,
    required this.objectId,
  });

  final String objectTypeRef;
  final String objectId;

  factory TripTimelinePlaceRef.fromWire(Map<String, Object?> map, [String path = "TripTimelinePlaceRef"]) {
    _rejectUnknownFields(map, const <String>{"objectTypeRef", "objectId"}, path);
    return TripTimelinePlaceRef(
      objectTypeRef: _requiredNonBlankString(map["objectTypeRef"], '$path.objectTypeRef'),
      objectId: _requiredNonBlankString(map["objectId"], '$path.objectId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "objectTypeRef": objectTypeRef,
    "objectId": objectId,
  };
}

final class TripTimelineView {
  const TripTimelineView({
    required this.tripId,
    required this.tripVersion,
    required this.tripStatus,
    required this.currentRevisionId,
    required this.currentRevisionNumber,
    required this.revisionChangeReason,
    required this.revisionSeverity,
    required this.tripContentLinks,
    required this.days,
    required this.sourceMomentIds,
    required this.sourceContentLinkIds,
    required this.sourceDigest,
    required this.sourceEventId,
    required this.projectedAt,
  });

  final String tripId;
  final int tripVersion;
  final TripPlanStatus tripStatus;
  final String currentRevisionId;
  final int currentRevisionNumber;
  final String revisionChangeReason;
  final TripRevisionSeverity revisionSeverity;
  final List<TripTimelineContentLinkSlice> tripContentLinks;
  final List<TripTimelineDaySlice> days;
  final List<String> sourceMomentIds;
  final List<String> sourceContentLinkIds;
  final String sourceDigest;
  final String sourceEventId;
  final DateTime projectedAt;

  factory TripTimelineView.fromWire(Map<String, Object?> map, [String path = "TripTimelineView"]) {
    _rejectUnknownFields(map, const <String>{"tripId", "tripVersion", "tripStatus", "currentRevisionId", "currentRevisionNumber", "revisionChangeReason", "revisionSeverity", "tripContentLinks", "days", "sourceMomentIds", "sourceContentLinkIds", "sourceDigest", "sourceEventId", "projectedAt"}, path);
    return TripTimelineView(
      tripId: _requiredString(map["tripId"], '$path.tripId'),
      tripVersion: _requiredInt(map["tripVersion"], '$path.tripVersion'),
      tripStatus: TripPlanStatus.fromWire(map["tripStatus"], '$path.tripStatus'),
      currentRevisionId: _requiredString(map["currentRevisionId"], '$path.currentRevisionId'),
      currentRevisionNumber: _requiredInt(map["currentRevisionNumber"], '$path.currentRevisionNumber'),
      revisionChangeReason: _requiredString(map["revisionChangeReason"], '$path.revisionChangeReason'),
      revisionSeverity: TripRevisionSeverity.fromWire(map["revisionSeverity"], '$path.revisionSeverity'),
      tripContentLinks: List<TripTimelineContentLinkSlice>.unmodifiable(_requiredList(map["tripContentLinks"], '$path.tripContentLinks').asMap().entries.map((entry) => TripTimelineContentLinkSlice.fromWire(_requiredObject(entry.value, '$path.tripContentLinks' + '[${entry.key}]'), '$path.tripContentLinks' + '[${entry.key}]'))),
      days: List<TripTimelineDaySlice>.unmodifiable(_requiredList(map["days"], '$path.days').asMap().entries.map((entry) => TripTimelineDaySlice.fromWire(_requiredObject(entry.value, '$path.days' + '[${entry.key}]'), '$path.days' + '[${entry.key}]'))),
      sourceMomentIds: List<String>.unmodifiable(_requiredList(map["sourceMomentIds"], '$path.sourceMomentIds').asMap().entries.map((entry) => _requiredString(entry.value, '$path.sourceMomentIds' + '[${entry.key}]'))),
      sourceContentLinkIds: List<String>.unmodifiable(_requiredList(map["sourceContentLinkIds"], '$path.sourceContentLinkIds').asMap().entries.map((entry) => _requiredString(entry.value, '$path.sourceContentLinkIds' + '[${entry.key}]'))),
      sourceDigest: _requiredString(map["sourceDigest"], '$path.sourceDigest'),
      sourceEventId: _requiredString(map["sourceEventId"], '$path.sourceEventId'),
      projectedAt: _requiredTimestamp(map["projectedAt"], '$path.projectedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "tripId": tripId,
    "tripVersion": tripVersion,
    "tripStatus": tripStatus.wireName,
    "currentRevisionId": currentRevisionId,
    "currentRevisionNumber": currentRevisionNumber,
    "revisionChangeReason": revisionChangeReason,
    "revisionSeverity": revisionSeverity.wireName,
    "tripContentLinks": tripContentLinks.map((value) => value.toWire()).toList(growable: false),
    "days": days.map((value) => value.toWire()).toList(growable: false),
    "sourceMomentIds": sourceMomentIds.map((value) => value).toList(growable: false),
    "sourceContentLinkIds": sourceContentLinkIds.map((value) => value).toList(growable: false),
    "sourceDigest": sourceDigest,
    "sourceEventId": sourceEventId,
    "projectedAt": projectedAt.toUtc().toIso8601String(),
  };
}

TripGuideAssignment decodeTripGuideAssignment(Object? response) =>
    TripGuideAssignment.fromWire(_requiredObject(response, "TripGuideAssignment"), "TripGuideAssignment");

TripGuideAssignmentListSlice decodeTripGuideAssignmentListSlice(Object? response) =>
    TripGuideAssignmentListSlice.fromWire(_requiredObject(response, "TripGuideAssignmentListSlice"), "TripGuideAssignmentListSlice");

TripMapView decodeTripMapView(Object? response) =>
    TripMapView.fromWire(_requiredObject(response, "TripMapView"), "TripMapView");

TripMembershipListSlice decodeTripMembershipListSlice(Object? response) =>
    TripMembershipListSlice.fromWire(_requiredObject(response, "TripMembershipListSlice"), "TripMembershipListSlice");

TripMembershipSlice decodeTripMembershipSlice(Object? response) =>
    TripMembershipSlice.fromWire(_requiredObject(response, "TripMembershipSlice"), "TripMembershipSlice");

TripMomentListSlice decodeTripMomentListSlice(Object? response) =>
    TripMomentListSlice.fromWire(_requiredObject(response, "TripMomentListSlice"), "TripMomentListSlice");

TripMomentSlice decodeTripMomentSlice(Object? response) =>
    TripMomentSlice.fromWire(_requiredObject(response, "TripMomentSlice"), "TripMomentSlice");

TripPlanCommandResult decodeTripPlanCommandResult(Object? response) =>
    TripPlanCommandResult.fromWire(_requiredObject(response, "TripPlanCommandResult"), "TripPlanCommandResult");

TripPlanContentLinkListSlice decodeTripPlanContentLinkListSlice(Object? response) =>
    TripPlanContentLinkListSlice.fromWire(_requiredObject(response, "TripPlanContentLinkListSlice"), "TripPlanContentLinkListSlice");

TripPlanContentLinkSlice decodeTripPlanContentLinkSlice(Object? response) =>
    TripPlanContentLinkSlice.fromWire(_requiredObject(response, "TripPlanContentLinkSlice"), "TripPlanContentLinkSlice");

TripPlanListSlice decodeTripPlanListSlice(Object? response) =>
    TripPlanListSlice.fromWire(_requiredObject(response, "TripPlanListSlice"), "TripPlanListSlice");

TripPlanPlacementListSlice decodeTripPlanPlacementListSlice(Object? response) =>
    TripPlanPlacementListSlice.fromWire(_requiredObject(response, "TripPlanPlacementListSlice"), "TripPlanPlacementListSlice");

TripPlanPlacementSlice decodeTripPlanPlacementSlice(Object? response) =>
    TripPlanPlacementSlice.fromWire(_requiredObject(response, "TripPlanPlacementSlice"), "TripPlanPlacementSlice");

TripPlanSlice decodeTripPlanSlice(Object? response) =>
    TripPlanSlice.fromWire(_requiredObject(response, "TripPlanSlice"), "TripPlanSlice");

TripPlanTemplate decodeTripPlanTemplate(Object? response) =>
    TripPlanTemplate.fromWire(_requiredObject(response, "TripPlanTemplate"), "TripPlanTemplate");

TripPlanTemplateListSlice decodeTripPlanTemplateListSlice(Object? response) =>
    TripPlanTemplateListSlice.fromWire(_requiredObject(response, "TripPlanTemplateListSlice"), "TripPlanTemplateListSlice");

TripShareSnapshot decodeTripShareSnapshot(Object? response) =>
    TripShareSnapshot.fromWire(_requiredObject(response, "TripShareSnapshot"), "TripShareSnapshot");

TripTimelineView decodeTripTimelineView(Object? response) =>
    TripTimelineView.fromWire(_requiredObject(response, "TripTimelineView"), "TripTimelineView");

Map<String, Object?> _requiredObject(Object? value, String path) {
  if (value is! Map<Object?, Object?>) {
    throw FormatException('$path must be an object');
  }
  final result = <String, Object?>{};
  for (final entry in value.entries) {
    final key = entry.key;
    if (key is! String) {
      throw FormatException('$path contains a non-string field name');
    }
    result[key] = entry.value;
  }
  return result;
}

void _rejectUnknownFields(
  Map<String, Object?> value,
  Set<String> allowed,
  String path,
) {
  final unknown = value.keys.where((key) => !allowed.contains(key)).toList()
    ..sort();
  if (unknown.isNotEmpty) {
    throw FormatException('$path contains unknown fields: ${unknown.join(', ')}');
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

int _requiredInt(Object? value, String path) {
  if (value is! int) throw FormatException('$path must be an int');
  return value;
}

bool _requiredBool(Object? value, String path) {
  if (value is! bool) throw FormatException('$path must be a bool');
  return value;
}

List<Object?> _requiredList(Object? value, String path) {
  if (value is! List<Object?>) {
    throw FormatException('$path must be a list');
  }
  return value;
}
