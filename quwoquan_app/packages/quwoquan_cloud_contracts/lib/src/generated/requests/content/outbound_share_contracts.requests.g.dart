// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 80b68db6b546ae955959cb31a73c5fdfb60da766b906dc9529a837191ea4a01e

part of '../../../content/outbound_share_contracts.dart';

String? _normalizeGeneratedOptionalText(String? value) {
  final normalized = value?.trim();
  return normalized == null || normalized.isEmpty ? null : normalized;
}

final class CreateContentOutboundShareCommand {
  CreateContentOutboundShareCommand({
    required String postId,
    required OutboundShareChannel channel,
    required OutboundShareDestinationKind destinationKind,
    String? destination,
    required String referralId,
    required String providerReceiptId,
    required DateTime clientConfirmedAt,
  }) : postId = postId.trim(),
       channel = channel,
       destinationKind = destinationKind,
       destination = _normalizeGeneratedOptionalText(destination),
       referralId = referralId.trim(),
       providerReceiptId = providerReceiptId.trim(),
       clientConfirmedAt = clientConfirmedAt.toUtc() {
    if (this.postId.isEmpty) {
      throw ArgumentError.value(this.postId, "postId", 'must not be blank');
    }
    if (this.referralId.isEmpty) {
      throw ArgumentError.value(this.referralId, "referralId", 'must not be blank');
    }
    if (this.providerReceiptId.isEmpty) {
      throw ArgumentError.value(this.providerReceiptId, "providerReceiptId", 'must not be blank');
    }
  }

  final String postId;
  final OutboundShareChannel channel;
  final OutboundShareDestinationKind destinationKind;
  final String? destination;
  final String referralId;
  final String providerReceiptId;
  final DateTime clientConfirmedAt;
}

CloudOperationRequestPayload encodeContentOutboundShareFactCreateOutboundShareGeneratedRequest(CreateContentOutboundShareCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "postId": request.postId,
    },
    body: <String, Object?>{
      "channel": switch (request.channel) { OutboundShareChannel.systemShare => "system_share", OutboundShareChannel.wechatFriend => "wechat_friend", OutboundShareChannel.wechatMoments => "wechat_moments", },
      "destinationKind": switch (request.destinationKind) { OutboundShareDestinationKind.externalApp => "external_app", },
      if (request.destination != null) "destination": request.destination!,
      "referralId": request.referralId,
      "providerReceiptId": request.providerReceiptId,
      "clientConfirmedAt": request.clientConfirmedAt.toUtc().toIso8601String(),
      "deliverySucceeded": true,
    },
  );
}

