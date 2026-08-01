// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 07b120d8c226ad653523b7a2965cf1f9e0f43704e848966de103c40df7ab319a

part of '../../../circle/circle_contracts.dart';

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

final class ArchiveCircleCommand {
  ArchiveCircleCommand({
    required String circleId,
  }) : circleId = circleId.trim() {
    if (this.circleId.isEmpty) {
      throw ArgumentError.value(this.circleId, "circleId", 'must not be blank');
    }
  }

  final String circleId;

  Map<String, Object?> toJson() => <String, Object?>{
    "circleId": this.circleId,
  };
}

final class CreateCircleCommand {
  CreateCircleCommand({
    required String name,
    String? description,
    String? rulesText,
    String? welcomeMessage,
    String? coverUrl,
    String? iconUrl,
    String? category,
    String? subCategory,
    List<String> tags = const <String>[],
    String? visibility,
    String? joinPolicy,
    String? kind,
    String? displaySubjectType,
    bool? followEnabled,
    bool? autoSyncChat,
    String? linkedHomepageId,
    String? linkedHomepageType,
    String? linkedHomepageTitle,
  }) : name = name.trim(),
       description = description,
       rulesText = rulesText,
       welcomeMessage = welcomeMessage,
       coverUrl = coverUrl,
       iconUrl = iconUrl,
       category = category,
       subCategory = subCategory,
       tags = _normalizeGeneratedTextList(tags, deduplicate: false),
       visibility = visibility,
       joinPolicy = joinPolicy,
       kind = kind,
       displaySubjectType = displaySubjectType,
       followEnabled = followEnabled,
       autoSyncChat = autoSyncChat,
       linkedHomepageId = linkedHomepageId,
       linkedHomepageType = linkedHomepageType,
       linkedHomepageTitle = linkedHomepageTitle {
    if (this.name.isEmpty) {
      throw ArgumentError.value(this.name, "name", 'must not be blank');
    }
  }

  final String name;
  final String? description;
  final String? rulesText;
  final String? welcomeMessage;
  final String? coverUrl;
  final String? iconUrl;
  final String? category;
  final String? subCategory;
  final List<String> tags;
  final String? visibility;
  final String? joinPolicy;
  final String? kind;
  final String? displaySubjectType;
  final bool? followEnabled;
  final bool? autoSyncChat;
  final String? linkedHomepageId;
  final String? linkedHomepageType;
  final String? linkedHomepageTitle;

  Map<String, Object?> toJson() => <String, Object?>{
    "name": this.name,
    if (this.description != null) "description": this.description!,
    if (this.rulesText != null) "rulesText": this.rulesText!,
    if (this.welcomeMessage != null) "welcomeMessage": this.welcomeMessage!,
    if (this.coverUrl != null) "coverUrl": this.coverUrl!,
    if (this.iconUrl != null) "iconUrl": this.iconUrl!,
    if (this.category != null) "category": this.category!,
    if (this.subCategory != null) "subCategory": this.subCategory!,
    if (this.tags.isNotEmpty) "tags": this.tags.map((value) => value).toList(growable: false),
    if (this.visibility != null) "visibility": this.visibility!,
    if (this.joinPolicy != null) "joinPolicy": this.joinPolicy!,
    if (this.kind != null) "kind": this.kind!,
    if (this.displaySubjectType != null) "displaySubjectType": this.displaySubjectType!,
    if (this.followEnabled != null) "followEnabled": this.followEnabled!,
    if (this.autoSyncChat != null) "autoSyncChat": this.autoSyncChat!,
    if (this.linkedHomepageId != null) "linkedHomepageId": this.linkedHomepageId!,
    if (this.linkedHomepageType != null) "linkedHomepageType": this.linkedHomepageType!,
    if (this.linkedHomepageTitle != null) "linkedHomepageTitle": this.linkedHomepageTitle!,
  };
}

final class UpdateCircleCommand {
  UpdateCircleCommand({
    required String circleId,
    String? name,
    String? description,
    String? rulesText,
    String? welcomeMessage,
    String? coverUrl,
    String? iconUrl,
    String? category,
    String? subCategory,
    List<String>? tags,
    String? visibility,
    String? joinPolicy,
    String? kind,
    String? displaySubjectType,
    bool? followEnabled,
    bool? autoSyncChat,
    String? linkedHomepageId,
    String? linkedHomepageType,
    String? linkedHomepageTitle,
  }) : circleId = circleId.trim(),
       name = name,
       description = description,
       rulesText = rulesText,
       welcomeMessage = welcomeMessage,
       coverUrl = coverUrl,
       iconUrl = iconUrl,
       category = category,
       subCategory = subCategory,
       tags = tags == null ? null : List.unmodifiable(tags),
       visibility = visibility,
       joinPolicy = joinPolicy,
       kind = kind,
       displaySubjectType = displaySubjectType,
       followEnabled = followEnabled,
       autoSyncChat = autoSyncChat,
       linkedHomepageId = linkedHomepageId,
       linkedHomepageType = linkedHomepageType,
       linkedHomepageTitle = linkedHomepageTitle {
    if (this.circleId.isEmpty) {
      throw ArgumentError.value(this.circleId, "circleId", 'must not be blank');
    }
  }

  final String circleId;
  final String? name;
  final String? description;
  final String? rulesText;
  final String? welcomeMessage;
  final String? coverUrl;
  final String? iconUrl;
  final String? category;
  final String? subCategory;
  final List<String>? tags;
  final String? visibility;
  final String? joinPolicy;
  final String? kind;
  final String? displaySubjectType;
  final bool? followEnabled;
  final bool? autoSyncChat;
  final String? linkedHomepageId;
  final String? linkedHomepageType;
  final String? linkedHomepageTitle;

  Map<String, Object?> toJson() => <String, Object?>{
    "circleId": this.circleId,
    if (this.name != null) "name": this.name!,
    if (this.description != null) "description": this.description!,
    if (this.rulesText != null) "rulesText": this.rulesText!,
    if (this.welcomeMessage != null) "welcomeMessage": this.welcomeMessage!,
    if (this.coverUrl != null) "coverUrl": this.coverUrl!,
    if (this.iconUrl != null) "iconUrl": this.iconUrl!,
    if (this.category != null) "category": this.category!,
    if (this.subCategory != null) "subCategory": this.subCategory!,
    if (this.tags != null) "tags": this.tags!.map((value) => value).toList(growable: false),
    if (this.visibility != null) "visibility": this.visibility!,
    if (this.joinPolicy != null) "joinPolicy": this.joinPolicy!,
    if (this.kind != null) "kind": this.kind!,
    if (this.displaySubjectType != null) "displaySubjectType": this.displaySubjectType!,
    if (this.followEnabled != null) "followEnabled": this.followEnabled!,
    if (this.autoSyncChat != null) "autoSyncChat": this.autoSyncChat!,
    if (this.linkedHomepageId != null) "linkedHomepageId": this.linkedHomepageId!,
    if (this.linkedHomepageType != null) "linkedHomepageType": this.linkedHomepageType!,
    if (this.linkedHomepageTitle != null) "linkedHomepageTitle": this.linkedHomepageTitle!,
  };
}

final class UpdateCircleSectionsCommand {
  UpdateCircleSectionsCommand({
    required String circleId,
    required List<CircleSectionConfigInput> sections,
  }) : circleId = circleId.trim(),
       sections = List.unmodifiable(sections) {
    if (this.circleId.isEmpty) {
      throw ArgumentError.value(this.circleId, "circleId", 'must not be blank');
    }
    if (this.sections.isEmpty) {
      throw ArgumentError.value(this.sections, "sections", 'must not be blank');
    }
  }

  final String circleId;
  final List<CircleSectionConfigInput> sections;

  Map<String, Object?> toJson() => <String, Object?>{
    "circleId": this.circleId,
    "sections": this.sections.map((value) => <String, Object?>{'sectionType': value.sectionType, 'visible': value.visible, 'order': value.order, if (value.customTitle != null) 'customTitle': value.customTitle}).toList(growable: false),
  };
}

CloudOperationRequestPayload encodeCircleCircleArchiveCircleGeneratedRequest(ArchiveCircleCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
    },
  );
}

CloudOperationRequestPayload encodeCircleCircleCreateCircleGeneratedRequest(CreateCircleCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "name": request.name,
      if (request.description != null) "description": request.description!,
      if (request.rulesText != null) "rulesText": request.rulesText!,
      if (request.welcomeMessage != null) "welcomeMessage": request.welcomeMessage!,
      if (request.coverUrl != null) "coverUrl": request.coverUrl!,
      if (request.iconUrl != null) "iconUrl": request.iconUrl!,
      if (request.category != null) "category": request.category!,
      if (request.subCategory != null) "subCategory": request.subCategory!,
      if (request.tags.isNotEmpty) "tags": request.tags.map((value) => value).toList(growable: false),
      if (request.visibility != null) "visibility": request.visibility!,
      if (request.joinPolicy != null) "joinPolicy": request.joinPolicy!,
      if (request.kind != null) "kind": request.kind!,
      if (request.displaySubjectType != null) "displaySubjectType": request.displaySubjectType!,
      if (request.followEnabled != null) "followEnabled": request.followEnabled!,
      if (request.autoSyncChat != null) "autoSyncChat": request.autoSyncChat!,
      if (request.linkedHomepageId != null) "linkedHomepageId": request.linkedHomepageId!,
      if (request.linkedHomepageType != null) "linkedHomepageType": request.linkedHomepageType!,
      if (request.linkedHomepageTitle != null) "linkedHomepageTitle": request.linkedHomepageTitle!,
    },
  );
}

CloudOperationRequestPayload encodeCircleCircleUpdateCircleGeneratedRequest(UpdateCircleCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
    },
    body: <String, Object?>{
      if (request.name != null) "name": request.name!,
      if (request.description != null) "description": request.description!,
      if (request.rulesText != null) "rulesText": request.rulesText!,
      if (request.welcomeMessage != null) "welcomeMessage": request.welcomeMessage!,
      if (request.coverUrl != null) "coverUrl": request.coverUrl!,
      if (request.iconUrl != null) "iconUrl": request.iconUrl!,
      if (request.category != null) "category": request.category!,
      if (request.subCategory != null) "subCategory": request.subCategory!,
      if (request.tags != null) "tags": request.tags!.map((value) => value).toList(growable: false),
      if (request.visibility != null) "visibility": request.visibility!,
      if (request.joinPolicy != null) "joinPolicy": request.joinPolicy!,
      if (request.kind != null) "kind": request.kind!,
      if (request.displaySubjectType != null) "displaySubjectType": request.displaySubjectType!,
      if (request.followEnabled != null) "followEnabled": request.followEnabled!,
      if (request.autoSyncChat != null) "autoSyncChat": request.autoSyncChat!,
      if (request.linkedHomepageId != null) "linkedHomepageId": request.linkedHomepageId!,
      if (request.linkedHomepageType != null) "linkedHomepageType": request.linkedHomepageType!,
      if (request.linkedHomepageTitle != null) "linkedHomepageTitle": request.linkedHomepageTitle!,
    },
  );
}

CloudOperationRequestPayload encodeCircleCircleUpdateCircleSectionsGeneratedRequest(UpdateCircleSectionsCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
    },
    body: <String, Object?>{
      "sections": request.sections.map((value) => <String, Object?>{'sectionType': value.sectionType, 'visible': value.visible, 'order': value.order, if (value.customTitle != null) 'customTitle': value.customTitle}).toList(growable: false),
    },
  );
}

