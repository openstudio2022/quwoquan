// spec_ref: specs/feature-tree/runtime/runtime-external-integration/user-connector-capability-gateway/spec.md#gwt-001
// readiness_case: connector_invocation_list_connector_invocations_app_api
// readiness_case: connector_invocation_get_connector_invocation_app_api

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/integration_api_contract_harness.dart';

IntegrationApiContractHarness? _harness;

IntegrationApiContractHarness get _api => _harness!;

void main() {
  setUpAll(() async => _harness = await IntegrationApiContractHarness.create());
  tearDownAll(() => _harness?.close());

  test(
    'fresh account 通过 production Remote 读取合法空列表且 missing ID 返回 typed 404',
    () async {
      final invocations = await _api.invocations.listConnectorInvocations();
      expect(invocations, isEmpty);

      final missingId =
          'missing-invocation-${DateTime.now().toUtc().microsecondsSinceEpoch}';
      await expectLater(
        _api.invocations.getConnectorInvocation(invocationId: missingId),
        throwsA(
          isA<CloudException>()
              .having((error) => error.type, 'type', CloudErrorType.notFound)
              .having((error) => error.statusCode, 'statusCode', 404)
              .having(
                (error) => error.sourceOperationId,
                'sourceOperationId',
                AppCloudOperationIds
                    .integrationConnectorInvocationGetConnectorInvocation,
              ),
        ),
      );

      final events = await _api.telemetry.waitForEvents(minimumCount: 3);
      final connectorEvents = events
          .where(
            (event) =>
                event.canonicalOperationId ==
                    AppCloudOperationIds
                        .integrationConnectorInvocationListConnectorInvocations ||
                event.canonicalOperationId ==
                    AppCloudOperationIds
                        .integrationConnectorInvocationGetConnectorInvocation,
          )
          .toList(growable: false);
      expect(
        connectorEvents.map((event) => event.canonicalOperationId),
        <String>[
          AppCloudOperationIds
              .integrationConnectorInvocationListConnectorInvocations,
          AppCloudOperationIds
              .integrationConnectorInvocationGetConnectorInvocation,
        ],
      );
      expect(connectorEvents.first.succeeded, isTrue);
      expect(connectorEvents.last.succeeded, isFalse);
      expect(connectorEvents.last.statusCode, 404);
      expect(
        connectorEvents.every(
          (event) => event.requestId.isNotEmpty && event.traceId.isNotEmpty,
        ),
        isTrue,
      );
    },
  );
}
