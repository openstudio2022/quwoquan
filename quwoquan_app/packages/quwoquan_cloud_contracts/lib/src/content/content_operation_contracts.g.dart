// Code generated from canonical domain contracts. DO NOT EDIT.
// ContractGraph SHA256: 93e9c73a4c6bfad3677c3ca5e7a48483a9c59860f345bbd49d9d67567d385255

library;

import '../operation_request_payload.dart';
import "../generated/recommendation/intersection_contract_vocabulary.g.dart";
import "../generated/shared_operation_enums.g.dart";
import "../recommendation/recommendation_operation_contracts.g.dart";

export "../generated/recommendation/intersection_contract_vocabulary.g.dart";
export "../generated/shared_operation_enums.g.dart";
export "../recommendation/recommendation_operation_contracts.g.dart";

part '../generated/requests/content/content_operation_contracts.g.requests.g.dart';

enum CaptureDisclosureGroup {
  gear("gear"),
  parameters("parameters"),
  place("place"),
  time("time");

  const CaptureDisclosureGroup(this.wireName);

  final String wireName;

  static CaptureDisclosureGroup fromWire(Object? value, String path) {
    return switch (value) {
      "gear" => CaptureDisclosureGroup.gear,
      "parameters" => CaptureDisclosureGroup.parameters,
      "place" => CaptureDisclosureGroup.place,
      "time" => CaptureDisclosureGroup.time,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum CommentReactionType {
  none("none"),
  like("like"),
  dislike("dislike");

  const CommentReactionType(this.wireName);

  final String wireName;

  static CommentReactionType fromWire(Object? value, String path) {
    return switch (value) {
      "none" => CommentReactionType.none,
      "like" => CommentReactionType.like,
      "dislike" => CommentReactionType.dislike,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum CommentSort {
  hot("hot"),
  latest("latest");

  const CommentSort(this.wireName);

  final String wireName;

  static CommentSort fromWire(Object? value, String path) {
    return switch (value) {
      "hot" => CommentSort.hot,
      "latest" => CommentSort.latest,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum CommentStatus {
  active("active"),
  hidden("hidden"),
  deleted("deleted"),
  tombstoned("tombstoned");

  const CommentStatus(this.wireName);

  final String wireName;

  static CommentStatus fromWire(Object? value, String path) {
    return switch (value) {
      "active" => CommentStatus.active,
      "hidden" => CommentStatus.hidden,
      "deleted" => CommentStatus.deleted,
      "tombstoned" => CommentStatus.tombstoned,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum CommentViewerRelation {
  none("none"),
  following("following"),
  friend("friend");

  const CommentViewerRelation(this.wireName);

  final String wireName;

  static CommentViewerRelation fromWire(Object? value, String path) {
    return switch (value) {
      "none" => CommentViewerRelation.none,
      "following" => CommentViewerRelation.following,
      "friend" => CommentViewerRelation.friend,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum ContentFeedEmptyReason {
  noActiveRelease("no_active_release"),
  noEligibleContent("no_eligible_content"),
  followingEmpty("following_empty"),
  continuationEnd("continuation_end");

  const ContentFeedEmptyReason(this.wireName);

  final String wireName;

  static ContentFeedEmptyReason fromWire(Object? value, String path) {
    return switch (value) {
      "no_active_release" => ContentFeedEmptyReason.noActiveRelease,
      "no_eligible_content" => ContentFeedEmptyReason.noEligibleContent,
      "following_empty" => ContentFeedEmptyReason.followingEmpty,
      "continuation_end" => ContentFeedEmptyReason.continuationEnd,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum ContentFeedOutcome {
  content("content"),
  empty("empty");

  const ContentFeedOutcome(this.wireName);

  final String wireName;

  static ContentFeedOutcome fromWire(Object? value, String path) {
    return switch (value) {
      "content" => ContentFeedOutcome.content,
      "empty" => ContentFeedOutcome.empty,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum ContentIdentity {
  moment("moment"),
  work("work");

  const ContentIdentity(this.wireName);

  final String wireName;

  static ContentIdentity fromWire(Object? value, String path) {
    return switch (value) {
      "moment" => ContentIdentity.moment,
      "work" => ContentIdentity.work,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum ContentType {
  image("image"),
  video("video"),
  micro("micro"),
  article("article");

  const ContentType(this.wireName);

  final String wireName;

  static ContentType fromWire(Object? value, String path) {
    return switch (value) {
      "image" => ContentType.image,
      "video" => ContentType.video,
      "micro" => ContentType.micro,
      "article" => ContentType.article,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum FilterCatalogReleaseStatus {
  staged("staged"),
  active("active"),
  retired("retired");

  const FilterCatalogReleaseStatus(this.wireName);

  final String wireName;

  static FilterCatalogReleaseStatus fromWire(Object? value, String path) {
    return switch (value) {
      "staged" => FilterCatalogReleaseStatus.staged,
      "active" => FilterCatalogReleaseStatus.active,
      "retired" => FilterCatalogReleaseStatus.retired,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum InteractionActivityType {
  like("like"),
  comment("comment"),
  share("share");

  const InteractionActivityType(this.wireName);

  final String wireName;

  static InteractionActivityType fromWire(Object? value, String path) {
    return switch (value) {
      "like" => InteractionActivityType.like,
      "comment" => InteractionActivityType.comment,
      "share" => InteractionActivityType.share,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum InteractionDirection {
  received("received"),
  sent("sent");

  const InteractionDirection(this.wireName);

  final String wireName;

  static InteractionDirection fromWire(Object? value, String path) {
    return switch (value) {
      "received" => InteractionDirection.received,
      "sent" => InteractionDirection.sent,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum MediaAssetAccessPolicy {
  ownerOnly("owner_only"),
  referencedPost("referenced_post"),
  public("public");

  const MediaAssetAccessPolicy(this.wireName);

  final String wireName;

  static MediaAssetAccessPolicy fromWire(Object? value, String path) {
    return switch (value) {
      "owner_only" => MediaAssetAccessPolicy.ownerOnly,
      "referenced_post" => MediaAssetAccessPolicy.referencedPost,
      "public" => MediaAssetAccessPolicy.public,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum MediaAssetDiscardStatus {
  deleted("deleted");

  const MediaAssetDiscardStatus(this.wireName);

  final String wireName;

  static MediaAssetDiscardStatus fromWire(Object? value, String path) {
    return switch (value) {
      "deleted" => MediaAssetDiscardStatus.deleted,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum MediaAssetStatus {
  processing("processing"),
  ready("ready"),
  rejected("rejected"),
  deleted("deleted");

  const MediaAssetStatus(this.wireName);

  final String wireName;

  static MediaAssetStatus fromWire(Object? value, String path) {
    return switch (value) {
      "processing" => MediaAssetStatus.processing,
      "ready" => MediaAssetStatus.ready,
      "rejected" => MediaAssetStatus.rejected,
      "deleted" => MediaAssetStatus.deleted,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum MediaCoverStrategy {
  firstFrame("first_frame"),
  manual("manual");

  const MediaCoverStrategy(this.wireName);

  final String wireName;

  static MediaCoverStrategy fromWire(Object? value, String path) {
    return switch (value) {
      "first_frame" => MediaCoverStrategy.firstFrame,
      "manual" => MediaCoverStrategy.manual,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum MediaOriginalAccessPurpose {
  view("view"),
  save("save");

  const MediaOriginalAccessPurpose(this.wireName);

  final String wireName;

  static MediaOriginalAccessPurpose fromWire(Object? value, String path) {
    return switch (value) {
      "view" => MediaOriginalAccessPurpose.view,
      "save" => MediaOriginalAccessPurpose.save,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum MediaType {
  image("image"),
  video("video"),
  audio("audio"),
  file("file");

  const MediaType(this.wireName);

  final String wireName;

  static MediaType fromWire(Object? value, String path) {
    return switch (value) {
      "image" => MediaType.image,
      "video" => MediaType.video,
      "audio" => MediaType.audio,
      "file" => MediaType.file,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum MediaUploadSessionStatus {
  pending("pending"),
  completed("completed"),
  aborted("aborted");

  const MediaUploadSessionStatus(this.wireName);

  final String wireName;

  static MediaUploadSessionStatus fromWire(Object? value, String path) {
    return switch (value) {
      "pending" => MediaUploadSessionStatus.pending,
      "completed" => MediaUploadSessionStatus.completed,
      "aborted" => MediaUploadSessionStatus.aborted,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum OutboundShareChannel {
  systemShare("system_share"),
  wechatFriend("wechat_friend"),
  wechatMoments("wechat_moments");

  const OutboundShareChannel(this.wireName);

  final String wireName;

  static OutboundShareChannel fromWire(Object? value, String path) {
    return switch (value) {
      "system_share" => OutboundShareChannel.systemShare,
      "wechat_friend" => OutboundShareChannel.wechatFriend,
      "wechat_moments" => OutboundShareChannel.wechatMoments,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum OutboundShareDestinationKind {
  externalApp("external_app");

  const OutboundShareDestinationKind(this.wireName);

  final String wireName;

  static OutboundShareDestinationKind fromWire(Object? value, String path) {
    return switch (value) {
      "external_app" => OutboundShareDestinationKind.externalApp,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum PostSourceType {
  original("original"),
  repost("repost"),
  quote("quote");

  const PostSourceType(this.wireName);

  final String wireName;

  static PostSourceType fromWire(Object? value, String path) {
    return switch (value) {
      "original" => PostSourceType.original,
      "repost" => PostSourceType.repost,
      "quote" => PostSourceType.quote,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum PostStatus {
  pendingReview("pending_review"),
  published("published"),
  rejected("rejected"),
  deleted("deleted");

  const PostStatus(this.wireName);

  final String wireName;

  static PostStatus fromWire(Object? value, String path) {
    return switch (value) {
      "pending_review" => PostStatus.pendingReview,
      "published" => PostStatus.published,
      "rejected" => PostStatus.rejected,
      "deleted" => PostStatus.deleted,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum ProfileInteractionReadState {
  seen("seen"),
  read("read");

  const ProfileInteractionReadState(this.wireName);

  final String wireName;

  static ProfileInteractionReadState fromWire(Object? value, String path) {
    return switch (value) {
      "seen" => ProfileInteractionReadState.seen,
      "read" => ProfileInteractionReadState.read,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum ReportReason {
  spam("spam"),
  harassment("harassment"),
  violence("violence"),
  adult("adult"),
  copyright("copyright"),
  other("other");

  const ReportReason(this.wireName);

  final String wireName;

  static ReportReason fromWire(Object? value, String path) {
    return switch (value) {
      "spam" => ReportReason.spam,
      "harassment" => ReportReason.harassment,
      "violence" => ReportReason.violence,
      "adult" => ReportReason.adult,
      "copyright" => ReportReason.copyright,
      "other" => ReportReason.other,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum ReportStatus {
  pending("pending"),
  reviewing("reviewing"),
  resolved("resolved"),
  dismissed("dismissed");

  const ReportStatus(this.wireName);

  final String wireName;

  static ReportStatus fromWire(Object? value, String path) {
    return switch (value) {
      "pending" => ReportStatus.pending,
      "reviewing" => ReportStatus.reviewing,
      "resolved" => ReportStatus.resolved,
      "dismissed" => ReportStatus.dismissed,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum ReportTargetType {
  post("post"),
  comment("comment"),
  user("user"),
  circle("circle"),
  gathering("gathering"),
  message("message");

  const ReportTargetType(this.wireName);

  final String wireName;

  static ReportTargetType fromWire(Object? value, String path) {
    return switch (value) {
      "post" => ReportTargetType.post,
      "comment" => ReportTargetType.comment,
      "user" => ReportTargetType.user,
      "circle" => ReportTargetType.circle,
      "gathering" => ReportTargetType.gathering,
      "message" => ReportTargetType.message,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum Visibility {
  public("public"),
  private("private");

  const Visibility(this.wireName);

  final String wireName;

  static Visibility fromWire(Object? value, String path) {
    return switch (value) {
      "public" => Visibility.public,
      "private" => Visibility.private,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

final class AppConfigActivationPolicy {
  const AppConfigActivationPolicy({
    required this.defaultActivation,
    required this.killSwitches,
  });

  final String defaultActivation;
  final String killSwitches;

  factory AppConfigActivationPolicy.fromWire(Map<String, Object?> map, [String path = "AppConfigActivationPolicy"]) {
    _rejectUnknownFields(map, const <String>{"default", "kill_switches"}, path);
    return AppConfigActivationPolicy(
      defaultActivation: _requiredString(map["default"], '$path.default'),
      killSwitches: _requiredString(map["kill_switches"], '$path.kill_switches'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "default": defaultActivation,
    "kill_switches": killSwitches,
  };
}

final class AppConfigSlice {
  const AppConfigSlice({
    required this.schema,
    required this.fetchedAt,
    required this.maxAgeSec,
    required this.activationPolicy,
    required this.content,
    required this.configHash,
  });

  final String schema;
  final DateTime fetchedAt;
  final int maxAgeSec;
  final AppConfigActivationPolicy activationPolicy;
  final ContentAppConfig content;
  final String configHash;

  factory AppConfigSlice.fromWire(Map<String, Object?> map, [String path = "AppConfigSlice"]) {
    _rejectUnknownFields(map, const <String>{"schema", "fetchedAt", "maxAgeSec", "activationPolicy", "content", "configHash"}, path);
    return AppConfigSlice(
      schema: _requiredString(map["schema"], '$path.schema'),
      fetchedAt: _requiredTimestamp(map["fetchedAt"], '$path.fetchedAt'),
      maxAgeSec: _requiredPositiveInt(map["maxAgeSec"], '$path.maxAgeSec'),
      activationPolicy: AppConfigActivationPolicy.fromWire(_requiredObject(map["activationPolicy"], '$path.activationPolicy'), '$path.activationPolicy'),
      content: ContentAppConfig.fromWire(_requiredObject(map["content"], '$path.content'), '$path.content'),
      configHash: _requiredString(map["configHash"], '$path.configHash'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "schema": schema,
    "fetchedAt": fetchedAt.toUtc().toIso8601String(),
    "maxAgeSec": maxAgeSec,
    "activationPolicy": activationPolicy.toWire(),
    "content": content.toWire(),
    "configHash": configHash,
  };
}

final class AuthorCommentPageSlice {
  const AuthorCommentPageSlice({
    required this.items,
    this.nextCursor,
    required this.total,
  });

  final List<CommentListItem> items;
  final String? nextCursor;
  final int total;

  factory AuthorCommentPageSlice.fromWire(Map<String, Object?> map, [String path = "AuthorCommentPageSlice"]) {
    _rejectUnknownFields(map, const <String>{"items", "nextCursor", "total"}, path);
    return AuthorCommentPageSlice(
      items: List<CommentListItem>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => CommentListItem.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      nextCursor: map["nextCursor"] == null ? null : _requiredString(map["nextCursor"], '$path.nextCursor'),
      total: _requiredInt(map["total"], '$path.total'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
    if (nextCursor != null) "nextCursor": nextCursor!,
    "total": total,
  };
}

final class AuthorImpactEvidenceItem {
  const AuthorImpactEvidenceItem({
    required this.evidenceId,
    required this.impactId,
    required this.helpType,
    required this.action,
    required this.intersectionDimension,
    required this.occurredAt,
    required this.summaryText,
    this.sampleVisual,
    this.representativeActor,
    required this.actionHints,
    this.contentTarget,
  });

  final String evidenceId;
  final String impactId;
  final String helpType;
  final String action;
  final String intersectionDimension;
  final DateTime occurredAt;
  final String summaryText;
  final IntersectionVisual? sampleVisual;
  final IntersectionRepresentativeActor? representativeActor;
  final List<IntersectionActionHint> actionHints;
  final IntersectionTarget? contentTarget;

  factory AuthorImpactEvidenceItem.fromWire(Map<String, Object?> map, [String path = "AuthorImpactEvidenceItem"]) {
    _rejectUnknownFields(map, const <String>{"evidenceId", "impactId", "helpType", "action", "intersectionDimension", "occurredAt", "summaryText", "sampleVisual", "representativeActor", "actionHints", "contentTarget"}, path);
    return AuthorImpactEvidenceItem(
      evidenceId: _requiredString(map["evidenceId"], '$path.evidenceId'),
      impactId: _requiredString(map["impactId"], '$path.impactId'),
      helpType: _requiredString(map["helpType"], '$path.helpType'),
      action: _requiredString(map["action"], '$path.action'),
      intersectionDimension: _requiredString(map["intersectionDimension"], '$path.intersectionDimension'),
      occurredAt: _requiredTimestamp(map["occurredAt"], '$path.occurredAt'),
      summaryText: _requiredString(map["summaryText"], '$path.summaryText'),
      sampleVisual: map["sampleVisual"] == null ? null : IntersectionVisual.fromWire(_requiredObject(map["sampleVisual"], '$path.sampleVisual'), '$path.sampleVisual'),
      representativeActor: map["representativeActor"] == null ? null : IntersectionRepresentativeActor.fromWire(_requiredObject(map["representativeActor"], '$path.representativeActor'), '$path.representativeActor'),
      actionHints: List<IntersectionActionHint>.unmodifiable(_requiredList(map["actionHints"], '$path.actionHints').asMap().entries.map((entry) => IntersectionActionHint.fromWire(_requiredObject(entry.value, '$path.actionHints' + '[${entry.key}]'), '$path.actionHints' + '[${entry.key}]'))),
      contentTarget: map["contentTarget"] == null ? null : IntersectionTarget.fromWire(_requiredObject(map["contentTarget"], '$path.contentTarget'), '$path.contentTarget'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "evidenceId": evidenceId,
    "impactId": impactId,
    "helpType": helpType,
    "action": action,
    "intersectionDimension": intersectionDimension,
    "occurredAt": occurredAt.toUtc().toIso8601String(),
    "summaryText": summaryText,
    if (sampleVisual != null) "sampleVisual": sampleVisual!.toWire(),
    if (representativeActor != null) "representativeActor": representativeActor!.toWire(),
    "actionHints": actionHints.map((value) => value.toWire()).toList(growable: false),
    if (contentTarget != null) "contentTarget": contentTarget!.toWire(),
  };
}

final class AuthorImpactEvidencePage {
  const AuthorImpactEvidencePage({
    required this.impactId,
    required this.evidenceSnapshotId,
    required this.totalCount,
    required this.items,
    required this.nextCursor,
    required this.hasMore,
  });

  final String impactId;
  final String evidenceSnapshotId;
  final int totalCount;
  final List<AuthorImpactEvidenceItem> items;
  final String nextCursor;
  final bool hasMore;

  factory AuthorImpactEvidencePage.fromWire(Map<String, Object?> map, [String path = "AuthorImpactEvidencePage"]) {
    _rejectUnknownFields(map, const <String>{"impactId", "evidenceSnapshotId", "totalCount", "items", "nextCursor", "hasMore"}, path);
    return AuthorImpactEvidencePage(
      impactId: _requiredString(map["impactId"], '$path.impactId'),
      evidenceSnapshotId: _requiredString(map["evidenceSnapshotId"], '$path.evidenceSnapshotId'),
      totalCount: _requiredInt(map["totalCount"], '$path.totalCount'),
      items: List<AuthorImpactEvidenceItem>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => AuthorImpactEvidenceItem.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      nextCursor: _requiredString(map["nextCursor"], '$path.nextCursor'),
      hasMore: _requiredBool(map["hasMore"], '$path.hasMore'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "impactId": impactId,
    "evidenceSnapshotId": evidenceSnapshotId,
    "totalCount": totalCount,
    "items": items.map((value) => value.toWire()).toList(growable: false),
    "nextCursor": nextCursor,
    "hasMore": hasMore,
  };
}

final class AuthorImpactItem {
  const AuthorImpactItem({
    required this.helpType,
    required this.action,
    required this.intersectionDimension,
    required this.tagRef,
    required this.source,
    required this.count,
    required this.primaryText,
    required this.subtitleText,
    required this.impactId,
    required this.primarySpans,
    required this.sampleVisuals,
    this.representativeActor,
    required this.actionHints,
    this.countTarget,
    required this.evidenceSnapshotId,
    required this.countObjectKind,
    this.propagationPath,
    required this.iconKey,
    required this.freshAt,
    required this.timeBucket,
    required this.lifecycleState,
    required this.previousStrength,
    required this.strengthDelta,
  });

  final String helpType;
  final String action;
  final String intersectionDimension;
  final String tagRef;
  final String source;
  final int count;
  final String primaryText;
  final String subtitleText;
  final String impactId;
  final List<IntersectionTextSpan> primarySpans;
  final List<IntersectionVisual> sampleVisuals;
  final IntersectionRepresentativeActor? representativeActor;
  final List<IntersectionActionHint> actionHints;
  final IntersectionTarget? countTarget;
  final String evidenceSnapshotId;
  final String countObjectKind;
  final IntersectionPropagationPath? propagationPath;
  final String iconKey;
  final DateTime freshAt;
  final String timeBucket;
  final String lifecycleState;
  final double previousStrength;
  final double strengthDelta;

  factory AuthorImpactItem.fromWire(Map<String, Object?> map, [String path = "AuthorImpactItem"]) {
    _rejectUnknownFields(map, const <String>{"helpType", "action", "intersectionDimension", "tagRef", "source", "count", "primaryText", "subtitleText", "impactId", "primarySpans", "sampleVisuals", "representativeActor", "actionHints", "countTarget", "evidenceSnapshotId", "countObjectKind", "propagationPath", "iconKey", "freshAt", "timeBucket", "lifecycleState", "previousStrength", "strengthDelta"}, path);
    return AuthorImpactItem(
      helpType: _requiredString(map["helpType"], '$path.helpType'),
      action: _requiredString(map["action"], '$path.action'),
      intersectionDimension: _requiredString(map["intersectionDimension"], '$path.intersectionDimension'),
      tagRef: _requiredString(map["tagRef"], '$path.tagRef'),
      source: _requiredString(map["source"], '$path.source'),
      count: _requiredInt(map["count"], '$path.count'),
      primaryText: _requiredString(map["primaryText"], '$path.primaryText'),
      subtitleText: _requiredString(map["subtitleText"], '$path.subtitleText'),
      impactId: _requiredString(map["impactId"], '$path.impactId'),
      primarySpans: List<IntersectionTextSpan>.unmodifiable(_requiredList(map["primarySpans"], '$path.primarySpans').asMap().entries.map((entry) => IntersectionTextSpan.fromWire(_requiredObject(entry.value, '$path.primarySpans' + '[${entry.key}]'), '$path.primarySpans' + '[${entry.key}]'))),
      sampleVisuals: List<IntersectionVisual>.unmodifiable(_requiredList(map["sampleVisuals"], '$path.sampleVisuals').asMap().entries.map((entry) => IntersectionVisual.fromWire(_requiredObject(entry.value, '$path.sampleVisuals' + '[${entry.key}]'), '$path.sampleVisuals' + '[${entry.key}]'))),
      representativeActor: map["representativeActor"] == null ? null : IntersectionRepresentativeActor.fromWire(_requiredObject(map["representativeActor"], '$path.representativeActor'), '$path.representativeActor'),
      actionHints: List<IntersectionActionHint>.unmodifiable(_requiredList(map["actionHints"], '$path.actionHints').asMap().entries.map((entry) => IntersectionActionHint.fromWire(_requiredObject(entry.value, '$path.actionHints' + '[${entry.key}]'), '$path.actionHints' + '[${entry.key}]'))),
      countTarget: map["countTarget"] == null ? null : IntersectionTarget.fromWire(_requiredObject(map["countTarget"], '$path.countTarget'), '$path.countTarget'),
      evidenceSnapshotId: _requiredString(map["evidenceSnapshotId"], '$path.evidenceSnapshotId'),
      countObjectKind: _requiredString(map["countObjectKind"], '$path.countObjectKind'),
      propagationPath: map["propagationPath"] == null ? null : IntersectionPropagationPath.fromWire(_requiredObject(map["propagationPath"], '$path.propagationPath'), '$path.propagationPath'),
      iconKey: _requiredString(map["iconKey"], '$path.iconKey'),
      freshAt: _requiredTimestamp(map["freshAt"], '$path.freshAt'),
      timeBucket: _requiredString(map["timeBucket"], '$path.timeBucket'),
      lifecycleState: _requiredString(map["lifecycleState"], '$path.lifecycleState'),
      previousStrength: _requiredDouble(map["previousStrength"], '$path.previousStrength'),
      strengthDelta: _requiredDouble(map["strengthDelta"], '$path.strengthDelta'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "helpType": helpType,
    "action": action,
    "intersectionDimension": intersectionDimension,
    "tagRef": tagRef,
    "source": source,
    "count": count,
    "primaryText": primaryText,
    "subtitleText": subtitleText,
    "impactId": impactId,
    "primarySpans": primarySpans.map((value) => value.toWire()).toList(growable: false),
    "sampleVisuals": sampleVisuals.map((value) => value.toWire()).toList(growable: false),
    if (representativeActor != null) "representativeActor": representativeActor!.toWire(),
    "actionHints": actionHints.map((value) => value.toWire()).toList(growable: false),
    if (countTarget != null) "countTarget": countTarget!.toWire(),
    "evidenceSnapshotId": evidenceSnapshotId,
    "countObjectKind": countObjectKind,
    if (propagationPath != null) "propagationPath": propagationPath!.toWire(),
    "iconKey": iconKey,
    "freshAt": freshAt.toUtc().toIso8601String(),
    "timeBucket": timeBucket,
    "lifecycleState": lifecycleState,
    "previousStrength": previousStrength,
    "strengthDelta": strengthDelta,
  };
}

final class AuthorImpactSummary {
  const AuthorImpactSummary({
    required this.authorId,
    required this.total,
    required this.items,
  });

  final String authorId;
  final int total;
  final List<AuthorImpactItem> items;

  factory AuthorImpactSummary.fromWire(Map<String, Object?> map, [String path = "AuthorImpactSummary"]) {
    _rejectUnknownFields(map, const <String>{"authorId", "total", "items"}, path);
    return AuthorImpactSummary(
      authorId: _requiredString(map["authorId"], '$path.authorId'),
      total: _requiredInt(map["total"], '$path.total'),
      items: List<AuthorImpactItem>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => AuthorImpactItem.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "authorId": authorId,
    "total": total,
    "items": items.map((value) => value.toWire()).toList(growable: false),
  };
}

final class AuthorPostPageSlice {
  const AuthorPostPageSlice({
    required this.items,
    this.nextCursor,
    required this.hasMore,
  });

  final List<ContentPostProjection> items;
  final String? nextCursor;
  final bool hasMore;

  factory AuthorPostPageSlice.fromWire(Map<String, Object?> map, [String path = "AuthorPostPageSlice"]) {
    _rejectUnknownFields(map, const <String>{"items", "nextCursor", "hasMore"}, path);
    return AuthorPostPageSlice(
      items: List<ContentPostProjection>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => ContentPostProjection.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      nextCursor: map["nextCursor"] == null ? null : _requiredString(map["nextCursor"], '$path.nextCursor'),
      hasMore: _requiredBool(map["hasMore"], '$path.hasMore'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
    if (nextCursor != null) "nextCursor": nextCursor!,
    "hasMore": hasMore,
  };
}

final class CommentAttachmentSlice {
  const CommentAttachmentSlice({
    required this.mediaId,
    this.mediaType,
    this.url,
    this.width,
    this.height,
    required this.available,
  });

  final String mediaId;
  final String? mediaType;
  final Uri? url;
  final int? width;
  final int? height;
  final bool available;

  factory CommentAttachmentSlice.fromWire(Map<String, Object?> map, [String path = "CommentAttachmentSlice"]) {
    _rejectUnknownFields(map, const <String>{"mediaId", "mediaType", "url", "width", "height", "available"}, path);
    return CommentAttachmentSlice(
      mediaId: _requiredString(map["mediaId"], '$path.mediaId'),
      mediaType: map["mediaType"] == null ? null : _requiredString(map["mediaType"], '$path.mediaType'),
      url: map["url"] == null ? null : _requiredUri(map["url"], '$path.url'),
      width: map["width"] == null ? null : _requiredPositiveInt(map["width"], '$path.width'),
      height: map["height"] == null ? null : _requiredPositiveInt(map["height"], '$path.height'),
      available: _requiredBool(map["available"], '$path.available'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "mediaId": mediaId,
    if (mediaType != null) "mediaType": mediaType!,
    if (url != null) "url": url!.toString(),
    if (width != null) "width": width!,
    if (height != null) "height": height!,
    "available": available,
  };
}

final class CommentCommandResult {
  const CommentCommandResult({
    required this.id,
    required this.version,
    required this.status,
    required this.replayed,
  });

  final String id;
  final int version;
  final CommentStatus status;
  final bool replayed;

  factory CommentCommandResult.fromWire(Map<String, Object?> map, [String path = "CommentCommandResult"]) {
    _rejectUnknownFields(map, const <String>{"id", "version", "status", "replayed"}, path);
    return CommentCommandResult(
      id: _requiredString(map["id"], '$path.id'),
      version: _requiredPositiveInt(map["version"], '$path.version'),
      status: CommentStatus.fromWire(map["status"], '$path.status'),
      replayed: _requiredBool(map["replayed"], '$path.replayed'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "id": id,
    "version": version,
    "status": status.wireName,
    "replayed": replayed,
  };
}

final class CommentListItem {
  const CommentListItem({
    required this.id,
    required this.version,
    required this.postId,
    required this.authorId,
    this.authorDisplayNameSnapshot,
    this.authorAvatarUrlSnapshot,
    this.personaContextVersion,
    required this.content,
    this.replyToCommentId,
    this.replyToUserId,
    this.parentCommentId,
    required this.attachmentMediaIds,
    required this.attachments,
    required this.mentions,
    required this.assistantMentioned,
    this.assistantReplySource,
    this.assistantCorrectionStatus,
    this.authorIpLocation,
    required this.status,
    required this.isPinned,
    this.pinnedAt,
    required this.createdAt,
    required this.updatedAt,
    this.deletedAt,
    required this.replyCount,
    required this.replyPreview,
    this.replyNextCursor,
    required this.likeCount,
    required this.dislikeCount,
    required this.viewerReaction,
    required this.authorLiked,
    required this.viewerRelation,
    required this.isAuthor,
    required this.canDelete,
    required this.canReply,
    required this.canReport,
    required this.canPin,
  });

  final String id;
  final int version;
  final String postId;
  final String authorId;
  final String? authorDisplayNameSnapshot;
  final Uri? authorAvatarUrlSnapshot;
  final int? personaContextVersion;
  final String content;
  final String? replyToCommentId;
  final String? replyToUserId;
  final String? parentCommentId;
  final List<String> attachmentMediaIds;
  final List<CommentAttachmentSlice> attachments;
  final List<CommentMention> mentions;
  final bool assistantMentioned;
  final String? assistantReplySource;
  final String? assistantCorrectionStatus;
  final String? authorIpLocation;
  final CommentStatus status;
  final bool isPinned;
  final DateTime? pinnedAt;
  final DateTime createdAt;
  final DateTime updatedAt;
  final DateTime? deletedAt;
  final int replyCount;
  final List<CommentListItem> replyPreview;
  final String? replyNextCursor;
  final int likeCount;
  final int dislikeCount;
  final CommentReactionType viewerReaction;
  final bool authorLiked;
  final CommentViewerRelation viewerRelation;
  final bool isAuthor;
  final bool canDelete;
  final bool canReply;
  final bool canReport;
  final bool canPin;

  factory CommentListItem.fromWire(Map<String, Object?> map, [String path = "CommentListItem"]) {
    _rejectUnknownFields(map, const <String>{"id", "version", "postId", "authorId", "authorDisplayNameSnapshot", "authorAvatarUrlSnapshot", "personaContextVersion", "content", "replyToCommentId", "replyToUserId", "parentCommentId", "attachmentMediaIds", "attachments", "mentions", "assistantMentioned", "assistantReplySource", "assistantCorrectionStatus", "authorIpLocation", "status", "isPinned", "pinnedAt", "createdAt", "updatedAt", "deletedAt", "replyCount", "replyPreview", "replyNextCursor", "likeCount", "dislikeCount", "viewerReaction", "authorLiked", "viewerRelation", "isAuthor", "canDelete", "canReply", "canReport", "canPin"}, path);
    return CommentListItem(
      id: _requiredString(map["id"], '$path.id'),
      version: _requiredPositiveInt(map["version"], '$path.version'),
      postId: _requiredString(map["postId"], '$path.postId'),
      authorId: _requiredString(map["authorId"], '$path.authorId'),
      authorDisplayNameSnapshot: map["authorDisplayNameSnapshot"] == null ? null : _requiredString(map["authorDisplayNameSnapshot"], '$path.authorDisplayNameSnapshot'),
      authorAvatarUrlSnapshot: map["authorAvatarUrlSnapshot"] == null ? null : _requiredUri(map["authorAvatarUrlSnapshot"], '$path.authorAvatarUrlSnapshot'),
      personaContextVersion: map["personaContextVersion"] == null ? null : _requiredPositiveInt(map["personaContextVersion"], '$path.personaContextVersion'),
      content: _requiredString(map["content"], '$path.content'),
      replyToCommentId: map["replyToCommentId"] == null ? null : _requiredString(map["replyToCommentId"], '$path.replyToCommentId'),
      replyToUserId: map["replyToUserId"] == null ? null : _requiredString(map["replyToUserId"], '$path.replyToUserId'),
      parentCommentId: map["parentCommentId"] == null ? null : _requiredString(map["parentCommentId"], '$path.parentCommentId'),
      attachmentMediaIds: List<String>.unmodifiable(_requiredList(map["attachmentMediaIds"], '$path.attachmentMediaIds').asMap().entries.map((entry) => _requiredString(entry.value, '$path.attachmentMediaIds' + '[${entry.key}]'))),
      attachments: List<CommentAttachmentSlice>.unmodifiable(_requiredList(map["attachments"], '$path.attachments').asMap().entries.map((entry) => CommentAttachmentSlice.fromWire(_requiredObject(entry.value, '$path.attachments' + '[${entry.key}]'), '$path.attachments' + '[${entry.key}]'))),
      mentions: List<CommentMention>.unmodifiable(_requiredList(map["mentions"], '$path.mentions').asMap().entries.map((entry) => CommentMention.fromWire(_requiredObject(entry.value, '$path.mentions' + '[${entry.key}]'), '$path.mentions' + '[${entry.key}]'))),
      assistantMentioned: _requiredBool(map["assistantMentioned"], '$path.assistantMentioned'),
      assistantReplySource: map["assistantReplySource"] == null ? null : _requiredString(map["assistantReplySource"], '$path.assistantReplySource'),
      assistantCorrectionStatus: map["assistantCorrectionStatus"] == null ? null : _requiredString(map["assistantCorrectionStatus"], '$path.assistantCorrectionStatus'),
      authorIpLocation: map["authorIpLocation"] == null ? null : _requiredString(map["authorIpLocation"], '$path.authorIpLocation'),
      status: CommentStatus.fromWire(map["status"], '$path.status'),
      isPinned: _requiredBool(map["isPinned"], '$path.isPinned'),
      pinnedAt: map["pinnedAt"] == null ? null : _requiredTimestamp(map["pinnedAt"], '$path.pinnedAt'),
      createdAt: _requiredTimestamp(map["createdAt"], '$path.createdAt'),
      updatedAt: _requiredTimestamp(map["updatedAt"], '$path.updatedAt'),
      deletedAt: map["deletedAt"] == null ? null : _requiredTimestamp(map["deletedAt"], '$path.deletedAt'),
      replyCount: _requiredInt(map["replyCount"], '$path.replyCount'),
      replyPreview: List<CommentListItem>.unmodifiable(_requiredList(map["replyPreview"], '$path.replyPreview').asMap().entries.map((entry) => CommentListItem.fromWire(_requiredObject(entry.value, '$path.replyPreview' + '[${entry.key}]'), '$path.replyPreview' + '[${entry.key}]'))),
      replyNextCursor: map["replyNextCursor"] == null ? null : _requiredString(map["replyNextCursor"], '$path.replyNextCursor'),
      likeCount: _requiredInt(map["likeCount"], '$path.likeCount'),
      dislikeCount: _requiredInt(map["dislikeCount"], '$path.dislikeCount'),
      viewerReaction: CommentReactionType.fromWire(map["viewerReaction"], '$path.viewerReaction'),
      authorLiked: _requiredBool(map["authorLiked"], '$path.authorLiked'),
      viewerRelation: CommentViewerRelation.fromWire(map["viewerRelation"], '$path.viewerRelation'),
      isAuthor: _requiredBool(map["isAuthor"], '$path.isAuthor'),
      canDelete: _requiredBool(map["canDelete"], '$path.canDelete'),
      canReply: _requiredBool(map["canReply"], '$path.canReply'),
      canReport: _requiredBool(map["canReport"], '$path.canReport'),
      canPin: _requiredBool(map["canPin"], '$path.canPin'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "id": id,
    "version": version,
    "postId": postId,
    "authorId": authorId,
    if (authorDisplayNameSnapshot != null) "authorDisplayNameSnapshot": authorDisplayNameSnapshot!,
    if (authorAvatarUrlSnapshot != null) "authorAvatarUrlSnapshot": authorAvatarUrlSnapshot!.toString(),
    if (personaContextVersion != null) "personaContextVersion": personaContextVersion!,
    "content": content,
    if (replyToCommentId != null) "replyToCommentId": replyToCommentId!,
    if (replyToUserId != null) "replyToUserId": replyToUserId!,
    if (parentCommentId != null) "parentCommentId": parentCommentId!,
    "attachmentMediaIds": attachmentMediaIds.map((value) => value).toList(growable: false),
    "attachments": attachments.map((value) => value.toWire()).toList(growable: false),
    "mentions": mentions.map((value) => value.toWire()).toList(growable: false),
    "assistantMentioned": assistantMentioned,
    if (assistantReplySource != null) "assistantReplySource": assistantReplySource!,
    if (assistantCorrectionStatus != null) "assistantCorrectionStatus": assistantCorrectionStatus!,
    if (authorIpLocation != null) "authorIpLocation": authorIpLocation!,
    "status": status.wireName,
    "isPinned": isPinned,
    if (pinnedAt != null) "pinnedAt": pinnedAt!.toUtc().toIso8601String(),
    "createdAt": createdAt.toUtc().toIso8601String(),
    "updatedAt": updatedAt.toUtc().toIso8601String(),
    if (deletedAt != null) "deletedAt": deletedAt!.toUtc().toIso8601String(),
    "replyCount": replyCount,
    "replyPreview": replyPreview.map((value) => value.toWire()).toList(growable: false),
    if (replyNextCursor != null) "replyNextCursor": replyNextCursor!,
    "likeCount": likeCount,
    "dislikeCount": dislikeCount,
    "viewerReaction": viewerReaction.wireName,
    "authorLiked": authorLiked,
    "viewerRelation": viewerRelation.wireName,
    "isAuthor": isAuthor,
    "canDelete": canDelete,
    "canReply": canReply,
    "canReport": canReport,
    "canPin": canPin,
  };
}

final class CommentMention {
  const CommentMention({
    required this.subjectType,
    required this.subjectId,
    this.displayName,
  });

  final String subjectType;
  final String subjectId;
  final String? displayName;

  factory CommentMention.fromWire(Map<String, Object?> map, [String path = "CommentMention"]) {
    _rejectUnknownFields(map, const <String>{"subjectType", "subjectId", "displayName"}, path);
    return CommentMention(
      subjectType: _requiredString(map["subjectType"], '$path.subjectType'),
      subjectId: _requiredString(map["subjectId"], '$path.subjectId'),
      displayName: map["displayName"] == null ? null : _requiredString(map["displayName"], '$path.displayName'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "subjectType": subjectType,
    "subjectId": subjectId,
    if (displayName != null) "displayName": displayName!,
  };
}

final class CommentPageSlice {
  const CommentPageSlice({
    required this.items,
    this.nextCursor,
    required this.total,
  });

  final List<CommentListItem> items;
  final String? nextCursor;
  final int total;

  factory CommentPageSlice.fromWire(Map<String, Object?> map, [String path = "CommentPageSlice"]) {
    _rejectUnknownFields(map, const <String>{"items", "nextCursor", "total"}, path);
    return CommentPageSlice(
      items: List<CommentListItem>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => CommentListItem.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      nextCursor: map["nextCursor"] == null ? null : _requiredString(map["nextCursor"], '$path.nextCursor'),
      total: _requiredInt(map["total"], '$path.total'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
    if (nextCursor != null) "nextCursor": nextCursor!,
    "total": total,
  };
}

final class ContentAppConfig {
  const ContentAppConfig({
    required this.featureFlags,
    required this.grayRelease,
    this.clientStateSync,
    this.homeChannels,
    this.comment,
    this.intersection,
  });

  final ContentAppConfigFeatureFlags featureFlags;
  final ContentAppConfigGrayRelease grayRelease;
  final ContentAppConfigClientStateSync? clientStateSync;
  final List<ContentAppConfigHomeChannel>? homeChannels;
  final ContentAppConfigComment? comment;
  final ContentAppConfigIntersection? intersection;

  factory ContentAppConfig.fromWire(Map<String, Object?> map, [String path = "ContentAppConfig"]) {
    _rejectUnknownFields(map, const <String>{"feature_flags", "gray_release", "client_state_sync", "home_channels", "comment", "intersection"}, path);
    return ContentAppConfig(
      featureFlags: ContentAppConfigFeatureFlags.fromWire(_requiredObject(map["feature_flags"], '$path.feature_flags'), '$path.feature_flags'),
      grayRelease: ContentAppConfigGrayRelease.fromWire(_requiredObject(map["gray_release"], '$path.gray_release'), '$path.gray_release'),
      clientStateSync: map["client_state_sync"] == null ? null : ContentAppConfigClientStateSync.fromWire(_requiredObject(map["client_state_sync"], '$path.client_state_sync'), '$path.client_state_sync'),
      homeChannels: map["home_channels"] == null ? null : List<ContentAppConfigHomeChannel>.unmodifiable(_requiredList(map["home_channels"], '$path.home_channels').asMap().entries.map((entry) => ContentAppConfigHomeChannel.fromWire(_requiredObject(entry.value, '$path.home_channels' + '[${entry.key}]'), '$path.home_channels' + '[${entry.key}]'))),
      comment: map["comment"] == null ? null : ContentAppConfigComment.fromWire(_requiredObject(map["comment"], '$path.comment'), '$path.comment'),
      intersection: map["intersection"] == null ? null : ContentAppConfigIntersection.fromWire(_requiredObject(map["intersection"], '$path.intersection'), '$path.intersection'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "feature_flags": featureFlags.toWire(),
    "gray_release": grayRelease.toWire(),
    if (clientStateSync != null) "client_state_sync": clientStateSync!.toWire(),
    if (homeChannels != null) "home_channels": homeChannels!.map((value) => value.toWire()).toList(growable: false),
    if (comment != null) "comment": comment!.toWire(),
    if (intersection != null) "intersection": intersection!.toWire(),
  };
}

final class ContentAppConfigCanaryStage {
  const ContentAppConfigCanaryStage({
    required this.stage,
    required this.rolloutPercent,
  });

  final String stage;
  final int rolloutPercent;

  factory ContentAppConfigCanaryStage.fromWire(Map<String, Object?> map, [String path = "ContentAppConfigCanaryStage"]) {
    _rejectUnknownFields(map, const <String>{"stage", "rolloutPercent"}, path);
    return ContentAppConfigCanaryStage(
      stage: _requiredString(map["stage"], '$path.stage'),
      rolloutPercent: _requiredBoundedInt(map["rolloutPercent"], '$path.rolloutPercent', min: 0, max: 100),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "stage": stage,
    "rolloutPercent": rolloutPercent,
  };
}

final class ContentAppConfigClientStateSync {
  const ContentAppConfigClientStateSync({
    this.flushDelaySec,
    this.retryDelaySec,
    this.maxBatchSize,
    this.maxPendingAgeSec,
    this.flushOnForegroundResume,
    this.flushOnNetworkRecovered,
  });

  final int? flushDelaySec;
  final int? retryDelaySec;
  final int? maxBatchSize;
  final int? maxPendingAgeSec;
  final bool? flushOnForegroundResume;
  final bool? flushOnNetworkRecovered;

  factory ContentAppConfigClientStateSync.fromWire(Map<String, Object?> map, [String path = "ContentAppConfigClientStateSync"]) {
    _rejectUnknownFields(map, const <String>{"flush_delay_sec", "retry_delay_sec", "max_batch_size", "max_pending_age_sec", "flush_on_foreground_resume", "flush_on_network_recovered"}, path);
    return ContentAppConfigClientStateSync(
      flushDelaySec: map["flush_delay_sec"] == null ? null : _requiredPositiveInt(map["flush_delay_sec"], '$path.flush_delay_sec'),
      retryDelaySec: map["retry_delay_sec"] == null ? null : _requiredPositiveInt(map["retry_delay_sec"], '$path.retry_delay_sec'),
      maxBatchSize: map["max_batch_size"] == null ? null : _requiredPositiveInt(map["max_batch_size"], '$path.max_batch_size'),
      maxPendingAgeSec: map["max_pending_age_sec"] == null ? null : _requiredPositiveInt(map["max_pending_age_sec"], '$path.max_pending_age_sec'),
      flushOnForegroundResume: map["flush_on_foreground_resume"] == null ? null : _requiredBool(map["flush_on_foreground_resume"], '$path.flush_on_foreground_resume'),
      flushOnNetworkRecovered: map["flush_on_network_recovered"] == null ? null : _requiredBool(map["flush_on_network_recovered"], '$path.flush_on_network_recovered'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (flushDelaySec != null) "flush_delay_sec": flushDelaySec!,
    if (retryDelaySec != null) "retry_delay_sec": retryDelaySec!,
    if (maxBatchSize != null) "max_batch_size": maxBatchSize!,
    if (maxPendingAgeSec != null) "max_pending_age_sec": maxPendingAgeSec!,
    if (flushOnForegroundResume != null) "flush_on_foreground_resume": flushOnForegroundResume!,
    if (flushOnNetworkRecovered != null) "flush_on_network_recovered": flushOnNetworkRecovered!,
  };
}

final class ContentAppConfigComment {
  const ContentAppConfigComment({
    this.maxLength,
    this.replyPreviewCount,
    this.replyFirstExpandPageSize,
    this.replyExpandPageSize,
    this.foldLineCount,
    this.attachment,
    this.enabled,
  });

  final int? maxLength;
  final int? replyPreviewCount;
  final int? replyFirstExpandPageSize;
  final int? replyExpandPageSize;
  final int? foldLineCount;
  final ContentAppConfigCommentAttachment? attachment;
  final bool? enabled;

  factory ContentAppConfigComment.fromWire(Map<String, Object?> map, [String path = "ContentAppConfigComment"]) {
    _rejectUnknownFields(map, const <String>{"max_length", "reply_preview_count", "reply_first_expand_page_size", "reply_expand_page_size", "fold_line_count", "attachment", "enabled"}, path);
    return ContentAppConfigComment(
      maxLength: map["max_length"] == null ? null : _requiredPositiveInt(map["max_length"], '$path.max_length'),
      replyPreviewCount: map["reply_preview_count"] == null ? null : _requiredPositiveInt(map["reply_preview_count"], '$path.reply_preview_count'),
      replyFirstExpandPageSize: map["reply_first_expand_page_size"] == null ? null : _requiredPositiveInt(map["reply_first_expand_page_size"], '$path.reply_first_expand_page_size'),
      replyExpandPageSize: map["reply_expand_page_size"] == null ? null : _requiredPositiveInt(map["reply_expand_page_size"], '$path.reply_expand_page_size'),
      foldLineCount: map["fold_line_count"] == null ? null : _requiredPositiveInt(map["fold_line_count"], '$path.fold_line_count'),
      attachment: map["attachment"] == null ? null : ContentAppConfigCommentAttachment.fromWire(_requiredObject(map["attachment"], '$path.attachment'), '$path.attachment'),
      enabled: map["enabled"] == null ? null : _requiredBool(map["enabled"], '$path.enabled'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (maxLength != null) "max_length": maxLength!,
    if (replyPreviewCount != null) "reply_preview_count": replyPreviewCount!,
    if (replyFirstExpandPageSize != null) "reply_first_expand_page_size": replyFirstExpandPageSize!,
    if (replyExpandPageSize != null) "reply_expand_page_size": replyExpandPageSize!,
    if (foldLineCount != null) "fold_line_count": foldLineCount!,
    if (attachment != null) "attachment": attachment!.toWire(),
    if (enabled != null) "enabled": enabled!,
  };
}

final class ContentAppConfigCommentAttachment {
  const ContentAppConfigCommentAttachment({
    this.maxImages,
  });

  final int? maxImages;

  factory ContentAppConfigCommentAttachment.fromWire(Map<String, Object?> map, [String path = "ContentAppConfigCommentAttachment"]) {
    _rejectUnknownFields(map, const <String>{"max_images"}, path);
    return ContentAppConfigCommentAttachment(
      maxImages: map["max_images"] == null ? null : _requiredPositiveInt(map["max_images"], '$path.max_images'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (maxImages != null) "max_images": maxImages!,
  };
}

final class ContentAppConfigFeatureFlags {
  const ContentAppConfigFeatureFlags({
    this.enableCreateActionEntry,
    this.enableUnifiedCreateEditor,
    this.enableIdentityBasedSurfaces,
    this.enableIdentityShareTemplate,
    this.enableArticleDistributionProfiles,
    this.enableArticleBookReader,
    this.enableArticlePageCurl,
    this.enableSharedVideoTimeline,
    this.enableVideoTimelinePreview,
    this.enableHlsCmafAbr,
    this.enableAssistantContentIdentityIndex,
    this.enableHelperRead,
    this.enableShareToCircle,
    this.showViewCount,
  });

  final bool? enableCreateActionEntry;
  final bool? enableUnifiedCreateEditor;
  final bool? enableIdentityBasedSurfaces;
  final bool? enableIdentityShareTemplate;
  final bool? enableArticleDistributionProfiles;
  final bool? enableArticleBookReader;
  final bool? enableArticlePageCurl;
  final bool? enableSharedVideoTimeline;
  final bool? enableVideoTimelinePreview;
  final bool? enableHlsCmafAbr;
  final bool? enableAssistantContentIdentityIndex;
  final bool? enableHelperRead;
  final bool? enableShareToCircle;
  final bool? showViewCount;

  factory ContentAppConfigFeatureFlags.fromWire(Map<String, Object?> map, [String path = "ContentAppConfigFeatureFlags"]) {
    _rejectUnknownFields(map, const <String>{"enable_create_action_entry", "enable_unified_create_editor", "enable_identity_based_surfaces", "enable_identity_share_template", "enable_article_distribution_profiles", "enable_article_book_reader", "enable_article_page_curl", "enable_shared_video_timeline", "enable_video_timeline_preview", "enable_hls_cmaf_abr", "enable_assistant_content_identity_index", "enable_helper_read", "enable_share_to_circle", "show_view_count"}, path);
    return ContentAppConfigFeatureFlags(
      enableCreateActionEntry: map["enable_create_action_entry"] == null ? null : _requiredBool(map["enable_create_action_entry"], '$path.enable_create_action_entry'),
      enableUnifiedCreateEditor: map["enable_unified_create_editor"] == null ? null : _requiredBool(map["enable_unified_create_editor"], '$path.enable_unified_create_editor'),
      enableIdentityBasedSurfaces: map["enable_identity_based_surfaces"] == null ? null : _requiredBool(map["enable_identity_based_surfaces"], '$path.enable_identity_based_surfaces'),
      enableIdentityShareTemplate: map["enable_identity_share_template"] == null ? null : _requiredBool(map["enable_identity_share_template"], '$path.enable_identity_share_template'),
      enableArticleDistributionProfiles: map["enable_article_distribution_profiles"] == null ? null : _requiredBool(map["enable_article_distribution_profiles"], '$path.enable_article_distribution_profiles'),
      enableArticleBookReader: map["enable_article_book_reader"] == null ? null : _requiredBool(map["enable_article_book_reader"], '$path.enable_article_book_reader'),
      enableArticlePageCurl: map["enable_article_page_curl"] == null ? null : _requiredBool(map["enable_article_page_curl"], '$path.enable_article_page_curl'),
      enableSharedVideoTimeline: map["enable_shared_video_timeline"] == null ? null : _requiredBool(map["enable_shared_video_timeline"], '$path.enable_shared_video_timeline'),
      enableVideoTimelinePreview: map["enable_video_timeline_preview"] == null ? null : _requiredBool(map["enable_video_timeline_preview"], '$path.enable_video_timeline_preview'),
      enableHlsCmafAbr: map["enable_hls_cmaf_abr"] == null ? null : _requiredBool(map["enable_hls_cmaf_abr"], '$path.enable_hls_cmaf_abr'),
      enableAssistantContentIdentityIndex: map["enable_assistant_content_identity_index"] == null ? null : _requiredBool(map["enable_assistant_content_identity_index"], '$path.enable_assistant_content_identity_index'),
      enableHelperRead: map["enable_helper_read"] == null ? null : _requiredBool(map["enable_helper_read"], '$path.enable_helper_read'),
      enableShareToCircle: map["enable_share_to_circle"] == null ? null : _requiredBool(map["enable_share_to_circle"], '$path.enable_share_to_circle'),
      showViewCount: map["show_view_count"] == null ? null : _requiredBool(map["show_view_count"], '$path.show_view_count'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (enableCreateActionEntry != null) "enable_create_action_entry": enableCreateActionEntry!,
    if (enableUnifiedCreateEditor != null) "enable_unified_create_editor": enableUnifiedCreateEditor!,
    if (enableIdentityBasedSurfaces != null) "enable_identity_based_surfaces": enableIdentityBasedSurfaces!,
    if (enableIdentityShareTemplate != null) "enable_identity_share_template": enableIdentityShareTemplate!,
    if (enableArticleDistributionProfiles != null) "enable_article_distribution_profiles": enableArticleDistributionProfiles!,
    if (enableArticleBookReader != null) "enable_article_book_reader": enableArticleBookReader!,
    if (enableArticlePageCurl != null) "enable_article_page_curl": enableArticlePageCurl!,
    if (enableSharedVideoTimeline != null) "enable_shared_video_timeline": enableSharedVideoTimeline!,
    if (enableVideoTimelinePreview != null) "enable_video_timeline_preview": enableVideoTimelinePreview!,
    if (enableHlsCmafAbr != null) "enable_hls_cmaf_abr": enableHlsCmafAbr!,
    if (enableAssistantContentIdentityIndex != null) "enable_assistant_content_identity_index": enableAssistantContentIdentityIndex!,
    if (enableHelperRead != null) "enable_helper_read": enableHelperRead!,
    if (enableShareToCircle != null) "enable_share_to_circle": enableShareToCircle!,
    if (showViewCount != null) "show_view_count": showViewCount!,
  };
}

final class ContentAppConfigGrayRelease {
  const ContentAppConfigGrayRelease({
    required this.experimentBucket,
    required this.currentStage,
    required this.canaryMatrix,
  });

  final String experimentBucket;
  final String currentStage;
  final List<ContentAppConfigCanaryStage> canaryMatrix;

  factory ContentAppConfigGrayRelease.fromWire(Map<String, Object?> map, [String path = "ContentAppConfigGrayRelease"]) {
    _rejectUnknownFields(map, const <String>{"experiment_bucket", "current_stage", "canary_matrix"}, path);
    return ContentAppConfigGrayRelease(
      experimentBucket: _requiredString(map["experiment_bucket"], '$path.experiment_bucket'),
      currentStage: _requiredString(map["current_stage"], '$path.current_stage'),
      canaryMatrix: List<ContentAppConfigCanaryStage>.unmodifiable(_requiredList(map["canary_matrix"], '$path.canary_matrix').asMap().entries.map((entry) => ContentAppConfigCanaryStage.fromWire(_requiredObject(entry.value, '$path.canary_matrix' + '[${entry.key}]'), '$path.canary_matrix' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "experiment_bucket": experimentBucket,
    "current_stage": currentStage,
    "canary_matrix": canaryMatrix.map((value) => value.toWire()).toList(growable: false),
  };
}

final class ContentAppConfigHomeChannel {
  const ContentAppConfigHomeChannel({
    required this.id,
    this.labelKey,
    this.template,
    this.layoutTemplate,
    this.phoneColumns,
    this.supportsFullSpanModules,
    this.intersectionModulePolicy,
    this.contentCardPolicy,
    this.feedQuery,
    this.moodCopyKey,
    this.order,
  });

  final String id;
  final String? labelKey;
  final String? template;
  final String? layoutTemplate;
  final int? phoneColumns;
  final bool? supportsFullSpanModules;
  final String? intersectionModulePolicy;
  final String? contentCardPolicy;
  final Map<String, Object?>? feedQuery;
  final String? moodCopyKey;
  final int? order;

  factory ContentAppConfigHomeChannel.fromWire(Map<String, Object?> map, [String path = "ContentAppConfigHomeChannel"]) {
    _rejectUnknownFields(map, const <String>{"id", "label_key", "template", "layout_template", "phone_columns", "supports_full_span_modules", "intersection_module_policy", "content_card_policy", "feed_query", "mood_copy_key", "order"}, path);
    return ContentAppConfigHomeChannel(
      id: _requiredString(map["id"], '$path.id'),
      labelKey: map["label_key"] == null ? null : _requiredString(map["label_key"], '$path.label_key'),
      template: map["template"] == null ? null : _requiredString(map["template"], '$path.template'),
      layoutTemplate: map["layout_template"] == null ? null : _requiredString(map["layout_template"], '$path.layout_template'),
      phoneColumns: map["phone_columns"] == null ? null : _requiredInt(map["phone_columns"], '$path.phone_columns'),
      supportsFullSpanModules: map["supports_full_span_modules"] == null ? null : _requiredBool(map["supports_full_span_modules"], '$path.supports_full_span_modules'),
      intersectionModulePolicy: map["intersection_module_policy"] == null ? null : _requiredString(map["intersection_module_policy"], '$path.intersection_module_policy'),
      contentCardPolicy: map["content_card_policy"] == null ? null : _requiredString(map["content_card_policy"], '$path.content_card_policy'),
      feedQuery: map["feed_query"] == null ? null : _requiredObject(map["feed_query"], '$path.feed_query'),
      moodCopyKey: map["mood_copy_key"] == null ? null : _requiredString(map["mood_copy_key"], '$path.mood_copy_key'),
      order: map["order"] == null ? null : _requiredInt(map["order"], '$path.order'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "id": id,
    if (labelKey != null) "label_key": labelKey!,
    if (template != null) "template": template!,
    if (layoutTemplate != null) "layout_template": layoutTemplate!,
    if (phoneColumns != null) "phone_columns": phoneColumns!,
    if (supportsFullSpanModules != null) "supports_full_span_modules": supportsFullSpanModules!,
    if (intersectionModulePolicy != null) "intersection_module_policy": intersectionModulePolicy!,
    if (contentCardPolicy != null) "content_card_policy": contentCardPolicy!,
    if (feedQuery != null) "feed_query": feedQuery!,
    if (moodCopyKey != null) "mood_copy_key": moodCopyKey!,
    if (order != null) "order": order!,
  };
}

final class ContentAppConfigIntersection {
  const ContentAppConfigIntersection({
    this.inlineExpandCount,
    this.maxCandidateWindow,
  });

  final int? inlineExpandCount;
  final int? maxCandidateWindow;

  factory ContentAppConfigIntersection.fromWire(Map<String, Object?> map, [String path = "ContentAppConfigIntersection"]) {
    _rejectUnknownFields(map, const <String>{"inline_expand_count", "max_candidate_window"}, path);
    return ContentAppConfigIntersection(
      inlineExpandCount: map["inline_expand_count"] == null ? null : _requiredPositiveInt(map["inline_expand_count"], '$path.inline_expand_count'),
      maxCandidateWindow: map["max_candidate_window"] == null ? null : _requiredPositiveInt(map["max_candidate_window"], '$path.max_candidate_window'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (inlineExpandCount != null) "inline_expand_count": inlineExpandCount!,
    if (maxCandidateWindow != null) "max_candidate_window": maxCandidateWindow!,
  };
}

final class ContentBehaviorReportReceipt {
  const ContentBehaviorReportReceipt({
    required this.acceptedCount,
    required this.replayedCount,
  });

  final int acceptedCount;
  final int replayedCount;

  factory ContentBehaviorReportReceipt.fromWire(Map<String, Object?> map, [String path = "ContentBehaviorReportReceipt"]) {
    _rejectUnknownFields(map, const <String>{"acceptedCount", "replayedCount"}, path);
    return ContentBehaviorReportReceipt(
      acceptedCount: _requiredInt(map["acceptedCount"], '$path.acceptedCount'),
      replayedCount: _requiredInt(map["replayedCount"], '$path.replayedCount'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "acceptedCount": acceptedCount,
    "replayedCount": replayedCount,
  };
}

final class ContentCommentReactionCommandResult {
  const ContentCommentReactionCommandResult({
    required this.reactionId,
    required this.version,
    required this.reaction,
    required this.changed,
    required this.replayed,
    required this.likeCount,
    required this.dislikeCount,
  });

  final String reactionId;
  final int version;
  final CommentReactionType reaction;
  final bool changed;
  final bool replayed;
  final int likeCount;
  final int dislikeCount;

  factory ContentCommentReactionCommandResult.fromWire(Map<String, Object?> map, [String path = "ContentCommentReactionCommandResult"]) {
    _rejectUnknownFields(map, const <String>{"reactionId", "version", "reaction", "changed", "replayed", "likeCount", "dislikeCount"}, path);
    return ContentCommentReactionCommandResult(
      reactionId: _requiredString(map["reactionId"], '$path.reactionId'),
      version: _requiredPositiveInt(map["version"], '$path.version'),
      reaction: CommentReactionType.fromWire(map["reaction"], '$path.reaction'),
      changed: _requiredBool(map["changed"], '$path.changed'),
      replayed: _requiredBool(map["replayed"], '$path.replayed'),
      likeCount: _requiredInt(map["likeCount"], '$path.likeCount'),
      dislikeCount: _requiredInt(map["dislikeCount"], '$path.dislikeCount'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "reactionId": reactionId,
    "version": version,
    "reaction": reaction.wireName,
    "changed": changed,
    "replayed": replayed,
    "likeCount": likeCount,
    "dislikeCount": dislikeCount,
  };
}

final class ContentDiscoveryFeedPageSlice {
  const ContentDiscoveryFeedPageSlice({
    required this.items,
    required this.outcome,
    this.emptyReason,
    this.nextCursor,
    this.previousCursor,
    this.paginationExpiresAt,
    required this.feedRequestId,
    this.policyDigest,
    required this.objectCards,
    this.releaseId,
    this.manifestDigest,
  });

  final List<ContentPostProjection> items;
  final ContentFeedOutcome outcome;
  final ContentFeedEmptyReason? emptyReason;
  final String? nextCursor;
  final String? previousCursor;
  final DateTime? paginationExpiresAt;
  final String feedRequestId;
  final String? policyDigest;
  final List<FeedObjectCard> objectCards;
  final String? releaseId;
  final String? manifestDigest;

  factory ContentDiscoveryFeedPageSlice.fromWire(Map<String, Object?> map, [String path = "ContentDiscoveryFeedPageSlice"]) {
    _rejectUnknownFields(map, const <String>{"items", "outcome", "emptyReason", "nextCursor", "previousCursor", "paginationExpiresAt", "feedRequestId", "policyDigest", "objectCards", "releaseId", "manifestDigest"}, path);
    return ContentDiscoveryFeedPageSlice(
      items: List<ContentPostProjection>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => ContentPostProjection.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      outcome: ContentFeedOutcome.fromWire(map["outcome"], '$path.outcome'),
      emptyReason: map["emptyReason"] == null ? null : ContentFeedEmptyReason.fromWire(map["emptyReason"], '$path.emptyReason'),
      nextCursor: map["nextCursor"] == null ? null : _requiredString(map["nextCursor"], '$path.nextCursor'),
      previousCursor: map["previousCursor"] == null ? null : _requiredString(map["previousCursor"], '$path.previousCursor'),
      paginationExpiresAt: map["paginationExpiresAt"] == null ? null : _requiredTimestamp(map["paginationExpiresAt"], '$path.paginationExpiresAt'),
      feedRequestId: _requiredString(map["feedRequestId"], '$path.feedRequestId'),
      policyDigest: map["policyDigest"] == null ? null : _requiredString(map["policyDigest"], '$path.policyDigest'),
      objectCards: List<FeedObjectCard>.unmodifiable(_requiredList(map["objectCards"], '$path.objectCards').asMap().entries.map((entry) => FeedObjectCard.fromWire(_requiredObject(entry.value, '$path.objectCards' + '[${entry.key}]'), '$path.objectCards' + '[${entry.key}]'))),
      releaseId: map["releaseId"] == null ? null : _requiredString(map["releaseId"], '$path.releaseId'),
      manifestDigest: map["manifestDigest"] == null ? null : _requiredString(map["manifestDigest"], '$path.manifestDigest'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
    "outcome": outcome.wireName,
    if (emptyReason != null) "emptyReason": emptyReason!.wireName,
    if (nextCursor != null) "nextCursor": nextCursor!,
    if (previousCursor != null) "previousCursor": previousCursor!,
    if (paginationExpiresAt != null) "paginationExpiresAt": paginationExpiresAt!.toUtc().toIso8601String(),
    "feedRequestId": feedRequestId,
    if (policyDigest != null) "policyDigest": policyDigest!,
    "objectCards": objectCards.map((value) => value.toWire()).toList(growable: false),
    if (releaseId != null) "releaseId": releaseId!,
    if (manifestDigest != null) "manifestDigest": manifestDigest!,
  };
}

final class ContentFootprintEntry {
  const ContentFootprintEntry({
    required this.postId,
    required this.action,
    required this.occurredAt,
    this.post,
  });

  final String postId;
  final String action;
  final DateTime occurredAt;
  final ContentPostProjection? post;

  factory ContentFootprintEntry.fromWire(Map<String, Object?> map, [String path = "ContentFootprintEntry"]) {
    _rejectUnknownFields(map, const <String>{"postId", "action", "occurredAt", "post"}, path);
    return ContentFootprintEntry(
      postId: _requiredString(map["postId"], '$path.postId'),
      action: _requiredString(map["action"], '$path.action'),
      occurredAt: _requiredTimestamp(map["occurredAt"], '$path.occurredAt'),
      post: map["post"] == null ? null : ContentPostProjection.fromWire(_requiredObject(map["post"], '$path.post'), '$path.post'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "postId": postId,
    "action": action,
    "occurredAt": occurredAt.toUtc().toIso8601String(),
    if (post != null) "post": post!.toWire(),
  };
}

final class ContentFootprintPageSlice {
  const ContentFootprintPageSlice({
    required this.items,
    this.nextCursor,
  });

  final List<ContentFootprintEntry> items;
  final String? nextCursor;

  factory ContentFootprintPageSlice.fromWire(Map<String, Object?> map, [String path = "ContentFootprintPageSlice"]) {
    _rejectUnknownFields(map, const <String>{"items", "nextCursor"}, path);
    return ContentFootprintPageSlice(
      items: List<ContentFootprintEntry>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => ContentFootprintEntry.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      nextCursor: map["nextCursor"] == null ? null : _requiredString(map["nextCursor"], '$path.nextCursor'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
    if (nextCursor != null) "nextCursor": nextCursor!,
  };
}

final class ContentPostDetailSlice {
  const ContentPostDetailSlice({
    required this.postId,
    required this.contentType,
    this.contentIdentity,
    this.assistantUsePolicy,
    this.authorId,
    this.authorDisplayName,
    this.authorAvatarUrl,
    this.title,
    this.body,
    this.summary,
    this.tagRefs,
    this.entityRefs,
    this.semanticMentions,
    this.mediaAssetIds,
    this.mediaUrls,
    this.mediaItems,
    this.coverUrl,
    this.thumbnailUrl,
    this.videoUrl,
    this.sourceAttribution,
    this.width,
    this.height,
    this.durationMs,
    this.articleMarkdown,
    this.markdownDialect,
    this.articleMarkdownDigest,
    this.articleAssetManifest,
    this.articleRenderProfile,
    this.contentVertical,
    this.entityMentions,
    this.articleTemplate,
    this.articleFontPreset,
    this.coverStrategy,
    this.coverFrameTimeMs,
    this.location,
    this.locationName,
    this.geoTagRef,
    this.visitedAt,
    this.primaryHomepageId,
    this.canonicalEntityId,
    this.primaryHomepageType,
    this.primaryHomepageSnapshot,
    this.gatheringRef,
    required this.status,
    required this.visibility,
    required this.likeCount,
    required this.commentCount,
    required this.shareCount,
    required this.viewCount,
    this.viewerLiked,
    required this.createdAt,
    required this.updatedAt,
    this.publishedAt,
  });

  final String postId;
  final String contentType;
  final String? contentIdentity;
  final AssistantUsePolicy? assistantUsePolicy;
  final String? authorId;
  final String? authorDisplayName;
  final String? authorAvatarUrl;
  final String? title;
  final String? body;
  final String? summary;
  final List<String>? tagRefs;
  final List<String>? entityRefs;
  final List<PostSemanticMention>? semanticMentions;
  final List<String>? mediaAssetIds;
  final List<String>? mediaUrls;
  final List<PostMediaItem>? mediaItems;
  final String? coverUrl;
  final String? thumbnailUrl;
  final String? videoUrl;
  final SourceAttribution? sourceAttribution;
  final int? width;
  final int? height;
  final int? durationMs;
  final String? articleMarkdown;
  final String? markdownDialect;
  final String? articleMarkdownDigest;
  final PostArticleAssetManifest? articleAssetManifest;
  final PostArticleRenderProfile? articleRenderProfile;
  final String? contentVertical;
  final List<PostEntityMention>? entityMentions;
  final String? articleTemplate;
  final String? articleFontPreset;
  final String? coverStrategy;
  final int? coverFrameTimeMs;
  final GeoPoint? location;
  final String? locationName;
  final String? geoTagRef;
  final DateTime? visitedAt;
  final String? primaryHomepageId;
  final String? canonicalEntityId;
  final String? primaryHomepageType;
  final PostHomepageSnapshot? primaryHomepageSnapshot;
  final String? gatheringRef;
  final String status;
  final String visibility;
  final int likeCount;
  final int commentCount;
  final int shareCount;
  final int viewCount;
  final bool? viewerLiked;
  final DateTime createdAt;
  final DateTime updatedAt;
  final DateTime? publishedAt;

  factory ContentPostDetailSlice.fromWire(Map<String, Object?> map, [String path = "ContentPostDetailSlice"]) {
    _rejectUnknownFields(map, const <String>{"postId", "contentType", "contentIdentity", "assistantUsePolicy", "authorId", "authorDisplayName", "authorAvatarUrl", "title", "body", "summary", "tagRefs", "entityRefs", "semanticMentions", "mediaAssetIds", "mediaUrls", "mediaItems", "coverUrl", "thumbnailUrl", "videoUrl", "sourceAttribution", "width", "height", "durationMs", "articleMarkdown", "markdownDialect", "articleMarkdownDigest", "articleAssetManifest", "articleRenderProfile", "contentVertical", "entityMentions", "articleTemplate", "articleFontPreset", "coverStrategy", "coverFrameTimeMs", "location", "locationName", "geoTagRef", "visitedAt", "primaryHomepageId", "canonicalEntityId", "primaryHomepageType", "primaryHomepageSnapshot", "gatheringRef", "status", "visibility", "likeCount", "commentCount", "shareCount", "viewCount", "viewerLiked", "createdAt", "updatedAt", "publishedAt"}, path);
    return ContentPostDetailSlice(
      postId: _requiredString(map["postId"], '$path.postId'),
      contentType: _requiredString(map["contentType"], '$path.contentType'),
      contentIdentity: map["contentIdentity"] == null ? null : _requiredString(map["contentIdentity"], '$path.contentIdentity'),
      assistantUsePolicy: map["assistantUsePolicy"] == null ? null : AssistantUsePolicy.fromWire(map["assistantUsePolicy"], '$path.assistantUsePolicy'),
      authorId: map["authorId"] == null ? null : _requiredString(map["authorId"], '$path.authorId'),
      authorDisplayName: map["authorDisplayName"] == null ? null : _requiredString(map["authorDisplayName"], '$path.authorDisplayName'),
      authorAvatarUrl: map["authorAvatarUrl"] == null ? null : _requiredString(map["authorAvatarUrl"], '$path.authorAvatarUrl'),
      title: map["title"] == null ? null : _requiredString(map["title"], '$path.title'),
      body: map["body"] == null ? null : _requiredString(map["body"], '$path.body'),
      summary: map["summary"] == null ? null : _requiredString(map["summary"], '$path.summary'),
      tagRefs: map["tagRefs"] == null ? null : List<String>.unmodifiable(_requiredList(map["tagRefs"], '$path.tagRefs').asMap().entries.map((entry) => _requiredString(entry.value, '$path.tagRefs' + '[${entry.key}]'))),
      entityRefs: map["entityRefs"] == null ? null : List<String>.unmodifiable(_requiredList(map["entityRefs"], '$path.entityRefs').asMap().entries.map((entry) => _requiredString(entry.value, '$path.entityRefs' + '[${entry.key}]'))),
      semanticMentions: map["semanticMentions"] == null ? null : List<PostSemanticMention>.unmodifiable(_requiredList(map["semanticMentions"], '$path.semanticMentions').asMap().entries.map((entry) => PostSemanticMention.fromWire(_requiredObject(entry.value, '$path.semanticMentions' + '[${entry.key}]'), '$path.semanticMentions' + '[${entry.key}]'))),
      mediaAssetIds: map["mediaAssetIds"] == null ? null : List<String>.unmodifiable(_requiredList(map["mediaAssetIds"], '$path.mediaAssetIds').asMap().entries.map((entry) => _requiredString(entry.value, '$path.mediaAssetIds' + '[${entry.key}]'))),
      mediaUrls: map["mediaUrls"] == null ? null : List<String>.unmodifiable(_requiredList(map["mediaUrls"], '$path.mediaUrls').asMap().entries.map((entry) => _requiredString(entry.value, '$path.mediaUrls' + '[${entry.key}]'))),
      mediaItems: map["mediaItems"] == null ? null : List<PostMediaItem>.unmodifiable(_requiredList(map["mediaItems"], '$path.mediaItems').asMap().entries.map((entry) => PostMediaItem.fromWire(_requiredObject(entry.value, '$path.mediaItems' + '[${entry.key}]'), '$path.mediaItems' + '[${entry.key}]'))),
      coverUrl: map["coverUrl"] == null ? null : _requiredString(map["coverUrl"], '$path.coverUrl'),
      thumbnailUrl: map["thumbnailUrl"] == null ? null : _requiredString(map["thumbnailUrl"], '$path.thumbnailUrl'),
      videoUrl: map["videoUrl"] == null ? null : _requiredString(map["videoUrl"], '$path.videoUrl'),
      sourceAttribution: map["sourceAttribution"] == null ? null : SourceAttribution.fromWire(_requiredObject(map["sourceAttribution"], '$path.sourceAttribution'), '$path.sourceAttribution'),
      width: map["width"] == null ? null : _requiredInt(map["width"], '$path.width'),
      height: map["height"] == null ? null : _requiredInt(map["height"], '$path.height'),
      durationMs: map["durationMs"] == null ? null : _requiredInt(map["durationMs"], '$path.durationMs'),
      articleMarkdown: map["articleMarkdown"] == null ? null : _requiredString(map["articleMarkdown"], '$path.articleMarkdown'),
      markdownDialect: map["markdownDialect"] == null ? null : _requiredString(map["markdownDialect"], '$path.markdownDialect'),
      articleMarkdownDigest: map["articleMarkdownDigest"] == null ? null : _requiredString(map["articleMarkdownDigest"], '$path.articleMarkdownDigest'),
      articleAssetManifest: map["articleAssetManifest"] == null ? null : PostArticleAssetManifest.fromWire(_requiredObject(map["articleAssetManifest"], '$path.articleAssetManifest'), '$path.articleAssetManifest'),
      articleRenderProfile: map["articleRenderProfile"] == null ? null : PostArticleRenderProfile.fromWire(_requiredObject(map["articleRenderProfile"], '$path.articleRenderProfile'), '$path.articleRenderProfile'),
      contentVertical: map["contentVertical"] == null ? null : _requiredString(map["contentVertical"], '$path.contentVertical'),
      entityMentions: map["entityMentions"] == null ? null : List<PostEntityMention>.unmodifiable(_requiredList(map["entityMentions"], '$path.entityMentions').asMap().entries.map((entry) => PostEntityMention.fromWire(_requiredObject(entry.value, '$path.entityMentions' + '[${entry.key}]'), '$path.entityMentions' + '[${entry.key}]'))),
      articleTemplate: map["articleTemplate"] == null ? null : _requiredString(map["articleTemplate"], '$path.articleTemplate'),
      articleFontPreset: map["articleFontPreset"] == null ? null : _requiredString(map["articleFontPreset"], '$path.articleFontPreset'),
      coverStrategy: map["coverStrategy"] == null ? null : _requiredString(map["coverStrategy"], '$path.coverStrategy'),
      coverFrameTimeMs: map["coverFrameTimeMs"] == null ? null : _requiredInt(map["coverFrameTimeMs"], '$path.coverFrameTimeMs'),
      location: map["location"] == null ? null : GeoPoint.fromWire(_requiredObject(map["location"], '$path.location'), '$path.location'),
      locationName: map["locationName"] == null ? null : _requiredString(map["locationName"], '$path.locationName'),
      geoTagRef: map["geoTagRef"] == null ? null : _requiredString(map["geoTagRef"], '$path.geoTagRef'),
      visitedAt: map["visitedAt"] == null ? null : _requiredTimestamp(map["visitedAt"], '$path.visitedAt'),
      primaryHomepageId: map["primaryHomepageId"] == null ? null : _requiredString(map["primaryHomepageId"], '$path.primaryHomepageId'),
      canonicalEntityId: map["canonicalEntityId"] == null ? null : _requiredString(map["canonicalEntityId"], '$path.canonicalEntityId'),
      primaryHomepageType: map["primaryHomepageType"] == null ? null : _requiredString(map["primaryHomepageType"], '$path.primaryHomepageType'),
      primaryHomepageSnapshot: map["primaryHomepageSnapshot"] == null ? null : PostHomepageSnapshot.fromWire(_requiredObject(map["primaryHomepageSnapshot"], '$path.primaryHomepageSnapshot'), '$path.primaryHomepageSnapshot'),
      gatheringRef: map["gatheringRef"] == null ? null : _requiredString(map["gatheringRef"], '$path.gatheringRef'),
      status: _requiredString(map["status"], '$path.status'),
      visibility: _requiredString(map["visibility"], '$path.visibility'),
      likeCount: _requiredInt(map["likeCount"], '$path.likeCount'),
      commentCount: _requiredInt(map["commentCount"], '$path.commentCount'),
      shareCount: _requiredInt(map["shareCount"], '$path.shareCount'),
      viewCount: _requiredInt(map["viewCount"], '$path.viewCount'),
      viewerLiked: map["viewerLiked"] == null ? null : _requiredBool(map["viewerLiked"], '$path.viewerLiked'),
      createdAt: _requiredTimestamp(map["createdAt"], '$path.createdAt'),
      updatedAt: _requiredTimestamp(map["updatedAt"], '$path.updatedAt'),
      publishedAt: map["publishedAt"] == null ? null : _requiredTimestamp(map["publishedAt"], '$path.publishedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "postId": postId,
    "contentType": contentType,
    if (contentIdentity != null) "contentIdentity": contentIdentity!,
    if (assistantUsePolicy != null) "assistantUsePolicy": assistantUsePolicy!.wireName,
    if (authorId != null) "authorId": authorId!,
    if (authorDisplayName != null) "authorDisplayName": authorDisplayName!,
    if (authorAvatarUrl != null) "authorAvatarUrl": authorAvatarUrl!,
    if (title != null) "title": title!,
    if (body != null) "body": body!,
    if (summary != null) "summary": summary!,
    if (tagRefs != null) "tagRefs": tagRefs!.map((value) => value).toList(growable: false),
    if (entityRefs != null) "entityRefs": entityRefs!.map((value) => value).toList(growable: false),
    if (semanticMentions != null) "semanticMentions": semanticMentions!.map((value) => value.toWire()).toList(growable: false),
    if (mediaAssetIds != null) "mediaAssetIds": mediaAssetIds!.map((value) => value).toList(growable: false),
    if (mediaUrls != null) "mediaUrls": mediaUrls!.map((value) => value).toList(growable: false),
    if (mediaItems != null) "mediaItems": mediaItems!.map((value) => value.toWire()).toList(growable: false),
    if (coverUrl != null) "coverUrl": coverUrl!,
    if (thumbnailUrl != null) "thumbnailUrl": thumbnailUrl!,
    if (videoUrl != null) "videoUrl": videoUrl!,
    if (sourceAttribution != null) "sourceAttribution": sourceAttribution!.toWire(),
    if (width != null) "width": width!,
    if (height != null) "height": height!,
    if (durationMs != null) "durationMs": durationMs!,
    if (articleMarkdown != null) "articleMarkdown": articleMarkdown!,
    if (markdownDialect != null) "markdownDialect": markdownDialect!,
    if (articleMarkdownDigest != null) "articleMarkdownDigest": articleMarkdownDigest!,
    if (articleAssetManifest != null) "articleAssetManifest": articleAssetManifest!.toWire(),
    if (articleRenderProfile != null) "articleRenderProfile": articleRenderProfile!.toWire(),
    if (contentVertical != null) "contentVertical": contentVertical!,
    if (entityMentions != null) "entityMentions": entityMentions!.map((value) => value.toWire()).toList(growable: false),
    if (articleTemplate != null) "articleTemplate": articleTemplate!,
    if (articleFontPreset != null) "articleFontPreset": articleFontPreset!,
    if (coverStrategy != null) "coverStrategy": coverStrategy!,
    if (coverFrameTimeMs != null) "coverFrameTimeMs": coverFrameTimeMs!,
    if (location != null) "location": location!.toWire(),
    if (locationName != null) "locationName": locationName!,
    if (geoTagRef != null) "geoTagRef": geoTagRef!,
    if (visitedAt != null) "visitedAt": visitedAt!.toUtc().toIso8601String(),
    if (primaryHomepageId != null) "primaryHomepageId": primaryHomepageId!,
    if (canonicalEntityId != null) "canonicalEntityId": canonicalEntityId!,
    if (primaryHomepageType != null) "primaryHomepageType": primaryHomepageType!,
    if (primaryHomepageSnapshot != null) "primaryHomepageSnapshot": primaryHomepageSnapshot!.toWire(),
    if (gatheringRef != null) "gatheringRef": gatheringRef!,
    "status": status,
    "visibility": visibility,
    "likeCount": likeCount,
    "commentCount": commentCount,
    "shareCount": shareCount,
    "viewCount": viewCount,
    if (viewerLiked != null) "viewerLiked": viewerLiked!,
    "createdAt": createdAt.toUtc().toIso8601String(),
    "updatedAt": updatedAt.toUtc().toIso8601String(),
    if (publishedAt != null) "publishedAt": publishedAt!.toUtc().toIso8601String(),
  };
}

final class ContentPostProjection {
  const ContentPostProjection({
    required this.postId,
    required this.contentType,
    this.contentIdentity,
    this.assistantUsePolicy,
    this.authorId,
    this.authorDisplayName,
    this.authorAvatarUrl,
    this.authorBackgroundUrl,
    this.authorRoleLabel,
    this.authorIdentityTags,
    this.authorVerified,
    this.title,
    this.body,
    this.summary,
    this.coverUrl,
    this.articleTemplate,
    this.articleFontPreset,
    this.mediaUrls,
    this.videoUrl,
    this.mediaAssetId,
    this.mediaAssetVersion,
    this.hlsCmafMasterManifestUrl,
    this.hlsCmafDescriptorVersion,
    this.thumbnailUrl,
    this.width,
    this.height,
    this.durationMs,
    required this.likeCount,
    required this.commentCount,
    required this.shareCount,
    this.viewerLiked,
    this.primaryHomepageId,
    this.primaryHomepageType,
    this.gatheringRef,
    this.createdAt,
    this.updatedAt,
    this.publishedAt,
    this.contentVertical,
    this.recallPath,
    this.supplySource,
    this.intersectionReasons,
  });

  final String postId;
  final String contentType;
  final String? contentIdentity;
  final AssistantUsePolicy? assistantUsePolicy;
  final String? authorId;
  final String? authorDisplayName;
  final String? authorAvatarUrl;
  final String? authorBackgroundUrl;
  final String? authorRoleLabel;
  final List<String>? authorIdentityTags;
  final bool? authorVerified;
  final String? title;
  final String? body;
  final String? summary;
  final String? coverUrl;
  final String? articleTemplate;
  final String? articleFontPreset;
  final List<String>? mediaUrls;
  final String? videoUrl;
  final String? mediaAssetId;
  final int? mediaAssetVersion;
  final String? hlsCmafMasterManifestUrl;
  final int? hlsCmafDescriptorVersion;
  final String? thumbnailUrl;
  final int? width;
  final int? height;
  final int? durationMs;
  final int likeCount;
  final int commentCount;
  final int shareCount;
  final bool? viewerLiked;
  final String? primaryHomepageId;
  final String? primaryHomepageType;
  final String? gatheringRef;
  final DateTime? createdAt;
  final DateTime? updatedAt;
  final DateTime? publishedAt;
  final String? contentVertical;
  final String? recallPath;
  final String? supplySource;
  final List<IntersectionReason>? intersectionReasons;

  factory ContentPostProjection.fromWire(Map<String, Object?> map, [String path = "ContentPostProjection"]) {
    _rejectUnknownFields(map, const <String>{"postId", "contentType", "contentIdentity", "assistantUsePolicy", "authorId", "authorDisplayName", "authorAvatarUrl", "authorBackgroundUrl", "authorRoleLabel", "authorIdentityTags", "authorVerified", "title", "body", "summary", "coverUrl", "articleTemplate", "articleFontPreset", "mediaUrls", "videoUrl", "mediaAssetId", "mediaAssetVersion", "hlsCmafMasterManifestUrl", "hlsCmafDescriptorVersion", "thumbnailUrl", "width", "height", "durationMs", "likeCount", "commentCount", "shareCount", "viewerLiked", "primaryHomepageId", "primaryHomepageType", "gatheringRef", "createdAt", "updatedAt", "publishedAt", "contentVertical", "recallPath", "supplySource", "intersectionReasons"}, path);
    return ContentPostProjection(
      postId: _requiredString(map["postId"], '$path.postId'),
      contentType: _requiredString(map["contentType"], '$path.contentType'),
      contentIdentity: map["contentIdentity"] == null ? null : _requiredString(map["contentIdentity"], '$path.contentIdentity'),
      assistantUsePolicy: map["assistantUsePolicy"] == null ? null : AssistantUsePolicy.fromWire(map["assistantUsePolicy"], '$path.assistantUsePolicy'),
      authorId: map["authorId"] == null ? null : _requiredString(map["authorId"], '$path.authorId'),
      authorDisplayName: map["authorDisplayName"] == null ? null : _requiredString(map["authorDisplayName"], '$path.authorDisplayName'),
      authorAvatarUrl: map["authorAvatarUrl"] == null ? null : _requiredString(map["authorAvatarUrl"], '$path.authorAvatarUrl'),
      authorBackgroundUrl: map["authorBackgroundUrl"] == null ? null : _requiredString(map["authorBackgroundUrl"], '$path.authorBackgroundUrl'),
      authorRoleLabel: map["authorRoleLabel"] == null ? null : _requiredString(map["authorRoleLabel"], '$path.authorRoleLabel'),
      authorIdentityTags: map["authorIdentityTags"] == null ? null : List<String>.unmodifiable(_requiredList(map["authorIdentityTags"], '$path.authorIdentityTags').asMap().entries.map((entry) => _requiredString(entry.value, '$path.authorIdentityTags' + '[${entry.key}]'))),
      authorVerified: map["authorVerified"] == null ? null : _requiredBool(map["authorVerified"], '$path.authorVerified'),
      title: map["title"] == null ? null : _requiredString(map["title"], '$path.title'),
      body: map["body"] == null ? null : _requiredString(map["body"], '$path.body'),
      summary: map["summary"] == null ? null : _requiredString(map["summary"], '$path.summary'),
      coverUrl: map["coverUrl"] == null ? null : _requiredString(map["coverUrl"], '$path.coverUrl'),
      articleTemplate: map["articleTemplate"] == null ? null : _requiredString(map["articleTemplate"], '$path.articleTemplate'),
      articleFontPreset: map["articleFontPreset"] == null ? null : _requiredString(map["articleFontPreset"], '$path.articleFontPreset'),
      mediaUrls: map["mediaUrls"] == null ? null : List<String>.unmodifiable(_requiredList(map["mediaUrls"], '$path.mediaUrls').asMap().entries.map((entry) => _requiredString(entry.value, '$path.mediaUrls' + '[${entry.key}]'))),
      videoUrl: map["videoUrl"] == null ? null : _requiredString(map["videoUrl"], '$path.videoUrl'),
      mediaAssetId: map["mediaAssetId"] == null ? null : _requiredString(map["mediaAssetId"], '$path.mediaAssetId'),
      mediaAssetVersion: map["mediaAssetVersion"] == null ? null : _requiredInt(map["mediaAssetVersion"], '$path.mediaAssetVersion'),
      hlsCmafMasterManifestUrl: map["hlsCmafMasterManifestUrl"] == null ? null : _requiredString(map["hlsCmafMasterManifestUrl"], '$path.hlsCmafMasterManifestUrl'),
      hlsCmafDescriptorVersion: map["hlsCmafDescriptorVersion"] == null ? null : _requiredInt(map["hlsCmafDescriptorVersion"], '$path.hlsCmafDescriptorVersion'),
      thumbnailUrl: map["thumbnailUrl"] == null ? null : _requiredString(map["thumbnailUrl"], '$path.thumbnailUrl'),
      width: map["width"] == null ? null : _requiredInt(map["width"], '$path.width'),
      height: map["height"] == null ? null : _requiredInt(map["height"], '$path.height'),
      durationMs: map["durationMs"] == null ? null : _requiredInt(map["durationMs"], '$path.durationMs'),
      likeCount: _requiredInt(map["likeCount"], '$path.likeCount'),
      commentCount: _requiredInt(map["commentCount"], '$path.commentCount'),
      shareCount: _requiredInt(map["shareCount"], '$path.shareCount'),
      viewerLiked: map["viewerLiked"] == null ? null : _requiredBool(map["viewerLiked"], '$path.viewerLiked'),
      primaryHomepageId: map["primaryHomepageId"] == null ? null : _requiredString(map["primaryHomepageId"], '$path.primaryHomepageId'),
      primaryHomepageType: map["primaryHomepageType"] == null ? null : _requiredString(map["primaryHomepageType"], '$path.primaryHomepageType'),
      gatheringRef: map["gatheringRef"] == null ? null : _requiredString(map["gatheringRef"], '$path.gatheringRef'),
      createdAt: map["createdAt"] == null ? null : _requiredTimestamp(map["createdAt"], '$path.createdAt'),
      updatedAt: map["updatedAt"] == null ? null : _requiredTimestamp(map["updatedAt"], '$path.updatedAt'),
      publishedAt: map["publishedAt"] == null ? null : _requiredTimestamp(map["publishedAt"], '$path.publishedAt'),
      contentVertical: map["contentVertical"] == null ? null : _requiredString(map["contentVertical"], '$path.contentVertical'),
      recallPath: map["recallPath"] == null ? null : _requiredString(map["recallPath"], '$path.recallPath'),
      supplySource: map["supplySource"] == null ? null : _requiredString(map["supplySource"], '$path.supplySource'),
      intersectionReasons: map["intersectionReasons"] == null ? null : List<IntersectionReason>.unmodifiable(_requiredList(map["intersectionReasons"], '$path.intersectionReasons').asMap().entries.map((entry) => IntersectionReason.fromWire(_requiredObject(entry.value, '$path.intersectionReasons' + '[${entry.key}]'), '$path.intersectionReasons' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "postId": postId,
    "contentType": contentType,
    if (contentIdentity != null) "contentIdentity": contentIdentity!,
    if (assistantUsePolicy != null) "assistantUsePolicy": assistantUsePolicy!.wireName,
    if (authorId != null) "authorId": authorId!,
    if (authorDisplayName != null) "authorDisplayName": authorDisplayName!,
    if (authorAvatarUrl != null) "authorAvatarUrl": authorAvatarUrl!,
    if (authorBackgroundUrl != null) "authorBackgroundUrl": authorBackgroundUrl!,
    if (authorRoleLabel != null) "authorRoleLabel": authorRoleLabel!,
    if (authorIdentityTags != null) "authorIdentityTags": authorIdentityTags!.map((value) => value).toList(growable: false),
    if (authorVerified != null) "authorVerified": authorVerified!,
    if (title != null) "title": title!,
    if (body != null) "body": body!,
    if (summary != null) "summary": summary!,
    if (coverUrl != null) "coverUrl": coverUrl!,
    if (articleTemplate != null) "articleTemplate": articleTemplate!,
    if (articleFontPreset != null) "articleFontPreset": articleFontPreset!,
    if (mediaUrls != null) "mediaUrls": mediaUrls!.map((value) => value).toList(growable: false),
    if (videoUrl != null) "videoUrl": videoUrl!,
    if (mediaAssetId != null) "mediaAssetId": mediaAssetId!,
    if (mediaAssetVersion != null) "mediaAssetVersion": mediaAssetVersion!,
    if (hlsCmafMasterManifestUrl != null) "hlsCmafMasterManifestUrl": hlsCmafMasterManifestUrl!,
    if (hlsCmafDescriptorVersion != null) "hlsCmafDescriptorVersion": hlsCmafDescriptorVersion!,
    if (thumbnailUrl != null) "thumbnailUrl": thumbnailUrl!,
    if (width != null) "width": width!,
    if (height != null) "height": height!,
    if (durationMs != null) "durationMs": durationMs!,
    "likeCount": likeCount,
    "commentCount": commentCount,
    "shareCount": shareCount,
    if (viewerLiked != null) "viewerLiked": viewerLiked!,
    if (primaryHomepageId != null) "primaryHomepageId": primaryHomepageId!,
    if (primaryHomepageType != null) "primaryHomepageType": primaryHomepageType!,
    if (gatheringRef != null) "gatheringRef": gatheringRef!,
    if (createdAt != null) "createdAt": createdAt!.toUtc().toIso8601String(),
    if (updatedAt != null) "updatedAt": updatedAt!.toUtc().toIso8601String(),
    if (publishedAt != null) "publishedAt": publishedAt!.toUtc().toIso8601String(),
    if (contentVertical != null) "contentVertical": contentVertical!,
    if (recallPath != null) "recallPath": recallPath!,
    if (supplySource != null) "supplySource": supplySource!,
    if (intersectionReasons != null) "intersectionReasons": intersectionReasons!.map((value) => value.toWire()).toList(growable: false),
  };
}

final class ContentReactionCommandResult {
  const ContentReactionCommandResult({
    required this.reactionId,
    required this.postId,
    required this.version,
    required this.liked,
    required this.changed,
    required this.replayed,
  });

  final String reactionId;
  final String postId;
  final int version;
  final bool liked;
  final bool changed;
  final bool replayed;

  factory ContentReactionCommandResult.fromWire(Map<String, Object?> map, [String path = "ContentReactionCommandResult"]) {
    _rejectUnknownFields(map, const <String>{"reactionId", "postId", "version", "liked", "changed", "replayed"}, path);
    return ContentReactionCommandResult(
      reactionId: _requiredString(map["reactionId"], '$path.reactionId'),
      postId: _requiredString(map["postId"], '$path.postId'),
      version: _requiredPositiveInt(map["version"], '$path.version'),
      liked: _requiredBool(map["liked"], '$path.liked'),
      changed: _requiredBool(map["changed"], '$path.changed'),
      replayed: _requiredBool(map["replayed"], '$path.replayed'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "reactionId": reactionId,
    "postId": postId,
    "version": version,
    "liked": liked,
    "changed": changed,
    "replayed": replayed,
  };
}

final class ContentReactionStateSlice {
  const ContentReactionStateSlice({
    required this.found,
    required this.postId,
    required this.liked,
    required this.version,
    this.updatedAt,
  });

  final bool found;
  final String postId;
  final bool liked;
  final int version;
  final DateTime? updatedAt;

  factory ContentReactionStateSlice.fromWire(Map<String, Object?> map, [String path = "ContentReactionStateSlice"]) {
    _rejectUnknownFields(map, const <String>{"found", "postId", "liked", "version", "updatedAt"}, path);
    return ContentReactionStateSlice(
      found: _requiredBool(map["found"], '$path.found'),
      postId: _requiredString(map["postId"], '$path.postId'),
      liked: _requiredBool(map["liked"], '$path.liked'),
      version: _requiredInt(map["version"], '$path.version'),
      updatedAt: map["updatedAt"] == null ? null : _requiredTimestamp(map["updatedAt"], '$path.updatedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "found": found,
    "postId": postId,
    "liked": liked,
    "version": version,
    if (updatedAt != null) "updatedAt": updatedAt!.toUtc().toIso8601String(),
  };
}

final class EntityWishlistState {
  const EntityWishlistState({
    required this.objectId,
    required this.objectKind,
    required this.wishlisted,
  });

  final String objectId;
  final String objectKind;
  final bool wishlisted;

  factory EntityWishlistState.fromWire(Map<String, Object?> map, [String path = "EntityWishlistState"]) {
    _rejectUnknownFields(map, const <String>{"objectId", "objectKind", "wishlisted"}, path);
    return EntityWishlistState(
      objectId: _requiredString(map["objectId"], '$path.objectId'),
      objectKind: _requiredString(map["objectKind"], '$path.objectKind'),
      wishlisted: _requiredBool(map["wishlisted"], '$path.wishlisted'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "objectId": objectId,
    "objectKind": objectKind,
    "wishlisted": wishlisted,
  };
}

final class FeedObjectCard {
  const FeedObjectCard({
    required this.objectKind,
    required this.objectId,
    required this.title,
    this.subtitle,
    this.coverUrl,
    required this.tagRefs,
    this.reasonText,
    this.recallPath,
    required this.anchorIndex,
  });

  final String objectKind;
  final String objectId;
  final String title;
  final String? subtitle;
  final String? coverUrl;
  final List<String> tagRefs;
  final String? reasonText;
  final String? recallPath;
  final int anchorIndex;

  factory FeedObjectCard.fromWire(Map<String, Object?> map, [String path = "FeedObjectCard"]) {
    _rejectUnknownFields(map, const <String>{"objectKind", "objectId", "title", "subtitle", "coverUrl", "tagRefs", "reasonText", "recallPath", "anchorIndex"}, path);
    return FeedObjectCard(
      objectKind: _requiredString(map["objectKind"], '$path.objectKind'),
      objectId: _requiredString(map["objectId"], '$path.objectId'),
      title: _requiredString(map["title"], '$path.title'),
      subtitle: map["subtitle"] == null ? null : _requiredString(map["subtitle"], '$path.subtitle'),
      coverUrl: map["coverUrl"] == null ? null : _requiredString(map["coverUrl"], '$path.coverUrl'),
      tagRefs: List<String>.unmodifiable(_requiredList(map["tagRefs"], '$path.tagRefs').asMap().entries.map((entry) => _requiredString(entry.value, '$path.tagRefs' + '[${entry.key}]'))),
      reasonText: map["reasonText"] == null ? null : _requiredString(map["reasonText"], '$path.reasonText'),
      recallPath: map["recallPath"] == null ? null : _requiredString(map["recallPath"], '$path.recallPath'),
      anchorIndex: _requiredInt(map["anchorIndex"], '$path.anchorIndex'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "objectKind": objectKind,
    "objectId": objectId,
    "title": title,
    if (subtitle != null) "subtitle": subtitle!,
    if (coverUrl != null) "coverUrl": coverUrl!,
    "tagRefs": tagRefs.map((value) => value).toList(growable: false),
    if (reasonText != null) "reasonText": reasonText!,
    if (recallPath != null) "recallPath": recallPath!,
    "anchorIndex": anchorIndex,
  };
}

final class FilterAdjustmentValues {
  const FilterAdjustmentValues({
    required this.lightSense,
    required this.brightness,
    required this.exposure,
    required this.contrast,
    required this.saturation,
    required this.vibrance,
    required this.texture,
    required this.sharpen,
    required this.structure,
    required this.highlight,
    required this.shadow,
    required this.temperature,
    required this.tint,
    required this.grain,
    required this.fade,
  });

  final double lightSense;
  final double brightness;
  final double exposure;
  final double contrast;
  final double saturation;
  final double vibrance;
  final double texture;
  final double sharpen;
  final double structure;
  final double highlight;
  final double shadow;
  final double temperature;
  final double tint;
  final double grain;
  final double fade;

  factory FilterAdjustmentValues.fromWire(Map<String, Object?> map, [String path = "FilterAdjustmentValues"]) {
    _rejectUnknownFields(map, const <String>{"lightSense", "brightness", "exposure", "contrast", "saturation", "vibrance", "texture", "sharpen", "structure", "highlight", "shadow", "temperature", "tint", "grain", "fade"}, path);
    return FilterAdjustmentValues(
      lightSense: _requiredDouble(map["lightSense"], '$path.lightSense'),
      brightness: _requiredDouble(map["brightness"], '$path.brightness'),
      exposure: _requiredDouble(map["exposure"], '$path.exposure'),
      contrast: _requiredDouble(map["contrast"], '$path.contrast'),
      saturation: _requiredDouble(map["saturation"], '$path.saturation'),
      vibrance: _requiredDouble(map["vibrance"], '$path.vibrance'),
      texture: _requiredDouble(map["texture"], '$path.texture'),
      sharpen: _requiredDouble(map["sharpen"], '$path.sharpen'),
      structure: _requiredDouble(map["structure"], '$path.structure'),
      highlight: _requiredDouble(map["highlight"], '$path.highlight'),
      shadow: _requiredDouble(map["shadow"], '$path.shadow'),
      temperature: _requiredDouble(map["temperature"], '$path.temperature'),
      tint: _requiredDouble(map["tint"], '$path.tint'),
      grain: _requiredDouble(map["grain"], '$path.grain'),
      fade: _requiredDouble(map["fade"], '$path.fade'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "lightSense": lightSense,
    "brightness": brightness,
    "exposure": exposure,
    "contrast": contrast,
    "saturation": saturation,
    "vibrance": vibrance,
    "texture": texture,
    "sharpen": sharpen,
    "structure": structure,
    "highlight": highlight,
    "shadow": shadow,
    "temperature": temperature,
    "tint": tint,
    "grain": grain,
    "fade": fade,
  };
}

final class FilterCatalogSlice {
  const FilterCatalogSlice({
    required this.releaseId,
    required this.canonicalDigest,
    required this.status,
    required this.categoryCount,
    required this.presetCount,
    required this.categories,
    required this.presets,
    required this.recommendedFallbackPresetIds,
    required this.importedAt,
    this.activatedAt,
  });

  final String releaseId;
  final String canonicalDigest;
  final FilterCatalogReleaseStatus status;
  final int categoryCount;
  final int presetCount;
  final List<FilterCategoryDefinition> categories;
  final List<FilterPresetDefinition> presets;
  final List<String> recommendedFallbackPresetIds;
  final DateTime importedAt;
  final DateTime? activatedAt;

  factory FilterCatalogSlice.fromWire(Map<String, Object?> map, [String path = "FilterCatalogSlice"]) {
    _rejectUnknownFields(map, const <String>{"releaseId", "canonicalDigest", "status", "categoryCount", "presetCount", "categories", "presets", "recommendedFallbackPresetIds", "importedAt", "activatedAt"}, path);
    return FilterCatalogSlice(
      releaseId: _requiredString(map["releaseId"], '$path.releaseId'),
      canonicalDigest: _requiredString(map["canonicalDigest"], '$path.canonicalDigest'),
      status: FilterCatalogReleaseStatus.fromWire(map["status"], '$path.status'),
      categoryCount: _requiredInt(map["categoryCount"], '$path.categoryCount'),
      presetCount: _requiredInt(map["presetCount"], '$path.presetCount'),
      categories: List<FilterCategoryDefinition>.unmodifiable(_requiredList(map["categories"], '$path.categories').asMap().entries.map((entry) => FilterCategoryDefinition.fromWire(_requiredObject(entry.value, '$path.categories' + '[${entry.key}]'), '$path.categories' + '[${entry.key}]'))),
      presets: List<FilterPresetDefinition>.unmodifiable(_requiredList(map["presets"], '$path.presets').asMap().entries.map((entry) => FilterPresetDefinition.fromWire(_requiredObject(entry.value, '$path.presets' + '[${entry.key}]'), '$path.presets' + '[${entry.key}]'))),
      recommendedFallbackPresetIds: List<String>.unmodifiable(_requiredList(map["recommendedFallbackPresetIds"], '$path.recommendedFallbackPresetIds').asMap().entries.map((entry) => _requiredString(entry.value, '$path.recommendedFallbackPresetIds' + '[${entry.key}]'))),
      importedAt: _requiredTimestamp(map["importedAt"], '$path.importedAt'),
      activatedAt: map["activatedAt"] == null ? null : _requiredTimestamp(map["activatedAt"], '$path.activatedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "releaseId": releaseId,
    "canonicalDigest": canonicalDigest,
    "status": status.wireName,
    "categoryCount": categoryCount,
    "presetCount": presetCount,
    "categories": categories.map((value) => value.toWire()).toList(growable: false),
    "presets": presets.map((value) => value.toWire()).toList(growable: false),
    "recommendedFallbackPresetIds": recommendedFallbackPresetIds.map((value) => value).toList(growable: false),
    "importedAt": importedAt.toUtc().toIso8601String(),
    if (activatedAt != null) "activatedAt": activatedAt!.toUtc().toIso8601String(),
  };
}

final class FilterCategoryDefinition {
  const FilterCategoryDefinition({
    required this.categoryId,
    required this.displayNameZhHans,
    this.displayNameEn,
    required this.sort,
    required this.enabled,
  });

  final String categoryId;
  final String displayNameZhHans;
  final String? displayNameEn;
  final int sort;
  final bool enabled;

  factory FilterCategoryDefinition.fromWire(Map<String, Object?> map, [String path = "FilterCategoryDefinition"]) {
    _rejectUnknownFields(map, const <String>{"categoryId", "displayNameZhHans", "displayNameEn", "sort", "enabled"}, path);
    return FilterCategoryDefinition(
      categoryId: _requiredString(map["categoryId"], '$path.categoryId'),
      displayNameZhHans: _requiredString(map["displayNameZhHans"], '$path.displayNameZhHans'),
      displayNameEn: map["displayNameEn"] == null ? null : _requiredString(map["displayNameEn"], '$path.displayNameEn'),
      sort: _requiredInt(map["sort"], '$path.sort'),
      enabled: _requiredBool(map["enabled"], '$path.enabled'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "categoryId": categoryId,
    "displayNameZhHans": displayNameZhHans,
    if (displayNameEn != null) "displayNameEn": displayNameEn!,
    "sort": sort,
    "enabled": enabled,
  };
}

final class FilterPresetDefinition {
  const FilterPresetDefinition({
    required this.presetId,
    required this.categoryId,
    required this.displayNameZhHans,
    this.displayNameEn,
    required this.sort,
    required this.enabled,
    required this.defaultStrength,
    required this.adjustments,
  });

  final String presetId;
  final String categoryId;
  final String displayNameZhHans;
  final String? displayNameEn;
  final int sort;
  final bool enabled;
  final double defaultStrength;
  final FilterAdjustmentValues adjustments;

  factory FilterPresetDefinition.fromWire(Map<String, Object?> map, [String path = "FilterPresetDefinition"]) {
    _rejectUnknownFields(map, const <String>{"presetId", "categoryId", "displayNameZhHans", "displayNameEn", "sort", "enabled", "defaultStrength", "adjustments"}, path);
    return FilterPresetDefinition(
      presetId: _requiredString(map["presetId"], '$path.presetId'),
      categoryId: _requiredString(map["categoryId"], '$path.categoryId'),
      displayNameZhHans: _requiredString(map["displayNameZhHans"], '$path.displayNameZhHans'),
      displayNameEn: map["displayNameEn"] == null ? null : _requiredString(map["displayNameEn"], '$path.displayNameEn'),
      sort: _requiredInt(map["sort"], '$path.sort'),
      enabled: _requiredBool(map["enabled"], '$path.enabled'),
      defaultStrength: _requiredDouble(map["defaultStrength"], '$path.defaultStrength'),
      adjustments: FilterAdjustmentValues.fromWire(_requiredObject(map["adjustments"], '$path.adjustments'), '$path.adjustments'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "presetId": presetId,
    "categoryId": categoryId,
    "displayNameZhHans": displayNameZhHans,
    if (displayNameEn != null) "displayNameEn": displayNameEn!,
    "sort": sort,
    "enabled": enabled,
    "defaultStrength": defaultStrength,
    "adjustments": adjustments.toWire(),
  };
}

final class GatheringPostPageSlice {
  const GatheringPostPageSlice({
    required this.items,
    this.nextCursor,
    required this.hasMore,
  });

  final List<ContentPostProjection> items;
  final String? nextCursor;
  final bool hasMore;

  factory GatheringPostPageSlice.fromWire(Map<String, Object?> map, [String path = "GatheringPostPageSlice"]) {
    _rejectUnknownFields(map, const <String>{"items", "nextCursor", "hasMore"}, path);
    return GatheringPostPageSlice(
      items: List<ContentPostProjection>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => ContentPostProjection.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      nextCursor: map["nextCursor"] == null ? null : _requiredString(map["nextCursor"], '$path.nextCursor'),
      hasMore: _requiredBool(map["hasMore"], '$path.hasMore'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
    if (nextCursor != null) "nextCursor": nextCursor!,
    "hasMore": hasMore,
  };
}

final class GatheringSocialProofSummary {
  const GatheringSocialProofSummary({
    required this.anchorKind,
    required this.objectId,
    required this.publishedCount,
    required this.formedCount,
    required this.experiencedCount,
  });

  final String anchorKind;
  final String objectId;
  final int publishedCount;
  final int formedCount;
  final int experiencedCount;

  factory GatheringSocialProofSummary.fromWire(Map<String, Object?> map, [String path = "GatheringSocialProofSummary"]) {
    _rejectUnknownFields(map, const <String>{"anchorKind", "objectId", "publishedCount", "formedCount", "experiencedCount"}, path);
    return GatheringSocialProofSummary(
      anchorKind: _requiredNonBlankString(map["anchorKind"], '$path.anchorKind'),
      objectId: _requiredNonBlankString(map["objectId"], '$path.objectId'),
      publishedCount: _requiredInt(map["publishedCount"], '$path.publishedCount'),
      formedCount: _requiredInt(map["formedCount"], '$path.formedCount'),
      experiencedCount: _requiredInt(map["experiencedCount"], '$path.experiencedCount'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "anchorKind": anchorKind,
    "objectId": objectId,
    "publishedCount": publishedCount,
    "formedCount": formedCount,
    "experiencedCount": experiencedCount,
  };
}

final class GeoPoint {
  const GeoPoint({
    required this.latitude,
    required this.longitude,
  });

  final double latitude;
  final double longitude;

  factory GeoPoint.fromWire(Map<String, Object?> map, [String path = "GeoPoint"]) {
    _rejectUnknownFields(map, const <String>{"latitude", "longitude"}, path);
    return GeoPoint(
      latitude: _requiredDouble(map["latitude"], '$path.latitude'),
      longitude: _requiredDouble(map["longitude"], '$path.longitude'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "latitude": latitude,
    "longitude": longitude,
  };
}

final class IntersectionReasonPageSlice {
  const IntersectionReasonPageSlice({
    required this.items,
    this.dimension,
    this.nextCursor,
    required this.hasMore,
  });

  final List<IntersectionReason> items;
  final String? dimension;
  final String? nextCursor;
  final bool hasMore;

  factory IntersectionReasonPageSlice.fromWire(Map<String, Object?> map, [String path = "IntersectionReasonPageSlice"]) {
    _rejectUnknownFields(map, const <String>{"items", "dimension", "nextCursor", "hasMore"}, path);
    return IntersectionReasonPageSlice(
      items: List<IntersectionReason>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => IntersectionReason.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      dimension: map["dimension"] == null ? null : _requiredString(map["dimension"], '$path.dimension'),
      nextCursor: map["nextCursor"] == null ? null : _requiredString(map["nextCursor"], '$path.nextCursor'),
      hasMore: _requiredBool(map["hasMore"], '$path.hasMore'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
    if (dimension != null) "dimension": dimension!,
    if (nextCursor != null) "nextCursor": nextCursor!,
    "hasMore": hasMore,
  };
}

final class MarkIntersectionsVisitedAck {
  const MarkIntersectionsVisitedAck({
    required this.dimensions,
    required this.status,
  });

  final List<String> dimensions;
  final String status;

  factory MarkIntersectionsVisitedAck.fromWire(Map<String, Object?> map, [String path = "MarkIntersectionsVisitedAck"]) {
    _rejectUnknownFields(map, const <String>{"dimensions", "status"}, path);
    return MarkIntersectionsVisitedAck(
      dimensions: List<String>.unmodifiable(_requiredList(map["dimensions"], '$path.dimensions').asMap().entries.map((entry) => _requiredString(entry.value, '$path.dimensions' + '[${entry.key}]'))),
      status: _requiredString(map["status"], '$path.status'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "dimensions": dimensions.map((value) => value).toList(growable: false),
    "status": status,
  };
}

final class MediaAssetDiscardResult {
  const MediaAssetDiscardResult({
    required this.mediaId,
    required this.status,
    required this.replayed,
  });

  final String mediaId;
  final MediaAssetDiscardStatus status;
  final bool replayed;

  factory MediaAssetDiscardResult.fromWire(Map<String, Object?> map, [String path = "MediaAssetDiscardResult"]) {
    _rejectUnknownFields(map, const <String>{"mediaId", "status", "replayed"}, path);
    return MediaAssetDiscardResult(
      mediaId: _requiredString(map["mediaId"], '$path.mediaId'),
      status: MediaAssetDiscardStatus.fromWire(map["status"], '$path.status'),
      replayed: _requiredBool(map["replayed"], '$path.replayed'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "mediaId": mediaId,
    "status": status.wireName,
    "replayed": replayed,
  };
}

final class MediaAssetSlice {
  const MediaAssetSlice({
    required this.assetId,
    required this.version,
    required this.mediaType,
    required this.mimeType,
    required this.fileSize,
    required this.status,
    required this.accessPolicy,
    this.imageWidth,
    this.imageHeight,
    this.imageDeliveryMimeType,
    this.imageDominantColor,
    this.imageLqip,
    this.imageContentProfile,
    this.imageDerivativePolicyVersion,
    required this.cdnUrl,
  });

  final String assetId;
  final int version;
  final MediaType mediaType;
  final String mimeType;
  final int fileSize;
  final MediaAssetStatus status;
  final MediaAssetAccessPolicy accessPolicy;
  final int? imageWidth;
  final int? imageHeight;
  final String? imageDeliveryMimeType;
  final String? imageDominantColor;
  final String? imageLqip;
  final String? imageContentProfile;
  final int? imageDerivativePolicyVersion;
  final Uri cdnUrl;

  factory MediaAssetSlice.fromWire(Map<String, Object?> map, [String path = "MediaAssetSlice"]) {
    _rejectUnknownFields(map, const <String>{"assetId", "version", "mediaType", "mimeType", "fileSize", "status", "accessPolicy", "imageWidth", "imageHeight", "imageDeliveryMimeType", "imageDominantColor", "imageLqip", "imageContentProfile", "imageDerivativePolicyVersion", "cdnUrl"}, path);
    return MediaAssetSlice(
      assetId: _requiredString(map["assetId"], '$path.assetId'),
      version: _requiredPositiveInt(map["version"], '$path.version'),
      mediaType: MediaType.fromWire(map["mediaType"], '$path.mediaType'),
      mimeType: _requiredString(map["mimeType"], '$path.mimeType'),
      fileSize: _requiredPositiveInt(map["fileSize"], '$path.fileSize'),
      status: MediaAssetStatus.fromWire(map["status"], '$path.status'),
      accessPolicy: MediaAssetAccessPolicy.fromWire(map["accessPolicy"], '$path.accessPolicy'),
      imageWidth: map["imageWidth"] == null ? null : _requiredPositiveInt(map["imageWidth"], '$path.imageWidth'),
      imageHeight: map["imageHeight"] == null ? null : _requiredPositiveInt(map["imageHeight"], '$path.imageHeight'),
      imageDeliveryMimeType: map["imageDeliveryMimeType"] == null ? null : _requiredString(map["imageDeliveryMimeType"], '$path.imageDeliveryMimeType'),
      imageDominantColor: map["imageDominantColor"] == null ? null : _requiredString(map["imageDominantColor"], '$path.imageDominantColor'),
      imageLqip: map["imageLqip"] == null ? null : _requiredString(map["imageLqip"], '$path.imageLqip'),
      imageContentProfile: map["imageContentProfile"] == null ? null : _requiredString(map["imageContentProfile"], '$path.imageContentProfile'),
      imageDerivativePolicyVersion: map["imageDerivativePolicyVersion"] == null ? null : _requiredPositiveInt(map["imageDerivativePolicyVersion"], '$path.imageDerivativePolicyVersion'),
      cdnUrl: _requiredUri(map["cdnUrl"], '$path.cdnUrl'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "assetId": assetId,
    "version": version,
    "mediaType": mediaType.wireName,
    "mimeType": mimeType,
    "fileSize": fileSize,
    "status": status.wireName,
    "accessPolicy": accessPolicy.wireName,
    if (imageWidth != null) "imageWidth": imageWidth!,
    if (imageHeight != null) "imageHeight": imageHeight!,
    if (imageDeliveryMimeType != null) "imageDeliveryMimeType": imageDeliveryMimeType!,
    if (imageDominantColor != null) "imageDominantColor": imageDominantColor!,
    if (imageLqip != null) "imageLqip": imageLqip!,
    if (imageContentProfile != null) "imageContentProfile": imageContentProfile!,
    if (imageDerivativePolicyVersion != null) "imageDerivativePolicyVersion": imageDerivativePolicyVersion!,
    "cdnUrl": cdnUrl.toString(),
  };
}

final class MediaCoverSelectionResult {
  const MediaCoverSelectionResult({
    required this.mediaId,
    required this.coverStrategy,
    this.manualCoverAssetId,
    required this.coverFrameTimeMs,
    required this.thumbnailUrl,
    required this.coverUrl,
  });

  final String mediaId;
  final MediaCoverStrategy coverStrategy;
  final String? manualCoverAssetId;
  final int coverFrameTimeMs;
  final Uri thumbnailUrl;
  final Uri coverUrl;

  factory MediaCoverSelectionResult.fromWire(Map<String, Object?> map, [String path = "MediaCoverSelectionResult"]) {
    _rejectUnknownFields(map, const <String>{"mediaId", "coverStrategy", "manualCoverAssetId", "coverFrameTimeMs", "thumbnailUrl", "coverUrl"}, path);
    return MediaCoverSelectionResult(
      mediaId: _requiredString(map["mediaId"], '$path.mediaId'),
      coverStrategy: MediaCoverStrategy.fromWire(map["coverStrategy"], '$path.coverStrategy'),
      manualCoverAssetId: map["manualCoverAssetId"] == null ? null : _requiredString(map["manualCoverAssetId"], '$path.manualCoverAssetId'),
      coverFrameTimeMs: _requiredInt(map["coverFrameTimeMs"], '$path.coverFrameTimeMs'),
      thumbnailUrl: _requiredUri(map["thumbnailUrl"], '$path.thumbnailUrl'),
      coverUrl: _requiredUri(map["coverUrl"], '$path.coverUrl'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "mediaId": mediaId,
    "coverStrategy": coverStrategy.wireName,
    if (manualCoverAssetId != null) "manualCoverAssetId": manualCoverAssetId!,
    "coverFrameTimeMs": coverFrameTimeMs,
    "thumbnailUrl": thumbnailUrl.toString(),
    "coverUrl": coverUrl.toString(),
  };
}

final class MediaOriginalAccessGrant {
  const MediaOriginalAccessGrant({
    required this.mediaId,
    required this.status,
    required this.originalUrl,
    required this.format,
    required this.sizeBytes,
    required this.expiresAt,
    required this.ttlSeconds,
    required this.auditId,
  });

  final String mediaId;
  final String status;
  final Uri originalUrl;
  final String format;
  final int sizeBytes;
  final DateTime expiresAt;
  final int ttlSeconds;
  final String auditId;

  factory MediaOriginalAccessGrant.fromWire(Map<String, Object?> map, [String path = "MediaOriginalAccessGrant"]) {
    _rejectUnknownFields(map, const <String>{"mediaId", "status", "originalUrl", "format", "sizeBytes", "expiresAt", "ttlSeconds", "auditId"}, path);
    return MediaOriginalAccessGrant(
      mediaId: _requiredString(map["mediaId"], '$path.mediaId'),
      status: _requiredString(map["status"], '$path.status'),
      originalUrl: _requiredUri(map["originalUrl"], '$path.originalUrl'),
      format: _requiredString(map["format"], '$path.format'),
      sizeBytes: _requiredPositiveInt(map["sizeBytes"], '$path.sizeBytes'),
      expiresAt: _requiredTimestamp(map["expiresAt"], '$path.expiresAt'),
      ttlSeconds: _requiredPositiveInt(map["ttlSeconds"], '$path.ttlSeconds'),
      auditId: _requiredString(map["auditId"], '$path.auditId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "mediaId": mediaId,
    "status": status,
    "originalUrl": originalUrl.toString(),
    "format": format,
    "sizeBytes": sizeBytes,
    "expiresAt": expiresAt.toUtc().toIso8601String(),
    "ttlSeconds": ttlSeconds,
    "auditId": auditId,
  };
}

final class MediaUploadSessionCommandResult {
  const MediaUploadSessionCommandResult({
    required this.sessionId,
    this.assetId,
    this.assetProcessingStatus,
    required this.status,
    this.uploadUrl,
    required this.expiresAt,
    required this.replayed,
  });

  final String sessionId;
  final String? assetId;
  final MediaAssetStatus? assetProcessingStatus;
  final MediaUploadSessionStatus status;
  final Uri? uploadUrl;
  final DateTime expiresAt;
  final bool replayed;

  factory MediaUploadSessionCommandResult.fromWire(Map<String, Object?> map, [String path = "MediaUploadSessionCommandResult"]) {
    _rejectUnknownFields(map, const <String>{"sessionId", "assetId", "assetProcessingStatus", "status", "uploadUrl", "expiresAt", "replayed"}, path);
    return MediaUploadSessionCommandResult(
      sessionId: _requiredString(map["sessionId"], '$path.sessionId'),
      assetId: map["assetId"] == null ? null : _requiredString(map["assetId"], '$path.assetId'),
      assetProcessingStatus: map["assetProcessingStatus"] == null ? null : MediaAssetStatus.fromWire(map["assetProcessingStatus"], '$path.assetProcessingStatus'),
      status: MediaUploadSessionStatus.fromWire(map["status"], '$path.status'),
      uploadUrl: map["uploadUrl"] == null ? null : _requiredUri(map["uploadUrl"], '$path.uploadUrl'),
      expiresAt: _requiredTimestamp(map["expiresAt"], '$path.expiresAt'),
      replayed: _requiredBool(map["replayed"], '$path.replayed'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "sessionId": sessionId,
    if (assetId != null) "assetId": assetId!,
    if (assetProcessingStatus != null) "assetProcessingStatus": assetProcessingStatus!.wireName,
    "status": status.wireName,
    if (uploadUrl != null) "uploadUrl": uploadUrl!.toString(),
    "expiresAt": expiresAt.toUtc().toIso8601String(),
    "replayed": replayed,
  };
}

final class MediaUploadSessionSlice {
  const MediaUploadSessionSlice({
    required this.sessionId,
    required this.version,
    this.assetId,
    required this.mediaType,
    required this.mimeType,
    required this.fileSize,
    required this.status,
    required this.createdAt,
    required this.updatedAt,
    required this.expiresAt,
  });

  final String sessionId;
  final int version;
  final String? assetId;
  final MediaType mediaType;
  final String mimeType;
  final int fileSize;
  final MediaUploadSessionStatus status;
  final DateTime createdAt;
  final DateTime updatedAt;
  final DateTime expiresAt;

  factory MediaUploadSessionSlice.fromWire(Map<String, Object?> map, [String path = "MediaUploadSessionSlice"]) {
    _rejectUnknownFields(map, const <String>{"sessionId", "version", "assetId", "mediaType", "mimeType", "fileSize", "status", "createdAt", "updatedAt", "expiresAt"}, path);
    return MediaUploadSessionSlice(
      sessionId: _requiredString(map["sessionId"], '$path.sessionId'),
      version: _requiredPositiveInt(map["version"], '$path.version'),
      assetId: map["assetId"] == null ? null : _requiredString(map["assetId"], '$path.assetId'),
      mediaType: MediaType.fromWire(map["mediaType"], '$path.mediaType'),
      mimeType: _requiredString(map["mimeType"], '$path.mimeType'),
      fileSize: _requiredPositiveInt(map["fileSize"], '$path.fileSize'),
      status: MediaUploadSessionStatus.fromWire(map["status"], '$path.status'),
      createdAt: _requiredTimestamp(map["createdAt"], '$path.createdAt'),
      updatedAt: _requiredTimestamp(map["updatedAt"], '$path.updatedAt'),
      expiresAt: _requiredTimestamp(map["expiresAt"], '$path.expiresAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "sessionId": sessionId,
    "version": version,
    if (assetId != null) "assetId": assetId!,
    "mediaType": mediaType.wireName,
    "mimeType": mimeType,
    "fileSize": fileSize,
    "status": status.wireName,
    "createdAt": createdAt.toUtc().toIso8601String(),
    "updatedAt": updatedAt.toUtc().toIso8601String(),
    "expiresAt": expiresAt.toUtc().toIso8601String(),
  };
}

final class MyReportItemSlice {
  const MyReportItemSlice({
    required this.id,
    required this.targetType,
    required this.targetId,
    required this.reason,
    this.description,
    required this.status,
    required this.createdAt,
    required this.updatedAt,
    this.resolvedAt,
  });

  final String id;
  final ReportTargetType targetType;
  final String targetId;
  final ReportReason reason;
  final String? description;
  final ReportStatus status;
  final DateTime createdAt;
  final DateTime updatedAt;
  final DateTime? resolvedAt;

  factory MyReportItemSlice.fromWire(Map<String, Object?> map, [String path = "MyReportItemSlice"]) {
    _rejectUnknownFields(map, const <String>{"id", "targetType", "targetId", "reason", "description", "status", "createdAt", "updatedAt", "resolvedAt"}, path);
    return MyReportItemSlice(
      id: _requiredString(map["id"], '$path.id'),
      targetType: ReportTargetType.fromWire(map["targetType"], '$path.targetType'),
      targetId: _requiredString(map["targetId"], '$path.targetId'),
      reason: ReportReason.fromWire(map["reason"], '$path.reason'),
      description: map["description"] == null ? null : _requiredString(map["description"], '$path.description'),
      status: ReportStatus.fromWire(map["status"], '$path.status'),
      createdAt: _requiredTimestamp(map["createdAt"], '$path.createdAt'),
      updatedAt: _requiredTimestamp(map["updatedAt"], '$path.updatedAt'),
      resolvedAt: map["resolvedAt"] == null ? null : _requiredTimestamp(map["resolvedAt"], '$path.resolvedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "id": id,
    "targetType": targetType.wireName,
    "targetId": targetId,
    "reason": reason.wireName,
    if (description != null) "description": description!,
    "status": status.wireName,
    "createdAt": createdAt.toUtc().toIso8601String(),
    "updatedAt": updatedAt.toUtc().toIso8601String(),
    if (resolvedAt != null) "resolvedAt": resolvedAt!.toUtc().toIso8601String(),
  };
}

final class MyReportPageSlice {
  const MyReportPageSlice({
    required this.items,
    this.nextCursor,
  });

  final List<MyReportItemSlice> items;
  final String? nextCursor;

  factory MyReportPageSlice.fromWire(Map<String, Object?> map, [String path = "MyReportPageSlice"]) {
    _rejectUnknownFields(map, const <String>{"items", "nextCursor"}, path);
    return MyReportPageSlice(
      items: List<MyReportItemSlice>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => MyReportItemSlice.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      nextCursor: map["nextCursor"] == null ? null : _requiredString(map["nextCursor"], '$path.nextCursor'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
    if (nextCursor != null) "nextCursor": nextCursor!,
  };
}

final class ObjectIntersectionReasonSlice {
  const ObjectIntersectionReasonSlice({
    required this.items,
    required this.objectId,
    required this.objectType,
  });

  final List<IntersectionReason> items;
  final String objectId;
  final String objectType;

  factory ObjectIntersectionReasonSlice.fromWire(Map<String, Object?> map, [String path = "ObjectIntersectionReasonSlice"]) {
    _rejectUnknownFields(map, const <String>{"items", "objectId", "objectType"}, path);
    return ObjectIntersectionReasonSlice(
      items: List<IntersectionReason>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => IntersectionReason.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      objectId: _requiredString(map["objectId"], '$path.objectId'),
      objectType: _requiredString(map["objectType"], '$path.objectType'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
    "objectId": objectId,
    "objectType": objectType,
  };
}

final class OutboundShareFactResult {
  const OutboundShareFactResult({
    required this.eventId,
    required this.postId,
    required this.channel,
    required this.referralId,
    required this.occurredAt,
    required this.replayed,
  });

  final String eventId;
  final String postId;
  final OutboundShareChannel channel;
  final String referralId;
  final DateTime occurredAt;
  final bool replayed;

  factory OutboundShareFactResult.fromWire(Map<String, Object?> map, [String path = "OutboundShareFactResult"]) {
    _rejectUnknownFields(map, const <String>{"eventId", "postId", "channel", "referralId", "occurredAt", "replayed"}, path);
    return OutboundShareFactResult(
      eventId: _requiredString(map["eventId"], '$path.eventId'),
      postId: _requiredString(map["postId"], '$path.postId'),
      channel: OutboundShareChannel.fromWire(map["channel"], '$path.channel'),
      referralId: _requiredString(map["referralId"], '$path.referralId'),
      occurredAt: _requiredTimestamp(map["occurredAt"], '$path.occurredAt'),
      replayed: _requiredBool(map["replayed"], '$path.replayed'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "eventId": eventId,
    "postId": postId,
    "channel": channel.wireName,
    "referralId": referralId,
    "occurredAt": occurredAt.toUtc().toIso8601String(),
    "replayed": replayed,
  };
}

final class PostArticleAsset {
  const PostArticleAsset({
    required this.assetId,
    this.kind,
    this.publicSliceKey,
    this.sha256,
    this.mimeType,
    this.sourceOriginalSha256,
    this.caption,
    this.role,
    this.layout,
    this.width,
    this.height,
    this.durationMs,
    this.thumbnailUrl,
    this.coverUrl,
    this.coverStrategy,
    this.coverFrameTimeMs,
    this.sourceCollectionId,
  });

  final String assetId;
  final String? kind;
  final String? publicSliceKey;
  final String? sha256;
  final String? mimeType;
  final String? sourceOriginalSha256;
  final String? caption;
  final String? role;
  final String? layout;
  final int? width;
  final int? height;
  final int? durationMs;
  final String? thumbnailUrl;
  final String? coverUrl;
  final String? coverStrategy;
  final int? coverFrameTimeMs;
  final String? sourceCollectionId;

  factory PostArticleAsset.fromWire(Map<String, Object?> map, [String path = "PostArticleAsset"]) {
    _rejectUnknownFields(map, const <String>{"assetId", "kind", "publicSliceKey", "sha256", "mimeType", "sourceOriginalSha256", "caption", "role", "layout", "width", "height", "durationMs", "thumbnailUrl", "coverUrl", "coverStrategy", "coverFrameTimeMs", "sourceCollectionId"}, path);
    return PostArticleAsset(
      assetId: _requiredString(map["assetId"], '$path.assetId'),
      kind: map["kind"] == null ? null : _requiredString(map["kind"], '$path.kind'),
      publicSliceKey: map["publicSliceKey"] == null ? null : _requiredString(map["publicSliceKey"], '$path.publicSliceKey'),
      sha256: map["sha256"] == null ? null : _requiredString(map["sha256"], '$path.sha256'),
      mimeType: map["mimeType"] == null ? null : _requiredString(map["mimeType"], '$path.mimeType'),
      sourceOriginalSha256: map["sourceOriginalSha256"] == null ? null : _requiredString(map["sourceOriginalSha256"], '$path.sourceOriginalSha256'),
      caption: map["caption"] == null ? null : _requiredString(map["caption"], '$path.caption'),
      role: map["role"] == null ? null : _requiredString(map["role"], '$path.role'),
      layout: map["layout"] == null ? null : _requiredString(map["layout"], '$path.layout'),
      width: map["width"] == null ? null : _requiredInt(map["width"], '$path.width'),
      height: map["height"] == null ? null : _requiredInt(map["height"], '$path.height'),
      durationMs: map["durationMs"] == null ? null : _requiredInt(map["durationMs"], '$path.durationMs'),
      thumbnailUrl: map["thumbnailUrl"] == null ? null : _requiredString(map["thumbnailUrl"], '$path.thumbnailUrl'),
      coverUrl: map["coverUrl"] == null ? null : _requiredString(map["coverUrl"], '$path.coverUrl'),
      coverStrategy: map["coverStrategy"] == null ? null : _requiredString(map["coverStrategy"], '$path.coverStrategy'),
      coverFrameTimeMs: map["coverFrameTimeMs"] == null ? null : _requiredInt(map["coverFrameTimeMs"], '$path.coverFrameTimeMs'),
      sourceCollectionId: map["sourceCollectionId"] == null ? null : _requiredString(map["sourceCollectionId"], '$path.sourceCollectionId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "assetId": assetId,
    if (kind != null) "kind": kind!,
    if (publicSliceKey != null) "publicSliceKey": publicSliceKey!,
    if (sha256 != null) "sha256": sha256!,
    if (mimeType != null) "mimeType": mimeType!,
    if (sourceOriginalSha256 != null) "sourceOriginalSha256": sourceOriginalSha256!,
    if (caption != null) "caption": caption!,
    if (role != null) "role": role!,
    if (layout != null) "layout": layout!,
    if (width != null) "width": width!,
    if (height != null) "height": height!,
    if (durationMs != null) "durationMs": durationMs!,
    if (thumbnailUrl != null) "thumbnailUrl": thumbnailUrl!,
    if (coverUrl != null) "coverUrl": coverUrl!,
    if (coverStrategy != null) "coverStrategy": coverStrategy!,
    if (coverFrameTimeMs != null) "coverFrameTimeMs": coverFrameTimeMs!,
    if (sourceCollectionId != null) "sourceCollectionId": sourceCollectionId!,
  };
}

final class PostArticleAssetManifest {
  const PostArticleAssetManifest({
    required this.schema,
    this.markdownVersion,
    this.markdownDialect,
    required this.articleMarkdownDigest,
    required this.documentSha256,
    required this.assetManifestSha256,
    required this.documentVersionSha256,
    required this.assets,
  });

  final String schema;
  final String? markdownVersion;
  final String? markdownDialect;
  final String articleMarkdownDigest;
  final String documentSha256;
  final String assetManifestSha256;
  final String documentVersionSha256;
  final List<PostArticleAsset> assets;

  factory PostArticleAssetManifest.fromWire(Map<String, Object?> map, [String path = "PostArticleAssetManifest"]) {
    _rejectUnknownFields(map, const <String>{"schema", "markdownVersion", "markdownDialect", "articleMarkdownDigest", "documentSha256", "assetManifestSha256", "documentVersionSha256", "assets"}, path);
    return PostArticleAssetManifest(
      schema: _requiredString(map["schema"], '$path.schema'),
      markdownVersion: map["markdownVersion"] == null ? null : _requiredString(map["markdownVersion"], '$path.markdownVersion'),
      markdownDialect: map["markdownDialect"] == null ? null : _requiredString(map["markdownDialect"], '$path.markdownDialect'),
      articleMarkdownDigest: _requiredString(map["articleMarkdownDigest"], '$path.articleMarkdownDigest'),
      documentSha256: _requiredString(map["documentSha256"], '$path.documentSha256'),
      assetManifestSha256: _requiredString(map["assetManifestSha256"], '$path.assetManifestSha256'),
      documentVersionSha256: _requiredString(map["documentVersionSha256"], '$path.documentVersionSha256'),
      assets: List<PostArticleAsset>.unmodifiable(_requiredList(map["assets"], '$path.assets').asMap().entries.map((entry) => PostArticleAsset.fromWire(_requiredObject(entry.value, '$path.assets' + '[${entry.key}]'), '$path.assets' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "schema": schema,
    if (markdownVersion != null) "markdownVersion": markdownVersion!,
    if (markdownDialect != null) "markdownDialect": markdownDialect!,
    "articleMarkdownDigest": articleMarkdownDigest,
    "documentSha256": documentSha256,
    "assetManifestSha256": assetManifestSha256,
    "documentVersionSha256": documentVersionSha256,
    "assets": assets.map((value) => value.toWire()).toList(growable: false),
  };
}

final class PostArticleLayoutPolicy {
  const PostArticleLayoutPolicy({
    this.wrapDowngrade,
    this.galleryDowngrade,
  });

  final String? wrapDowngrade;
  final String? galleryDowngrade;

  factory PostArticleLayoutPolicy.fromWire(Map<String, Object?> map, [String path = "PostArticleLayoutPolicy"]) {
    _rejectUnknownFields(map, const <String>{"wrapDowngrade", "galleryDowngrade"}, path);
    return PostArticleLayoutPolicy(
      wrapDowngrade: map["wrapDowngrade"] == null ? null : _requiredString(map["wrapDowngrade"], '$path.wrapDowngrade'),
      galleryDowngrade: map["galleryDowngrade"] == null ? null : _requiredString(map["galleryDowngrade"], '$path.galleryDowngrade'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (wrapDowngrade != null) "wrapDowngrade": wrapDowngrade!,
    if (galleryDowngrade != null) "galleryDowngrade": galleryDowngrade!,
  };
}

final class PostArticleRenderProfile {
  const PostArticleRenderProfile({
    this.template,
    this.fontPreset,
    this.paperThemeMode,
    this.paperTexture,
    this.contentVertical,
    this.layoutPolicy,
    this.width,
    this.height,
    this.durationMs,
  });

  final String? template;
  final String? fontPreset;
  final String? paperThemeMode;
  final String? paperTexture;
  final String? contentVertical;
  final PostArticleLayoutPolicy? layoutPolicy;
  final int? width;
  final int? height;
  final int? durationMs;

  factory PostArticleRenderProfile.fromWire(Map<String, Object?> map, [String path = "PostArticleRenderProfile"]) {
    _rejectUnknownFields(map, const <String>{"template", "fontPreset", "paperThemeMode", "paperTexture", "contentVertical", "layoutPolicy", "width", "height", "durationMs"}, path);
    return PostArticleRenderProfile(
      template: map["template"] == null ? null : _requiredString(map["template"], '$path.template'),
      fontPreset: map["fontPreset"] == null ? null : _requiredString(map["fontPreset"], '$path.fontPreset'),
      paperThemeMode: map["paperThemeMode"] == null ? null : _requiredString(map["paperThemeMode"], '$path.paperThemeMode'),
      paperTexture: map["paperTexture"] == null ? null : _requiredString(map["paperTexture"], '$path.paperTexture'),
      contentVertical: map["contentVertical"] == null ? null : _requiredString(map["contentVertical"], '$path.contentVertical'),
      layoutPolicy: map["layoutPolicy"] == null ? null : PostArticleLayoutPolicy.fromWire(_requiredObject(map["layoutPolicy"], '$path.layoutPolicy'), '$path.layoutPolicy'),
      width: map["width"] == null ? null : _requiredInt(map["width"], '$path.width'),
      height: map["height"] == null ? null : _requiredInt(map["height"], '$path.height'),
      durationMs: map["durationMs"] == null ? null : _requiredInt(map["durationMs"], '$path.durationMs'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (template != null) "template": template!,
    if (fontPreset != null) "fontPreset": fontPreset!,
    if (paperThemeMode != null) "paperThemeMode": paperThemeMode!,
    if (paperTexture != null) "paperTexture": paperTexture!,
    if (contentVertical != null) "contentVertical": contentVertical!,
    if (layoutPolicy != null) "layoutPolicy": layoutPolicy!.toWire(),
    if (width != null) "width": width!,
    if (height != null) "height": height!,
    if (durationMs != null) "durationMs": durationMs!,
  };
}

final class PostDeletionReceipt {
  const PostDeletionReceipt({
    required this.postId,
    required this.status,
    required this.replayed,
  });

  final String postId;
  final PostStatus status;
  final bool replayed;

  factory PostDeletionReceipt.fromWire(Map<String, Object?> map, [String path = "PostDeletionReceipt"]) {
    _rejectUnknownFields(map, const <String>{"postId", "status", "replayed"}, path);
    return PostDeletionReceipt(
      postId: _requiredNonBlankString(map["postId"], '$path.postId'),
      status: PostStatus.fromWire(map["status"], '$path.status'),
      replayed: _requiredBool(map["replayed"], '$path.replayed'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "postId": postId,
    "status": status.wireName,
    "replayed": replayed,
  };
}

final class PostEntityMention {
  const PostEntityMention({
    required this.subjectType,
    required this.subjectId,
    required this.homepageId,
    required this.displayName,
    required this.rangeStart,
    required this.rangeEnd,
  });

  final String subjectType;
  final String subjectId;
  final String homepageId;
  final String displayName;
  final int rangeStart;
  final int rangeEnd;

  factory PostEntityMention.fromWire(Map<String, Object?> map, [String path = "PostEntityMention"]) {
    _rejectUnknownFields(map, const <String>{"subjectType", "subjectId", "homepageId", "displayName", "rangeStart", "rangeEnd"}, path);
    return PostEntityMention(
      subjectType: _requiredString(map["subjectType"], '$path.subjectType'),
      subjectId: _requiredString(map["subjectId"], '$path.subjectId'),
      homepageId: _requiredString(map["homepageId"], '$path.homepageId'),
      displayName: _requiredString(map["displayName"], '$path.displayName'),
      rangeStart: _requiredInt(map["rangeStart"], '$path.rangeStart'),
      rangeEnd: _requiredInt(map["rangeEnd"], '$path.rangeEnd'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "subjectType": subjectType,
    "subjectId": subjectId,
    "homepageId": homepageId,
    "displayName": displayName,
    "rangeStart": rangeStart,
    "rangeEnd": rangeEnd,
  };
}

final class PostHomepageSnapshot {
  const PostHomepageSnapshot({
    this.canonicalEntityId,
    this.title,
    this.subtitle,
    this.coverUrl,
    this.width,
    this.height,
    this.durationMs,
  });

  final String? canonicalEntityId;
  final String? title;
  final String? subtitle;
  final String? coverUrl;
  final int? width;
  final int? height;
  final int? durationMs;

  factory PostHomepageSnapshot.fromWire(Map<String, Object?> map, [String path = "PostHomepageSnapshot"]) {
    _rejectUnknownFields(map, const <String>{"canonicalEntityId", "title", "subtitle", "coverUrl", "width", "height", "durationMs"}, path);
    return PostHomepageSnapshot(
      canonicalEntityId: map["canonicalEntityId"] == null ? null : _requiredString(map["canonicalEntityId"], '$path.canonicalEntityId'),
      title: map["title"] == null ? null : _requiredString(map["title"], '$path.title'),
      subtitle: map["subtitle"] == null ? null : _requiredString(map["subtitle"], '$path.subtitle'),
      coverUrl: map["coverUrl"] == null ? null : _requiredString(map["coverUrl"], '$path.coverUrl'),
      width: map["width"] == null ? null : _requiredInt(map["width"], '$path.width'),
      height: map["height"] == null ? null : _requiredInt(map["height"], '$path.height'),
      durationMs: map["durationMs"] == null ? null : _requiredInt(map["durationMs"], '$path.durationMs'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (canonicalEntityId != null) "canonicalEntityId": canonicalEntityId!,
    if (title != null) "title": title!,
    if (subtitle != null) "subtitle": subtitle!,
    if (coverUrl != null) "coverUrl": coverUrl!,
    if (width != null) "width": width!,
    if (height != null) "height": height!,
    if (durationMs != null) "durationMs": durationMs!,
  };
}

final class PostMediaItem {
  const PostMediaItem({
    required this.kind,
    this.mediaAssetId,
    this.mediaAssetVersion,
    required this.url,
    this.coverUrl,
    this.thumbnailUrl,
    this.durationMs,
    this.width,
    this.height,
    this.previewTrackManifestUrl,
    this.previewTrackVersion,
    this.hlsCmafMasterManifestUrl,
    this.hlsCmafDescriptorVersion,
    this.title,
    this.coverStrategy,
    this.coverFrameTimeMs,
  });

  final String kind;
  final String? mediaAssetId;
  final int? mediaAssetVersion;
  final String url;
  final String? coverUrl;
  final String? thumbnailUrl;
  final int? durationMs;
  final int? width;
  final int? height;
  final String? previewTrackManifestUrl;
  final int? previewTrackVersion;
  final String? hlsCmafMasterManifestUrl;
  final int? hlsCmafDescriptorVersion;
  final String? title;
  final String? coverStrategy;
  final int? coverFrameTimeMs;

  factory PostMediaItem.fromWire(Map<String, Object?> map, [String path = "PostMediaItem"]) {
    _rejectUnknownFields(map, const <String>{"kind", "mediaAssetId", "mediaAssetVersion", "url", "coverUrl", "thumbnailUrl", "durationMs", "width", "height", "previewTrackManifestUrl", "previewTrackVersion", "hlsCmafMasterManifestUrl", "hlsCmafDescriptorVersion", "title", "coverStrategy", "coverFrameTimeMs"}, path);
    return PostMediaItem(
      kind: _requiredString(map["kind"], '$path.kind'),
      mediaAssetId: map["mediaAssetId"] == null ? null : _requiredString(map["mediaAssetId"], '$path.mediaAssetId'),
      mediaAssetVersion: map["mediaAssetVersion"] == null ? null : _requiredInt(map["mediaAssetVersion"], '$path.mediaAssetVersion'),
      url: _requiredString(map["url"], '$path.url'),
      coverUrl: map["coverUrl"] == null ? null : _requiredString(map["coverUrl"], '$path.coverUrl'),
      thumbnailUrl: map["thumbnailUrl"] == null ? null : _requiredString(map["thumbnailUrl"], '$path.thumbnailUrl'),
      durationMs: map["durationMs"] == null ? null : _requiredInt(map["durationMs"], '$path.durationMs'),
      width: map["width"] == null ? null : _requiredInt(map["width"], '$path.width'),
      height: map["height"] == null ? null : _requiredInt(map["height"], '$path.height'),
      previewTrackManifestUrl: map["previewTrackManifestUrl"] == null ? null : _requiredString(map["previewTrackManifestUrl"], '$path.previewTrackManifestUrl'),
      previewTrackVersion: map["previewTrackVersion"] == null ? null : _requiredInt(map["previewTrackVersion"], '$path.previewTrackVersion'),
      hlsCmafMasterManifestUrl: map["hlsCmafMasterManifestUrl"] == null ? null : _requiredString(map["hlsCmafMasterManifestUrl"], '$path.hlsCmafMasterManifestUrl'),
      hlsCmafDescriptorVersion: map["hlsCmafDescriptorVersion"] == null ? null : _requiredInt(map["hlsCmafDescriptorVersion"], '$path.hlsCmafDescriptorVersion'),
      title: map["title"] == null ? null : _requiredString(map["title"], '$path.title'),
      coverStrategy: map["coverStrategy"] == null ? null : _requiredString(map["coverStrategy"], '$path.coverStrategy'),
      coverFrameTimeMs: map["coverFrameTimeMs"] == null ? null : _requiredInt(map["coverFrameTimeMs"], '$path.coverFrameTimeMs'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "kind": kind,
    if (mediaAssetId != null) "mediaAssetId": mediaAssetId!,
    if (mediaAssetVersion != null) "mediaAssetVersion": mediaAssetVersion!,
    "url": url,
    if (coverUrl != null) "coverUrl": coverUrl!,
    if (thumbnailUrl != null) "thumbnailUrl": thumbnailUrl!,
    if (durationMs != null) "durationMs": durationMs!,
    if (width != null) "width": width!,
    if (height != null) "height": height!,
    if (previewTrackManifestUrl != null) "previewTrackManifestUrl": previewTrackManifestUrl!,
    if (previewTrackVersion != null) "previewTrackVersion": previewTrackVersion!,
    if (hlsCmafMasterManifestUrl != null) "hlsCmafMasterManifestUrl": hlsCmafMasterManifestUrl!,
    if (hlsCmafDescriptorVersion != null) "hlsCmafDescriptorVersion": hlsCmafDescriptorVersion!,
    if (title != null) "title": title!,
    if (coverStrategy != null) "coverStrategy": coverStrategy!,
    if (coverFrameTimeMs != null) "coverFrameTimeMs": coverFrameTimeMs!,
  };
}

final class PostPublicationReceipt {
  const PostPublicationReceipt({
    required this.publishIntentId,
    required this.localDraftId,
    required this.postId,
    required this.state,
    required this.committedVersion,
    required this.acceptedAt,
  });

  final String publishIntentId;
  final String localDraftId;
  final String postId;
  final String state;
  final int committedVersion;
  final DateTime acceptedAt;

  factory PostPublicationReceipt.fromWire(Map<String, Object?> map, [String path = "PostPublicationReceipt"]) {
    _rejectUnknownFields(map, const <String>{"publishIntentId", "localDraftId", "postId", "state", "committedVersion", "acceptedAt"}, path);
    return PostPublicationReceipt(
      publishIntentId: _requiredString(map["publishIntentId"], '$path.publishIntentId'),
      localDraftId: _requiredString(map["localDraftId"], '$path.localDraftId'),
      postId: _requiredString(map["postId"], '$path.postId'),
      state: _requiredString(map["state"], '$path.state'),
      committedVersion: _requiredInt(map["committedVersion"], '$path.committedVersion'),
      acceptedAt: _requiredTimestamp(map["acceptedAt"], '$path.acceptedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "publishIntentId": publishIntentId,
    "localDraftId": localDraftId,
    "postId": postId,
    "state": state,
    "committedVersion": committedVersion,
    "acceptedAt": acceptedAt.toUtc().toIso8601String(),
  };
}

final class PostSemanticMention {
  const PostSemanticMention({
    required this.mentionId,
    required this.kind,
    required this.surface,
    required this.location,
    this.rangeStart,
    this.rangeEnd,
    required this.status,
    this.candidateId,
    this.targetRef,
  });

  final String mentionId;
  final String kind;
  final String surface;
  final String location;
  final int? rangeStart;
  final int? rangeEnd;
  final String status;
  final String? candidateId;
  final String? targetRef;

  factory PostSemanticMention.fromWire(Map<String, Object?> map, [String path = "PostSemanticMention"]) {
    _rejectUnknownFields(map, const <String>{"mentionId", "kind", "surface", "location", "rangeStart", "rangeEnd", "status", "candidateId", "targetRef"}, path);
    return PostSemanticMention(
      mentionId: _requiredString(map["mentionId"], '$path.mentionId'),
      kind: _requiredString(map["kind"], '$path.kind'),
      surface: _requiredString(map["surface"], '$path.surface'),
      location: _requiredString(map["location"], '$path.location'),
      rangeStart: map["rangeStart"] == null ? null : _requiredInt(map["rangeStart"], '$path.rangeStart'),
      rangeEnd: map["rangeEnd"] == null ? null : _requiredInt(map["rangeEnd"], '$path.rangeEnd'),
      status: _requiredString(map["status"], '$path.status'),
      candidateId: map["candidateId"] == null ? null : _requiredString(map["candidateId"], '$path.candidateId'),
      targetRef: map["targetRef"] == null ? null : _requiredString(map["targetRef"], '$path.targetRef'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "mentionId": mentionId,
    "kind": kind,
    "surface": surface,
    "location": location,
    if (rangeStart != null) "rangeStart": rangeStart!,
    if (rangeEnd != null) "rangeEnd": rangeEnd!,
    "status": status,
    if (candidateId != null) "candidateId": candidateId!,
    if (targetRef != null) "targetRef": targetRef!,
  };
}

final class ProfileInteractionActivityPageSlice {
  const ProfileInteractionActivityPageSlice({
    required this.items,
    this.nextCursor,
    required this.hasMore,
  });

  final List<ProfileInteractionActivityView> items;
  final String? nextCursor;
  final bool hasMore;

  factory ProfileInteractionActivityPageSlice.fromWire(Map<String, Object?> map, [String path = "ProfileInteractionActivityPageSlice"]) {
    _rejectUnknownFields(map, const <String>{"items", "nextCursor", "hasMore"}, path);
    return ProfileInteractionActivityPageSlice(
      items: List<ProfileInteractionActivityView>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => ProfileInteractionActivityView.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      nextCursor: map["nextCursor"] == null ? null : _requiredString(map["nextCursor"], '$path.nextCursor'),
      hasMore: _requiredBool(map["hasMore"], '$path.hasMore'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
    if (nextCursor != null) "nextCursor": nextCursor!,
    "hasMore": hasMore,
  };
}

final class ProfileInteractionActivityView {
  const ProfileInteractionActivityView({
    required this.ownerPersonaId,
    required this.activityId,
    required this.activityType,
    required this.direction,
    required this.sourceType,
    required this.sourceEventId,
    required this.sourceVersion,
    required this.viewerReactionVersion,
    required this.targetVersion,
    required this.active,
    required this.commentKind,
    this.commentId,
    this.parentCommentId,
    required this.viewerReaction,
    required this.actorPersonaId,
    required this.actorDisplayName,
    this.actorAvatarUrl,
    required this.actorAvatarVersion,
    this.counterpartPersonaId,
    this.counterpartDisplayName,
    this.counterpartAvatarUrl,
    required this.targetPersonaId,
    required this.targetContentId,
    required this.targetContentType,
    this.targetContentSummary,
    required this.targetKind,
    required this.targetAvailability,
    required this.targetReplyCount,
    required this.displayPersonaId,
    required this.displayName,
    this.displayAvatarUrl,
    required this.displayAvatarVersion,
    this.displayUserRouteId,
    required this.primaryText,
    this.contextText,
    required this.previewMediaKind,
    this.previewImageUrl,
    this.previewText,
    required this.previewUnavailable,
    this.previewObjectId,
    this.previewRouteId,
    this.outboundShareEventId,
    this.shareText,
    this.impactPrimaryText,
    this.impactDeepLink,
    required this.filterKeys,
    required this.createdAt,
    required this.occurredAt,
    this.seenAt,
    this.readAt,
  });

  final String ownerPersonaId;
  final String activityId;
  final InteractionActivityType activityType;
  final InteractionDirection direction;
  final String sourceType;
  final String sourceEventId;
  final int sourceVersion;
  final int viewerReactionVersion;
  final int targetVersion;
  final bool active;
  final String commentKind;
  final String? commentId;
  final String? parentCommentId;
  final CommentReactionType viewerReaction;
  final String actorPersonaId;
  final String actorDisplayName;
  final String? actorAvatarUrl;
  final int actorAvatarVersion;
  final String? counterpartPersonaId;
  final String? counterpartDisplayName;
  final String? counterpartAvatarUrl;
  final String targetPersonaId;
  final String targetContentId;
  final ContentType targetContentType;
  final String? targetContentSummary;
  final String targetKind;
  final String targetAvailability;
  final int targetReplyCount;
  final String displayPersonaId;
  final String displayName;
  final String? displayAvatarUrl;
  final int displayAvatarVersion;
  final String? displayUserRouteId;
  final String primaryText;
  final String? contextText;
  final String previewMediaKind;
  final String? previewImageUrl;
  final String? previewText;
  final bool previewUnavailable;
  final String? previewObjectId;
  final String? previewRouteId;
  final String? outboundShareEventId;
  final String? shareText;
  final String? impactPrimaryText;
  final String? impactDeepLink;
  final List<String> filterKeys;
  final DateTime createdAt;
  final DateTime occurredAt;
  final DateTime? seenAt;
  final DateTime? readAt;

  factory ProfileInteractionActivityView.fromWire(Map<String, Object?> map, [String path = "ProfileInteractionActivityView"]) {
    _rejectUnknownFields(map, const <String>{"ownerPersonaId", "activityId", "activityType", "direction", "sourceType", "sourceEventId", "sourceVersion", "viewerReactionVersion", "targetVersion", "active", "commentKind", "commentId", "parentCommentId", "viewerReaction", "actorPersonaId", "actorDisplayName", "actorAvatarUrl", "actorAvatarVersion", "counterpartPersonaId", "counterpartDisplayName", "counterpartAvatarUrl", "targetPersonaId", "targetContentId", "targetContentType", "targetContentSummary", "targetKind", "targetAvailability", "targetReplyCount", "displayPersonaId", "displayName", "displayAvatarUrl", "displayAvatarVersion", "displayUserRouteId", "primaryText", "contextText", "previewMediaKind", "previewImageUrl", "previewText", "previewUnavailable", "previewObjectId", "previewRouteId", "outboundShareEventId", "shareText", "impactPrimaryText", "impactDeepLink", "filterKeys", "createdAt", "occurredAt", "seenAt", "readAt"}, path);
    return ProfileInteractionActivityView(
      ownerPersonaId: _requiredString(map["ownerPersonaId"], '$path.ownerPersonaId'),
      activityId: _requiredString(map["activityId"], '$path.activityId'),
      activityType: InteractionActivityType.fromWire(map["activityType"], '$path.activityType'),
      direction: InteractionDirection.fromWire(map["direction"], '$path.direction'),
      sourceType: _requiredString(map["sourceType"], '$path.sourceType'),
      sourceEventId: _requiredString(map["sourceEventId"], '$path.sourceEventId'),
      sourceVersion: _requiredInt(map["sourceVersion"], '$path.sourceVersion'),
      viewerReactionVersion: _requiredInt(map["viewerReactionVersion"], '$path.viewerReactionVersion'),
      targetVersion: _requiredInt(map["targetVersion"], '$path.targetVersion'),
      active: _requiredBool(map["active"], '$path.active'),
      commentKind: _requiredString(map["commentKind"], '$path.commentKind'),
      commentId: map["commentId"] == null ? null : _requiredString(map["commentId"], '$path.commentId'),
      parentCommentId: map["parentCommentId"] == null ? null : _requiredString(map["parentCommentId"], '$path.parentCommentId'),
      viewerReaction: CommentReactionType.fromWire(map["viewerReaction"], '$path.viewerReaction'),
      actorPersonaId: _requiredString(map["actorPersonaId"], '$path.actorPersonaId'),
      actorDisplayName: _requiredString(map["actorDisplayName"], '$path.actorDisplayName'),
      actorAvatarUrl: map["actorAvatarUrl"] == null ? null : _requiredString(map["actorAvatarUrl"], '$path.actorAvatarUrl'),
      actorAvatarVersion: _requiredInt(map["actorAvatarVersion"], '$path.actorAvatarVersion'),
      counterpartPersonaId: map["counterpartPersonaId"] == null ? null : _requiredString(map["counterpartPersonaId"], '$path.counterpartPersonaId'),
      counterpartDisplayName: map["counterpartDisplayName"] == null ? null : _requiredString(map["counterpartDisplayName"], '$path.counterpartDisplayName'),
      counterpartAvatarUrl: map["counterpartAvatarUrl"] == null ? null : _requiredString(map["counterpartAvatarUrl"], '$path.counterpartAvatarUrl'),
      targetPersonaId: _requiredString(map["targetPersonaId"], '$path.targetPersonaId'),
      targetContentId: _requiredString(map["targetContentId"], '$path.targetContentId'),
      targetContentType: ContentType.fromWire(map["targetContentType"], '$path.targetContentType'),
      targetContentSummary: map["targetContentSummary"] == null ? null : _requiredString(map["targetContentSummary"], '$path.targetContentSummary'),
      targetKind: _requiredString(map["targetKind"], '$path.targetKind'),
      targetAvailability: _requiredString(map["targetAvailability"], '$path.targetAvailability'),
      targetReplyCount: _requiredInt(map["targetReplyCount"], '$path.targetReplyCount'),
      displayPersonaId: _requiredString(map["displayPersonaId"], '$path.displayPersonaId'),
      displayName: _requiredString(map["displayName"], '$path.displayName'),
      displayAvatarUrl: map["displayAvatarUrl"] == null ? null : _requiredString(map["displayAvatarUrl"], '$path.displayAvatarUrl'),
      displayAvatarVersion: _requiredInt(map["displayAvatarVersion"], '$path.displayAvatarVersion'),
      displayUserRouteId: map["displayUserRouteId"] == null ? null : _requiredString(map["displayUserRouteId"], '$path.displayUserRouteId'),
      primaryText: _requiredString(map["primaryText"], '$path.primaryText'),
      contextText: map["contextText"] == null ? null : _requiredString(map["contextText"], '$path.contextText'),
      previewMediaKind: _requiredString(map["previewMediaKind"], '$path.previewMediaKind'),
      previewImageUrl: map["previewImageUrl"] == null ? null : _requiredString(map["previewImageUrl"], '$path.previewImageUrl'),
      previewText: map["previewText"] == null ? null : _requiredString(map["previewText"], '$path.previewText'),
      previewUnavailable: _requiredBool(map["previewUnavailable"], '$path.previewUnavailable'),
      previewObjectId: map["previewObjectId"] == null ? null : _requiredString(map["previewObjectId"], '$path.previewObjectId'),
      previewRouteId: map["previewRouteId"] == null ? null : _requiredString(map["previewRouteId"], '$path.previewRouteId'),
      outboundShareEventId: map["outboundShareEventId"] == null ? null : _requiredString(map["outboundShareEventId"], '$path.outboundShareEventId'),
      shareText: map["shareText"] == null ? null : _requiredString(map["shareText"], '$path.shareText'),
      impactPrimaryText: map["impactPrimaryText"] == null ? null : _requiredString(map["impactPrimaryText"], '$path.impactPrimaryText'),
      impactDeepLink: map["impactDeepLink"] == null ? null : _requiredString(map["impactDeepLink"], '$path.impactDeepLink'),
      filterKeys: List<String>.unmodifiable(_requiredList(map["filterKeys"], '$path.filterKeys').asMap().entries.map((entry) => _requiredString(entry.value, '$path.filterKeys' + '[${entry.key}]'))),
      createdAt: _requiredTimestamp(map["createdAt"], '$path.createdAt'),
      occurredAt: _requiredTimestamp(map["occurredAt"], '$path.occurredAt'),
      seenAt: map["seenAt"] == null ? null : _requiredTimestamp(map["seenAt"], '$path.seenAt'),
      readAt: map["readAt"] == null ? null : _requiredTimestamp(map["readAt"], '$path.readAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "ownerPersonaId": ownerPersonaId,
    "activityId": activityId,
    "activityType": activityType.wireName,
    "direction": direction.wireName,
    "sourceType": sourceType,
    "sourceEventId": sourceEventId,
    "sourceVersion": sourceVersion,
    "viewerReactionVersion": viewerReactionVersion,
    "targetVersion": targetVersion,
    "active": active,
    "commentKind": commentKind,
    if (commentId != null) "commentId": commentId!,
    if (parentCommentId != null) "parentCommentId": parentCommentId!,
    "viewerReaction": viewerReaction.wireName,
    "actorPersonaId": actorPersonaId,
    "actorDisplayName": actorDisplayName,
    if (actorAvatarUrl != null) "actorAvatarUrl": actorAvatarUrl!,
    "actorAvatarVersion": actorAvatarVersion,
    if (counterpartPersonaId != null) "counterpartPersonaId": counterpartPersonaId!,
    if (counterpartDisplayName != null) "counterpartDisplayName": counterpartDisplayName!,
    if (counterpartAvatarUrl != null) "counterpartAvatarUrl": counterpartAvatarUrl!,
    "targetPersonaId": targetPersonaId,
    "targetContentId": targetContentId,
    "targetContentType": targetContentType.wireName,
    if (targetContentSummary != null) "targetContentSummary": targetContentSummary!,
    "targetKind": targetKind,
    "targetAvailability": targetAvailability,
    "targetReplyCount": targetReplyCount,
    "displayPersonaId": displayPersonaId,
    "displayName": displayName,
    if (displayAvatarUrl != null) "displayAvatarUrl": displayAvatarUrl!,
    "displayAvatarVersion": displayAvatarVersion,
    if (displayUserRouteId != null) "displayUserRouteId": displayUserRouteId!,
    "primaryText": primaryText,
    if (contextText != null) "contextText": contextText!,
    "previewMediaKind": previewMediaKind,
    if (previewImageUrl != null) "previewImageUrl": previewImageUrl!,
    if (previewText != null) "previewText": previewText!,
    "previewUnavailable": previewUnavailable,
    if (previewObjectId != null) "previewObjectId": previewObjectId!,
    if (previewRouteId != null) "previewRouteId": previewRouteId!,
    if (outboundShareEventId != null) "outboundShareEventId": outboundShareEventId!,
    if (shareText != null) "shareText": shareText!,
    if (impactPrimaryText != null) "impactPrimaryText": impactPrimaryText!,
    if (impactDeepLink != null) "impactDeepLink": impactDeepLink!,
    "filterKeys": filterKeys.map((value) => value).toList(growable: false),
    "createdAt": createdAt.toUtc().toIso8601String(),
    "occurredAt": occurredAt.toUtc().toIso8601String(),
    if (seenAt != null) "seenAt": seenAt!.toUtc().toIso8601String(),
    if (readAt != null) "readAt": readAt!.toUtc().toIso8601String(),
  };
}

final class ProfileInteractionReadFactAck {
  const ProfileInteractionReadFactAck({
    required this.factId,
    required this.activityId,
    required this.state,
    required this.occurredAt,
    required this.replayed,
  });

  final String factId;
  final String activityId;
  final ProfileInteractionReadState state;
  final DateTime occurredAt;
  final bool replayed;

  factory ProfileInteractionReadFactAck.fromWire(Map<String, Object?> map, [String path = "ProfileInteractionReadFactAck"]) {
    _rejectUnknownFields(map, const <String>{"factId", "activityId", "state", "occurredAt", "replayed"}, path);
    return ProfileInteractionReadFactAck(
      factId: _requiredString(map["factId"], '$path.factId'),
      activityId: _requiredString(map["activityId"], '$path.activityId'),
      state: ProfileInteractionReadState.fromWire(map["state"], '$path.state'),
      occurredAt: _requiredTimestamp(map["occurredAt"], '$path.occurredAt'),
      replayed: _requiredBool(map["replayed"], '$path.replayed'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "factId": factId,
    "activityId": activityId,
    "state": state.wireName,
    "occurredAt": occurredAt.toUtc().toIso8601String(),
    "replayed": replayed,
  };
}

final class ReceivedCommentPageSlice {
  const ReceivedCommentPageSlice({
    required this.items,
    this.nextCursor,
    required this.total,
  });

  final List<CommentListItem> items;
  final String? nextCursor;
  final int total;

  factory ReceivedCommentPageSlice.fromWire(Map<String, Object?> map, [String path = "ReceivedCommentPageSlice"]) {
    _rejectUnknownFields(map, const <String>{"items", "nextCursor", "total"}, path);
    return ReceivedCommentPageSlice(
      items: List<CommentListItem>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => CommentListItem.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      nextCursor: map["nextCursor"] == null ? null : _requiredString(map["nextCursor"], '$path.nextCursor'),
      total: _requiredInt(map["total"], '$path.total'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
    if (nextCursor != null) "nextCursor": nextCursor!,
    "total": total,
  };
}

final class ReplyPageSlice {
  const ReplyPageSlice({
    required this.items,
    this.nextCursor,
    required this.total,
  });

  final List<CommentListItem> items;
  final String? nextCursor;
  final int total;

  factory ReplyPageSlice.fromWire(Map<String, Object?> map, [String path = "ReplyPageSlice"]) {
    _rejectUnknownFields(map, const <String>{"items", "nextCursor", "total"}, path);
    return ReplyPageSlice(
      items: List<CommentListItem>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => CommentListItem.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      nextCursor: map["nextCursor"] == null ? null : _requiredString(map["nextCursor"], '$path.nextCursor'),
      total: _requiredInt(map["total"], '$path.total'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
    if (nextCursor != null) "nextCursor": nextCursor!,
    "total": total,
  };
}

final class ReportCommandResult {
  const ReportCommandResult({
    required this.id,
    required this.version,
    required this.status,
    required this.replayed,
  });

  final String id;
  final int version;
  final ReportStatus status;
  final bool replayed;

  factory ReportCommandResult.fromWire(Map<String, Object?> map, [String path = "ReportCommandResult"]) {
    _rejectUnknownFields(map, const <String>{"id", "version", "status", "replayed"}, path);
    return ReportCommandResult(
      id: _requiredString(map["id"], '$path.id'),
      version: _requiredPositiveInt(map["version"], '$path.version'),
      status: ReportStatus.fromWire(map["status"], '$path.status'),
      replayed: _requiredBool(map["replayed"], '$path.replayed'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "id": id,
    "version": version,
    "status": status.wireName,
    "replayed": replayed,
  };
}

final class ResearchReleaseReadbackView {
  const ResearchReleaseReadbackView({
    required this.releaseId,
    required this.manifestDigest,
    required this.subjectHash,
    required this.attestationIdHash,
    required this.signatureVerified,
    required this.researchBadgeVisible,
    required this.postIds,
    required this.entityRefs,
    required this.mediaAssetIds,
    required this.publicCdnDetected,
    required this.anonymousMediaUrlDetected,
  });

  final String releaseId;
  final String manifestDigest;
  final String subjectHash;
  final String attestationIdHash;
  final bool signatureVerified;
  final bool researchBadgeVisible;
  final List<String> postIds;
  final List<String> entityRefs;
  final List<String> mediaAssetIds;
  final bool publicCdnDetected;
  final bool anonymousMediaUrlDetected;

  factory ResearchReleaseReadbackView.fromWire(Map<String, Object?> map, [String path = "ResearchReleaseReadbackView"]) {
    _rejectUnknownFields(map, const <String>{"releaseId", "manifestDigest", "subjectHash", "attestationIdHash", "signatureVerified", "researchBadgeVisible", "postIds", "entityRefs", "mediaAssetIds", "publicCdnDetected", "anonymousMediaUrlDetected"}, path);
    return ResearchReleaseReadbackView(
      releaseId: _requiredNonBlankString(map["releaseId"], '$path.releaseId'),
      manifestDigest: _requiredNonBlankString(map["manifestDigest"], '$path.manifestDigest'),
      subjectHash: _requiredNonBlankString(map["subjectHash"], '$path.subjectHash'),
      attestationIdHash: _requiredNonBlankString(map["attestationIdHash"], '$path.attestationIdHash'),
      signatureVerified: _requiredBool(map["signatureVerified"], '$path.signatureVerified'),
      researchBadgeVisible: _requiredBool(map["researchBadgeVisible"], '$path.researchBadgeVisible'),
      postIds: List<String>.unmodifiable(_requiredList(map["postIds"], '$path.postIds').asMap().entries.map((entry) => _requiredString(entry.value, '$path.postIds' + '[${entry.key}]'))),
      entityRefs: List<String>.unmodifiable(_requiredList(map["entityRefs"], '$path.entityRefs').asMap().entries.map((entry) => _requiredString(entry.value, '$path.entityRefs' + '[${entry.key}]'))),
      mediaAssetIds: List<String>.unmodifiable(_requiredList(map["mediaAssetIds"], '$path.mediaAssetIds').asMap().entries.map((entry) => _requiredString(entry.value, '$path.mediaAssetIds' + '[${entry.key}]'))),
      publicCdnDetected: _requiredBool(map["publicCdnDetected"], '$path.publicCdnDetected'),
      anonymousMediaUrlDetected: _requiredBool(map["anonymousMediaUrlDetected"], '$path.anonymousMediaUrlDetected'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "releaseId": releaseId,
    "manifestDigest": manifestDigest,
    "subjectHash": subjectHash,
    "attestationIdHash": attestationIdHash,
    "signatureVerified": signatureVerified,
    "researchBadgeVisible": researchBadgeVisible,
    "postIds": postIds.map((value) => value).toList(growable: false),
    "entityRefs": entityRefs.map((value) => value).toList(growable: false),
    "mediaAssetIds": mediaAssetIds.map((value) => value).toList(growable: false),
    "publicCdnDetected": publicCdnDetected,
    "anonymousMediaUrlDetected": anonymousMediaUrlDetected,
  };
}

final class SourceAttribution {
  const SourceAttribution({
    required this.isOriginal,
    this.originalCreatorId,
    required this.originalCreatorName,
    this.originalCreatorProfileUrl,
    required this.platform,
    required this.sourcePostUrl,
    required this.originalAssetUrl,
    required this.attributionText,
    required this.rightsBasis,
    required this.commercialAuthorizationStatus,
    required this.publicationAdmission,
    this.authorizationProofUrl,
    this.termsUrl,
    this.riskAcceptanceId,
    required this.watermarkStatus,
    required this.audioRightsStatus,
    required this.modelReleaseStatus,
    required this.propertyReleaseStatus,
    required this.collectedAt,
    required this.takedownPolicy,
  });

  final bool isOriginal;
  final String? originalCreatorId;
  final String originalCreatorName;
  final String? originalCreatorProfileUrl;
  final String platform;
  final String sourcePostUrl;
  final String originalAssetUrl;
  final String attributionText;
  final String rightsBasis;
  final String commercialAuthorizationStatus;
  final String publicationAdmission;
  final String? authorizationProofUrl;
  final String? termsUrl;
  final String? riskAcceptanceId;
  final String watermarkStatus;
  final String audioRightsStatus;
  final String modelReleaseStatus;
  final String propertyReleaseStatus;
  final DateTime collectedAt;
  final String takedownPolicy;

  factory SourceAttribution.fromWire(Map<String, Object?> map, [String path = "SourceAttribution"]) {
    _rejectUnknownFields(map, const <String>{"isOriginal", "originalCreatorId", "originalCreatorName", "originalCreatorProfileUrl", "platform", "sourcePostUrl", "originalAssetUrl", "attributionText", "rightsBasis", "commercialAuthorizationStatus", "publicationAdmission", "authorizationProofUrl", "termsUrl", "riskAcceptanceId", "watermarkStatus", "audioRightsStatus", "modelReleaseStatus", "propertyReleaseStatus", "collectedAt", "takedownPolicy"}, path);
    return SourceAttribution(
      isOriginal: _requiredBool(map["isOriginal"], '$path.isOriginal'),
      originalCreatorId: map["originalCreatorId"] == null ? null : _requiredString(map["originalCreatorId"], '$path.originalCreatorId'),
      originalCreatorName: _requiredString(map["originalCreatorName"], '$path.originalCreatorName'),
      originalCreatorProfileUrl: map["originalCreatorProfileUrl"] == null ? null : _requiredString(map["originalCreatorProfileUrl"], '$path.originalCreatorProfileUrl'),
      platform: _requiredString(map["platform"], '$path.platform'),
      sourcePostUrl: _requiredString(map["sourcePostUrl"], '$path.sourcePostUrl'),
      originalAssetUrl: _requiredString(map["originalAssetUrl"], '$path.originalAssetUrl'),
      attributionText: _requiredString(map["attributionText"], '$path.attributionText'),
      rightsBasis: _requiredString(map["rightsBasis"], '$path.rightsBasis'),
      commercialAuthorizationStatus: _requiredString(map["commercialAuthorizationStatus"], '$path.commercialAuthorizationStatus'),
      publicationAdmission: _requiredString(map["publicationAdmission"], '$path.publicationAdmission'),
      authorizationProofUrl: map["authorizationProofUrl"] == null ? null : _requiredString(map["authorizationProofUrl"], '$path.authorizationProofUrl'),
      termsUrl: map["termsUrl"] == null ? null : _requiredString(map["termsUrl"], '$path.termsUrl'),
      riskAcceptanceId: map["riskAcceptanceId"] == null ? null : _requiredString(map["riskAcceptanceId"], '$path.riskAcceptanceId'),
      watermarkStatus: _requiredString(map["watermarkStatus"], '$path.watermarkStatus'),
      audioRightsStatus: _requiredString(map["audioRightsStatus"], '$path.audioRightsStatus'),
      modelReleaseStatus: _requiredString(map["modelReleaseStatus"], '$path.modelReleaseStatus'),
      propertyReleaseStatus: _requiredString(map["propertyReleaseStatus"], '$path.propertyReleaseStatus'),
      collectedAt: _requiredTimestamp(map["collectedAt"], '$path.collectedAt'),
      takedownPolicy: _requiredString(map["takedownPolicy"], '$path.takedownPolicy'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "isOriginal": isOriginal,
    if (originalCreatorId != null) "originalCreatorId": originalCreatorId!,
    "originalCreatorName": originalCreatorName,
    if (originalCreatorProfileUrl != null) "originalCreatorProfileUrl": originalCreatorProfileUrl!,
    "platform": platform,
    "sourcePostUrl": sourcePostUrl,
    "originalAssetUrl": originalAssetUrl,
    "attributionText": attributionText,
    "rightsBasis": rightsBasis,
    "commercialAuthorizationStatus": commercialAuthorizationStatus,
    "publicationAdmission": publicationAdmission,
    if (authorizationProofUrl != null) "authorizationProofUrl": authorizationProofUrl!,
    if (termsUrl != null) "termsUrl": termsUrl!,
    if (riskAcceptanceId != null) "riskAcceptanceId": riskAcceptanceId!,
    "watermarkStatus": watermarkStatus,
    "audioRightsStatus": audioRightsStatus,
    "modelReleaseStatus": modelReleaseStatus,
    "propertyReleaseStatus": propertyReleaseStatus,
    "collectedAt": collectedAt.toUtc().toIso8601String(),
    "takedownPolicy": takedownPolicy,
  };
}

AppConfigSlice decodeAppConfigSlice(Object? response) =>
    AppConfigSlice.fromWire(_requiredObject(response, "AppConfigSlice"), "AppConfigSlice");

AuthorCommentPageSlice decodeAuthorCommentPageSlice(Object? response) =>
    AuthorCommentPageSlice.fromWire(_requiredObject(response, "AuthorCommentPageSlice"), "AuthorCommentPageSlice");

AuthorImpactEvidencePage decodeAuthorImpactEvidencePage(Object? response) =>
    AuthorImpactEvidencePage.fromWire(_requiredObject(response, "AuthorImpactEvidencePage"), "AuthorImpactEvidencePage");

AuthorImpactSummary decodeAuthorImpactSummary(Object? response) =>
    AuthorImpactSummary.fromWire(_requiredObject(response, "AuthorImpactSummary"), "AuthorImpactSummary");

AuthorPostPageSlice decodeAuthorPostPageSlice(Object? response) =>
    AuthorPostPageSlice.fromWire(_requiredObject(response, "AuthorPostPageSlice"), "AuthorPostPageSlice");

CommentCommandResult decodeCommentCommandResult(Object? response) =>
    CommentCommandResult.fromWire(_requiredObject(response, "CommentCommandResult"), "CommentCommandResult");

CommentPageSlice decodeCommentPageSlice(Object? response) =>
    CommentPageSlice.fromWire(_requiredObject(response, "CommentPageSlice"), "CommentPageSlice");

ContentBehaviorReportReceipt decodeContentBehaviorReportReceipt(Object? response) =>
    ContentBehaviorReportReceipt.fromWire(_requiredObject(response, "ContentBehaviorReportReceipt"), "ContentBehaviorReportReceipt");

ContentCommentReactionCommandResult decodeContentCommentReactionCommandResult(Object? response) =>
    ContentCommentReactionCommandResult.fromWire(_requiredObject(response, "ContentCommentReactionCommandResult"), "ContentCommentReactionCommandResult");

ContentDiscoveryFeedPageSlice decodeContentDiscoveryFeedPageSlice(Object? response) =>
    ContentDiscoveryFeedPageSlice.fromWire(_requiredObject(response, "ContentDiscoveryFeedPageSlice"), "ContentDiscoveryFeedPageSlice");

ContentFootprintPageSlice decodeContentFootprintPageSlice(Object? response) =>
    ContentFootprintPageSlice.fromWire(_requiredObject(response, "ContentFootprintPageSlice"), "ContentFootprintPageSlice");

ContentPostDetailSlice decodeContentPostDetailSlice(Object? response) =>
    ContentPostDetailSlice.fromWire(_requiredObject(response, "ContentPostDetailSlice"), "ContentPostDetailSlice");

ContentReactionCommandResult decodeContentReactionCommandResult(Object? response) =>
    ContentReactionCommandResult.fromWire(_requiredObject(response, "ContentReactionCommandResult"), "ContentReactionCommandResult");

ContentReactionStateSlice decodeContentReactionStateSlice(Object? response) =>
    ContentReactionStateSlice.fromWire(_requiredObject(response, "ContentReactionStateSlice"), "ContentReactionStateSlice");

EntityWishlistState decodeEntityWishlistState(Object? response) =>
    EntityWishlistState.fromWire(_requiredObject(response, "EntityWishlistState"), "EntityWishlistState");

FilterCatalogSlice decodeFilterCatalogSlice(Object? response) =>
    FilterCatalogSlice.fromWire(_requiredObject(response, "FilterCatalogSlice"), "FilterCatalogSlice");

GatheringPostPageSlice decodeGatheringPostPageSlice(Object? response) =>
    GatheringPostPageSlice.fromWire(_requiredObject(response, "GatheringPostPageSlice"), "GatheringPostPageSlice");

GatheringSocialProofSummary decodeGatheringSocialProofSummary(Object? response) =>
    GatheringSocialProofSummary.fromWire(_requiredObject(response, "GatheringSocialProofSummary"), "GatheringSocialProofSummary");

IntersectionInboxSummary decodeIntersectionInboxSummary(Object? response) =>
    IntersectionInboxSummary.fromWire(_requiredObject(response, "IntersectionInboxSummary"), "IntersectionInboxSummary");

IntersectionReasonPageSlice decodeIntersectionReasonPageSlice(Object? response) =>
    IntersectionReasonPageSlice.fromWire(_requiredObject(response, "IntersectionReasonPageSlice"), "IntersectionReasonPageSlice");

MarkIntersectionsVisitedAck decodeMarkIntersectionsVisitedAck(Object? response) =>
    MarkIntersectionsVisitedAck.fromWire(_requiredObject(response, "MarkIntersectionsVisitedAck"), "MarkIntersectionsVisitedAck");

MediaAssetDiscardResult decodeMediaAssetDiscardResult(Object? response) =>
    MediaAssetDiscardResult.fromWire(_requiredObject(response, "MediaAssetDiscardResult"), "MediaAssetDiscardResult");

MediaAssetSlice decodeMediaAssetSlice(Object? response) =>
    MediaAssetSlice.fromWire(_requiredObject(response, "MediaAssetSlice"), "MediaAssetSlice");

MediaCoverSelectionResult decodeMediaCoverSelectionResult(Object? response) =>
    MediaCoverSelectionResult.fromWire(_requiredObject(response, "MediaCoverSelectionResult"), "MediaCoverSelectionResult");

MediaOriginalAccessGrant decodeMediaOriginalAccessGrant(Object? response) =>
    MediaOriginalAccessGrant.fromWire(_requiredObject(response, "MediaOriginalAccessGrant"), "MediaOriginalAccessGrant");

MediaUploadSessionCommandResult decodeMediaUploadSessionCommandResult(Object? response) =>
    MediaUploadSessionCommandResult.fromWire(_requiredObject(response, "MediaUploadSessionCommandResult"), "MediaUploadSessionCommandResult");

MediaUploadSessionSlice decodeMediaUploadSessionSlice(Object? response) =>
    MediaUploadSessionSlice.fromWire(_requiredObject(response, "MediaUploadSessionSlice"), "MediaUploadSessionSlice");

MyReportPageSlice decodeMyReportPageSlice(Object? response) =>
    MyReportPageSlice.fromWire(_requiredObject(response, "MyReportPageSlice"), "MyReportPageSlice");

ObjectIntersectionReasonSlice decodeObjectIntersectionReasonSlice(Object? response) =>
    ObjectIntersectionReasonSlice.fromWire(_requiredObject(response, "ObjectIntersectionReasonSlice"), "ObjectIntersectionReasonSlice");

OutboundShareFactResult decodeOutboundShareFactResult(Object? response) =>
    OutboundShareFactResult.fromWire(_requiredObject(response, "OutboundShareFactResult"), "OutboundShareFactResult");

PostDeletionReceipt decodePostDeletionReceipt(Object? response) =>
    PostDeletionReceipt.fromWire(_requiredObject(response, "PostDeletionReceipt"), "PostDeletionReceipt");

PostPublicationReceipt decodePostPublicationReceipt(Object? response) =>
    PostPublicationReceipt.fromWire(_requiredObject(response, "PostPublicationReceipt"), "PostPublicationReceipt");

ProfileInteractionActivityPageSlice decodeProfileInteractionActivityPageSlice(Object? response) =>
    ProfileInteractionActivityPageSlice.fromWire(_requiredObject(response, "ProfileInteractionActivityPageSlice"), "ProfileInteractionActivityPageSlice");

ProfileInteractionReadFactAck decodeProfileInteractionReadFactAck(Object? response) =>
    ProfileInteractionReadFactAck.fromWire(_requiredObject(response, "ProfileInteractionReadFactAck"), "ProfileInteractionReadFactAck");

ReceivedCommentPageSlice decodeReceivedCommentPageSlice(Object? response) =>
    ReceivedCommentPageSlice.fromWire(_requiredObject(response, "ReceivedCommentPageSlice"), "ReceivedCommentPageSlice");

ReplyPageSlice decodeReplyPageSlice(Object? response) =>
    ReplyPageSlice.fromWire(_requiredObject(response, "ReplyPageSlice"), "ReplyPageSlice");

ReportCommandResult decodeReportCommandResult(Object? response) =>
    ReportCommandResult.fromWire(_requiredObject(response, "ReportCommandResult"), "ReportCommandResult");

ResearchReleaseReadbackView decodeResearchReleaseReadbackView(Object? response) =>
    ResearchReleaseReadbackView.fromWire(_requiredObject(response, "ResearchReleaseReadbackView"), "ResearchReleaseReadbackView");

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

Uri _requiredUri(Object? value, String path) {
  final raw = _requiredNonBlankString(value, path);
  final parsed = Uri.tryParse(raw);
  if (parsed == null || !parsed.hasScheme) {
    throw FormatException('$path must be an absolute URI');
  }
  return parsed;
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

int _requiredPositiveInt(Object? value, String path) {
  final result = _requiredInt(value, path);
  if (result < 1) {
    throw FormatException('$path must be positive');
  }
  return result;
}

int _requiredBoundedInt(
  Object? value,
  String path, {
  int? min,
  int? max,
}) {
  final result = _requiredInt(value, path);
  if (min != null && result < min) {
    throw FormatException('$path must be at least $min');
  }
  if (max != null && result > max) {
    throw FormatException('$path must not exceed $max');
  }
  return result;
}

double _requiredDouble(Object? value, String path) {
  if (value is! num) throw FormatException('$path must be a number');
  return value.toDouble();
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
