import 'package:quwoquan_app/cloud/runtime/generated/integration/integration_request_page_ids.g.dart';
import 'package:quwoquan_app/integration/external_integration/location/application/location_query_contracts.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef LocationInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

final class RemoteLocationQueryAdapter
    implements NearbyLocationReader, LocationSearchReader {
  const RemoteLocationQueryAdapter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final LocationInvocationContextFactory invocationContext;

  @override
  Future<LocationPoiListSlice> getNearbyLocations(
    NearbyLocationQueryParams query,
  ) {
    return client.integrationLocationGetNearbyLocations(
      query,
      context: invocationContext(IntegrationRequestPageIds.getNearbyLocations),
    );
  }

  @override
  Future<LocationPoiListSlice> searchLocations(
    LocationSearchQueryParams query,
  ) {
    return client.integrationLocationSearchLocations(
      query,
      context: invocationContext(IntegrationRequestPageIds.searchLocations),
    );
  }
}
