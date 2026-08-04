import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('canonical realtime envelope round-trips through one tagged union', () {
    final event = RealtimeEventEnvelope.fromWire(<String, Object?>{
      'type': 'sync_hint',
      'eventId': 'sync-event-1',
      'occurredAt': '2026-08-04T12:00:00Z',
      'payload': <String, Object?>{
        'userId': 'user-1',
        'latestSyncSeq': 9,
      },
    });

    expect(event, isA<UserSyncHintRealtimeEventEnvelope>());
    expect(event.toWire(), <String, Object?>{
      'type': 'sync_hint',
      'eventId': 'sync-event-1',
      'occurredAt': '2026-08-04T12:00:00.000Z',
      'payload': <String, Object?>{
        'userId': 'user-1',
        'latestSyncSeq': 9,
      },
    });
  });

  test('unknown realtime type and payload field fail closed', () {
    expect(
      () => RealtimeEventEnvelope.fromWire(<String, Object?>{
        'type': 'future.event',
        'occurredAt': '2026-08-04T12:00:00Z',
        'payload': <String, Object?>{},
      }),
      throwsFormatException,
    );
    expect(
      () => RealtimeEventEnvelope.fromWire(<String, Object?>{
        'type': 'sync_hint',
        'occurredAt': '2026-08-04T12:00:00Z',
        'payload': <String, Object?>{
          'userId': 'user-1',
          'latestSyncSeq': 9,
          'legacySeq': 8,
        },
      }),
      throwsFormatException,
    );
  });
}
