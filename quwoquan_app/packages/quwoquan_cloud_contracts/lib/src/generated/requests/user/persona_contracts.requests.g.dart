// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 07b120d8c226ad653523b7a2965cf1f9e0f43704e848966de103c40df7ab319a

part of '../../../user/persona_contracts.dart';

String? _normalizeGeneratedOptionalText(String? value) {
  final normalized = value?.trim();
  return normalized == null || normalized.isEmpty ? null : normalized;
}

final class ActivatePersonaCommand {
  ActivatePersonaCommand({
    required String personaId,
  }) : personaId = personaId.trim() {
    if (this.personaId.isEmpty) {
      throw ArgumentError.value(this.personaId, "personaId", 'must not be blank');
    }
  }

  final String personaId;

  Map<String, Object?> toJson() => <String, Object?>{
    "personaId": this.personaId,
  };
}

final class ApplyPersonaProfileSyncCommand {
  ApplyPersonaProfileSyncCommand({
    required String personaId,
    required String applyScope,
    List<String>? syncTargetIds,
    List<String>? fieldsMask,
  }) : personaId = personaId.trim(),
       applyScope = applyScope.trim(),
       syncTargetIds = syncTargetIds == null ? null : List.unmodifiable(syncTargetIds),
       fieldsMask = fieldsMask == null ? null : List.unmodifiable(fieldsMask) {
    if (this.personaId.isEmpty) {
      throw ArgumentError.value(this.personaId, "personaId", 'must not be blank');
    }
    if (this.applyScope.isEmpty) {
      throw ArgumentError.value(this.applyScope, "applyScope", 'must not be blank');
    }
  }

  final String personaId;
  final String applyScope;
  final List<String>? syncTargetIds;
  final List<String>? fieldsMask;

  Map<String, Object?> toJson() => <String, Object?>{
    "personaId": this.personaId,
    "applyScope": this.applyScope,
    if (this.syncTargetIds != null) "syncTargetIds": this.syncTargetIds!.map((value) => value).toList(growable: false),
    if (this.fieldsMask != null) "fieldsMask": this.fieldsMask!.map((value) => value).toList(growable: false),
  };
}

final class CreatePersonaCommand {
  CreatePersonaCommand({
    required String displayName,
    String? avatarUrl,
    String? isolationLevel,
    String? purposeHint,
  }) : displayName = displayName.trim(),
       avatarUrl = avatarUrl,
       isolationLevel = isolationLevel,
       purposeHint = purposeHint {
    if (this.displayName.isEmpty) {
      throw ArgumentError.value(this.displayName, "displayName", 'must not be blank');
    }
  }

  final String displayName;
  final String? avatarUrl;
  final String? isolationLevel;
  final String? purposeHint;

  Map<String, Object?> toJson() => <String, Object?>{
    "displayName": this.displayName,
    if (this.avatarUrl != null) "avatarUrl": this.avatarUrl!,
    if (this.isolationLevel != null) "isolationLevel": this.isolationLevel!,
    if (this.purposeHint != null) "purposeHint": this.purposeHint!,
  };
}

final class RetirePersonaCommand {
  RetirePersonaCommand({
    required String personaId,
  }) : personaId = personaId.trim() {
    if (this.personaId.isEmpty) {
      throw ArgumentError.value(this.personaId, "personaId", 'must not be blank');
    }
  }

  final String personaId;

  Map<String, Object?> toJson() => <String, Object?>{
    "personaId": this.personaId,
  };
}

final class UpdatePersonaCommand {
  UpdatePersonaCommand({
    required String personaId,
    String? displayName,
    String? avatarUrl,
    String? backgroundUrl,
    String? isolationLevel,
    String? purposeHint,
    String? applyScope,
    List<String>? syncTargetIds,
    List<String>? fieldsMask,
  }) : personaId = personaId.trim(),
       displayName = displayName,
       avatarUrl = avatarUrl,
       backgroundUrl = backgroundUrl,
       isolationLevel = isolationLevel,
       purposeHint = purposeHint,
       applyScope = applyScope,
       syncTargetIds = syncTargetIds == null ? null : List.unmodifiable(syncTargetIds),
       fieldsMask = fieldsMask == null ? null : List.unmodifiable(fieldsMask) {
    if (this.personaId.isEmpty) {
      throw ArgumentError.value(this.personaId, "personaId", 'must not be blank');
    }
  }

  final String personaId;
  final String? displayName;
  final String? avatarUrl;
  final String? backgroundUrl;
  final String? isolationLevel;
  final String? purposeHint;
  final String? applyScope;
  final List<String>? syncTargetIds;
  final List<String>? fieldsMask;

  Map<String, Object?> toJson() => <String, Object?>{
    "personaId": this.personaId,
    if (this.displayName != null) "displayName": this.displayName!,
    if (this.avatarUrl != null) "avatarUrl": this.avatarUrl!,
    if (this.backgroundUrl != null) "backgroundUrl": this.backgroundUrl!,
    if (this.isolationLevel != null) "isolationLevel": this.isolationLevel!,
    if (this.purposeHint != null) "purposeHint": this.purposeHint!,
    if (this.applyScope != null) "applyScope": this.applyScope!,
    if (this.syncTargetIds != null) "syncTargetIds": this.syncTargetIds!.map((value) => value).toList(growable: false),
    if (this.fieldsMask != null) "fieldsMask": this.fieldsMask!.map((value) => value).toList(growable: false),
  };
}

final class UpdateUserProfileCommand {
  UpdateUserProfileCommand({
    String? nickname,
    String? displayName,
    String? avatarAssetId,
    String? avatarUrl,
    String? backgroundAssetId,
    String? backgroundUrl,
    String? bio,
    String? gender,
    String? birthDate,
    String? regionTagRef,
    String? occupationTagRef,
    List<String>? interestTagRefs,
    String? expectedTaxonomyReleaseId,
    List<String>? identityTags,
    String? profileVisibility,
    String? applyScope,
    List<String>? syncTargetIds,
    List<String>? fieldsMask,
  }) : nickname = nickname,
       displayName = displayName,
       avatarAssetId = avatarAssetId,
       avatarUrl = avatarUrl,
       backgroundAssetId = backgroundAssetId,
       backgroundUrl = backgroundUrl,
       bio = bio,
       gender = gender,
       birthDate = birthDate,
       regionTagRef = regionTagRef,
       occupationTagRef = occupationTagRef,
       interestTagRefs = interestTagRefs == null ? null : List.unmodifiable(interestTagRefs),
       expectedTaxonomyReleaseId = _normalizeGeneratedOptionalText(expectedTaxonomyReleaseId),
       identityTags = identityTags == null ? null : List.unmodifiable(identityTags),
       profileVisibility = profileVisibility,
       applyScope = applyScope,
       syncTargetIds = syncTargetIds == null ? null : List.unmodifiable(syncTargetIds),
       fieldsMask = fieldsMask == null ? null : List.unmodifiable(fieldsMask) {
  }

  final String? nickname;
  final String? displayName;
  final String? avatarAssetId;
  final String? avatarUrl;
  final String? backgroundAssetId;
  final String? backgroundUrl;
  final String? bio;
  final String? gender;
  final String? birthDate;
  final String? regionTagRef;
  final String? occupationTagRef;
  final List<String>? interestTagRefs;
  final String? expectedTaxonomyReleaseId;
  final List<String>? identityTags;
  final String? profileVisibility;
  final String? applyScope;
  final List<String>? syncTargetIds;
  final List<String>? fieldsMask;

  Map<String, Object?> toJson() => <String, Object?>{
    if (this.nickname != null) "nickname": this.nickname!,
    if (this.displayName != null) "displayName": this.displayName!,
    if (this.avatarAssetId != null) "avatarAssetId": this.avatarAssetId!,
    if (this.avatarUrl != null) "avatarUrl": this.avatarUrl!,
    if (this.backgroundAssetId != null) "backgroundAssetId": this.backgroundAssetId!,
    if (this.backgroundUrl != null) "backgroundUrl": this.backgroundUrl!,
    if (this.bio != null) "bio": this.bio!,
    if (this.gender != null) "gender": this.gender!,
    if (this.birthDate != null) "birthDate": this.birthDate!,
    if (this.regionTagRef != null) "regionTagRef": this.regionTagRef!,
    if (this.occupationTagRef != null) "occupationTagRef": this.occupationTagRef!,
    if (this.interestTagRefs != null) "interestTagRefs": this.interestTagRefs!.map((value) => value).toList(growable: false),
    if (this.expectedTaxonomyReleaseId != null) "expectedTaxonomyReleaseId": this.expectedTaxonomyReleaseId!,
    if (this.identityTags != null) "identityTags": this.identityTags!.map((value) => value).toList(growable: false),
    if (this.profileVisibility != null) "profileVisibility": this.profileVisibility!,
    if (this.applyScope != null) "applyScope": this.applyScope!,
    if (this.syncTargetIds != null) "syncTargetIds": this.syncTargetIds!.map((value) => value).toList(growable: false),
    if (this.fieldsMask != null) "fieldsMask": this.fieldsMask!.map((value) => value).toList(growable: false),
  };
}

CloudOperationRequestPayload encodeUserPersonaActivatePersonaGeneratedRequest(ActivatePersonaCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "personaId": request.personaId,
    },
  );
}

CloudOperationRequestPayload encodeUserPersonaApplyPersonaProfileSyncGeneratedRequest(ApplyPersonaProfileSyncCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "personaId": request.personaId,
    },
    body: <String, Object?>{
      "applyScope": request.applyScope,
      if (request.syncTargetIds != null) "syncTargetIds": request.syncTargetIds!.map((value) => value).toList(growable: false),
      if (request.fieldsMask != null) "fieldsMask": request.fieldsMask!.map((value) => value).toList(growable: false),
    },
  );
}

CloudOperationRequestPayload encodeUserPersonaCreatePersonaGeneratedRequest(CreatePersonaCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "displayName": request.displayName,
      if (request.avatarUrl != null) "avatarUrl": request.avatarUrl!,
      if (request.isolationLevel != null) "isolationLevel": request.isolationLevel!,
      if (request.purposeHint != null) "purposeHint": request.purposeHint!,
    },
  );
}

CloudOperationRequestPayload encodeUserPersonaRetirePersonaGeneratedRequest(RetirePersonaCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "personaId": request.personaId,
    },
  );
}

CloudOperationRequestPayload encodeUserPersonaUpdatePersonaGeneratedRequest(UpdatePersonaCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "personaId": request.personaId,
    },
    body: <String, Object?>{
      if (request.displayName != null) "displayName": request.displayName!,
      if (request.avatarUrl != null) "avatarUrl": request.avatarUrl!,
      if (request.backgroundUrl != null) "backgroundUrl": request.backgroundUrl!,
      if (request.isolationLevel != null) "isolationLevel": request.isolationLevel!,
      if (request.purposeHint != null) "purposeHint": request.purposeHint!,
      if (request.applyScope != null) "applyScope": request.applyScope!,
      if (request.syncTargetIds != null) "syncTargetIds": request.syncTargetIds!.map((value) => value).toList(growable: false),
      if (request.fieldsMask != null) "fieldsMask": request.fieldsMask!.map((value) => value).toList(growable: false),
    },
  );
}

CloudOperationRequestPayload encodeUserPersonaUpdateUserProfileGeneratedRequest(UpdateUserProfileCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      if (request.nickname != null) "nickname": request.nickname!,
      if (request.displayName != null) "displayName": request.displayName!,
      if (request.avatarAssetId != null) "avatarAssetId": request.avatarAssetId!,
      if (request.avatarUrl != null) "avatarUrl": request.avatarUrl!,
      if (request.backgroundAssetId != null) "backgroundAssetId": request.backgroundAssetId!,
      if (request.backgroundUrl != null) "backgroundUrl": request.backgroundUrl!,
      if (request.bio != null) "bio": request.bio!,
      if (request.gender != null) "gender": request.gender!,
      if (request.birthDate != null) "birthDate": request.birthDate!,
      if (request.regionTagRef != null) "regionTagRef": request.regionTagRef!,
      if (request.occupationTagRef != null) "occupationTagRef": request.occupationTagRef!,
      if (request.interestTagRefs != null) "interestTagRefs": request.interestTagRefs!.map((value) => value).toList(growable: false),
      if (request.expectedTaxonomyReleaseId != null) "expectedTaxonomyReleaseId": request.expectedTaxonomyReleaseId!,
      if (request.identityTags != null) "identityTags": request.identityTags!.map((value) => value).toList(growable: false),
      if (request.profileVisibility != null) "profileVisibility": request.profileVisibility!,
      if (request.applyScope != null) "applyScope": request.applyScope!,
      if (request.syncTargetIds != null) "syncTargetIds": request.syncTargetIds!.map((value) => value).toList(growable: false),
      if (request.fieldsMask != null) "fieldsMask": request.fieldsMask!.map((value) => value).toList(growable: false),
    },
  );
}

