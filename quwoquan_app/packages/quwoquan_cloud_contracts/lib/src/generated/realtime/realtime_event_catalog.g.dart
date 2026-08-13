// Code generated from _shared/realtime_event_catalog.yaml. DO NOT EDIT.
// Payload fields remain owned by object-local contracts.

import 'chat_realtime_events.g.dart';
import 'feed_realtime_patch.g.dart';
import 'rtc_signal_payloads.g.dart';

export 'chat_realtime_events.g.dart';
export 'feed_realtime_patch.g.dart';
export 'rtc_signal_payloads.g.dart';
export 'shared_realtime_event_enums.g.dart';

sealed class RealtimeEventEnvelope {
  const RealtimeEventEnvelope({required this.wireType, this.eventId, required this.occurredAt});
  factory RealtimeEventEnvelope.fromWire(Map<String, Object?> wire, [String path = 'RealtimeEventEnvelope']) => decodeRealtimeEventEnvelope(wire, path);
  final String wireType;
  final String? eventId;
  final DateTime occurredAt;
  Map<String, Object?> toWire();
}

final class ChatRealtimeEventEnvelope extends RealtimeEventEnvelope {
  const ChatRealtimeEventEnvelope({required super.wireType, super.eventId, required super.occurredAt, required this.payload});
  final ChatRealtimeEventPayload payload;
  @override
  Map<String, Object?> toWire() => _realtimeEnvelopeToWire(wireType, eventId, occurredAt, payload.toWire());
}

final class RtcRealtimeEventEnvelope extends RealtimeEventEnvelope {
  const RtcRealtimeEventEnvelope({required super.wireType, super.eventId, required super.occurredAt, required this.payload});
  final RtcWsPayload payload;
  @override
  Map<String, Object?> toWire() => _realtimeEnvelopeToWire(wireType, eventId, occurredAt, payload.toWire());
}

final class UserSyncHintEventPayload {
  const UserSyncHintEventPayload({required this.userId, required this.latestSyncSeq});
  final String userId;
  final int latestSyncSeq;
  Map<String, Object?> toWire() => <String, Object?>{'userId': userId, 'latestSyncSeq': latestSyncSeq};
}

final class UserSyncHintRealtimeEventEnvelope extends RealtimeEventEnvelope {
  const UserSyncHintRealtimeEventEnvelope({required super.wireType, super.eventId, required super.occurredAt, required this.payload});
  final UserSyncHintEventPayload payload;
  @override
  Map<String, Object?> toWire() => _realtimeEnvelopeToWire(wireType, eventId, occurredAt, payload.toWire());
}

final class FeedPatchRealtimeEventEnvelope extends RealtimeEventEnvelope {
  const FeedPatchRealtimeEventEnvelope({required super.wireType, super.eventId, required super.occurredAt, required this.payload});
  final FeedRealtimePatch payload;
  @override
  Map<String, Object?> toWire() => _realtimeEnvelopeToWire(wireType, eventId, occurredAt, payload.toWire());
}

const realtimeEventOwnerByWireType = <String, String>{
  'ConversationAvatarUpdated': 'chat.conversation',
  'ConversationDissolved': 'chat.conversation',
  'ConversationMemberLeft': 'chat.conversation_membership',
  'ConversationMemberRemoved': 'chat.conversation_membership',
  'ConversationReadWatermarkAdvanced': 'chat.conversation_user_state',
  'ConversationRosterUpdated': 'chat.conversation',
  'ConversationUserSettingsChanged': 'chat.conversation_user_state',
  'GatheringConversationPolicyChanged': 'chat.conversation',
  'MessageRecalled': 'chat.message',
  'MessageSent': 'chat.message',
  'call.answered': 'rtc.call_session',
  'call.connected': 'rtc.call_session',
  'call.ended': 'rtc.call_session',
  'call.initiated': 'rtc.call_session',
  'call.ringing': 'rtc.call_session',
  'feed.patch': 'content.post',
  'participant.joined': 'rtc.call_session',
  'participant.left': 'rtc.call_session',
  'screen_share.started': 'rtc.call_session',
  'screen_share.stopped': 'rtc.call_session',
  'sync_hint': 'user.user_account',
};

String requireRealtimeEventOwner(String wireType) {
  final owner = realtimeEventOwnerByWireType[wireType];
  if (owner == null) { throw FormatException('Unsupported realtime event type: $wireType'); }
  return owner;
}


RealtimeEventEnvelope decodeRealtimeEventEnvelope(Map<String, Object?> wire, [String path = 'RealtimeEventEnvelope']) {
  _realtimeRequireExactFields(wire, const <String>{'type', 'eventId', 'occurredAt', 'payload'}, path);
  final wireType = _realtimeRequiredString(wire, 'type', '$path.type');
  requireRealtimeEventOwner(wireType);
  final eventId = _realtimeOptionalString(wire, 'eventId', '$path.eventId');
  final occurredAtRaw = _realtimeRequiredString(wire, 'occurredAt', '$path.occurredAt');
  final occurredAt = DateTime.tryParse(occurredAtRaw);
  if (occurredAt == null) throw FormatException('$path.occurredAt must be ISO-8601');
  final rawPayload = wire['payload'];
  if (rawPayload is! Map || rawPayload.keys.any((key) => key is! String)) throw FormatException('$path.payload must be an object');
  final payload = Map<String, dynamic>.from(rawPayload);
  switch (wireType) {
    case 'ConversationAvatarUpdated':
      return ChatRealtimeEventEnvelope(wireType: wireType, eventId: eventId, occurredAt: occurredAt, payload: decodeChatRealtimeEventPayload(eventType: wireType, payload: payload));
    case 'ConversationDissolved':
      return ChatRealtimeEventEnvelope(wireType: wireType, eventId: eventId, occurredAt: occurredAt, payload: decodeChatRealtimeEventPayload(eventType: wireType, payload: payload));
    case 'ConversationMemberLeft':
      return ChatRealtimeEventEnvelope(wireType: wireType, eventId: eventId, occurredAt: occurredAt, payload: decodeChatRealtimeEventPayload(eventType: wireType, payload: payload));
    case 'ConversationMemberRemoved':
      return ChatRealtimeEventEnvelope(wireType: wireType, eventId: eventId, occurredAt: occurredAt, payload: decodeChatRealtimeEventPayload(eventType: wireType, payload: payload));
    case 'ConversationReadWatermarkAdvanced':
      return ChatRealtimeEventEnvelope(wireType: wireType, eventId: eventId, occurredAt: occurredAt, payload: decodeChatRealtimeEventPayload(eventType: wireType, payload: payload));
    case 'ConversationRosterUpdated':
      return ChatRealtimeEventEnvelope(wireType: wireType, eventId: eventId, occurredAt: occurredAt, payload: decodeChatRealtimeEventPayload(eventType: wireType, payload: payload));
    case 'ConversationUserSettingsChanged':
      return ChatRealtimeEventEnvelope(wireType: wireType, eventId: eventId, occurredAt: occurredAt, payload: decodeChatRealtimeEventPayload(eventType: wireType, payload: payload));
    case 'GatheringConversationPolicyChanged':
      return ChatRealtimeEventEnvelope(wireType: wireType, eventId: eventId, occurredAt: occurredAt, payload: decodeChatRealtimeEventPayload(eventType: wireType, payload: payload));
    case 'MessageRecalled':
      return ChatRealtimeEventEnvelope(wireType: wireType, eventId: eventId, occurredAt: occurredAt, payload: decodeChatRealtimeEventPayload(eventType: wireType, payload: payload));
    case 'MessageSent':
      return ChatRealtimeEventEnvelope(wireType: wireType, eventId: eventId, occurredAt: occurredAt, payload: decodeChatRealtimeEventPayload(eventType: wireType, payload: payload));
    case 'call.answered':
      return RtcRealtimeEventEnvelope(wireType: wireType, eventId: eventId, occurredAt: occurredAt, payload: parseRtcWsPayload(wireType: wireType, payload: payload));
    case 'call.connected':
      return RtcRealtimeEventEnvelope(wireType: wireType, eventId: eventId, occurredAt: occurredAt, payload: parseRtcWsPayload(wireType: wireType, payload: payload));
    case 'call.ended':
      return RtcRealtimeEventEnvelope(wireType: wireType, eventId: eventId, occurredAt: occurredAt, payload: parseRtcWsPayload(wireType: wireType, payload: payload));
    case 'call.initiated':
      return RtcRealtimeEventEnvelope(wireType: wireType, eventId: eventId, occurredAt: occurredAt, payload: parseRtcWsPayload(wireType: wireType, payload: payload));
    case 'call.ringing':
      return RtcRealtimeEventEnvelope(wireType: wireType, eventId: eventId, occurredAt: occurredAt, payload: parseRtcWsPayload(wireType: wireType, payload: payload));
    case 'feed.patch':
      return FeedPatchRealtimeEventEnvelope(wireType: wireType, eventId: eventId, occurredAt: occurredAt, payload: parseFeedRealtimePatch(payload));
    case 'participant.joined':
      return RtcRealtimeEventEnvelope(wireType: wireType, eventId: eventId, occurredAt: occurredAt, payload: parseRtcWsPayload(wireType: wireType, payload: payload));
    case 'participant.left':
      return RtcRealtimeEventEnvelope(wireType: wireType, eventId: eventId, occurredAt: occurredAt, payload: parseRtcWsPayload(wireType: wireType, payload: payload));
    case 'screen_share.started':
      return RtcRealtimeEventEnvelope(wireType: wireType, eventId: eventId, occurredAt: occurredAt, payload: parseRtcWsPayload(wireType: wireType, payload: payload));
    case 'screen_share.stopped':
      return RtcRealtimeEventEnvelope(wireType: wireType, eventId: eventId, occurredAt: occurredAt, payload: parseRtcWsPayload(wireType: wireType, payload: payload));
    case 'sync_hint':
      _realtimeRequireExactFields(payload, const <String>{'userId', 'latestSyncSeq'}, 'UserSyncHintEventPayload');
      final userId = _realtimeRequiredString(payload, 'userId', 'UserSyncHintEventPayload.userId');
      final latestSyncSeq = payload['latestSyncSeq'];
      if (latestSyncSeq is! int || latestSyncSeq <= 0) throw FormatException('UserSyncHintEventPayload.latestSyncSeq must be positive integer');
      return UserSyncHintRealtimeEventEnvelope(wireType: wireType, eventId: eventId, occurredAt: occurredAt, payload: UserSyncHintEventPayload(userId: userId, latestSyncSeq: latestSyncSeq));
    default:
      throw FormatException('Unsupported realtime event type: $wireType');
  }
}

Map<String, Object?> _realtimeEnvelopeToWire(
  String wireType,
  String? eventId,
  DateTime occurredAt,
  Map<String, Object?> payload,
) => <String, Object?>{
  'type': wireType,
  if (eventId != null) 'eventId': eventId,
  'occurredAt': occurredAt.toUtc().toIso8601String(),
  'payload': payload,
};

void _realtimeRequireExactFields(Map<String, Object?> wire, Set<String> allowed, String path) {
  final unknown = wire.keys.where((key) => !allowed.contains(key)).toList(growable: false);
  if (unknown.isNotEmpty) throw FormatException('$path contains unknown fields: ${unknown.join(',')}');
}

String _realtimeRequiredString(Map<String, Object?> wire, String field, String path) {
  final value = wire[field];
  if (value is! String || value.trim().isEmpty) throw FormatException('$path must be a non-empty string');
  return value.trim();
}

String? _realtimeOptionalString(Map<String, Object?> wire, String field, String path) {
  final value = wire[field];
  if (value == null) return null;
  if (value is! String || value.trim().isEmpty) throw FormatException('$path must be a non-empty string');
  return value.trim();
}
