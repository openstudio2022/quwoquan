import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('AssistantSession query encoders own path and keyset query', () {
    final list =
        encodeAssistantAssistantSessionListAssistantSessionsGeneratedRequest(
          AssistantSessionListQuery(limit: 40, cursor: ' cursor-1 '),
        );
    final byId =
        encodeAssistantAssistantSessionGetAssistantSessionGeneratedRequest(
          AssistantSessionByIdQuery(sessionId: ' session-1 '),
        );

    expect(list.queryParameters, <String, String>{
      'limit': '40',
      'cursor': 'cursor-1',
    });
    expect(byId.pathParameters, <String, String>{'sessionId': 'session-1'});
  });

  test('AssistantSession decoder preserves the canonical wire', () {
    final decoded = decodeAssistantSessionWire(<String, Object?>{
      'sessionId': 'session-1',
      'userId': 'user-1',
      'state': 'active',
      'activeTurnId': '',
      'lastTurnId': 'turn-1',
      'summary': '',
      'createdAt': '2026-07-28T00:00:00Z',
      'updatedAt': '2026-07-28T00:01:00Z',
    });

    expect(decoded.sessionId, 'session-1');
    expect(decoded.activeTurnId, isEmpty);
    expect(decoded.summary, isEmpty);
    expect(decoded.updatedAt, '2026-07-28T00:01:00Z');
  });

  test('AssistantSession list decoder is strict and keeps nullable cursor', () {
    final page = decodeAssistantSessionListView(<String, Object?>{
      'items': <Object?>[
        <String, Object?>{
          'sessionId': 'session-1',
          'userId': 'user-1',
          'state': 'active',
          'activeTurnId': '',
          'lastTurnId': '',
          'summary': '摘要',
          'createdAt': '2026-07-28T00:00:00Z',
          'updatedAt': '2026-07-28T00:01:00Z',
        },
      ],
      'nextCursor': null,
    });

    expect(page.items, hasLength(1));
    expect(page.nextCursor, isNull);
    expect(
      () => decodeAssistantSessionWire(<String, Object?>{
        'userId': 'user-1',
        'state': 'active',
        'activeTurnId': '',
        'lastTurnId': '',
        'summary': '',
        'createdAt': '2026-07-28T00:00:00Z',
        'updatedAt': '2026-07-28T00:01:00Z',
      }),
      throwsFormatException,
    );
  });
}
