import 'package:quwoquan_app/service/integration_service/external_integration/connector_connection/adapters/connector_management_remote.dart';
import 'package:quwoquan_app/service/integration_service/external_integration/connector_definition/adapters/connector_definition_remote.dart';
import 'package:quwoquan_app/service/integration_service/external_integration/connector_invocation/adapters/connector_invocation_remote.dart';
import 'package:quwoquan_app/service/integration_service/external_integration/location/adapters/location_query_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// integration domain 的 production Remote adapter 种类。
///
/// 只有本文件可以命名 `Remote*` 实现；Provider 侧只声明 typed port 泛型。
enum IntegrationProductionAdapter { connectorManagement, locationQuery }

/// integration domain 的唯一 production 装配入口。
final class IntegrationProductionComposition {
  const IntegrationProductionComposition._();

  static T generatedAdapter<T>(
    IntegrationProductionAdapter adapter, {
    required GeneratedCloudOperationClient client,
    required Object invocationContext,
  }) {
    final dynamic context = invocationContext;
    final Object result = switch (adapter) {
      IntegrationProductionAdapter.connectorManagement =>
        RemoteConnectorManagementFacet(
          client: client,
          invocationContext: context,
          definitionReader: RemoteConnectorDefinitionReader(
            client: client,
            invocationContext: (clientPageId) => context(clientPageId),
          ),
          invocationReader: RemoteConnectorInvocationReader(
            client: client,
            invocationContext: (clientPageId) => context(clientPageId),
          ),
        ),
      IntegrationProductionAdapter.locationQuery => RemoteLocationQueryAdapter(
        client: client,
        invocationContext: context,
      ),
    };
    return result as T;
  }
}
