import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/testing.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/create_location_coordinator.dart';
import 'package:quwoquan_app/service/integration_service/external_integration/location/adapters/location_query_remote.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';

import '../../../support/runtime/cloud_boundary_test_scope.dart';

void main() {
  test('production composition 只装配 Remote Location adapter', () {
    final container = ProviderContainer(
      overrides: generatedClientBoundaryOverrides(
        transport: MockClient(
          (_) async => throw StateError('unexpected location transport call'),
        ),
      ),
    );
    addTearDown(container.dispose);

    expect(
      container.read(createLocationNearbyReaderProvider),
      isA<RemoteLocationQueryAdapter>(),
    );
    expect(
      container.read(createLocationSearchReaderProvider),
      isA<RemoteLocationQueryAdapter>(),
    );
    expect(
      container.read(createLocationCoordinatorProvider),
      isA<CreateLocationCoordinator>(),
    );
  });
}
