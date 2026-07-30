// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 80b68db6b546ae955959cb31a73c5fdfb60da766b906dc9529a837191ea4a01e

part of '../../../circle/post_placement_contracts.dart';

String? _normalizeGeneratedOptionalText(String? value) {
  final normalized = value?.trim();
  return normalized == null || normalized.isEmpty ? null : normalized;
}

final class FeatureCirclePostCommand {
  FeatureCirclePostCommand({
    required String circleId,
    required String placementId,
    required bool enabled,
  }) : circleId = circleId.trim(),
       placementId = placementId.trim(),
       enabled = enabled {
    if (this.circleId.isEmpty) {
      throw ArgumentError.value(this.circleId, "circleId", 'must not be blank');
    }
    if (this.placementId.isEmpty) {
      throw ArgumentError.value(this.placementId, "placementId", 'must not be blank');
    }
  }

  final String circleId;
  final String placementId;
  final bool enabled;
}

final class PinCirclePostCommand {
  PinCirclePostCommand({
    required String circleId,
    required String placementId,
    required bool enabled,
  }) : circleId = circleId.trim(),
       placementId = placementId.trim(),
       enabled = enabled {
    if (this.circleId.isEmpty) {
      throw ArgumentError.value(this.circleId, "circleId", 'must not be blank');
    }
    if (this.placementId.isEmpty) {
      throw ArgumentError.value(this.placementId, "placementId", 'must not be blank');
    }
  }

  final String circleId;
  final String placementId;
  final bool enabled;
}

final class PlaceCirclePostCommand {
  PlaceCirclePostCommand({
    required String circleId,
    required String postId,
    String? groupId,
  }) : circleId = circleId.trim(),
       postId = postId.trim(),
       groupId = _normalizeGeneratedOptionalText(groupId) {
    if (this.circleId.isEmpty) {
      throw ArgumentError.value(this.circleId, "circleId", 'must not be blank');
    }
    if (this.postId.isEmpty) {
      throw ArgumentError.value(this.postId, "postId", 'must not be blank');
    }
  }

  final String circleId;
  final String postId;
  final String? groupId;
}

final class RemoveCirclePostCommand {
  RemoveCirclePostCommand({
    required String circleId,
    required String placementId,
  }) : circleId = circleId.trim(),
       placementId = placementId.trim() {
    if (this.circleId.isEmpty) {
      throw ArgumentError.value(this.circleId, "circleId", 'must not be blank');
    }
    if (this.placementId.isEmpty) {
      throw ArgumentError.value(this.placementId, "placementId", 'must not be blank');
    }
  }

  final String circleId;
  final String placementId;
}

CloudOperationRequestPayload encodeCircleCirclePostPlacementFeatureCirclePostGeneratedRequest(FeatureCirclePostCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
      "placementId": request.placementId,
    },
    body: <String, Object?>{
      "enabled": request.enabled,
    },
  );
}

CloudOperationRequestPayload encodeCircleCirclePostPlacementPinCirclePostGeneratedRequest(PinCirclePostCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
      "placementId": request.placementId,
    },
    body: <String, Object?>{
      "enabled": request.enabled,
    },
  );
}

CloudOperationRequestPayload encodeCircleCirclePostPlacementPlacePostInCircleGeneratedRequest(PlaceCirclePostCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
    },
    body: <String, Object?>{
      "postId": request.postId,
      if (request.groupId != null) "groupId": request.groupId!,
    },
  );
}

CloudOperationRequestPayload encodeCircleCirclePostPlacementRemovePostFromCircleGeneratedRequest(RemoveCirclePostCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "circleId": request.circleId,
      "placementId": request.placementId,
    },
  );
}

