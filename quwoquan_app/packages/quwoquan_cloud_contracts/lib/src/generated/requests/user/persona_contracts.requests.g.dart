// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 80b68db6b546ae955959cb31a73c5fdfb60da766b906dc9529a837191ea4a01e

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

