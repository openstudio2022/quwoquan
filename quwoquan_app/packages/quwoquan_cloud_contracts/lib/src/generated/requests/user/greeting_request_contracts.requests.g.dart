// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 07b120d8c226ad653523b7a2965cf1f9e0f43704e848966de103c40df7ab319a

part of '../../../user/greeting_request_contracts.dart';

String? _normalizeGeneratedOptionalText(String? value) {
  final normalized = value?.trim();
  return normalized == null || normalized.isEmpty ? null : normalized;
}

final class CancelGreetingCommand {
  CancelGreetingCommand({
    required String requestId,
  }) : requestId = requestId.trim() {
    if (this.requestId.isEmpty) {
      throw ArgumentError.value(this.requestId, "requestId", 'must not be blank');
    }
  }

  final String requestId;

  Map<String, Object?> toJson() => <String, Object?>{
    "requestId": this.requestId,
  };
}

final class IgnoreGreetingCommand {
  IgnoreGreetingCommand({
    required String requestId,
  }) : requestId = requestId.trim() {
    if (this.requestId.isEmpty) {
      throw ArgumentError.value(this.requestId, "requestId", 'must not be blank');
    }
  }

  final String requestId;

  Map<String, Object?> toJson() => <String, Object?>{
    "requestId": this.requestId,
  };
}

final class ListGreetingRequestsQuery {
  const ListGreetingRequestsQuery({
    String status = 'pending',
    String? cursor,
    int limit = 20,
  }) : status = status,
       cursor = cursor,
       limit = limit;

  final String status;
  final String? cursor;
  final int limit;

  Map<String, Object?> toJson() => <String, Object?>{
    if (this.status.isNotEmpty) "status": this.status,
    if (this.cursor?.isNotEmpty == true) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

final class ReplyGreetingCommand {
  ReplyGreetingCommand({
    required String requestId,
  }) : requestId = requestId.trim() {
    if (this.requestId.isEmpty) {
      throw ArgumentError.value(this.requestId, "requestId", 'must not be blank');
    }
  }

  final String requestId;

  Map<String, Object?> toJson() => <String, Object?>{
    "requestId": this.requestId,
  };
}

final class SendGreetingCommand {
  SendGreetingCommand({
    required String targetPersonaId,
    String? requestMessage,
    String source = 'profile',
    GreetingIntersectionRef? intersectionRef,
  }) : targetPersonaId = targetPersonaId.trim(),
       requestMessage = _normalizeGeneratedOptionalText(requestMessage),
       source = source.trim(),
       intersectionRef = intersectionRef {
    if (this.targetPersonaId.isEmpty) {
      throw ArgumentError.value(this.targetPersonaId, "targetPersonaId", 'must not be blank');
    }
    if (this.source.isEmpty) {
      throw ArgumentError.value(this.source, "source", 'must not be blank');
    }
  }

  final String targetPersonaId;
  final String? requestMessage;
  final String source;
  final GreetingIntersectionRef? intersectionRef;

  Map<String, Object?> toJson() => <String, Object?>{
    "targetPersonaId": this.targetPersonaId,
    if (this.requestMessage?.isNotEmpty == true) "requestMessage": this.requestMessage!,
    "source": this.source,
    if (this.intersectionRef?.isNotEmpty == true) "intersectionRef": this.intersectionRef!.toWire(),
  };
}

CloudOperationRequestPayload encodeUserGreetingRequestCancelGreetingRequestGeneratedRequest(CancelGreetingCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "requestId": request.requestId,
    },
  );
}

CloudOperationRequestPayload encodeUserGreetingRequestIgnoreGreetingRequestGeneratedRequest(IgnoreGreetingCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "requestId": request.requestId,
    },
  );
}

CloudOperationRequestPayload encodeUserGreetingRequestListGreetingInboxGeneratedRequest(ListGreetingRequestsQuery request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      if (request.status.isNotEmpty) "status": request.status,
      if (request.cursor?.isNotEmpty == true) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
    },
  );
}

CloudOperationRequestPayload encodeUserGreetingRequestListGreetingOutboxGeneratedRequest(ListGreetingRequestsQuery request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      if (request.status.isNotEmpty) "status": request.status,
      if (request.cursor?.isNotEmpty == true) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
    },
  );
}

CloudOperationRequestPayload encodeUserGreetingRequestReplyGreetingRequestGeneratedRequest(ReplyGreetingCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "requestId": request.requestId,
    },
  );
}

CloudOperationRequestPayload encodeUserGreetingRequestSendGreetingRequestGeneratedRequest(SendGreetingCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "targetPersonaId": request.targetPersonaId,
      if (request.requestMessage?.isNotEmpty == true) "requestMessage": request.requestMessage!,
      "source": request.source,
      if (request.intersectionRef?.isNotEmpty == true) "intersectionRef": request.intersectionRef!.toWire(),
    },
  );
}

