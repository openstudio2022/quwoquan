// Code generated from canonical domain contracts. DO NOT EDIT.
// ContractGraph SHA256: 93359367b8614f01bb5e1c51e37af383332b01f117cc1c6cf39e4fdf838e49d2

library;

import '../operation_request_payload.dart';

part '../generated/requests/ops/ops_operation_contracts.g.requests.g.dart';

enum VisitTargetType {
  page("page"),
  post("post"),
  circle("circle"),
  user("user");

  const VisitTargetType(this.wireName);

  final String wireName;

  static VisitTargetType fromWire(Object? value, String path) {
    return switch (value) {
      "page" => VisitTargetType.page,
      "post" => VisitTargetType.post,
      "circle" => VisitTargetType.circle,
      "user" => VisitTargetType.user,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

final class EventRecordBatchReceipt {
  const EventRecordBatchReceipt({
    required this.acceptedCount,
    required this.duplicateBatch,
  });

  final int acceptedCount;
  final bool duplicateBatch;

  factory EventRecordBatchReceipt.fromWire(Map<String, Object?> map, [String path = "EventRecordBatchReceipt"]) {
    _rejectUnknownFields(map, const <String>{"acceptedCount", "duplicateBatch"}, path);
    return EventRecordBatchReceipt(
      acceptedCount: _requiredInt(map["acceptedCount"], '$path.acceptedCount'),
      duplicateBatch: _requiredBool(map["duplicateBatch"], '$path.duplicateBatch'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "acceptedCount": acceptedCount,
    "duplicateBatch": duplicateBatch,
  };
}

final class RecordVisitReceipt {
  const RecordVisitReceipt({
    required this.targetType,
    required this.targetKey,
    required this.visitCount,
    required this.occurredAt,
    required this.replayed,
  });

  final VisitTargetType targetType;
  final String targetKey;
  final int visitCount;
  final DateTime occurredAt;
  final bool replayed;

  factory RecordVisitReceipt.fromWire(Map<String, Object?> map, [String path = "RecordVisitReceipt"]) {
    _rejectUnknownFields(map, const <String>{"targetType", "targetKey", "visitCount", "occurredAt", "replayed"}, path);
    return RecordVisitReceipt(
      targetType: VisitTargetType.fromWire(map["targetType"], '$path.targetType'),
      targetKey: _requiredNonBlankString(map["targetKey"], '$path.targetKey'),
      visitCount: _requiredInt(map["visitCount"], '$path.visitCount'),
      occurredAt: _requiredTimestamp(map["occurredAt"], '$path.occurredAt'),
      replayed: _requiredBool(map["replayed"], '$path.replayed'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "targetType": targetType.wireName,
    "targetKey": targetKey,
    "visitCount": visitCount,
    "occurredAt": occurredAt.toUtc().toIso8601String(),
    "replayed": replayed,
  };
}

final class StartupTelemetryBatchReceipt {
  const StartupTelemetryBatchReceipt({
    required this.acceptedCount,
    required this.duplicateBatch,
  });

  final int acceptedCount;
  final bool duplicateBatch;

  factory StartupTelemetryBatchReceipt.fromWire(Map<String, Object?> map, [String path = "StartupTelemetryBatchReceipt"]) {
    _rejectUnknownFields(map, const <String>{"acceptedCount", "duplicateBatch"}, path);
    return StartupTelemetryBatchReceipt(
      acceptedCount: _requiredInt(map["acceptedCount"], '$path.acceptedCount'),
      duplicateBatch: _requiredBool(map["duplicateBatch"], '$path.duplicateBatch'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "acceptedCount": acceptedCount,
    "duplicateBatch": duplicateBatch,
  };
}

EventRecordBatchReceipt decodeEventRecordBatchReceipt(Object? response) =>
    EventRecordBatchReceipt.fromWire(_requiredObject(response, "EventRecordBatchReceipt"), "EventRecordBatchReceipt");

RecordVisitReceipt decodeRecordVisitReceipt(Object? response) =>
    RecordVisitReceipt.fromWire(_requiredObject(response, "RecordVisitReceipt"), "RecordVisitReceipt");

StartupTelemetryBatchReceipt decodeStartupTelemetryBatchReceipt(Object? response) =>
    StartupTelemetryBatchReceipt.fromWire(_requiredObject(response, "StartupTelemetryBatchReceipt"), "StartupTelemetryBatchReceipt");

Map<String, Object?> _requiredObject(Object? value, String path) {
  if (value is! Map<Object?, Object?>) {
    throw FormatException('$path must be an object');
  }
  final result = <String, Object?>{};
  for (final entry in value.entries) {
    final key = entry.key;
    if (key is! String) {
      throw FormatException('$path contains a non-string field name');
    }
    result[key] = entry.value;
  }
  return result;
}

void _rejectUnknownFields(
  Map<String, Object?> value,
  Set<String> allowed,
  String path,
) {
  final unknown = value.keys.where((key) => !allowed.contains(key)).toList()
    ..sort();
  if (unknown.isNotEmpty) {
    throw FormatException('$path contains unknown fields: ${unknown.join(', ')}');
  }
}

String _requiredString(Object? value, String path) {
  if (value is! String) throw FormatException('$path must be a string');
  return value;
}

String _requiredNonBlankString(Object? value, String path) {
  final result = _requiredString(value, path);
  if (result.trim().isEmpty) {
    throw FormatException('$path must not be blank');
  }
  return result;
}

DateTime _requiredTimestamp(Object? value, String path) {
  final result = _requiredString(value, path);
  final parsed = DateTime.tryParse(result);
  if (parsed == null) {
    throw FormatException('$path must be an ISO-8601 timestamp');
  }
  return parsed;
}

int _requiredInt(Object? value, String path) {
  if (value is! int) throw FormatException('$path must be an int');
  return value;
}

bool _requiredBool(Object? value, String path) {
  if (value is! bool) throw FormatException('$path must be a bool');
  return value;
}
