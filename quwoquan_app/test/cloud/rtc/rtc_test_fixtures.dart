import 'dart:convert';

/// 与 rtc-service `GET /v1/rtc/calls` 响应形状一致（`items` + `cursor`），供 wire 单测复用。
String rtcListCallsResponseJsonWithCursor() {
  return jsonEncode({
    'items': [
      {
        '_id': 'call_x',
        'callType': 'audio',
        'status': 'ended',
        'initiatorId': 'u1',
        'roomId': 'room_x',
        'maxParticipants': 2,
        'participantCount': 1,
        'createdAt': '2026-01-01T00:00:00Z',
        'updatedAt': '2026-01-01T00:00:00Z',
      },
    ],
    'cursor': 'opaque_next',
  });
}
