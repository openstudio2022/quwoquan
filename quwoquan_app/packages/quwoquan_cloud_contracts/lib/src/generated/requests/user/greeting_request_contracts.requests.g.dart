// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 80b68db6b546ae955959cb31a73c5fdfb60da766b906dc9529a837191ea4a01e

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
}

final class SendGreetingCommand {
  SendGreetingCommand({
    required String targetPersonaId,
    String? requestMessage,
    String source = 'profile',
  }) : targetPersonaId = targetPersonaId.trim(),
       requestMessage = _normalizeGeneratedOptionalText(requestMessage),
       source = source.trim() {
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
    },
  );
}

