// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 07b120d8c226ad653523b7a2965cf1f9e0f43704e848966de103c40df7ab319a

part of '../../../content/media_contracts.dart';

String? _normalizeGeneratedOptionalText(String? value) {
  final normalized = value?.trim();
  return normalized == null || normalized.isEmpty ? null : normalized;
}

final class AbortContentMediaUploadCommand {
  AbortContentMediaUploadCommand({
    required String sessionId,
  }) : sessionId = sessionId.trim() {
    if (this.sessionId.isEmpty) {
      throw ArgumentError.value(this.sessionId, "sessionId", 'must not be blank');
    }
  }

  final String sessionId;

  Map<String, Object?> toJson() => <String, Object?>{
    "sessionId": this.sessionId,
  };
}

final class CompleteContentMediaUploadCommand {
  CompleteContentMediaUploadCommand({
    required String sessionId,
    ContentMediaAccessPolicy accessPolicy = ContentMediaAccessPolicy.ownerOnly,
    ContentMediaCaptureMetadata? captureMetadata,
  }) : sessionId = sessionId.trim(),
       accessPolicy = accessPolicy,
       captureMetadata = captureMetadata {
    if (this.sessionId.isEmpty) {
      throw ArgumentError.value(this.sessionId, "sessionId", 'must not be blank');
    }
  }

  final String sessionId;
  final ContentMediaAccessPolicy accessPolicy;
  final ContentMediaCaptureMetadata? captureMetadata;

  Map<String, Object?> toJson() => <String, Object?>{
    "sessionId": this.sessionId,
    "accessPolicy": switch (this.accessPolicy) { ContentMediaAccessPolicy.ownerOnly => "owner_only", ContentMediaAccessPolicy.referencedPost => "referenced_post", ContentMediaAccessPolicy.public => "public", },
    if (this.captureMetadata != null) "captureMetadata": this.captureMetadata!.toWire(),
  };
}

final class DiscardContentMediaAssetCommand {
  DiscardContentMediaAssetCommand({
    required String mediaId,
  }) : mediaId = mediaId.trim() {
    if (this.mediaId.isEmpty) {
      throw ArgumentError.value(this.mediaId, "mediaId", 'must not be blank');
    }
  }

  final String mediaId;

  Map<String, Object?> toJson() => <String, Object?>{
    "mediaId": this.mediaId,
  };
}

final class GetContentMediaAssetQuery {
  GetContentMediaAssetQuery({
    required String mediaId,
  }) : mediaId = mediaId.trim() {
    if (this.mediaId.isEmpty) {
      throw ArgumentError.value(this.mediaId, "mediaId", 'must not be blank');
    }
  }

  final String mediaId;

  Map<String, Object?> toJson() => <String, Object?>{
    "mediaId": this.mediaId,
  };
}

final class GetContentMediaUploadSessionQuery {
  GetContentMediaUploadSessionQuery({
    required String sessionId,
  }) : sessionId = sessionId.trim() {
    if (this.sessionId.isEmpty) {
      throw ArgumentError.value(this.sessionId, "sessionId", 'must not be blank');
    }
  }

  final String sessionId;

  Map<String, Object?> toJson() => <String, Object?>{
    "sessionId": this.sessionId,
  };
}

final class InitContentMediaUploadCommand {
  InitContentMediaUploadCommand({
    required ContentMediaType mediaType,
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

  final ContentMediaType mediaType;
  final String mimeType;
  final int fileSize;
  final String expectedSha256;

  Map<String, Object?> toJson() => <String, Object?>{
    "mediaType": switch (this.mediaType) { ContentMediaType.image => "image", ContentMediaType.video => "video", ContentMediaType.audio => "audio", ContentMediaType.file => "file", },
    "mimeType": this.mimeType,
    "fileSize": this.fileSize,
    "expectedSha256": this.expectedSha256,
  };
}

final class RequestContentMediaOriginalAccessCommand {
  RequestContentMediaOriginalAccessCommand({
    required String mediaId,
    ContentMediaOriginalAccessPurpose purpose = ContentMediaOriginalAccessPurpose.view,
  }) : mediaId = mediaId.trim(),
       purpose = purpose {
    if (this.mediaId.isEmpty) {
      throw ArgumentError.value(this.mediaId, "mediaId", 'must not be blank');
    }
  }

  final String mediaId;
  final ContentMediaOriginalAccessPurpose purpose;

  Map<String, Object?> toJson() => <String, Object?>{
    "mediaId": this.mediaId,
    "purpose": switch (this.purpose) { ContentMediaOriginalAccessPurpose.view => "view", ContentMediaOriginalAccessPurpose.save => "save", },
  };
}

final class SelectAutoContentMediaCoverCommand {
  SelectAutoContentMediaCoverCommand({
    required String mediaId,
  }) : mediaId = mediaId.trim() {
    if (this.mediaId.isEmpty) {
      throw ArgumentError.value(this.mediaId, "mediaId", 'must not be blank');
    }
  }

  final String mediaId;

  Map<String, Object?> toJson() => <String, Object?>{
    "mediaId": this.mediaId,
  };
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

  Map<String, Object?> toJson() => <String, Object?>{
    "mediaId": this.mediaId,
    if (this.coverAssetId != null) "coverAssetId": this.coverAssetId!,
    "coverFrameTimeMs": this.coverFrameTimeMs,
  };
}

CloudOperationRequestPayload encodeContentMediaAssetDiscardMediaAssetGeneratedRequest(DiscardContentMediaAssetCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "mediaId": request.mediaId,
    },
  );
}

CloudOperationRequestPayload encodeContentMediaAssetGetMediaAssetGeneratedRequest(GetContentMediaAssetQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "mediaId": request.mediaId,
    },
  );
}

CloudOperationRequestPayload encodeContentMediaAssetSelectAutoVideoCoverGeneratedRequest(SelectAutoContentMediaCoverCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "mediaId": request.mediaId,
    },
  );
}

CloudOperationRequestPayload encodeContentMediaAssetSelectManualVideoCoverGeneratedRequest(SelectManualContentMediaCoverCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "mediaId": request.mediaId,
    },
    body: <String, Object?>{
      if (request.coverAssetId != null) "coverAssetId": request.coverAssetId!,
      "coverFrameTimeMs": request.coverFrameTimeMs,
    },
  );
}

CloudOperationRequestPayload encodeContentMediaOriginalAccessFactRequestOriginalImageAccessGeneratedRequest(RequestContentMediaOriginalAccessCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "mediaId": request.mediaId,
    },
    body: <String, Object?>{
      "purpose": switch (request.purpose) { ContentMediaOriginalAccessPurpose.view => "view", ContentMediaOriginalAccessPurpose.save => "save", },
    },
  );
}

CloudOperationRequestPayload encodeContentMediaUploadSessionAbortMediaUploadGeneratedRequest(AbortContentMediaUploadCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "sessionId": request.sessionId,
    },
  );
}

CloudOperationRequestPayload encodeContentMediaUploadSessionCompleteMediaUploadGeneratedRequest(CompleteContentMediaUploadCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "sessionId": request.sessionId,
    },
    body: <String, Object?>{
      "accessPolicy": switch (request.accessPolicy) { ContentMediaAccessPolicy.ownerOnly => "owner_only", ContentMediaAccessPolicy.referencedPost => "referenced_post", ContentMediaAccessPolicy.public => "public", },
      if (request.captureMetadata != null) "captureMetadata": request.captureMetadata!.toWire(),
    },
  );
}

CloudOperationRequestPayload encodeContentMediaUploadSessionGetMediaUploadSessionGeneratedRequest(GetContentMediaUploadSessionQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "sessionId": request.sessionId,
    },
  );
}

CloudOperationRequestPayload encodeContentMediaUploadSessionInitMediaUploadGeneratedRequest(InitContentMediaUploadCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "mediaType": switch (request.mediaType) { ContentMediaType.image => "image", ContentMediaType.video => "video", ContentMediaType.audio => "audio", ContentMediaType.file => "file", },
      "mimeType": request.mimeType,
      "fileSize": request.fileSize,
      "expectedSha256": request.expectedSha256,
    },
  );
}

