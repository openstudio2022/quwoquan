// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 07b120d8c226ad653523b7a2965cf1f9e0f43704e848966de103c40df7ab319a

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

  Map<String, Object?> toJson() => <String, Object?>{
    "circleId": this.circleId,
    "placementId": this.placementId,
    "enabled": this.enabled,
  };
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

  Map<String, Object?> toJson() => <String, Object?>{
    "circleId": this.circleId,
    "placementId": this.placementId,
    "enabled": this.enabled,
  };
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

  Map<String, Object?> toJson() => <String, Object?>{
    "circleId": this.circleId,
    "postId": this.postId,
    if (this.groupId != null) "groupId": this.groupId!,
  };
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

  Map<String, Object?> toJson() => <String, Object?>{
    "circleId": this.circleId,
    "placementId": this.placementId,
  };
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

