// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 80b68db6b546ae955959cb31a73c5fdfb60da766b906dc9529a837191ea4a01e

part of '../../../entity/homepage_commands.dart';

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

final class CreateHomepageClaimRequestCommand {
  CreateHomepageClaimRequestCommand({
    required String homepageId,
    required String claimTier,
    String? businessLicenseUrl,
    String? contactPhone,
    String? identityCardFrontUrl,
    String? identityCardBackUrl,
    String? note,
  }) : homepageId = homepageId.trim(),
       claimTier = claimTier.trim(),
       businessLicenseUrl = _normalizeGeneratedOptionalText(businessLicenseUrl),
       contactPhone = _normalizeGeneratedOptionalText(contactPhone),
       identityCardFrontUrl = _normalizeGeneratedOptionalText(identityCardFrontUrl),
       identityCardBackUrl = _normalizeGeneratedOptionalText(identityCardBackUrl),
       note = _normalizeGeneratedOptionalText(note) {
    if (this.homepageId.isEmpty) {
      throw ArgumentError.value(this.homepageId, "homepageId", 'must not be blank');
    }
    if (this.claimTier.isEmpty) {
      throw ArgumentError.value(this.claimTier, "claimTier", 'must not be blank');
    }
  }

  final String homepageId;
  final String claimTier;
  final String? businessLicenseUrl;
  final String? contactPhone;
  final String? identityCardFrontUrl;
  final String? identityCardBackUrl;
  final String? note;
}

final class CreateHomepageStatusReportCommand {
  CreateHomepageStatusReportCommand({
    required String homepageId,
    required String reason,
    String? description,
    List<String> evidenceUrls = const <String>[],
  }) : homepageId = homepageId.trim(),
       reason = reason.trim(),
       description = _normalizeGeneratedOptionalText(description),
       evidenceUrls = _normalizeGeneratedTextList(evidenceUrls, deduplicate: false) {
    if (this.homepageId.isEmpty) {
      throw ArgumentError.value(this.homepageId, "homepageId", 'must not be blank');
    }
    if (this.reason.isEmpty) {
      throw ArgumentError.value(this.reason, "reason", 'must not be blank');
    }
  }

  final String homepageId;
  final String reason;
  final String? description;
  final List<String> evidenceUrls;
}

final class SuggestHomepageCandidateCommand {
  SuggestHomepageCandidateCommand({
    required String title,
    required String homepageType,
    String? subtitle,
    List<String> categoryTags = const <String>[],
    String? coverUrl,
    String? address,
    String? city,
    String? sourcePlaceId,
    HomepageGeoPointInput? location,
  }) : title = title.trim(),
       homepageType = homepageType.trim(),
       subtitle = _normalizeGeneratedOptionalText(subtitle),
       categoryTags = _normalizeGeneratedTextList(categoryTags, deduplicate: false),
       coverUrl = _normalizeGeneratedOptionalText(coverUrl),
       address = _normalizeGeneratedOptionalText(address),
       city = _normalizeGeneratedOptionalText(city),
       sourcePlaceId = _normalizeGeneratedOptionalText(sourcePlaceId),
       location = location {
    if (this.title.isEmpty) {
      throw ArgumentError.value(this.title, "title", 'must not be blank');
    }
    if (this.homepageType.isEmpty) {
      throw ArgumentError.value(this.homepageType, "homepageType", 'must not be blank');
    }
  }

  final String title;
  final String homepageType;
  final String? subtitle;
  final List<String> categoryTags;
  final String? coverUrl;
  final String? address;
  final String? city;
  final String? sourcePlaceId;
  final HomepageGeoPointInput? location;
}

final class UpdateClaimedHomepageBasicsCommand {
  UpdateClaimedHomepageBasicsCommand({
    required String homepageId,
    String? title,
    String? subtitle,
    List<String>? categoryTags,
    String? coverUrl,
    String? address,
    String? city,
    HomepageGeoPointInput? location,
  }) : homepageId = homepageId.trim(),
       title = _normalizeGeneratedOptionalText(title),
       subtitle = _normalizeGeneratedOptionalText(subtitle),
       categoryTags = categoryTags == null ? null : _normalizeGeneratedTextList(categoryTags, deduplicate: false),
       coverUrl = _normalizeGeneratedOptionalText(coverUrl),
       address = _normalizeGeneratedOptionalText(address),
       city = _normalizeGeneratedOptionalText(city),
       location = location {
    if (this.homepageId.isEmpty) {
      throw ArgumentError.value(this.homepageId, "homepageId", 'must not be blank');
    }
  }

  final String homepageId;
  final String? title;
  final String? subtitle;
  final List<String>? categoryTags;
  final String? coverUrl;
  final String? address;
  final String? city;
  final HomepageGeoPointInput? location;
}

CloudOperationRequestPayload encodeEntityHomepageSuggestHomepageCandidateGeneratedRequest(SuggestHomepageCandidateCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "title": request.title,
      "homepageType": request.homepageType,
      if (request.subtitle != null) "subtitle": request.subtitle!,
      if (request.categoryTags.isNotEmpty) "categoryTags": request.categoryTags.map((value) => value).toList(growable: false),
      if (request.coverUrl != null) "coverUrl": request.coverUrl!,
      if (request.address != null) "address": request.address!,
      if (request.city != null) "city": request.city!,
      if (request.sourcePlaceId != null) "sourcePlaceId": request.sourcePlaceId!,
      if (request.location != null) "location": <String, Object?>{'lat': request.location!.lat, 'lng': request.location!.lng},
    },
  );
}

CloudOperationRequestPayload encodeEntityHomepageUpdateClaimedHomepageBasicsGeneratedRequest(UpdateClaimedHomepageBasicsCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "homepageId": request.homepageId,
    },
    body: <String, Object?>{
      if (request.title != null) "title": request.title!,
      if (request.subtitle != null) "subtitle": request.subtitle!,
      if (request.categoryTags != null) "categoryTags": request.categoryTags!.map((value) => value).toList(growable: false),
      if (request.coverUrl != null) "coverUrl": request.coverUrl!,
      if (request.address != null) "address": request.address!,
      if (request.city != null) "city": request.city!,
      if (request.location != null) "location": <String, Object?>{'lat': request.location!.lat, 'lng': request.location!.lng},
    },
  );
}

CloudOperationRequestPayload encodeEntityHomepageClaimRequestCreateHomepageClaimRequestGeneratedRequest(CreateHomepageClaimRequestCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "homepageId": request.homepageId,
    },
    body: <String, Object?>{
      "claimTier": request.claimTier,
      if (request.businessLicenseUrl != null) "businessLicenseUrl": request.businessLicenseUrl!,
      if (request.contactPhone != null) "contactPhone": request.contactPhone!,
      if (request.identityCardFrontUrl != null) "identityCardFrontUrl": request.identityCardFrontUrl!,
      if (request.identityCardBackUrl != null) "identityCardBackUrl": request.identityCardBackUrl!,
      if (request.note != null) "note": request.note!,
    },
  );
}

CloudOperationRequestPayload encodeEntityHomepageStatusReportCreateHomepageStatusReportGeneratedRequest(CreateHomepageStatusReportCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "homepageId": request.homepageId,
    },
    body: <String, Object?>{
      "reason": request.reason,
      if (request.description != null) "description": request.description!,
      if (request.evidenceUrls.isNotEmpty) "evidenceUrls": request.evidenceUrls.map((value) => value).toList(growable: false),
    },
  );
}

