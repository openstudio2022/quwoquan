import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('inbox query preserves opaque keyset cursor', () {
    final payload = encodeChatChatInboxViewListInboxGeneratedRequest(
      ChatListInboxQuery(cursor: 'opaque-keyset', limit: 30),
    );

    expect(payload.queryParameters, <String, String>{
      'limit': '30',
      'cursor': 'opaque-keyset',
    });
  });
}
