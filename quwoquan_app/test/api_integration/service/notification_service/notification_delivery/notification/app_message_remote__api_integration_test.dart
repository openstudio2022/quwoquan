// spec_ref: specs/feature-tree/chat-conversation/list-detail-message-delivery/conversation-list-source-switch/spec.md#gwt-001

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/notification_api_contract_harness.dart';

void main() {
  late NotificationApiContractHarness harness;

  setUpAll(() async => harness = await NotificationApiContractHarness.create());
  tearDownAll(() => harness.close());

  test('generated Remote 列出 AppMessage inbox slice', () async {
    final stopwatch = Stopwatch()..start();
    final slice = await harness.query.listAppMessages(
      ListAppMessagesQuery(limit: 20),
    );
    stopwatch.stop();

    expect(stopwatch.elapsedMilliseconds, lessThan(1500));
    expect(slice.items, isA<List<AppMessage>>());
  });

  test('generated Remote 返回 unread count slice', () async {
    final unread = await harness.query.getUnreadCount(
      GetAppMessageUnreadCountQuery(),
    );

    expect(unread.unreadCount, greaterThanOrEqualTo(0));
  });
}
