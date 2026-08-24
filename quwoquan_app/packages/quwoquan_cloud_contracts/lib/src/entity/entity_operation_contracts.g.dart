// Code generated from canonical domain contracts. DO NOT EDIT.
// ContractGraph SHA256: de1588937c1b2c6a5f3dc4704a931120e96cb4362f0ba19031a05faa45983317

library;

import '../operation_request_payload.dart';
import "../generated/shared_operation_enums.g.dart";
import "../recommendation/recommendation_operation_contracts.g.dart";

export "../generated/shared_operation_enums.g.dart";
export "../recommendation/recommendation_operation_contracts.g.dart";

part '../generated/requests/entity/entity_operation_contracts.g.requests.g.dart';

enum HomepageClaimReviewStatus {
  pendingReview("pending_review"),
  approved("approved"),
  rejected("rejected");

  const HomepageClaimReviewStatus(this.wireName);

  final String wireName;

  static HomepageClaimReviewStatus fromWire(Object? value, String path) {
    return switch (value) {
      "pending_review" => HomepageClaimReviewStatus.pendingReview,
      "approved" => HomepageClaimReviewStatus.approved,
      "rejected" => HomepageClaimReviewStatus.rejected,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum HomepageClaimTier {
  basic("basic"),
  verified("verified");

  const HomepageClaimTier(this.wireName);

  final String wireName;

  static HomepageClaimTier fromWire(Object? value, String path) {
    return switch (value) {
      "basic" => HomepageClaimTier.basic,
      "verified" => HomepageClaimTier.verified,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum HomepageReviewStatus {
  active("active"),
  deleted("deleted");

  const HomepageReviewStatus(this.wireName);

  final String wireName;

  static HomepageReviewStatus fromWire(Object? value, String path) {
    return switch (value) {
      "active" => HomepageReviewStatus.active,
      "deleted" => HomepageReviewStatus.deleted,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum HomepageStatus {
  candidate("candidate"),
  published("published"),
  offline("offline");

  const HomepageStatus(this.wireName);

  final String wireName;

  static HomepageStatus fromWire(Object? value, String path) {
    return switch (value) {
      "candidate" => HomepageStatus.candidate,
      "published" => HomepageStatus.published,
      "offline" => HomepageStatus.offline,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum HomepageStatusReportReason {
  offline("offline"),
  incorrectInfo("incorrect_info"),
  duplicateEntry("duplicate_entry"),
  inactive("inactive");

  const HomepageStatusReportReason(this.wireName);

  final String wireName;

  static HomepageStatusReportReason fromWire(Object? value, String path) {
    return switch (value) {
      "offline" => HomepageStatusReportReason.offline,
      "incorrect_info" => HomepageStatusReportReason.incorrectInfo,
      "duplicate_entry" => HomepageStatusReportReason.duplicateEntry,
      "inactive" => HomepageStatusReportReason.inactive,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum HomepageStatusReportStatus {
  pendingReview("pending_review"),
  confirmedOffline("confirmed_offline"),
  dismissed("dismissed");

  const HomepageStatusReportStatus(this.wireName);

  final String wireName;

  static HomepageStatusReportStatus fromWire(Object? value, String path) {
    return switch (value) {
      "pending_review" => HomepageStatusReportStatus.pendingReview,
      "confirmed_offline" => HomepageStatusReportStatus.confirmedOffline,
      "dismissed" => HomepageStatusReportStatus.dismissed,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum HomepageStructuredFactField {
  openinghours("openingHours"),
  ticketpricerange("ticketPriceRange"),
  recommendeddurationminutes("recommendedDurationMinutes"),
  bestseasontagrefs("bestSeasonTagRefs"),
  altitudemeters("altitudeMeters"),
  officialwebsite("officialWebsite");

  const HomepageStructuredFactField(this.wireName);

  final String wireName;

  static HomepageStructuredFactField fromWire(Object? value, String path) {
    return switch (value) {
      "openingHours" => HomepageStructuredFactField.openinghours,
      "ticketPriceRange" => HomepageStructuredFactField.ticketpricerange,
      "recommendedDurationMinutes" => HomepageStructuredFactField.recommendeddurationminutes,
      "bestSeasonTagRefs" => HomepageStructuredFactField.bestseasontagrefs,
      "altitudeMeters" => HomepageStructuredFactField.altitudemeters,
      "officialWebsite" => HomepageStructuredFactField.officialwebsite,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum HomepageStructuredFactSourceClass {
  encyclopedia("encyclopedia"),
  officialSite("official_site"),
  governmentTourism("government_tourism");

  const HomepageStructuredFactSourceClass(this.wireName);

  final String wireName;

  static HomepageStructuredFactSourceClass fromWire(Object? value, String path) {
    return switch (value) {
      "encyclopedia" => HomepageStructuredFactSourceClass.encyclopedia,
      "official_site" => HomepageStructuredFactSourceClass.officialSite,
      "government_tourism" => HomepageStructuredFactSourceClass.governmentTourism,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum ObjectRelationEdgeType {
  authorOf("author_of"),
  postedToCircle("posted_to_circle"),
  resharedToCircle("reshared_to_circle"),
  mentionsEntity("mentions_entity"),
  commentAboutEntity("comment_about_entity"),
  circleUnderEntity("circle_under_entity"),
  memberOf("member_of"),
  reviewOf("review_of"),
  locatedIn("located_in"),
  partOf("part_of"),
  near("near"),
  routeStop("route_stop"),
  semanticCoMention("semantic_co_mention"),
  tagOverlap("tag_overlap"),
  geoProximity("geo_proximity"),
  behaviorCoEngagement("behavior_co_engagement");

  const ObjectRelationEdgeType(this.wireName);

  final String wireName;

  static ObjectRelationEdgeType fromWire(Object? value, String path) {
    return switch (value) {
      "author_of" => ObjectRelationEdgeType.authorOf,
      "posted_to_circle" => ObjectRelationEdgeType.postedToCircle,
      "reshared_to_circle" => ObjectRelationEdgeType.resharedToCircle,
      "mentions_entity" => ObjectRelationEdgeType.mentionsEntity,
      "comment_about_entity" => ObjectRelationEdgeType.commentAboutEntity,
      "circle_under_entity" => ObjectRelationEdgeType.circleUnderEntity,
      "member_of" => ObjectRelationEdgeType.memberOf,
      "review_of" => ObjectRelationEdgeType.reviewOf,
      "located_in" => ObjectRelationEdgeType.locatedIn,
      "part_of" => ObjectRelationEdgeType.partOf,
      "near" => ObjectRelationEdgeType.near,
      "route_stop" => ObjectRelationEdgeType.routeStop,
      "semantic_co_mention" => ObjectRelationEdgeType.semanticCoMention,
      "tag_overlap" => ObjectRelationEdgeType.tagOverlap,
      "geo_proximity" => ObjectRelationEdgeType.geoProximity,
      "behavior_co_engagement" => ObjectRelationEdgeType.behaviorCoEngagement,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

final class EntityImpactItem {
  const EntityImpactItem({
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

  factory EntityImpactItem.fromWire(Map<String, Object?> map, [String path = "EntityImpactItem"]) {
    _rejectUnknownFields(map, const <String>{"helpType", "action", "intersectionDimension", "tagRef", "source", "count", "primaryText", "subtitleText", "impactId", "primarySpans", "sampleVisuals", "representativeActor", "actionHints", "countTarget", "evidenceSnapshotId", "countObjectKind", "propagationPath", "iconKey"}, path);
    return EntityImpactItem(
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
  };
}

final class EntityImpactSummary {
  const EntityImpactSummary({
    required this.homepageId,
    required this.total,
    required this.items,
  });

  final String homepageId;
  final int total;
  final List<EntityImpactItem> items;

  factory EntityImpactSummary.fromWire(Map<String, Object?> map, [String path = "EntityImpactSummary"]) {
    _rejectUnknownFields(map, const <String>{"homepageId", "total", "items"}, path);
    return EntityImpactSummary(
      homepageId: _requiredString(map["homepageId"], '$path.homepageId'),
      total: _requiredInt(map["total"], '$path.total'),
      items: List<EntityImpactItem>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => EntityImpactItem.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "homepageId": homepageId,
    "total": total,
    "items": items.map((value) => value.toWire()).toList(growable: false),
  };
}

final class HomepageClaimRequestView {
  const HomepageClaimRequestView({
    required this.claimRequestId,
    required this.homepageId,
    required this.requesterPersonaId,
    required this.claimTier,
    required this.status,
    this.reviewNote,
    required this.createdAt,
    this.reviewedAt,
  });

  final String claimRequestId;
  final String homepageId;
  final String requesterPersonaId;
  final HomepageClaimTier claimTier;
  final HomepageClaimReviewStatus status;
  final String? reviewNote;
  final DateTime createdAt;
  final DateTime? reviewedAt;

  factory HomepageClaimRequestView.fromWire(Map<String, Object?> map, [String path = "HomepageClaimRequestView"]) {
    _rejectUnknownFields(map, const <String>{"claimRequestId", "homepageId", "requesterPersonaId", "claimTier", "status", "reviewNote", "createdAt", "reviewedAt"}, path);
    return HomepageClaimRequestView(
      claimRequestId: _requiredNonBlankString(map["claimRequestId"], '$path.claimRequestId'),
      homepageId: _requiredNonBlankString(map["homepageId"], '$path.homepageId'),
      requesterPersonaId: _requiredNonBlankString(map["requesterPersonaId"], '$path.requesterPersonaId'),
      claimTier: HomepageClaimTier.fromWire(map["claimTier"], '$path.claimTier'),
      status: HomepageClaimReviewStatus.fromWire(map["status"], '$path.status'),
      reviewNote: map["reviewNote"] == null ? null : _requiredString(map["reviewNote"], '$path.reviewNote'),
      createdAt: _requiredTimestamp(map["createdAt"], '$path.createdAt'),
      reviewedAt: map["reviewedAt"] == null ? null : _requiredTimestamp(map["reviewedAt"], '$path.reviewedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "claimRequestId": claimRequestId,
    "homepageId": homepageId,
    "requesterPersonaId": requesterPersonaId,
    "claimTier": claimTier.wireName,
    "status": status.wireName,
    if (reviewNote != null) "reviewNote": reviewNote!,
    "createdAt": createdAt.toUtc().toIso8601String(),
    if (reviewedAt != null) "reviewedAt": reviewedAt!.toUtc().toIso8601String(),
  };
}

final class HomepageContentPreview {
  const HomepageContentPreview({
    required this.postId,
    required this.title,
    this.summary,
    this.contentType,
    this.coverUrl,
    this.authorName,
    required this.likeCount,
    this.intersectionReasons,
  });

  final String postId;
  final String title;
  final String? summary;
  final String? contentType;
  final String? coverUrl;
  final String? authorName;
  final int likeCount;
  final List<IntersectionReason>? intersectionReasons;

  factory HomepageContentPreview.fromWire(Map<String, Object?> map, [String path = "HomepageContentPreview"]) {
    _rejectUnknownFields(map, const <String>{"postId", "title", "summary", "contentType", "coverUrl", "authorName", "likeCount", "intersectionReasons"}, path);
    return HomepageContentPreview(
      postId: _requiredString(map["postId"], '$path.postId'),
      title: _requiredString(map["title"], '$path.title'),
      summary: map["summary"] == null ? null : _requiredString(map["summary"], '$path.summary'),
      contentType: map["contentType"] == null ? null : _requiredString(map["contentType"], '$path.contentType'),
      coverUrl: map["coverUrl"] == null ? null : _requiredString(map["coverUrl"], '$path.coverUrl'),
      authorName: map["authorName"] == null ? null : _requiredString(map["authorName"], '$path.authorName'),
      likeCount: _requiredInt(map["likeCount"], '$path.likeCount'),
      intersectionReasons: map["intersectionReasons"] == null ? null : List<IntersectionReason>.unmodifiable(_requiredList(map["intersectionReasons"], '$path.intersectionReasons').asMap().entries.map((entry) => IntersectionReason.fromWire(_requiredObject(entry.value, '$path.intersectionReasons' + '[${entry.key}]'), '$path.intersectionReasons' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "postId": postId,
    "title": title,
    if (summary != null) "summary": summary!,
    if (contentType != null) "contentType": contentType!,
    if (coverUrl != null) "coverUrl": coverUrl!,
    if (authorName != null) "authorName": authorName!,
    "likeCount": likeCount,
    if (intersectionReasons != null) "intersectionReasons": intersectionReasons!.map((value) => value.toWire()).toList(growable: false),
  };
}

final class HomepageDetailView {
  const HomepageDetailView({
    required this.homepageId,
    required this.title,
    this.subtitle,
    required this.homepageType,
    required this.status,
    required this.claimStatus,
    required this.categoryTags,
    this.coverUrl,
    this.address,
    this.city,
    this.location,
    this.ownerUserId,
    this.ownerPersonaId,
    required this.viewerFollow,
    required this.verified,
    this.establishedYear,
    this.averageRating,
    required this.ratingCount,
    this.reviewSummary,
    required this.contentPreview,
    required this.questionPreview,
    required this.relatedGroups,
    this.structuredFacts,
    required this.relationEdges,
    this.assistantContext,
    this.introductionMarkdown,
    required this.introductionAssets,
    this.primarySource,
    required this.sourceUrls,
    required this.createdAt,
    required this.updatedAt,
    this.publishedAt,
    this.offlineAt,
  });

  final String homepageId;
  final String title;
  final String? subtitle;
  final String homepageType;
  final String status;
  final String claimStatus;
  final List<String> categoryTags;
  final String? coverUrl;
  final String? address;
  final String? city;
  final HomepageGeoPoint? location;
  final String? ownerUserId;
  final String? ownerPersonaId;
  final HomepageViewerFollowSlice viewerFollow;
  final bool verified;
  final int? establishedYear;
  final double? averageRating;
  final int ratingCount;
  final HomepageReviewSummaryView? reviewSummary;
  final List<HomepageContentPreview> contentPreview;
  final List<HomepageQuestionPreview> questionPreview;
  final List<HomepageRelatedGroupSummary> relatedGroups;
  final HomepageStructuredFactsView? structuredFacts;
  final List<ObjectRelationEdge> relationEdges;
  final Map<String, Object?>? assistantContext;
  final String? introductionMarkdown;
  final List<HomepageIntroductionAsset> introductionAssets;
  final HomepageSource? primarySource;
  final List<String> sourceUrls;
  final DateTime createdAt;
  final DateTime updatedAt;
  final DateTime? publishedAt;
  final DateTime? offlineAt;

  factory HomepageDetailView.fromWire(Map<String, Object?> map, [String path = "HomepageDetailView"]) {
    _rejectUnknownFields(map, const <String>{"homepageId", "title", "subtitle", "homepageType", "status", "claimStatus", "categoryTags", "coverUrl", "address", "city", "location", "ownerUserId", "ownerPersonaId", "viewerFollow", "verified", "establishedYear", "averageRating", "ratingCount", "reviewSummary", "contentPreview", "questionPreview", "relatedGroups", "structuredFacts", "relationEdges", "assistantContext", "introductionMarkdown", "introductionAssets", "primarySource", "sourceUrls", "createdAt", "updatedAt", "publishedAt", "offlineAt"}, path);
    return HomepageDetailView(
      homepageId: _requiredString(map["homepageId"], '$path.homepageId'),
      title: _requiredString(map["title"], '$path.title'),
      subtitle: map["subtitle"] == null ? null : _requiredString(map["subtitle"], '$path.subtitle'),
      homepageType: _requiredString(map["homepageType"], '$path.homepageType'),
      status: _requiredString(map["status"], '$path.status'),
      claimStatus: _requiredString(map["claimStatus"], '$path.claimStatus'),
      categoryTags: List<String>.unmodifiable(_requiredList(map["categoryTags"], '$path.categoryTags').asMap().entries.map((entry) => _requiredString(entry.value, '$path.categoryTags' + '[${entry.key}]'))),
      coverUrl: map["coverUrl"] == null ? null : _requiredString(map["coverUrl"], '$path.coverUrl'),
      address: map["address"] == null ? null : _requiredString(map["address"], '$path.address'),
      city: map["city"] == null ? null : _requiredString(map["city"], '$path.city'),
      location: map["location"] == null ? null : HomepageGeoPoint.fromWire(_requiredObject(map["location"], '$path.location'), '$path.location'),
      ownerUserId: map["ownerUserId"] == null ? null : _requiredString(map["ownerUserId"], '$path.ownerUserId'),
      ownerPersonaId: map["ownerPersonaId"] == null ? null : _requiredString(map["ownerPersonaId"], '$path.ownerPersonaId'),
      viewerFollow: HomepageViewerFollowSlice.fromWire(_requiredObject(map["viewerFollow"], '$path.viewerFollow'), '$path.viewerFollow'),
      verified: _requiredBool(map["verified"], '$path.verified'),
      establishedYear: map["establishedYear"] == null ? null : _requiredInt(map["establishedYear"], '$path.establishedYear'),
      averageRating: map["averageRating"] == null ? null : _requiredDouble(map["averageRating"], '$path.averageRating'),
      ratingCount: _requiredInt(map["ratingCount"], '$path.ratingCount'),
      reviewSummary: map["reviewSummary"] == null ? null : HomepageReviewSummaryView.fromWire(_requiredObject(map["reviewSummary"], '$path.reviewSummary'), '$path.reviewSummary'),
      contentPreview: List<HomepageContentPreview>.unmodifiable(_requiredList(map["contentPreview"], '$path.contentPreview').asMap().entries.map((entry) => HomepageContentPreview.fromWire(_requiredObject(entry.value, '$path.contentPreview' + '[${entry.key}]'), '$path.contentPreview' + '[${entry.key}]'))),
      questionPreview: List<HomepageQuestionPreview>.unmodifiable(_requiredList(map["questionPreview"], '$path.questionPreview').asMap().entries.map((entry) => HomepageQuestionPreview.fromWire(_requiredObject(entry.value, '$path.questionPreview' + '[${entry.key}]'), '$path.questionPreview' + '[${entry.key}]'))),
      relatedGroups: List<HomepageRelatedGroupSummary>.unmodifiable(_requiredList(map["relatedGroups"], '$path.relatedGroups').asMap().entries.map((entry) => HomepageRelatedGroupSummary.fromWire(_requiredObject(entry.value, '$path.relatedGroups' + '[${entry.key}]'), '$path.relatedGroups' + '[${entry.key}]'))),
      structuredFacts: map["structuredFacts"] == null ? null : HomepageStructuredFactsView.fromWire(_requiredObject(map["structuredFacts"], '$path.structuredFacts'), '$path.structuredFacts'),
      relationEdges: List<ObjectRelationEdge>.unmodifiable(_requiredList(map["relationEdges"], '$path.relationEdges').asMap().entries.map((entry) => ObjectRelationEdge.fromWire(_requiredObject(entry.value, '$path.relationEdges' + '[${entry.key}]'), '$path.relationEdges' + '[${entry.key}]'))),
      assistantContext: map["assistantContext"] == null ? null : _requiredObject(map["assistantContext"], '$path.assistantContext'),
      introductionMarkdown: map["introductionMarkdown"] == null ? null : _requiredString(map["introductionMarkdown"], '$path.introductionMarkdown'),
      introductionAssets: List<HomepageIntroductionAsset>.unmodifiable(_requiredList(map["introductionAssets"], '$path.introductionAssets').asMap().entries.map((entry) => HomepageIntroductionAsset.fromWire(_requiredObject(entry.value, '$path.introductionAssets' + '[${entry.key}]'), '$path.introductionAssets' + '[${entry.key}]'))),
      primarySource: map["primarySource"] == null ? null : HomepageSource.fromWire(_requiredObject(map["primarySource"], '$path.primarySource'), '$path.primarySource'),
      sourceUrls: List<String>.unmodifiable(_requiredList(map["sourceUrls"], '$path.sourceUrls').asMap().entries.map((entry) => _requiredString(entry.value, '$path.sourceUrls' + '[${entry.key}]'))),
      createdAt: _requiredTimestamp(map["createdAt"], '$path.createdAt'),
      updatedAt: _requiredTimestamp(map["updatedAt"], '$path.updatedAt'),
      publishedAt: map["publishedAt"] == null ? null : _requiredTimestamp(map["publishedAt"], '$path.publishedAt'),
      offlineAt: map["offlineAt"] == null ? null : _requiredTimestamp(map["offlineAt"], '$path.offlineAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "homepageId": homepageId,
    "title": title,
    if (subtitle != null) "subtitle": subtitle!,
    "homepageType": homepageType,
    "status": status,
    "claimStatus": claimStatus,
    "categoryTags": categoryTags.map((value) => value).toList(growable: false),
    if (coverUrl != null) "coverUrl": coverUrl!,
    if (address != null) "address": address!,
    if (city != null) "city": city!,
    if (location != null) "location": location!.toWire(),
    if (ownerUserId != null) "ownerUserId": ownerUserId!,
    if (ownerPersonaId != null) "ownerPersonaId": ownerPersonaId!,
    "viewerFollow": viewerFollow.toWire(),
    "verified": verified,
    if (establishedYear != null) "establishedYear": establishedYear!,
    if (averageRating != null) "averageRating": averageRating!,
    "ratingCount": ratingCount,
    if (reviewSummary != null) "reviewSummary": reviewSummary!.toWire(),
    "contentPreview": contentPreview.map((value) => value.toWire()).toList(growable: false),
    "questionPreview": questionPreview.map((value) => value.toWire()).toList(growable: false),
    "relatedGroups": relatedGroups.map((value) => value.toWire()).toList(growable: false),
    if (structuredFacts != null) "structuredFacts": structuredFacts!.toWire(),
    "relationEdges": relationEdges.map((value) => value.toWire()).toList(growable: false),
    if (assistantContext != null) "assistantContext": assistantContext!,
    if (introductionMarkdown != null) "introductionMarkdown": introductionMarkdown!,
    "introductionAssets": introductionAssets.map((value) => value.toWire()).toList(growable: false),
    if (primarySource != null) "primarySource": primarySource!.toWire(),
    "sourceUrls": sourceUrls.map((value) => value).toList(growable: false),
    "createdAt": createdAt.toUtc().toIso8601String(),
    "updatedAt": updatedAt.toUtc().toIso8601String(),
    if (publishedAt != null) "publishedAt": publishedAt!.toUtc().toIso8601String(),
    if (offlineAt != null) "offlineAt": offlineAt!.toUtc().toIso8601String(),
  };
}

final class HomepageDurationRange {
  const HomepageDurationRange({
    required this.minMinutes,
    required this.maxMinutes,
  });

  final int minMinutes;
  final int maxMinutes;

  factory HomepageDurationRange.fromWire(Map<String, Object?> map, [String path = "HomepageDurationRange"]) {
    _rejectUnknownFields(map, const <String>{"minMinutes", "maxMinutes"}, path);
    return HomepageDurationRange(
      minMinutes: _requiredInt(map["minMinutes"], '$path.minMinutes'),
      maxMinutes: _requiredInt(map["maxMinutes"], '$path.maxMinutes'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "minMinutes": minMinutes,
    "maxMinutes": maxMinutes,
  };
}

final class HomepageFactSource {
  const HomepageFactSource({
    required this.field,
    required this.sourceId,
    required this.sourceClass,
    required this.sourceUrl,
    required this.observedAt,
    required this.confidence,
    this.conflictsWithSourceIds,
  });

  final HomepageStructuredFactField field;
  final String sourceId;
  final HomepageStructuredFactSourceClass sourceClass;
  final String sourceUrl;
  final DateTime observedAt;
  final double confidence;
  final List<String>? conflictsWithSourceIds;

  factory HomepageFactSource.fromWire(Map<String, Object?> map, [String path = "HomepageFactSource"]) {
    _rejectUnknownFields(map, const <String>{"field", "sourceId", "sourceClass", "sourceUrl", "observedAt", "confidence", "conflictsWithSourceIds"}, path);
    return HomepageFactSource(
      field: HomepageStructuredFactField.fromWire(map["field"], '$path.field'),
      sourceId: _requiredString(map["sourceId"], '$path.sourceId'),
      sourceClass: HomepageStructuredFactSourceClass.fromWire(map["sourceClass"], '$path.sourceClass'),
      sourceUrl: _requiredString(map["sourceUrl"], '$path.sourceUrl'),
      observedAt: _requiredTimestamp(map["observedAt"], '$path.observedAt'),
      confidence: _requiredDouble(map["confidence"], '$path.confidence'),
      conflictsWithSourceIds: map["conflictsWithSourceIds"] == null ? null : List<String>.unmodifiable(_requiredList(map["conflictsWithSourceIds"], '$path.conflictsWithSourceIds').asMap().entries.map((entry) => _requiredString(entry.value, '$path.conflictsWithSourceIds' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "field": field.wireName,
    "sourceId": sourceId,
    "sourceClass": sourceClass.wireName,
    "sourceUrl": sourceUrl,
    "observedAt": observedAt.toUtc().toIso8601String(),
    "confidence": confidence,
    if (conflictsWithSourceIds != null) "conflictsWithSourceIds": conflictsWithSourceIds!.map((value) => value).toList(growable: false),
  };
}

final class HomepageGeoPoint {
  const HomepageGeoPoint({
    required this.latitude,
    required this.longitude,
  });

  final double latitude;
  final double longitude;

  factory HomepageGeoPoint.fromWire(Map<String, Object?> map, [String path = "HomepageGeoPoint"]) {
    _rejectUnknownFields(map, const <String>{"latitude", "longitude"}, path);
    return HomepageGeoPoint(
      latitude: _requiredDouble(map["latitude"], '$path.latitude'),
      longitude: _requiredDouble(map["longitude"], '$path.longitude'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "latitude": latitude,
    "longitude": longitude,
  };
}

final class HomepageIntroduction {
  const HomepageIntroduction({
    required this.homepageId,
    required this.displayName,
    required this.homepageType,
    this.coverUrl,
    required this.summary,
    required this.sections,
    required this.relatedObjects,
    this.primarySource,
    required this.sourceUrls,
    required this.updatedAt,
  });

  final String homepageId;
  final String displayName;
  final String homepageType;
  final String? coverUrl;
  final String summary;
  final List<HomepageIntroductionSection> sections;
  final List<HomepageRelatedGroupSummary> relatedObjects;
  final HomepageSource? primarySource;
  final List<String> sourceUrls;
  final String updatedAt;

  factory HomepageIntroduction.fromWire(Map<String, Object?> map, [String path = "HomepageIntroduction"]) {
    _rejectUnknownFields(map, const <String>{"homepageId", "displayName", "homepageType", "coverUrl", "summary", "sections", "relatedObjects", "primarySource", "sourceUrls", "updatedAt"}, path);
    return HomepageIntroduction(
      homepageId: _requiredString(map["homepageId"], '$path.homepageId'),
      displayName: _requiredString(map["displayName"], '$path.displayName'),
      homepageType: _requiredString(map["homepageType"], '$path.homepageType'),
      coverUrl: map["coverUrl"] == null ? null : _requiredString(map["coverUrl"], '$path.coverUrl'),
      summary: _requiredString(map["summary"], '$path.summary'),
      sections: List<HomepageIntroductionSection>.unmodifiable(_requiredList(map["sections"], '$path.sections').asMap().entries.map((entry) => HomepageIntroductionSection.fromWire(_requiredObject(entry.value, '$path.sections' + '[${entry.key}]'), '$path.sections' + '[${entry.key}]'))),
      relatedObjects: List<HomepageRelatedGroupSummary>.unmodifiable(_requiredList(map["relatedObjects"], '$path.relatedObjects').asMap().entries.map((entry) => HomepageRelatedGroupSummary.fromWire(_requiredObject(entry.value, '$path.relatedObjects' + '[${entry.key}]'), '$path.relatedObjects' + '[${entry.key}]'))),
      primarySource: map["primarySource"] == null ? null : HomepageSource.fromWire(_requiredObject(map["primarySource"], '$path.primarySource'), '$path.primarySource'),
      sourceUrls: List<String>.unmodifiable(_requiredList(map["sourceUrls"], '$path.sourceUrls').asMap().entries.map((entry) => _requiredString(entry.value, '$path.sourceUrls' + '[${entry.key}]'))),
      updatedAt: _requiredString(map["updatedAt"], '$path.updatedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "homepageId": homepageId,
    "displayName": displayName,
    "homepageType": homepageType,
    if (coverUrl != null) "coverUrl": coverUrl!,
    "summary": summary,
    "sections": sections.map((value) => value.toWire()).toList(growable: false),
    "relatedObjects": relatedObjects.map((value) => value.toWire()).toList(growable: false),
    if (primarySource != null) "primarySource": primarySource!.toWire(),
    "sourceUrls": sourceUrls.map((value) => value).toList(growable: false),
    "updatedAt": updatedAt,
  };
}

final class HomepageIntroductionAsset {
  const HomepageIntroductionAsset({
    required this.assetId,
    required this.url,
    this.caption,
    required this.role,
  });

  final String assetId;
  final String url;
  final String? caption;
  final String role;

  factory HomepageIntroductionAsset.fromWire(Map<String, Object?> map, [String path = "HomepageIntroductionAsset"]) {
    _rejectUnknownFields(map, const <String>{"assetId", "url", "caption", "role"}, path);
    return HomepageIntroductionAsset(
      assetId: _requiredString(map["assetId"], '$path.assetId'),
      url: _requiredString(map["url"], '$path.url'),
      caption: map["caption"] == null ? null : _requiredString(map["caption"], '$path.caption'),
      role: _requiredString(map["role"], '$path.role'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "assetId": assetId,
    "url": url,
    if (caption != null) "caption": caption!,
    "role": role,
  };
}

final class HomepageIntroductionSection {
  const HomepageIntroductionSection({
    required this.kind,
    required this.title,
    this.bodyMarkdown,
    required this.assets,
    required this.timelineItems,
  });

  final String kind;
  final String title;
  final String? bodyMarkdown;
  final List<HomepageIntroductionAsset> assets;
  final List<HomepageIntroductionTimelineItem> timelineItems;

  factory HomepageIntroductionSection.fromWire(Map<String, Object?> map, [String path = "HomepageIntroductionSection"]) {
    _rejectUnknownFields(map, const <String>{"kind", "title", "bodyMarkdown", "assets", "timelineItems"}, path);
    return HomepageIntroductionSection(
      kind: _requiredString(map["kind"], '$path.kind'),
      title: _requiredString(map["title"], '$path.title'),
      bodyMarkdown: map["bodyMarkdown"] == null ? null : _requiredString(map["bodyMarkdown"], '$path.bodyMarkdown'),
      assets: List<HomepageIntroductionAsset>.unmodifiable(_requiredList(map["assets"], '$path.assets').asMap().entries.map((entry) => HomepageIntroductionAsset.fromWire(_requiredObject(entry.value, '$path.assets' + '[${entry.key}]'), '$path.assets' + '[${entry.key}]'))),
      timelineItems: List<HomepageIntroductionTimelineItem>.unmodifiable(_requiredList(map["timelineItems"], '$path.timelineItems').asMap().entries.map((entry) => HomepageIntroductionTimelineItem.fromWire(_requiredObject(entry.value, '$path.timelineItems' + '[${entry.key}]'), '$path.timelineItems' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "kind": kind,
    "title": title,
    if (bodyMarkdown != null) "bodyMarkdown": bodyMarkdown!,
    "assets": assets.map((value) => value.toWire()).toList(growable: false),
    "timelineItems": timelineItems.map((value) => value.toWire()).toList(growable: false),
  };
}

final class HomepageIntroductionTimelineItem {
  const HomepageIntroductionTimelineItem({
    required this.dateLabel,
    required this.text,
    this.assetUrl,
  });

  final String dateLabel;
  final String text;
  final String? assetUrl;

  factory HomepageIntroductionTimelineItem.fromWire(Map<String, Object?> map, [String path = "HomepageIntroductionTimelineItem"]) {
    _rejectUnknownFields(map, const <String>{"dateLabel", "text", "assetUrl"}, path);
    return HomepageIntroductionTimelineItem(
      dateLabel: _requiredString(map["dateLabel"], '$path.dateLabel'),
      text: _requiredString(map["text"], '$path.text'),
      assetUrl: map["assetUrl"] == null ? null : _requiredString(map["assetUrl"], '$path.assetUrl'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "dateLabel": dateLabel,
    "text": text,
    if (assetUrl != null) "assetUrl": assetUrl!,
  };
}

final class HomepageOpeningHoursEntry {
  const HomepageOpeningHoursEntry({
    this.appliesFrom,
    this.appliesTo,
    this.weekdays,
    required this.openMinuteOfDay,
    required this.closeMinuteOfDay,
    required this.closed,
  });

  final String? appliesFrom;
  final String? appliesTo;
  final List<int>? weekdays;
  final int openMinuteOfDay;
  final int closeMinuteOfDay;
  final bool closed;

  factory HomepageOpeningHoursEntry.fromWire(Map<String, Object?> map, [String path = "HomepageOpeningHoursEntry"]) {
    _rejectUnknownFields(map, const <String>{"appliesFrom", "appliesTo", "weekdays", "openMinuteOfDay", "closeMinuteOfDay", "closed"}, path);
    return HomepageOpeningHoursEntry(
      appliesFrom: map["appliesFrom"] == null ? null : _requiredString(map["appliesFrom"], '$path.appliesFrom'),
      appliesTo: map["appliesTo"] == null ? null : _requiredString(map["appliesTo"], '$path.appliesTo'),
      weekdays: map["weekdays"] == null ? null : List<int>.unmodifiable(_requiredList(map["weekdays"], '$path.weekdays').asMap().entries.map((entry) => _requiredInt(entry.value, '$path.weekdays' + '[${entry.key}]'))),
      openMinuteOfDay: _requiredInt(map["openMinuteOfDay"], '$path.openMinuteOfDay'),
      closeMinuteOfDay: _requiredInt(map["closeMinuteOfDay"], '$path.closeMinuteOfDay'),
      closed: _requiredBool(map["closed"], '$path.closed'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (appliesFrom != null) "appliesFrom": appliesFrom!,
    if (appliesTo != null) "appliesTo": appliesTo!,
    if (weekdays != null) "weekdays": weekdays!.map((value) => value).toList(growable: false),
    "openMinuteOfDay": openMinuteOfDay,
    "closeMinuteOfDay": closeMinuteOfDay,
    "closed": closed,
  };
}

final class HomepageQuestionPreview {
  const HomepageQuestionPreview({
    required this.postId,
    required this.title,
    this.summary,
  });

  final String postId;
  final String title;
  final String? summary;

  factory HomepageQuestionPreview.fromWire(Map<String, Object?> map, [String path = "HomepageQuestionPreview"]) {
    _rejectUnknownFields(map, const <String>{"postId", "title", "summary"}, path);
    return HomepageQuestionPreview(
      postId: _requiredString(map["postId"], '$path.postId'),
      title: _requiredString(map["title"], '$path.title'),
      summary: map["summary"] == null ? null : _requiredString(map["summary"], '$path.summary'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "postId": postId,
    "title": title,
    if (summary != null) "summary": summary!,
  };
}

final class HomepageRelatedGroupSummary {
  const HomepageRelatedGroupSummary({
    required this.circleId,
    required this.name,
    required this.memberCount,
    this.linkedHomepageId,
    this.linkedHomepageTitle,
    required this.ownerUserId,
    required this.ownerDisplayNameSnapshot,
    required this.ownerAvatarUrlSnapshot,
    required this.evidenceSnapshotId,
  });

  final String circleId;
  final String name;
  final int memberCount;
  final String? linkedHomepageId;
  final String? linkedHomepageTitle;
  final String ownerUserId;
  final String ownerDisplayNameSnapshot;
  final String ownerAvatarUrlSnapshot;
  final String evidenceSnapshotId;

  factory HomepageRelatedGroupSummary.fromWire(Map<String, Object?> map, [String path = "HomepageRelatedGroupSummary"]) {
    _rejectUnknownFields(map, const <String>{"circleId", "name", "memberCount", "linkedHomepageId", "linkedHomepageTitle", "ownerUserId", "ownerDisplayNameSnapshot", "ownerAvatarUrlSnapshot", "evidenceSnapshotId"}, path);
    return HomepageRelatedGroupSummary(
      circleId: _requiredString(map["circleId"], '$path.circleId'),
      name: _requiredString(map["name"], '$path.name'),
      memberCount: _requiredInt(map["memberCount"], '$path.memberCount'),
      linkedHomepageId: map["linkedHomepageId"] == null ? null : _requiredString(map["linkedHomepageId"], '$path.linkedHomepageId'),
      linkedHomepageTitle: map["linkedHomepageTitle"] == null ? null : _requiredString(map["linkedHomepageTitle"], '$path.linkedHomepageTitle'),
      ownerUserId: _requiredString(map["ownerUserId"], '$path.ownerUserId'),
      ownerDisplayNameSnapshot: _requiredString(map["ownerDisplayNameSnapshot"], '$path.ownerDisplayNameSnapshot'),
      ownerAvatarUrlSnapshot: _requiredString(map["ownerAvatarUrlSnapshot"], '$path.ownerAvatarUrlSnapshot'),
      evidenceSnapshotId: _requiredString(map["evidenceSnapshotId"], '$path.evidenceSnapshotId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "circleId": circleId,
    "name": name,
    "memberCount": memberCount,
    if (linkedHomepageId != null) "linkedHomepageId": linkedHomepageId!,
    if (linkedHomepageTitle != null) "linkedHomepageTitle": linkedHomepageTitle!,
    "ownerUserId": ownerUserId,
    "ownerDisplayNameSnapshot": ownerDisplayNameSnapshot,
    "ownerAvatarUrlSnapshot": ownerAvatarUrlSnapshot,
    "evidenceSnapshotId": evidenceSnapshotId,
  };
}

final class HomepageRelatedGroupSummaryView {
  const HomepageRelatedGroupSummaryView({
    this.groups,
  });

  final List<HomepageRelatedGroupSummary>? groups;

  factory HomepageRelatedGroupSummaryView.fromWire(Map<String, Object?> map, [String path = "HomepageRelatedGroupSummaryView"]) {
    _rejectUnknownFields(map, const <String>{"groups"}, path);
    return HomepageRelatedGroupSummaryView(
      groups: map["groups"] == null ? null : List<HomepageRelatedGroupSummary>.unmodifiable(_requiredList(map["groups"], '$path.groups').asMap().entries.map((entry) => HomepageRelatedGroupSummary.fromWire(_requiredObject(entry.value, '$path.groups' + '[${entry.key}]'), '$path.groups' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (groups != null) "groups": groups!.map((value) => value.toWire()).toList(growable: false),
  };
}

final class HomepageReviewPageSlice {
  const HomepageReviewPageSlice({
    required this.items,
    this.nextCursor,
  });

  final List<HomepageReviewView> items;
  final String? nextCursor;

  factory HomepageReviewPageSlice.fromWire(Map<String, Object?> map, [String path = "HomepageReviewPageSlice"]) {
    _rejectUnknownFields(map, const <String>{"items", "nextCursor"}, path);
    return HomepageReviewPageSlice(
      items: List<HomepageReviewView>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => HomepageReviewView.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      nextCursor: map["nextCursor"] == null ? null : _requiredString(map["nextCursor"], '$path.nextCursor'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
    if (nextCursor != null) "nextCursor": nextCursor!,
  };
}

final class HomepageReviewSummaryData {
  const HomepageReviewSummaryData({
    this.averageRating,
    required this.ratingCount,
    required this.highlightTags,
  });

  final double? averageRating;
  final int ratingCount;
  final List<String> highlightTags;

  factory HomepageReviewSummaryData.fromWire(Map<String, Object?> map, [String path = "HomepageReviewSummaryData"]) {
    _rejectUnknownFields(map, const <String>{"averageRating", "ratingCount", "highlightTags"}, path);
    return HomepageReviewSummaryData(
      averageRating: map["averageRating"] == null ? null : _requiredDouble(map["averageRating"], '$path.averageRating'),
      ratingCount: _requiredInt(map["ratingCount"], '$path.ratingCount'),
      highlightTags: List<String>.unmodifiable(_requiredList(map["highlightTags"], '$path.highlightTags').asMap().entries.map((entry) => _requiredString(entry.value, '$path.highlightTags' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (averageRating != null) "averageRating": averageRating!,
    "ratingCount": ratingCount,
    "highlightTags": highlightTags.map((value) => value).toList(growable: false),
  };
}

final class HomepageReviewSummaryView {
  const HomepageReviewSummaryView({
    this.averageRating,
    required this.ratingCount,
    this.highlightTags,
  });

  final double? averageRating;
  final int ratingCount;
  final List<String>? highlightTags;

  factory HomepageReviewSummaryView.fromWire(Map<String, Object?> map, [String path = "HomepageReviewSummaryView"]) {
    _rejectUnknownFields(map, const <String>{"averageRating", "ratingCount", "highlightTags"}, path);
    return HomepageReviewSummaryView(
      averageRating: map["averageRating"] == null ? null : _requiredDouble(map["averageRating"], '$path.averageRating'),
      ratingCount: _requiredInt(map["ratingCount"], '$path.ratingCount'),
      highlightTags: map["highlightTags"] == null ? null : List<String>.unmodifiable(_requiredList(map["highlightTags"], '$path.highlightTags').asMap().entries.map((entry) => _requiredString(entry.value, '$path.highlightTags' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (averageRating != null) "averageRating": averageRating!,
    "ratingCount": ratingCount,
    if (highlightTags != null) "highlightTags": highlightTags!.map((value) => value).toList(growable: false),
  };
}

final class HomepageReviewView {
  const HomepageReviewView({
    required this.id,
    required this.homepageId,
    required this.authorPersonaId,
    required this.rating,
    required this.status,
    required this.createdAt,
    required this.updatedAt,
    this.authorDisplayNameSnapshot,
    this.authorAvatarUrlSnapshot,
    this.body,
    this.tagRefs,
  });

  final String id;
  final String homepageId;
  final String authorPersonaId;
  final int rating;
  final HomepageReviewStatus status;
  final DateTime createdAt;
  final DateTime updatedAt;
  final String? authorDisplayNameSnapshot;
  final String? authorAvatarUrlSnapshot;
  final String? body;
  final List<String>? tagRefs;

  factory HomepageReviewView.fromWire(Map<String, Object?> map, [String path = "HomepageReviewView"]) {
    _rejectUnknownFields(map, const <String>{"id", "homepageId", "authorPersonaId", "rating", "status", "createdAt", "updatedAt", "authorDisplayNameSnapshot", "authorAvatarUrlSnapshot", "body", "tagRefs"}, path);
    return HomepageReviewView(
      id: _requiredNonBlankString(map["id"], '$path.id'),
      homepageId: _requiredNonBlankString(map["homepageId"], '$path.homepageId'),
      authorPersonaId: _requiredNonBlankString(map["authorPersonaId"], '$path.authorPersonaId'),
      rating: _requiredBoundedInt(map["rating"], '$path.rating', min: 1, max: 5),
      status: HomepageReviewStatus.fromWire(map["status"], '$path.status'),
      createdAt: _requiredTimestamp(map["createdAt"], '$path.createdAt'),
      updatedAt: _requiredTimestamp(map["updatedAt"], '$path.updatedAt'),
      authorDisplayNameSnapshot: map["authorDisplayNameSnapshot"] == null ? null : _requiredString(map["authorDisplayNameSnapshot"], '$path.authorDisplayNameSnapshot'),
      authorAvatarUrlSnapshot: map["authorAvatarUrlSnapshot"] == null ? null : _requiredString(map["authorAvatarUrlSnapshot"], '$path.authorAvatarUrlSnapshot'),
      body: map["body"] == null ? null : _requiredString(map["body"], '$path.body'),
      tagRefs: map["tagRefs"] == null ? null : List<String>.unmodifiable(_requiredList(map["tagRefs"], '$path.tagRefs').asMap().entries.map((entry) => _requiredString(entry.value, '$path.tagRefs' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "id": id,
    "homepageId": homepageId,
    "authorPersonaId": authorPersonaId,
    "rating": rating,
    "status": status.wireName,
    "createdAt": createdAt.toUtc().toIso8601String(),
    "updatedAt": updatedAt.toUtc().toIso8601String(),
    if (authorDisplayNameSnapshot != null) "authorDisplayNameSnapshot": authorDisplayNameSnapshot!,
    if (authorAvatarUrlSnapshot != null) "authorAvatarUrlSnapshot": authorAvatarUrlSnapshot!,
    if (body != null) "body": body!,
    if (tagRefs != null) "tagRefs": tagRefs!.map((value) => value).toList(growable: false),
  };
}

final class HomepageSearchItemView {
  const HomepageSearchItemView({
    required this.homepageId,
    required this.canonicalEntityId,
    required this.title,
    this.subtitle,
    required this.homepageType,
    this.coverUrl,
    this.city,
    this.address,
    required this.status,
    this.averageRating,
    required this.ratingCount,
  });

  final String homepageId;
  final String canonicalEntityId;
  final String title;
  final String? subtitle;
  final HomepageType homepageType;
  final String? coverUrl;
  final String? city;
  final String? address;
  final HomepageStatus status;
  final double? averageRating;
  final int ratingCount;

  factory HomepageSearchItemView.fromWire(Map<String, Object?> map, [String path = "HomepageSearchItemView"]) {
    _rejectUnknownFields(map, const <String>{"homepageId", "canonicalEntityId", "title", "subtitle", "homepageType", "coverUrl", "city", "address", "status", "averageRating", "ratingCount"}, path);
    return HomepageSearchItemView(
      homepageId: _requiredString(map["homepageId"], '$path.homepageId'),
      canonicalEntityId: _requiredString(map["canonicalEntityId"], '$path.canonicalEntityId'),
      title: _requiredString(map["title"], '$path.title'),
      subtitle: map["subtitle"] == null ? null : _requiredString(map["subtitle"], '$path.subtitle'),
      homepageType: HomepageType.fromWire(map["homepageType"], '$path.homepageType'),
      coverUrl: map["coverUrl"] == null ? null : _requiredString(map["coverUrl"], '$path.coverUrl'),
      city: map["city"] == null ? null : _requiredString(map["city"], '$path.city'),
      address: map["address"] == null ? null : _requiredString(map["address"], '$path.address'),
      status: HomepageStatus.fromWire(map["status"], '$path.status'),
      averageRating: map["averageRating"] == null ? null : _requiredDouble(map["averageRating"], '$path.averageRating'),
      ratingCount: _requiredInt(map["ratingCount"], '$path.ratingCount'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "homepageId": homepageId,
    "canonicalEntityId": canonicalEntityId,
    "title": title,
    if (subtitle != null) "subtitle": subtitle!,
    "homepageType": homepageType.wireName,
    if (coverUrl != null) "coverUrl": coverUrl!,
    if (city != null) "city": city!,
    if (address != null) "address": address!,
    "status": status.wireName,
    if (averageRating != null) "averageRating": averageRating!,
    "ratingCount": ratingCount,
  };
}

final class HomepageSearchSlice {
  const HomepageSearchSlice({
    required this.items,
    this.nextCursor,
  });

  final List<HomepageSearchItemView> items;
  final String? nextCursor;

  factory HomepageSearchSlice.fromWire(Map<String, Object?> map, [String path = "HomepageSearchSlice"]) {
    _rejectUnknownFields(map, const <String>{"items", "nextCursor"}, path);
    return HomepageSearchSlice(
      items: List<HomepageSearchItemView>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => HomepageSearchItemView.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      nextCursor: map["nextCursor"] == null ? null : _requiredString(map["nextCursor"], '$path.nextCursor'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
    if (nextCursor != null) "nextCursor": nextCursor!,
  };
}

final class HomepageShellView {
  const HomepageShellView({
    required this.homepage,
    this.reviewSummary,
    this.contentPreview,
    this.questionPreview,
    this.relatedGroups,
  });

  final HomepageDetailView homepage;
  final HomepageReviewSummaryData? reviewSummary;
  final List<HomepageContentPreview>? contentPreview;
  final List<HomepageQuestionPreview>? questionPreview;
  final List<HomepageRelatedGroupSummary>? relatedGroups;

  factory HomepageShellView.fromWire(Map<String, Object?> map, [String path = "HomepageShellView"]) {
    _rejectUnknownFields(map, const <String>{"homepage", "reviewSummary", "contentPreview", "questionPreview", "relatedGroups"}, path);
    return HomepageShellView(
      homepage: HomepageDetailView.fromWire(_requiredObject(map["homepage"], '$path.homepage'), '$path.homepage'),
      reviewSummary: map["reviewSummary"] == null ? null : HomepageReviewSummaryData.fromWire(_requiredObject(map["reviewSummary"], '$path.reviewSummary'), '$path.reviewSummary'),
      contentPreview: map["contentPreview"] == null ? null : List<HomepageContentPreview>.unmodifiable(_requiredList(map["contentPreview"], '$path.contentPreview').asMap().entries.map((entry) => HomepageContentPreview.fromWire(_requiredObject(entry.value, '$path.contentPreview' + '[${entry.key}]'), '$path.contentPreview' + '[${entry.key}]'))),
      questionPreview: map["questionPreview"] == null ? null : List<HomepageQuestionPreview>.unmodifiable(_requiredList(map["questionPreview"], '$path.questionPreview').asMap().entries.map((entry) => HomepageQuestionPreview.fromWire(_requiredObject(entry.value, '$path.questionPreview' + '[${entry.key}]'), '$path.questionPreview' + '[${entry.key}]'))),
      relatedGroups: map["relatedGroups"] == null ? null : List<HomepageRelatedGroupSummary>.unmodifiable(_requiredList(map["relatedGroups"], '$path.relatedGroups').asMap().entries.map((entry) => HomepageRelatedGroupSummary.fromWire(_requiredObject(entry.value, '$path.relatedGroups' + '[${entry.key}]'), '$path.relatedGroups' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "homepage": homepage.toWire(),
    if (reviewSummary != null) "reviewSummary": reviewSummary!.toWire(),
    if (contentPreview != null) "contentPreview": contentPreview!.map((value) => value.toWire()).toList(growable: false),
    if (questionPreview != null) "questionPreview": questionPreview!.map((value) => value.toWire()).toList(growable: false),
    if (relatedGroups != null) "relatedGroups": relatedGroups!.map((value) => value.toWire()).toList(growable: false),
  };
}

final class HomepageSource {
  const HomepageSource({
    required this.sourceKind,
    required this.sourceUrl,
    required this.title,
    required this.fetchedAt,
    required this.snapshotHash,
    required this.policyRevision,
    required this.sourceUseMode,
  });

  final String sourceKind;
  final String sourceUrl;
  final String title;
  final String fetchedAt;
  final String snapshotHash;
  final String policyRevision;
  final String sourceUseMode;

  factory HomepageSource.fromWire(Map<String, Object?> map, [String path = "HomepageSource"]) {
    _rejectUnknownFields(map, const <String>{"sourceKind", "sourceUrl", "title", "fetchedAt", "snapshotHash", "policyRevision", "sourceUseMode"}, path);
    return HomepageSource(
      sourceKind: _requiredString(map["sourceKind"], '$path.sourceKind'),
      sourceUrl: _requiredString(map["sourceUrl"], '$path.sourceUrl'),
      title: _requiredString(map["title"], '$path.title'),
      fetchedAt: _requiredString(map["fetchedAt"], '$path.fetchedAt'),
      snapshotHash: _requiredString(map["snapshotHash"], '$path.snapshotHash'),
      policyRevision: _requiredString(map["policyRevision"], '$path.policyRevision'),
      sourceUseMode: _requiredString(map["sourceUseMode"], '$path.sourceUseMode'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "sourceKind": sourceKind,
    "sourceUrl": sourceUrl,
    "title": title,
    "fetchedAt": fetchedAt,
    "snapshotHash": snapshotHash,
    "policyRevision": policyRevision,
    "sourceUseMode": sourceUseMode,
  };
}

final class HomepageStatusReportView {
  const HomepageStatusReportView({
    required this.reportId,
    required this.homepageId,
    required this.reporterPersonaId,
    required this.reason,
    required this.status,
    this.description,
    this.evidenceUrls,
    this.reviewNote,
    required this.createdAt,
    this.reviewedAt,
  });

  final String reportId;
  final String homepageId;
  final String reporterPersonaId;
  final HomepageStatusReportReason reason;
  final HomepageStatusReportStatus status;
  final String? description;
  final List<String>? evidenceUrls;
  final String? reviewNote;
  final DateTime createdAt;
  final DateTime? reviewedAt;

  factory HomepageStatusReportView.fromWire(Map<String, Object?> map, [String path = "HomepageStatusReportView"]) {
    _rejectUnknownFields(map, const <String>{"reportId", "homepageId", "reporterPersonaId", "reason", "status", "description", "evidenceUrls", "reviewNote", "createdAt", "reviewedAt"}, path);
    return HomepageStatusReportView(
      reportId: _requiredNonBlankString(map["reportId"], '$path.reportId'),
      homepageId: _requiredNonBlankString(map["homepageId"], '$path.homepageId'),
      reporterPersonaId: _requiredNonBlankString(map["reporterPersonaId"], '$path.reporterPersonaId'),
      reason: HomepageStatusReportReason.fromWire(map["reason"], '$path.reason'),
      status: HomepageStatusReportStatus.fromWire(map["status"], '$path.status'),
      description: map["description"] == null ? null : _requiredString(map["description"], '$path.description'),
      evidenceUrls: map["evidenceUrls"] == null ? null : List<String>.unmodifiable(_requiredList(map["evidenceUrls"], '$path.evidenceUrls').asMap().entries.map((entry) => _requiredString(entry.value, '$path.evidenceUrls' + '[${entry.key}]'))),
      reviewNote: map["reviewNote"] == null ? null : _requiredString(map["reviewNote"], '$path.reviewNote'),
      createdAt: _requiredTimestamp(map["createdAt"], '$path.createdAt'),
      reviewedAt: map["reviewedAt"] == null ? null : _requiredTimestamp(map["reviewedAt"], '$path.reviewedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "reportId": reportId,
    "homepageId": homepageId,
    "reporterPersonaId": reporterPersonaId,
    "reason": reason.wireName,
    "status": status.wireName,
    if (description != null) "description": description!,
    if (evidenceUrls != null) "evidenceUrls": evidenceUrls!.map((value) => value).toList(growable: false),
    if (reviewNote != null) "reviewNote": reviewNote!,
    "createdAt": createdAt.toUtc().toIso8601String(),
    if (reviewedAt != null) "reviewedAt": reviewedAt!.toUtc().toIso8601String(),
  };
}

final class HomepageStructuredFactsView {
  const HomepageStructuredFactsView({
    this.openingHours,
    this.ticketPriceRange,
    this.recommendedDurationMinutes,
    this.bestSeasonTagRefs,
    this.altitudeMeters,
    this.officialWebsite,
    this.factSources,
  });

  final List<HomepageOpeningHoursEntry>? openingHours;
  final HomepageTicketPriceRange? ticketPriceRange;
  final HomepageDurationRange? recommendedDurationMinutes;
  final List<String>? bestSeasonTagRefs;
  final int? altitudeMeters;
  final String? officialWebsite;
  final List<HomepageFactSource>? factSources;

  factory HomepageStructuredFactsView.fromWire(Map<String, Object?> map, [String path = "HomepageStructuredFactsView"]) {
    _rejectUnknownFields(map, const <String>{"openingHours", "ticketPriceRange", "recommendedDurationMinutes", "bestSeasonTagRefs", "altitudeMeters", "officialWebsite", "factSources"}, path);
    return HomepageStructuredFactsView(
      openingHours: map["openingHours"] == null ? null : List<HomepageOpeningHoursEntry>.unmodifiable(_requiredList(map["openingHours"], '$path.openingHours').asMap().entries.map((entry) => HomepageOpeningHoursEntry.fromWire(_requiredObject(entry.value, '$path.openingHours' + '[${entry.key}]'), '$path.openingHours' + '[${entry.key}]'))),
      ticketPriceRange: map["ticketPriceRange"] == null ? null : HomepageTicketPriceRange.fromWire(_requiredObject(map["ticketPriceRange"], '$path.ticketPriceRange'), '$path.ticketPriceRange'),
      recommendedDurationMinutes: map["recommendedDurationMinutes"] == null ? null : HomepageDurationRange.fromWire(_requiredObject(map["recommendedDurationMinutes"], '$path.recommendedDurationMinutes'), '$path.recommendedDurationMinutes'),
      bestSeasonTagRefs: map["bestSeasonTagRefs"] == null ? null : List<String>.unmodifiable(_requiredList(map["bestSeasonTagRefs"], '$path.bestSeasonTagRefs').asMap().entries.map((entry) => _requiredString(entry.value, '$path.bestSeasonTagRefs' + '[${entry.key}]'))),
      altitudeMeters: map["altitudeMeters"] == null ? null : _requiredInt(map["altitudeMeters"], '$path.altitudeMeters'),
      officialWebsite: map["officialWebsite"] == null ? null : _requiredString(map["officialWebsite"], '$path.officialWebsite'),
      factSources: map["factSources"] == null ? null : List<HomepageFactSource>.unmodifiable(_requiredList(map["factSources"], '$path.factSources').asMap().entries.map((entry) => HomepageFactSource.fromWire(_requiredObject(entry.value, '$path.factSources' + '[${entry.key}]'), '$path.factSources' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (openingHours != null) "openingHours": openingHours!.map((value) => value.toWire()).toList(growable: false),
    if (ticketPriceRange != null) "ticketPriceRange": ticketPriceRange!.toWire(),
    if (recommendedDurationMinutes != null) "recommendedDurationMinutes": recommendedDurationMinutes!.toWire(),
    if (bestSeasonTagRefs != null) "bestSeasonTagRefs": bestSeasonTagRefs!.map((value) => value).toList(growable: false),
    if (altitudeMeters != null) "altitudeMeters": altitudeMeters!,
    if (officialWebsite != null) "officialWebsite": officialWebsite!,
    if (factSources != null) "factSources": factSources!.map((value) => value.toWire()).toList(growable: false),
  };
}

final class HomepageTicketPriceRange {
  const HomepageTicketPriceRange({
    required this.currency,
    required this.minAmountCents,
    required this.maxAmountCents,
    required this.free,
  });

  final String currency;
  final int minAmountCents;
  final int maxAmountCents;
  final bool free;

  factory HomepageTicketPriceRange.fromWire(Map<String, Object?> map, [String path = "HomepageTicketPriceRange"]) {
    _rejectUnknownFields(map, const <String>{"currency", "minAmountCents", "maxAmountCents", "free"}, path);
    return HomepageTicketPriceRange(
      currency: _requiredString(map["currency"], '$path.currency'),
      minAmountCents: _requiredInt(map["minAmountCents"], '$path.minAmountCents'),
      maxAmountCents: _requiredInt(map["maxAmountCents"], '$path.maxAmountCents'),
      free: _requiredBool(map["free"], '$path.free'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "currency": currency,
    "minAmountCents": minAmountCents,
    "maxAmountCents": maxAmountCents,
    "free": free,
  };
}

final class HomepageViewerFollowSlice {
  const HomepageViewerFollowSlice({
    required this.viewerFollowsHomepage,
    required this.followerCount,
  });

  final bool viewerFollowsHomepage;
  final int followerCount;

  factory HomepageViewerFollowSlice.fromWire(Map<String, Object?> map, [String path = "HomepageViewerFollowSlice"]) {
    _rejectUnknownFields(map, const <String>{"viewerFollowsHomepage", "followerCount"}, path);
    return HomepageViewerFollowSlice(
      viewerFollowsHomepage: _requiredBool(map["viewerFollowsHomepage"], '$path.viewerFollowsHomepage'),
      followerCount: _requiredInt(map["followerCount"], '$path.followerCount'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "viewerFollowsHomepage": viewerFollowsHomepage,
    "followerCount": followerCount,
  };
}

final class ObjectPageBundle {
  const ObjectPageBundle({
    required this.objectType,
    required this.objectId,
    required this.canonicalEntityId,
    required this.title,
    this.subtitle,
    this.coverUrl,
    required this.objectPageTemplate,
    required this.tagRefs,
    required this.stats,
    required this.intersectionReasons,
    required this.highlightItems,
    required this.contentSections,
    required this.relatedObjects,
    required this.relationEdges,
    this.assistantContext,
    this.rolloutContext,
  });

  final String objectType;
  final String objectId;
  final String canonicalEntityId;
  final String title;
  final String? subtitle;
  final String? coverUrl;
  final String objectPageTemplate;
  final List<String> tagRefs;
  final Map<String, Object?> stats;
  final List<IntersectionReason> intersectionReasons;
  final List<HomepageContentPreview> highlightItems;
  final Map<String, Object?> contentSections;
  final List<HomepageRelatedGroupSummary> relatedObjects;
  final List<ObjectRelationEdge> relationEdges;
  final ObjectPageContext? assistantContext;
  final ObjectPageRolloutContext? rolloutContext;

  factory ObjectPageBundle.fromWire(Map<String, Object?> map, [String path = "ObjectPageBundle"]) {
    _rejectUnknownFields(map, const <String>{"objectType", "objectId", "canonicalEntityId", "title", "subtitle", "coverUrl", "objectPageTemplate", "tagRefs", "stats", "intersectionReasons", "highlightItems", "contentSections", "relatedObjects", "relationEdges", "assistantContext", "rolloutContext"}, path);
    return ObjectPageBundle(
      objectType: _requiredString(map["objectType"], '$path.objectType'),
      objectId: _requiredString(map["objectId"], '$path.objectId'),
      canonicalEntityId: _requiredString(map["canonicalEntityId"], '$path.canonicalEntityId'),
      title: _requiredString(map["title"], '$path.title'),
      subtitle: map["subtitle"] == null ? null : _requiredString(map["subtitle"], '$path.subtitle'),
      coverUrl: map["coverUrl"] == null ? null : _requiredString(map["coverUrl"], '$path.coverUrl'),
      objectPageTemplate: _requiredString(map["objectPageTemplate"], '$path.objectPageTemplate'),
      tagRefs: List<String>.unmodifiable(_requiredList(map["tagRefs"], '$path.tagRefs').asMap().entries.map((entry) => _requiredString(entry.value, '$path.tagRefs' + '[${entry.key}]'))),
      stats: _requiredObject(map["stats"], '$path.stats'),
      intersectionReasons: List<IntersectionReason>.unmodifiable(_requiredList(map["intersectionReasons"], '$path.intersectionReasons').asMap().entries.map((entry) => IntersectionReason.fromWire(_requiredObject(entry.value, '$path.intersectionReasons' + '[${entry.key}]'), '$path.intersectionReasons' + '[${entry.key}]'))),
      highlightItems: List<HomepageContentPreview>.unmodifiable(_requiredList(map["highlightItems"], '$path.highlightItems').asMap().entries.map((entry) => HomepageContentPreview.fromWire(_requiredObject(entry.value, '$path.highlightItems' + '[${entry.key}]'), '$path.highlightItems' + '[${entry.key}]'))),
      contentSections: _requiredObject(map["contentSections"], '$path.contentSections'),
      relatedObjects: List<HomepageRelatedGroupSummary>.unmodifiable(_requiredList(map["relatedObjects"], '$path.relatedObjects').asMap().entries.map((entry) => HomepageRelatedGroupSummary.fromWire(_requiredObject(entry.value, '$path.relatedObjects' + '[${entry.key}]'), '$path.relatedObjects' + '[${entry.key}]'))),
      relationEdges: List<ObjectRelationEdge>.unmodifiable(_requiredList(map["relationEdges"], '$path.relationEdges').asMap().entries.map((entry) => ObjectRelationEdge.fromWire(_requiredObject(entry.value, '$path.relationEdges' + '[${entry.key}]'), '$path.relationEdges' + '[${entry.key}]'))),
      assistantContext: map["assistantContext"] == null ? null : ObjectPageContext.fromWire(_requiredObject(map["assistantContext"], '$path.assistantContext'), '$path.assistantContext'),
      rolloutContext: map["rolloutContext"] == null ? null : ObjectPageRolloutContext.fromWire(_requiredObject(map["rolloutContext"], '$path.rolloutContext'), '$path.rolloutContext'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "objectType": objectType,
    "objectId": objectId,
    "canonicalEntityId": canonicalEntityId,
    "title": title,
    if (subtitle != null) "subtitle": subtitle!,
    if (coverUrl != null) "coverUrl": coverUrl!,
    "objectPageTemplate": objectPageTemplate,
    "tagRefs": tagRefs.map((value) => value).toList(growable: false),
    "stats": stats,
    "intersectionReasons": intersectionReasons.map((value) => value.toWire()).toList(growable: false),
    "highlightItems": highlightItems.map((value) => value.toWire()).toList(growable: false),
    "contentSections": contentSections,
    "relatedObjects": relatedObjects.map((value) => value.toWire()).toList(growable: false),
    "relationEdges": relationEdges.map((value) => value.toWire()).toList(growable: false),
    if (assistantContext != null) "assistantContext": assistantContext!.toWire(),
    if (rolloutContext != null) "rolloutContext": rolloutContext!.toWire(),
  };
}

final class ObjectPageContext {
  const ObjectPageContext({
    required this.objectType,
    required this.objectId,
    required this.canonicalEntityId,
    required this.tagRefs,
    required this.entityRefs,
    required this.relationEdgeIds,
    required this.referralSource,
    required this.feedRequestId,
    required this.recommendationTraceId,
    required this.experimentBucket,
    required this.rolloutCohort,
  });

  final String objectType;
  final String objectId;
  final String canonicalEntityId;
  final List<String> tagRefs;
  final List<String> entityRefs;
  final List<String> relationEdgeIds;
  final String referralSource;
  final String feedRequestId;
  final String recommendationTraceId;
  final String experimentBucket;
  final String rolloutCohort;

  factory ObjectPageContext.fromWire(Map<String, Object?> map, [String path = "ObjectPageContext"]) {
    _rejectUnknownFields(map, const <String>{"objectType", "objectId", "canonicalEntityId", "tagRefs", "entityRefs", "relationEdgeIds", "referralSource", "feedRequestId", "recommendationTraceId", "experimentBucket", "rolloutCohort"}, path);
    return ObjectPageContext(
      objectType: _requiredString(map["objectType"], '$path.objectType'),
      objectId: _requiredString(map["objectId"], '$path.objectId'),
      canonicalEntityId: _requiredString(map["canonicalEntityId"], '$path.canonicalEntityId'),
      tagRefs: List<String>.unmodifiable(_requiredList(map["tagRefs"], '$path.tagRefs').asMap().entries.map((entry) => _requiredString(entry.value, '$path.tagRefs' + '[${entry.key}]'))),
      entityRefs: List<String>.unmodifiable(_requiredList(map["entityRefs"], '$path.entityRefs').asMap().entries.map((entry) => _requiredString(entry.value, '$path.entityRefs' + '[${entry.key}]'))),
      relationEdgeIds: List<String>.unmodifiable(_requiredList(map["relationEdgeIds"], '$path.relationEdgeIds').asMap().entries.map((entry) => _requiredString(entry.value, '$path.relationEdgeIds' + '[${entry.key}]'))),
      referralSource: _requiredString(map["referralSource"], '$path.referralSource'),
      feedRequestId: _requiredString(map["feedRequestId"], '$path.feedRequestId'),
      recommendationTraceId: _requiredString(map["recommendationTraceId"], '$path.recommendationTraceId'),
      experimentBucket: _requiredString(map["experimentBucket"], '$path.experimentBucket'),
      rolloutCohort: _requiredString(map["rolloutCohort"], '$path.rolloutCohort'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "objectType": objectType,
    "objectId": objectId,
    "canonicalEntityId": canonicalEntityId,
    "tagRefs": tagRefs.map((value) => value).toList(growable: false),
    "entityRefs": entityRefs.map((value) => value).toList(growable: false),
    "relationEdgeIds": relationEdgeIds.map((value) => value).toList(growable: false),
    "referralSource": referralSource,
    "feedRequestId": feedRequestId,
    "recommendationTraceId": recommendationTraceId,
    "experimentBucket": experimentBucket,
    "rolloutCohort": rolloutCohort,
  };
}

final class ObjectPageRolloutContext {
  const ObjectPageRolloutContext({
    required this.enabled,
    required this.cohort,
    required this.region,
    required this.city,
    required this.campus,
    required this.appVersion,
    required this.experimentBucket,
    required this.objectType,
    required this.assistantProactiveEnabled,
    required this.relationEvidenceEnabled,
  });

  final bool enabled;
  final String cohort;
  final String region;
  final String city;
  final String campus;
  final String appVersion;
  final String experimentBucket;
  final String objectType;
  final bool assistantProactiveEnabled;
  final bool relationEvidenceEnabled;

  factory ObjectPageRolloutContext.fromWire(Map<String, Object?> map, [String path = "ObjectPageRolloutContext"]) {
    _rejectUnknownFields(map, const <String>{"enabled", "cohort", "region", "city", "campus", "appVersion", "experimentBucket", "objectType", "assistantProactiveEnabled", "relationEvidenceEnabled"}, path);
    return ObjectPageRolloutContext(
      enabled: _requiredBool(map["enabled"], '$path.enabled'),
      cohort: _requiredString(map["cohort"], '$path.cohort'),
      region: _requiredString(map["region"], '$path.region'),
      city: _requiredString(map["city"], '$path.city'),
      campus: _requiredString(map["campus"], '$path.campus'),
      appVersion: _requiredString(map["appVersion"], '$path.appVersion'),
      experimentBucket: _requiredString(map["experimentBucket"], '$path.experimentBucket'),
      objectType: _requiredString(map["objectType"], '$path.objectType'),
      assistantProactiveEnabled: _requiredBool(map["assistantProactiveEnabled"], '$path.assistantProactiveEnabled'),
      relationEvidenceEnabled: _requiredBool(map["relationEvidenceEnabled"], '$path.relationEvidenceEnabled'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "enabled": enabled,
    "cohort": cohort,
    "region": region,
    "city": city,
    "campus": campus,
    "appVersion": appVersion,
    "experimentBucket": experimentBucket,
    "objectType": objectType,
    "assistantProactiveEnabled": assistantProactiveEnabled,
    "relationEvidenceEnabled": relationEvidenceEnabled,
  };
}

final class ObjectRelationEdge {
  const ObjectRelationEdge({
    required this.edgeId,
    required this.edgeType,
    required this.sourceObjectType,
    required this.sourceObjectId,
    required this.targetObjectType,
    required this.targetObjectId,
    required this.canonicalEntityId,
    required this.tagRefs,
    required this.evidenceRefs,
    required this.confidence,
    this.createdAt,
  });

  final String edgeId;
  final ObjectRelationEdgeType edgeType;
  final String sourceObjectType;
  final String sourceObjectId;
  final String targetObjectType;
  final String targetObjectId;
  final String canonicalEntityId;
  final List<String> tagRefs;
  final List<String> evidenceRefs;
  final double confidence;
  final DateTime? createdAt;

  factory ObjectRelationEdge.fromWire(Map<String, Object?> map, [String path = "ObjectRelationEdge"]) {
    _rejectUnknownFields(map, const <String>{"edgeId", "edgeType", "sourceObjectType", "sourceObjectId", "targetObjectType", "targetObjectId", "canonicalEntityId", "tagRefs", "evidenceRefs", "confidence", "createdAt"}, path);
    return ObjectRelationEdge(
      edgeId: _requiredString(map["edgeId"], '$path.edgeId'),
      edgeType: ObjectRelationEdgeType.fromWire(map["edgeType"], '$path.edgeType'),
      sourceObjectType: _requiredString(map["sourceObjectType"], '$path.sourceObjectType'),
      sourceObjectId: _requiredString(map["sourceObjectId"], '$path.sourceObjectId'),
      targetObjectType: _requiredString(map["targetObjectType"], '$path.targetObjectType'),
      targetObjectId: _requiredString(map["targetObjectId"], '$path.targetObjectId'),
      canonicalEntityId: _requiredString(map["canonicalEntityId"], '$path.canonicalEntityId'),
      tagRefs: List<String>.unmodifiable(_requiredList(map["tagRefs"], '$path.tagRefs').asMap().entries.map((entry) => _requiredString(entry.value, '$path.tagRefs' + '[${entry.key}]'))),
      evidenceRefs: List<String>.unmodifiable(_requiredList(map["evidenceRefs"], '$path.evidenceRefs').asMap().entries.map((entry) => _requiredString(entry.value, '$path.evidenceRefs' + '[${entry.key}]'))),
      confidence: _requiredDouble(map["confidence"], '$path.confidence'),
      createdAt: map["createdAt"] == null ? null : _requiredTimestamp(map["createdAt"], '$path.createdAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "edgeId": edgeId,
    "edgeType": edgeType.wireName,
    "sourceObjectType": sourceObjectType,
    "sourceObjectId": sourceObjectId,
    "targetObjectType": targetObjectType,
    "targetObjectId": targetObjectId,
    "canonicalEntityId": canonicalEntityId,
    "tagRefs": tagRefs.map((value) => value).toList(growable: false),
    "evidenceRefs": evidenceRefs.map((value) => value).toList(growable: false),
    "confidence": confidence,
    if (createdAt != null) "createdAt": createdAt!.toUtc().toIso8601String(),
  };
}

EntityImpactSummary decodeEntityImpactSummary(Object? response) =>
    EntityImpactSummary.fromWire(_requiredObject(response, "EntityImpactSummary"), "EntityImpactSummary");

HomepageClaimRequestView decodeHomepageClaimRequestView(Object? response) =>
    HomepageClaimRequestView.fromWire(_requiredObject(response, "HomepageClaimRequestView"), "HomepageClaimRequestView");

HomepageDetailView decodeHomepageDetailView(Object? response) =>
    HomepageDetailView.fromWire(_requiredObject(response, "HomepageDetailView"), "HomepageDetailView");

HomepageIntroduction decodeHomepageIntroduction(Object? response) =>
    HomepageIntroduction.fromWire(_requiredObject(response, "HomepageIntroduction"), "HomepageIntroduction");

HomepageRelatedGroupSummaryView decodeHomepageRelatedGroupSummaryView(Object? response) =>
    HomepageRelatedGroupSummaryView.fromWire(_requiredObject(response, "HomepageRelatedGroupSummaryView"), "HomepageRelatedGroupSummaryView");

HomepageReviewPageSlice decodeHomepageReviewPageSlice(Object? response) =>
    HomepageReviewPageSlice.fromWire(_requiredObject(response, "HomepageReviewPageSlice"), "HomepageReviewPageSlice");

HomepageReviewSummaryView decodeHomepageReviewSummaryView(Object? response) =>
    HomepageReviewSummaryView.fromWire(_requiredObject(response, "HomepageReviewSummaryView"), "HomepageReviewSummaryView");

HomepageReviewView decodeHomepageReviewView(Object? response) =>
    HomepageReviewView.fromWire(_requiredObject(response, "HomepageReviewView"), "HomepageReviewView");

HomepageSearchSlice decodeHomepageSearchSlice(Object? response) =>
    HomepageSearchSlice.fromWire(_requiredObject(response, "HomepageSearchSlice"), "HomepageSearchSlice");

HomepageShellView decodeHomepageShellView(Object? response) =>
    HomepageShellView.fromWire(_requiredObject(response, "HomepageShellView"), "HomepageShellView");

HomepageStatusReportView decodeHomepageStatusReportView(Object? response) =>
    HomepageStatusReportView.fromWire(_requiredObject(response, "HomepageStatusReportView"), "HomepageStatusReportView");

ObjectPageBundle decodeObjectPageBundle(Object? response) =>
    ObjectPageBundle.fromWire(_requiredObject(response, "ObjectPageBundle"), "ObjectPageBundle");

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
