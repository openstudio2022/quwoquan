// Code generated from canonical domain contracts. DO NOT EDIT.
// ContractGraph SHA256: 216475b7580978f5946c482640af45d09b2377ec753e34244c4db530a81cf051

library;

import '../operation_request_payload.dart';
import "../generated/realtime/realtime_event_catalog.g.dart";

export "../generated/realtime/realtime_event_catalog.g.dart";

part '../generated/requests/realtime/realtime_operation_contracts.g.requests.g.dart';

final class ConnectionTicket {
  const ConnectionTicket({required this.ticket, required this.expiresAt});

  final String ticket;
  final DateTime expiresAt;

  factory ConnectionTicket.fromWire(
    Map<String, Object?> map, [
    String path = "ConnectionTicket",
  ]) {
    _rejectUnknownFields(map, const <String>{"ticket", "expiresAt"}, path);
    return ConnectionTicket(
      ticket: _requiredString(map["ticket"], '$path.ticket'),
      expiresAt: _requiredTimestamp(map["expiresAt"], '$path.expiresAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "ticket": ticket,
    "expiresAt": expiresAt.toUtc().toIso8601String(),
  };
}

final class LongPollResponse {
  const LongPollResponse({
    required this.events,
    required this.nextCursor,
    required this.transportResumed,
  });

  final List<RealtimeEventEnvelope> events;
  final String nextCursor;
  final bool transportResumed;

  factory LongPollResponse.fromWire(
    Map<String, Object?> map, [
    String path = "LongPollResponse",
  ]) {
    _rejectUnknownFields(map, const <String>{
      "events",
      "nextCursor",
      "transportResumed",
    }, path);
    return LongPollResponse(
      events: List<RealtimeEventEnvelope>.unmodifiable(
        _requiredList(map["events"], '$path.events').asMap().entries.map(
          (entry) => RealtimeEventEnvelope.fromWire(
            _requiredObject(entry.value, '$path.events' + '[${entry.key}]'),
            '$path.events' + '[${entry.key}]',
          ),
        ),
      ),
      nextCursor: _requiredString(map["nextCursor"], '$path.nextCursor'),
      transportResumed: _requiredBool(
        map["transportResumed"],
        '$path.transportResumed',
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "events": events.map((value) => value.toWire()).toList(growable: false),
    "nextCursor": nextCursor,
    "transportResumed": transportResumed,
  };
}

ConnectionTicket decodeConnectionTicket(Object? response) =>
    ConnectionTicket.fromWire(
      _requiredObject(response, "ConnectionTicket"),
      "ConnectionTicket",
    );

LongPollResponse decodeLongPollResponse(Object? response) =>
    LongPollResponse.fromWire(
      _requiredObject(response, "LongPollResponse"),
      "LongPollResponse",
    );

void decodeEmptyResponse(Object? response) {
  if (response != null) {
    throw const FormatException('empty response must not contain a body');
  }
}

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
    throw FormatException(
      '$path contains unknown fields: ${unknown.join(', ')}',
    );
  }
}

String _requiredString(Object? value, String path) {
  if (value is! String) throw FormatException('$path must be a string');
  return value;
}

DateTime _requiredTimestamp(Object? value, String path) {
  final result = _requiredString(value, path);
  final parsed = DateTime.tryParse(result);
  if (parsed == null) {
    throw FormatException('$path must be an ISO-8601 timestamp');
  }
  return parsed;
}

bool _requiredBool(Object? value, String path) {
  if (value is! bool) throw FormatException('$path must be a bool');
  return value;
}

List<Object?> _requiredList(Object? value, String path) {
  if (value is! List<Object?>) {
    throw FormatException('$path must be a list');
  }
  return value;
}
