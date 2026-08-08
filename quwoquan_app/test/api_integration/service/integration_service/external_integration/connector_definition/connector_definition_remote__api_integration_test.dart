// spec_ref: specs/feature-tree/runtime/runtime-external-integration/user-connector-capability-gateway/spec.md#gwt-001
// readiness_case: connector_definition_list_connector_definitions_app_api
// readiness_case: connector_definition_get_connector_definition_app_api

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/integration_api_contract_harness.dart';

IntegrationApiContractHarness? _harness;

IntegrationApiContractHarness get _api => _harness!;

void main() {
  setUpAll(() async => _harness = await IntegrationApiContractHarness.create());
  tearDownAll(() => _harness?.close());

  test('production Remote 通过真实 gateway 列出 catalog 并按返回 ID 读取同一定义', () async {
    final definitions = await _api.definitions.listConnectorDefinitions();

    expect(definitions, isNotEmpty, reason: '目标环境必须发布真实 Connector catalog');
    expect(
      definitions.every(
        (definition) =>
            definition.connectorId.isNotEmpty &&
            definition.capabilities.isNotEmpty &&
            definition.releaseDigest.isNotEmpty,
      ),
      isTrue,
    );

    final listed = definitions.first;
    final detail = await _api.definitions.getConnectorDefinition(
      connectorId: listed.connectorId,
    );
    expect(detail.toWire(), listed.toWire());

    final events = await _api.telemetry.waitForEvents(minimumCount: 3);
    final connectorEvents = events
        .where(
          (event) =>
              event.canonicalOperationId ==
                  AppCloudOperationIds
                      .integrationConnectorDefinitionListConnectorDefinitions ||
              event.canonicalOperationId ==
                  AppCloudOperationIds
                      .integrationConnectorDefinitionGetConnectorDefinition,
        )
        .toList(growable: false);
    expect(connectorEvents.map((event) => event.canonicalOperationId), <String>[
      AppCloudOperationIds
          .integrationConnectorDefinitionListConnectorDefinitions,
      AppCloudOperationIds.integrationConnectorDefinitionGetConnectorDefinition,
    ]);
    expect(connectorEvents.every((event) => event.succeeded), isTrue);
    expect(
      connectorEvents.every(
        (event) => event.requestId.isNotEmpty && event.traceId.isNotEmpty,
      ),
      isTrue,
    );
  });
}
