// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 80b68db6b546ae955959cb31a73c5fdfb60da766b906dc9529a837191ea4a01e

part of '../../../content/content_behavior_contracts.dart';

final class ReportContentBehaviorsCommand {
  ReportContentBehaviorsCommand({
    required List<ContentBehaviorEventWire> events,
  }) : events = List.unmodifiable(events) {
  }

  final List<ContentBehaviorEventWire> events;
}

CloudOperationRequestPayload encodeContentContentBehaviorFactReportBehaviorsGeneratedRequest(ReportContentBehaviorsCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "events": request.events.map((value) => value.toWireMap()).toList(growable: false),
    },
  );
}

