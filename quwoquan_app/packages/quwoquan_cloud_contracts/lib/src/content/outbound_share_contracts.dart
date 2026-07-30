import '../operation_request_payload.dart';
part '../generated/requests/content/outbound_share_contracts.requests.g.dart';

enum OutboundShareChannel {
  systemShare('system_share'),
  wechatFriend('wechat_friend'),
  wechatMoments('wechat_moments');

  const OutboundShareChannel(this.wireValue);

  final String wireValue;

  static OutboundShareChannel fromString(String raw) => switch (raw.trim()) {
    'system_share' => OutboundShareChannel.systemShare,
    'wechat_friend' => OutboundShareChannel.wechatFriend,
    'wechat_moments' => OutboundShareChannel.wechatMoments,
    _ => throw FormatException('Unknown OutboundShareChannel: $raw'),
  };
}

enum OutboundShareDestinationKind {
  externalApp('external_app');

  const OutboundShareDestinationKind(this.wireValue);

  final String wireValue;

  static OutboundShareDestinationKind fromString(String raw) => switch (raw
      .trim()) {
    'external_app' => OutboundShareDestinationKind.externalApp,
    _ => throw FormatException('Unknown OutboundShareDestinationKind: $raw'),
  };
}

final class ContentOutboundShareFactResult {
  const ContentOutboundShareFactResult({
    required this.eventId,
    required this.postId,
    required this.channel,
    required this.referralId,
    required this.occurredAt,
    required this.replayed,
  });

  final String eventId;
  final String postId;
  final String channel;
  final String referralId;
  final DateTime occurredAt;
  final bool replayed;
}

abstract interface class ContentOutboundShareAppendWriter {
  Future<ContentOutboundShareFactResult> appendOutboundShare(
    CreateContentOutboundShareCommand command,
  );
}

ContentOutboundShareFactResult decodeContentOutboundShareFactResult(
  Object? value,
) {
  if (value is! Map) {
    throw const FormatException(
      'ContentOutboundShareFactResult must be an object',
    );
  }
  final map = value.map((key, item) => MapEntry(key.toString(), item));
  final occurredAt = DateTime.tryParse(_string(map, 'occurredAt'));
  final replayed = map['replayed'];
  if (occurredAt == null)
    throw const FormatException('occurredAt must be RFC3339');
  if (replayed is! bool)
    throw const FormatException('replayed must be a boolean');
  return ContentOutboundShareFactResult(
    eventId: _string(map, 'eventId'),
    postId: _string(map, 'postId'),
    channel: _string(map, 'channel'),
    referralId: _string(map, 'referralId'),
    occurredAt: occurredAt.toUtc(),
    replayed: replayed,
  );
}

String _string(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! String || value.trim().isEmpty) {
    throw FormatException('$key must be a non-empty string');
  }
  return value.trim();
}
