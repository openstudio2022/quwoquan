// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 80b68db6b546ae955959cb31a73c5fdfb60da766b906dc9529a837191ea4a01e

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

