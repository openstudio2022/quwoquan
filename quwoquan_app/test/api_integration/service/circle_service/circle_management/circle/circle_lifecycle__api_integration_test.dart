// spec_ref: specs/feature-tree/circle-community/activity-member-governance/circle-lifecycle/spec.md#gwt-002

/// Circle aggregate API integration contract.
///
/// Run with:
/// ```
/// flutter test \
///   test/api_integration/service/circle_service/circle_management/circle/circle_lifecycle__api_integration_test.dart \
///   --dart-define=API_CONTRACT_ENV=gamma \
///   --dart-define=API_CONTRACT_BASE_URL=https://api.gamma.quwoquan.com
/// ```
///
/// Missing or unreachable Gamma configuration fails closed in [setUpAll].
library;

import 'package:flutter_test/flutter_test.dart';

import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/circle_api_contract_harness.dart';

CircleApiContractHarness? _harness;

CircleApiContractHarness get _api => _harness!;

void main() {
  setUpAll(() async {
    _harness = await CircleApiContractHarness.create();
    await _api.loginDisposableAccount('lifecycle-owner');
  });

  tearDownAll(() => _harness?.close());

  // contract.yaml: circle_create_with_owner / circle_update_owner_cas /
  //                circle_archive_named_transition
  group('circle_lifecycle_end_to_end', () {
    late String circleId;
    final createKey =
        'l3-circle-create-${DateTime.now().microsecondsSinceEpoch}';

    test('CreateCircle 返回稳定回执且同 key 重放', () async {
      final command = CreateCircleCommand(
        name: 'L3 契约圈 $createKey',
        category: 'tech',
        tags: const <String>['l3-contract'],
      );
      final receipt = await _api.withIdempotencyKey(
        createKey,
        () => _api.lifecycle.createCircle(command),
      );
      circleId = receipt.circleId;
      expect(circleId, isNotEmpty);
      expect(receipt.version, 1);
      expect(receipt.status, CircleStatus.active);
      expect(receipt.idempotentReplay, false);

      final replayReceipt = await _api.withIdempotencyKey(
        createKey,
        () => _api.lifecycle.createCircle(command),
      );
      expect(replayReceipt.circleId, circleId);
      expect(replayReceipt.idempotentReplay, true);
    });

    test('UpdateCircle 服务端 CAS 推进版本且详情回读一致', () async {
      final receipt = await _api.withIdempotencyKey(
        'l3-circle-update-$circleId',
        () => _api.lifecycle.updateCircle(
          UpdateCircleCommand(circleId: circleId, description: 'L3 更新描述'),
        ),
      );
      expect(receipt.version, 2);
      expect(receipt.status, CircleStatus.active);

      final detail = await _api.query.get(
        CircleDetailQuery(circleId: circleId),
      );
      expect(detail.description, 'L3 更新描述');
      expect(detail.version, 2, reason: '详情回读必须暴露聚合版本');
    });

    test('ArchiveCircle 命名迁移；已归档时 no-op receipt 不递增版本', () async {
      final command = ArchiveCircleCommand(circleId: circleId);
      final receipt = await _api.withIdempotencyKey(
        'l3-circle-archive-$circleId',
        () => _api.lifecycle.archiveCircle(command),
      );
      expect(receipt.status, CircleStatus.archived);
      expect(receipt.version, 3);

      final noopReceipt = await _api.withIdempotencyKey(
        'l3-circle-archive-noop-$circleId',
        () => _api.lifecycle.archiveCircle(command),
      );
      expect(noopReceipt.version, 3, reason: 'no-op 不得递增版本');
      expect(noopReceipt.idempotentReplay, true);

      final noopReplay = await _api.withIdempotencyKey(
        'l3-circle-archive-noop-$circleId',
        () => _api.lifecycle.archiveCircle(command),
      );
      expect(noopReplay.idempotentReplay, true);
    });
  });
}
