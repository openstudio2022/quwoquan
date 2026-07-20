import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/io_client.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/remote/search/search_query_remote.dart';
import 'package:quwoquan_app/cloud/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/cloud/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/cloud/runtime/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_contract.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_registry.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/core/services/remote_search_repository.dart';
import 'package:quwoquan_app/core/services/search_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../support/recording_cloud_operation_telemetry_sink.dart';

const _gatewayUrl = String.fromEnvironment(
  'GAMMA_GATEWAY_URL',
  defaultValue: 'https://gamma-api.quwoquan-env.test:19000',
);
const _gatewayResolveHost = String.fromEnvironment(
  'GAMMA_GATEWAY_RESOLVE_HOST',
);

final class _GammaSearchClientContext implements CloudClientContextProvider {
  const _GammaSearchClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'gamma-search-api-integration',
      deviceActorId: 'gamma-search-device',
      platform: 'test',
      appVersion: 'api-integration',
      locale: 'zh-CN',
    );
  }
}

void main() {
  test(
    'generated RemoteSearchRepository 通过 gateway 返回真实 canonical hits',
    () async {
      final httpClient = _buildGammaHttpClient();
      final telemetry = RecordingCloudOperationTelemetrySink();
      addTearDown(httpClient.close);
      final client = buildGeneratedCloudOperationClient(
        httpClient: httpClient,
        clientContextProvider: const _GammaSearchClientContext(),
        telemetrySink: telemetry,
        environment: CloudRuntimeEnvironment(
          environment: CloudEnvironment.gamma,
          gatewayBaseUri: Uri.parse(_gatewayUrl),
        ),
      );
      final remote = RemoteCanonicalSearchQuery(
        client: client,
        invocationContext: (clientPageId) => CloudOperationInvocationContext(
          surfaceId: AppUiSurfaces.globalSearchNetworkResults.id,
          routeId: AppUiSurfaces.globalSearchNetworkResults.routeId,
          clientPageId: clientPageId,
          actor: const CloudOperationActorContext(
            deviceActorId: 'gamma-search-device',
          ),
        ),
      );
      final repository = RemoteSearchRepository(remoteQuery: remote);

      final response = await repository.search(
        const SearchRequest(
          query: '西湖',
          mode: SearchMode.result,
          objectTypes: <SearchObjectType>{
            SearchObjectType.contentPost,
            SearchObjectType.entityHomepage,
            SearchObjectType.locationPlace,
            SearchObjectType.userProfile,
          },
          limit: 20,
        ),
      );

      expect(response.searchRequestId, isNotEmpty);
      expect(response.hits, isNotEmpty);
      expect(
        response.hits.every(
          (hit) => hit.objectId.isNotEmpty && hit.title.isNotEmpty,
        ),
        isTrue,
      );
      expect(
        response.hits.any(
          (hit) =>
              hit.objectType == SearchObjectType.contentPost ||
              hit.objectType == SearchObjectType.entityHomepage ||
              hit.objectType == SearchObjectType.locationPlace,
        ),
        isTrue,
      );
      expect(telemetry.events, hasLength(1));
      expect(telemetry.events.single.succeeded, isTrue);
      expect(telemetry.events.single.requestId, isNotEmpty);
      expect(telemetry.events.single.traceId, isNotEmpty);
    },
  );
}

CloudHttpClient _buildGammaHttpClient() {
  if (_gatewayResolveHost.trim().isEmpty) {
    return CloudHttpClient();
  }
  final gateway = Uri.parse(_gatewayUrl);
  final nativeClient = HttpClient();
  nativeClient.findProxy = (_) => 'DIRECT';
  nativeClient.badCertificateCallback = (_, host, _) => host == gateway.host;
  nativeClient.connectionFactory = (uri, proxyHost, proxyPort) {
    if (uri.host != gateway.host) {
      throw StateError(
        'gamma search integration client rejected unexpected host ${uri.host}',
      );
    }
    return Socket.startConnect(_gatewayResolveHost, uri.port).then((task) {
      final secureSocket = task.socket.then<Socket>(
        (socket) => SecureSocket.secure(
          socket,
          host: uri.host,
          onBadCertificate: (_) => uri.host == gateway.host,
        ),
      );
      return ConnectionTask.fromSocket<Socket>(secureSocket, task.cancel);
    });
  };
  return CloudHttpClient(client: IOClient(nativeClient));
}
