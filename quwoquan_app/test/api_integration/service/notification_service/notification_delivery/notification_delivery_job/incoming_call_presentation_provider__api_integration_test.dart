// spec_ref: specs/feature-tree/chat-conversation/realtime-call/one-to-one-call/spec.md#gwt-003
/// 受管来电 Provider 展示 receipt 的 production Remote ACK runner。
///
/// access token、deliveryKey 与设备身份只允许由进程环境注入，禁止进入
/// dart-define、日志和断言。当前不登记 readiness_case：该 source runner 只消费同一
/// 次真实物理展示产生的短时 receipt；完整 realtime/push/CallKit、timeline readback 与
/// Android+iPhone ResultBundle 由环境 UAT 独立验收。
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    as cloud;

import '../../../../../support/runtime/api_contract/notification_api_contract_harness.dart';

void main() {
  test(
    'production Remote acknowledges one fresh physical incoming-call presentation receipt',
    () async {
      final harness = await NotificationIncomingCallApiContractHarness.create();
      addTearDown(harness.close);

      await harness.writer.acknowledge(harness.receipt);

      final events = await harness.telemetry.waitForEvents(minimumCount: 1);
      if (events.length != 1 ||
          !events.single.succeeded ||
          events.single.canonicalOperationId !=
              cloud
                  .AppCloudOperationIds
                  .notificationNotificationDeliveryJobAckIncomingCallPresentation) {
        throw StateError(
          'incoming-call presentation did not emit one canonical successful ACK',
        );
      }
    },
  );
}
