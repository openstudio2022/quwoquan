// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 38d9a30782053808eed9dafedb8a0299c7855b95cc45d809812cdd9512649746

part of '../../../content/content_operation_contracts.g.dart';

String? _normalizeGeneratedOptionalText(String? value) {
  final normalized = value?.trim();
  return normalized == null || normalized.isEmpty ? null : normalized;
}

List<String> _normalizeGeneratedTextList(
  Iterable<String> values, {
  required bool deduplicate,
}) {
  final result = <String>[];
  final seen = <String>{};
  for (final value in values) {
    final normalized = value.trim();
    if (normalized.isEmpty) continue;
    if (deduplicate && !seen.add(normalized)) continue;
    result.add(normalized);
  }
  return List<String>.unmodifiable(result);
}

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

double _generatedRequestDouble(Object? value, String path) {
  if (value is num) return value.toDouble();
  throw FormatException('$path must be a number');
}

bool _generatedRequestBool(Object? value, String path) {
  if (value is bool) return value;
  throw FormatException('$path must be a boolean');
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

final class AbortContentMediaUploadCommand {
  AbortContentMediaUploadCommand({required String sessionId})
    : sessionId = sessionId.trim() {
    if (this.sessionId.isEmpty) {
      throw ArgumentError.value(
        this.sessionId,
        "sessionId",
        'must not be blank',
      );
    }
  }

  final String sessionId;

  factory AbortContentMediaUploadCommand.fromWire(
    Map<String, Object?> map, [
    String path = "AbortContentMediaUploadCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "sessionId",
    }, path);
    return AbortContentMediaUploadCommand(
      sessionId: _generatedRequestString(map["sessionId"], '$path.sessionId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "sessionId": this.sessionId,
  };
}

final class AppendContentProfileInteractionReadFactCommand {
  AppendContentProfileInteractionReadFactCommand({
    required String personaId,
    required String activityId,
    required ProfileInteractionReadState state,
  }) : personaId = personaId.trim(),
       activityId = activityId.trim(),
       state = state {
    if (this.personaId.isEmpty) {
      throw ArgumentError.value(
        this.personaId,
        "personaId",
        'must not be blank',
      );
    }
    if (this.activityId.isEmpty) {
      throw ArgumentError.value(
        this.activityId,
        "activityId",
        'must not be blank',
      );
    }
  }

  final String personaId;
  final String activityId;
  final ProfileInteractionReadState state;

  factory AppendContentProfileInteractionReadFactCommand.fromWire(
    Map<String, Object?> map, [
    String path = "AppendContentProfileInteractionReadFactCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "personaId",
      "interactionId",
      "state",
    }, path);
    return AppendContentProfileInteractionReadFactCommand(
      personaId: _generatedRequestString(map["personaId"], '$path.personaId'),
      activityId: _generatedRequestString(
        map["interactionId"],
        '$path.interactionId',
      ),
      state: switch (map["state"]) {
        "seen" => ProfileInteractionReadState.seen,
        "read" => ProfileInteractionReadState.read,
        _ => throw FormatException(
          '$path.state' + ' has an invalid enum value',
        ),
      },
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "personaId": this.personaId,
    "interactionId": this.activityId,
    "state": this.state.wireName,
  };
}

final class BindContentCommentAttachmentsCommand {
  BindContentCommentAttachmentsCommand({
    required String commentId,
    required Iterable<String> attachmentMediaIds,
  }) : commentId = commentId.trim(),
       attachmentMediaIds = _normalizeGeneratedTextList(
         attachmentMediaIds,
         deduplicate: false,
       ) {
    if (this.commentId.isEmpty) {
      throw ArgumentError.value(
        this.commentId,
        "commentId",
        'must not be blank',
      );
    }
    if (this.attachmentMediaIds.isEmpty) {
      throw ArgumentError.value(
        this.attachmentMediaIds,
        "attachmentMediaIds",
        'must not be blank',
      );
    }
  }

  final String commentId;
  final List<String> attachmentMediaIds;

  factory BindContentCommentAttachmentsCommand.fromWire(
    Map<String, Object?> map, [
    String path = "BindContentCommentAttachmentsCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "commentId",
      "attachmentMediaIds",
    }, path);
    return BindContentCommentAttachmentsCommand(
      commentId: _generatedRequestString(map["commentId"], '$path.commentId'),
      attachmentMediaIds: List<String>.unmodifiable(
        _generatedRequestList(
          map["attachmentMediaIds"],
          '$path.attachmentMediaIds',
        ).asMap().entries.map(
          (entry) => _generatedRequestString(
            entry.value,
            '$path.attachmentMediaIds' + '[${entry.key}]',
          ),
        ),
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "commentId": this.commentId,
    "attachmentMediaIds": this.attachmentMediaIds
        .map((value) => value)
        .toList(growable: false),
  };
}

final class ChangeContentCommentPinCommand {
  ChangeContentCommentPinCommand({
    required String postId,
    required String commentId,
  }) : postId = postId.trim(),
       commentId = commentId.trim() {
    if (this.postId.isEmpty) {
      throw ArgumentError.value(this.postId, "postId", 'must not be blank');
    }
    if (this.commentId.isEmpty) {
      throw ArgumentError.value(
        this.commentId,
        "commentId",
        'must not be blank',
      );
    }
  }

  final String postId;
  final String commentId;

  factory ChangeContentCommentPinCommand.fromWire(
    Map<String, Object?> map, [
    String path = "ChangeContentCommentPinCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "postId",
      "commentId",
    }, path);
    return ChangeContentCommentPinCommand(
      postId: _generatedRequestString(map["postId"], '$path.postId'),
      commentId: _generatedRequestString(map["commentId"], '$path.commentId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "postId": this.postId,
    "commentId": this.commentId,
  };
}

final class CompleteContentMediaUploadCommand {
  CompleteContentMediaUploadCommand({
    required String sessionId,
    MediaAssetAccessPolicy accessPolicy = MediaAssetAccessPolicy.ownerOnly,
    MediaCaptureMetadata? captureMetadata,
  }) : sessionId = sessionId.trim(),
       accessPolicy = accessPolicy,
       captureMetadata = captureMetadata {
    if (this.sessionId.isEmpty) {
      throw ArgumentError.value(
        this.sessionId,
        "sessionId",
        'must not be blank',
      );
    }
  }

  final String sessionId;
  final MediaAssetAccessPolicy accessPolicy;
  final MediaCaptureMetadata? captureMetadata;

  factory CompleteContentMediaUploadCommand.fromWire(
    Map<String, Object?> map, [
    String path = "CompleteContentMediaUploadCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "sessionId",
      "accessPolicy",
      "captureMetadata",
    }, path);
    return CompleteContentMediaUploadCommand(
      sessionId: _generatedRequestString(map["sessionId"], '$path.sessionId'),
      accessPolicy: map.containsKey("accessPolicy")
          ? switch (map["accessPolicy"]) {
              "owner_only" => MediaAssetAccessPolicy.ownerOnly,
              "referenced_post" => MediaAssetAccessPolicy.referencedPost,
              "public" => MediaAssetAccessPolicy.public,
              _ => throw FormatException(
                '$path.accessPolicy' + ' has an invalid enum value',
              ),
            }
          : MediaAssetAccessPolicy.ownerOnly,
      captureMetadata: map["captureMetadata"] == null
          ? null
          : MediaCaptureMetadata.fromWire(
              _generatedRequestObject(
                map["captureMetadata"],
                '$path.captureMetadata',
              ),
              '$path.captureMetadata',
            ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "sessionId": this.sessionId,
    "accessPolicy": this.accessPolicy.wireName,
    if (this.captureMetadata != null)
      "captureMetadata": this.captureMetadata!.toWire(),
  };
}

final class ContentAuthorPostsQuery {
  static const int defaultLimit = 20;
  static const int maximumLimit = 100;

  ContentAuthorPostsQuery({
    required String personaId,
    String? identity,
    String? type,
    String? visibility,
    String? cursor,
    int limit = 20,
  }) : personaId = personaId,
       identity = identity,
       type = type,
       visibility = visibility,
       cursor = cursor,
       limit = limit {
    if (this.limit <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit > 100) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 100");
    }
  }

  final String personaId;
  final String? identity;
  final String? type;
  final String? visibility;
  final String? cursor;
  final int limit;

  factory ContentAuthorPostsQuery.fromWire(
    Map<String, Object?> map, [
    String path = "ContentAuthorPostsQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "personaId",
      "identity",
      "type",
      "visibility",
      "cursor",
      "limit",
    }, path);
    return ContentAuthorPostsQuery(
      personaId: _generatedRequestString(map["personaId"], '$path.personaId'),
      identity: map["identity"] == null
          ? null
          : _generatedRequestString(map["identity"], '$path.identity'),
      type: map["type"] == null
          ? null
          : _generatedRequestString(map["type"], '$path.type'),
      visibility: map["visibility"] == null
          ? null
          : _generatedRequestString(map["visibility"], '$path.visibility'),
      cursor: map["cursor"] == null
          ? null
          : _generatedRequestString(map["cursor"], '$path.cursor'),
      limit: map.containsKey("limit")
          ? _generatedRequestInt(map["limit"], '$path.limit')
          : 20,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "personaId": this.personaId,
    if (this.identity != null) "identity": this.identity!,
    if (this.type != null) "type": this.type!,
    if (this.visibility != null) "visibility": this.visibility!,
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

final class ContentBehaviorEventWire {
  ContentBehaviorEventWire({
    required String clientEventId,
    required DateTime occurredAt,
    String? contentId,
    required BehaviorEventType action,
    String? state,
    ContentType? contentType,
    String? objectId,
    String? objectKind,
    String? displayName,
    String? sourceSurface,
    List<String>? tagRefs,
    double? duration,
    String? feedRequestId,
    int? position,
    String? channelId,
    String? policyDigest,
    String? recallPath,
    String? contentVertical,
    String? supplySource,
    int? commentLength,
    String? authorId,
    String? referralSource,
    int? engagementDepth,
    double? consumedRatio,
    int? totalUnits,
    int? effectivePlayMs,
    String? feedSessionId,
    String? playbackSessionId,
    List<String>? entityRefs,
    String? pageVisitId,
    IntersectionDimension? intersectionDimension,
    String? intersectionSourceRef,
    List<String>? intersectionTagRefs,
    String? intersectionId,
    String? intersectionClass,
    String? intersectionEvidenceId,
    String? subjectId,
    String? feedbackKind,
    String? taxonomyReleaseId,
    String? direction,
    String? motionProfile,
    int? settleMs,
    bool? reducedMotion,
    bool? committed,
  }) : clientEventId = clientEventId,
       occurredAt = occurredAt,
       contentId = contentId,
       action = action,
       state = state,
       contentType = contentType,
       objectId = objectId,
       objectKind = objectKind,
       displayName = displayName,
       sourceSurface = sourceSurface,
       tagRefs = tagRefs == null ? null : List.unmodifiable(tagRefs),
       duration = duration,
       feedRequestId = feedRequestId,
       position = position,
       channelId = channelId,
       policyDigest = policyDigest,
       recallPath = recallPath,
       contentVertical = contentVertical,
       supplySource = supplySource,
       commentLength = commentLength,
       authorId = authorId,
       referralSource = referralSource,
       engagementDepth = engagementDepth,
       consumedRatio = consumedRatio,
       totalUnits = totalUnits,
       effectivePlayMs = effectivePlayMs,
       feedSessionId = feedSessionId,
       playbackSessionId = playbackSessionId,
       entityRefs = entityRefs == null ? null : List.unmodifiable(entityRefs),
       pageVisitId = pageVisitId,
       intersectionDimension = intersectionDimension,
       intersectionSourceRef = intersectionSourceRef,
       intersectionTagRefs = intersectionTagRefs == null
           ? null
           : List.unmodifiable(intersectionTagRefs),
       intersectionId = intersectionId,
       intersectionClass = intersectionClass,
       intersectionEvidenceId = intersectionEvidenceId,
       subjectId = subjectId,
       feedbackKind = feedbackKind,
       taxonomyReleaseId = taxonomyReleaseId,
       direction = direction,
       motionProfile = motionProfile,
       settleMs = settleMs,
       reducedMotion = reducedMotion,
       committed = committed {
    if (this.clientEventId.isEmpty) {
      throw ArgumentError.value(
        this.clientEventId,
        "clientEventId",
        'must not be blank',
      );
    }
    if (this.position != null && this.position! < 0) {
      throw ArgumentError.value(
        this.position,
        "position",
        "must be at least 0",
      );
    }
    if (this.commentLength != null && this.commentLength! < 0) {
      throw ArgumentError.value(
        this.commentLength,
        "commentLength",
        "must be at least 0",
      );
    }
    if (this.engagementDepth != null && this.engagementDepth! < 0) {
      throw ArgumentError.value(
        this.engagementDepth,
        "engagementDepth",
        "must be at least 0",
      );
    }
    if (this.totalUnits != null && this.totalUnits! < 0) {
      throw ArgumentError.value(
        this.totalUnits,
        "totalUnits",
        "must be at least 0",
      );
    }
    if (this.effectivePlayMs != null && this.effectivePlayMs! < 0) {
      throw ArgumentError.value(
        this.effectivePlayMs,
        "effectivePlayMs",
        "must be at least 0",
      );
    }
    if (this.settleMs != null && this.settleMs! < 0) {
      throw ArgumentError.value(
        this.settleMs,
        "settleMs",
        "must be at least 0",
      );
    }
  }

  final String clientEventId;
  final DateTime occurredAt;
  final String? contentId;
  final BehaviorEventType action;
  final String? state;
  final ContentType? contentType;
  final String? objectId;
  final String? objectKind;
  final String? displayName;
  final String? sourceSurface;
  final List<String>? tagRefs;
  final double? duration;
  final String? feedRequestId;
  final int? position;
  final String? channelId;
  final String? policyDigest;
  final String? recallPath;
  final String? contentVertical;
  final String? supplySource;
  final int? commentLength;
  final String? authorId;
  final String? referralSource;
  final int? engagementDepth;
  final double? consumedRatio;
  final int? totalUnits;
  final int? effectivePlayMs;
  final String? feedSessionId;
  final String? playbackSessionId;
  final List<String>? entityRefs;
  final String? pageVisitId;
  final IntersectionDimension? intersectionDimension;
  final String? intersectionSourceRef;
  final List<String>? intersectionTagRefs;
  final String? intersectionId;
  final String? intersectionClass;
  final String? intersectionEvidenceId;
  final String? subjectId;
  final String? feedbackKind;
  final String? taxonomyReleaseId;
  final String? direction;
  final String? motionProfile;
  final int? settleMs;
  final bool? reducedMotion;
  final bool? committed;

  factory ContentBehaviorEventWire.fromWire(
    Map<String, Object?> map, [
    String path = "ContentBehaviorEventWire",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "clientEventId",
      "occurredAt",
      "contentId",
      "action",
      "state",
      "contentType",
      "objectId",
      "objectKind",
      "displayName",
      "sourceSurface",
      "tagRefs",
      "duration",
      "feedRequestId",
      "position",
      "channelId",
      "policyDigest",
      "recallPath",
      "contentVertical",
      "supplySource",
      "commentLength",
      "authorId",
      "referralSource",
      "engagementDepth",
      "consumedRatio",
      "totalUnits",
      "effectivePlayMs",
      "feedSessionId",
      "playbackSessionId",
      "entityRefs",
      "pageVisitId",
      "intersectionDimension",
      "intersectionSourceRef",
      "intersectionTagRefs",
      "intersectionId",
      "intersectionClass",
      "intersectionEvidenceId",
      "subjectId",
      "feedbackKind",
      "taxonomyReleaseId",
      "direction",
      "motionProfile",
      "settleMs",
      "reducedMotion",
      "committed",
    }, path);
    return ContentBehaviorEventWire(
      clientEventId: _generatedRequestString(
        map["clientEventId"],
        '$path.clientEventId',
      ),
      occurredAt: _generatedRequestTimestamp(
        map["occurredAt"],
        '$path.occurredAt',
      ),
      contentId: map["contentId"] == null
          ? null
          : _generatedRequestString(map["contentId"], '$path.contentId'),
      action: switch (map["action"]) {
        "impression" => BehaviorEventType.impression,
        "click" => BehaviorEventType.click,
        "dwell" => BehaviorEventType.dwell,
        "like" => BehaviorEventType.like,
        "dislike" => BehaviorEventType.dislike,
        "undo_dislike" => BehaviorEventType.undoDislike,
        "hide_author" => BehaviorEventType.hideAuthor,
        "hide_content_type" => BehaviorEventType.hideContentType,
        "report" => BehaviorEventType.report,
        "share" => BehaviorEventType.share,
        "comment" => BehaviorEventType.comment,
        "intersection_expand" => BehaviorEventType.intersectionExpand,
        "intersection_feedback" => BehaviorEventType.intersectionFeedback,
        "wishlist_add" => BehaviorEventType.wishlistAdd,
        "wishlist_remove" => BehaviorEventType.wishlistRemove,
        "skip" => BehaviorEventType.skip,
        "follow" => BehaviorEventType.follow,
        "join_circle" => BehaviorEventType.joinCircle,
        "leave_circle" => BehaviorEventType.leaveCircle,
        "add_contact" => BehaviorEventType.addContact,
        "author_view" => BehaviorEventType.authorView,
        "entity_page_view" => BehaviorEventType.entityPageView,
        "tag_click" => BehaviorEventType.tagClick,
        "content_depth" => BehaviorEventType.contentDepth,
        "play_progress" => BehaviorEventType.playProgress,
        "effective_play" => BehaviorEventType.effectivePlay,
        "assistant_interest" => BehaviorEventType.assistantInterest,
        "onboarding_interest" => BehaviorEventType.onboardingInterest,
        _ => throw FormatException(
          '$path.action' + ' has an invalid enum value',
        ),
      },
      state: map["state"] == null
          ? null
          : _generatedRequestString(map["state"], '$path.state'),
      contentType: map["contentType"] == null
          ? null
          : switch (map["contentType"]) {
              "image" => ContentType.image,
              "video" => ContentType.video,
              "micro" => ContentType.micro,
              "article" => ContentType.article,
              _ => throw FormatException(
                '$path.contentType' + ' has an invalid enum value',
              ),
            },
      objectId: map["objectId"] == null
          ? null
          : _generatedRequestString(map["objectId"], '$path.objectId'),
      objectKind: map["objectKind"] == null
          ? null
          : _generatedRequestString(map["objectKind"], '$path.objectKind'),
      displayName: map["displayName"] == null
          ? null
          : _generatedRequestString(map["displayName"], '$path.displayName'),
      sourceSurface: map["sourceSurface"] == null
          ? null
          : _generatedRequestString(
              map["sourceSurface"],
              '$path.sourceSurface',
            ),
      tagRefs: map["tagRefs"] == null
          ? null
          : List<String>.unmodifiable(
              _generatedRequestList(
                map["tagRefs"],
                '$path.tagRefs',
              ).asMap().entries.map(
                (entry) => _generatedRequestString(
                  entry.value,
                  '$path.tagRefs' + '[${entry.key}]',
                ),
              ),
            ),
      duration: map["duration"] == null
          ? null
          : _generatedRequestDouble(map["duration"], '$path.duration'),
      feedRequestId: map["feedRequestId"] == null
          ? null
          : _generatedRequestString(
              map["feedRequestId"],
              '$path.feedRequestId',
            ),
      position: map["position"] == null
          ? null
          : _generatedRequestInt(map["position"], '$path.position'),
      channelId: map["channelId"] == null
          ? null
          : _generatedRequestString(map["channelId"], '$path.channelId'),
      policyDigest: map["policyDigest"] == null
          ? null
          : _generatedRequestString(map["policyDigest"], '$path.policyDigest'),
      recallPath: map["recallPath"] == null
          ? null
          : _generatedRequestString(map["recallPath"], '$path.recallPath'),
      contentVertical: map["contentVertical"] == null
          ? null
          : _generatedRequestString(
              map["contentVertical"],
              '$path.contentVertical',
            ),
      supplySource: map["supplySource"] == null
          ? null
          : _generatedRequestString(map["supplySource"], '$path.supplySource'),
      commentLength: map["commentLength"] == null
          ? null
          : _generatedRequestInt(map["commentLength"], '$path.commentLength'),
      authorId: map["authorId"] == null
          ? null
          : _generatedRequestString(map["authorId"], '$path.authorId'),
      referralSource: map["referralSource"] == null
          ? null
          : _generatedRequestString(
              map["referralSource"],
              '$path.referralSource',
            ),
      engagementDepth: map["engagementDepth"] == null
          ? null
          : _generatedRequestInt(
              map["engagementDepth"],
              '$path.engagementDepth',
            ),
      consumedRatio: map["consumedRatio"] == null
          ? null
          : _generatedRequestDouble(
              map["consumedRatio"],
              '$path.consumedRatio',
            ),
      totalUnits: map["totalUnits"] == null
          ? null
          : _generatedRequestInt(map["totalUnits"], '$path.totalUnits'),
      effectivePlayMs: map["effectivePlayMs"] == null
          ? null
          : _generatedRequestInt(
              map["effectivePlayMs"],
              '$path.effectivePlayMs',
            ),
      feedSessionId: map["feedSessionId"] == null
          ? null
          : _generatedRequestString(
              map["feedSessionId"],
              '$path.feedSessionId',
            ),
      playbackSessionId: map["playbackSessionId"] == null
          ? null
          : _generatedRequestString(
              map["playbackSessionId"],
              '$path.playbackSessionId',
            ),
      entityRefs: map["entityRefs"] == null
          ? null
          : List<String>.unmodifiable(
              _generatedRequestList(
                map["entityRefs"],
                '$path.entityRefs',
              ).asMap().entries.map(
                (entry) => _generatedRequestString(
                  entry.value,
                  '$path.entityRefs' + '[${entry.key}]',
                ),
              ),
            ),
      pageVisitId: map["pageVisitId"] == null
          ? null
          : _generatedRequestString(map["pageVisitId"], '$path.pageVisitId'),
      intersectionDimension: map["intersectionDimension"] == null
          ? null
          : switch (map["intersectionDimension"]) {
              "identity" => IntersectionDimension.identity,
              "location" => IntersectionDimension.location,
              "content" => IntersectionDimension.content,
              "interest" => IntersectionDimension.interest,
              "relationship" => IntersectionDimension.relationship,
              _ => throw FormatException(
                '$path.intersectionDimension' + ' has an invalid enum value',
              ),
            },
      intersectionSourceRef: map["intersectionSourceRef"] == null
          ? null
          : _generatedRequestString(
              map["intersectionSourceRef"],
              '$path.intersectionSourceRef',
            ),
      intersectionTagRefs: map["intersectionTagRefs"] == null
          ? null
          : List<String>.unmodifiable(
              _generatedRequestList(
                map["intersectionTagRefs"],
                '$path.intersectionTagRefs',
              ).asMap().entries.map(
                (entry) => _generatedRequestString(
                  entry.value,
                  '$path.intersectionTagRefs' + '[${entry.key}]',
                ),
              ),
            ),
      intersectionId: map["intersectionId"] == null
          ? null
          : _generatedRequestString(
              map["intersectionId"],
              '$path.intersectionId',
            ),
      intersectionClass: map["intersectionClass"] == null
          ? null
          : _generatedRequestString(
              map["intersectionClass"],
              '$path.intersectionClass',
            ),
      intersectionEvidenceId: map["intersectionEvidenceId"] == null
          ? null
          : _generatedRequestString(
              map["intersectionEvidenceId"],
              '$path.intersectionEvidenceId',
            ),
      subjectId: map["subjectId"] == null
          ? null
          : _generatedRequestString(map["subjectId"], '$path.subjectId'),
      feedbackKind: map["feedbackKind"] == null
          ? null
          : _generatedRequestString(map["feedbackKind"], '$path.feedbackKind'),
      taxonomyReleaseId: map["taxonomyReleaseId"] == null
          ? null
          : _generatedRequestString(
              map["taxonomyReleaseId"],
              '$path.taxonomyReleaseId',
            ),
      direction: map["direction"] == null
          ? null
          : _generatedRequestString(map["direction"], '$path.direction'),
      motionProfile: map["motionProfile"] == null
          ? null
          : _generatedRequestString(
              map["motionProfile"],
              '$path.motionProfile',
            ),
      settleMs: map["settleMs"] == null
          ? null
          : _generatedRequestInt(map["settleMs"], '$path.settleMs'),
      reducedMotion: map["reducedMotion"] == null
          ? null
          : _generatedRequestBool(map["reducedMotion"], '$path.reducedMotion'),
      committed: map["committed"] == null
          ? null
          : _generatedRequestBool(map["committed"], '$path.committed'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "clientEventId": this.clientEventId,
    "occurredAt": this.occurredAt.toUtc().toIso8601String(),
    if (this.contentId != null) "contentId": this.contentId!,
    "action": this.action.wireName,
    if (this.state != null) "state": this.state!,
    if (this.contentType != null) "contentType": this.contentType!.wireName,
    if (this.objectId != null) "objectId": this.objectId!,
    if (this.objectKind != null) "objectKind": this.objectKind!,
    if (this.displayName != null) "displayName": this.displayName!,
    if (this.sourceSurface != null) "sourceSurface": this.sourceSurface!,
    if (this.tagRefs != null)
      "tagRefs": this.tagRefs!.map((value) => value).toList(growable: false),
    if (this.duration != null) "duration": this.duration!,
    if (this.feedRequestId != null) "feedRequestId": this.feedRequestId!,
    if (this.position != null) "position": this.position!,
    if (this.channelId != null) "channelId": this.channelId!,
    if (this.policyDigest != null) "policyDigest": this.policyDigest!,
    if (this.recallPath != null) "recallPath": this.recallPath!,
    if (this.contentVertical != null) "contentVertical": this.contentVertical!,
    if (this.supplySource != null) "supplySource": this.supplySource!,
    if (this.commentLength != null) "commentLength": this.commentLength!,
    if (this.authorId != null) "authorId": this.authorId!,
    if (this.referralSource != null) "referralSource": this.referralSource!,
    if (this.engagementDepth != null) "engagementDepth": this.engagementDepth!,
    if (this.consumedRatio != null) "consumedRatio": this.consumedRatio!,
    if (this.totalUnits != null) "totalUnits": this.totalUnits!,
    if (this.effectivePlayMs != null) "effectivePlayMs": this.effectivePlayMs!,
    if (this.feedSessionId != null) "feedSessionId": this.feedSessionId!,
    if (this.playbackSessionId != null)
      "playbackSessionId": this.playbackSessionId!,
    if (this.entityRefs != null)
      "entityRefs": this.entityRefs!
          .map((value) => value)
          .toList(growable: false),
    if (this.pageVisitId != null) "pageVisitId": this.pageVisitId!,
    if (this.intersectionDimension != null)
      "intersectionDimension": this.intersectionDimension!.wireName,
    if (this.intersectionSourceRef != null)
      "intersectionSourceRef": this.intersectionSourceRef!,
    if (this.intersectionTagRefs != null)
      "intersectionTagRefs": this.intersectionTagRefs!
          .map((value) => value)
          .toList(growable: false),
    if (this.intersectionId != null) "intersectionId": this.intersectionId!,
    if (this.intersectionClass != null)
      "intersectionClass": this.intersectionClass!,
    if (this.intersectionEvidenceId != null)
      "intersectionEvidenceId": this.intersectionEvidenceId!,
    if (this.subjectId != null) "subjectId": this.subjectId!,
    if (this.feedbackKind != null) "feedbackKind": this.feedbackKind!,
    if (this.taxonomyReleaseId != null)
      "taxonomyReleaseId": this.taxonomyReleaseId!,
    if (this.direction != null) "direction": this.direction!,
    if (this.motionProfile != null) "motionProfile": this.motionProfile!,
    if (this.settleMs != null) "settleMs": this.settleMs!,
    if (this.reducedMotion != null) "reducedMotion": this.reducedMotion!,
    if (this.committed != null) "committed": this.committed!,
  };
}

final class ContentCommentPageQuery {
  static const int defaultLimit = 20;
  static const int maximumLimit = 100;

  ContentCommentPageQuery({String? cursor, int limit = 20})
    : cursor = _normalizeGeneratedOptionalText(cursor),
      limit = limit {
    if (this.limit <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit > 100) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 100");
    }
  }

  final String? cursor;
  final int limit;

  factory ContentCommentPageQuery.fromWire(
    Map<String, Object?> map, [
    String path = "ContentCommentPageQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "cursor",
      "limit",
    }, path);
    return ContentCommentPageQuery(
      cursor: map["cursor"] == null
          ? null
          : _generatedRequestString(map["cursor"], '$path.cursor'),
      limit: map.containsKey("limit")
          ? _generatedRequestInt(map["limit"], '$path.limit')
          : 20,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

final class ContentDiscoveryFeedQuery {
  static const int defaultLimit = 20;
  static const int maximumLimit = 20;

  ContentDiscoveryFeedQuery({
    String? identity,
    String? type,
    String? sort,
    String? cursor,
    String? subCategory,
    String? channelId,
    String? sessionId,
    String? feedRequestId,
    int limit = 20,
    Iterable<String> blockedKeywords = const <String>[],
  }) : identity = identity,
       type = type,
       sort = sort,
       cursor = cursor,
       subCategory = subCategory,
       channelId = channelId,
       sessionId = sessionId,
       feedRequestId = feedRequestId,
       limit = limit,
       blockedKeywords = List.unmodifiable(blockedKeywords) {
    if (this.limit <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit > 20) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 20");
    }
  }

  final String? identity;
  final String? type;
  final String? sort;
  final String? cursor;
  final String? subCategory;
  final String? channelId;
  final String? sessionId;
  final String? feedRequestId;
  final int limit;
  final List<String> blockedKeywords;

  factory ContentDiscoveryFeedQuery.fromWire(
    Map<String, Object?> map, [
    String path = "ContentDiscoveryFeedQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "identity",
      "type",
      "sort",
      "cursor",
      "subCategory",
      "channelId",
      "sessionId",
      "feedRequestId",
      "limit",
      "X-Blocked-Keywords",
    }, path);
    return ContentDiscoveryFeedQuery(
      identity: map["identity"] == null
          ? null
          : _generatedRequestString(map["identity"], '$path.identity'),
      type: map["type"] == null
          ? null
          : _generatedRequestString(map["type"], '$path.type'),
      sort: map["sort"] == null
          ? null
          : _generatedRequestString(map["sort"], '$path.sort'),
      cursor: map["cursor"] == null
          ? null
          : _generatedRequestString(map["cursor"], '$path.cursor'),
      subCategory: map["subCategory"] == null
          ? null
          : _generatedRequestString(map["subCategory"], '$path.subCategory'),
      channelId: map["channelId"] == null
          ? null
          : _generatedRequestString(map["channelId"], '$path.channelId'),
      sessionId: map["sessionId"] == null
          ? null
          : _generatedRequestString(map["sessionId"], '$path.sessionId'),
      feedRequestId: map["feedRequestId"] == null
          ? null
          : _generatedRequestString(
              map["feedRequestId"],
              '$path.feedRequestId',
            ),
      limit: map.containsKey("limit")
          ? _generatedRequestInt(map["limit"], '$path.limit')
          : 20,
      blockedKeywords: map.containsKey("X-Blocked-Keywords")
          ? List<String>.unmodifiable(
              _generatedRequestString(
                    map["X-Blocked-Keywords"],
                    '$path.X-Blocked-Keywords',
                  )
                  .split(',')
                  .where((value) => value.isNotEmpty)
                  .map(Uri.decodeQueryComponent),
            )
          : const <String>[],
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (this.identity != null) "identity": this.identity!,
    if (this.type != null) "type": this.type!,
    if (this.sort != null) "sort": this.sort!,
    if (this.cursor != null) "cursor": this.cursor!,
    if (this.subCategory != null) "subCategory": this.subCategory!,
    if (this.channelId != null) "channelId": this.channelId!,
    if (this.sessionId != null) "sessionId": this.sessionId!,
    if (this.feedRequestId != null) "feedRequestId": this.feedRequestId!,
    "limit": this.limit,
    if (this.blockedKeywords.isNotEmpty)
      "X-Blocked-Keywords": this.blockedKeywords
          .map(Uri.encodeQueryComponent)
          .join(','),
  };
}

final class ContentFootprintQuery {
  static const int defaultLimit = 20;
  static const int maximumLimit = 100;

  ContentFootprintQuery({String? type, String? cursor, int limit = 20})
    : type = type,
      cursor = cursor,
      limit = limit {
    if (this.limit <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit > 100) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 100");
    }
  }

  final String? type;
  final String? cursor;
  final int limit;

  factory ContentFootprintQuery.fromWire(
    Map<String, Object?> map, [
    String path = "ContentFootprintQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "type",
      "cursor",
      "limit",
    }, path);
    return ContentFootprintQuery(
      type: map["type"] == null
          ? null
          : _generatedRequestString(map["type"], '$path.type'),
      cursor: map["cursor"] == null
          ? null
          : _generatedRequestString(map["cursor"], '$path.cursor'),
      limit: map.containsKey("limit")
          ? _generatedRequestInt(map["limit"], '$path.limit')
          : 20,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (this.type != null) "type": this.type!,
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

final class ContentGatheringPostsQuery {
  static const int defaultLimit = 20;
  static const int maximumLimit = 100;

  ContentGatheringPostsQuery({
    required String gatheringId,
    String? cursor,
    int limit = 20,
  }) : gatheringId = gatheringId.trim(),
       cursor = cursor,
       limit = limit {
    if (this.gatheringId.isEmpty) {
      throw ArgumentError.value(
        this.gatheringId,
        "gatheringId",
        'must not be blank',
      );
    }
    if (this.limit <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit > 100) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 100");
    }
  }

  final String gatheringId;
  final String? cursor;
  final int limit;

  factory ContentGatheringPostsQuery.fromWire(
    Map<String, Object?> map, [
    String path = "ContentGatheringPostsQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "gatheringId",
      "cursor",
      "limit",
    }, path);
    return ContentGatheringPostsQuery(
      gatheringId: _generatedRequestString(
        map["gatheringId"],
        '$path.gatheringId',
      ),
      cursor: map["cursor"] == null
          ? null
          : _generatedRequestString(map["cursor"], '$path.cursor'),
      limit: map.containsKey("limit")
          ? _generatedRequestInt(map["limit"], '$path.limit')
          : 20,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "gatheringId": this.gatheringId,
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

final class ContentMyReportsQuery {
  static const int defaultLimit = 20;
  static const int maximumLimit = 100;

  ContentMyReportsQuery({String? cursor, int limit = 20})
    : cursor = cursor,
      limit = limit {
    if (this.limit <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit > 100) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 100");
    }
  }

  final String? cursor;
  final int limit;

  factory ContentMyReportsQuery.fromWire(
    Map<String, Object?> map, [
    String path = "ContentMyReportsQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "cursor",
      "limit",
    }, path);
    return ContentMyReportsQuery(
      cursor: map["cursor"] == null
          ? null
          : _generatedRequestString(map["cursor"], '$path.cursor'),
      limit: map.containsKey("limit")
          ? _generatedRequestInt(map["limit"], '$path.limit')
          : 20,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

final class ContentPostDetailQuery {
  const ContentPostDetailQuery({required String postId}) : postId = postId;

  final String postId;

  factory ContentPostDetailQuery.fromWire(
    Map<String, Object?> map, [
    String path = "ContentPostDetailQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"postId"}, path);
    return ContentPostDetailQuery(
      postId: _generatedRequestString(map["postId"], '$path.postId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{"postId": this.postId};
}

final class ContentProfileInteractionPageQuery {
  static const int defaultLimit = 20;
  static const int maximumLimit = 50;

  ContentProfileInteractionPageQuery({
    required String personaId,
    required InteractionActivityType type,
    String? cursor,
    int limit = 20,
  }) : personaId = personaId.trim(),
       type = type,
       cursor = cursor,
       limit = limit {
    if (this.personaId.isEmpty) {
      throw ArgumentError.value(
        this.personaId,
        "personaId",
        'must not be blank',
      );
    }
    if (this.limit <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit > 50) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 50");
    }
  }

  final String personaId;
  final InteractionActivityType type;
  final String? cursor;
  final int limit;

  factory ContentProfileInteractionPageQuery.fromWire(
    Map<String, Object?> map, [
    String path = "ContentProfileInteractionPageQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "personaId",
      "type",
      "cursor",
      "limit",
    }, path);
    return ContentProfileInteractionPageQuery(
      personaId: _generatedRequestString(map["personaId"], '$path.personaId'),
      type: switch (map["type"]) {
        "like" => InteractionActivityType.like,
        "comment" => InteractionActivityType.comment,
        "share" => InteractionActivityType.share,
        _ => throw FormatException('$path.type' + ' has an invalid enum value'),
      },
      cursor: map["cursor"] == null
          ? null
          : _generatedRequestString(map["cursor"], '$path.cursor'),
      limit: map.containsKey("limit")
          ? _generatedRequestInt(map["limit"], '$path.limit')
          : 20,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "personaId": this.personaId,
    "type": this.type.wireName,
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

final class CreateContentCommentCommand {
  CreateContentCommentCommand({
    required String postId,
    required String content,
    String? replyToCommentId,
    Iterable<String> attachmentMediaIds = const <String>[],
    Iterable<CommentMention> mentions = const <CommentMention>[],
    String? authorDisplayNameSnapshot,
    String? authorAvatarUrlSnapshot,
    int? personaContextVersion,
  }) : postId = postId.trim(),
       content = content.trim(),
       replyToCommentId = _normalizeGeneratedOptionalText(replyToCommentId),
       attachmentMediaIds = _normalizeGeneratedTextList(
         attachmentMediaIds,
         deduplicate: false,
       ),
       mentions = List.unmodifiable(mentions),
       authorDisplayNameSnapshot = _normalizeGeneratedOptionalText(
         authorDisplayNameSnapshot,
       ),
       authorAvatarUrlSnapshot = _normalizeGeneratedOptionalText(
         authorAvatarUrlSnapshot,
       ),
       personaContextVersion = personaContextVersion {
    if (this.postId.isEmpty) {
      throw ArgumentError.value(this.postId, "postId", 'must not be blank');
    }
    if (this.content.isEmpty) {
      throw ArgumentError.value(this.content, "content", 'must not be blank');
    }
  }

  final String postId;
  final String content;
  final String? replyToCommentId;
  final List<String> attachmentMediaIds;
  final List<CommentMention> mentions;
  final String? authorDisplayNameSnapshot;
  final String? authorAvatarUrlSnapshot;
  final int? personaContextVersion;

  factory CreateContentCommentCommand.fromWire(
    Map<String, Object?> map, [
    String path = "CreateContentCommentCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "postId",
      "content",
      "replyToCommentId",
      "attachmentMediaIds",
      "mentions",
      "authorDisplayNameSnapshot",
      "authorAvatarUrlSnapshot",
      "personaContextVersion",
    }, path);
    return CreateContentCommentCommand(
      postId: _generatedRequestString(map["postId"], '$path.postId'),
      content: _generatedRequestString(map["content"], '$path.content'),
      replyToCommentId: map["replyToCommentId"] == null
          ? null
          : _generatedRequestString(
              map["replyToCommentId"],
              '$path.replyToCommentId',
            ),
      attachmentMediaIds: map.containsKey("attachmentMediaIds")
          ? List<String>.unmodifiable(
              _generatedRequestList(
                map["attachmentMediaIds"],
                '$path.attachmentMediaIds',
              ).asMap().entries.map(
                (entry) => _generatedRequestString(
                  entry.value,
                  '$path.attachmentMediaIds' + '[${entry.key}]',
                ),
              ),
            )
          : const <String>[],
      mentions: map.containsKey("mentions")
          ? List<CommentMention>.unmodifiable(
              _generatedRequestList(
                map["mentions"],
                '$path.mentions',
              ).asMap().entries.map(
                (entry) => CommentMention.fromWire(
                  _generatedRequestObject(
                    entry.value,
                    '$path.mentions' + '[${entry.key}]',
                  ),
                  '$path.mentions' + '[${entry.key}]',
                ),
              ),
            )
          : const <CommentMention>[],
      authorDisplayNameSnapshot: map["authorDisplayNameSnapshot"] == null
          ? null
          : _generatedRequestString(
              map["authorDisplayNameSnapshot"],
              '$path.authorDisplayNameSnapshot',
            ),
      authorAvatarUrlSnapshot: map["authorAvatarUrlSnapshot"] == null
          ? null
          : _generatedRequestString(
              map["authorAvatarUrlSnapshot"],
              '$path.authorAvatarUrlSnapshot',
            ),
      personaContextVersion: map["personaContextVersion"] == null
          ? null
          : _generatedRequestInt(
              map["personaContextVersion"],
              '$path.personaContextVersion',
            ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "postId": this.postId,
    "content": this.content,
    if (this.replyToCommentId != null)
      "replyToCommentId": this.replyToCommentId!,
    "attachmentMediaIds": this.attachmentMediaIds
        .map((value) => value)
        .toList(growable: false),
    "mentions": this.mentions
        .map((value) => value.toWire())
        .toList(growable: false),
    if (this.authorDisplayNameSnapshot != null)
      "authorDisplayNameSnapshot": this.authorDisplayNameSnapshot!,
    if (this.authorAvatarUrlSnapshot != null)
      "authorAvatarUrlSnapshot": this.authorAvatarUrlSnapshot!,
    if (this.personaContextVersion != null)
      "personaContextVersion": this.personaContextVersion!,
  };
}

final class CreateContentOutboundShareCommand {
  CreateContentOutboundShareCommand({
    required String postId,
    required OutboundShareChannel channel,
    required OutboundShareDestinationKind destinationKind,
    String? destination,
    required String referralId,
    required String providerReceiptId,
    required DateTime clientConfirmedAt,
  }) : postId = postId.trim(),
       channel = channel,
       destinationKind = destinationKind,
       destination = _normalizeGeneratedOptionalText(destination),
       referralId = referralId.trim(),
       providerReceiptId = providerReceiptId.trim(),
       clientConfirmedAt = clientConfirmedAt.toUtc() {
    if (this.postId.isEmpty) {
      throw ArgumentError.value(this.postId, "postId", 'must not be blank');
    }
    if (this.referralId.isEmpty) {
      throw ArgumentError.value(
        this.referralId,
        "referralId",
        'must not be blank',
      );
    }
    if (this.providerReceiptId.isEmpty) {
      throw ArgumentError.value(
        this.providerReceiptId,
        "providerReceiptId",
        'must not be blank',
      );
    }
  }

  final String postId;
  final OutboundShareChannel channel;
  final OutboundShareDestinationKind destinationKind;
  final String? destination;
  final String referralId;
  final String providerReceiptId;
  final DateTime clientConfirmedAt;

  factory CreateContentOutboundShareCommand.fromWire(
    Map<String, Object?> map, [
    String path = "CreateContentOutboundShareCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "postId",
      "channel",
      "destinationKind",
      "destination",
      "referralId",
      "providerReceiptId",
      "clientConfirmedAt",
    }, path);
    return CreateContentOutboundShareCommand(
      postId: _generatedRequestString(map["postId"], '$path.postId'),
      channel: switch (map["channel"]) {
        "system_share" => OutboundShareChannel.systemShare,
        "wechat_friend" => OutboundShareChannel.wechatFriend,
        "wechat_moments" => OutboundShareChannel.wechatMoments,
        _ => throw FormatException(
          '$path.channel' + ' has an invalid enum value',
        ),
      },
      destinationKind: switch (map["destinationKind"]) {
        "external_app" => OutboundShareDestinationKind.externalApp,
        _ => throw FormatException(
          '$path.destinationKind' + ' has an invalid enum value',
        ),
      },
      destination: map["destination"] == null
          ? null
          : _generatedRequestString(map["destination"], '$path.destination'),
      referralId: _generatedRequestString(
        map["referralId"],
        '$path.referralId',
      ),
      providerReceiptId: _generatedRequestString(
        map["providerReceiptId"],
        '$path.providerReceiptId',
      ),
      clientConfirmedAt: _generatedRequestTimestamp(
        map["clientConfirmedAt"],
        '$path.clientConfirmedAt',
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "postId": this.postId,
    "channel": this.channel.wireName,
    "destinationKind": this.destinationKind.wireName,
    if (this.destination != null) "destination": this.destination!,
    "referralId": this.referralId,
    "providerReceiptId": this.providerReceiptId,
    "clientConfirmedAt": this.clientConfirmedAt.toUtc().toIso8601String(),
  };
}

final class CreateContentReportCommand {
  CreateContentReportCommand({
    required String targetId,
    required ReportTargetType targetType,
    required ReportReason reason,
    String? description,
  }) : targetId = targetId.trim(),
       targetType = targetType,
       reason = reason,
       description = _normalizeGeneratedOptionalText(description) {
    if (this.targetId.isEmpty) {
      throw ArgumentError.value(this.targetId, "targetId", 'must not be blank');
    }
  }

  final String targetId;
  final ReportTargetType targetType;
  final ReportReason reason;
  final String? description;

  factory CreateContentReportCommand.fromWire(
    Map<String, Object?> map, [
    String path = "CreateContentReportCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "targetId",
      "targetType",
      "reason",
      "description",
    }, path);
    return CreateContentReportCommand(
      targetId: _generatedRequestString(map["targetId"], '$path.targetId'),
      targetType: switch (map["targetType"]) {
        "post" => ReportTargetType.post,
        "comment" => ReportTargetType.comment,
        "user" => ReportTargetType.user,
        "circle" => ReportTargetType.circle,
        "gathering" => ReportTargetType.gathering,
        "message" => ReportTargetType.message,
        _ => throw FormatException(
          '$path.targetType' + ' has an invalid enum value',
        ),
      },
      reason: switch (map["reason"]) {
        "spam" => ReportReason.spam,
        "harassment" => ReportReason.harassment,
        "violence" => ReportReason.violence,
        "adult" => ReportReason.adult,
        "copyright" => ReportReason.copyright,
        "other" => ReportReason.other,
        _ => throw FormatException(
          '$path.reason' + ' has an invalid enum value',
        ),
      },
      description: map["description"] == null
          ? null
          : _generatedRequestString(map["description"], '$path.description'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "targetId": this.targetId,
    "targetType": this.targetType.wireName,
    "reason": this.reason.wireName,
    if (this.description != null) "description": this.description!,
  };
}

final class DeleteContentCommentCommand {
  DeleteContentCommentCommand({
    required String postId,
    required String commentId,
  }) : postId = postId.trim(),
       commentId = commentId.trim() {
    if (this.postId.isEmpty) {
      throw ArgumentError.value(this.postId, "postId", 'must not be blank');
    }
    if (this.commentId.isEmpty) {
      throw ArgumentError.value(
        this.commentId,
        "commentId",
        'must not be blank',
      );
    }
  }

  final String postId;
  final String commentId;

  factory DeleteContentCommentCommand.fromWire(
    Map<String, Object?> map, [
    String path = "DeleteContentCommentCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "postId",
      "commentId",
    }, path);
    return DeleteContentCommentCommand(
      postId: _generatedRequestString(map["postId"], '$path.postId'),
      commentId: _generatedRequestString(map["commentId"], '$path.commentId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "postId": this.postId,
    "commentId": this.commentId,
  };
}

final class DeletePostCommand {
  DeletePostCommand({required String postId}) : postId = postId.trim() {
    if (this.postId.isEmpty) {
      throw ArgumentError.value(this.postId, "postId", 'must not be blank');
    }
  }

  final String postId;

  factory DeletePostCommand.fromWire(
    Map<String, Object?> map, [
    String path = "DeletePostCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"postId"}, path);
    return DeletePostCommand(
      postId: _generatedRequestString(map["postId"], '$path.postId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{"postId": this.postId};
}

final class DiscardContentMediaAssetCommand {
  DiscardContentMediaAssetCommand({required String mediaId})
    : mediaId = mediaId.trim() {
    if (this.mediaId.isEmpty) {
      throw ArgumentError.value(this.mediaId, "mediaId", 'must not be blank');
    }
  }

  final String mediaId;

  factory DiscardContentMediaAssetCommand.fromWire(
    Map<String, Object?> map, [
    String path = "DiscardContentMediaAssetCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"mediaId"}, path);
    return DiscardContentMediaAssetCommand(
      mediaId: _generatedRequestString(map["mediaId"], '$path.mediaId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{"mediaId": this.mediaId};
}

final class EntityWishlistStateQuery {
  const EntityWishlistStateQuery({
    required String objectId,
    required String objectKind,
  }) : objectId = objectId,
       objectKind = objectKind;

  final String objectId;
  final String objectKind;

  factory EntityWishlistStateQuery.fromWire(
    Map<String, Object?> map, [
    String path = "EntityWishlistStateQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "objectId",
      "objectKind",
    }, path);
    return EntityWishlistStateQuery(
      objectId: _generatedRequestString(map["objectId"], '$path.objectId'),
      objectKind: _generatedRequestString(
        map["objectKind"],
        '$path.objectKind',
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "objectId": this.objectId,
    "objectKind": this.objectKind,
  };
}

final class FilterCatalogQuery {
  const FilterCatalogQuery();
}

final class GetAppConfigQuery {
  const GetAppConfigQuery();
}

final class GetAuthorImpactQuery {
  static const int defaultLimit = 12;
  static const int maximumLimit = 50;

  GetAuthorImpactQuery({required String personaId, int limit = 12})
    : personaId = personaId,
      limit = limit {
    if (this.limit <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit > 50) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 50");
    }
  }

  final String personaId;
  final int limit;

  factory GetAuthorImpactQuery.fromWire(
    Map<String, Object?> map, [
    String path = "GetAuthorImpactQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "personaId",
      "limit",
    }, path);
    return GetAuthorImpactQuery(
      personaId: _generatedRequestString(map["personaId"], '$path.personaId'),
      limit: map.containsKey("limit")
          ? _generatedRequestInt(map["limit"], '$path.limit')
          : 12,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "personaId": this.personaId,
    "limit": this.limit,
  };
}

final class GetContentMediaAssetQuery {
  GetContentMediaAssetQuery({required String mediaId})
    : mediaId = mediaId.trim() {
    if (this.mediaId.isEmpty) {
      throw ArgumentError.value(this.mediaId, "mediaId", 'must not be blank');
    }
  }

  final String mediaId;

  factory GetContentMediaAssetQuery.fromWire(
    Map<String, Object?> map, [
    String path = "GetContentMediaAssetQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"mediaId"}, path);
    return GetContentMediaAssetQuery(
      mediaId: _generatedRequestString(map["mediaId"], '$path.mediaId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{"mediaId": this.mediaId};
}

final class GetContentMediaUploadSessionQuery {
  GetContentMediaUploadSessionQuery({required String sessionId})
    : sessionId = sessionId.trim() {
    if (this.sessionId.isEmpty) {
      throw ArgumentError.value(
        this.sessionId,
        "sessionId",
        'must not be blank',
      );
    }
  }

  final String sessionId;

  factory GetContentMediaUploadSessionQuery.fromWire(
    Map<String, Object?> map, [
    String path = "GetContentMediaUploadSessionQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "sessionId",
    }, path);
    return GetContentMediaUploadSessionQuery(
      sessionId: _generatedRequestString(map["sessionId"], '$path.sessionId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "sessionId": this.sessionId,
  };
}

final class GetContentPostReactionStateQuery {
  GetContentPostReactionStateQuery({required String postId})
    : postId = postId.trim() {
    if (this.postId.isEmpty) {
      throw ArgumentError.value(this.postId, "postId", 'must not be blank');
    }
  }

  final String postId;

  factory GetContentPostReactionStateQuery.fromWire(
    Map<String, Object?> map, [
    String path = "GetContentPostReactionStateQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"postId"}, path);
    return GetContentPostReactionStateQuery(
      postId: _generatedRequestString(map["postId"], '$path.postId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{"postId": this.postId};
}

final class GetGatheringSocialProofQuery {
  GetGatheringSocialProofQuery({
    required String anchorKind,
    required String objectId,
  }) : anchorKind = anchorKind.trim(),
       objectId = objectId.trim() {
    if (this.anchorKind.isEmpty) {
      throw ArgumentError.value(
        this.anchorKind,
        "anchorKind",
        'must not be blank',
      );
    }
    if (this.objectId.isEmpty) {
      throw ArgumentError.value(this.objectId, "objectId", 'must not be blank');
    }
  }

  final String anchorKind;
  final String objectId;

  factory GetGatheringSocialProofQuery.fromWire(
    Map<String, Object?> map, [
    String path = "GetGatheringSocialProofQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "anchorKind",
      "objectId",
    }, path);
    return GetGatheringSocialProofQuery(
      anchorKind: _generatedRequestString(
        map["anchorKind"],
        '$path.anchorKind',
      ),
      objectId: _generatedRequestString(map["objectId"], '$path.objectId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "anchorKind": this.anchorKind,
    "objectId": this.objectId,
  };
}

final class GetMyIntersectionSummaryQuery {
  const GetMyIntersectionSummaryQuery();
}

final class GetObjectIntersectionsQuery {
  GetObjectIntersectionsQuery({
    required String objectId,
    String? objectType,
    int limit = 8,
  }) : objectId = objectId,
       objectType = objectType,
       limit = limit {
    if (this.objectId.isEmpty) {
      throw ArgumentError.value(this.objectId, "objectId", 'must not be blank');
    }
  }

  final String objectId;
  final String? objectType;
  final int limit;

  factory GetObjectIntersectionsQuery.fromWire(
    Map<String, Object?> map, [
    String path = "GetObjectIntersectionsQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "objectId",
      "objectType",
      "limit",
    }, path);
    return GetObjectIntersectionsQuery(
      objectId: _generatedRequestString(map["objectId"], '$path.objectId'),
      objectType: map["objectType"] == null
          ? null
          : _generatedRequestString(map["objectType"], '$path.objectType'),
      limit: map.containsKey("limit")
          ? _generatedRequestInt(map["limit"], '$path.limit')
          : 8,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "objectId": this.objectId,
    if (this.objectType != null) "objectType": this.objectType!,
    "limit": this.limit,
  };
}

final class InitContentMediaUploadCommand {
  InitContentMediaUploadCommand({
    required MediaType mediaType,
    required String mimeType,
    required int fileSize,
    required String expectedSha256,
  }) : mediaType = mediaType,
       mimeType = mimeType.trim(),
       fileSize = fileSize,
       expectedSha256 = expectedSha256.trim().toLowerCase() {
    if (this.mimeType.isEmpty) {
      throw ArgumentError.value(this.mimeType, "mimeType", 'must not be blank');
    }
  }

  final MediaType mediaType;
  final String mimeType;
  final int fileSize;
  final String expectedSha256;

  factory InitContentMediaUploadCommand.fromWire(
    Map<String, Object?> map, [
    String path = "InitContentMediaUploadCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "mediaType",
      "mimeType",
      "fileSize",
      "expectedSha256",
    }, path);
    return InitContentMediaUploadCommand(
      mediaType: switch (map["mediaType"]) {
        "image" => MediaType.image,
        "video" => MediaType.video,
        "audio" => MediaType.audio,
        "file" => MediaType.file,
        _ => throw FormatException(
          '$path.mediaType' + ' has an invalid enum value',
        ),
      },
      mimeType: _generatedRequestString(map["mimeType"], '$path.mimeType'),
      fileSize: _generatedRequestInt(map["fileSize"], '$path.fileSize'),
      expectedSha256: _generatedRequestString(
        map["expectedSha256"],
        '$path.expectedSha256',
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "mediaType": this.mediaType.wireName,
    "mimeType": this.mimeType,
    "fileSize": this.fileSize,
    "expectedSha256": this.expectedSha256,
  };
}

final class LikeContentPostCommand {
  LikeContentPostCommand({required String postId}) : postId = postId.trim() {
    if (this.postId.isEmpty) {
      throw ArgumentError.value(this.postId, "postId", 'must not be blank');
    }
  }

  final String postId;

  factory LikeContentPostCommand.fromWire(
    Map<String, Object?> map, [
    String path = "LikeContentPostCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"postId"}, path);
    return LikeContentPostCommand(
      postId: _generatedRequestString(map["postId"], '$path.postId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{"postId": this.postId};
}

final class ListAuthorImpactEvidenceQuery {
  static const int defaultLimit = 20;
  static const int maximumLimit = 50;

  ListAuthorImpactEvidenceQuery({
    required String personaId,
    required String impactId,
    String? evidenceSnapshotId,
    String? cursor,
    int limit = 20,
  }) : personaId = personaId,
       impactId = impactId,
       evidenceSnapshotId = evidenceSnapshotId,
       cursor = cursor,
       limit = limit {
    if (this.limit <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit > 50) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 50");
    }
  }

  final String personaId;
  final String impactId;
  final String? evidenceSnapshotId;
  final String? cursor;
  final int limit;

  factory ListAuthorImpactEvidenceQuery.fromWire(
    Map<String, Object?> map, [
    String path = "ListAuthorImpactEvidenceQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "personaId",
      "impactId",
      "evidenceSnapshotId",
      "cursor",
      "limit",
    }, path);
    return ListAuthorImpactEvidenceQuery(
      personaId: _generatedRequestString(map["personaId"], '$path.personaId'),
      impactId: _generatedRequestString(map["impactId"], '$path.impactId'),
      evidenceSnapshotId: map["evidenceSnapshotId"] == null
          ? null
          : _generatedRequestString(
              map["evidenceSnapshotId"],
              '$path.evidenceSnapshotId',
            ),
      cursor: map["cursor"] == null
          ? null
          : _generatedRequestString(map["cursor"], '$path.cursor'),
      limit: map.containsKey("limit")
          ? _generatedRequestInt(map["limit"], '$path.limit')
          : 20,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "personaId": this.personaId,
    "impactId": this.impactId,
    if (this.evidenceSnapshotId != null)
      "evidenceSnapshotId": this.evidenceSnapshotId!,
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

final class ListContentCommentRepliesQuery {
  static const int defaultLimit = 10;
  static const int maximumLimit = 100;

  ListContentCommentRepliesQuery({
    required String postId,
    required String commentId,
    String? cursor,
    int limit = 10,
  }) : postId = postId.trim(),
       commentId = commentId.trim(),
       cursor = _normalizeGeneratedOptionalText(cursor),
       limit = limit {
    if (this.postId.isEmpty) {
      throw ArgumentError.value(this.postId, "postId", 'must not be blank');
    }
    if (this.commentId.isEmpty) {
      throw ArgumentError.value(
        this.commentId,
        "commentId",
        'must not be blank',
      );
    }
    if (this.limit <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit > 100) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 100");
    }
  }

  final String postId;
  final String commentId;
  final String? cursor;
  final int limit;

  factory ListContentCommentRepliesQuery.fromWire(
    Map<String, Object?> map, [
    String path = "ListContentCommentRepliesQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "postId",
      "commentId",
      "cursor",
      "limit",
    }, path);
    return ListContentCommentRepliesQuery(
      postId: _generatedRequestString(map["postId"], '$path.postId'),
      commentId: _generatedRequestString(map["commentId"], '$path.commentId'),
      cursor: map["cursor"] == null
          ? null
          : _generatedRequestString(map["cursor"], '$path.cursor'),
      limit: map.containsKey("limit")
          ? _generatedRequestInt(map["limit"], '$path.limit')
          : 10,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "postId": this.postId,
    "commentId": this.commentId,
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

final class ListContentCommentsQuery {
  static const int defaultLimit = 20;
  static const int maximumLimit = 100;

  ListContentCommentsQuery({
    required String postId,
    String? cursor,
    int limit = 20,
    CommentSort sort = CommentSort.hot,
  }) : postId = postId.trim(),
       cursor = _normalizeGeneratedOptionalText(cursor),
       limit = limit,
       sort = sort {
    if (this.postId.isEmpty) {
      throw ArgumentError.value(this.postId, "postId", 'must not be blank');
    }
    if (this.limit <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit > 100) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 100");
    }
  }

  final String postId;
  final String? cursor;
  final int limit;
  final CommentSort sort;

  factory ListContentCommentsQuery.fromWire(
    Map<String, Object?> map, [
    String path = "ListContentCommentsQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "postId",
      "cursor",
      "limit",
      "sort",
    }, path);
    return ListContentCommentsQuery(
      postId: _generatedRequestString(map["postId"], '$path.postId'),
      cursor: map["cursor"] == null
          ? null
          : _generatedRequestString(map["cursor"], '$path.cursor'),
      limit: map.containsKey("limit")
          ? _generatedRequestInt(map["limit"], '$path.limit')
          : 20,
      sort: map.containsKey("sort")
          ? switch (map["sort"]) {
              "hot" => CommentSort.hot,
              "latest" => CommentSort.latest,
              _ => throw FormatException(
                '$path.sort' + ' has an invalid enum value',
              ),
            }
          : CommentSort.hot,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "postId": this.postId,
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
    "sort": this.sort.wireName,
  };
}

final class ListMyIntersectionsQuery {
  static const int defaultLimit = 50;
  static const int maximumLimit = 100;

  ListMyIntersectionsQuery({
    String? dimension,
    String? filter,
    String? sourceRef,
    String? timeBucket,
    String? cursor,
    int limit = 50,
  }) : dimension = dimension,
       filter = filter,
       sourceRef = sourceRef,
       timeBucket = timeBucket,
       cursor = cursor,
       limit = limit {
    if (this.limit <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit > 100) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 100");
    }
  }

  final String? dimension;
  final String? filter;
  final String? sourceRef;
  final String? timeBucket;
  final String? cursor;
  final int limit;

  factory ListMyIntersectionsQuery.fromWire(
    Map<String, Object?> map, [
    String path = "ListMyIntersectionsQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "dimension",
      "filter",
      "sourceRef",
      "timeBucket",
      "cursor",
      "limit",
    }, path);
    return ListMyIntersectionsQuery(
      dimension: map["dimension"] == null
          ? null
          : _generatedRequestString(map["dimension"], '$path.dimension'),
      filter: map["filter"] == null
          ? null
          : _generatedRequestString(map["filter"], '$path.filter'),
      sourceRef: map["sourceRef"] == null
          ? null
          : _generatedRequestString(map["sourceRef"], '$path.sourceRef'),
      timeBucket: map["timeBucket"] == null
          ? null
          : _generatedRequestString(map["timeBucket"], '$path.timeBucket'),
      cursor: map["cursor"] == null
          ? null
          : _generatedRequestString(map["cursor"], '$path.cursor'),
      limit: map.containsKey("limit")
          ? _generatedRequestInt(map["limit"], '$path.limit')
          : 50,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (this.dimension != null) "dimension": this.dimension!,
    if (this.filter != null) "filter": this.filter!,
    if (this.sourceRef != null) "sourceRef": this.sourceRef!,
    if (this.timeBucket != null) "timeBucket": this.timeBucket!,
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

final class MarkIntersectionsVisitedRequest {
  const MarkIntersectionsVisitedRequest({IntersectionDimension? dimension})
    : dimension = dimension;

  final IntersectionDimension? dimension;

  factory MarkIntersectionsVisitedRequest.fromWire(
    Map<String, Object?> map, [
    String path = "MarkIntersectionsVisitedRequest",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "dimension",
    }, path);
    return MarkIntersectionsVisitedRequest(
      dimension: map["dimension"] == null
          ? null
          : switch (map["dimension"]) {
              "identity" => IntersectionDimension.identity,
              "location" => IntersectionDimension.location,
              "content" => IntersectionDimension.content,
              "interest" => IntersectionDimension.interest,
              "relationship" => IntersectionDimension.relationship,
              _ => throw FormatException(
                '$path.dimension' + ' has an invalid enum value',
              ),
            },
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (this.dimension != null) "dimension": this.dimension!.wireName,
  };
}

final class MediaCaptureMetadata {
  MediaCaptureMetadata({
    String? cameraMake,
    String? cameraModel,
    String? lensModel,
    double? focalLengthMm,
    double? apertureFNumber,
    double? shutterSpeedSeconds,
    int? isoSensitivity,
    DateTime? capturedAt,
    double? gpsLatitude,
    double? gpsLongitude,
  }) : cameraMake = cameraMake,
       cameraModel = cameraModel,
       lensModel = lensModel,
       focalLengthMm = focalLengthMm,
       apertureFNumber = apertureFNumber,
       shutterSpeedSeconds = shutterSpeedSeconds,
       isoSensitivity = isoSensitivity,
       capturedAt = capturedAt,
       gpsLatitude = gpsLatitude,
       gpsLongitude = gpsLongitude {
    if (this.cameraMake != null && this.cameraMake!.length > 128) {
      throw ArgumentError.value(
        this.cameraMake,
        "cameraMake",
        "length exceeds 128",
      );
    }
    if (this.cameraModel != null && this.cameraModel!.length > 128) {
      throw ArgumentError.value(
        this.cameraModel,
        "cameraModel",
        "length exceeds 128",
      );
    }
    if (this.lensModel != null && this.lensModel!.length > 192) {
      throw ArgumentError.value(
        this.lensModel,
        "lensModel",
        "length exceeds 192",
      );
    }
    if (this.focalLengthMm != null && this.focalLengthMm! <= 0) {
      throw ArgumentError.value(
        this.focalLengthMm,
        "focalLengthMm",
        "must be positive",
      );
    }
    if (this.apertureFNumber != null && this.apertureFNumber! <= 0) {
      throw ArgumentError.value(
        this.apertureFNumber,
        "apertureFNumber",
        "must be positive",
      );
    }
    if (this.shutterSpeedSeconds != null && this.shutterSpeedSeconds! <= 0) {
      throw ArgumentError.value(
        this.shutterSpeedSeconds,
        "shutterSpeedSeconds",
        "must be positive",
      );
    }
    if (this.isoSensitivity != null && this.isoSensitivity! <= 0) {
      throw ArgumentError.value(
        this.isoSensitivity,
        "isoSensitivity",
        "must be positive",
      );
    }
  }

  final String? cameraMake;
  final String? cameraModel;
  final String? lensModel;
  final double? focalLengthMm;
  final double? apertureFNumber;
  final double? shutterSpeedSeconds;
  final int? isoSensitivity;
  final DateTime? capturedAt;
  final double? gpsLatitude;
  final double? gpsLongitude;

  factory MediaCaptureMetadata.fromWire(
    Map<String, Object?> map, [
    String path = "MediaCaptureMetadata",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "cameraMake",
      "cameraModel",
      "lensModel",
      "focalLengthMm",
      "apertureFNumber",
      "shutterSpeedSeconds",
      "isoSensitivity",
      "capturedAt",
      "gpsLatitude",
      "gpsLongitude",
    }, path);
    return MediaCaptureMetadata(
      cameraMake: map["cameraMake"] == null
          ? null
          : _generatedRequestString(map["cameraMake"], '$path.cameraMake'),
      cameraModel: map["cameraModel"] == null
          ? null
          : _generatedRequestString(map["cameraModel"], '$path.cameraModel'),
      lensModel: map["lensModel"] == null
          ? null
          : _generatedRequestString(map["lensModel"], '$path.lensModel'),
      focalLengthMm: map["focalLengthMm"] == null
          ? null
          : _generatedRequestDouble(
              map["focalLengthMm"],
              '$path.focalLengthMm',
            ),
      apertureFNumber: map["apertureFNumber"] == null
          ? null
          : _generatedRequestDouble(
              map["apertureFNumber"],
              '$path.apertureFNumber',
            ),
      shutterSpeedSeconds: map["shutterSpeedSeconds"] == null
          ? null
          : _generatedRequestDouble(
              map["shutterSpeedSeconds"],
              '$path.shutterSpeedSeconds',
            ),
      isoSensitivity: map["isoSensitivity"] == null
          ? null
          : _generatedRequestInt(map["isoSensitivity"], '$path.isoSensitivity'),
      capturedAt: map["capturedAt"] == null
          ? null
          : _generatedRequestTimestamp(map["capturedAt"], '$path.capturedAt'),
      gpsLatitude: map["gpsLatitude"] == null
          ? null
          : _generatedRequestDouble(map["gpsLatitude"], '$path.gpsLatitude'),
      gpsLongitude: map["gpsLongitude"] == null
          ? null
          : _generatedRequestDouble(map["gpsLongitude"], '$path.gpsLongitude'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (this.cameraMake != null) "cameraMake": this.cameraMake!,
    if (this.cameraModel != null) "cameraModel": this.cameraModel!,
    if (this.lensModel != null) "lensModel": this.lensModel!,
    if (this.focalLengthMm != null) "focalLengthMm": this.focalLengthMm!,
    if (this.apertureFNumber != null) "apertureFNumber": this.apertureFNumber!,
    if (this.shutterSpeedSeconds != null)
      "shutterSpeedSeconds": this.shutterSpeedSeconds!,
    if (this.isoSensitivity != null) "isoSensitivity": this.isoSensitivity!,
    if (this.capturedAt != null)
      "capturedAt": this.capturedAt!.toUtc().toIso8601String(),
    if (this.gpsLatitude != null) "gpsLatitude": this.gpsLatitude!,
    if (this.gpsLongitude != null) "gpsLongitude": this.gpsLongitude!,
  };
}

final class PostArticleAssetInput {
  const PostArticleAssetInput({
    required String assetId,
    String? role,
    String? layout,
    String? caption,
  }) : assetId = assetId,
       role = role,
       layout = layout,
       caption = caption;

  final String assetId;
  final String? role;
  final String? layout;
  final String? caption;

  factory PostArticleAssetInput.fromWire(
    Map<String, Object?> map, [
    String path = "PostArticleAssetInput",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "assetId",
      "role",
      "layout",
      "caption",
    }, path);
    return PostArticleAssetInput(
      assetId: _generatedRequestString(map["assetId"], '$path.assetId'),
      role: map["role"] == null
          ? null
          : _generatedRequestString(map["role"], '$path.role'),
      layout: map["layout"] == null
          ? null
          : _generatedRequestString(map["layout"], '$path.layout'),
      caption: map["caption"] == null
          ? null
          : _generatedRequestString(map["caption"], '$path.caption'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "assetId": this.assetId,
    if (this.role != null) "role": this.role!,
    if (this.layout != null) "layout": this.layout!,
    if (this.caption != null) "caption": this.caption!,
  };
}

final class PostArticleAssetManifestInput {
  PostArticleAssetManifestInput({
    required String schema,
    String? markdownVersion,
    required List<PostArticleAssetInput> assets,
  }) : schema = schema,
       markdownVersion = markdownVersion,
       assets = List.unmodifiable(assets) {}

  final String schema;
  final String? markdownVersion;
  final List<PostArticleAssetInput> assets;

  factory PostArticleAssetManifestInput.fromWire(
    Map<String, Object?> map, [
    String path = "PostArticleAssetManifestInput",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "schema",
      "markdownVersion",
      "assets",
    }, path);
    return PostArticleAssetManifestInput(
      schema: _generatedRequestString(map["schema"], '$path.schema'),
      markdownVersion: map["markdownVersion"] == null
          ? null
          : _generatedRequestString(
              map["markdownVersion"],
              '$path.markdownVersion',
            ),
      assets: List<PostArticleAssetInput>.unmodifiable(
        _generatedRequestList(
          map["assets"],
          '$path.assets',
        ).asMap().entries.map(
          (entry) => PostArticleAssetInput.fromWire(
            _generatedRequestObject(
              entry.value,
              '$path.assets' + '[${entry.key}]',
            ),
            '$path.assets' + '[${entry.key}]',
          ),
        ),
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "schema": this.schema,
    if (this.markdownVersion != null) "markdownVersion": this.markdownVersion!,
    "assets": this.assets
        .map((value) => value.toWire())
        .toList(growable: false),
  };
}

final class PostDeviceInfo {
  const PostDeviceInfo({
    String? manufacturer,
    String? brand,
    String? model,
    String? os,
    String? appVersion,
    int? width,
    int? height,
    int? durationMs,
  }) : manufacturer = manufacturer,
       brand = brand,
       model = model,
       os = os,
       appVersion = appVersion,
       width = width,
       height = height,
       durationMs = durationMs;

  final String? manufacturer;
  final String? brand;
  final String? model;
  final String? os;
  final String? appVersion;
  final int? width;
  final int? height;
  final int? durationMs;

  factory PostDeviceInfo.fromWire(
    Map<String, Object?> map, [
    String path = "PostDeviceInfo",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "manufacturer",
      "brand",
      "model",
      "os",
      "appVersion",
      "width",
      "height",
      "durationMs",
    }, path);
    return PostDeviceInfo(
      manufacturer: map["manufacturer"] == null
          ? null
          : _generatedRequestString(map["manufacturer"], '$path.manufacturer'),
      brand: map["brand"] == null
          ? null
          : _generatedRequestString(map["brand"], '$path.brand'),
      model: map["model"] == null
          ? null
          : _generatedRequestString(map["model"], '$path.model'),
      os: map["os"] == null
          ? null
          : _generatedRequestString(map["os"], '$path.os'),
      appVersion: map["appVersion"] == null
          ? null
          : _generatedRequestString(map["appVersion"], '$path.appVersion'),
      width: map["width"] == null
          ? null
          : _generatedRequestInt(map["width"], '$path.width'),
      height: map["height"] == null
          ? null
          : _generatedRequestInt(map["height"], '$path.height'),
      durationMs: map["durationMs"] == null
          ? null
          : _generatedRequestInt(map["durationMs"], '$path.durationMs'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (this.manufacturer != null) "manufacturer": this.manufacturer!,
    if (this.brand != null) "brand": this.brand!,
    if (this.model != null) "model": this.model!,
    if (this.os != null) "os": this.os!,
    if (this.appVersion != null) "appVersion": this.appVersion!,
    if (this.width != null) "width": this.width!,
    if (this.height != null) "height": this.height!,
    if (this.durationMs != null) "durationMs": this.durationMs!,
  };
}

final class PostPublishLocation {
  const PostPublishLocation({String? country, String? province, String? city})
    : country = country,
      province = province,
      city = city;

  final String? country;
  final String? province;
  final String? city;

  factory PostPublishLocation.fromWire(
    Map<String, Object?> map, [
    String path = "PostPublishLocation",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "country",
      "province",
      "city",
    }, path);
    return PostPublishLocation(
      country: map["country"] == null
          ? null
          : _generatedRequestString(map["country"], '$path.country'),
      province: map["province"] == null
          ? null
          : _generatedRequestString(map["province"], '$path.province'),
      city: map["city"] == null
          ? null
          : _generatedRequestString(map["city"], '$path.city'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (this.country != null) "country": this.country!,
    if (this.province != null) "province": this.province!,
    if (this.city != null) "city": this.city!,
  };
}

final class ReactToContentCommentCommand {
  ReactToContentCommentCommand({
    required String commentId,
    required CommentReactionType reaction,
  }) : commentId = commentId.trim(),
       reaction = reaction {
    if (this.commentId.isEmpty) {
      throw ArgumentError.value(
        this.commentId,
        "commentId",
        'must not be blank',
      );
    }
  }

  final String commentId;
  final CommentReactionType reaction;

  factory ReactToContentCommentCommand.fromWire(
    Map<String, Object?> map, [
    String path = "ReactToContentCommentCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "commentId",
      "reaction",
    }, path);
    return ReactToContentCommentCommand(
      commentId: _generatedRequestString(map["commentId"], '$path.commentId'),
      reaction: switch (map["reaction"]) {
        "none" => CommentReactionType.none,
        "like" => CommentReactionType.like,
        "dislike" => CommentReactionType.dislike,
        _ => throw FormatException(
          '$path.reaction' + ' has an invalid enum value',
        ),
      },
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "commentId": this.commentId,
    "reaction": this.reaction.wireName,
  };
}

final class ReportContentBehaviorsCommand {
  ReportContentBehaviorsCommand({
    required List<ContentBehaviorEventWire> events,
  }) : events = List.unmodifiable(events) {
    if (this.events.length < 1) {
      throw ArgumentError.value(this.events, "events", "item count is below 1");
    }
  }

  final List<ContentBehaviorEventWire> events;

  factory ReportContentBehaviorsCommand.fromWire(
    Map<String, Object?> map, [
    String path = "ReportContentBehaviorsCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"events"}, path);
    return ReportContentBehaviorsCommand(
      events: List<ContentBehaviorEventWire>.unmodifiable(
        _generatedRequestList(
          map["events"],
          '$path.events',
        ).asMap().entries.map(
          (entry) => ContentBehaviorEventWire.fromWire(
            _generatedRequestObject(
              entry.value,
              '$path.events' + '[${entry.key}]',
            ),
            '$path.events' + '[${entry.key}]',
          ),
        ),
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "events": this.events
        .map((value) => value.toWire())
        .toList(growable: false),
  };
}

final class RequestContentMediaOriginalAccessCommand {
  RequestContentMediaOriginalAccessCommand({
    required String mediaId,
    MediaOriginalAccessPurpose purpose = MediaOriginalAccessPurpose.view,
  }) : mediaId = mediaId.trim(),
       purpose = purpose {
    if (this.mediaId.isEmpty) {
      throw ArgumentError.value(this.mediaId, "mediaId", 'must not be blank');
    }
  }

  final String mediaId;
  final MediaOriginalAccessPurpose purpose;

  factory RequestContentMediaOriginalAccessCommand.fromWire(
    Map<String, Object?> map, [
    String path = "RequestContentMediaOriginalAccessCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "mediaId",
      "purpose",
    }, path);
    return RequestContentMediaOriginalAccessCommand(
      mediaId: _generatedRequestString(map["mediaId"], '$path.mediaId'),
      purpose: map.containsKey("purpose")
          ? switch (map["purpose"]) {
              "view" => MediaOriginalAccessPurpose.view,
              "save" => MediaOriginalAccessPurpose.save,
              _ => throw FormatException(
                '$path.purpose' + ' has an invalid enum value',
              ),
            }
          : MediaOriginalAccessPurpose.view,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "mediaId": this.mediaId,
    "purpose": this.purpose.wireName,
  };
}

final class ResearchReleaseReadbackQuery {
  ResearchReleaseReadbackQuery({required String researchIdentityAttestation})
    : researchIdentityAttestation = researchIdentityAttestation {
    if (this.researchIdentityAttestation.isEmpty) {
      throw ArgumentError.value(
        this.researchIdentityAttestation,
        "researchIdentityAttestation",
        'must not be blank',
      );
    }
  }

  final String researchIdentityAttestation;

  factory ResearchReleaseReadbackQuery.fromWire(
    Map<String, Object?> map, [
    String path = "ResearchReleaseReadbackQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "X-Research-Identity-Attestation",
    }, path);
    return ResearchReleaseReadbackQuery(
      researchIdentityAttestation: _generatedRequestString(
        map["X-Research-Identity-Attestation"],
        '$path.X-Research-Identity-Attestation',
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "X-Research-Identity-Attestation": this.researchIdentityAttestation,
  };
}

final class SelectAutoContentMediaCoverCommand {
  SelectAutoContentMediaCoverCommand({required String mediaId})
    : mediaId = mediaId.trim() {
    if (this.mediaId.isEmpty) {
      throw ArgumentError.value(this.mediaId, "mediaId", 'must not be blank');
    }
  }

  final String mediaId;

  factory SelectAutoContentMediaCoverCommand.fromWire(
    Map<String, Object?> map, [
    String path = "SelectAutoContentMediaCoverCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"mediaId"}, path);
    return SelectAutoContentMediaCoverCommand(
      mediaId: _generatedRequestString(map["mediaId"], '$path.mediaId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{"mediaId": this.mediaId};
}

final class SelectManualContentMediaCoverCommand {
  SelectManualContentMediaCoverCommand({
    required String mediaId,
    String? coverAssetId,
    int coverFrameTimeMs = 0,
  }) : mediaId = mediaId.trim(),
       coverAssetId = _normalizeGeneratedOptionalText(coverAssetId),
       coverFrameTimeMs = coverFrameTimeMs {
    if (this.mediaId.isEmpty) {
      throw ArgumentError.value(this.mediaId, "mediaId", 'must not be blank');
    }
  }

  final String mediaId;
  final String? coverAssetId;
  final int coverFrameTimeMs;

  factory SelectManualContentMediaCoverCommand.fromWire(
    Map<String, Object?> map, [
    String path = "SelectManualContentMediaCoverCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "mediaId",
      "coverAssetId",
      "coverFrameTimeMs",
    }, path);
    return SelectManualContentMediaCoverCommand(
      mediaId: _generatedRequestString(map["mediaId"], '$path.mediaId'),
      coverAssetId: map["coverAssetId"] == null
          ? null
          : _generatedRequestString(map["coverAssetId"], '$path.coverAssetId'),
      coverFrameTimeMs: map.containsKey("coverFrameTimeMs")
          ? _generatedRequestInt(
              map["coverFrameTimeMs"],
              '$path.coverFrameTimeMs',
            )
          : 0,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "mediaId": this.mediaId,
    if (this.coverAssetId != null) "coverAssetId": this.coverAssetId!,
    "coverFrameTimeMs": this.coverFrameTimeMs,
  };
}

final class SubmitContentPostPublicationCommand {
  SubmitContentPostPublicationCommand({
    required String publishIntentId,
    required String localDraftId,
    required ContentType contentType,
    ContentIdentity? contentIdentity,
    String? title,
    String? body,
    String? summary,
    Iterable<PostSemanticMention> semanticMentions = const [],
    Iterable<String> mediaAssetIds = const [],
    String? articleMarkdown,
    String? markdownDialect,
    PostArticleAssetManifestInput? articleAssetManifest,
    PostArticleRenderProfile? articleRenderProfile,
    String? coverStrategy,
    int? coverFrameTimeMs,
    String? illustrationAssetId,
    GeoPoint? location,
    String? locationName,
    String? geoTagRef,
    DateTime? visitedAt,
    Iterable<CaptureDisclosureGroup> captureDisclosure =
        const <CaptureDisclosureGroup>[],
    String? primaryHomepageId,
    String? primaryHomepageType,
    PostHomepageSnapshot? primaryHomepageSnapshot,
    String? gatheringRef,
    Visibility? visibility,
    AssistantUsePolicy? assistantUsePolicy,
    String? sourcePostId,
    PostSourceType? sourceType,
    PostDeviceInfo? deviceInfo,
    PostPublishLocation? publishLocation,
    String? authorDisplayNameSnapshot,
    String? authorAvatarUrlSnapshot,
    int? personaContextVersion,
  }) : publishIntentId = publishIntentId.trim(),
       localDraftId = localDraftId.trim(),
       contentType = contentType,
       contentIdentity = contentIdentity,
       title = title,
       body = body,
       summary = summary,
       semanticMentions = List.unmodifiable(semanticMentions),
       mediaAssetIds = _normalizeGeneratedTextList(
         mediaAssetIds,
         deduplicate: false,
       ),
       articleMarkdown = articleMarkdown,
       markdownDialect = markdownDialect,
       articleAssetManifest = articleAssetManifest,
       articleRenderProfile = articleRenderProfile,
       coverStrategy = coverStrategy,
       coverFrameTimeMs = coverFrameTimeMs,
       illustrationAssetId = illustrationAssetId,
       location = location,
       locationName = locationName,
       geoTagRef = geoTagRef,
       visitedAt = visitedAt,
       captureDisclosure = List.unmodifiable(captureDisclosure),
       primaryHomepageId = primaryHomepageId,
       primaryHomepageType = primaryHomepageType,
       primaryHomepageSnapshot = primaryHomepageSnapshot,
       gatheringRef = gatheringRef,
       visibility = visibility,
       assistantUsePolicy = assistantUsePolicy,
       sourcePostId = sourcePostId,
       sourceType = sourceType,
       deviceInfo = deviceInfo,
       publishLocation = publishLocation,
       authorDisplayNameSnapshot = authorDisplayNameSnapshot,
       authorAvatarUrlSnapshot = authorAvatarUrlSnapshot,
       personaContextVersion = personaContextVersion {
    if (this.publishIntentId.isEmpty) {
      throw ArgumentError.value(
        this.publishIntentId,
        "publishIntentId",
        'must not be blank',
      );
    }
    if (this.localDraftId.isEmpty) {
      throw ArgumentError.value(
        this.localDraftId,
        "localDraftId",
        'must not be blank',
      );
    }
  }

  final String publishIntentId;
  final String localDraftId;
  final ContentType contentType;
  final ContentIdentity? contentIdentity;
  final String? title;
  final String? body;
  final String? summary;
  final List<PostSemanticMention> semanticMentions;
  final List<String> mediaAssetIds;
  final String? articleMarkdown;
  final String? markdownDialect;
  final PostArticleAssetManifestInput? articleAssetManifest;
  final PostArticleRenderProfile? articleRenderProfile;
  final String? coverStrategy;
  final int? coverFrameTimeMs;
  final String? illustrationAssetId;
  final GeoPoint? location;
  final String? locationName;
  final String? geoTagRef;
  final DateTime? visitedAt;
  final List<CaptureDisclosureGroup> captureDisclosure;
  final String? primaryHomepageId;
  final String? primaryHomepageType;
  final PostHomepageSnapshot? primaryHomepageSnapshot;
  final String? gatheringRef;
  final Visibility? visibility;
  final AssistantUsePolicy? assistantUsePolicy;
  final String? sourcePostId;
  final PostSourceType? sourceType;
  final PostDeviceInfo? deviceInfo;
  final PostPublishLocation? publishLocation;
  final String? authorDisplayNameSnapshot;
  final String? authorAvatarUrlSnapshot;
  final int? personaContextVersion;

  factory SubmitContentPostPublicationCommand.fromWire(
    Map<String, Object?> map, [
    String path = "SubmitContentPostPublicationCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "publishIntentId",
      "localDraftId",
      "contentType",
      "contentIdentity",
      "title",
      "body",
      "summary",
      "semanticMentions",
      "mediaAssetIds",
      "articleMarkdown",
      "markdownDialect",
      "articleAssetManifest",
      "articleRenderProfile",
      "coverStrategy",
      "coverFrameTimeMs",
      "illustrationAssetId",
      "location",
      "locationName",
      "geoTagRef",
      "visitedAt",
      "captureDisclosure",
      "primaryHomepageId",
      "primaryHomepageType",
      "primaryHomepageSnapshot",
      "gatheringRef",
      "visibility",
      "assistantUsePolicy",
      "sourcePostId",
      "sourceType",
      "deviceInfo",
      "publishLocation",
      "authorDisplayNameSnapshot",
      "authorAvatarUrlSnapshot",
      "personaContextVersion",
    }, path);
    return SubmitContentPostPublicationCommand(
      publishIntentId: _generatedRequestString(
        map["publishIntentId"],
        '$path.publishIntentId',
      ),
      localDraftId: _generatedRequestString(
        map["localDraftId"],
        '$path.localDraftId',
      ),
      contentType: switch (map["contentType"]) {
        "image" => ContentType.image,
        "video" => ContentType.video,
        "micro" => ContentType.micro,
        "article" => ContentType.article,
        _ => throw FormatException(
          '$path.contentType' + ' has an invalid enum value',
        ),
      },
      contentIdentity: map["contentIdentity"] == null
          ? null
          : switch (map["contentIdentity"]) {
              "moment" => ContentIdentity.moment,
              "work" => ContentIdentity.work,
              _ => throw FormatException(
                '$path.contentIdentity' + ' has an invalid enum value',
              ),
            },
      title: map["title"] == null
          ? null
          : _generatedRequestString(map["title"], '$path.title'),
      body: map["body"] == null
          ? null
          : _generatedRequestString(map["body"], '$path.body'),
      summary: map["summary"] == null
          ? null
          : _generatedRequestString(map["summary"], '$path.summary'),
      semanticMentions: map.containsKey("semanticMentions")
          ? List<PostSemanticMention>.unmodifiable(
              _generatedRequestList(
                map["semanticMentions"],
                '$path.semanticMentions',
              ).asMap().entries.map(
                (entry) => PostSemanticMention.fromWire(
                  _generatedRequestObject(
                    entry.value,
                    '$path.semanticMentions' + '[${entry.key}]',
                  ),
                  '$path.semanticMentions' + '[${entry.key}]',
                ),
              ),
            )
          : const [],
      mediaAssetIds: map.containsKey("mediaAssetIds")
          ? List<String>.unmodifiable(
              _generatedRequestList(
                map["mediaAssetIds"],
                '$path.mediaAssetIds',
              ).asMap().entries.map(
                (entry) => _generatedRequestString(
                  entry.value,
                  '$path.mediaAssetIds' + '[${entry.key}]',
                ),
              ),
            )
          : const [],
      articleMarkdown: map["articleMarkdown"] == null
          ? null
          : _generatedRequestString(
              map["articleMarkdown"],
              '$path.articleMarkdown',
            ),
      markdownDialect: map["markdownDialect"] == null
          ? null
          : _generatedRequestString(
              map["markdownDialect"],
              '$path.markdownDialect',
            ),
      articleAssetManifest: map["articleAssetManifest"] == null
          ? null
          : PostArticleAssetManifestInput.fromWire(
              _generatedRequestObject(
                map["articleAssetManifest"],
                '$path.articleAssetManifest',
              ),
              '$path.articleAssetManifest',
            ),
      articleRenderProfile: map["articleRenderProfile"] == null
          ? null
          : PostArticleRenderProfile.fromWire(
              _generatedRequestObject(
                map["articleRenderProfile"],
                '$path.articleRenderProfile',
              ),
              '$path.articleRenderProfile',
            ),
      coverStrategy: map["coverStrategy"] == null
          ? null
          : _generatedRequestString(
              map["coverStrategy"],
              '$path.coverStrategy',
            ),
      coverFrameTimeMs: map["coverFrameTimeMs"] == null
          ? null
          : _generatedRequestInt(
              map["coverFrameTimeMs"],
              '$path.coverFrameTimeMs',
            ),
      illustrationAssetId: map["illustrationAssetId"] == null
          ? null
          : _generatedRequestString(
              map["illustrationAssetId"],
              '$path.illustrationAssetId',
            ),
      location: map["location"] == null
          ? null
          : GeoPoint.fromWire(
              _generatedRequestObject(map["location"], '$path.location'),
              '$path.location',
            ),
      locationName: map["locationName"] == null
          ? null
          : _generatedRequestString(map["locationName"], '$path.locationName'),
      geoTagRef: map["geoTagRef"] == null
          ? null
          : _generatedRequestString(map["geoTagRef"], '$path.geoTagRef'),
      visitedAt: map["visitedAt"] == null
          ? null
          : _generatedRequestTimestamp(map["visitedAt"], '$path.visitedAt'),
      captureDisclosure: map.containsKey("captureDisclosure")
          ? List<CaptureDisclosureGroup>.unmodifiable(
              _generatedRequestList(
                map["captureDisclosure"],
                '$path.captureDisclosure',
              ).asMap().entries.map(
                (entry) => switch (entry.value) {
                  "gear" => CaptureDisclosureGroup.gear,
                  "parameters" => CaptureDisclosureGroup.parameters,
                  "place" => CaptureDisclosureGroup.place,
                  "time" => CaptureDisclosureGroup.time,
                  _ => throw FormatException(
                    '$path.captureDisclosure' +
                        '[${entry.key}]' +
                        ' has an invalid enum value',
                  ),
                },
              ),
            )
          : const <CaptureDisclosureGroup>[],
      primaryHomepageId: map["primaryHomepageId"] == null
          ? null
          : _generatedRequestString(
              map["primaryHomepageId"],
              '$path.primaryHomepageId',
            ),
      primaryHomepageType: map["primaryHomepageType"] == null
          ? null
          : _generatedRequestString(
              map["primaryHomepageType"],
              '$path.primaryHomepageType',
            ),
      primaryHomepageSnapshot: map["primaryHomepageSnapshot"] == null
          ? null
          : PostHomepageSnapshot.fromWire(
              _generatedRequestObject(
                map["primaryHomepageSnapshot"],
                '$path.primaryHomepageSnapshot',
              ),
              '$path.primaryHomepageSnapshot',
            ),
      gatheringRef: map["gatheringRef"] == null
          ? null
          : _generatedRequestString(map["gatheringRef"], '$path.gatheringRef'),
      visibility: map["visibility"] == null
          ? null
          : switch (map["visibility"]) {
              "public" => Visibility.public,
              "private" => Visibility.private,
              _ => throw FormatException(
                '$path.visibility' + ' has an invalid enum value',
              ),
            },
      assistantUsePolicy: map["assistantUsePolicy"] == null
          ? null
          : switch (map["assistantUsePolicy"]) {
              "inherit" => AssistantUsePolicy.inherit,
              "exclude" => AssistantUsePolicy.exclude,
              _ => throw FormatException(
                '$path.assistantUsePolicy' + ' has an invalid enum value',
              ),
            },
      sourcePostId: map["sourcePostId"] == null
          ? null
          : _generatedRequestString(map["sourcePostId"], '$path.sourcePostId'),
      sourceType: map["sourceType"] == null
          ? null
          : switch (map["sourceType"]) {
              "original" => PostSourceType.original,
              "repost" => PostSourceType.repost,
              "quote" => PostSourceType.quote,
              _ => throw FormatException(
                '$path.sourceType' + ' has an invalid enum value',
              ),
            },
      deviceInfo: map["deviceInfo"] == null
          ? null
          : PostDeviceInfo.fromWire(
              _generatedRequestObject(map["deviceInfo"], '$path.deviceInfo'),
              '$path.deviceInfo',
            ),
      publishLocation: map["publishLocation"] == null
          ? null
          : PostPublishLocation.fromWire(
              _generatedRequestObject(
                map["publishLocation"],
                '$path.publishLocation',
              ),
              '$path.publishLocation',
            ),
      authorDisplayNameSnapshot: map["authorDisplayNameSnapshot"] == null
          ? null
          : _generatedRequestString(
              map["authorDisplayNameSnapshot"],
              '$path.authorDisplayNameSnapshot',
            ),
      authorAvatarUrlSnapshot: map["authorAvatarUrlSnapshot"] == null
          ? null
          : _generatedRequestString(
              map["authorAvatarUrlSnapshot"],
              '$path.authorAvatarUrlSnapshot',
            ),
      personaContextVersion: map["personaContextVersion"] == null
          ? null
          : _generatedRequestInt(
              map["personaContextVersion"],
              '$path.personaContextVersion',
            ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "publishIntentId": this.publishIntentId,
    "localDraftId": this.localDraftId,
    "contentType": this.contentType.wireName,
    if (this.contentIdentity != null)
      "contentIdentity": this.contentIdentity!.wireName,
    if (this.title != null) "title": this.title!,
    if (this.body != null) "body": this.body!,
    if (this.summary != null) "summary": this.summary!,
    if (this.semanticMentions.isNotEmpty)
      "semanticMentions": this.semanticMentions
          .map((value) => value.toWire())
          .toList(growable: false),
    if (this.mediaAssetIds.isNotEmpty)
      "mediaAssetIds": this.mediaAssetIds
          .map((value) => value)
          .toList(growable: false),
    if (this.articleMarkdown != null) "articleMarkdown": this.articleMarkdown!,
    if (this.markdownDialect != null) "markdownDialect": this.markdownDialect!,
    if (this.articleAssetManifest != null)
      "articleAssetManifest": this.articleAssetManifest!.toWire(),
    if (this.articleRenderProfile != null)
      "articleRenderProfile": this.articleRenderProfile!.toWire(),
    if (this.coverStrategy != null) "coverStrategy": this.coverStrategy!,
    if (this.coverFrameTimeMs != null)
      "coverFrameTimeMs": this.coverFrameTimeMs!,
    if (this.illustrationAssetId != null)
      "illustrationAssetId": this.illustrationAssetId!,
    if (this.location != null) "location": this.location!.toWire(),
    if (this.locationName != null) "locationName": this.locationName!,
    if (this.geoTagRef != null) "geoTagRef": this.geoTagRef!,
    if (this.visitedAt != null)
      "visitedAt": this.visitedAt!.toUtc().toIso8601String(),
    "captureDisclosure": this.captureDisclosure
        .map((value) => value.wireName)
        .toList(growable: false),
    if (this.primaryHomepageId != null)
      "primaryHomepageId": this.primaryHomepageId!,
    if (this.primaryHomepageType != null)
      "primaryHomepageType": this.primaryHomepageType!,
    if (this.primaryHomepageSnapshot != null)
      "primaryHomepageSnapshot": this.primaryHomepageSnapshot!.toWire(),
    if (this.gatheringRef != null) "gatheringRef": this.gatheringRef!,
    if (this.visibility != null) "visibility": this.visibility!.wireName,
    if (this.assistantUsePolicy != null)
      "assistantUsePolicy": this.assistantUsePolicy!.wireName,
    if (this.sourcePostId != null) "sourcePostId": this.sourcePostId!,
    if (this.sourceType != null) "sourceType": this.sourceType!.wireName,
    if (this.deviceInfo != null) "deviceInfo": this.deviceInfo!.toWire(),
    if (this.publishLocation != null)
      "publishLocation": this.publishLocation!.toWire(),
    if (this.authorDisplayNameSnapshot != null)
      "authorDisplayNameSnapshot": this.authorDisplayNameSnapshot!,
    if (this.authorAvatarUrlSnapshot != null)
      "authorAvatarUrlSnapshot": this.authorAvatarUrlSnapshot!,
    if (this.personaContextVersion != null)
      "personaContextVersion": this.personaContextVersion!,
  };
}

final class UnlikeContentPostCommand {
  UnlikeContentPostCommand({required String postId}) : postId = postId.trim() {
    if (this.postId.isEmpty) {
      throw ArgumentError.value(this.postId, "postId", 'must not be blank');
    }
  }

  final String postId;

  factory UnlikeContentPostCommand.fromWire(
    Map<String, Object?> map, [
    String path = "UnlikeContentPostCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"postId"}, path);
    return UnlikeContentPostCommand(
      postId: _generatedRequestString(map["postId"], '$path.postId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{"postId": this.postId};
}

CloudOperationRequestPayload
encodeContentCommentBindMediaAssetsToCommentGeneratedRequest(
  BindContentCommentAttachmentsCommand request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"commentId": request.commentId},
    body: <String, Object?>{
      "attachmentMediaIds": request.attachmentMediaIds
          .map((value) => value)
          .toList(growable: false),
    },
  );
}

CloudOperationRequestPayload encodeContentCommentCreateCommentGeneratedRequest(
  CreateContentCommentCommand request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"postId": request.postId},
    body: <String, Object?>{
      "content": request.content,
      if (request.replyToCommentId != null)
        "replyToCommentId": request.replyToCommentId!,
      "attachmentMediaIds": request.attachmentMediaIds
          .map((value) => value)
          .toList(growable: false),
      "mentions": request.mentions
          .map((value) => value.toWire())
          .toList(growable: false),
      if (request.authorDisplayNameSnapshot != null)
        "authorDisplayNameSnapshot": request.authorDisplayNameSnapshot!,
      if (request.authorAvatarUrlSnapshot != null)
        "authorAvatarUrlSnapshot": request.authorAvatarUrlSnapshot!,
      if (request.personaContextVersion != null)
        "personaContextVersion": request.personaContextVersion!,
    },
  );
}

CloudOperationRequestPayload encodeContentCommentDeleteCommentGeneratedRequest(
  DeleteContentCommentCommand request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "postId": request.postId,
      "commentId": request.commentId,
    },
  );
}

CloudOperationRequestPayload
encodeContentCommentListCommentRepliesGeneratedRequest(
  ListContentCommentRepliesQuery request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "postId": request.postId,
      "commentId": request.commentId,
    },
    queryParameters: <String, String>{
      "limit": (request.limit).toString(),
      if (request.cursor != null) "cursor": request.cursor!,
    },
  );
}

CloudOperationRequestPayload encodeContentCommentListCommentsGeneratedRequest(
  ListContentCommentsQuery request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"postId": request.postId},
    queryParameters: <String, String>{
      "limit": (request.limit).toString(),
      if (request.cursor != null) "cursor": request.cursor!,
      "sort": (request.sort.wireName).toString(),
    },
  );
}

CloudOperationRequestPayload
encodeContentCommentListCommentsByAuthorGeneratedRequest(
  ContentCommentPageQuery request,
) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      "limit": (request.limit).toString(),
      if (request.cursor != null) "cursor": request.cursor!,
    },
  );
}

CloudOperationRequestPayload
encodeContentCommentListCommentsForPostAuthorGeneratedRequest(
  ContentCommentPageQuery request,
) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      "limit": (request.limit).toString(),
      if (request.cursor != null) "cursor": request.cursor!,
    },
  );
}

CloudOperationRequestPayload encodeContentCommentPinCommentGeneratedRequest(
  ChangeContentCommentPinCommand request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "postId": request.postId,
      "commentId": request.commentId,
    },
  );
}

CloudOperationRequestPayload encodeContentCommentUnpinCommentGeneratedRequest(
  ChangeContentCommentPinCommand request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "postId": request.postId,
      "commentId": request.commentId,
    },
  );
}

CloudOperationRequestPayload
encodeContentContentBehaviorFactReportBehaviorsGeneratedRequest(
  ReportContentBehaviorsCommand request,
) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "events": request.events
          .map((value) => value.toWire())
          .toList(growable: false),
    },
  );
}

CloudOperationRequestPayload
encodeContentContentReactionGetContentReactionStateGeneratedRequest(
  GetContentPostReactionStateQuery request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"postId": request.postId},
  );
}

CloudOperationRequestPayload
encodeContentContentReactionLikePostGeneratedRequest(
  LikeContentPostCommand request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"postId": request.postId},
  );
}

CloudOperationRequestPayload
encodeContentContentReactionReactToCommentGeneratedRequest(
  ReactToContentCommentCommand request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"commentId": request.commentId},
    body: <String, Object?>{"reaction": request.reaction.wireName},
  );
}

CloudOperationRequestPayload
encodeContentContentReactionUnlikePostGeneratedRequest(
  UnlikeContentPostCommand request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"postId": request.postId},
  );
}

CloudOperationRequestPayload
encodeContentFilterCatalogReleaseGetActiveFilterCatalogGeneratedRequest(
  FilterCatalogQuery request,
) {
  return CloudOperationRequestPayload();
}

CloudOperationRequestPayload
encodeContentIntersectionVisitStateGetMyIntersectionSummaryGeneratedRequest(
  GetMyIntersectionSummaryQuery request,
) {
  return CloudOperationRequestPayload();
}

CloudOperationRequestPayload
encodeContentIntersectionVisitStateGetObjectIntersectionsGeneratedRequest(
  GetObjectIntersectionsQuery request,
) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      "objectId": request.objectId,
      if (request.objectType != null) "objectType": request.objectType!,
      "limit": (request.limit).toString(),
    },
  );
}

CloudOperationRequestPayload
encodeContentIntersectionVisitStateListMyIntersectionsGeneratedRequest(
  ListMyIntersectionsQuery request,
) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      if (request.dimension != null) "dimension": request.dimension!,
      if (request.filter != null) "filter": request.filter!,
      if (request.sourceRef != null) "sourceRef": request.sourceRef!,
      if (request.timeBucket != null) "timeBucket": request.timeBucket!,
      if (request.cursor != null) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
    },
  );
}

CloudOperationRequestPayload
encodeContentIntersectionVisitStateMarkIntersectionsVisitedGeneratedRequest(
  MarkIntersectionsVisitedRequest request,
) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      if (request.dimension != null) "dimension": request.dimension!.wireName,
    },
  );
}

CloudOperationRequestPayload
encodeContentMediaAssetDiscardMediaAssetGeneratedRequest(
  DiscardContentMediaAssetCommand request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"mediaId": request.mediaId},
  );
}

CloudOperationRequestPayload
encodeContentMediaAssetGetMediaAssetGeneratedRequest(
  GetContentMediaAssetQuery request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"mediaId": request.mediaId},
  );
}

CloudOperationRequestPayload
encodeContentMediaAssetSelectAutoVideoCoverGeneratedRequest(
  SelectAutoContentMediaCoverCommand request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"mediaId": request.mediaId},
  );
}

CloudOperationRequestPayload
encodeContentMediaAssetSelectManualVideoCoverGeneratedRequest(
  SelectManualContentMediaCoverCommand request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"mediaId": request.mediaId},
    body: <String, Object?>{
      if (request.coverAssetId != null) "coverAssetId": request.coverAssetId!,
      "coverFrameTimeMs": request.coverFrameTimeMs,
    },
  );
}

CloudOperationRequestPayload
encodeContentMediaUploadSessionAbortMediaUploadGeneratedRequest(
  AbortContentMediaUploadCommand request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"sessionId": request.sessionId},
  );
}

CloudOperationRequestPayload
encodeContentMediaUploadSessionCompleteMediaUploadGeneratedRequest(
  CompleteContentMediaUploadCommand request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"sessionId": request.sessionId},
    body: <String, Object?>{
      "accessPolicy": request.accessPolicy.wireName,
      if (request.captureMetadata != null)
        "captureMetadata": request.captureMetadata!.toWire(),
    },
  );
}

CloudOperationRequestPayload
encodeContentMediaUploadSessionGetMediaUploadSessionGeneratedRequest(
  GetContentMediaUploadSessionQuery request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"sessionId": request.sessionId},
  );
}

CloudOperationRequestPayload
encodeContentMediaUploadSessionInitMediaUploadGeneratedRequest(
  InitContentMediaUploadCommand request,
) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "mediaType": request.mediaType.wireName,
      "mimeType": request.mimeType,
      "fileSize": request.fileSize,
      "expectedSha256": request.expectedSha256,
    },
  );
}

CloudOperationRequestPayload
encodeContentOriginalAccessQuotaReserveOriginalImageAccessGrantGeneratedRequest(
  RequestContentMediaOriginalAccessCommand request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"mediaId": request.mediaId},
    body: <String, Object?>{"purpose": request.purpose.wireName},
  );
}

CloudOperationRequestPayload
encodeContentOutboundShareFactAppendOutboundShareFactGeneratedRequest(
  CreateContentOutboundShareCommand request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"postId": request.postId},
    body: <String, Object?>{
      "channel": request.channel.wireName,
      "destinationKind": request.destinationKind.wireName,
      if (request.destination != null) "destination": request.destination!,
      "referralId": request.referralId,
      "providerReceiptId": request.providerReceiptId,
      "clientConfirmedAt": request.clientConfirmedAt.toUtc().toIso8601String(),
      "deliverySucceeded": true,
    },
  );
}

CloudOperationRequestPayload encodeContentPostDeletePostGeneratedRequest(
  DeletePostCommand request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"postId": request.postId},
  );
}

CloudOperationRequestPayload encodeContentPostGetAppConfigGeneratedRequest(
  GetAppConfigQuery request,
) {
  return CloudOperationRequestPayload();
}

CloudOperationRequestPayload encodeContentPostGetAuthorImpactGeneratedRequest(
  GetAuthorImpactQuery request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"personaId": request.personaId},
    queryParameters: <String, String>{"limit": (request.limit).toString()},
  );
}

CloudOperationRequestPayload
encodeContentPostGetEntityWishlistStateGeneratedRequest(
  EntityWishlistStateQuery request,
) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      "objectId": request.objectId,
      "objectKind": request.objectKind,
    },
  );
}

CloudOperationRequestPayload encodeContentPostGetFeedGeneratedRequest(
  ContentDiscoveryFeedQuery request,
) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      if (request.identity != null) "identity": request.identity!,
      if (request.type != null) "type": request.type!,
      if (request.sort != null) "sort": request.sort!,
      if (request.cursor != null) "cursor": request.cursor!,
      if (request.subCategory != null) "subCategory": request.subCategory!,
      if (request.channelId != null) "channelId": request.channelId!,
      if (request.sessionId != null) "sessionId": request.sessionId!,
      if (request.feedRequestId != null)
        "feedRequestId": request.feedRequestId!,
      "limit": (request.limit).toString(),
    },
    headers: <String, String>{
      if (request.blockedKeywords.isNotEmpty)
        "X-Blocked-Keywords": request.blockedKeywords
            .map(Uri.encodeQueryComponent)
            .join(','),
    },
  );
}

CloudOperationRequestPayload
encodeContentPostGetGatheringSocialProofGeneratedRequest(
  GetGatheringSocialProofQuery request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "anchorKind": request.anchorKind,
      "objectId": request.objectId,
    },
  );
}

CloudOperationRequestPayload encodeContentPostGetMyFootprintGeneratedRequest(
  ContentFootprintQuery request,
) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      if (request.type != null) "type": request.type!,
      if (request.cursor != null) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
    },
  );
}

CloudOperationRequestPayload encodeContentPostGetPostGeneratedRequest(
  ContentPostDetailQuery request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"postId": request.postId},
  );
}

CloudOperationRequestPayload
encodeContentPostGetResearchReleaseReadbackGeneratedRequest(
  ResearchReleaseReadbackQuery request,
) {
  return CloudOperationRequestPayload(
    headers: <String, String>{
      "X-Research-Identity-Attestation": request.researchIdentityAttestation,
    },
  );
}

CloudOperationRequestPayload
encodeContentPostListAuthorImpactEvidenceGeneratedRequest(
  ListAuthorImpactEvidenceQuery request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"personaId": request.personaId},
    queryParameters: <String, String>{
      "impactId": request.impactId,
      if (request.evidenceSnapshotId != null)
        "evidenceSnapshotId": request.evidenceSnapshotId!,
      if (request.cursor != null) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
    },
  );
}

CloudOperationRequestPayload
encodeContentPostListPostsByGatheringGeneratedRequest(
  ContentGatheringPostsQuery request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"gatheringId": request.gatheringId},
    queryParameters: <String, String>{
      if (request.cursor != null) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
    },
  );
}

CloudOperationRequestPayload encodeContentPostListUserPostsGeneratedRequest(
  ContentAuthorPostsQuery request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"personaId": request.personaId},
    queryParameters: <String, String>{
      if (request.identity != null) "identity": request.identity!,
      if (request.type != null) "type": request.type!,
      if (request.visibility != null) "visibility": request.visibility!,
      if (request.cursor != null) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
    },
  );
}

CloudOperationRequestPayload
encodeContentPostSubmitPostPublicationGeneratedRequest(
  SubmitContentPostPublicationCommand request,
) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "publishIntentId": request.publishIntentId,
      "localDraftId": request.localDraftId,
      "contentType": request.contentType.wireName,
      if (request.contentIdentity != null)
        "contentIdentity": request.contentIdentity!.wireName,
      if (request.title != null) "title": request.title!,
      if (request.body != null) "body": request.body!,
      if (request.summary != null) "summary": request.summary!,
      if (request.semanticMentions.isNotEmpty)
        "semanticMentions": request.semanticMentions
            .map((value) => value.toWire())
            .toList(growable: false),
      if (request.mediaAssetIds.isNotEmpty)
        "mediaAssetIds": request.mediaAssetIds
            .map((value) => value)
            .toList(growable: false),
      if (request.articleMarkdown != null)
        "articleMarkdown": request.articleMarkdown!,
      if (request.markdownDialect != null)
        "markdownDialect": request.markdownDialect!,
      if (request.articleAssetManifest != null)
        "articleAssetManifest": request.articleAssetManifest!.toWire(),
      if (request.articleRenderProfile != null)
        "articleRenderProfile": request.articleRenderProfile!.toWire(),
      if (request.coverStrategy != null)
        "coverStrategy": request.coverStrategy!,
      if (request.coverFrameTimeMs != null)
        "coverFrameTimeMs": request.coverFrameTimeMs!,
      if (request.illustrationAssetId != null)
        "illustrationAssetId": request.illustrationAssetId!,
      if (request.location != null) "location": request.location!.toWire(),
      if (request.locationName != null) "locationName": request.locationName!,
      if (request.geoTagRef != null) "geoTagRef": request.geoTagRef!,
      if (request.visitedAt != null)
        "visitedAt": request.visitedAt!.toUtc().toIso8601String(),
      "captureDisclosure": request.captureDisclosure
          .map((value) => value.wireName)
          .toList(growable: false),
      if (request.primaryHomepageId != null)
        "primaryHomepageId": request.primaryHomepageId!,
      if (request.primaryHomepageType != null)
        "primaryHomepageType": request.primaryHomepageType!,
      if (request.primaryHomepageSnapshot != null)
        "primaryHomepageSnapshot": request.primaryHomepageSnapshot!.toWire(),
      if (request.gatheringRef != null) "gatheringRef": request.gatheringRef!,
      if (request.visibility != null)
        "visibility": request.visibility!.wireName,
      if (request.assistantUsePolicy != null)
        "assistantUsePolicy": request.assistantUsePolicy!.wireName,
      if (request.sourcePostId != null) "sourcePostId": request.sourcePostId!,
      if (request.sourceType != null)
        "sourceType": request.sourceType!.wireName,
      if (request.deviceInfo != null)
        "deviceInfo": request.deviceInfo!.toWire(),
      if (request.publishLocation != null)
        "publishLocation": request.publishLocation!.toWire(),
      if (request.authorDisplayNameSnapshot != null)
        "authorDisplayNameSnapshot": request.authorDisplayNameSnapshot!,
      if (request.authorAvatarUrlSnapshot != null)
        "authorAvatarUrlSnapshot": request.authorAvatarUrlSnapshot!,
      if (request.personaContextVersion != null)
        "personaContextVersion": request.personaContextVersion!,
    },
  );
}

CloudOperationRequestPayload
encodeContentProfileInteractionActivityViewListProfileInteractionActivitiesReceivedGeneratedRequest(
  ContentProfileInteractionPageQuery request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"personaId": request.personaId},
    queryParameters: <String, String>{
      "type": (request.type.wireName).toString(),
      if (request.cursor != null) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
    },
  );
}

CloudOperationRequestPayload
encodeContentProfileInteractionActivityViewListProfileInteractionActivitiesSentGeneratedRequest(
  ContentProfileInteractionPageQuery request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"personaId": request.personaId},
    queryParameters: <String, String>{
      "type": (request.type.wireName).toString(),
      if (request.cursor != null) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
    },
  );
}

CloudOperationRequestPayload
encodeContentProfileInteractionReadFactAppendProfileInteractionReadFactGeneratedRequest(
  AppendContentProfileInteractionReadFactCommand request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "personaId": request.personaId,
      "interactionId": request.activityId,
    },
    body: <String, Object?>{"state": request.state.wireName},
  );
}

CloudOperationRequestPayload encodeContentReportCreateReportGeneratedRequest(
  CreateContentReportCommand request,
) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "targetId": request.targetId,
      "targetType": request.targetType.wireName,
      "reason": request.reason.wireName,
      if (request.description != null) "description": request.description!,
    },
  );
}

CloudOperationRequestPayload encodeContentReportListMyReportsGeneratedRequest(
  ContentMyReportsQuery request,
) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      if (request.cursor != null) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
    },
  );
}
