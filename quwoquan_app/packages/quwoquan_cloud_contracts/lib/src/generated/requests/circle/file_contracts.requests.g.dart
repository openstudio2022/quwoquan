// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 07b120d8c226ad653523b7a2965cf1f9e0f43704e848966de103c40df7ab319a

part of '../../../circle/file_contracts.dart';

String? _normalizeGeneratedOptionalText(String? value) {
  final normalized = value?.trim();
  return normalized == null || normalized.isEmpty ? null : normalized;
}

final class CircleFileListQuery {
  CircleFileListQuery({
    required String circleId,
    String? groupId,
    String? parentFolderId,
    String? cursor,
    int limit = 20,
  }) : circleId = circleId.trim(),
       groupId = _normalizeGeneratedOptionalText(groupId),
       parentFolderId = _normalizeGeneratedOptionalText(parentFolderId),
       cursor = _normalizeGeneratedOptionalText(cursor),
       limit = limit {
    if (this.circleId.isEmpty) {
      throw ArgumentError.value(this.circleId, "circleId", 'must not be blank');
    }
  }

  final String circleId;
  final String? groupId;
  final String? parentFolderId;
  final String? cursor;
  final int limit;

  Map<String, Object?> toJson() => <String, Object?>{
    "circleId": this.circleId,
    if (this.groupId != null) "groupId": this.groupId!,
    if (this.parentFolderId != null) "parentFolderId": this.parentFolderId!,
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

final class CircleFileQuery {
  CircleFileQuery({
    required String circleId,
    required String fileId,
  }) : circleId = circleId.trim(),
       fileId = fileId.trim() {
    if (this.circleId.isEmpty) {
      throw ArgumentError.value(this.circleId, "circleId", 'must not be blank');
    }
    if (this.fileId.isEmpty) {
      throw ArgumentError.value(this.fileId, "fileId", 'must not be blank');
    }
  }

  final String circleId;
  final String fileId;

  Map<String, Object?> toJson() => <String, Object?>{
    "circleId": this.circleId,
    "fileId": this.fileId,
  };
}

final class CreateCircleFileCommand {
  CreateCircleFileCommand({
    required String circleId,
    String? groupId,
    String? parentFolderId,
    required String name,
    required CircleFileType fileType,
    String? assetId,
  }) : circleId = circleId.trim(),
       groupId = _normalizeGeneratedOptionalText(groupId),
       parentFolderId = _normalizeGeneratedOptionalText(parentFolderId),
       name = name.trim(),
       fileType = fileType,
       assetId = _normalizeGeneratedOptionalText(assetId) {
    if (this.circleId.isEmpty) {
      throw ArgumentError.value(this.circleId, "circleId", 'must not be blank');
    }
    if (this.name.isEmpty) {
      throw ArgumentError.value(this.name, "name", 'must not be blank');
    }
    if (this.fileType == CircleFileType.file && this.assetId == null) {
      throw ArgumentError.value(this.assetId, "assetId", "is required when fileType is file");
    }
    if (this.fileType != CircleFileType.file && this.assetId != null) {
      throw ArgumentError.value(this.assetId, "assetId", "is forbidden unless fileType is file");
    }
  }

  final String circleId;
  final String? groupId;
  final String? parentFolderId;
  final String name;
  final CircleFileType fileType;
  final String? assetId;

  Map<String, Object?> toJson() => <String, Object?>{
    "circleId": this.circleId,
    if (this.groupId != null) "groupId": this.groupId!,
    if (this.parentFolderId != null) "parentFolderId": this.parentFolderId!,
    "name": this.name,
    "fileType": switch (this.fileType) { CircleFileType.file => "file", CircleFileType.folder => "folder", },
    if (this.assetId != null) "assetId": this.assetId!,
  };
}

final class DeleteCircleFileCommand {
  DeleteCircleFileCommand({
    required String circleId,
    required String fileId,
  }) : circleId = circleId.trim(),
       fileId = fileId.trim() {
    if (this.circleId.isEmpty) {
      throw ArgumentError.value(this.circleId, "circleId", 'must not be blank');
    }
    if (this.fileId.isEmpty) {
      throw ArgumentError.value(this.fileId, "fileId", 'must not be blank');
    }
  }

  final String circleId;
  final String fileId;

  Map<String, Object?> toJson() => <String, Object?>{
    "circleId": this.circleId,
    "fileId": this.fileId,
  };
}

final class UpdateCircleFileCommand {
  UpdateCircleFileCommand({
    required String circleId,
    required String fileId,
    required int expectedVersion,
    String? parentFolderId,
    String? name,
  }) : circleId = circleId.trim(),
       fileId = fileId.trim(),
       expectedVersion = expectedVersion,
       parentFolderId = parentFolderId,
       name = name {
    if (this.circleId.isEmpty) {
      throw ArgumentError.value(this.circleId, "circleId", 'must not be blank');
    }
    if (this.fileId.isEmpty) {
      throw ArgumentError.value(this.fileId, "fileId", 'must not be blank');
    }
    if (this.expectedVersion <= 0) {
      throw ArgumentError.value(this.expectedVersion, "expectedVersion", "must be positive");
    }
  }

  final String circleId;
  final String fileId;
  final int expectedVersion;
  final String? parentFolderId;
  final String? name;

  Map<String, Object?> toJson() => <String, Object?>{
    "circleId": this.circleId,
    "fileId": this.fileId,
    "expectedVersion": '"${this.expectedVersion}"',
    if (this.parentFolderId != null) "parentFolderId": this.parentFolderId!,
    if (this.name != null) "name": this.name!,
  };
}

CloudOperationRequestPayload encodeCircleCircleFileCreateCircleFileGeneratedRequest(CreateCircleFileCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
    },
    body: <String, Object?>{
      if (request.groupId != null) "groupId": request.groupId!,
      if (request.parentFolderId != null) "parentFolderId": request.parentFolderId!,
      "name": request.name,
      "fileType": switch (request.fileType) { CircleFileType.file => "file", CircleFileType.folder => "folder", },
      if (request.assetId != null) "assetId": request.assetId!,
    },
  );
}

CloudOperationRequestPayload encodeCircleCircleFileDeleteCircleFileGeneratedRequest(DeleteCircleFileCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
      "fileId": request.fileId,
    },
  );
}

CloudOperationRequestPayload encodeCircleCircleFileGetCircleFileGeneratedRequest(CircleFileQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
      "fileId": request.fileId,
    },
  );
}

CloudOperationRequestPayload encodeCircleCircleFileListCircleFilesGeneratedRequest(CircleFileListQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
    },
    queryParameters: <String, String>{
      if (request.groupId != null) "groupId": request.groupId!,
      if (request.parentFolderId != null) "parentFolderId": request.parentFolderId!,
      if (request.cursor != null) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
    },
  );
}

CloudOperationRequestPayload encodeCircleCircleFileUpdateCircleFileGeneratedRequest(UpdateCircleFileCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
      "fileId": request.fileId,
    },
    headers: <String, String>{
      "If-Match": '"${request.expectedVersion}"',
    },
    body: <String, Object?>{
      if (request.parentFolderId != null) "parentFolderId": request.parentFolderId!,
      if (request.name != null) "name": request.name!,
    },
  );
}

