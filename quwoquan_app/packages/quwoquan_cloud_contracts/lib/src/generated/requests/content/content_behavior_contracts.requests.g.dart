// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 07b120d8c226ad653523b7a2965cf1f9e0f43704e848966de103c40df7ab319a

part of '../../../content/content_behavior_contracts.dart';

final class ReportContentBehaviorsCommand {
  ReportContentBehaviorsCommand({
    required List<ContentBehaviorEventWire> events,
  }) : events = List.unmodifiable(events) {
  }

  final List<ContentBehaviorEventWire> events;

  Map<String, Object?> toJson() => <String, Object?>{
    "events": this.events.map((value) => value.toWireMap()).toList(growable: false),
  };
}

CloudOperationRequestPayload encodeContentContentBehaviorFactReportBehaviorsGeneratedRequest(ReportContentBehaviorsCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "events": request.events.map((value) => value.toWireMap()).toList(growable: false),
    },
  );
}

